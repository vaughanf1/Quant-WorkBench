"""Append-only JSONL alert persistence with pruning (tickflow pattern)."""
from __future__ import annotations

import json
import logging
import threading
import time

from app.config import paths

log = logging.getLogger("workbench.alerts")

_FILE = paths.user_data / "alerts.jsonl"
_MAX_DAYS = 30
_MAX_RECORDS = 10_000
_lock = threading.Lock()
_writes_since_prune = 0


def append(alerts: list[dict]) -> None:
    global _writes_since_prune
    if not alerts:
        return
    now = time.time()
    with _lock:
        with _FILE.open("a") as fh:
            for a in alerts:
                fh.write(json.dumps({**a, "ts": now}) + "\n")
        _writes_since_prune += 1
        if _writes_since_prune >= 20:
            _prune_locked()
            _writes_since_prune = 0


def _prune_locked() -> None:
    if not _FILE.exists():
        return
    cutoff = time.time() - _MAX_DAYS * 86400
    rows = list_all()
    kept = [r for r in rows if r.get("ts", 0) >= cutoff][-_MAX_RECORDS:]
    with _FILE.open("w") as fh:
        for r in kept:
            fh.write(json.dumps(r) + "\n")


def list_all() -> list[dict]:
    if not _FILE.exists():
        return []
    out = []
    for line in _FILE.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def list_recent(limit: int = 200, severity: str | None = None,
                rule_type: str | None = None) -> list[dict]:
    rows = list_all()
    if severity:
        rows = [r for r in rows if r.get("severity") == severity]
    if rule_type:
        rows = [r for r in rows if r.get("type") == rule_type]
    return rows[-limit:][::-1]


def clear() -> int:
    with _lock:
        n = len(list_all())
        _FILE.write_text("")
    return n
