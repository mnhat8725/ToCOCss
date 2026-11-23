"""Tkinter image inspection UI sharing the offline ONNX engine with the bot."""
from datetime import datetime
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from cocbot.vision.onnx_engine import Engine, MODELS, read_image, rendered_rgb, export_result
from cocbot.vision.state_detection import ScreenDetector
from cocbot.core.paths import user_path


class LatestJob:
    """One worker at a time; invalidated results never reach the current view."""
    def __init__(self):
        self.queue = queue.Queue()
        self.generation = 0
        self.busy = False
        self.closed = False

    def submit(self, function):
        if self.closed or self.busy:
            return False
        self.generation += 1
        generation = self.generation
        self.busy = True
        def run():
            try:
                self.queue.put((generation, function(), None))
            except Exception as exc:
                self.queue.put((generation, None, str(exc)))
        threading.Thread(target=run, daemon=True).start()
        return True

    def receive(self):
        generation, value, error = self.queue.get_nowait()
        self.busy = False
        if self.closed or generation != self.generation:
            return None
        return value, error

    def close(self):
        self.closed = True
        self.generation += 1


class VisionLab:
    def __init__(self, root, capture=None):
        self.root, self.capture = root, capture
        self.engine, self.jobs = Engine(), LatestJob()
        self.image = self.result = self.photo = self.display_rgb = None
        self.source = ""
        self.zoom = 1.0
        root.title("Kiểm tra nhận diện — COC Auto Farm")
        root.geometry("1180x760")
        root.minsize(900, 580)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        self._poll_id = root.after(100, self._poll)

    def _build(self):
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(fill="x")
        self.open_btn = ttk.Button(toolbar, text="Mở ảnh", command=self.open_image)
        self.open_btn.pack(side="left", padx=3)
        self.capture_btn = ttk.Button(toolbar, text="Chụp giả lập", command=self.capture_image)
        self.capture_btn.pack(side="left", padx=3)
        if self.capture is None:
            self.capture_btn.config(state="disabled")
        self.model = tk.StringVar(value="smart_farm")
        self.model_box = ttk.Combobox(toolbar, textvariable=self.model, values=list(MODELS), state="readonly", width=15)
        self.model_box.pack(side="left", padx=5)
        self.conf, self.iou = tk.StringVar(value="0.25"), tk.StringVar(value="0.45")
        ttk.Label(toolbar, text="Confidence").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.conf, width=6).pack(side="left", padx=3)
        ttk.Label(toolbar, text="IoU").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.iou, width=6).pack(side="left", padx=3)
        self.run_btn = ttk.Button(toolbar, text="Phân tích", command=self.analyze)
        self.run_btn.pack(side="left", padx=5)
        self.export_btn = ttk.Button(toolbar, text="Xuất PNG + JSON", command=self.export, state="disabled")
        self.export_btn.pack(side="left", padx=3)
        options = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        options.pack(fill="x")
        self.crop, self.regions = tk.BooleanVar(value=False), tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="Crop đối chiếu", variable=self.crop).pack(side="left")
        ttk.Checkbutton(options, text="Quét vùng (ứng viên ?)", variable=self.regions).pack(side="left")
        self.boxes, self.masks, self.compact = (tk.BooleanVar(value=True) for _ in range(3))
        for text, var in (("Box", self.boxes), ("Mask", self.masks), ("Nhãn gọn", self.compact)):
            ttk.Checkbutton(options, text=text, variable=var, command=self.render).pack(side="left", padx=5)
        ttk.Button(options, text="Vừa khung", command=self.fit).pack(side="left", padx=5)
        self.plan_btn = ttk.Button(options, text="Xem kịch bản thử", command=self.preview_plan, state="disabled")
        self.plan_btn.pack(side="left", padx=5)
        pane = ttk.Panedwindow(self.root, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=8)
        self.canvas = tk.Canvas(pane, bg="#18202b", highlightthickness=0)
        pane.add(self.canvas, weight=3)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<ButtonPress-1>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B1-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.table = ttk.Treeview(pane, columns=("id", "name", "score", "candidate"), show="headings", height=15)
        for name, label, width in (("id", "#", 30), ("name", "Lớp", 170), ("score", "Điểm", 60), ("candidate", "Ứng viên", 70)):
            self.table.heading(name, text=label)
            self.table.column(name, width=width)
        pane.add(self.table, weight=1)
        self.status = tk.StringVar(value="Mở ảnh hoặc chụp giả lập để kiểm tra. Không thực hiện thao tác trong game.")
        ttk.Label(self.root, textvariable=self.status, wraplength=1100, padding=8).pack(fill="x")
        self.note = tk.StringVar(value="Deploy Zone / Spell Target dành cho Clan Capital. Điểm model không phải lượng tài nguyên.")
        ttk.Label(self.root, textvariable=self.note, wraplength=1100, padding=(8, 0, 8, 8)).pack(fill="x")

    def _busy(self, active):
        state = "disabled" if active else "normal"
        self.open_btn.config(state=state)
        self.run_btn.config(state=state)
        self.capture_btn.config(state=state if self.capture else "disabled")
        self.export_btn.config(state=state if self.result else "disabled")
        self.plan_btn.config(state=state if self.result and self.result.model == "smart_farm" else "disabled")

    def _submit(self, function):
        if self.jobs.submit(function):
            self._busy(True)
            self.status.set("Đang xử lý…")

    def open_image(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if path:
            self._submit(lambda: ("image", read_image(path), path))

    def capture_image(self):
        if self.capture:
            self._submit(lambda: ("image", self.capture(), "ADB screenshot"))

    def analyze(self):
        if self.image is None:
            messagebox.showinfo("Chưa có ảnh", "Mở ảnh hoặc chụp giả lập trước.", parent=self.root)
            return
        try:
            conf, iou = float(self.conf.get()), float(self.iou.get())
            if not 0 < conf <= 1 or not 0 < iou <= 1:
                raise ValueError("Confidence và IoU phải nằm trong (0, 1].")
            model, crop, regions = self.model.get(), self.crop.get(), self.regions.get()
            if crop and regions or model != "smart_farm" and (crop or regions):
                raise ValueError("Crop/quét vùng chỉ dùng Smart Farm và không bật cùng lúc.")
        except ValueError as exc:
            messagebox.showerror("Tham số không hợp lệ", str(exc), parent=self.root)
            return
        image, source = self.image.copy(), self.source
        def work():
            result = self.engine.infer(image, source, model, conf, iou, crop, regions)
            observation = ScreenDetector().detect(image)
            return "result", result, observation.metadata()
        self._submit(work)

    def _poll(self):
        if self.jobs.closed:
            return
        try:
            received = self.jobs.receive()
            if received:
                value, error = received
                if error:
                    self.status.set("Lỗi: " + error)
                    messagebox.showerror("Không phân tích được", error, parent=self.root)
                elif value[0] == "image":
                    _, self.image, self.source = value
                    self.result = None
                    self.table.delete(*self.table.get_children())
                    self.display_rgb = self.image[:, :, ::-1].copy()
                    self.fit()
                    self.status.set(f"{self.source} — {self.image.shape[1]}×{self.image.shape[0]}")
                elif value[0] == "result":
                    _, self.result, observation = value
                    self.table.delete(*self.table.get_children())
                    for i, detection in enumerate(self.result.detections, 1):
                        self.table.insert("", "end", values=(i, detection['class_name'], f"{detection['confidence']:.3f}",
                                                             f"? ({detection.get('supporting_views', 0)})" if detection.get('candidate_only') else ""))
                    metadata = self.result.metadata()
                    counts = metadata.get("baseline_predictions")
                    candidates = sum(bool(d.get("candidate_only")) for d in self.result.detections)
                    summary = f"Kho: {counts['storages']} | Mỏ: {counts['extractors']} | Ứng viên riêng: {candidates}" if counts else f"{len(self.result.detections)} dự đoán"
                    self.status.set(f"{self.result.model}: {summary} | Inference {self.result.inference_ms:.0f} ms | Màn hình: {observation['state']}")
                    self.note.set(f"Kết quả dùng conf={self.result.parameters['confidence']}, IoU={self.result.parameters['nms_iou']}. "
                                  "Dự đoán chưa được xác nhận; ứng viên ? không dùng để lập hành động tự động.")
                    self.render()
                elif value[0] == "export":
                    self.status.set(f"Đã xuất: {value[1]}")
                self._busy(False)
        except queue.Empty:
            pass
        self._poll_id = self.root.after(100, self._poll)

    def render(self):
        if self.result:
            self.display_rgb = rendered_rgb(self.result, self.masks.get(), self.boxes.get(), self.compact.get())
        if self.display_rgb is not None:
            height, width = self.display_rgb.shape[:2]
            resized = Image.fromarray(self.display_rgb).resize((max(1, round(width * self.zoom)), max(1, round(height * self.zoom))))
            self.photo = ImageTk.PhotoImage(resized)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
            self.canvas.config(scrollregion=(0, 0, resized.width, resized.height))

    def fit(self):
        if self.display_rgb is not None:
            height, width = self.display_rgb.shape[:2]
            self.zoom = min(max(100, self.canvas.winfo_width()) / width, max(100, self.canvas.winfo_height()) / height)
            self.render()

    def _wheel(self, event):
        self.zoom = min(4, max(.1, self.zoom * (1.15 if event.delta > 0 else 1 / 1.15)))
        self.render()

    def export(self):
        if self.result is None:
            return
        path = filedialog.askdirectory(parent=self.root, title="Thư mục lưu kết quả")
        if path:
            directory = Path(path) / datetime.now().strftime("vision_%Y%m%d_%H%M%S_%f")
            result = self.result
            masks, boxes, compact = self.masks.get(), self.boxes.get(), self.compact.get()
            self._submit(lambda: ("export", str(export_result(directory, result, masks, boxes, compact))))

    def preview_plan(self):
        if self.result is None or self.result.model != "smart_farm":
            return
        from cocbot.game.strategy import build_preview_plan, save_plan
        plan = build_preview_plan(self.result)
        path = Path(user_path("logs/plans")) / datetime.now().strftime("plan_%Y%m%d_%H%M%S_%f.json")
        save_plan(path, plan)
        self.status.set(f"Kịch bản chạy thử: {plan['status']} | {len(plan['actions'])} bước | {path}")

    def close(self):
        self.jobs.close()
        self.root.after_cancel(self._poll_id)
        self.root.destroy()


def main():
    root = tk.Tk()
    VisionLab(root)
    root.mainloop()


if __name__ == "__main__":
    main()
