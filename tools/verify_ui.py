"""Exercise Tk construction, image rendering and close lifecycle with a hidden test window."""
from pathlib import Path
import sys
import tkinter as tk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cocbot.vision.onnx_engine import Engine, read_image, sample_path
from cocbot.ui.vision_lab import VisionLab


def main():
    root = tk.Tk()
    root.withdraw()
    lab = VisionLab(root)
    root.update_idletasks()
    lab.image = read_image(sample_path("top.png"))
    lab.source = "top.png"
    lab.result = Engine().infer(lab.image, lab.source, "smart_farm")
    lab.render()
    root.update_idletasks()
    assert lab.photo is not None
    assert len(lab.canvas.find_all()) == 1
    lab.boxes.set(False)
    lab.render()
    lab.preview_plan()
    lab.close()
    assert lab.jobs.closed
    print("PASS: hidden Tk UI constructed, image rendered, overlay toggled, preview exported, worker lifecycle closed")
    print("This is a widget smoke test, not a desktop visual/interaction review.")


if __name__ == "__main__":
    main()
