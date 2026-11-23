"""Inventory template assets without loading or changing the bot."""

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs/template_audit"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted((ROOT / "templates").rglob("*"))
    files = [p for p in files if p.is_file()]
    images, errors, hashes = [], [], defaultdict(list)
    for path in files:
        if path.suffix.lower() != ".png":
            continue
        relative = path.relative_to(ROOT / "templates").as_posix()
        try:
            with Image.open(path) as im:
                im.load()
                rgba = im.convert("RGBA")
                digest = hashlib.sha256(str(rgba.size).encode() + rgba.tobytes()).hexdigest()
                hashes[digest].append(relative)
                alpha = rgba.getchannel("A").getextrema()
                images.append({"path": relative, "width": im.width, "height": im.height,
                               "mode": im.mode, "transparent": alpha[0] < 255,
                               "constant_rgb": all(lo == hi for lo, hi in rgba.convert("RGB").getextrema())})
        except Exception as exc:
            errors.append({"path": relative, "error": str(exc)})
    models = []
    for path in sorted((ROOT / "templates/models").glob("*.onnx")):
        raw = path.read_bytes()
        strings = re.findall(rb"[\x20-\x7e]{6,}", raw)
        hints = [s.decode("ascii") for s in strings if
                 any(token in s.lower() for token in (b"ultralytics", b"yolo", b"{0:", b"{\"0\"", b"author", b"description"))]
        models.append({"path": path.name, "bytes": len(raw), "metadata_string_hints": hints[-20:]})
    if "--check-onnx" in sys.argv:
        import cv2
        import numpy as np
        import time

        sizes = {"smart_farm.onnx": 416, "deploy_zone.onnx": 1280, "spell_target.onnx": 320}
        for model in models:
            started = time.perf_counter()
            try:
                net = cv2.dnn.readNetFromONNX(str(ROOT / "templates/models" / model["path"]))
                size = sizes[model["path"]]
                net.setInput(np.zeros((1, 3, size, size), dtype=np.float32))
                outputs = net.forward(net.getUnconnectedOutLayersNames())
                model["opencv_smoke_test"] = {"ok": True, "input_size": size,
                    "outputs": [list(value.shape) for value in outputs],
                    "seconds_including_load": round(time.perf_counter() - started, 3)}
            except Exception as exc:
                model["opencv_smoke_test"] = {"ok": False, "error": str(exc)}
    report = {
        "files": len(files), "extensions": dict(Counter(p.suffix for p in files)),
        "groups": dict(Counter(p.relative_to(ROOT / "templates").parts[0]
                               if len(p.relative_to(ROOT / "templates").parts) > 1 else "(root)" for p in files)),
        "valid_png": len(images), "invalid_png": errors,
        "transparent_png": sum(i["transparent"] for i in images),
        "constant_rgb_png": [i["path"] for i in images if i["constant_rgb"]],
        "duplicate_groups": [v for v in hashes.values() if len(v) > 1],
        "models": models, "images": images,
    }
    (OUT / "inventory.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    selected = ["attack_button.png", "find_match.png", "start_attack.png", "surrender.png",
                "return_home.png", "goblin.png", "goblin_click.png", "upgrade_names/main/gold_storage.png",
                "upgrade_names/main/gold_mine.png", "upgrade_names/main/elixir_collector.png",
                "upgrade_names/main/town_hall.png", "laboratory.png", "icons/clan_castle_broken.png",
                "gold_transparent.png", "digits/0.png", "mau.png", "mau2.png", "mau3.png", "mau4.png"]
    canvas = Image.new("RGB", (1200, ((len(selected) + 3) // 4) * 180), "#30343b")
    draw = ImageDraw.Draw(canvas)
    for i, name in enumerate(selected):
        path = ROOT / "templates" / name
        if not path.exists():
            continue
        with Image.open(path) as im:
            x, y = (i % 4) * 300, (i // 4) * 180
            label = name.replace("upgrade_names/main/", "upgrade_names/\n")
            draw.text((x + 5, y + 3), f"{label}\n{im.width}x{im.height}", fill="white")
            tile = im.convert("RGBA")
            tile.thumbnail((290, 115))
            canvas.paste(tile, (x + 5, y + 60), tile)
    canvas.save(OUT / "contact_sheet.png")
    summary = {k: v for k, v in report.items() if k not in ("images", "duplicate_groups")}
    summary["duplicate_groups"] = len(report["duplicate_groups"])
    summary["redundant_copies"] = sum(len(v) - 1 for v in report["duplicate_groups"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
