"""
dp_logging.py — Shared logging for the Designer Plants scraper.

Two responsibilities:

  1. init(component)   — Mirror everything printed to the console into a
                         per-execution log file (logs/run_<RUN_ID>.log) and
                         force UTF-8 console output on Windows. Returns the run id.
                         Replaces the old inline sys.stdout encoding wrapper.

  2. record_status(...) — Append a one-line structured outcome to two files:
                            logs/status.jsonl  (machine-readable, one JSON per line)
                            logs/runs.log      (human-readable summary table)

Run grouping:
  run.bat exports DP_RUN_ID before launching the per-catalog python processes,
  so login.py + every scrape_full.py + verify.py in a single full run all append
  to the same logs/run_<RUN_ID>.log. When a script is launched manually without
  DP_RUN_ID set, a fresh timestamp-based run id is generated for that process.

All scripts in this project live in the same directory, so logs/ is created
next to this module.
"""

import io
import json
import os
import pathlib
import sys
import traceback
from datetime import datetime

HERE = pathlib.Path(__file__).parent
LOG_DIR = HERE / "logs"

# Set by init(); reused by record_status() so both halves share one run id.
_RUN_ID: str | None = None


def _now() -> str:
    """Local wall-clock timestamp for human-readable log lines."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _run_id() -> str:
    """Resolve the run id: explicit (set by init) → env (set by run.bat) → fresh."""
    if _RUN_ID:
        return _RUN_ID
    return os.environ.get("DP_RUN_ID") or datetime.now().strftime("%Y%m%d_%H%M%S")


class _Tee:
    """Forward writes/flushes to several streams (console + log file)."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for stream in self._streams:
            try:
                stream.write(data)
            except Exception:
                pass  # never let logging plumbing crash the scrape
        return len(data)

    def flush(self):
        for stream in self._streams:
            try:
                stream.flush()
            except Exception:
                pass


def init(component: str) -> str:
    """
    Tee stdout/stderr to logs/run_<RUN_ID>.log and force UTF-8 on the Windows
    console. Call this once at the very top of a script, before any print().

    Returns the run id so the caller can surface it to the user.
    """
    global _RUN_ID
    LOG_DIR.mkdir(exist_ok=True)
    _RUN_ID = _run_id()
    log_path = LOG_DIR / f"run_{_RUN_ID}.log"

    # UTF-8 console (the project uses unicode arrows/dashes in print output that
    # the default Windows code page cp1252 cannot encode).
    if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
        console_out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        console_err = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    else:
        console_out, console_err = sys.stdout, sys.stderr

    # Append so every process in one run adds to the same file. Line-buffered so a
    # crash mid-catalog still leaves the log on disk.
    log_file = open(log_path, "a", encoding="utf-8", errors="replace", buffering=1)
    log_file.write(f"\n{'=' * 70}\n")
    log_file.write(f"[{_now()}] START {component}  (run {_RUN_ID})\n")
    log_file.write(f"{'=' * 70}\n")
    log_file.flush()

    sys.stdout = _Tee(console_out, log_file)
    sys.stderr = _Tee(console_err, log_file)
    return _RUN_ID


def record_status(component: str, status: str, **fields) -> None:
    """
    Append one outcome record to logs/status.jsonl (JSON) and logs/runs.log (text).

    component — "login" | "scrape_full" | "verify"
    status    — short outcome token, e.g. "ok", "failed", "session_expired",
                "passed", "failed".
    **fields  — extra context (catalog, products, skipped, failed, seconds, error).
    """
    LOG_DIR.mkdir(exist_ok=True)
    record = {
        "run_id": _run_id(),
        "ts": _now(),
        "component": component,
        "status": status,
        **fields,
    }
    try:
        with open(LOG_DIR / "status.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass

    extras = "  ".join(f"{k}={v}" for k, v in fields.items())
    line = f"[{record['ts']}] run={record['run_id']:<15} {component:<12} {status:<14} {extras}\n"
    try:
        with open(LOG_DIR / "runs.log", "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def format_exc() -> str:
    """Full traceback string for the currently handled exception."""
    return traceback.format_exc()
