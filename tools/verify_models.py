"""Real model smoke tests; outputs are predictions, not accuracy measurements."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cocbot.vision.onnx_engine import Engine, read_image, export_result, sample_path


def main():
    engine = Engine()
    output = ROOT / "logs/verification/model_outputs"
    records = []
    for sample in ("top.png", "mid.png", "bottom.png"):
        image = read_image(sample_path(sample))
        for mode in ("baseline", "crop", "regions"):
            result = engine.infer(image, sample, "smart_farm", crop=mode == "crop", scan_regions=mode == "regions")
            export_result(output / f"{Path(sample).stem}_{mode}", result)
            records.append({"sample": sample, "model": result.model, "mode": mode,
                            "detections": len(result.detections), "inference_ms": result.inference_ms})
    for model in ("spell_target", "deploy_zone"):
        result = engine.infer(read_image(sample_path("top.png")), "top.png", model)
        export_result(output / model, result)
        records.append({"model": model, "shapes": result.output_shapes,
                        "note": "Runtime smoke test only. Main-village sample is not Capital validation."})
    print(json.dumps(records, indent=2))
    print("PASS: all three models executed; accuracy has not been measured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
