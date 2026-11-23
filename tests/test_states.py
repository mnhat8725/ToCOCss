import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

import cv2
import numpy as np

from cocbot.core.diagnostics import SessionRecorder
from cocbot.vision.state_detection import Marker, Observation, ScreenDetector, ScreenState, StateGuard, StateTimeout


class StateTests(unittest.TestCase):
    def test_template_maps_roi_coordinates_and_blank_is_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            tile = np.random.default_rng(2).integers(0, 255, (20, 40, 3), dtype=np.uint8)
            cv2.imwrite(str(Path(folder) / "button.png"), tile)
            detector = ScreenDetector(folder, .95, (1,), [Marker("button.png", ScreenState.HOME, (.5, .5, 1, 1))])
            frame = np.zeros((200, 300, 3), np.uint8)
            self.assertEqual(detector.detect(frame).state, ScreenState.UNKNOWN)
            frame[130:150, 180:220] = tile
            result = detector.detect(frame)
            self.assertEqual(result.state, ScreenState.HOME)
            self.assertEqual(result.evidence[0]["box_xyxy"], [180, 130, 220, 150])

    def test_guard_requires_consecutive_same_state(self):
        detector = Mock()
        detector.detect.side_effect = [Observation(s, [], (100, 100)) for s in
                                      [ScreenState.HOME, ScreenState.UNKNOWN, ScreenState.HOME, ScreenState.HOME]]
        guard = StateGuard(Mock(), detector, threading.Event(), poll=0)
        self.assertEqual(guard.wait_for([ScreenState.HOME]).state, ScreenState.HOME)
        self.assertEqual(detector.detect.call_count, 4)

    def test_unknown_timeout_saves_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder = SessionRecorder(folder)
            detector = Mock()
            detector.detect.return_value = Observation(ScreenState.UNKNOWN, [], (32, 32))
            guard = StateGuard(lambda: np.zeros((32, 32, 3), np.uint8), detector, threading.Event(), recorder)
            with self.assertRaises(StateTimeout):
                guard.wait_for([ScreenState.HOME], timeout=0)
            event = json.loads((recorder.directory / "events.jsonl").read_text())
            self.assertEqual(event["expected"], ["home"])
            self.assertTrue((recorder.directory / event["screenshot"]).is_file())

    def test_stop_does_not_capture_or_wait(self):
        stop = threading.Event()
        stop.set()
        capture = Mock()
        with self.assertRaisesRegex(RuntimeError, "Bot stopped"):
            StateGuard(capture, Mock(), stop).wait_for([ScreenState.HOME])
        capture.assert_not_called()
