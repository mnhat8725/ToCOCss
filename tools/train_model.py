"""Prepare a reviewed dataset; train only with --execute. Never replace the active model."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.dataset_tool import export_dataset
from cocbot.core.paths import configure_runtime_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--weights", type=Path, default=ROOT / "models/best.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        if not args.weights.is_file() or args.weights.suffix != ".pt":
            raise ValueError("Training requires an existing PyTorch .pt checkpoint, not an ONNX export")
        if not 1 <= args.epochs <= 1000:
            raise ValueError("epochs must be between 1 and 1000")
        data, report = export_dataset(args.manifest)
        print(json.dumps({"weights": str(args.weights), "epochs": args.epochs, "data": str(data),
                          "execute": args.execute, "validation": report}, indent=2), flush=True)
        if args.execute:
            configure_runtime_env()
            from ultralytics import YOLO
            model = YOLO(str(args.weights))
            model.train(data=str(data), imgsz=416, epochs=args.epochs, device=args.device,
                        project=str(ROOT / "runs/training"), name="smart_farm", exist_ok=False)
            model.val(data=str(data), split="test", device=args.device)
        else:
            print("DRY RUN: dataset validated; training has not started")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"TRAINING NOT READY: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
