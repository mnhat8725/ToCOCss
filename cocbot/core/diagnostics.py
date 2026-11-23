"""Per-session structured events and screenshots for reproducible failures."""
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid

import cv2

from cocbot.core.paths import user_path


class SessionRecorder:
    def __init__(self, directory=None):
        self.directory = Path(directory or user_path("logs/sessions")) / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8])
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(self, event, frame=None, **data):
        with self._lock:
            record = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **data}
            if frame is not None:
                name = f"{uuid.uuid4().hex}.png"
                ok, encoded = cv2.imencode(".png", frame)
                if not ok:
                    raise ValueError("Cannot encode diagnostic screenshot")
                encoded.tofile(str(self.directory / name))
                record["screenshot"] = name
            with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        return record
