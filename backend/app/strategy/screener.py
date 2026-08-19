"""Screener runner: apply a strategy's filter to the enriched panel.

Strategies see a trailing window of enriched history (so per-symbol shifts
and rolling expressions work), then hits are taken from the evaluation date
only, ranked by the strategy's ``order_by`` column.
"""
from __future__ import annotations

import logging

import polars as pl

from app.data.store import get_store
from app.strategy import custom_signals
from app.strategy.engine import StrategyDef, get_engine

log = logging.getLogger("workbench.screener")

_WINDOW_DAYS = 300  # trading days of history handed to strategy filters

_DISPLAY_COLS = ["symbol", "close", "ret_1d", "vol_ratio_20", "rsi14",
                 "mom_20d", "dist_52w_high", "rvol_20d"]


def _panel(date: str | None = None) -> tuple[pl.DataFrame, str] | tuple[None, None]:
    store = get_store()
    eval_date = date or store.latest_enriched_date()
    if eval_date is None:
        return None, None
    lf = store.scan_enriched().filter(pl.col("date") <= pl.lit(eval_date).cast(pl.Date))
    dates = (lf.select(pl.col("date").unique().sort(descending=True).head(_WINDOW_DAYS))
             .collect()["date"])
    if dates.is_empty():
        return None, None
    df = lf.filter(pl.col("date") >= dates.min()).collect().sort(["symbol", "date"])
    df = custom_signals.inject(df)
    return df, str(eval_date)


def run_strategy(sdef: StrategyDef, params: dict | None = None,
                 date: str | None = None) -> dict:
    df, eval_date = _panel(date)
    if df is None:
        return {"strategy": sdef.id, "date": None, "hits": [], "count": 0,
                "error": "no enriched data — run the data pipeline first"}
    merged = {**sdef.defaults(), **(params or {})}
    try:
        mask = sdef.filter_fn(df, merged)
        hits = df.filter(mask & (pl.col("date") == pl.lit(eval_date).cast(pl.Date)))
    except Exception as exc:
        log.warning("strategy %s failed: %s", sdef.id, exc)
        return {"strategy": sdef.id, "date": eval_date, "hits": [], "count": 0,
                "error": f"filter error: {exc}"}

    if sdef.order_by and sdef.order_by in hits.columns:
        hits = hits.sort(sdef.order_by, descending=sdef.descending, nulls_last=True)
    hits = hits.head(sdef.limit)
    cols = [c for c in _DISPLAY_COLS if c in hits.columns]
    if sdef.order_by and sdef.order_by in hits.columns and sdef.order_by not in cols:
        cols.append(sdef.order_by)
    rows = hits.select(cols).to_dicts()
    return {"strategy": sdef.id, "date": eval_date, "hits": rows, "count": len(rows)}


def run_all(date: str | None = None) -> dict:
    """Hit counts for every loaded strategy (drives the strategy card grid)."""
    df, eval_date = _panel(date)
    engine = get_engine()
    results = {}
    if df is None:
        return {"date": None, "counts": {}, "errors": engine.load_errors()}
    today = df.filter(pl.col("date") == pl.lit(eval_date).cast(pl.Date))
    for sdef in engine.all():
        try:
            mask = sdef.filter_fn(df, sdef.defaults())
            n = df.filter(mask & (pl.col("date") == pl.lit(eval_date).cast(pl.Date))).height
            results[sdef.id] = n
        except Exception as exc:
            log.warning("strategy %s failed in run_all: %s", sdef.id, exc)
            results[sdef.id] = -1  # signals an error to the UI
    _ = today
    return {"date": eval_date, "counts": results, "errors": engine.load_errors()}


def run_custom_signal_screen(signal_id: str, date: str | None = None) -> dict:
    """Screen the universe on a single custom signal column."""
    df, eval_date = _panel(date)
    col = custom_signals.column_name(signal_id)
    if df is None or col not in df.columns:
        return {"signal": signal_id, "date": eval_date, "hits": [], "count": 0,
                "error": None if df is not None else "no enriched data"}
    hits = df.filter(pl.col(col) & (pl.col("date") == pl.lit(eval_date).cast(pl.Date)))
    rows = hits.select([c for c in _DISPLAY_COLS if c in hits.columns]).to_dicts()
    return {"signal": signal_id, "date": eval_date, "hits": rows, "count": len(rows)}
