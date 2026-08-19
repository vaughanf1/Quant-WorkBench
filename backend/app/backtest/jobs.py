"""Backtest job registry: hash-keyed jobs, thread workers, SSE-friendly progress.

Pattern from tickflow-stock-panel: the job key is a hash of the request
params, so a page refresh reconnects to the *running* job instead of starting
a duplicate; progress is an append-only list and each SSE connection keeps
its own cursor, so N clients each receive the full stream.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time

import polars as pl

from app.backtest.engine import BacktestConfig, run_backtest
from app.config import paths
from app.data.store import get_store
from app.strategy import custom_signals
from app.strategy.engine import get_engine

log = logging.getLogger("workbench.backtest.jobs")

_MAX_CONCURRENT = 2
_semaphore = threading.Semaphore(_MAX_CONCURRENT)
_jobs: dict[str, "BacktestJob"] = {}
_jobs_lock = threading.Lock()
_JOB_TTL_S = 3600


class BacktestJob:
    def __init__(self, key: str, request: dict) -> None:
        self.key = key
        self.request = request
        self.progress: list[dict] = []      # append-only; SSE readers keep cursors
        self.result: dict | None = None
        self.error: str | None = None
        self.cancel_event = threading.Event()
        self.done_event = threading.Event()
        self.created_at = time.time()

    def push(self, kind: str, data: dict) -> None:
        self.progress.append({"kind": kind, "data": data})


def job_key(request: dict) -> str:
    canonical = json.dumps(request, sort_keys=True, default=str)
    return hashlib.md5(canonical.encode()).hexdigest()


def _run(job: BacktestJob) -> None:
    try:
        with _semaphore:
            if job.cancel_event.is_set():
                raise InterruptedError("cancelled while queued")
            req = job.request
            sdef = get_engine().get(req["strategy"])
            if sdef is None:
                raise ValueError(f"unknown strategy '{req['strategy']}'")

            store = get_store()
            panel = (store.scan_enriched().collect().sort(["symbol", "date"]))
            panel = custom_signals.inject(panel)
            params = {**sdef.defaults(), **(req.get("params") or {})}
            cfg = BacktestConfig(
                start=req["start"], end=req["end"],
                commission_bps=float(req.get("commission_bps", 1.0)),
                slippage_bps=float(req.get("slippage_bps", 5.0)),
                stop_loss=req.get("stop_loss", sdef.stop_loss),
                take_profit=req.get("take_profit", sdef.take_profit),
                max_hold_days=int(req.get("max_hold_days", sdef.max_hold_days or 20)),
                max_positions=int(req.get("max_positions", 10)),
            )

            last_pushed = 0.0

            def on_progress(day: int, total: int, date: str, equity: float) -> bool:
                nonlocal last_pushed
                now = time.time()
                if now - last_pushed > 0.15 or day == total:  # throttle SSE frames
                    job.push("progress", {"day": day, "total": total,
                                          "date": date, "equity": round(equity, 2)})
                    last_pushed = now
                return not job.cancel_event.is_set()

            result = run_backtest(panel, sdef.filter_fn(panel, params), cfg, on_progress)
            result["strategy"] = sdef.id
            job.result = result
            _persist(job)
            job.push("done", _summary_payload(result))
    except Exception as exc:
        log.warning("backtest job %s failed: %s", job.key, exc)
        job.error = str(exc)
        job.push("error", {"message": str(exc)})
    finally:
        job.done_event.set()


def _summary_payload(result: dict) -> dict:
    return {k: result[k] for k in ("strategy", "config", "metrics", "equity", "cancelled")
            if k in result} | {"trades": result.get("trades", [])[:500],
                               "n_trades_total": len(result.get("trades", []))}


def _persist(job: BacktestJob) -> None:
    out = paths.backtests / f"{job.key}.json"
    out.write_text(json.dumps({"request": job.request, "result": job.result}, default=str))


def start_or_attach(request: dict) -> tuple[BacktestJob, bool]:
    """Return (job, is_new). An identical in-flight request attaches."""
    key = job_key(request)
    with _jobs_lock:
        # prune finished, stale jobs
        for k in [k for k, j in _jobs.items()
                  if j.done_event.is_set() and time.time() - j.created_at > _JOB_TTL_S]:
            _jobs.pop(k)
        existing = _jobs.get(key)
        if existing is not None and not existing.done_event.is_set():
            return existing, False
        job = BacktestJob(key, request)
        _jobs[key] = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return job, True


def get_job(key: str) -> BacktestJob | None:
    with _jobs_lock:
        return _jobs.get(key)


def cancel(request: dict) -> bool:
    job = get_job(job_key(request))
    if job is None:
        return False
    job.cancel_event.set()
    return True
