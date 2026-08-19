"""Backtest summary metrics: equity-curve stats + true per-trade stats.

Equity-curve math follows GreyMatter's metrics module; per-trade win rate,
profit factor and holding stats are computed from the trade list (the piece
the original engine lacked).
"""
from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


def max_drawdown(equity: np.ndarray) -> tuple[float, int]:
    """Return (max drawdown as negative fraction, duration in days)."""
    if equity.size == 0:
        return 0.0, 0
    peaks = np.maximum.accumulate(equity)
    dd = equity / peaks - 1
    trough = int(dd.argmin())
    peak = int(equity[:trough + 1].argmax()) if trough else 0
    return float(dd.min()), trough - peak


def summary_metrics(equity: np.ndarray, trades: list[dict], initial: float) -> dict:
    out: dict = {"n_trades": len(trades)}
    if equity.size >= 2:
        rets = np.diff(equity) / equity[:-1]
        total = float(equity[-1] / initial - 1)
        years = equity.size / TRADING_DAYS
        vol = float(rets.std(ddof=1)) if rets.size > 1 else 0.0
        mdd, mdd_days = max_drawdown(equity)
        out.update({
            "total_return": round(total, 6),
            "ann_return": round((1 + total) ** (1 / years) - 1, 6) if years > 0 and total > -1 else None,
            "ann_vol": round(vol * TRADING_DAYS ** 0.5, 6),
            "sharpe": round(float(rets.mean()) / vol * TRADING_DAYS ** 0.5, 4) if vol > 0 else None,
            "max_drawdown": round(mdd, 6),
            "max_drawdown_days": mdd_days,
            "final_equity": round(float(equity[-1]), 2),
        })
    if trades:
        rets_t = np.array([t["ret"] for t in trades])
        wins, losses = rets_t[rets_t > 0], rets_t[rets_t <= 0]
        gross_win = float(sum(t["pnl"] for t in trades if t["pnl"] > 0))
        gross_loss = float(-sum(t["pnl"] for t in trades if t["pnl"] < 0))
        reasons: dict[str, int] = {}
        for t in trades:
            reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1
        out.update({
            "win_rate": round(float((rets_t > 0).mean()), 4),
            "avg_win": round(float(wins.mean()), 6) if wins.size else None,
            "avg_loss": round(float(losses.mean()), 6) if losses.size else None,
            "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else None,
            "avg_hold_days": round(float(np.mean([t["hold_days"] for t in trades])), 2),
            "exit_reasons": reasons,
        })
    return out
