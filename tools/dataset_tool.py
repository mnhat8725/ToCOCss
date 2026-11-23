"""Validate reviewed YOLO data, prevent split leakage, and export data.yaml."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from PIL import Image

NAMES = ["gold_mine_full", "gold_storage_full", "elixir_collector_full",
         "elixir_storage_full", "de_drill_full", "de_storage_full"]


def validate_dataset(manifest_path):
    path = Path(manifest_path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("names") != NAMES:
        raise ValueError("Dataset must use schema 1 and the six Smart Farm _full classes in metadata order")
    records = data.get("records", [])
    if not records:
        raise ValueError("No reviewed labeled images. Collect and annotate screenshots before training.")
    root = path.parent
    splits = {name: [] for name in ("train", "val", "test")}
    hashes, groups, paths = {}, {}, set()
    counts = {name: [0] * len(NAMES) for name in splits}
    for record in records:
        split = record.get("split")
        if split not in splits or record.get("reviewed") is not True or not record.get("group"):
            raise ValueError("Every image requires train/val/test, group (raid/village), and reviewed=true")
        image_path = (root / record["image"]).resolve()
        label_path = (root / record["label"]).resolve()
        if not image_path.is_relative_to(root) or not label_path.is_relative_to(root):
            raise ValueError("Dataset paths must stay inside the dataset directory")
        image_relative = image_path.relative_to(root)
        if image_relative.parts[:2] != ("images", split):
            raise ValueError("Images must be under images/<split>/")
        expected_label = root / "labels" / Path(*image_relative.parts[1:]).with_suffix(".txt")
        if label_path != expected_label:
            raise ValueError("Label must mirror image under labels/<split>/ with .txt suffix")
        if image_path in paths:
            raise ValueError("Duplicate image entry")
        paths.add(image_path)
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            if min(image.size) < 16 or image.width * image.height > 24_000_000:
                raise ValueError("Image dimensions are outside supported limits")
            digest = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
        if digest in hashes:
            raise ValueError(f"Duplicate image pixels: {image_path} and {hashes[digest]}")
        hashes[digest] = str(image_path)
        group = str(record["group"])
        if group in groups and groups[group] != split:
            raise ValueError(f"Split leakage: raid/village group {group} occurs in multiple splits")
        groups[group] = split
        for line in label_path.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) != 5:
                raise ValueError(f"Expected class cx cy width height in {label_path}")
            cls = int(fields[0])
            cx, cy, width, height = map(float, fields[1:])
            if not 0 <= cls < len(NAMES) or not all(math.isfinite(v) for v in (cx, cy, width, height)):
                raise ValueError("Invalid class or non-finite box")
            if not 0 < width <= 1 or not 0 < height <= 1 or min(cx-width/2, cy-height/2) < -1e-6 or max(cx+width/2, cy+height/2) > 1+1e-6:
                raise ValueError("Bounding box extends outside image")
            counts[split][cls] += 1
        splits[split].append(str(image_path))
    if any(not paths for paths in splits.values()):
        raise ValueError("Provide separate nonempty train, val and test image sets")
    if not sum(counts["train"]):
        raise ValueError("Training split has no positive annotations")
    return root, splits, {"images": {k: len(v) for k, v in splits.items()}, "objects_by_class": counts,
                          "names": NAMES, "groups": len(groups), "accuracy_measured": False}


def export_dataset(path):
    root, splits, report = validate_dataset(path)
    for split, paths in splits.items():
        (root / f"{split}.txt").write_text("\n".join(paths) + "\n", encoding="utf-8")
    configuration = {"path": str(root), "train": "train.txt", "val": "val.txt", "test": "test.txt",
                     "names": dict(enumerate(NAMES))}
    (root / "data.yaml").write_text(json.dumps(configuration, indent=2), encoding="utf-8")
    (root / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return root / "data.yaml", report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "validate", "export"))
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "init":
            args.manifest.parent.mkdir(parents=True, exist_ok=True)
            with args.manifest.open("x", encoding="utf-8") as stream:
                json.dump({"schema_version": 1, "names": NAMES, "records": []}, stream, indent=2)
            print(f"Created empty annotation manifest: {args.manifest}")
        elif args.action == "export":
            path, report = export_dataset(args.manifest)
            print(json.dumps({"data_yaml": str(path), **report}, indent=2))
        else:
            _, _, report = validate_dataset(args.manifest)
            print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"DATASET NOT READY: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
