"""Rolling 7/30-day scorecards per strategy, from recorded outcomes.

QuantLive's PerformanceTracker pattern, with its staleness bug fixed: the
scorecard is recomputed on read (and by the scheduled pipeline), so a
strategy that stops firing rolls off honestly instead of freezing.
"""
from __future__ import annotations

import datetime as dt

from app.monitor.outcomes import list_closed

PERIODS = {"7d": 7, "30d": 30}
WIN_RESULTS = {"target_hit"}


def scorecards(now: dt.date | None = None) -> list[dict]:
    now = now or dt.date.today()
    rows = list_closed(limit=100_000)
    out: list[dict] = []
    strategies = sorted({str(r.get("strategy_id") or "manual") for r in rows})
    for strat in strategies:
        for period, days in PERIODS.items():
            cutoff = (now - dt.timedelta(days=days)).isoformat()
            sample = [r for r in rows
                      if str(r.get("strategy_id") or "manual") == strat
                      and str(r.get("exit_date", "")) >= cutoff]
            if not sample:
                continue
            wins = [r for r in sample if r["result"] in WIN_RESULTS or r.get("ret", 0) > 0]
            gross_win = sum(r["ret"] for r in sample if r.get("ret", 0) > 0)
            gross_loss = -sum(r["ret"] for r in sample if r.get("ret", 0) < 0)
            out.append({
                "strategy_id": strat, "period": period, "n": len(sample),
                "win_rate": round(len(wins) / len(sample), 4),
                "avg_ret": round(sum(r.get("ret", 0) for r in sample) / len(sample), 6),
                "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else None,
                "results": {k: sum(1 for r in sample if r["result"] == k)
                            for k in ("target_hit", "stop_hit", "expired")},
            })
    return out
