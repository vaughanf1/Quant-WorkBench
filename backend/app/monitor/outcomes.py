"""Outcome tracking: fired signals get a recorded result, not a memory hole.

Ported from QuantLive's OutcomeDetector, adapted from a single live-price
instrument to EOD bars over many symbols:

  * when an alert with ``track_outcome`` fires (or a screener strategy is
    tracked), a signal is opened with entry price, target, stop and expiry
    derived from the strategy's TAKE_PROFIT / STOP_LOSS / MAX_HOLD_DAYS;
  * each post-market run walks subsequent daily bars and resolves, in
    priority order: expiry -> stop (day low breaches) -> target (day high
    reaches). Priority is conservative: a bar that touches both counts as
    a stop.

Storage: JSON per open signal, JSONL for closed outcomes.
"""
from __future__ import annotations

import json
import logging
import uuid

import polars as pl

from app.config import paths
from app.data.store import get_store

log = logging.getLogger("workbench.outcomes")

_OPEN_DIR = paths.user_data / "open_signals"
_CLOSED = paths.user_data / "outcomes.jsonl"

DEFAULT_TARGET = 0.10
DEFAULT_STOP = -0.05
DEFAULT_EXPIRY_DAYS = 20


def open_signal(symbol: str, entry_date: str, entry_price: float, strategy_id: str | None,
                target_pct: float | None, stop_pct: float | None,
                expiry_days: int | None, source: str = "monitor") -> dict:
    _OPEN_DIR.mkdir(parents=True, exist_ok=True)
    sig = {
        "id": uuid.uuid4().hex[:12], "symbol": symbol.upper(),
        "entry_date": entry_date, "entry_price": entry_price,
        "strategy_id": strategy_id, "source": source,
        "target_pct": target_pct if target_pct is not None else DEFAULT_TARGET,
        "stop_pct": stop_pct if stop_pct is not None else DEFAULT_STOP,
        "expiry_days": expiry_days if expiry_days is not None else DEFAULT_EXPIRY_DAYS,
    }
    (_OPEN_DIR / f"{sig['id']}.json").write_text(json.dumps(sig, indent=2))
    return sig


def list_open() -> list[dict]:
    _OPEN_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for f in sorted(_OPEN_DIR.glob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except Exception as exc:
            log.warning("skipping corrupted open signal %s: %s", f, exc)
    return out


def list_closed(limit: int = 500) -> list[dict]:
    if not _CLOSED.exists():
        return []
    rows = []
    for line in _CLOSED.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:][::-1]


def evaluate_signal(sig: dict, bars: list[dict]) -> dict | None:
    """Pure resolution over daily bars strictly after entry_date.

    Returns the outcome dict or None if still open. Priority per bar:
    stop before target (conservative); expiry checked by bar count.
    """
    target_px = sig["entry_price"] * (1 + sig["target_pct"])
    stop_px = sig["entry_price"] * (1 + sig["stop_pct"])
    for i, bar in enumerate(bars, start=1):
        if bar["low"] <= stop_px:
            fill = min(bar["open"], stop_px)
            return _outcome(sig, "stop_hit", fill, bar["date"], i)
        if bar["high"] >= target_px:
            fill = max(bar["open"], target_px)
            return _outcome(sig, "target_hit", fill, bar["date"], i)
        if i >= sig["expiry_days"]:
            return _outcome(sig, "expired", bar["close"], bar["date"], i)
    return None


def _outcome(sig: dict, result: str, exit_price: float, exit_date, days: int) -> dict:
    return {**sig, "result": result, "exit_price": round(float(exit_price), 4),
            "exit_date": str(exit_date), "days_held": days,
            "ret": round(float(exit_price) / sig["entry_price"] - 1, 6)}


def check_outcomes() -> list[dict]:
    """Resolve all open signals against bars now on disk. Returns new outcomes."""
    open_signals = list_open()
    if not open_signals:
        return []
    store = get_store()
    symbols = sorted({s["symbol"] for s in open_signals})
    panel = (store.scan_prices()
             .filter(pl.col("symbol").is_in(symbols))
             .select(["symbol", "date", "open", "high", "low", "close"])
             .collect().sort(["symbol", "date"]))
    closed: list[dict] = []
    for sig in open_signals:
        bars = (panel.filter((pl.col("symbol") == sig["symbol"])
                             & (pl.col("date") > pl.lit(sig["entry_date"]).cast(pl.Date)))
                .to_dicts())
        outcome = evaluate_signal(sig, bars)
        if outcome is not None:
            closed.append(outcome)
            (_OPEN_DIR / f"{sig['id']}.json").unlink(missing_ok=True)
    if closed:
        with _CLOSED.open("a") as fh:
            for o in closed:
                fh.write(json.dumps(o, default=str) + "\n")
    return closed
