"""
Entry point: composes all modules and starts the Tkinter GUI.
"""

print("COC Auto-Farm: starting...", flush=True)

import logging
import os
import queue
import sys
import tkinter as tk
from tkinter import messagebox, ttk

import keyboard

from cocbot.core.config import AppConfig, apply_settings
from cocbot.device.adb import EmulatorAdb
from cocbot.core.logger import setup_logging
from cocbot.device.window_manager import WindowManager
from cocbot.core.settings import load_settings
from cocbot.vision.manager import VisionManager
from cocbot.device.automation import AutomationController
from cocbot.game.bot import CocBot
from cocbot.ui.gui import BotGUI
from cocbot.core.notify import Notifier
from cocbot.core.paths import configure_runtime_env, resource_path
from cocbot.vision.state_detection import ScreenDetector
from cocbot.core.diagnostics import SessionRecorder

logger = logging.getLogger(__name__)

# Kept so the top-level crash handler can reuse the existing root window
# instead of creating a second one.
_root = None


def _selftest():
    """
    Import every heavy dependency and report what is available.

    Run with ``CocAutoFarm.exe --selftest`` to verify a build on a machine
    without an emulator attached. Exits with 0 when everything imported.
    """
    configure_runtime_env()

    checks = [
        ("cv2", "cv2"),
        ("numpy", "numpy"),
        ("PIL", "PIL"),
        ("keyboard", "keyboard"),
        ("torch", "torch"),
        ("torchvision", "torchvision"),
        ("ultralytics", "ultralytics"),
        ("easyocr", "easyocr"),
        ("onnxruntime", "onnxruntime"),
    ]
    failures = []
    for label, module in checks:
        try:
            mod = __import__(module)
            version = getattr(mod, "__version__", "?")
            print(f"  OK   {label:<12} {version}")
        except Exception as e:
            failures.append(f"{label}: {type(e).__name__}: {e}")
            print(f"  FAIL {label:<12} {type(e).__name__}: {e}")

    try:
        from ultralytics import YOLO
        from cocbot.core.config import AppConfig
        from cocbot.core.paths import resource_path

        model = resource_path(AppConfig().model_path)
        if not os.path.exists(model):
            failures.append(f"YOLO model missing: {model}")
            print(f"  FAIL yolo model   not found: {model}")
        else:
            YOLO(model)
            print(f"  OK   yolo model   {model}")
    except Exception as e:
        failures.append(f"ultralytics/YOLO: {type(e).__name__}: {e}")
        print(f"  FAIL yolo model   {type(e).__name__}: {e}")

    try:
        from cocbot.vision.manager import VisionManager

        config = AppConfig()
        config.model_path = resource_path(config.model_path)
        VisionManager(config).load()
        print("  OK   OCR reader   weights verified and loaded offline")
        import numpy as np
        from cocbot.vision.onnx_engine import Engine
        for name in ("smart_farm", "spell_target", "deploy_zone"):
            result = Engine().infer(np.zeros((64, 64, 3), dtype=np.uint8), "selftest", name)
            print(f"  OK   ONNX {name}: {result.output_shapes}")
    except Exception as e:
        failures.append(f"OCR reader: {type(e).__name__}: {e}")
        print(f"  FAIL OCR reader   {type(e).__name__}: {e}")

    print()
    if failures:
        print(f"SELFTEST FAILED ({len(failures)} problem(s)):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELFTEST PASSED")
    return 0


def _show_splash(root, message):
    """Small 'starting' window shown while the ADB connection is attempted."""
    win = tk.Toplevel(root)
    win.title("COC Auto-Farm")
    win.resizable(False, False)
    win.transient(root)

    frame = ttk.Frame(win, padding=20)
    frame.pack()
    ttk.Label(frame, text="COC Auto-Farm", font=("Segoe UI", 12, "bold")).pack(
        pady=(0, 10)
    )
    label = ttk.Label(frame, text=message)
    label.pack()

    win.protocol("WM_DELETE_WINDOW", win.destroy)
    win.update_idletasks()
    return win, label


def main():
    setup_logging()
    logger.info("COC Auto-Farm starting")

    configure_runtime_env()

    config = AppConfig()

    # The YOLO model ships inside the bundle (read-only); from source it is
    # next to the project files.
    model_full_path = resource_path(config.model_path)
    if os.path.exists(model_full_path):
        config.model_path = model_full_path

    settings = load_settings(strict=True)
    apply_settings(config, settings)
    notifier = Notifier(settings.get("notifications"))

    # Root is kept hidden until the emulator is reachable; error dialogs
    # (and the GUI) still work while it is withdrawn.
    root = tk.Tk()
    root.withdraw()
    global _root
    _root = root

    splash, splash_label = _show_splash(root, "Starting...")

    def step(text):
        splash_label.config(text=text)
        splash.update()

    adb = EmulatorAdb(
        host=config.adb_host, port=config.adb_port, adb_path=config.adb_path
    )
    step("Connecting to the emulator over ADB...")
    splash.update()
    if not adb.connect():
        logger.error(f"ADB connect failed: {adb.last_error}")
        # Process is about to exit, so send synchronously (text only: ADB is down).
        notifier.notify(
            "COC Auto-Farm: ADB error",
            "Could not connect to the emulator via ADB. "
            f"Details: {adb.last_error}",
            blocking=True,
            priority="high",
            tags="warning",
        )
        splash.destroy()
        messagebox.showerror(
            "ADB Error",
            "Could not connect to the emulator via ADB.\n\n"
            "Start the emulator and enable 'ADB local connection' in LDPlayer "
            "settings (Settings > Others).\n"
            "Expected device: 127.0.0.1:5555 (first instance).\n\n"
            f"Details: {adb.last_error}",
        )
        sys.exit(1)

    step("Loading components...")
    splash.update()

    window = WindowManager(adb=adb)
    vision = VisionManager(config)
    automation = AutomationController(adb=adb)
    controls = settings.get("controls") or {}
    waits = settings.get("waits") or {}
    recovery = settings.get("recovery") or {}
    attack = settings.get("attack") or {}

    msg_queue = queue.Queue()
    recorder = SessionRecorder()
    detector = ScreenDetector(threshold=config.template_threshold) if config.state_guard_enabled else None
    bot = CocBot(config, window, vision, automation, msg_queue, controls=controls, waits=waits,
                 notifier=notifier, recovery=recovery, attack=attack, screen_detector=detector, recorder=recorder)

    splash.destroy()
    app = BotGUI(root, bot, msg_queue, settings=settings)
    root.deiconify()

    # Emergency keyboard stop
    try:
        keyboard.add_hotkey("f12", bot.stop)
    except Exception as e:
        logger.warning(f"Could not register F12 hotkey: {e}")

    root.mainloop()


if __name__ == "__main__":
    if "--vision-lab" in sys.argv:
        from cocbot.ui.vision_lab import main as lab_main
        lab_main()
        sys.exit(0)
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback

        detail = traceback.format_exc()
        logger.critical("Fatal error:\n%s", detail)
        try:
            if _root is None:
                _root = tk.Tk()
                _root.withdraw()
            messagebox.showerror(
                "COC Auto-Farm crashed",
                "An unexpected error occurred.\n\n"
                f"{detail[-1500:]}\n\n"
                "The full traceback was written to the log file.",
            )
        except Exception:
            pass
        sys.exit(1)
