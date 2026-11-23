import hashlib
import io
from pathlib import Path
import queue
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error
import zipfile

from cocbot.device.adb import EmulatorAdb
from cocbot.game.bot import CocBot
from cocbot.core.config import AppConfig
from cocbot.ui.gui import BotGUI
from cocbot.vision.ocr_models import prepare_models


class BotTests(unittest.TestCase):
    def make_bot(self, **kwargs):
        return CocBot(AppConfig(), Mock(), Mock(), Mock(), queue.Queue(), **kwargs)

    def test_goals_ignore_disabled_resources_and_accept_exact_total(self):
        totals = {"gold": 100, "elixir": 100, "delixir": 0}
        self.assertTrue(CocBot.goals_reached(totals, (100, 100, 0)))
        self.assertFalse(CocBot.goals_reached(totals, (101, 100, 0)))
        self.assertFalse(CocBot.goals_reached(totals, (0, 0, 0)))

    def test_missing_calibration_reports_terminal_state(self):
        bot = self.make_bot()
        self.assertFalse(bot.start((0, 0, 0), (1, 1, 0)))
        messages = list(bot.msg_queue.queue)
        self.assertIn({"type": "status", "state": "error"}, messages)
        self.assertFalse(bot.is_running())

    def test_invalid_coordinates_rejected(self):
        for point in ({"x": -1, "y": 0}, {"x": "0.5", "y": 0},
                      {"x": float("nan"), "y": 0}, None):
            self.assertFalse(CocBot._valid_control(point))

    def test_stop_prevents_next_tap(self):
        bot = self.make_bot()
        bot._stop_event.set()
        with self.assertRaisesRegex(RuntimeError, "Bot stopped"):
            bot._press_button("surr")
        bot.auto.click.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "Bot stopped"):
            bot._sleep(0)

    def test_loading_failure_is_not_overwritten_with_stopped(self):
        bot = self.make_bot()
        bot.vision.load.side_effect = RuntimeError("missing weights")
        bot._farm_loop((0, 0, 0), (1, 1, 0))
        states = [m["state"] for m in bot.msg_queue.queue if m["type"] == "status"]
        self.assertEqual(states[-1], "error")
        bot.auto.click.assert_not_called()

    def test_stop_interrupts_sweep_before_second_tap(self):
        bot = self.make_bot()
        bot.window.win_left = 0
        bot.window.win_width = 1000
        bot.auto.click.side_effect = lambda *args: bot._stop_event.set()
        with self.assertRaisesRegex(RuntimeError, "Bot stopped"):
            bot._sweep_rows([200, 300])
        self.assertEqual(bot.auto.click.call_count, 1)


class AdbTests(unittest.TestCase):
    def test_device_timeout_returns_false(self):
        adb = EmulatorAdb(adb_path="adb.exe")
        with patch.object(adb, "_run", return_value=None):
            self.assertFalse(adb._is_device(adb.serial))

    def test_launch_failure_is_reported(self):
        adb = EmulatorAdb(adb_path="missing.exe")
        with patch("cocbot.device.adb.subprocess.run", side_effect=FileNotFoundError("missing")):
            self.assertIsNone(adb._run(["devices"]))
        self.assertIn("could not run adb", adb.last_error)

    def test_override_resolution_wins(self):
        adb = EmulatorAdb(adb_path="adb.exe")
        result = subprocess.CompletedProcess([], 0, b"Physical size: 1080x1920\nOverride size: 900x1600\n")
        with patch.object(adb, "_run", return_value=result):
            self.assertEqual(adb.resolution(), (900, 1600))


class GuiTests(unittest.TestCase):
    def make_gui(self, value="1"):
        gui = BotGUI.__new__(BotGUI)
        for field in ("min_gold", "min_elixir", "min_dark", "goal_gold", "goal_elixir", "goal_dark"):
            setattr(gui, field, Mock(get=Mock(return_value=value)))
        gui.bot = Mock()
        gui.start_btn = Mock()
        gui.stop_btn = Mock()
        gui.status_var = Mock()
        return gui

    def test_decimal_input_is_rejected_without_starting(self):
        gui = self.make_gui("1.5")
        with patch("cocbot.ui.gui.messagebox.showerror") as alert:
            gui._on_start()
            alert.assert_called_once()
        gui.bot.start.assert_not_called()

    def test_rejected_start_restores_buttons(self):
        gui = self.make_gui()
        gui.bot.start.return_value = False
        gui._on_start()
        gui.start_btn.config.assert_called_with(state="normal")
        gui.stop_btn.config.assert_called_with(state="disabled")


class ModelSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.weights = b"valid-test-weights"
        self.spec = {"filename": "test.pth", "url": "https://example.invalid/model.zip",
                     "md5sum": hashlib.md5(self.weights).hexdigest()}
        for name, value in (("model_directory", self.directory), ("required_models", [self.spec])):
            patcher = patch(f"cocbot.vision.ocr_models.{name}", return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def archive(self, content):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("test.pth", content)
        return io.BytesIO(stream.getvalue())

    def test_missing_weights_do_not_trigger_network_during_farming(self):
        with patch("cocbot.vision.ocr_models.urllib.request.urlopen") as request:
            with self.assertRaisesRegex(RuntimeError, "prepare_models.py"):
                prepare_models()
            request.assert_not_called()

    def test_gateway_retry_then_offline_cache(self):
        error = urllib.error.HTTPError(self.spec["url"], 502, "Bad Gateway", {}, None)
        with patch("cocbot.vision.ocr_models.urllib.request.urlopen", side_effect=[error, self.archive(self.weights)]) as request, \
                patch("cocbot.vision.ocr_models.time.sleep"):
            prepare_models(download=True)
            self.assertEqual(request.call_count, 2)
        with patch("cocbot.vision.ocr_models.urllib.request.urlopen") as request:
            prepare_models()
            request.assert_not_called()
        self.assertEqual((self.directory / "test.pth").read_bytes(), self.weights)

    def test_corrupt_download_does_not_replace_existing_file(self):
        target = self.directory / "test.pth"
        target.write_bytes(b"old-invalid-file")
        with patch("cocbot.vision.ocr_models.urllib.request.urlopen", return_value=self.archive(b"corrupt")):
            with self.assertRaisesRegex(RuntimeError, "Checksum mismatch"):
                prepare_models(download=True, attempts=1)
        self.assertEqual(target.read_bytes(), b"old-invalid-file")


if __name__ == "__main__":
    unittest.main()
