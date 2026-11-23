# Tiến độ dự án

Mục tiêu: bot dùng riêng, **nhìn ảnh base → hiểu base → tự đánh**, chạy qua ADB trên giả lập.

Ký hiệu: ✅ xong · 🔄 đang làm · ⬜ chưa làm · ❓ cần quyết định

---

## Quy trình

```
B0 Nền tảng ─► B1 Thu ảnh ─► B2 Gán nhãn ─► B3 Train model ─► B4 Thanh quân ─► B5 Tự đánh ─► B6 Học từ trận (tuỳ chọn)
```

### B0. Nền tảng và dọn dẹp 🔄

Mục tiêu: bot điều hướng menu chắc chắn và không tap bừa.

- ✅ ADB: chụp màn hình và tap, toạ độ chuẩn hoá 0..1 — `adb.py`, `settings.json`
- ✅ Nhận diện màn hình bằng template, cần 2 frame xác nhận, gặp `unknown` thì không tap — `state_detection.py`
- ✅ Engine ONNX (letterbox, NMS, mask) và 3 model có sẵn — `onnx_engine.py`, `templates/models/`
- ✅ Bộ chạy hành động: validate, dry-run, stop, timeout — `execution.py`
- ✅ 49 test hồi quy đều pass (chạy bằng mock)
- ✅ 23/11: dọn `templates/`, gỡ 1 file hỏng và 86 file trùng (1.137 → 1.051 ảnh). Backup ở `backup/templates_removed_2026-11-23/`
- ✅ 23/11: gom code vào package `cocbot/` (core, device, vision, game, ui). Công cụ chuyển vào `tools/`. 49 test và self-test đều pass
- ⬜ Cắt lại 7 template trạng thái từ chính giả lập (1600×900, tiếng Anh). `next_button.png` đang dính số tiền, cần bỏ
- ⬜ Bổ sung chữ `p` cho `scid_chars` (file cũ gán nhầm thành chữ u)
- ⬜ Chạy 1 vòng farm thật, có người theo dõi

**Xong khi:** bot đi trọn Home → Find → Preview → Next → Attack → Results mà không bị `unknown`.

### B1. Thu ảnh base ⬜

- ⬜ Viết `tools/collect.py`: ở màn preview, chụp ảnh → bấm Next → lặp lại, có delay ngẫu nhiên
- ⬜ Lưu vào `datasets/raw/`, tên file theo thời gian, bỏ ảnh trùng
- ⬜ Thu ít nhất 300 base

**Lưu ý:** 3 ảnh `top/mid/bottom.png` là ảnh quảng cáo đã chỉnh sửa, không dùng để train.

### B2. Gán nhãn ⬜

- ❓ Chốt danh sách lớp. Phụ thuộc cấp Town Hall bạn chơi
- ⬜ Dựng Label Studio hoặc CVAT, dùng `smart_farm.onnx` và `best.pt` để gán nhãn trước
- ⬜ Gán nhãn vùng thả quân (polygon theo viền đỏ)
- ⬜ Nhập vào `datasets/` qua `tools/dataset_tool.py` (manifest, chia train/val/test, chống trùng)

Danh sách lớp dự kiến (khoảng 15–20): 6 lớp kho/mỏ đầy · Town Hall · Clan Castle · cannon · archer tower · mortar · wizard tower · air defense · inferno · x-bow · eagle · scattershot · bomb tower · …

### B3. Train model ⬜

- ❓ Có GPU NVIDIA không? Nếu chỉ có CPU thì train trên Colab
- ⬜ Detector công trình: YOLO, imgsz 960–1280 — `tools/train_model.py`
- ⬜ Model segmentation cho vùng thả quân ở làng chính
- ⬜ Đánh giá trên tập test riêng, ghi lại mAP theo từng lớp

**Xong khi:** mAP50 ≥ 0.8 với các lớp phòng thủ chính trên tập test.

### B4. Nhận diện thanh quân ⬜

- ⬜ Tìm từng ô trên thanh quân bằng icon quân/phép có sẵn (`archer.png`, `dragon.png`…)
- ⬜ Đọc số lượng còn lại (`x9`, `x14`) bằng OCR
- ⬜ Biết ô nào đang được chọn (dùng các bản `*_click.png`)

### B5. Tự đánh bằng luật (heuristic) ⬜

- ⬜ Base map: danh sách công trình, toạ độ, viền vùng thả
- ⬜ Chọn hướng tấn công: nhiều tài nguyên, ít phòng thủ
- ⬜ Mẫu thả quân cho từng loại army, thả dọc viền vùng thả qua `execution.py`
- ⬜ Thay đoạn quét goblin ngang hàng trong `bot.py` (`_initiate_attack`)
- ⬜ Theo dõi % phá huỷ và số sao để quyết định khi nào kết thúc trận

### B6. Học từ trận đánh tay (tuỳ chọn) ⬜

- ⬜ Ghi lại trận bạn tự đánh: ảnh, các lần tap (`adb getevent`), kết quả
- ⬜ Train model bắt chước: từ base map dự đoán thả gì, ở đâu

---

## Cần bạn trả lời

1. Bạn đang ở Town Hall mấy?
2. Máy có GPU NVIDIA không?
3. Bạn định dùng army gì để farm?

## Nhật ký

| Ngày | Việc |
|---|---|
| 08/11/2026 | Nâng cấp vision/ONNX, thêm state guard và execution, 49 test pass. Chi tiết: `LOG_2026-11-08_*.md` |
| 23/11/2026 | Phân tích tool, chốt hướng đi. Dọn templates. Gom tài liệu về `progress/`. Đóng gói code vào `cocbot/` |

## Cấu trúc code

| Thư mục | Nội dung |
|---|---|
| `main.py`, `run.bat` | Điểm chạy chính |
| `cocbot/core/` | Đường dẫn, cấu hình, settings, log, thông báo, ghi phiên |
| `cocbot/device/` | ADB: kết nối, chụp màn hình, tap |
| `cocbot/vision/` | Nhận diện màn hình, ONNX/YOLO, OCR |
| `cocbot/game/` | Vòng farm, chiến thuật, chạy hành động |
| `cocbot/ui/` | Giao diện bot, Vision Lab |
| `tools/` | calibrate, pinpoint, diagnose, prepare_models, dataset, train, verify |
| `tests/` | Test (`python -m unittest discover -s tests`) |

## Tài liệu trong thư mục này

| File | Nội dung |
|---|---|
| `PROGRESS.md` | File này: quy trình và trạng thái |
| `HANDOFF_VI.md` | Hồ sơ bàn giao AutoCOCVN: chức năng gốc, model, thuật toán |
| `UPGRADE_GUIDE_VI.md` | Cách dùng bản nâng cấp: vision lab, self-test, cấu hình |
| `TEMPLATE_ANALYSIS.md` | Phân tích thư mục `templates/` (số liệu cũ, trước khi dọn ngày 23/11) |
| `LOG_2026-11-08_review.md` | Rà soát lỗi và các bản sửa ngày 08/11 |
| `LOG_2026-11-08_verification.md` | Log kiểm thử ngày 08/11 (file bị lỗi encoding, mất dấu tiếng Việt) |
