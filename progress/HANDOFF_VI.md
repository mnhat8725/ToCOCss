# Hồ sơ bàn giao AutoCOCVN và định hướng nâng cấp repo

Ngày tổng hợp: 08/11/2026 (Asia/Saigon).

## 1. Cách dùng tài liệu

Mang nguyên file này sang repo đích và yêu cầu người triển khai đọc trước khi sửa code. Tài liệu gom chức năng tool, các điều chỉnh đã ghi nhận và kế hoạch nâng cấp thành dự án có cấu trúc, kiểm thử và khả năng đóng gói.

Phạm vi tổng hợp là tài liệu, mã nguồn ONNX Image Lab, cấu hình và kết quả kiểm tra đang lưu trong workspace AutoCOCVN. Lịch sử trao đổi trước đó không được cung cấp đầy đủ trong lượt tổng hợp này; các yêu cầu “vừa rồi” chỉ được ghi là đã xác nhận khi có dấu vết trong tài liệu/code. Các phần đề xuất bên dưới là định hướng bàn giao, chưa phải thay đổi đã triển khai hay cam kết đã được người dùng duyệt từng mục.

Đây là **một file thông tin**, không nhúng mã nguồn, model ONNX, ảnh mẫu hoặc binary. Repo đích có thể dùng riêng file này để lập kế hoạch; để chạy lại tool cần bổ sung các tài nguyên tại mục 10.

## 2. Hai thành phần cần phân biệt

| Thành phần | Hiện trạng | Vai trò |
|---|---|---|
| AutoCOCVN gốc | Bộ phần mềm đã đóng gói; `version.json` ghi 6.0.5, build 23/07/2026 | Quản lý và tự động hóa các luồng Clash of Clans; phần lớn logic ở module Python biên dịch |
| ONNX Image Lab | Mã Python mới, giao diện tiếng Việt; phiên bản 0.3 | Kiểm tra độc lập ba model trên ảnh có sẵn, xem dự đoán, xuất PNG/JSON |

AutoCOCVN có launcher/manager .NET tại `AutoCOCVN.exe`. `bin/bot.exe` là native x64, import Python 3.12; các `.pyd` có bằng chứng mạnh là mã biên dịch Nuitka. Không xem đây là gói PyInstaller có thể lấy lại nguyên vẹn toàn bộ `.py`.

Image Lab dùng PySide6, OpenCV, NumPy, ONNX Runtime CPU và được đóng gói bằng PyInstaller. GUI này được viết mới, không phải mã nguồn AutoCOCVN đã phục hồi.

## 3. Danh mục chức năng AutoCOCVN gốc

Quy ước mức bằng chứng:

- **Mã giả/metadata:** có kết quả phân tích tĩnh; không đồng nghĩa đã chạy thành công trong game.
- **Cấu hình:** có khóa thiết lập trên đĩa; chưa xác nhận toàn bộ hành vi runtime.
- **Changelog:** phần mềm tự công bố trong `version.json`; chưa kiểm chứng độc lập.

| Nhóm | Chức năng cần tham chiếu khi nâng cấp | Bằng chứng hiện có |
|---|---|---|
| Quản lý | Manager, cấu hình profile, tài khoản và lựa chọn giả lập | Launcher, `account_manager.pyd`, `manager_config.json`, thư mục `user_configs`, khóa `SELECTED_EMULATOR_NAME`; logic quản lý chưa phục hồi đầy đủ |
| Làng chính | Đánh thường/farm, đánh rank, lọc tài nguyên tối thiểu, chọn combo | Tên hàm `perform_normal_attack_sequence`, `perform_rank_battle_sequence`; `MIN_GOLD`, `MIN_ELIXIR`, `MIN_DARK_ELIXIR`, `MIN_SUM`, `ATTACK_MODE`, `ATTACK_COMBO` |
| Smart Farm | Phát hiện công trình tài nguyên đầy và chấm điểm hướng đánh | `smart_farm.pyd`, mã giả các hàm phân tích, detect, NMS, tính điểm |
| Kịch bản thả | Thả lính/tướng/phép/xe công thành, dùng kỹ năng, delay, đổi hướng tọa độ | `custom_deploy.pyd`, `CustomDeployParser.execute_sequence`, `coords.json` |
| Làng đêm | Chuỗi đánh riêng, giới hạn cúp, nhận tiên dược, nâng tường | Tên `perform_night_village_attack_sequence`, các khóa `NIGHT_*`, `UPGRADE_WALLS_*_NIGHT`; changelog có sửa nhận tiên dược |
| Clan Capital | Raid, nhận diện vùng thả và cụm công trình | `clan_capital.pyd`, model `deploy_zone`, `spell_target`, các khóa `CAPITAL_RAID_*` |
| Nâng cấp | Công trình, Nhà Chính, Hội Thành, lính, phép, tướng, hai làng | Cấu hình `AUTO_UPGRADE_BUILDING`, `AUTO_UPGRADE_TROOP`, các danh sách lựa chọn; changelog 6.0.5 |
| Tường | Nâng bằng tài nguyên được chọn, khi đầy hoặc theo số trận; tùy chọn 10 tường/lần | Các khóa `WALL_UPGRADE_*`, `ATTACKS_BEFORE_WALL_UPGRADE*`; changelog |
| Xin/cho quân | Xin lính theo cooldown; donate theo thiết lập, chu kỳ và tài nguyên | `USE_REQUEST_TROOPS`, `TROOP_REQUEST_COOLDOWN`, `ENABLE_DONATE`, `AUTO_DONATE_*`, `DONATE_*` |
| Chế độ chỉ xin/cho quân | Cần làm rõ ý nghĩa chính xác trước khi port | Changelog tiếng Việt ghi “chỉ xin lính”, tiếng Anh ghi “Donate Only”; hai bản mô tả không đồng nhất |
| Chuyển đổi | Chuyển làng theo trận/thời gian; đổi tài khoản và chu kỳ | `VILLAGE_SWITCH_*`, `SWITCH_*`, file tài khoản; chưa xác minh mọi quan hệ giữa các khóa |
| Clan Games | Thiết lập chọn nhiệm vụ/chuyển theo điểm | `clan_games.json`, `CG_*`; mới ở mức cấu hình |
| Kết thúc/rút lui | Điều kiện thời gian, tài nguyên, phần trăm phá hủy, smart surrender | Các khóa `SMART_SURRENDER*`, `SURRENDER_*`; chưa xác minh toàn bộ thứ tự/ưu tiên điều kiện |
| Lập lịch và dừng | Tự bắt đầu, dừng theo trận/phút/tài nguyên | `AUTO_START_*`, `AUTO_STOP_*` |
| Thống kê và debug | Tài nguyên farm, cúp, sao, log chi tiết, ảnh debug | `FARM_RESOURCE_STATS`, `ENABLE_TROPHY_TRACKING`, `ENABLE_STAR_STAT_TRACKING`, `ENABLE_DETAILED_LOG`, `DEBUG_IMAGE` |
| Thiết bị | Chụp màn hình, template matching, batch click, retry, delay ADB | Mã giả `lib_utils.pyd`; khóa `ADB_SAFE_MODE`, `ADB_COMMAND_DELAY`, các delay thao tác |
| Phân phối | Updater, UI cập nhật, đa ngôn ngữ, các module auth/integrity | Tên file `update.exe`, `updater.pyd`, `update_ui.pyd`, `lang.pyd`, `auth_sys.pyd`, `anti_tampering.pyd`; chưa phân tích đủ hành vi |

Tên khóa là điểm đối chiếu khi viết migration, không phải đặc tả đầy đủ về kiểu dữ liệu, đơn vị, giá trị mặc định hoặc thứ tự chạy. Không suy ra module đã hoàn thiện chỉ từ tên file hoặc tên thiết lập.

## 4. Chức năng ONNX Image Lab 0.3 đang có

- Mở PNG/JPG/BMP/WebP qua hộp thoại, kéo thả hoặc ảnh mẫu `top.png`, `mid.png`, `bottom.png`.
- Chọn Smart Farm, Spell Target hoặc Deploy Zone; điều chỉnh confidence và NMS IoU.
- Chạy inference ở worker thread, hiển thị ảnh, bảng nhãn/điểm/tọa độ, thời gian inference và tổng thời gian xử lý.
- Zoom bằng con lăn, kéo để di chuyển, vừa ảnh với khung; tùy chọn vẽ box, mask và nhãn gọn.
- Nhãn gọn mặc định dùng số thứ tự liên kết với bảng để giảm che ảnh.
- Smart Farm thống kê riêng kho, mỏ/máy khai thác và số dự đoán từng lớp; số tổng có thể gồm ứng viên quét vùng chưa xác nhận.
- Giữ crop 8–82% như tùy chọn thử nghiệm và quét thêm vùng như chế độ đối chiếu riêng.
- Lưu PNG của phần hiển thị và JSON của kết quả nhận diện; không sửa ảnh đầu vào.
- Tối đa 100 dự đoán trong kết quả; JSON có cờ cho biết đã cắt bớt.
- Kiểm tra ảnh tối thiểu 16×16 pixel, tối đa 100 MB và 24 megapixel; báo lỗi khi ảnh/model/đầu ra không hợp lệ.
- Có `--self-test OUTPUT_DIR` chạy GUI Qt offscreen, lưu kết quả và ảnh chụp kiểm tra.
- Chạy ngoại tuyến trên CPU; không kết nối ADB hay thực thi bot gốc.

## 5. Các yêu cầu và thay đổi đã ghi nhận

### 5.1. Phạm vi nhận diện: chỉ kho/mỏ đầy

`STORAGE_DIAGNOSIS.md` ghi nhận người dùng chỉ quan tâm kho/mỏ đầy. Giữ nguyên sáu nhãn `_full`, không đổi ý nghĩa thành nhận diện mọi công trình tài nguyên hoặc mọi trạng thái đầy/vơi.

| Class ID | Nhãn model | Ý nghĩa |
|---:|---|---|
| 0 | `gold_mine_full` | Mỏ vàng đầy |
| 1 | `gold_storage_full` | Kho vàng đầy |
| 2 | `elixir_collector_full` | Máy khai thác tiên dược đầy |
| 3 | `elixir_storage_full` | Kho tiên dược đầy |
| 4 | `de_drill_full` | Máy khoan hắc tiên dược đầy |
| 5 | `de_storage_full` | Kho hắc tiên dược đầy |

Đọc thứ tự lớp từ metadata ONNX. Không tự đảo kho/mỏ. Không diễn giải confidence là xác suất đã hiệu chuẩn, độ chính xác đo được hoặc lượng tài nguyên. Số 0 chỉ có nghĩa không có dự đoán vượt ngưỡng.

### 5.2. Thay đổi ở 0.2

- Mặc định dùng **toàn ảnh**, confidence **0.25**, NMS **theo lớp**, IoU **0.45**.
- Không tự bật crop khi chọn Smart Farm.
- Phân biệt thống kê kho với mỏ/máy khai thác và đưa thống kê vào JSON.
- Giữ crop Y `[int(H×0.08), int(H×0.82))` để so sánh. Muốn đối chiếu tham số khôi phục từ bot: bật crop, confidence 0.35, IoU 0.50, NMS không phân lớp, resize lấy phần nguyên.
- Không thay trọng số model. Các mặc định mới chưa được chứng minh tối ưu trên tập dữ liệu gán nhãn.

### 5.3. Thay đổi ở 0.3

- Dùng nhãn số mặc định; bảng giữ tên lớp tiếng Việt và điểm model.
- Thêm “Quét thêm vùng (cần đối chiếu)”, **tắt mặc định**, chỉ cho Smart Farm toàn ảnh, không kết hợp crop.
- Giữ kết quả toàn ảnh; quét tối đa 10 vùng bổ sung: bốn góc và tâm ở hai tỷ lệ 90%/75%, bỏ vùng trùng.
- Ứng viên bổ sung cần confidence ≥ `max(0.35, ngưỡng người dùng)` và ít nhất hai vùng khác nhau đồng ý cùng lớp.
- Loại box sát mép cắt bên trong vùng theo kiểm tra biên 3 pixel; gom ứng viên theo IoU người dùng, loại phần bổ sung trùng baseline/kết quả đã thêm với IoU > 0.3.
- Đánh dấu `?` và `candidate_only: true`, xuất `supporting_views`; các ứng viên vẫn được tính trong tổng đang hiển thị.
- Không thay model; không tuyên bố quét vùng đã sửa hết bỏ sót hay đã tăng recall.
- Bản build 0.3 nằm riêng tại `onnx_image_lab/dist-v0.3/ONNXImageLab/` vì bản cũ đang mở khi build.

### 5.4. Bài học từ chẩn đoán

Crop làm đổi tensor đầu vào, tỷ lệ/padding và ngữ cảnh, nên có thể làm mất dự đoán hoặc đổi lớp. Trên `bottom.png`, toàn ảnh có hai dự đoán kho tiên dược ở confidence 0.35; crop ở 0.25 chỉ còn một. Không quy mọi khác biệt về lỗi vẽ box hoặc NMS.

Ở `mid.png`, điểm kho rất thấp ngay trước NMS. Chỉ hạ nhẹ ngưỡng hay sửa GUI không đủ giải quyết. Quét vùng có thể tạo thêm nhầm loại: trên mẫu hiện có, chế độ 0.3 bổ sung 1 ứng viên ở mid, 3 ở top, 3 ở bottom, tất cả chưa được xác nhận đúng.

Muốn nâng chất lượng cần gán nhãn công trình đầy bị bỏ sót, đồng thời có kho/mỏ chưa đầy và công trình dễ nhầm làm đối chứng; đánh giá trên ảnh tách khỏi dữ liệu huấn luyện.

## 6. Model và luồng xử lý cần giữ đúng

| Model | Input NCHW | Output | Ngữ cảnh |
|---|---|---|---|
| `smart_farm.onnx` | 1×3×416×416 | 1×10×3549 | Sáu lớp công trình tài nguyên đầy |
| `spell_target.onnx` | 1×3×320×320 | 1×5×2100 | Một lớp `building_cluster`, được tham chiếu trong Clan Capital |
| `deploy_zone.onnx` | 1×3×1280×1280 | 1×37×33600 và 1×32×320×320 | Một lớp vùng thả + 32 hệ số mask và prototype segmentation cho Clan Capital |

Tiền xử lý Image Lab: đọc BGR → letterbox giữ tỷ lệ, nền 114 → RGB → NCHW float32 /255. Decode box tâm/kích thước, điểm lớp, NMS, bỏ padding và quy đổi về ảnh gốc; nếu crop phải cộng offset Y. Mask cần giải mã từ hệ số và prototype, đổi về không gian ảnh gốc.

Không dùng decoder có giả định objectness riêng nếu đầu ra model hiện tại không có trường đó. Luôn kiểm tra shape, metadata và số hữu hạn.

### Chọn hướng làng chính

Luồng tham chiếu: ảnh → Smart Farm → công trình tài nguyên → chấm điểm hướng → bộ tọa độ → kịch bản hành động.

`smart_farm.pyd` có bốn hướng `top_right`, `top_left`, `bottom_right`, `bottom_left`. Trọng số class 0–5: `1.0, 1.5, 1.0, 1.5, 1.2, 1.8`. Điểm kết hợp confidence, căn diện tích có chặn dưới và trọng số. Mã có hệ số phân vùng 0.3; không rút gọn thành bốn góc phần tư và gọi đó là bản sao chính xác thuật toán gốc. Caller có fallback khi không chọn được hướng; toàn bộ caller chưa phục hồi.

Profile `default` trong báo cáo đặt `SMART_FARM: false`; không suy ra mọi tài khoản hay phiên chạy đều dùng AI chọn hướng.

`coords.json` có preset `dragon`, `super_dragon`, `electro_dragon`, chia bốn hướng; các nhóm `troops`, `heroes`, `rage`, `freeze`, thêm `balloons` ở electro_dragon. Tọa độ lưu sẵn phụ thuộc hệ quy chiếu, độ phân giải và zoom.

`CustomDeployParser.execute_sequence` có action `drop_troop`, `drop_hero`, `drop_spell`, `drop_siege`, `use_ability`, `delay`, cùng kiểm tra dừng. Các tham chiếu tọa độ được mô tả gồm `@troops`, `@heroes`, `@rage`, `@freeze`, `@balloons`, `@custom`. Chi tiết transform chưa được xác minh toàn bộ.

### Vùng thả Clan Capital

Mask ONNX → loại UI/xử lý hình học → morphology/contour → chọn điểm bên trong vùng → kiểm tra điều kiện → lập hành động.

Có bằng chứng về xử lý một hoặc hai frame, giao mask, kernel ellipse 15×15 với `MORPH_CLOSE`, lọc diện tích, `distanceTransform`, `minMaxLoc`, HSV, `pointPolygonTest`, các nhánh CV/template và nhiều frame. Thứ tự fallback trong toàn bộ caller chưa được xác minh. Không mặc định tâm bounding box là tọa độ thả hợp lệ.

Ảnh mẫu hiện có là làng chính, không đủ đánh giá Deploy Zone cho Clan Capital. Hai model Spell Target/Deploy Zone không phải bộ nhận diện quân.

## 7. Bằng chứng kiểm tra và những phần chưa hoàn thành

`onnx_image_lab/verification/build_verification_v03.json` ghi:

- 15 ca source, 15 ca packaged và 6 kiểm tra giả lập đã pass.
- Ba model đóng gói giống byte với model đối chiếu gốc.
- GUI kiểm tra offscreen; đây là kiểm tra vận hành/hồi quy, không phải đo accuracy.

Những kết quả này là **bản ghi có sẵn**, không phải các bài kiểm tra được chạy lại khi tạo tài liệu bàn giao.

Ba model chạy được bằng ONNX Runtime CPU. `onnx.checker` từng báo lỗi thứ tự topo ở `spell_target`, nhưng runtime vẫn nạp và suy luận được; chưa sửa graph gốc.

Chưa có ground truth để báo precision/recall/mAP/IoU. Chưa huấn luyện lại, chưa chứng minh hết bỏ sót, chưa đối chiếu từng tensor với bot gốc.

Phân tích `core_engine.pyd` xác định được nhiều tên hàm qua code object, nhưng các thân hàm lớn đã timeout/vượt giới hạn. Không nói đã khôi phục đầy đủ main loop, kết thúc trận, thứ tự fallback hoặc mọi tính năng gốc. Các phân tích trước thực hiện tĩnh và inference ngoại tuyến, không chạy bot/ADB.

`DEPLOYMENT_ANALYSIS.md` tham chiếu `BATTLE_END.md`, nhưng file này không có tại vị trí được tham chiếu trong workspace khi tổng hợp. Phần kết thúc/rút lui vì vậy cần xem là thiếu tài liệu xác minh.

## 8. Định hướng nâng cấp repo đích — đề xuất triển khai

### 8.1. Nguyên tắc kiến trúc

Ưu tiên thích nghi với cấu trúc, ngôn ngữ và các chức năng đang có của repo đích. Nếu repo đã có UI hoặc engine ổn định, tích hợp qua interface; không mặc định viết lại toàn bộ bằng Python/PySide6.

Tách các trách nhiệm sau:

| Thành phần | Trách nhiệm |
|---|---|
| `capture` | Nguồn ảnh file/replay; adapter thiết bị riêng nếu cần triển khai sau |
| `vision` | Tiền xử lý, session, decoder, NMS, segmentation; không phát lệnh thao tác |
| `domain` | Detection, resource counts, direction scores, deploy region, trạng thái trận |
| `strategy` | Chấm điểm hướng/chọn mục tiêu; kết quả không đủ chắc phải có trạng thái rõ ràng |
| `scripts` | Schema action, preset, kiểm tra tọa độ, tham số và delay |
| `execution` | Dry-run/replay và adapter thao tác; hỗ trợ stop/cancel/timeout |
| `orchestration` | State machine của các luồng; trạng thái, timeout, retry, hồi phục |
| `config` | Schema có phiên bản, mặc định, validation, migration profile |
| `ui` | Hiển thị, cấu hình và điều khiển; worker xử lý nặng ngoài UI thread |
| `observability` | Log có cấu trúc, ảnh/JSON debug, thời gian từng giai đoạn và nguyên nhân fallback |

Mọi tọa độ cần ghi rõ đang ở ảnh gốc, crop, letterbox, mask hay thiết bị. Có hàm đổi hệ tọa độ được kiểm tra. Không dùng hằng pixel ngầm cho mọi độ phân giải.

### 8.2. Lộ trình theo thứ tự

1. **Khảo sát repo đích:** đọc hướng dẫn repo, công nghệ, điểm khởi chạy, model, config và test; lập bảng chức năng đang có/thiếu/khác hành vi so với tài liệu này. Ghi riêng dữ liệu chưa đủ xác định.
2. **Dựng baseline nhận diện:** tách engine, giữ nguyên model, đọc metadata; tái tạo chế độ toàn ảnh và crop đối chiếu; giữ đường xuất PNG/JSON và nhãn ứng viên.
3. **Cải thiện kiểm chứng:** bộ ảnh gán nhãn đúng ngữ cảnh, gồm đầy/chưa đầy/ảnh trống/loại dễ nhầm/nhiều tỷ lệ; đánh giá precision/recall từng lớp và false positive. Giữ riêng kết quả baseline và candidate khi đánh giá.
4. **Hoàn thiện UX:** thống kê kho/mỏ rõ ràng; chỉ ra số ứng viên chưa xác nhận, tham số đang dùng, trạng thái xử lý và lỗi dễ hiểu; không chặn UI khi inference.
5. **Chiến lược và kịch bản:** chuẩn hóa hướng, preset, schema action và state machine; trước hết chạy dry-run trên ảnh/replay, ghi hành động dự kiến; bổ sung điều kiện dừng, timeout và fallback bằng yêu cầu cụ thể.
6. **Tích hợp các luồng gốc theo nhu cầu dự án:** làng chính, làng đêm, Capital, nâng cấp, tài khoản, donate, Clan Games, lịch và thống kê. Với mục mới ở mức khóa config/changelog, phải xác định hành vi mong muốn trước khi gọi là port tương đương.
7. **Phân phối:** tài nguyên đi kèm, build tái lập, kiểm tra bundle trên máy thiếu Python, ghi version/changelog và hướng dẫn sử dụng.

### 8.3. Tiêu chí nghiệm thu

- Repo chạy theo hướng dẫn trên môi trường sạch, không phụ thuộc đường dẫn máy cũ.
- Giữ đúng sáu lớp `_full`, đọc class ID từ metadata; test có tình huống đổi lớp, cùng lớp/khác lớp chồng nhau và đổi hệ tọa độ.
- Mặc định toàn ảnh 0.25/0.45; crop/quét vùng tắt mặc định, loại trừ nhau, chỉ có ở Smart Farm.
- Quét vùng bảo toàn baseline trong giới hạn 100 kết quả; phần bổ sung có dấu `?`, cờ và số vùng hỗ trợ trong JSON.
- Xuất PNG/JSON khớp kết quả đang xem; ghi version, tham số, kích thước ảnh, thời gian, cờ cắt bớt và thống kê. Có thể bổ sung hash model để truy vết.
- Ảnh trống, ảnh lỗi, đường dẫn Unicode, kích thước không hợp lệ, model thiếu/shape sai được xử lý rõ ràng.
- GUI giữ khả năng tương tác, không cập nhật kết quả cũ vào ảnh mới; dừng/đóng cửa sổ xử lý worker đúng vòng đời.
- Pipeline chiến lược không biến `candidate_only` thành mục tiêu đã xác nhận một cách ngầm định; chính sách sử dụng ứng viên phải được khai báo.
- Chỉ kết luận tăng chất lượng khi có phép đo trên tập nhãn tách biệt; số khung nhiều hơn không phải tiêu chí duy nhất.
- Luồng điều khiển nếu được tích hợp có dry-run, stop/cancel, giới hạn retry và log trạng thái; mỗi tính năng mới có bài kiểm tra phù hợp hành vi.

## 9. Định dạng kết quả để repo đích tham chiếu

JSON hiện có từ `Result.metadata()` gồm:

```text
application, model, source, image_size [width,height], parameters,
inference_ms, total_ms, output_shapes, detection_count, detections,
truncated_to_100, resource_predictions, note

detection:
  class_id, class_name, confidence, box_xyxy [x1,y1,x2,y2]
  candidate_only, supporting_views       # chỉ ứng viên bổ sung
  mask_pixels, mask_fraction             # khi có segmentation

resource_predictions:
  storages, extractors, by_class         # chỉ Smart Farm
```

JSON hiện lưu thống kê mask, không nhúng toàn bộ bitmap mask. Nếu repo đích cần tái tạo mask đầy đủ, bổ sung định dạng export có phiên bản như PNG/RLE/polygon cùng hệ tọa độ; đây là phần nâng cấp đề xuất.

## 10. Tài nguyên, đường dẫn và chuyển repo

### File nên lấy thêm khi cần triển khai thực tế

- Source Image Lab: `main.py`, `app.py`, `engine.py`, `selftest.py`, `test_resource_decoder.py`, `diagnose_storage.py`, `diagnose_regions.py`.
- Build: `requirements.txt`, `build.ps1`, `ONNXImageLab.spec`.
- Tài liệu gốc: `onnx_image_lab/README.md`, `onnx_image_lab/STORAGE_DIAGNOSIS.md`, `analysis_output/REPORT.md`, `analysis_output/DEPLOYMENT_ANALYSIS.md`.
- Bằng chứng: `analysis_output/symbol_map.json`, `core_engine_function_names.json`, các bảng hằng, mã giả cần thiết và kết quả `onnx_image_lab/verification/`.
- Ba model và ảnh mẫu; không cần sao chép toàn bộ Python runtime/binary bot để viết lại engine nhận diện.

### Vướng mắc đường dẫn đã phát hiện

Source `engine.asset_root()` và file spec đang tìm tài nguyên ở `templates/` dưới thư mục gốc AutoCOCVN. Thư mục này **không xuất hiện ở cấp gốc workspace khi tổng hợp**. Tuy nhiên bundle 0.3 có:

```text
onnx_image_lab/dist-v0.3/ONNXImageLab/_internal/models/
  smart_farm.onnx
  spell_target.onnx
  deploy_zone.onnx
onnx_image_lab/dist-v0.3/ONNXImageLab/_internal/samples/
  top.png
  mid.png
  bottom.png
```

Nếu dùng bundle làm nguồn chuyển, kiểm tra hash rồi đưa model/ảnh vào thư mục assets của repo đích; cập nhật resolver và spec cùng lúc. Không giả định chỉ copy `.py` là chạy được. `build.ps1` cũng phụ thuộc `.analysis_tools/python312/python.exe`; cần đổi sang môi trường Python/venv của repo đích.

### Dependency của bản hiện có

```text
Python 3.12 (môi trường portable đang dùng)
numpy==2.2.6
opencv-python-headless==4.12.0.88
onnxruntime==1.23.2
PySide6-Essentials==6.10.1
pyinstaller==6.16.0
pyinstaller-hooks-contrib==2026.9
```

Đây là snapshot của bản hiện có, không phải danh sách phiên bản mới nhất hay yêu cầu bắt buộc cho mọi repo. Nếu nâng dependency, chạy hồi quy tương ứng.

### SHA-256 model theo bản ghi xác minh 0.3

| Model | SHA-256 |
|---|---|
| smart_farm | `06b067110fee3afc6fde890280ee87f8789c29f9bbf06ee40ffc5a93c84e810f` |
| spell_target | `4e4ced8baa68030d5c88c2d59ef90862e5486f6822c213c9f5694862c3edef92` |
| deploy_zone | `8bb9fdeb55f4188c7ac35fff3adbb207b7b542a287ca824e47bff8ca43fa6105` |

Không đưa tài khoản cá nhân, token/license hay toàn bộ config người dùng vào tài liệu công khai. Khi migration config, dùng mẫu đã lược dữ liệu cá nhân và chỉ đưa các trường cần thiết.

## 11. Lệnh tham chiếu

Các lệnh dưới đây dùng cấu trúc workspace cũ và yêu cầu khôi phục đúng assets nguồn trước khi chạy:

```powershell
.\.analysis_tools\python312\python.exe -B onnx_image_lab\main.py
.\.analysis_tools\python312\python.exe -B onnx_image_lab\test_resource_decoder.py
.\.analysis_tools\python312\python.exe -B onnx_image_lab\main.py --self-test onnx_image_lab\verification\source_migration
powershell -NoProfile -ExecutionPolicy Bypass -File onnx_image_lab\build.ps1 -DistFolder dist-migration
```

Muốn dùng bản 0.3 đã đóng gói, mở `onnx_image_lab/dist-v0.3/ONNXImageLab/ONNXImageLab.exe` và giữ nguyên `_internal` bên cạnh. EXE không chạy độc lập khi tách khỏi thư mục phụ thuộc.

## 12. Prompt dùng ngay ở repo đích

> Đọc toàn bộ progress/HANDOFF_VI.md cùng hướng dẫn của repo này. Mục tiêu là nâng cấp dự án hiện có theo các chức năng và điều chỉnh đã ghi nhận trong tài liệu, ưu tiên tái sử dụng kiến trúc repo.
>
> Trước tiên khảo sát source, cấu hình, UI, model, tài nguyên và test. Lập bảng đối chiếu chức năng hiện có/thiếu/khác hành vi; phân biệt chức năng có bằng chứng mã giả, chỉ có config/changelog và phần đề xuất. Không xem mọi tính năng AutoCOCVN là đã có mã nguồn để port.
>
> Triển khai theo từng bước chạy được: baseline nhận diện → GUI/thống kê/export → kiểm chứng dữ liệu → chiến lược/kịch bản/dry-run → các luồng tự động hóa phù hợp phạm vi repo → đóng gói. Giữ mặc định Smart Farm toàn ảnh 0.25/0.45; sáu lớp chỉ kho/mỏ đầy; crop và quét vùng là tùy chọn đối chiếu, ứng viên bổ sung luôn được đánh dấu rõ.
>
> Xử lý đường dẫn assets và môi trường build để dự án chạy độc lập máy cũ. Không phụ thuộc module .pyd gốc cho engine viết mới. Khi thiếu model/ảnh, nêu chính xác tài nguyên thiếu và tiếp tục phần độc lập với chúng. Kiểm tra đúng ngữ cảnh Clan Capital cho Deploy Zone.
>
> Sau mỗi phần triển khai, chạy kiểm tra phù hợp và báo thay đổi, kết quả, giới hạn. Không tuyên bố tăng accuracy/recall nếu chưa có đánh giá trên tập nhãn tách biệt. Những chi tiết thuật toán gốc chưa phục hồi phải được ghi rõ là quyết định triển khai mới hoặc cần xác minh.

