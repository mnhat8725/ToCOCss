"""Template evidence for screen transitions, independent of input execution."""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import time

import cv2
import numpy as np

from cocbot.core.paths import resource_path


class ScreenState(str, Enum):
    HOME = "home"
    MATCH_MENU = "match_menu"
    PREVIEW = "preview"
    BATTLE = "battle"
    RESULTS = "results"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Marker:
    filename: str
    state: ScreenState
    roi: tuple = (0, 0, 1, 1)


# These are visual hypotheses. Real-device validation remains necessary for
# other languages, skins and UI versions; an unknown screen never authorizes a tap.
DEFAULT_MARKERS = (
    Marker("return_home.png", ScreenState.RESULTS, (0, .45, 1, 1)),
    Marker("next_button.png", ScreenState.PREVIEW, (.5, .3, 1, 1)),
    Marker("surrender.png", ScreenState.BATTLE, (0, .45, .4, 1)),
    Marker("end_battle.png", ScreenState.BATTLE, (0, .45, .4, 1)),
    Marker("find_match.png", ScreenState.MATCH_MENU),
    Marker("start_attack.png", ScreenState.MATCH_MENU),
    Marker("attack_button.png", ScreenState.HOME, (0, .45, .35, 1)),
)


@dataclass
class Observation:
    state: ScreenState
    evidence: list
    image_size: tuple

    def metadata(self):
        return {"state": self.state.value, "evidence": self.evidence,
                "image_size": list(self.image_size)}


class ScreenDetector:
    def __init__(self, template_dir=None, threshold=.85, scales=(.5, .67, .8, 1., 1.25, 1.5), markers=None):
        if not 0 < threshold <= 1:
            raise ValueError("Template threshold must be in (0, 1]")
        self.directory = Path(template_dir or resource_path("templates"))
        self.threshold = threshold
        self.scales = scales
        self.markers = tuple(markers if markers is not None else DEFAULT_MARKERS)
        self._templates = {}

    def _template(self, name):
        if name not in self._templates:
            path = self.directory / name
            im = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_UNCHANGED) if path.is_file() else None
            if im is None:
                raise ValueError(f"Missing or unreadable screen template: {path}")
            if im.ndim == 3 and im.shape[2] == 4:
                alpha = im[:, :, 3:4].astype(np.float32) / 255
                im = (im[:, :, :3] * alpha + 114 * (1 - alpha)).astype(np.uint8)
            gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) if im.ndim == 3 else im
            if float(gray.std()) < 1:
                raise ValueError(f"Constant template cannot identify a screen: {path}")
            self._templates[name] = gray
        return self._templates[name]

    def detect(self, frame):
        if frame is None or frame.ndim != 3 or min(frame.shape[:2]) < 16:
            raise ValueError("Expected a BGR screenshot at least 16x16")
        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        evidence = []
        for marker in self.markers:
            template = self._template(marker.filename)
            x1, y1, x2, y2 = [round(v * size) for v, size in zip(marker.roi, (width, height, width, height))]
            roi = gray[y1:y2, x1:x2]
            best = None
            for scale in self.scales:
                w, h = max(2, round(template.shape[1] * scale)), max(2, round(template.shape[0] * scale))
                if w > roi.shape[1] or h > roi.shape[0]:
                    continue
                resized = cv2.resize(template, (w, h))
                if float(resized.std()) < 1:
                    continue
                scores = cv2.matchTemplate(roi, resized, cv2.TM_CCOEFF_NORMED)
                _, score, _, point = cv2.minMaxLoc(scores)
                if np.isfinite(score) and (best is None or score > best["score"]):
                    px, py = point
                    best = {"template": marker.filename, "state": marker.state.value,
                            "score": float(score), "scale": scale,
                            "box_xyxy": [x1 + px, y1 + py, x1 + px + w, y1 + py + h]}
            if best and best["score"] >= self.threshold:
                evidence.append(best)
        # Preview may contain a surrender button too. The Next marker is stronger
        # evidence of preview; results take precedence over underlying screens.
        states = {item["state"] for item in evidence}
        selected = ScreenState.UNKNOWN
        for state in (ScreenState.RESULTS, ScreenState.PREVIEW, ScreenState.MATCH_MENU, ScreenState.HOME, ScreenState.BATTLE):
            if state.value in states:
                selected = state
                break
        return Observation(selected, evidence, (width, height))


class StateTimeout(RuntimeError):
    pass


class StateGuard:
    def __init__(self, capture, detector, stop_event, recorder=None, poll=.3, confirmations=2):
        self.capture, self.detector, self.stop_event = capture, detector, stop_event
        self.recorder = recorder
        self.poll = poll
        self.confirmations = confirmations

    def wait_for(self, expected, timeout=10, action="observe"):
        expected = set(expected)
        deadline = time.monotonic() + timeout
        streak = 0
        last_state = None
        while True:
            if self.stop_event.is_set():
                raise RuntimeError("Bot stopped")
            frame = self.capture()
            observation = self.detector.detect(frame)
            matched = observation.state in expected
            streak = streak + 1 if matched and observation.state == last_state else int(matched)
            last_state = observation.state
            if streak >= self.confirmations:
                if self.recorder:
                    self.recorder.record("state_verified", action=action, **observation.metadata())
                return observation
            if time.monotonic() >= deadline:
                if self.recorder:
                    self.recorder.record("state_timeout", frame=frame, action=action,
                                         expected=sorted(s.value for s in expected), **observation.metadata())
                raise StateTimeout(f"{action}: expected {','.join(s.value for s in expected)}, observed {observation.state.value}")
            if self.stop_event.wait(self.poll):
                raise RuntimeError("Bot stopped")
