import logging
import math
import os
import queue
import threading
import time
from collections import Counter

import cv2

from cocbot.core.config import AppConfig
from cocbot.core.notify import Notifier
from cocbot.core.paths import user_path
from cocbot.vision.state_detection import ScreenState, StateGuard, StateTimeout

logger = logging.getLogger(__name__)


DEFAULT_WAITS = {
    AppConfig.ATTACK_BTN_HOME: 0.5,
    AppConfig.FIND_BTN: 0.5,
    AppConfig.NXT_BTN: 1.5,
    AppConfig.ATTACK_BTN: 0.5,
    AppConfig.SURR_BTN: 1.0,
    AppConfig.SURR_CONF: 1.0,
    AppConfig.RETURN_HOME: 0.5,
    AppConfig.RETRY_BTN_1: 0.5,
    AppConfig.RETRY_BTN_2: 0.5,
    AppConfig.RETRY_BTN_3: 0.5,
    "scan_base_first": 3.0,
    "scan_base_retry": 2.0,
    "scan_treasures_first": 1.0,
    "scan_treasures_retry": 0.5,
    "scan_post_interval": 0.3,
    "scan_post_timeout": 12.0,
    "attack_settle": 5.0,
    "attack_wave_settle": 5.0,
}

# ntfy.sh caps attachments at 2 MB, so notification captures are downscaled and
# JPEG-encoded to stay comfortably under that limit.
NOTIFY_IMAGE_MAX_WIDTH = 1280
NOTIFY_IMAGE_QUALITY = 75

# The post-battle YOLO model sometimes labels one on-screen row as two different
# resources (e.g. the Gold row also tagged as Elixir). Boxes overlapping this
# much are treated as the same row and only counted once.
_BOX_OVERLAP_IOU = 0.6


def _iou(a, b):
    """Intersection-over-union of two (x1, y1, x2, y2) boxes."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = min(ax2, bx2) - max(ax1, bx1)
    ih = min(ay2, by2) - max(ay1, by1)
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0

# Recovery/beat-the-runtime knobs (settings.json -> "recovery").
DEFAULT_RECOVERY = {
    "scan_restart_limit": 3,
}

# Bounded waves. Detection loss is not evidence of damage or collected loot.
DEFAULT_ATTACK = {
    "time_limit": 30.0,
    "max_waves": 3,
}

# Sweep geometry (preserved from the notebook): tap every `_SWEEP_STEP` px from
# the left edge to `_SWEEP_RIGHT_MARGIN` before the right edge.
_SWEEP_STEP = 50
_SWEEP_RIGHT_MARGIN = 100

# Only rows at least this far *above* the surr button are swept, so a sweep can
# never land on the surr tap itself.
_ATTACK_ROW_MARGIN = 100

# Provider rows closer than this (guest px) are merged into a single sweep row,
# so a gold and an elixir store on the same line are only swept once.
_ATTACK_ROW_TOLERANCE = 20


class ScanFailed(RuntimeError):
    """A layout/treasure scan could not read the resources after its retries.

    Unlike other RuntimeErrors (ADB failure, uncalibrated button, clean stop),
    this is treated as recoverable: the farm loop taps the retry spots and
    restarts, and only alerts after several failures in a row.
    """


class TreasureScanFailed(ScanFailed):
    """The resource (gold/elixir/dark) values could not be detected at all.

    A subclass of :class:`ScanFailed` so callers can special-case it: the first
    consecutive failure of this kind taps ``surr`` (rather than the retry spots)
    before restarting Phase 1 — the resource row is often hidden by a dialog or
    a lingering battle, and ``surr`` backs out of those states.
    """


class CocBot:
    """
    Core farming bot. Preserves the exact notebook logic but wraps it in a
    thread-safe class with graceful stop support and GUI queue messaging.
    """

    def __init__(
        self,
        config: AppConfig,
        window_manager,
        vision_manager,
        automation_controller,
        msg_queue: queue.Queue,
        controls: dict | None = None,
        waits: dict | None = None,
        notifier: Notifier | None = None,
        recovery: dict | None = None,
        attack: dict | None = None,
        screen_detector=None,
        recorder=None,
    ):
        self.config = config
        self.window = window_manager
        self.vision = vision_manager
        self.auto = automation_controller
        self.msg_queue = msg_queue
        self.controls = controls or {}
        self.waits = {
            k: max(0.0, float(v)) for k, v in {**DEFAULT_WAITS, **(waits or {})}.items()
        }
        self.recovery = {**DEFAULT_RECOVERY, **(recovery or {})}
        self.attack = {**DEFAULT_ATTACK, **(attack or {})}
        self.notifier = notifier or Notifier()

        self._stop_event = threading.Event()
        self._thread = None
        self.recorder = recorder
        self.guard = StateGuard(self.window.capture_window, screen_detector, self._stop_event, recorder) if screen_detector else None
        self.required_resources = {config.GOLD, config.ELIXIR}

    def _ensure_state(self, expected, action):
        if self.guard:
            observation = self.guard.wait_for(expected, timeout=self.config.state_timeout, action=action)
            self._log(f"screen: {observation.state.value} ({action})")
            return observation.state
        return None

    def _navigate_to_preview(self):
        if not self.guard:
            for button in (self.config.ATTACK_BTN_HOME, self.config.FIND_BTN, self.config.ATTACK_BTN):
                self._press_button(button)
            return
        state = self._ensure_state([ScreenState.HOME, ScreenState.MATCH_MENU, ScreenState.PREVIEW], "start search")
        if state == ScreenState.HOME:
            self._press_button(self.config.ATTACK_BTN_HOME)
            state = self._ensure_state([ScreenState.MATCH_MENU, ScreenState.PREVIEW], "open attack menu")
        if state == ScreenState.MATCH_MENU:
            self._press_button(self.config.FIND_BTN)
            state = self._ensure_state([ScreenState.MATCH_MENU, ScreenState.PREVIEW], "find match")
            if state == ScreenState.MATCH_MENU:
                self._press_button(self.config.ATTACK_BTN)
                self._ensure_state([ScreenState.PREVIEW], "confirm match")

    # ---- Public lifecycle ----

    @staticmethod
    def goals_reached(totals, goals):
        active = [(totals[key], goal) for key, goal in zip(
            ("gold", "elixir", "delixir"), goals
        ) if goal > 0]
        return bool(active) and all(total >= goal for total, goal in active)

    def start(self, targets, goals):
        """
        Start the farm loop in a daemon thread.

        Args:
            targets: tuple (gtarget, etarget, detarget) — minimum resources to attack
            goals:   tuple (g_goal, e_goal, de_goal) — total resources to farm before stopping
        """
        if self._thread and self._thread.is_alive():
            self._log("Bot is already running")
            return False

        if any(len(values) != 3 or any(
            not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in values
        ) for values in (targets, goals)):
            self._alert("Thresholds and goals must be three non-negative integers.")
            self._set_status("error")
            return False

        missing = [
            name
            for name in (
                self.config.ATTACK_BTN_HOME,
                self.config.FIND_BTN,
                self.config.NXT_BTN,
                self.config.ATTACK_BTN,
                self.config.S_GOBLIN,
                self.config.SURR_BTN,
                self.config.SURR_CONF,
                self.config.RETURN_HOME,
                self.config.RETRY_BTN_1,
                self.config.RETRY_BTN_2,
                self.config.RETRY_BTN_3,
            )
            if not self._valid_control(self.controls.get(name))
        ]
        if missing:
            msg = (
                "Cannot start: button positions missing for "
                + ", ".join(missing)
                + ". Run tools/calibrate.py first."
            )
            self._log(msg)
            self._alert(msg)
            self._notify("COC Auto-Farm: cannot start", msg)
            self._set_status("error")
            return False

        self._stop_event.clear()
        if self.recorder:
            self.recorder.record("farm_start", targets=list(targets), goals=list(goals),
                                 layout_backend=self.config.layout_backend)
        self._thread = threading.Thread(
            target=self._farm_loop,
            args=(targets, goals),
            daemon=True,
        )
        self._set_status("running")
        self._log("Bot started")
        self._thread.start()
        return True

    @staticmethod
    def _valid_control(control):
        return isinstance(control, dict) and all(
            isinstance(control.get(axis), (int, float))
            and not isinstance(control[axis], bool)
            and math.isfinite(control[axis])
            and 0 <= control[axis] <= 1
            for axis in ("x", "y")
        )

    def stop(self):
        """Request graceful stop."""
        if not self.is_running():
            return
        self._log("Stop requested")
        self._stop_event.set()
        self._set_status("stopping")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---- GUI communication helpers ----

    def _log(self, text: str):
        logger.info(text)
        if self.msg_queue is not None:
            self.msg_queue.put({"type": "log", "text": text})

    def _alert(self, text: str):
        if self.msg_queue is not None:
            self.msg_queue.put({"type": "alert", "text": text})

    def _set_status(self, state: str):
        if self.msg_queue is not None:
            self.msg_queue.put({"type": "status", "state": state})

    def _show_totals(self, totals: dict):
        if self.msg_queue is not None:
            self.msg_queue.put({"type": "totals", "data": totals})

    @staticmethod
    def _drain_summary(drains: list) -> str:
        """End-of-session line: every raid's %drained plus the average."""
        if not drains:
            return "Detection loss is not used as a loot or destruction measurement."
        per = ", ".join(f"{d * 100:.0f}%" for d in drains)
        avg = sum(drains) / len(drains)
        return (
            f"drain per raid: {per} | "
            f"average {avg * 100:.0f}% over {len(drains)} raid(s)"
        )

    @staticmethod
    def _drain_average(drains: list) -> str:
        """Short ``' | avg drain N%'`` suffix for notifications ('' if no raids)."""
        if not drains:
            return ""
        avg = sum(drains) / len(drains)
        return f" | avg drain {avg * 100:.0f}%"

    # ---- Notifications (best-effort, never disturb the loop) ----

    def _capture_screenshot(self) -> str | None:
        """
        Capture the emulator screen, shrink it, and save a compressed JPEG under
        logs/. ntfy.sh caps attachments at 2 MB, so the frame is downscaled to
        NOTIFY_IMAGE_MAX_WIDTH and JPEG-encoded (NOTIFY_IMAGE_QUALITY). Best-effort:
        returns the path, or None if the capture/save fails (e.g. ADB is down).
        """
        try:
            frame = self.window.capture_window()
        except Exception as e:
            logger.debug(f"screenshot capture failed: {e}")
            return None

        try:
            h, w = frame.shape[:2]
            if w > NOTIFY_IMAGE_MAX_WIDTH:
                scale = NOTIFY_IMAGE_MAX_WIDTH / float(w)
                frame = cv2.resize(
                    frame,
                    (NOTIFY_IMAGE_MAX_WIDTH, max(1, int(h * scale))),
                    interpolation=cv2.INTER_AREA,
                )
            log_dir = user_path("logs")
            os.makedirs(log_dir, exist_ok=True)
            path = os.path.join(
                log_dir, "error_" + time.strftime("%Y%m%d_%H%M%S") + ".jpg"
            )
            cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, NOTIFY_IMAGE_QUALITY])
            return path
        except Exception as e:
            logger.debug(f"screenshot save failed: {e}")
            return None

    def _notify(self, title: str, message: str, success: bool = False):
        """
        Push a notification through the configured notifier, attaching a
        screenshot when possible. Does nothing (and skips the capture) unless a
        channel is configured, and never raises.
        """
        if not getattr(self.notifier, "is_configured", False):
            return
        try:
            image = self._capture_screenshot()
            self.notifier.notify(
                title,
                message,
                image_path=image,
                priority="default" if success else "high",
                tags="white_check_mark" if success else "warning",
            )
        except Exception as e:
            logger.debug(f"notification dispatch failed: {e}")

    # ---- Sleeping with stop awareness ----

    def _sleep(self, seconds: float, why: str | None = None):
        """
        Sleep in small chunks so we can exit quickly when stop is requested.
        Preserves timing close to the original notebook sleep calls.
        When `why` is given, logs the actual elapsed time afterward (DEBUG,
        file only).
        """
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self._stop_event.is_set():
                break
            time.sleep(0.1)
        if why is not None:
            logger.debug(
                f"waited {time.time() - (deadline - seconds):.2f}s "
                f"(target {seconds:.2f}s) for {why}"
            )
        if self._stop_event.is_set():
            raise RuntimeError("Bot stopped")

    # ---- Fixed button helpers (normalized coords, no YOLO) ----

    def _button_coords(self, name: str):
        """
        Convert a normalized control (fractions of the screen, 0..1) to pixel
        coordinates using the current capture resolution.
        """
        norm = self.controls.get(name)
        if not norm or "x" not in norm or "y" not in norm:
            raise KeyError(name)

        if not self.window.win_width or not self.window.win_height:
            self.window.get_rect()
        return (
            min(self.window.win_width - 1, int(norm["x"] * self.window.win_width)),
            min(self.window.win_height - 1, int(norm["y"] * self.window.win_height)),
        )

    def _press_button(self, name: str, wait_after: float | None = None):
        """
        Tap a calibrated UI button and wait the configured amount afterward.
        There is no YOLO fallback: if the button was never calibrated the farm
        loop refuses to start, so missing entries here are a programming error
        / stale settings. An explicit wait_after overrides the settings value.
        """
        if self._stop_event.is_set():
            raise RuntimeError("Bot stopped")
        try:
            x, y = self._button_coords(name)
        except KeyError:
            raise RuntimeError(f"'{name}' is not calibrated") from None
        norm = self.controls.get(name, {})
        wait = self.waits.get(name, DEFAULT_WAITS.get(name, 0.5)) if wait_after is None else wait_after
        self._log(
            f"tap {name} at ({x}, {y})"
            f" [{norm.get('x', 0):.3f}, {norm.get('y', 0):.3f}] wait {wait:g}s"
        )
        self.auto.click(x, y)
        if self.recorder:
            self.recorder.record("tap", button=name, pixel=[x, y], wait_seconds=wait)
        self._sleep(wait)

    # ---- Vision helpers (YOLO/OCR for content that moves per base) ----

    def _scan_treasures(self):
        """
        Replicates:
        detect(classin=['gold','elixir','d_elixir'], listMode=True, store_value=True)
        Returns dict: {class_name: str_value, ...}
        """
        max_retries = self.config.max_retries
        targets = [self.config.GOLD, self.config.ELIXIR, self.config.D_ELIXIR]
        previous = None

        for attempt in range(1, max_retries + 1):
            if self._stop_event.is_set():
                raise RuntimeError("Bot stopped")

            if attempt == 1:
                self._sleep(self.waits["scan_treasures_first"], why="first treasure scan")
            else:
                self._sleep(self.waits["scan_treasures_retry"], why="treasure scan retry")

            frame = self.window.capture_window()
            details = self.vision.detect_with_details(frame, targets)
            if not details:
                continue

            result = {}
            for cls in targets:
                if cls in details:
                    bbox = details[cls][0]["bbox"]
                    reading = self.vision.read_number_result(frame, bbox)
                    if reading.value is not None:
                        result[cls] = str(reading.value)

            required = {k: result[k] for k in self.required_resources if k in result}
            if self.required_resources.issubset(result) and required == previous:
                logger.debug(f"base treasures read: {result}")
                return result
            previous = required if self.required_resources.issubset(result) else None

        raise TreasureScanFailed(
            f"Could not find treasures {targets} after {max_retries} attempts"
        )

    def _scan_base_layout(self):
        """
        Scan for the storehouses available to attack. The fixed UI buttons
        (surr / s_goblin / nxt_btn) are calibrated controls now, so only the
        per-base storehouse labels stay on YOLO.
        Returns dict: {class_name: [(cx_rel, cy_rel), ...], ...}
        """
        max_retries = self.config.max_retries
        targets = [
            self.config.ELIXIRS,
            self.config.GOLDS,
            self.config.D_ELIXIRS,
        ]

        for attempt in range(1, max_retries + 1):
            if self._stop_event.is_set():
                raise RuntimeError("Bot stopped")

            if attempt == 1:
                self._sleep(self.waits["scan_base_first"], why="base layout scan")
            else:
                self._sleep(self.waits["scan_base_retry"], why="base layout scan retry")

            frame = self.window.capture_window()
            layout = self.vision.detect_layout(frame)
            if layout:
                if self.recorder and self.vision.last_layout_result is not None:
                    self.recorder.record("layout", **self.vision.last_layout_result.metadata())
                return layout

        raise ScanFailed(
            f"Could not find base layout {targets} after {max_retries} attempts"
        )

    def _scan_post_game(self):
        """
        Read the post-battle loot (YOLO boxes -> OCR values), driven by data
        rather than a fixed pause.

        Require two agreeing readings per resource, including a real zero.
        Unreadable values do not vote. A single high outlier cannot inflate totals;
        at timeout only values confirmed in multiple frames are returned.
        """
        targets = [
            self.config.POST_GOLD,
            self.config.POST_ELIXIR,
            self.config.POST_D_ELIXIR,
        ]
        interval = self.waits["scan_post_interval"]
        deadline = time.time() + self.waits["scan_post_timeout"]
        # The post-battle labels are small and low-contrast; at the default
        # confidence a real box (often Dark Elixir) is missed, while pushing the
        # confidence much lower starts inventing boxes, so use 0.35 but never go
        # below 0.3 even if config.conf is set lower.
        post_conf = max(0.3, min(self.config.conf, 0.35))
        summary_marker = self.config.RETURN_HOME
        best = {}
        votes = {cls: Counter() for cls in targets}
        polls = 0

        while True:
            if self._stop_event.is_set():
                raise RuntimeError("Bot stopped")

            frame = self.window.capture_window()
            details = self.vision.detect_with_details(
                frame, targets + [summary_marker], conf=post_conf
            )
            polls += 1

            kept = []
            for cls in targets:
                for item in details.get(cls, []):
                    bbox = item["bbox"]
                    # Skip a box that is really the same row as one already read
                    # (the model sometimes tags one row as two resources).
                    if any(_iou(bbox, seen) > _BOX_OVERLAP_IOU for seen in kept):
                        continue
                    kept.append(bbox)
                    reading = self.vision.read_number_result(frame, bbox)
                    if reading.value is not None:
                        votes[cls][reading.value] += 1
                        if votes[cls][reading.value] >= 2:
                            best[cls] = reading.value
                    break  # at most one vote per resource per frame

            logger.debug(f"post-game poll {polls}: {best}")
            self._dump_post_frame(frame, polls)

            if all(cls in best for cls in targets):
                result = {cls: str(v) for cls, v in best.items()}
                logger.debug(f"post-game loot read: {result} (after {polls} poll(s))")
                return result

            if time.time() >= deadline:
                if not any(v > 0 for v in best.values()):
                    self._log(
                        f"post-battle loot not readable after "
                        f"{self.waits['scan_post_timeout']:g}s; no confirmed loot"
                    )
                    return {}
                result = {cls: str(v) for cls, v in best.items()}
                logger.debug(
                    f"post-game loot read: {result} (partial after {polls} poll(s))"
                )
                return result

            self._sleep(interval, why="post-game loot poll")

    def _dump_post_frame(self, frame, poll):
        """
        Diagnostic only: when the ``COC_POST_DEBUG`` environment variable points
        at a directory, save every post-game poll frame there as a full-res PNG
        so the post-battle screen can be inspected offline.
        """
        debug_dir = os.environ.get("COC_POST_DEBUG")
        if not debug_dir:
            return
        try:
            os.makedirs(debug_dir, exist_ok=True)
            path = os.path.join(
                debug_dir,
                "post_" + time.strftime("%Y%m%d_%H%M%S") + f"_poll{poll}.png",
            )
            cv2.imwrite(path, frame)
        except Exception as e:
            logger.debug(f"post-frame dump failed: {e}")

    # ---- Attack logic ----

    def _provider_counts(self, base: dict) -> dict:
        """Number of detected stores per provider class in ``base``."""
        return {
            cls: len(base.get(cls, []))
            for cls in (self.config.GOLDS, self.config.ELIXIRS, self.config.D_ELIXIRS)
        }

    def _count_providers_now(self) -> int | None:
        """
        Best-effort single-shot provider count for the pre-surrender reading.
        Unlike ``_scan_base_layout`` it does not retry and does **not** check the
        stop event, so it still reads after a manual stop. Returns the total
        store count, or ``None`` if the frame can't be read (ADB down, etc.).
        """
        try:
            frame = self.window.capture_window()
            details = self.vision.detect_with_details(
                frame,
                [self.config.GOLDS, self.config.ELIXIRS, self.config.D_ELIXIRS],
            )
            return sum(self._provider_counts(details).values())
        except Exception as e:
            logger.debug(f"pre-surrender provider scan failed: {e}")
            return None

    def _attack_rows(self, base: dict) -> list:
        """
        Guest-pixel y of every sweep row. Rows come from all three provider
        classes (gold/elixir/dark), keep only the ones at least
        ``_ATTACK_ROW_MARGIN`` above the surr button (so a sweep never taps
        surr), and merge rows closer than ``_ATTACK_ROW_TOLERANCE`` so a store is
        not swept twice.
        """
        _, limit = self._button_coords(self.config.SURR_BTN)
        margin = _ATTACK_ROW_MARGIN * self.window.win_height / 900
        tolerance = _ATTACK_ROW_TOLERANCE * self.window.win_height / 900
        rows = []
        for cls in (self.config.GOLDS, self.config.ELIXIRS, self.config.D_ELIXIRS):
            for item in base.get(cls, []):
                y = item[1]
                if y >= limit - margin:
                    continue
                if any(abs(y - seen) <= tolerance for seen in rows):
                    continue
                rows.append(y)
        return rows

    def _sweep_rows(self, rows: list) -> int:
        """
        Deploy goblins across every row and return the total tap count. A failing
        tap is logged with its coordinate and re-raised (aborting the session).
        """
        started = time.time()
        total_taps = 0
        for k in rows:
            row_taps = 0
            for a in range(
                self.window.win_left,
                self.window.win_width - _SWEEP_RIGHT_MARGIN,
                _SWEEP_STEP,
            ):
                if self._stop_event.is_set():
                    raise RuntimeError("Bot stopped")
                logger.debug(f"tap sweep at ({a}, {k})")
                try:
                    self.auto.click(a, k)
                except Exception as e:
                    logger.error(f"deploy tap failed at ({a}, {k}): {e}")
                    raise
                row_taps += 1
            total_taps += row_taps
            self._log(f"swept row y={k}: {row_taps} taps")
        self._log(
            f"attack sweep done: {len(rows)} row(s), {total_taps} taps "
            f"in {time.time() - started:.1f}s"
        )
        return total_taps

    def _initiate_attack(self, base: dict):
        """Execute bounded goblin waves; detection loss never estimates loot."""
        from cocbot.game.execution import execute_plan

        if self._stop_event.is_set():
            raise RuntimeError("Bot stopped")
        time_limit = float(self.attack.get("time_limit", 30.0))
        max_waves = int(self.attack.get("max_waves", 3))
        if not math.isfinite(time_limit) or not 0 < time_limit <= 300 or not 1 <= max_waves <= 20:
            raise ValueError("Attack requires 0 < time_limit <= 300 and 1 <= max_waves <= 20")
        deadline = time.monotonic() + time_limit
        current = base
        for wave in range(1, max_waves + 1):
            if self._stop_event.is_set():
                raise RuntimeError("Bot stopped")
            rows = self._attack_rows(current)
            if not rows:
                raise RuntimeError("No usable deployment rows; no troops deployed in this wave")
            width, height = self.window.win_width, self.window.win_height
            step = max(1, round(50 * width / 1600))
            actions = [{"type": "select", "control": self.config.S_GOBLIN}]
            for row in rows:
                for x in range(step, width - max(1, round(100 * width / 1600)), step):
                    actions.append({"type": "drop_troop", "point": [x / width, row / height],
                                    "count": 1, "interval": 0.0})
            plan = {"schema_version": 1, "coordinate_space": "normalized_device",
                    "dry_run_only": False, "strategy": "existing_goblin_row_sweep",
                    "actions": actions}
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._log(f"wave {wave}/{max_waves}: {len(rows)} rows, {len(actions)-1} deployment taps")
            try:
                execute_plan(plan, (width, height), self._stop_event, controller=self.auto,
                             controls=self.controls, dry_run=False, recorder=self.recorder, timeout=remaining)
            except TimeoutError:
                self._log("Attack time limit reached during wave")
                break
            self._sleep(min(self.waits.get("attack_wave_settle", 5.0), max(0, deadline-time.monotonic())))
            if wave == max_waves or time.monotonic() >= deadline:
                break
            state = self._ensure_state([ScreenState.BATTLE, ScreenState.PREVIEW, ScreenState.RESULTS], "between waves")
            if state == ScreenState.RESULTS:
                break
            try:
                current = self._scan_base_layout()
            except ScanFailed:
                self._log("No reliable targets after wave; ending deployment without inferring destruction")
                break
        self._sleep(min(self.waits.get("attack_settle", 5.0), max(0, deadline-time.monotonic())))
        return None

    # ---- Farm loop (preserved notebook behaviour) ----

    def _farm_loop(self, targets, goals):
        gtarget, etarget, detarget = targets
        self.required_resources = {cls for cls, threshold in zip(
            (self.config.GOLD, self.config.ELIXIR, self.config.D_ELIXIR), targets) if threshold > 0}
        if not self.required_resources:
            self.required_resources = {self.config.GOLD, self.config.ELIXIR}

        st_time = time.time()
        totals = {"gold": 0, "elixir": 0, "delixir": 0}
        raid_drains = []
        final_status = "stopped"

        # Warm up the models up front so there is no stall mid-raid.
        self._set_status("loading")
        try:
            self._log("Loading YOLO + OCR models...")
            self.vision.load()
            self._log("Models ready")

            self._set_status("farming")
            scan_streak = 0
            scan_limit = max(1, int(self.recovery.get("scan_restart_limit", 3)))
            zero_loot_streak = 0

            while not self._stop_event.is_set():
                # Check total goals
                if self.goals_reached(totals, goals):
                    e_time = time.time()
                    mins = (e_time - st_time) // 60
                    msg = f"Completed in {mins} min"
                    self._log(msg)
                    self._alert(msg)
                    self._notify(
                        "COC Auto-Farm: completed",
                        f"Gold {totals['gold']} | Elixir {totals['elixir']} | "
                        f"Dark {totals['delixir']}, in {mins} min"
                        + self._drain_average(raid_drains),
                        success=True,
                    )
                    break

                self._navigate_to_preview()

                if self._stop_event.is_set():
                    break

                # Phase 2: search and decide
                gave_up = False
                search = True
                while search and not self._stop_event.is_set():
                    try:
                        self._ensure_state([ScreenState.PREVIEW], "scan opponent")
                        base = self._scan_base_layout()
                        base_treasure = self._scan_treasures()
                    except ScanFailed as e:
                        scan_streak += 1
                        if self.recorder:
                            self.recorder.record("scan_failed", frame=self.window.capture_window(),
                                                 error=str(e), streak=scan_streak)
                        if self.guard:
                            if scan_streak >= scan_limit:
                                raise RuntimeError(f"Scan failed {scan_streak} times: {e}") from e
                            self._ensure_state([ScreenState.PREVIEW], "recover scan failure")
                            self._press_button(self.config.NXT_BTN)
                            self._ensure_state([ScreenState.PREVIEW], "next opponent after scan failure")
                            continue
                        # Notify on every failure, attaching a screenshot of the
                        # failing screen (captured here, before the recovery taps
                        # below, so the image is not the post-recovery screen).
                        self._notify(
                            f"COC Auto-Farm: scan failed "
                            f"({scan_streak}/{scan_limit})",
                            f"{e}"
                            + (" (stopping)" if scan_streak >= scan_limit else "")
                            + (
                                self._drain_average(raid_drains)
                                if scan_streak >= scan_limit
                                else ""
                            ),
                        )
                        # The resource row is often hidden behind a dialog or a
                        # lingering battle; on the very first resource-scan
                        # failure, tap surr to back out and restart Phase 1.
                        # From the second failure on, use the retry spots.
                        if isinstance(e, TreasureScanFailed) and scan_streak == 1:
                            self._log(
                                f"resource scan failed ({scan_streak}/{scan_limit}): "
                                f"{e}; tapping surr and restarting phase 1"
                            )
                            self._press_button(self.config.SURR_BTN)
                        else:
                            self._log(
                                f"scan failed ({scan_streak}/{scan_limit}): {e}; "
                                "backing out (retry_btn_1/2/3) and restarting"
                            )
                            self._press_button(self.config.RETRY_BTN_1)
                            self._press_button(self.config.RETRY_BTN_2)
                            self._press_button(self.config.RETRY_BTN_3)
                        if scan_streak >= scan_limit:
                            mins = (time.time() - st_time) // 60
                            self._alert(
                                f"error: {e}, in {mins} min "
                                f"(scan failed {scan_streak}x, stopping)"
                            )
                            gave_up = True
                        search = False
                        break

                    # A successful scan clears the consecutive-failure streak.
                    scan_streak = 0

                    current_gold = int(base_treasure.get(self.config.GOLD, 0))
                    current_elixir = int(base_treasure.get(self.config.ELIXIR, 0))
                    current_delixir = int(base_treasure.get(self.config.D_ELIXIR, 0))

                    self._log(
                        f"base loot: Gold {current_gold} | "
                        f"Elixir {current_elixir} | Dark {current_delixir}"
                    )

                    if (
                        current_gold >= gtarget
                        and current_delixir >= detarget
                        and current_elixir >= etarget
                    ):
                        # Attack
                        self._ensure_state([ScreenState.PREVIEW], "before deploy")
                        drained = self._initiate_attack(base)

                        state = self._ensure_state([ScreenState.BATTLE, ScreenState.PREVIEW, ScreenState.RESULTS], "finish attack")
                        if state != ScreenState.RESULTS:
                            self._press_button(self.config.SURR_BTN)
                            self._press_button(self.config.SURR_CONF)

                        self._ensure_state([ScreenState.RESULTS], "read battle result")

                        post_game = self._scan_post_game()
                        g_gain = int(post_game.get(self.config.POST_GOLD, 0))
                        e_gain = int(post_game.get(self.config.POST_ELIXIR, 0))
                        de_gain = int(post_game.get(self.config.POST_D_ELIXIR, 0))
                        totals["gold"] += g_gain
                        totals["elixir"] += e_gain
                        totals["delixir"] += de_gain
                        self._log(
                            f"loot this raid: Gold +{g_gain} | Elixir +{e_gain} | "
                            f"Dark +{de_gain}  (totals Gold {totals['gold']} | "
                            f"Elixir {totals['elixir']} | Dark {totals['delixir']})"
                        )
                        self._show_totals(totals)

                        # Only count a raid once it has fully completed: the loot
                        # read landed in totals. If the session errors during
                        # surrender or the post-game read, this never runs, so the
                        # error-time average covers only completed raids.
                        if drained is not None:
                            raid_drains.append(drained)

                        # Watchdog: a raid that collected nothing at all usually
                        # means the post-battle read failed (e.g. a missed
                        # surrender) rather than a genuinely empty base, so a run
                        # of them means the bot is desynced.
                        if g_gain == 0 and e_gain == 0 and de_gain == 0:
                            zero_loot_streak += 1
                        else:
                            zero_loot_streak = 0

                        self._press_button(self.config.RETURN_HOME)
                        self._ensure_state([ScreenState.HOME], "return home")

                        if zero_loot_streak >= scan_limit:
                            mins = (time.time() - st_time) // 60
                            self._alert(
                                f"error: no loot read for {zero_loot_streak} raids "
                                f"in a row, in {mins} min"
                            )
                            self._notify(
                                "COC Auto-Farm: no loot read",
                                f"{zero_loot_streak} raids in a row collected 0 "
                                f"loot; stopping after {mins} min"
                                + self._drain_average(raid_drains),
                            )
                            gave_up = True

                        search = False
                    else:
                        # Next base (calibrated button; low loot -> skip)
                        self._press_button(self.config.NXT_BTN)

                if gave_up:
                    final_status = "error"
                    break

        except RuntimeError as e:
            if "Bot stopped" in str(e):
                self._log("Bot stopped cleanly")
            else:
                self._log(f"error: {e}")
                mins = (time.time() - st_time) // 60
                self._alert(f"error: {e}, in {mins} min")
                self._notify(
                    "COC Auto-Farm: error",
                    f"{e} (after {mins} min)" + self._drain_average(raid_drains),
                )
                final_status = "error"
        except Exception as e:
            logger.exception("Farm loop failed")
            self._log(f"error: {e}")
            mins = (time.time() - st_time) // 60
            self._alert(f"error: {e}, in {mins} min")
            self._notify(
                "COC Auto-Farm: error",
                f"{e} (after {mins} min)" + self._drain_average(raid_drains),
            )
            final_status = "error"
        finally:
            if self.recorder:
                self.recorder.record("farm_end", status=final_status, totals=totals)
            self._set_status(final_status)
            self._show_totals(totals)
            self._log(self._drain_summary(raid_drains))
