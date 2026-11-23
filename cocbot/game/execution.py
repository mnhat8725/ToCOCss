"""Validated, cancellable action scripts with a dry-run adapter."""
import math
import time


def _number(value, low, high):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and low <= value <= high


def validate_plan(plan):
    if plan.get("schema_version") != 1 or plan.get("coordinate_space") != "normalized_device":
        raise ValueError("Unsupported plan schema or coordinate space")
    actions = plan.get("actions")
    if not isinstance(actions, list) or len(actions) > 500:
        raise ValueError("Expected at most 500 actions")
    total_taps, total_wait = 0, 0.
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("Action must be an object")
        kind = action.get("type")
        if kind == "select":
            if not isinstance(action.get("control"), str) or not action["control"]:
                raise ValueError("Selection requires a calibrated control")
            total_taps += 1
        elif kind == "delay":
            if not _number(action.get("seconds"), 0, 60):
                raise ValueError("Delay must be between 0 and 60 seconds")
            total_wait += action["seconds"]
        elif kind in ("drop_troop", "drop_hero", "drop_spell", "drop_siege", "use_ability"):
            point = action.get("point")
            if not isinstance(point, (list, tuple)) or len(point) != 2 or not all(_number(v, 0, 1) for v in point):
                raise ValueError("Action point must be normalized to [0, 1]")
            count, interval = action.get("count", 1), action.get("interval", .1)
            if type(count) is not int or not 1 <= count <= 100 or not _number(interval, 0, 10):
                raise ValueError("Invalid action count or interval")
            total_taps += count
            total_wait += count * interval
        else:
            raise ValueError(f"Unknown action: {kind}")
    if total_taps > 1000 or total_wait > 300:
        raise ValueError("Plan exceeds 1000 taps or 300 seconds of waits")
    return actions


def execute_plan(plan, size, stop_event, controller=None, controls=None, dry_run=True, recorder=None, timeout=300):
    actions = validate_plan(plan)
    if not dry_run and (plan.get("dry_run_only", True) or controller is None):
        raise ValueError("Preview plans cannot execute live actions")
    width, height = size
    if type(width) is not int or type(height) is not int or min(width, height) < 16:
        raise ValueError("Invalid device resolution")
    # Resolve every point before the first action, so a bad late selection cannot
    # leave a partially executed script behind.
    resolved = []
    for action in actions:
        if action["type"] == "delay":
            resolved.append((action, None))
            continue
        if action["type"] == "select":
            point = (controls or {}).get(action["control"])
            if point is None and dry_run:
                resolved.append((action, None))
                continue
            if not isinstance(point, dict) or not all(_number(point.get(k), 0, 1) for k in ("x", "y")):
                raise ValueError(f"Missing or invalid control: {action['control']}")
            point = [point["x"], point["y"]]
        else:
            point = action["point"]
        resolved.append((action, [min(width - 1, round(point[0] * width)), min(height - 1, round(point[1] * height))]))
    deadline = time.monotonic() + timeout
    events = []
    def check_stop():
        if stop_event.is_set():
            raise RuntimeError("Bot stopped")
        if time.monotonic() >= deadline:
            raise TimeoutError("Action script timed out")
    def wait(seconds):
        if dry_run:
            return
        if stop_event.wait(min(seconds, max(0, deadline - time.monotonic()))):
            raise RuntimeError("Bot stopped")
        check_stop()
    for index, (action, point) in enumerate(resolved):
        check_stop()
        event = {"index": index, "action": action, "pixel": point, "dry_run": dry_run}
        if recorder:
            recorder.record("script_action", **event)
        events.append(event)
        if action["type"] == "delay":
            wait(action["seconds"])
        else:
            for _ in range(action.get("count", 1)):
                check_stop()
                if not dry_run:
                    controller.click(*point)
                wait(action.get("interval", .1))
    return events
