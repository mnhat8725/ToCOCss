# COC Auto Farm Bot

> **Note:** the `templates/` folder (UI template images and the ONNX models
> `smart_farm`, `spell_target`, `deploy_zone`) is not included in this
> repository. Place it locally at `templates/` before running the bot.

## Vision and verification upgrade

See [Vietnamese upgrade guide](progress/UPGRADE_GUIDE_VI.md) and
[project progress](progress/PROGRESS.md) for the current behavior.
The new default uses Smart Farm ONNX for full-resource buildings, template
screen guards, and bounded goblin waves. Detection loss no longer estimates loot.

Open the image inspector without an emulator:

```powershell
.venv\Scripts\python.exe main.py --vision-lab
```

Run all regression tests with persistent logs:

```powershell
.venv\Scripts\python.exe tools\verify_step.py regression
```

Each step retains a log and JSON result under `logs/verification/`. Per-session
screen evidence is stored in `logs/sessions/`. Training requires reviewed labels;
the dataset tooling rejects missing labels and cross-split duplicates.

A **thread-safe** automation bot for Clash of Clans farming on LDPlayer. It screenshots the emulator through **ADB** (works while the window is minimized / in the background), taps fixed buttons from **calibrated coordinates** (no YOLO retraining after game updates), and uses YOLO + EasyOCR only for content that moves per base — layout, resource values, and post-battle loot.

## Features

- **Background farming**: input + capture go through ADB, so the emulator window does not need focus or visibility
- **Button calibration**: click the 11 fixed buttons once on a screenshot (`python tools/calibrate.py`); positions are stored as normalized coordinates and scaled to any resolution
- **No retraining**: after a game update that moves buttons, just recalibrate (click the buttons again) instead of retraining YOLO
- **YOLO + OCR for dynamic content**: base layout, Gold/Elixir/Dark Elixir values, post-battle loot are still detected per base
- **Thread-safe GUI**: Tkinter interface communicates with the bot worker via a `queue` (no main-thread crashes)
- **Graceful stop**: press **F12** to stop farming cleanly at any time
- **Verified recovery**: bounded scan retries; skip an opponent only after verifying the preview screen. Unknown states stop with diagnostic evidence.
- **Fast start**: YOLO/OCR models load when you press Start, so the first raid has no cold-start stall
- **Logging**: file + console logs to `logs/bot.log`; every tap is logged (button name, pixel + normalized coords), with per-sweep-tap detail in the file and per-row sweep summaries in the GUI log
- **Error notifications (optional)**: push errors and completed sessions to your phone via [ntfy.sh](https://ntfy.sh), with an emulator screenshot attached

## Requirements

### Software
- **Windows** (any emulator reachable over ADB)
- **Python 3.10+** (`gpu: bool | None` type syntax requires it)
- **LDPlayer** (or any emulator reachable over ADB) with **Settings → Others → ADB local connection** enabled
- **ADB binary**: auto-detected — LDPlayer ships one (`C:\LDPlayer\LDPlayer9\adb.exe`), or Android `platform-tools` on `PATH`
- **NVIDIA GPU** (recommended for YOLO inference; CPU mode supported)

### Python Dependencies
See `requirements.txt`:
- `ultralytics` (YOLO)
- `easyocr` (OCR)
- `opencv-python`, `numpy` (image processing)
- `Pillow` (calibration screenshot previewer)
- `keyboard` (F12 hotkey)

## Installation

```bash
git clone https://github.com/anugrhaswi/Coc-Auto-Farm.git
cd Coc-Auto-Farm
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Place your trained `best.pt` at `models/best.pt` (the default in `config.py`), or point `config.model_path` elsewhere.

Prepare the two EasyOCR weights once while internet is available:

```powershell
.venv\Scripts\python.exe tools\1.py
.venv\Scripts\python.exe main.py --selftest
```

Setup reuses valid files from `~/.EasyOCR/model`, verifies model checksums, and
retries failed downloads. The bot loads OCR weights offline. `run.bat` runs the
setup automatically before opening the GUI. See the HTTP 502/504 section in
[Troubleshooting](docs/TROUBLESHOOTING.md) for manual setup.

## Usage

### 1. Calibrate the buttons (required once)

Make sure LDPlayer is running and on your main village, then:

```bash
python tools/calibrate.py
```

Click the 11 buttons in the order shown, then **Save**. This writes a `controls` section into `settings.json`. Use the **Recapture** button to grab a fresh screenshot whenever you navigate the game to another button's screen (no need to restart the tool). Recalibrate after a game update that moves buttons.

### 2. Run the bot

Easiest: double-click `run.bat` — on first run it creates `.venv` and installs
dependencies (with a prompt), then launches the GUI.
Or manually:

```bash
.venv\Scripts\Activate.ps1   # PowerShell (or: .venv\Scripts\activate.bat in cmd)
python main.py
```

The GUI lets you set **thresholds** (minimum resources to attack), **goals** (total resources before stopping), Start/Stop, and a live log. **F12** stops the farm.

A goal of **0 disables that resource goal**. The bot stops when all positive
goals have been reached (including exact totals). With all goals at 0 it keeps
running until stopped. Thresholds and goals must be non-negative whole numbers.

### Selecting the emulator

There is no window picking. The emulator is identified purely by its **ADB port** — the default `127.0.0.1:5555` targets the first LDPlayer instance (mono/multi, single box). For another instance set `adb_port` in `config.py` (5557, 5559, ...). If the port can't connect at startup, the app shows an ADB error dialog and exits.

## Configuration

`cocbot/core/config.py` holds an `AppConfig` dataclass (YOLO model, `conf`, `gpu`, retries, and ADB host/port/path). End-user data lives in `settings.json` (`controls`). See [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Architecture

```
main.py                  Entry point (GUI bot, --selftest, --vision-lab)
run.bat                  First-run setup + launch
cocbot/
  core/      paths.py (source/bundle/user paths), config.py (AppConfig), settings.py (settings.json),
             logger.py, notify.py (ntfy.sh), diagnostics.py (SessionRecorder)
  device/    adb.py (EmulatorAdb), automation.py (tap/keyevent), window_manager.py (capture)
  vision/    manager.py (VisionManager: YOLO + EasyOCR), onnx_engine.py (ONNX decoder),
             ocr_models.py (OCR weights), state_detection.py (screen templates + StateGuard)
  game/      bot.py (CocBot farm loop), strategy.py (attack plans), execution.py (action runner)
  ui/        gui.py (BotGUI), vision_lab.py (image inspector)
tools/       calibrate.py, pinpoint.py, diagnose.py, prepare_models.py,
             dataset/train/verify/replay utilities
tests/       unittest suite (python -m unittest discover -s tests)
templates/   UI templates + ONNX models     models/  YOLO best.pt
progress/    roadmap, handoff and work logs
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full picture.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — module diagram, thread model, coordinate systems
- [Configuration](docs/CONFIGURATION.md) — every setting and the `settings.json` schema
- [Usage](docs/USAGE.md) — calibration, running, tips
- [Troubleshooting](docs/TROUBLESHOOTING.md) — common issues and fixes
- [Development](docs/DEVELOPMENT.md) — full API reference and extending the bot

## Known Limitations

- **ADB only**: all screen data and taps go through ADB (`screencap` + `input tap`); there is no desktop screenshot/click mode
- **ADB required for farming**: the fixed buttons are calibrated guest-screen coordinates with no YOLO fallback, so the bot needs the ADB connection alive
- **Single emulator instance**: defaults to `127.0.0.1:5555` (first LDPlayer instance). Set `adb_port` for another instance.
- **Single strategy**: goblin-based farming; other strategies not yet implemented
- **YOLO model required** for layout/treasure/loot detection

## Journey

This bot is the result of iterative learning:

1. **Window Management**: failed with `pygetwindow`, succeeded with `pywinauto` + focus fallback trick
2. **OCR Reliability**: safe defaults to handle empty OCR results
3. **Detection Retries**: max-4-attempt loop for async game loading
4. **Threading**: fixed `RuntimeError` by replacing `root.after()` with queue-based messaging
5. **Architecture**: modularized globals into focused classes
6. **Background mode**: replaced desktop mouse/keyboard with ADB `screencap` + `input tap`
7. **Buttons without YOLO**: calibrated normalized coordinates, so game updates no longer force model retraining
8. **ADB-only**: removed the desktop capture/click fallback (`pyautogui`) and the window picker (`pywinauto`) — the emulator is chosen by ADB port

## License

MIT License — See `LICENSE` file.

## Author

**Anugrha Bhujel** ([GitHub](https://github.com/anugrhaswi), [LinkedIn](https://www.linkedin.com/in/anugrhaswi/))
