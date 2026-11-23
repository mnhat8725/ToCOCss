from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock
import json
import numpy as np

from cocbot.game.execution import execute_plan
from cocbot.vision.onnx_engine import Result, export_result
from cocbot.game.strategy import build_preview_plan, capital_deploy_point
from cocbot.ui.vision_lab import LatestJob


def result(detections=None, model="smart_farm", masks=None):
    return Result(model, "synthetic", np.zeros((100, 200, 3), np.uint8), detections or [], masks or [], {}, 1, 2, [])


class LabStrategyTests(unittest.TestCase):
    def test_preview_excludes_candidates_and_never_taps(self):
        candidate = dict(class_name="gold_storage_full", class_id=1, confidence=.9, box_xyxy=[10, 20, 40, 60], candidate_only=True)
        self.assertEqual(build_preview_plan(result([candidate]))["status"], "no_targets")
        plan = build_preview_plan(result([dict(candidate, candidate_only=False)]))
        controller = Mock()
        events = execute_plan(plan, (200, 100), threading.Event(), controller=controller)
        self.assertTrue(events)
        controller.click.assert_not_called()
        with self.assertRaisesRegex(ValueError, "Preview"):
            execute_plan(plan, (200, 100), threading.Event(), controller=controller, dry_run=False)

    def test_invalid_late_action_causes_no_partial_execution(self):
        plan = {"schema_version": 1, "coordinate_space": "normalized_device", "dry_run_only": False,
                "actions": [{"type": "drop_troop", "point": [.1, .2]}, {"type": "drop_spell", "point": [float('nan'), .2]}]}
        controller = Mock()
        with self.assertRaises(ValueError):
            execute_plan(plan, (200, 100), threading.Event(), controller=controller, dry_run=False)
        controller.click.assert_not_called()

    def test_cancellation_stops_between_taps(self):
        stop = threading.Event()
        controller = Mock()
        controller.click.side_effect = lambda *args: stop.set()
        plan = {"schema_version": 1, "coordinate_space": "normalized_device", "dry_run_only": False,
                "actions": [{"type": "drop_troop", "point": [.1, .2], "count": 5}]}
        with self.assertRaisesRegex(RuntimeError, "Bot stopped"):
            execute_plan(plan, (200, 100), stop, controller=controller, dry_run=False)
        self.assertEqual(controller.click.call_count, 1)

    def test_mask_point_is_inside_mask_and_capital_only(self):
        mask = np.zeros((100, 200), bool)
        mask[20:70, 30:100] = True
        detected = result(model="deploy_zone", masks=[(0, 0, 0, mask)])
        point = capital_deploy_point(detected, "clan_capital")["point"]
        self.assertTrue(mask[round(point[1] * 100), round(point[0] * 200)])
        with self.assertRaises(ValueError):
            capital_deploy_point(detected, "main_village")

    def test_export_preserves_full_mask_and_selected_display(self):
        with tempfile.TemporaryDirectory() as folder:
            detected = result(model="deploy_zone", masks=[(0, 20, 30, np.ones((10, 15), bool))])
            export_result(folder, detected, show_boxes=False)
            metadata = json.loads((Path(folder) / "result.json").read_text(encoding="utf-8"))
            self.assertFalse(metadata["display"]["show_boxes"])
            import cv2
            mask = cv2.imread(str(Path(folder) / "mask_1.png"), cv2.IMREAD_GRAYSCALE)
            self.assertEqual(mask.shape, (100, 200))
            self.assertEqual(int((mask > 0).sum()), 150)

    def test_closed_worker_discards_result(self):
        gate = threading.Event()
        job = LatestJob()
        self.assertTrue(job.submit(lambda: (gate.wait(2), "result")))
        self.assertFalse(job.submit(lambda: "second"))
        job.close()
        gate.set()
        deadline = time.monotonic() + 3
        while job.queue.empty() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertIsNone(job.receive())
