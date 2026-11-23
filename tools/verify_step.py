"""Run a verification command and retain its output, duration and exit status."""
import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.step):
        parser.error("Step must contain only letters, digits, underscores or hyphens")
    root = Path(__file__).resolve().parents[1]
    command = args.command or [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    if command[0] == "python":
        command[0] = sys.executable
    now = datetime.now(timezone(timedelta(hours=7)))
    folder = root / "logs/verification"
    folder.mkdir(parents=True, exist_ok=True)
    stem = folder / f"{now:%Y%m%d_%H%M%S_%f}_{args.step}"
    started = time.perf_counter()
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        code, output = result.returncode, result.stdout + result.stderr
    except OSError as exc:
        code, output = 1, str(exc)
    record = {"step": args.step, "started": now.isoformat(), "command": command,
              "duration_seconds": round(time.perf_counter() - started, 3),
              "exit_code": code, "status": "PASS" if code == 0 else "FAIL",
              "log": str(stem.with_suffix(".log"))}
    stem.with_suffix(".log").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n\n" + output,
                                        encoding="utf-8")
    stem.with_suffix(".json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    print(f"{record['status']}: {stem.with_suffix('.log')}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
