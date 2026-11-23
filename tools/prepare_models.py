"""One-time model setup. Farming itself never needs to download OCR weights."""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # project root

import argparse
import logging

from cocbot.vision.ocr_models import prepare_models
from cocbot.core.paths import configure_runtime_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate local weights without downloading")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    configure_runtime_env()
    try:
        directory = prepare_models(download=not args.check)
    except Exception as exc:
        logging.error("%s", exc)
        return 1
    print(f"EasyOCR models ready: {directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
