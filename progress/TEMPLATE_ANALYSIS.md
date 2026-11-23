# Phân tích thư mục templates

Kiểm tra ngày 08/11/2026. Chỉ đọc tài nguyên, tạo báo cáo và chạy suy luận
thử model; chưa tích hợp vào bot, chưa train và không điều khiển game.

## Kết quả kiểm kê

Thư mục có 1.148 tệp: 1.138 PNG theo phần mở rộng, 3 ONNX, 4 ICO và 3 ENC.
Pillow đọc được 1.137/1.138 ảnh có đuôi PNG. `x_shop.png` có header `ftyp/mif1`,
không phải PNG thật và chưa đọc được bằng bộ thư viện ảnh hiện tại.

Có 76 nhóm ảnh trùng nội dung pixel, tương ứng 86 bản sao dư. Ví dụ:
`archer.png`, `cungthu.png`, `event/main/archer.png`. Chưa xóa hoặc đổi tên vì
các tên này có thể phục vụ những ngữ cảnh khác nhau.

13 ảnh có độ trong suốt. `folder.png`, `pause.png`, `play.png`, `stop.png`
có RGB toàn màu đen nhưng alpha chứa hình dạng. Không được coi là ảnh trống;
chuyển trực tiếp sang grayscale và bỏ alpha sẽ mất thông tin của chúng.

Các nhóm chính: 160 ảnh `upgrade_names`, 169 `clan_games`, 162 `donate`,
68 `event`, 48 `digits`, 34 `walls`, 28 `clan_capital`, 25 `icons`,
20 `popup`, 62 `scid_chars`; còn lại nằm ở gốc và `models`.

## Nhận diện công trình và giao diện

Quan sát ảnh cho thấy `upgrade_names/main/gold_storage.png` là chữ
"Gold Storage", kích thước 140x27; `gold_mine.png` là chữ "Gold Mine",
103x25; `town_hall.png` là chữ "Town Hall", 103x22. Chúng phù hợp nhận
diện tên trong bảng thông tin/nâng cấp khi bảng đó hiện ra. Không thể coi
chúng là mẫu ngoại hình công trình để tìm vị trí trên bản đồ.

`upgrade_names` gồm 54 ảnh nhóm main, 31 night, 58 troop_main,
12 troop_night, 3 headings và 2 ảnh trực tiếp. Cần kiểm tra từng nhóm khi
tích hợp; chưa xác minh chính xác nhận dạng trên màn hình game thực tế.

Các ảnh `attack_button`, `find_match`, `start_attack`, `surrender`,
`return_home` có thể hỗ trợ xác minh bước chuyển màn hình, thay vì chỉ bấm
tọa độ rồi chờ. `goblin.png` và `goblin_click.png` là hai crop giao diện
khác nhau, không nên mặc định là hai loại quân hay coi cả hai là goblin tàng hình.

Ảnh có nhiều kích thước; chưa có thông tin độ phân giải chuẩn/ROI/ngưỡng
matching. Cần thử nhiều tỉ lệ, giới hạn vùng tìm và kiểm chứng false positive.
Ảnh nút có chữ tiếng Anh cần được kiểm tra với ngôn ngữ game thực tế.

## Ba model ONNX đã có sẵn

Thông tin lớp và kích thước dưới đây đọc từ chuỗi metadata nhúng trong tệp.
Smoke test dùng ảnh toàn 0, CPU và OpenCV 5.0.0 hiện có, không đánh giá độ
chính xác trên game và không đại diện cho benchmark ổn định.

| Model | Vai trò theo metadata | Input | Kết quả thử |
|---|---|---|---|
| smart_farm.onnx | Detection, 6 lớp công trình tài nguyên đầy | 416x416 | Nạp và suy luận được; output 1x10x3549 |
| deploy_zone.onnx | Segmentation, lớp deploy_zone | 1280x1280 | Nạp và suy luận được; outputs 1x37x33600 và 1x32x320x320 |
| spell_target.onnx | Detection, lớp building_cluster | 320x320 | OpenCV hiện tại lỗi parse Conv; metadata ghi half=True |

Sáu lớp của smart_farm:

- `gold_mine_full`, `gold_storage_full`
- `elixir_collector_full`, `elixir_storage_full`
- `de_drill_full`, `de_storage_full`

Đây là ứng viên phù hợp nhất để bổ sung nhận diện mục tiêu farm. Chỉ có
nhãn dạng `*_full`, nên chưa có cơ sở khẳng định model sẽ tìm đủ mọi kho/mỏ
ở mọi trạng thái. Không dùng số lượng detection của model này làm số lượng
toàn bộ công trình nếu chưa kiểm chứng.

`deploy_zone` cần xử lý output segmentation thành mask và chuyển tọa độ về
ảnh gốc. `spell_target` cần thử backend phù hợp hoặc bản export khác trước
khi dùng; lỗi OpenCV chưa đủ để kết luận trọng số bị hỏng.

Không thể chỉ đổi `config.model_path` sang smart_farm: code hiện tại yêu cầu
`gold`, `elixir`, `d_elixir`, `post_gold`... để OCR và tính loot, nhưng model
mới không có những lớp đó. Nên tách model tìm công trình khỏi phần đọc số.

## Khả năng train

Không thấy `.txt`, `.yaml`, `.json`, `.xml` chứa nhãn trong templates; không
có bộ ảnh toàn màn hình kèm bounding box/mask và tập train/validation/test.
Các template crop có thể hỗ trợ matching hoặc chuẩn bị dữ liệu, nhưng chưa
phải dataset detection/segmentation hoàn chỉnh.

Nếu "train" nghĩa là huấn luyện AI: ưu tiên đánh giá model ONNX sẵn có trên
ảnh màn hình thật; thu thập lỗi, gán nhãn công trình và vùng triển khai, tách
các trận/làng khác nhau sang các tập khác nhau rồi mới huấn luyện. Các ảnh
trùng không nên nằm ở cả train và validation/test. File .pt hiện có cũng cần
kiểm tra lớp và khả năng dùng làm điểm khởi đầu trước khi chọn cách train.

Nếu "train" nghĩa là huấn luyện/chọn quân trong game: đây chỉ là tài nguyên
nhận diện. Bot hiện tại vẫn chỉ có chiến thuật goblin, chưa có quy trình đọc
đội hình, chọn quân, xác nhận số lượng và xác minh thao tác từ bộ template này.

## Thứ tự tích hợp đề xuất

1. Dùng template kiểm tra các trạng thái tìm trận/đầu hàng/về nhà, lưu ảnh khi
   không khớp để chẩn đoán các lần scan fail trong log.
2. Thử smart_farm trên ảnh trận thật, vẽ bbox, đo false positive và đối chiếu
   với model cũ trước khi thay nguồn tọa độ công trình.
3. Thử mask deploy_zone và kiểm tra tọa độ triển khai hợp lệ trước khi nối
   với thao tác thả quân.
4. Thu thập/gán nhãn các trường hợp còn thiếu; chỉ train khi có dữ liệu và
   tiêu chí đo lường cụ thể. Chưa có số liệu precision/recall trong lần kiểm tra này.

Mã hiện tại chưa đọc `templates`; việc thêm thư mục chưa thay đổi hành vi bot.
Log phiên 18:06 đã nạp model cũ thành công nhưng còn lỗi scan layout/treasure,
nên cần phân biệt sai màn hình với model không nhận ra đối tượng trước khi train.

## Tái chạy kiểm tra

```powershell
.venv\Scripts\python.exe tools\audit_templates.py --check-onnx
```

Kết quả chi tiết: `logs/template_audit/inventory.json` và ảnh tổng hợp
`logs/template_audit/contact_sheet.png`. Các tệp này nằm trong logs, không
được đưa vào Git. Công cụ không tải gói mới, không đổi model và không xóa mẫu.
