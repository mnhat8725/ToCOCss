"""Re-analyze saved screenshots and produce dry-run plans without an ADB connection."""
import argparse
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cocbot.core.diagnostics import SessionRecorder
from cocbot.game.execution import execute_plan
from cocbot.vision.onnx_engine import Engine, export_result, read_image
from cocbot.vision.state_detection import ScreenDetector
from cocbot.game.strategy import build_preview_plan, save_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Image or directory of original screenshot PNGs")
    parser.add_argument("--output", type=Path, default=ROOT / "logs/replays")
    args = parser.parse_args()
    paths = sorted(args.source.glob("*.png")) if args.source.is_dir() else [args.source]
    if not paths or any(not p.is_file() for p in paths):
        parser.error("No screenshots found")
    recorder = SessionRecorder(args.output)
    engine, detector = Engine(), ScreenDetector()
    for index, path in enumerate(paths):
        frame = read_image(path)
        observation = detector.detect(frame)
        result = engine.infer(frame, str(path), "smart_farm")
        destination = recorder.directory / f"{index:04}_{path.stem}"
        export_result(destination, result)
        plan = build_preview_plan(result)
        save_plan(destination / "plan.json", plan)
        events = execute_plan(plan, (frame.shape[1], frame.shape[0]), threading.Event(), recorder=recorder)
        recorder.record("replayed_frame", source=str(path), **observation.metadata(),
                        detections=len(result.detections), planned_actions=len(events))
    print(f"PASS: replayed {len(paths)} image(s), no device actions. Artifacts: {recorder.directory}")


if __name__ == "__main__":
    main()
