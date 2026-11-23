"""Prepare verified EasyOCR weights separately from the farming session."""

import hashlib
from contextlib import contextmanager
import logging
import os
from pathlib import Path
import shutil
import tempfile
import time
import urllib.request
import uuid
import zipfile

from cocbot.core.paths import resource_path, user_path

logger = logging.getLogger(__name__)


@contextmanager
def staged_model(directory):
    # Windows gives TemporaryDirectory private ACLs. Moving a file out of that
    # directory preserves them, preventing another account from reading it.
    # Stage weights directly in the model directory to inherit its normal ACL.
    path = directory / f".{uuid.uuid4().hex}.tmp"
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def model_directory():
    module_path = os.environ.get("EASYOCR_MODULE_PATH") or os.environ.get("MODULE_PATH")
    if module_path:
        return Path(module_path).expanduser() / "model"
    bundled = Path(resource_path("easyocr_data/model"))
    if bundled.is_dir():
        return bundled
    return Path(user_path("easyocr_data/model"))


def required_models():
    # Use the URLs and checksums belonging to the installed EasyOCR version.
    from easyocr.config import detection_models, recognition_models

    return [detection_models["craft"], recognition_models["gen2"]["english_g2"]]


def valid_model(path, checksum):
    try:
        digest = hashlib.md5()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == checksum
    except OSError:
        return False


def prepare_models(download=False, attempts=3):
    """Reuse local weights; optionally download with bounded retries and atomic writes."""
    directory = model_directory()
    specs = required_models()
    directory.mkdir(parents=True, exist_ok=True)
    missing = []
    for spec in specs:
        target = directory / spec["filename"]
        if valid_model(target, spec["md5sum"]):
            continue
        # Reuse the normal EasyOCR cache and older packaged layouts offline.
        candidates = [
            Path.home() / ".EasyOCR/model" / target.name,
            Path(resource_path("assets/easyocr_data/model")) / target.name,
        ]
        for candidate in candidates:
            if candidate != target and valid_model(candidate, spec["md5sum"]):
                with staged_model(directory) as staged:
                    shutil.copyfile(candidate, staged)
                    os.replace(staged, target)
                break
        if valid_model(target, spec["md5sum"]):
            continue
        if not download:
            missing.append(f"{target.name}: {spec['url']}")
            continue
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                logger.info("Downloading %s (attempt %d/%d)", target.name, attempt, attempts)
                with tempfile.TemporaryDirectory(dir=directory) as tmp, staged_model(directory) as staged:
                    archive = Path(tmp) / "model.zip"
                    request = urllib.request.Request(spec["url"], headers={"User-Agent": "COCAutoFarm-model-setup"})
                    with urllib.request.urlopen(request, timeout=30) as response, archive.open("wb") as out:
                        shutil.copyfileobj(response, out)
                    with zipfile.ZipFile(archive) as zipped, zipped.open(target.name) as source, staged.open("wb") as out:
                        shutil.copyfileobj(source, out)
                    if not valid_model(staged, spec["md5sum"]):
                        raise ValueError(f"Checksum mismatch for {target.name}")
                    os.replace(staged, target)
                last_error = None
                break
            except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
                last_error = exc
                logger.warning("Download failed: %s", exc)
                if attempt < attempts:
                    time.sleep(attempt * 2)
        if last_error is not None:
            missing.append(f"{target.name}: {last_error}; URL: {spec['url']}")
    if missing:
        raise RuntimeError(
            "EasyOCR weights missing or invalid. Run .venv\\Scripts\\python.exe tools\\prepare_models.py"
            "before starting the bot. If GitHub returns HTTP 502/504, retry later or "
            f"download the ZIPs below and extract the .pth files into {directory}.\n"
            + "\n".join(missing)
        )
    return directory
