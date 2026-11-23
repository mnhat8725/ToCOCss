# Rà soát dự án ngày 08/11/2026

## Nguyên nhân lỗi 502

`logs/bot.log` ghi nhận EasyOCR tải detection model bị HTTP 504 lúc 17:29,
và tải recognition model bị HTTP 502 lúc 17:35. Bot dừng ngay trong
`VisionManager.load()`, chưa hoàn thành trận nào. Đây là lỗi tải trọng số OCR.
`models/best.pt` đã có và nạp được.

Đã tải `english_g2.pth` từ bản phát hành chính thức của EasyOCR, xác minh
checksum và tái sử dụng `craft_mlt_25k.pth` đã tải trước đó. Hai model dùng
ngoại tuyến nằm trong `easyocr_data/model/` và không được đưa vào Git.

## Những lỗi đã sửa

- Chuẩn bị OCR riêng bằng `prepare_models.py`: thử lại tải lỗi, timeout socket,
  checksum, ghi tệp qua tệp tạm; phiên farm không tự tải trọng số.
- `run.bat` kiểm tra model OCR trước khi mở giao diện.
- `--selftest` thực sự nạp OCR ngoại tuyến; trước đây chỉ kiểm tra import nên
  vẫn báo đạt khi thiếu model OCR.
- Mục tiêu bằng 0 được bỏ qua; đạt đúng mục tiêu cũng kết thúc. Trước đây
  Dark Elixir bằng 0 vẫn yêu cầu tổng Dark lớn hơn 0 nên có thể chạy mãi.
- Khôi phục nút Start khi hiệu chỉnh thiếu/sai; kiểm tra tọa độ 0..1 và dữ liệu
  nhập là số nguyên không âm.
- Giữ trạng thái Error khi lỗi; tránh thông báo running đến sau khi worker lỗi.
- Stop/F12 được kiểm tra trước nút bấm, từng lần thả quân và sau thời gian chờ.
- Đóng giao diện gửi yêu cầu dừng worker.
- Xử lý ADB timeout/không chạy được thay vì truy cập `returncode` của `None`;
  ưu tiên độ phân giải Override khi ADB báo cả Physical và Override.
- Chặn vùng OCR vượt biên ảnh và tọa độ nút nằm ngoài pixel cuối màn hình.

## Các hạn chế còn lại cần ưu tiên

1. **Chuyển màn hình dựa vào tọa độ và thời gian chờ.** `_press_button()` chưa
   xác minh màn hình đích. Nếu mạng game chậm hoặc có hộp thoại, chuỗi thao tác
   có thể lệch trạng thái. Nên bổ sung nhận diện trạng thái trước/sau các bước
   tìm trận, đầu hàng và về nhà.
2. **OCR chưa phân biệt không đọc được với số 0.** `read_number()` trả `"0"`
   khi trống; `_scan_treasures()` chấp nhận cả kết quả chỉ đọc được một phần.
   Nên trả thêm độ tin cậy và đọc lại các tài nguyên đang được yêu cầu.
3. **Tổng loot chưa được đối chiếu.** `_scan_post_game()` giữ giá trị cao nhất
   qua các lần đọc; một lần OCR đọc quá cao có thể làm tổng và mục tiêu sai.
   Nên dùng nhiều kết quả đồng thuận hoặc kiểm tra giới hạn hợp lý.
4. **Chiến thuật còn cố định.** Khoảng quét 50 px và các margin dùng pixel,
   chưa co giãn theo độ phân giải; chưa đọc số quân, chưa xác minh thả quân
   thành công. Chỉ phù hợp chiến thuật goblin đang được triển khai.
5. **Chọn giả lập còn tự động quét cổng.** `EmulatorAdb` có thể chọn cổng khác
   nếu cổng cấu hình không kết nối được; giao diện chưa hiển thị/chọn rõ instance.
6. **Lưu cấu hình còn đơn giản.** `settings.py` ghi trực tiếp JSON và bỏ qua lỗi
   đọc; chưa có ghi nguyên tử/khôi phục bản sao hay báo rõ JSON hỏng. Ngưỡng và
   mục tiêu nhập trong GUI chưa được lưu qua lần mở ứng dụng tiếp theo.
7. **Phụ thuộc chưa khóa phiên bản.** `requirements.txt` chỉ có giới hạn dưới;
   cài ở máy khác có thể lấy bộ Torch/OpenCV/Ultralytics khác bộ vừa kiểm chứng.
   Nên có bộ phiên bản đã kiểm thử và hướng dẫn CPU/CUDA riêng.

## Phạm vi kiểm chứng

- Các kiểm thử hồi quy trong `tests/` không điều khiển giả lập.
- `main.py --selftest` nạp thành công YOLO và EasyOCR ngoại tuyến.
- Chạy suy luận YOLO trên ảnh kiểm tra thành công; OCR đọc ảnh chữ
  `1,234,567` thành `1234567`.
- Chưa xác minh độ chính xác nhận dạng trên màn hình game hiện tại, hiệu chỉnh
  từng nút hay một vòng farm thực tế. Cần kiểm tra với giả lập trước khi coi
  các giới hạn về chiến thuật và trạng thái màn hình đã được giải quyết.

## Chạy ứng dụng thực tế sau rà soát

- Mở được GUI và kết nối `127.0.0.1:5555`.
- Lần Start đầu phát hiện lỗi quyền đọc `craft_mlt_25k.pth`: tệp được di chuyển
  từ TemporaryDirectory giữ ACL riêng trên Windows. Đã chuyển staging trọng số
  sang thư mục model để kế thừa quyền đọc và tạo lại tệp bị ảnh hưởng.
- Chạy `main.py --selftest` bằng tài khoản Windows của người dùng: đạt, OCR
  nạp ngoại tuyến thành công sau sửa quyền.
- Chạy `diagnose.py`: chụp màn hình giả lập 1600x900 thành công, nạp cả hai
  bộ model và nhận diện được `attack_btn_home` trên màn hình hiện tại.
- Chẩn đoán chỉ đọc, không thả quân. Computer Use từ chối điều khiển cửa sổ
  Python, nên chưa kiểm chứng một vòng farm qua GUI sau sửa lỗi quyền.
