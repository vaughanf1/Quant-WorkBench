"""REST API: strategies, screener, custom signals, monitor, data, dashboard."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import threading

import polars as pl
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.backtest import jobs as bt_jobs
from app.data.store import get_store
from app.data.universe import UniverseProvider
from app.indicators.pipeline import SIGNAL_COLUMNS
from app.jobs import daily_pipeline
from app.monitor import alert_store, outcomes, performance
from app.monitor import rules as monitor_rules
from app.monitor.engine import get_monitor, run_monitor_cycle
from app.strategy import custom_signals, screener
from app.strategy.engine import get_engine

log = logging.getLogger("workbench.api")
router = APIRouter()

_uni = UniverseProvider()


# ---- strategies -------------------------------------------------------------
@router.get("/strategies")
def list_strategies():
    eng = get_engine()
    return {"strategies": [s.meta_dict() for s in eng.all()],
            "load_errors": eng.load_errors()}


@router.post("/strategies/reload")
def reload_strategies():
    get_engine().reload()
    return list_strategies()


# ---- screener ---------------------------------------------------------------
@router.get("/screener/all")
def screener_all(date: str | None = None):
    return screener.run_all(date)


@router.get("/screener/run")
def screener_run(strategy: str, date: str | None = None, params: str | None = None):
    sdef = get_engine().get(strategy)
    if sdef is None:
        raise HTTPException(404, f"unknown strategy '{strategy}'")
    parsed = json.loads(params) if params else None
    return screener.run_strategy(sdef, parsed, date)


@router.get("/screener/custom/{signal_id}")
def screener_custom(signal_id: str, date: str | None = None):
    return screener.run_custom_signal_screen(signal_id, date)


# ---- custom signals ----------------------------------------------------------
@router.get("/custom-signals")
def list_custom_signals():
    return {"signals": custom_signals.load_all()}


@router.get("/custom-signals/options")
def custom_signal_options():
    return custom_signals.options()


class SignalBody(BaseModel):
    id: str
    name: str = ""
    enabled: bool = True
    conditions: list[dict]


@router.post("/custom-signals")
def save_custom_signal(body: SignalBody):
    err = custom_signals.save(body.model_dump())
    if err:
        raise HTTPException(422, err)
    return {"ok": True}


@router.delete("/custom-signals/{signal_id}")
def delete_custom_signal(signal_id: str):
    return {"deleted": custom_signals.delete(signal_id)}


# ---- backtest ----------------------------------------------------------------
def _bt_request(strategy: str, start: str, end: str, commission_bps: float,
                slippage_bps: float, stop_loss: float | None, take_profit: float | None,
                max_hold_days: int | None, max_positions: int, params: str | None) -> dict:
    req = {"strategy": strategy, "start": start, "end": end,
           "commission_bps": commission_bps, "slippage_bps": slippage_bps,
           "max_positions": max_positions}
    if stop_loss is not None:
        req["stop_loss"] = stop_loss
    if take_profit is not None:
        req["take_profit"] = take_profit
    if max_hold_days is not None:
        req["max_hold_days"] = max_hold_days
    if params:
        req["params"] = json.loads(params)
    return req


@router.get("/backtest/stream")
async def backtest_stream(request: Request, strategy: str, start: str, end: str,
                          commission_bps: float = 1.0, slippage_bps: float = 5.0,
                          stop_loss: float | None = None, take_profit: float | None = None,
                          max_hold_days: int | None = None, max_positions: int = 10,
                          params: str | None = None):
    """SSE backtest run. Identical params re-attach to the running job, so a
    page refresh resumes the stream instead of restarting the backtest."""
    req = _bt_request(strategy, start, end, commission_bps, slippage_bps,
                      stop_loss, take_profit, max_hold_days, max_positions, params)
    job, _ = bt_jobs.start_or_attach(req)

    async def gen():
        cursor = 0
        while True:
            if await request.is_disconnected():
                break
            while cursor < len(job.progress):
                item = job.progress[cursor]
                cursor += 1
                yield {"event": item["kind"], "data": json.dumps(item["data"], default=str)}
                if item["kind"] in ("done", "error"):
                    return
            await asyncio.sleep(0.2)

    return EventSourceResponse(gen())


class CancelBody(BaseModel):
    request: dict


@router.post("/backtest/cancel")
def backtest_cancel(body: CancelBody):
    return {"cancelled": bt_jobs.cancel(body.request)}


# ---- monitor -------------------------------------------------------------------
@router.get("/monitor/rules")
def list_rules():
    return {"rules": monitor_rules.load_all(),
            "options": {"types": sorted(monitor_rules.RULE_TYPES),
                        "logics": sorted(monitor_rules.LOGICS),
                        "severities": sorted(monitor_rules.SEVERITIES),
                        "signal_fields": custom_signals.options()}}


@router.post("/monitor/rules")
def save_rule(rule: dict):
    saved, err = monitor_rules.save(rule)
    if err:
        raise HTTPException(422, err)
    get_monitor().reset_cooldowns(saved["id"])
    return {"rule": saved}


@router.delete("/monitor/rules/{rule_id}")
def delete_rule(rule_id: str):
    return {"deleted": monitor_rules.delete(rule_id)}


@router.post("/monitor/run")
def monitor_run():
    """Manual monitor pass (also runs in the daily pipeline)."""
    alerts = run_monitor_cycle()
    alert_store.append(alerts)
    _track_alert_outcomes(alerts)
    if alerts:
        from app.api.stream import publish_threadsafe
        publish_threadsafe("alerts", alerts)
    return {"alerts": alerts, "count": len(alerts)}


def _track_alert_outcomes(alerts: list[dict]) -> None:
    eng = get_engine()
    for a in alerts:
        if not a.get("track_outcome"):
            continue
        sdef = eng.get(a.get("strategy_id") or "")
        outcomes.open_signal(
            a["symbol"], a["date"], a["close"], a.get("strategy_id"),
            target_pct=getattr(sdef, "take_profit", None) if sdef else None,
            stop_pct=getattr(sdef, "stop_loss", None) if sdef else None,
            expiry_days=getattr(sdef, "max_hold_days", None) if sdef else None)


@router.get("/monitor/alerts")
def list_alerts(limit: int = 200, severity: str | None = None, type: str | None = None):
    return {"alerts": alert_store.list_recent(limit, severity, type)}


@router.delete("/monitor/alerts")
def clear_alerts():
    return {"cleared": alert_store.clear()}


@router.get("/monitor/outcomes")
def list_outcomes():
    return {"open": outcomes.list_open(), "closed": outcomes.list_closed(200),
            "scorecards": performance.scorecards()}


# ---- data / pipeline --------------------------------------------------------
@router.get("/data/status")
def data_status():
    store = get_store()
    latest = store.latest_enriched_date()
    n_symbols = None
    if latest:
        day = store.read_enriched_day(latest)
        n_symbols = day.height if day is not None else None
    return {"latest_enriched": latest, "symbols": n_symbols,
            "pipeline": daily_pipeline.status(),
            "universe_size": len(_uni.get_universe())}


@router.post("/data/pipeline/run")
def pipeline_run(lookback_days: int = 30):
    if daily_pipeline.status()["state"] == "running":
        return {"started": False, "reason": "already running"}
    threading.Thread(target=daily_pipeline.run_now,
                     kwargs={"lookback_days": lookback_days}, daemon=True).start()
    return {"started": True}


@router.get("/data/candles/{symbol}")
def candles(symbol: str, days: int = 250):
    store = get_store()
    df = (store.scan_prices().filter(pl.col("symbol") == symbol.upper())
          .sort("date").tail(days).collect())
    if df.is_empty():
        raise HTTPException(404, f"no bars for {symbol}")
    return {"symbol": symbol.upper(),
            "bars": df.select(["date", "open", "high", "low", "close", "volume"])
                      .with_columns(pl.col("date").cast(pl.Date).cast(pl.Utf8)).to_dicts()}


# ---- dashboard ----------------------------------------------------------------
@router.get("/dashboard")
def dashboard():
    store = get_store()
    latest = store.latest_enriched_date()
    if latest is None:
        return {"date": None}
    df = store.scan_enriched().filter(
        pl.col("date") == pl.lit(latest).cast(pl.Date)).collect()

    adv = df.filter(pl.col("ret_1d") > 0).height
    dec = df.filter(pl.col("ret_1d") < 0).height
    above_ma200 = df.filter(pl.col("close") > pl.col("ma200")).height
    new_highs = int(df["signal_new_high_252d"].sum())
    new_lows = int(df["signal_new_low_60d"].sum())

    movers_cols = ["symbol", "close", "ret_1d", "vol_ratio_20", "mom_20d"]
    gainers = df.sort("ret_1d", descending=True).head(8).select(movers_cols).to_dicts()
    losers = df.sort("ret_1d").head(8).select(movers_cols).to_dicts()

    sectors = _uni.sectors()
    sec_df = (df.with_columns(pl.col("symbol").replace_strict(sectors, default="Unknown")
                              .alias("sector"))
              .group_by("sector").agg(pl.col("ret_1d").mean().alias("avg_ret"),
                                      pl.len().alias("n"))
              .sort("avg_ret", descending=True))

    # SPY benchmark sparkline (kept out of the enriched universe panel)
    spy = (store.scan_prices().filter(pl.col("symbol") == "SPY").sort("date")
           .tail(120).select(["date", "close"]).collect())
    spark = spy.with_columns(pl.col("date").cast(pl.Date).cast(pl.Utf8)).to_dicts()

    counts = screener.run_all(latest)["counts"]
    return {
        "date": str(latest),
        "breadth": {"advancers": adv, "decliners": dec, "above_ma200": above_ma200,
                    "total": df.height, "new_highs_252d": new_highs, "new_lows_60d": new_lows},
        "gainers": gainers, "losers": losers,
        "sectors": sec_df.to_dicts(),
        "spy": spark,
        "strategy_counts": counts,
        "alerts": alert_store.list_recent(8),
        "scorecards": performance.scorecards(),
    }


@router.get("/universe")
def universe():
    names = _uni.names()
    sectors = _uni.sectors()
    return {"tickers": [{"symbol": t, "name": names.get(t), "sector": sectors.get(t)}
                        for t in _uni.get_universe()]}


@router.get("/health")
def health():
    return {"ok": True, "time": dt.datetime.now().isoformat(timespec="seconds")}
