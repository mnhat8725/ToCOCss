import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import numpy as np

from cocbot.game.bot import CocBot, TreasureScanFailed
from cocbot.core.config import AppConfig
from cocbot.core.diagnostics import SessionRecorder
from cocbot.vision.state_detection import Observation, ScreenState, StateTimeout
from cocbot.vision.manager import NumberReading, VisionManager


class FarmPipelineTests(unittest.TestCase):
    def make_bot(self):
        bot = CocBot(AppConfig(), Mock(), Mock(), Mock(), queue.Queue())
        bot._sleep = Mock()
        return bot

    def test_unknown_screen_never_taps(self):
        bot = self.make_bot()
        bot.guard = Mock()
        bot.guard.wait_for.side_effect = StateTimeout("unknown")
        with self.assertRaises(StateTimeout):
            bot._navigate_to_preview()
        bot.auto.click.assert_not_called()

    def test_already_in_preview_does_not_reopen_attack_menu(self):
        bot = self.make_bot()
        bot.guard = Mock()
        bot.guard.wait_for.return_value = Observation(ScreenState.PREVIEW, [], (1600, 900))
        bot._navigate_to_preview()
        bot.auto.click.assert_not_called()

    def test_missing_required_ocr_is_not_zero_and_requires_stability(self):
        bot = self.make_bot()
        frame = np.zeros((100, 100, 3), np.uint8)
        bot.window.capture_window.return_value = frame
        bot.vision.detect_with_details.return_value = {"gold": [{"bbox": [0, 0, 10, 10]}]}
        bot.vision.read_number_result.return_value = NumberReading(0, "0", .9)
        with self.assertRaises(TreasureScanFailed):
            bot._scan_treasures()
        bot.required_resources = {"gold"}
        self.assertEqual(bot._scan_treasures(), {"gold": "0"})

    def test_low_confidence_ocr_is_unreadable_but_real_zero_is_valid(self):
        vision = VisionManager(AppConfig())
        vision.reader = Mock()
        frame = np.zeros((100, 100, 3), np.uint8)
        vision.reader.readtext.return_value = [([], "12345", .1)]
        self.assertIsNone(vision.read_number_result(frame, (0, 0, 100, 100)).value)
        vision.reader.readtext.return_value = [([], "0", .99)]
        self.assertEqual(vision.read_number_result(frame, (0, 0, 100, 100)).value, 0)

    def test_full_resource_labels_keep_semantics_and_exclude_candidates(self):
        vision = VisionManager(AppConfig())
        vision.layout_engine = Mock()
        vision.layout_engine.infer.return_value.detections = [
            {"class_name": "gold_mine_full", "box_xyxy": [10, 20, 30, 40]},
            {"class_name": "de_storage_full", "box_xyxy": [30, 30, 50, 50], "candidate_only": True}]
        result = vision.detect_layout(np.zeros((100, 100, 3), np.uint8))
        self.assertEqual(result, {"golds": [(20, 30)]})

    def test_one_complete_raid_in_replay_with_exact_goal(self):
        bot = self.make_bot()
        bot.guard = Mock()
        bot.guard.wait_for.side_effect = [Observation(state, [], (1600, 900)) for state in
                                        [ScreenState.PREVIEW, ScreenState.PREVIEW, ScreenState.PREVIEW,
                                         ScreenState.RESULTS, ScreenState.RESULTS, ScreenState.HOME]]
        bot.controls = {"return_home": {"x": .5, "y": .9}}
        bot.window.win_width, bot.window.win_height = 1600, 900
        bot._scan_base_layout = Mock(return_value={"golds": [(100, 100)]})
        bot._scan_treasures = Mock(return_value={"gold": "100", "elixir": "200", "d_elixir": "0"})
        bot._initiate_attack = Mock(return_value=None)
        bot._scan_post_game = Mock(return_value={"post_gold": "100", "post_elixir": "200", "post_d_elixir": "0"})
        with tempfile.TemporaryDirectory() as folder:
            bot.recorder = SessionRecorder(folder)
            bot._farm_loop((100, 200, 0), (100, 200, 0))
            bot._initiate_attack.assert_called_once()
            # Result screen was already visible: only Return Home is tapped.
            bot.auto.click.assert_called_once_with(800, 810)
            totals = [m["data"] for m in bot.msg_queue.queue if m["type"] == "totals"]
            self.assertEqual(totals[-1], {"gold": 100, "elixir": 200, "delixir": 0})

    def test_post_loot_ignores_single_high_outlier(self):
        bot = self.make_bot()
        bot.waits["scan_post_timeout"] = 10
        bot.vision.detect_with_details.return_value = {
            "post_gold": [{"bbox": (0, 0, 10, 10)}],
            "post_elixir": [{"bbox": (20, 0, 30, 10)}],
            "post_d_elixir": [{"bbox": (40, 0, 50, 10)}]}
        values = [9999999, 200, 0, 100, 200, 0, 100, 200, 0]
        bot.vision.read_number_result.side_effect = [NumberReading(v, str(v), .9) for v in values]
        self.assertEqual(bot._scan_post_game(), {"post_gold": "100", "post_elixir": "200", "post_d_elixir": "0"})
