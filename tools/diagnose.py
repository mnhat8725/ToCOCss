"""Read-only emulator/model diagnostics. Never taps or deploys troops."""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # project root

import logging

from cocbot.device.adb import EmulatorAdb
from cocbot.core.config import AppConfig
from cocbot.core.paths import configure_runtime_env, resource_path
from cocbot.vision.manager import VisionManager
from cocbot.vision.onnx_engine import export_result
from cocbot.vision.state_detection import ScreenDetector
from cocbot.core.diagnostics import SessionRecorder


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    configure_runtime_env()
    config = AppConfig()
    config.model_path = resource_path(config.model_path)
    recorder = SessionRecorder()
    recorder.record("diagnostic_start")
    adb = EmulatorAdb(host=config.adb_host, port=config.adb_port, adb_path=config.adb_path)
    if not adb.connect():
        recorder.record("diagnostic_failed", phase="connect", error=adb.last_error)
        logging.error("ADB connection failed: %s", adb.last_error)
        return 1
    print(f"ADB connected: {adb.serial}", flush=True)
    frame = adb.screencap()
    if frame is None:
        recorder.record("diagnostic_failed", phase="screenshot", error=adb.last_error)
        logging.error("Screenshot failed: %s", adb.last_error)
        return 1
    print(f"Screenshot: {frame.shape[1]}x{frame.shape[0]}", flush=True)
    observation = ScreenDetector().detect(frame)
    recorder.record("read_only_diagnostic", frame=frame, **observation.metadata())
    print("Screen state:", observation.metadata(), flush=True)
    vision = VisionManager(config)
    vision.load()
    print("YOLO and OCR ready offline", flush=True)
    layout = vision.detect_layout(frame)
    print("Smart Farm layout:", layout, flush=True)
    if vision.last_layout_result is not None:
        export_result(recorder.directory / "smart_farm", vision.last_layout_result)
    print("Artifacts:", recorder.directory, flush=True)
    labels = list(vision.model.names.values())
    details = vision.detect_with_details(frame, labels)
    print("Detected objects:", {key: len(value) for key, value in details.items()}, flush=True)
    resources = (config.GOLD, config.ELIXIR, config.D_ELIXIR,
                 config.POST_GOLD, config.POST_ELIXIR, config.POST_D_ELIXIR)
    for label in resources:
        for item in details.get(label, []):
            print(f"OCR {label}: {vision.read_number(frame, item['bbox'])}", flush=True)
    print("DIAGNOSTICS PASSED (read-only; no farming actions)", flush=True)
    recorder.record("diagnostic_passed", state=observation.state.value,
                    note="Read-only smoke test; no real raid executed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logging.exception("Diagnostics failed")
        raise SystemExit(1)
