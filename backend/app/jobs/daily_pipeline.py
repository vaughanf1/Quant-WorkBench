"""Post-market pipeline: pull EOD bars -> rebuild enriched -> monitor pass.

Staged with a progress callback (stage, pct, message); stage failures
accumulate and mark the run failed at the end rather than dying midway.
Scheduled weekdays after the US close (America/New_York).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import threading
import time
from typing import Callable

log = logging.getLogger("workbench.pipeline")

ProgressCb = Callable[[str, int, str], None]

BENCHMARKS = ["SPY", "QQQ"]

_status_lock = threading.Lock()
_status: dict = {"state": "idle", "stage": None, "pct": 0, "message": "",
                 "last_run": None, "errors": []}


def status() -> dict:
    with _status_lock:
        return dict(_status)


def _set(state: str | None = None, stage: str | None = None, pct: int | None = None,
         message: str | None = None, error: str | None = None) -> None:
    with _status_lock:
        if state is not None:
            _status["state"] = state
        if stage is not None:
            _status["stage"] = stage
        if pct is not None:
            _status["pct"] = pct
        if message is not None:
            _status["message"] = message
        if error is not None:
            _status["errors"].append(error)


def run_now(on_progress: ProgressCb | None = None, lookback_days: int = 30) -> dict:
    """Run the pipeline synchronously (call from a worker thread)."""
    import polars as pl

    from app.data.prices import refresh_universe_prices
    from app.data.store import get_store
    from app.data.universe import UniverseProvider
    from app.indicators.pipeline import build_enriched
    from app.monitor import alert_store, outcomes
    from app.monitor.engine import run_monitor_cycle

    def emit(stage: str, pct: int, message: str) -> None:
        _set(stage=stage, pct=pct, message=message)
        if on_progress:
            on_progress(stage, pct, message)
        log.info("[pipeline] %s %d%% %s", stage, pct, message)

    _set(state="running", pct=0, message="starting")
    with _status_lock:
        _status["errors"] = []
    started = time.time()
    result: dict = {}
    try:
        emit("universe", 2, "resolving universe")
        uni = UniverseProvider()
        tickers = uni.get_universe() + BENCHMARKS

        emit("prices", 5, f"refreshing EOD bars for {len(tickers)} tickers")
        end = dt.date.today()
        start = end - dt.timedelta(days=lookback_days)
        done_box = {"n": 0}

        def price_progress(done: int, total: int, ticker: str) -> None:
            done_box["n"] = done
            if done % 25 == 0 or done == total:
                emit("prices", 5 + int(55 * done / total), f"{done}/{total} {ticker}")

        res = refresh_universe_prices(tickers, start, end, on_progress=price_progress)
        empty = [t for t, v in res.items() if v == 0]
        if empty:
            _set(error=f"{len(empty)} tickers returned no bars: {empty[:10]}")
        result["prices"] = {"ok": len(res) - len(empty), "empty": len(empty)}

        emit("enrich", 65, "rebuilding enriched panel")
        store = get_store()
        store.refresh_views()
        enriched = build_enriched(store.scan_prices().filter(
            ~pl.col("symbol").is_in(BENCHMARKS)))
        n_parts = store.write_enriched(enriched)
        result["enriched_partitions"] = n_parts

        emit("outcomes", 85, "resolving open signal outcomes")
        closed = outcomes.check_outcomes()
        result["outcomes_closed"] = len(closed)

        emit("monitor", 92, "running monitor rules")
        alerts = run_monitor_cycle()
        alert_store.append(alerts)
        result["alerts"] = len(alerts)

        # push to subscribers + telegram (best-effort)
        try:
            from app.api.stream import publish_alerts_threadsafe
            publish_alerts_threadsafe(alerts)
        except Exception:
            pass
        try:
            from app.monitor.telegram import get_notifier
            notifier = get_notifier()
            if notifier.enabled and (alerts or closed):
                async def _push() -> None:
                    await notifier.notify_alerts(alerts)
                    for o in closed:
                        await notifier.notify_outcome(o)
                asyncio.run(_push())
        except Exception as exc:
            _set(error=f"telegram push failed: {exc}")

        emit("done", 100, f"pipeline complete in {time.time() - started:.0f}s")
        with _status_lock:
            failed = bool(_status["errors"])
            _status.update(state="failed" if failed else "idle",
                           last_run=dt.datetime.now().isoformat(timespec="seconds"))
        result["errors"] = status()["errors"]
        return result
    except Exception as exc:
        log.exception("pipeline failed")
        _set(state="failed", error=str(exc))
        with _status_lock:
            _status["last_run"] = dt.datetime.now().isoformat(timespec="seconds")
        return {"error": str(exc), **result}


def start_scheduler() -> object:
    """APScheduler: post-market pipeline weekdays 17:30 America/New_York."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched = AsyncIOScheduler(timezone="America/New_York")
    sched.add_job(lambda: threading.Thread(target=run_now, daemon=True).start(),
                  CronTrigger(day_of_week="mon-fri", hour=17, minute=30),
                  id="daily_pipeline", coalesce=True, max_instances=1,
                  misfire_grace_time=3600)
    sched.start()
    return sched
