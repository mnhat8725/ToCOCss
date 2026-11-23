# Ti?n ?? n?ng c?p v? log ki?m th?

Ng?y 08/11/2026. ??y l? tr?ng th?i th?c t? c?a l?n tri?n khai, kh?ng ph?i ??nh gi? accuracy.

## C?c b??c ?? tri?n khai

| B??c | K?t qu? tri?n khai | Ki?m ch?ng |
|---|---|---|
| 1. Tr?ng th?i m?n h?nh | Template ROI/nhi?u t? l?, x?c nh?n nhi?u frame, guard n?i v?o farm, ?nh v? JSON khi timeout | Ki?m th? unit v? tr??ng h?p m?n h?nh Android tr? unknown |
| 2. B? nh?n di?n ONNX | T?i s? d?ng Image Lab, metadata/shape/finite validation, baseline/crop/qu?t v?ng, hash model | C? 3 model ch?y ONNX Runtime CPU; 9 c?u h?nh Smart Farm tr?n top/mid/bottom |
| 3. Giao di?n ki?m tra | M? ?nh/ch?p ADB, box/mask/zoom, b?ng d? ?o?n, th?ng k? ri?ng ?ng vi?n, xu?t ?nh/JSON/mask | Ki?m th? widget Tk ?n v? v?ng ??i worker; ch?a ki?m tra thao t?c desktop tr?c quan |
| 4. Chi?n thu?t/th?c thi | Schema action, dry-run, stop/timeout, ?i?m chu?n h?a; chi?n thu?t goblin c? c? gi?i h?n | Replay m?t v?ng farm b?ng mocks, ki?m th? kh?ng b?m khi unknown/plan l?i/preview-only |
| 5. OCR v? c?u h?nh | Ph?n bi?t unreadable/0, ??ng thu?n nhi?u l?n ??c, ghi config nguy?n t? v? ki?m tra schema | Ki?m th? thi?u t?i nguy?n, outlier, t?p h?ng, NaN/?i?m ngo?i ?nh |
| 6. D? li?u/train | Manifest reviewed, ch?ng tr?ng pixel/c?ng tr?n gi?a split, export data.yaml, CLI train c? --execute | C?ng c? ??t test; d? li?u th?t ch?a c? nh?n n?n readiness FAIL c? ch? ??ch |
| Capital | Hai model ho?t ??ng trong lab; t?m ?i?m trong mask ch? ? ng? c?nh Capital, lu?n preview-only | Test h?nh h?c mask; ch?a c? nghi?m thu tr?n ?nh Capital th?t |

**49 ki?m th? h?i quy ??t.** Self-test n?p YOLO, OCR v? c? ba ONNX ngo?i tuy?n ??t.
Kh?ng thay tr?ng s? ho?c t? ??a model m?i train v?o bot.

## Ch?n ?o?n thi?t b?

L?n th? ??u k?t n?i ???c ADB nh?ng screencap th?t b?i. ?? b? sung th?ng b?o
chi ti?t l?i ADB. L?n ti?p theo ch?p ???c ?nh 1600x900, n?p c?c model th?nh c?ng.
?nh cho th?y m?n h?nh Android launcher, ch?a m? Clash of Clans. K?t qu? state
`unknown` v? kh?ng c? m?c ti?u Smart Farm ph? h?p v?i m?n h?nh n?y.

B?ng ch?ng: [events.jsonl](../logs/sessions/20261108T123528Z_2bb96965/events.jsonl)
v? [?nh g?c](../logs/sessions/20261108T123528Z_2bb96965/6f16849dff9349509e9ebc0c7f879d02.png).
Ch?a ch?y m?t tr?n th?t b?ng code m?i. V?ng farm trong test d?ng mocks,
kh?ng ???c coi l? ch?ng minh farm ?n ??nh tr?n game.

## C?c FAIL ?? ghi nh?n

- `03_ui_widgets`: sandbox kh?ng t?m/??c ???c Tcl c?a Miniforge. Ch?y l?i b?ng
  t?i kho?n Windows (`03_ui_widgets_user`) ?? PASS.
- `05_dataset_readiness`: manifest th?t ch?a c? b?n ghi g?n nh?n. Gi? nguy?n
  FAIL ?? th? hi?n training ?ang thi?u d? li?u, kh?ng s?a test ?? b?o xanh.
- ONNX Runtime 1.23.2 trong handoff kh?ng c? wheel cho Python 3.14 hi?n t?i;
  ?? c?i v? ki?m ch?ng 1.24.4. Kh?ng thay phi?n b?n model.

## Ph?n c?n c?n nghi?m thu

- C?c tr?ng th?i game th?t theo ng?n ng?/zoom hi?n t?i; m?t v?ng farm c? ng??i theo d?i.
- Nh?n ??ng/sai cho kho/m? ??y ?? ??nh gi? precision/recall v? train b? sung.
- ?nh v? k?ch b?n Clan Capital. T? n?ng c?p, ??i t?i kho?n, donate, Clan Games
  ch?a ???c tri?n khai trong ??t core n?y.

## Danh s?ch log c?a t?ng l?n ch?y

Log v? JSON ???c gi? ri?ng m?i l?n ch?y, bao g?m c?c l?n FAIL. ???ng d?n d??i
??y l? t?p local trong workspace; th? m?c logs ???c gitignore.

| B??c ki?m tra | K?t qu? | Th?i l??ng | Log ??y ?? |
|---|---|---|---|
| 00_baseline | PASS | 0.99 s | [20261108_184008_212963_00_baseline.log](../logs/verification/20261108_184008_212963_00_baseline.log) |
| 01_states | PASS | 0.693 s | [20261108_184600_940019_01_states.log](../logs/verification/20261108_184600_940019_01_states.log) |
| 02_decoder | PASS | 0.705 s | [20261108_191422_831668_02_decoder.log](../logs/verification/20261108_191422_831668_02_decoder.log) |
| 02_models | PASS | 5.377 s | [20261108_191605_037727_02_models.log](../logs/verification/20261108_191605_037727_02_models.log) |
| 03_lab_scripts | PASS | 0.635 s | [20261108_191757_149915_03_lab_scripts.log](../logs/verification/20261108_191757_149915_03_lab_scripts.log) |
| 04_farm_integration | PASS | 0.518 s | [20261108_192004_842008_04_farm_integration.log](../logs/verification/20261108_192004_842008_04_farm_integration.log) |
| 05_dataset_config | PASS | 0.69 s | [20261108_192244_712592_05_dataset_config.log](../logs/verification/20261108_192244_712592_05_dataset_config.log) |
| 03_ui_widgets | FAIL | 0.398 s | [20261108_192245_562875_03_ui_widgets.log](../logs/verification/20261108_192245_562875_03_ui_widgets.log) |
| 05_dataset_readiness | FAIL | 0.191 s | [20261108_192246_310394_05_dataset_readiness.log](../logs/verification/20261108_192246_310394_05_dataset_readiness.log) |
| 03_ui_widgets_user | PASS | 1.576 s | [20261108_193258_662616_03_ui_widgets_user.log](../logs/verification/20261108_193258_662616_03_ui_widgets_user.log) |
| 06_full_regression | PASS | 0.924 s | [20261108_193305_191871_06_full_regression.log](../logs/verification/20261108_193305_191871_06_full_regression.log) |
| 06_replay | PASS | 3.292 s | [20261108_193851_184205_06_replay.log](../logs/verification/20261108_193851_184205_06_replay.log) |
| 06_selftest | PASS | 9.822 s | [20261108_193854_639771_06_selftest.log](../logs/verification/20261108_193854_639771_06_selftest.log) |
| 07_final_regression | PASS | 1.099 s | [20261108_194020_170763_07_final_regression.log](../logs/verification/20261108_194020_170763_07_final_regression.log) |
| 07_compile | PASS | 0.207 s | [20261108_194021_461901_07_compile.log](../logs/verification/20261108_194021_461901_07_compile.log) |
