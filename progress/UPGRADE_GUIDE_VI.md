# Bản nâng cấp nhận diện và kiểm chứng

Bản này bổ sung vào bot Tkinter/ADB hiện tại. Source giải mã được thích nghi
từ ONNX Image Lab 0.3 tìm thấy trong workspace cũ; runtime không phụ thuộc vào
đường dẫn workspace đó. Ba model giữ nguyên trọng số và tên lớp.

## Mở và kiểm tra

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe tools\1.py
.venv\Scripts\python.exe main.py --selftest
.venv\Scripts\python.exe main.py --vision-lab
```

`--vision-lab` mở công cụ ảnh độc lập, không cần giả lập. Trong GUI farm có
nút **Kiểm tra ảnh**, mở cùng công cụ với chức năng **Chụp giả lập**.

Chọn ảnh, model và bấm **Phân tích**. Toàn ảnh, confidence 0.25, IoU 0.45,
NMS theo lớp là baseline Smart Farm. Crop/quét vùng tắt mặc định và loại trừ
nhau. Bảng hiển thị class ID qua số thứ tự, tên lớp và điểm; ảnh hỗ trợ zoom,
kéo, bật/tắt box/mask và nhãn gọn. Ứng viên quét vùng được đánh dấu `?` và
thống kê riêng; chúng không đi vào kế hoạch hành động.

**Xuất PNG + JSON** lưu overlay đúng tùy chọn đang xem, tham số của kết quả,
hash model và mask PNG đầy đủ ở hệ tọa độ ảnh gốc. Việc thay ngưỡng sau khi
phân tích không làm thay đổi kết quả cũ; bấm Phân tích để tạo kết quả mới.

**Xem kịch bản thử** ghi JSON vào `logs/plans/`. Điểm ở đây chỉ minh họa một
chiến lược chia bốn góc mới, chưa xác minh là vùng thả hợp lệ. Kịch bản này
có `dry_run_only=true`, bộ thực thi sẽ từ chối chạy thật.

## Luồng farm mới

- Smart Farm phụ trách tọa độ kho/mỏ đầy; model .pt cũ và EasyOCR phụ trách
  vùng chữ/tài nguyên/loot. Không đổi nghĩa sáu lớp `_full` thành mọi công trình.
- Màn hình phải được xác nhận qua hai ảnh liên tiếp trước các bước quan trọng.
  Các trạng thái gồm home, match_menu, preview, battle, results và unknown.
- Khi unknown hoặc timeout, bot lưu ảnh và bằng chứng rồi dừng. Khi đọc tài
  nguyên thất bại nhưng vẫn xác minh được preview, bot có thể chuyển đối thủ
  trong giới hạn retry. Không bấm chuỗi retry tọa độ mù trong chế độ có guard.
- OCR phân biệt số 0 hợp lệ và không đọc được; các tài nguyên đang đặt ngưỡng
  phải có hai lần đọc nhất quán. Loot dùng các giá trị được xác nhận ít nhất
  hai lần, thay vì lấy giá trị lớn nhất từng thấy.
- Chiến thuật live vẫn là quét hàng goblin đã có, được chuyển thành action
  có tọa độ chuẩn hóa và thực thi có giới hạn. Mặc định tối đa 3 đợt/30 giây;
  không suy luận tỷ lệ phá hủy hoặc lượng loot từ việc mất detection.
- Điểm dừng được kiểm tra giữa các lần bấm. Một lệnh ADB đang chạy vẫn có
  thể cần chờ đến khi trả về hoặc hết timeout của lệnh đó.

Template trạng thái là giả thuyết cần kiểm tra với ngôn ngữ/skin/zoom của game
thực tế. Quét hàng goblin cũng chưa phải thuật toán vùng thả cho làng chính.

## Cấu hình

Giữ nguyên phần `controls` đã hiệu chỉnh trong settings.json. Các trường mới
có thể bổ sung cùng các trường cũ:

```json
{
  "schema_version": 1,
  "vision": {
    "layout_backend": "smart_farm",
    "smart_farm_confidence": 0.25,
    "smart_farm_iou": 0.45,
    "template_threshold": 0.85,
    "state_timeout": 12
  },
  "attack": {"time_limit": 30, "max_waves": 3},
  "farm": {"targets": [500000, 500000, 0], "goals": [20000000, 20000000, 0]}
}
```

GUI lưu ngưỡng/mục tiêu khi Start. Ghi settings dùng tệp tạm ngay trong thư mục
đích rồi thay nguyên tử. JSON hỏng được báo rõ khi khởi động; các tọa độ cũ
không bị tự ghi đè. `layout_backend=legacy` dùng lại detector công trình .pt.
`attack.drain_ratio` cũ không còn điều khiển kết thúc trận.

## Log kiểm thử và chẩn đoán

```powershell
.venv\Scripts\python.exe tools\verify_step.py regression
.venv\Scripts\python.exe tools\verify_step.py models python tools\verify_models.py
.venv\Scripts\python.exe tools\verify_step.py widgets python tools\verify_ui.py
.venv\Scripts\python.exe tools\1.py
```

Mỗi lần verify tạo `.log` + `.json` trong `logs/verification/`, gồm thời điểm
UTC+7, câu lệnh, exit code, thời lượng và toàn bộ output. Kết quả FAIL được giữ
lại; lần chạy sau tạo tệp mới. Log phiên farm/chẩn đoán ở `logs/sessions/`
gồm JSONL và ảnh khi cần. Chẩn đoán ADB chỉ chụp/nhận diện, không bấm trong game.

## Chuẩn bị và train Smart Farm

Manifest đã khởi tạo tại `datasets/smart_farm/manifest.json`, hiện chưa có nhãn.
Mỗi ảnh cần một bản ghi, ví dụ:

```json
{
  "image": "images/train/raid001.png",
  "label": "labels/train/raid001.txt",
  "split": "train",
  "group": "village001_raid001",
  "reviewed": true
}
```

Giữ đúng `names` trong manifest. Label YOLO là `class cx cy width height`
chuẩn hóa 0..1; ảnh đối chứng không có mục tiêu dùng tệp label trống đã được
kiểm tra. Cần có train/val/test riêng, không trùng pixel hoặc cùng nhóm trận
giữa các tập. Không đánh dấu ứng viên từ model là reviewed trước khi kiểm tra.

```powershell
.venv\Scripts\python.exe tools\verify_step.py dataset python tools\dataset_tool.py validate datasets\smart_farm\manifest.json
.venv\Scripts\python.exe tools\train_model.py datasets\smart_farm\manifest.json
.venv\Scripts\python.exe tools\verify_step.py training python tools\train_model.py datasets\smart_farm\manifest.json --epochs 50 --execute
```

Lệnh train mặc định chỉ kiểm tra/xuất cấu hình. Có `--execute` mới train và
đánh giá tập test; đầu ra ở `runs/training/`, không thay model đang chạy.
Chưa có dữ liệu nhãn thật nên chưa thực hiện training, chưa có precision/recall/mAP.

## Clan Capital và phạm vi còn lại

Spell Target và Deploy Zone chạy được trong công cụ ảnh bằng ONNX Runtime CPU.
Hàm thử điểm thả chỉ chấp nhận ngữ cảnh `clan_capital`, chọn điểm trong mask
đã loại UI/co biên và luôn đánh dấu dry-run. Chưa có ảnh Capital được gán nhãn
hoặc replay Capital để nghiệm thu luồng đánh tự động.

Chưa triển khai tự nâng cấp công trình, đổi tài khoản, donate và Clan Games.
Handoff mới có nhiều phần ở mức cấu hình/changelog; cần quy tắc thao tác và
dữ liệu kiểm chứng cụ thể trước khi mở rộng các luồng này.
