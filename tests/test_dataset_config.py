import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from cocbot.core.config import AppConfig, apply_settings
from cocbot.core import settings
from tools.dataset_tool import NAMES, validate_dataset, export_dataset


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        records = []
        for index, split in enumerate(("train", "val", "test")):
            image = self.root / f"images/{split}/frame.png"
            label = self.root / f"labels/{split}/frame.txt"
            image.parent.mkdir(parents=True)
            label.parent.mkdir(parents=True)
            pixels = np.random.default_rng(index).integers(0, 255, (32, 32, 3), dtype=np.uint8)
            Image.fromarray(pixels).save(image)
            label.write_text("1 0.5 0.5 0.2 0.3\n")
            records.append({"image": image.relative_to(self.root).as_posix(),
                            "label": label.relative_to(self.root).as_posix(), "split": split,
                            "group": f"raid_{index}", "reviewed": True})
        self.data = {"schema_version": 1, "names": NAMES, "records": records}
        self.manifest = self.root / "manifest.json"
        self.write()

    def write(self):
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")

    def test_reviewed_dataset_exports_without_training(self):
        path, report = export_dataset(self.manifest)
        self.assertTrue(path.is_file())
        self.assertEqual(report["images"], {"train": 1, "val": 1, "test": 1})
        self.assertFalse(report["accuracy_measured"])

    def test_same_raid_cannot_leak_across_splits(self):
        self.data["records"][1]["group"] = "raid_0"
        self.write()
        with self.assertRaisesRegex(ValueError, "leakage"):
            validate_dataset(self.manifest)

    def test_duplicate_pixels_detected_despite_different_filename(self):
        Image.open(self.root / "images/train/frame.png").save(self.root / "images/test/frame.png")
        with self.assertRaisesRegex(ValueError, "Duplicate image pixels"):
            validate_dataset(self.manifest)

    def test_candidates_are_not_reviewed_ground_truth(self):
        self.data["records"][0]["reviewed"] = False
        self.write()
        with self.assertRaisesRegex(ValueError, "reviewed=true"):
            validate_dataset(self.manifest)

    def test_invalid_box_and_missing_labels_are_rejected(self):
        (self.root / "labels/train/frame.txt").write_text("1 0.95 0.5 0.5 0.2")
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_dataset(self.manifest)


class ConfigTests(unittest.TestCase):
    def test_bad_settings_leave_previous_file_intact(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(settings, "SETTINGS_PATH", str(Path(folder) / "settings.json")):
            self.assertTrue(settings.save_settings({"controls": {"x": 1}}))
            before = Path(settings.SETTINGS_PATH).read_bytes()
            with self.assertLogs("cocbot.core.settings", level="ERROR"):
                self.assertFalse(settings.save_settings({"bad": float("nan")}))
            self.assertEqual(Path(settings.SETTINGS_PATH).read_bytes(), before)

    def test_corrupt_settings_are_explicit_in_strict_mode(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(settings, "SETTINGS_PATH", str(Path(folder) / "settings.json")):
            Path(settings.SETTINGS_PATH).write_text("{")
            with self.assertLogs("cocbot.core.settings", level="ERROR"), self.assertRaises(ValueError):
                settings.load_settings(strict=True)

    def test_configuration_ranges_and_schema(self):
        for data in ({"schema_version": 99}, {"vision": {"state_timeout": float("nan")}},
                     {"vision": {"smart_farm_iou": 0}}, {"vision": {"layout_backend": "bad"}}):
            with self.assertRaises(ValueError):
                apply_settings(AppConfig(), data)
        self.assertEqual(apply_settings(AppConfig(), {"vision": {"layout_backend": "legacy"}}).layout_backend, "legacy")

    def test_invalid_control_wait_and_attack_are_rejected_before_running(self):
        for data in ({"controls": []}, {"controls": {"attack": {"x": 2, "y": .5}}},
                     {"waits": {"scan": float("inf")}}, {"attack": {"max_waves": 0}},
                     {"attack": {"time_limit": -1}}, {"recovery": {"scan_restart_limit": True}}):
            with self.assertRaises(ValueError):
                apply_settings(AppConfig(), data)
