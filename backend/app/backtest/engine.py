"""Per-trade, signal-driven backtest engine.

Mechanics (no lookahead by construction):
  * entry signals are evaluated on day T from the strategy's Polars mask;
  * entries fill at day T+1's OPEN, plus slippage, plus commission;
  * exits check, in priority order: stop loss (intraday, gap-aware), take
    profit (intraday, gap-aware), max holding period (close), end of data;
  * equal-weight sizing across a max number of concurrent positions.

Outputs: daily equity curve, per-trade detail (entry/exit dates and prices,
return, holding days, exit reason), and summary metrics.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np
import polars as pl

from app.backtest.metrics import summary_metrics

log = logging.getLogger("workbench.backtest")


@dataclass(frozen=True)
class BacktestConfig:
    start: str
    end: str
    commission_bps: float = 1.0        # per side (IBKR-tier ~0.5-1bp on liquid names)
    slippage_bps: float = 5.0          # per side
    stop_loss: float | None = -0.08    # negative fraction from entry
    take_profit: float | None = None   # positive fraction from entry
    max_hold_days: int = 20
    max_positions: int = 10
    initial_capital: float = 100_000.0


def run_backtest(panel: pl.DataFrame, entry_mask: pl.Expr, cfg: BacktestConfig,
                 on_progress: Callable[[int, int, str, float], bool] | None = None) -> dict:
    """Run the simulation. ``panel`` is the enriched long panel (sorted by
    symbol, date); ``entry_mask`` is the strategy's boolean expression.

    ``on_progress(day_idx, total_days, date, equity)`` is called each simulated
    day; returning False cancels the run.
    """
    df = (panel.with_columns(entry_mask.fill_null(False).alias("_entry"))
               .select(["symbol", "date", "open", "high", "low", "close", "_entry"])
               .sort(["symbol", "date"]))

    dates = (df.filter((pl.col("date") >= pl.lit(cfg.start).cast(pl.Date))
                       & (pl.col("date") <= pl.lit(cfg.end).cast(pl.Date)))
               .select(pl.col("date").unique().sort()).to_series().to_list())
    if len(dates) < 2:
        return {"error": "not enough trading days in range", "trades": [], "equity": []}

    # index bars by date for O(1) daily access
    by_date: dict = {d: g for (d,), g in
                     df.filter(pl.col("date").is_in(dates)).partition_by("date", as_dict=True).items()}

    cost_in = 1 + (cfg.commission_bps + cfg.slippage_bps) / 1e4
    cost_out = 1 - (cfg.commission_bps + cfg.slippage_bps) / 1e4

    cash = cfg.initial_capital
    positions: dict[str, dict] = {}   # symbol -> {shares, entry_px, entry_date, days}
    pending_entries: list[str] = []
    trades: list[dict] = []
    equity_curve: list[dict] = []
    cancelled = False

    def _close_position(sym: str, px: float, date, reason: str) -> None:
        nonlocal cash
        pos = positions.pop(sym)
        proceeds = pos["shares"] * px * cost_out
        cash += proceeds
        entry_cost = pos["shares"] * pos["entry_px"] * cost_in
        trades.append({
            "symbol": sym, "entry_date": str(pos["entry_date"]), "exit_date": str(date),
            "entry_price": round(pos["entry_px"], 4), "exit_price": round(px, 4),
            "shares": pos["shares"], "pnl": round(proceeds - entry_cost, 2),
            "ret": round(proceeds / entry_cost - 1, 6),
            "hold_days": pos["days"], "exit_reason": reason,
        })

    for i, d in enumerate(dates):
        day = by_date.get(d)
        if day is None:
            continue
        bars = {r["symbol"]: r for r in day.to_dicts()}

        # 1) fill pending entries at today's open
        for sym in pending_entries:
            if sym in positions or sym not in bars:
                continue
            if len(positions) >= cfg.max_positions:
                break
            open_px = bars[sym]["open"]
            if not open_px or open_px <= 0:
                continue
            equity_now = cash + sum(p["shares"] * bars.get(s, {}).get("open", p["entry_px"])
                                    for s, p in positions.items())
            slot = equity_now / cfg.max_positions
            budget = min(slot, cash)
            shares = int(budget / (open_px * cost_in))
            if shares <= 0:
                continue
            cash -= shares * open_px * cost_in
            positions[sym] = {"shares": shares, "entry_px": open_px, "entry_date": d, "days": 0}
        pending_entries = []

        # 2) manage open positions: stop -> take profit -> max hold
        for sym in list(positions):
            bar = bars.get(sym)
            if bar is None:      # halted / missing bar: age the position, keep it
                positions[sym]["days"] += 1
                continue
            pos = positions[sym]
            pos["days"] += 1
            entry_px = pos["entry_px"]
            if cfg.stop_loss is not None:
                stop_px = entry_px * (1 + cfg.stop_loss)
                if bar["low"] <= stop_px:
                    fill = min(bar["open"], stop_px)  # gap through the stop fills at open
                    _close_position(sym, fill, d, "stop_loss")
                    continue
            if cfg.take_profit is not None:
                tp_px = entry_px * (1 + cfg.take_profit)
                if bar["high"] >= tp_px:
                    fill = max(bar["open"], tp_px)
                    _close_position(sym, fill, d, "take_profit")
                    continue
            if pos["days"] >= cfg.max_hold_days:
                _close_position(sym, bar["close"], d, "max_hold")

        # 3) collect today's signals for tomorrow's open
        if len(positions) < cfg.max_positions:
            hits = day.filter(pl.col("_entry"))
            if hits.height:
                pending_entries = [s for s in hits["symbol"].to_list() if s not in positions]

        # 4) mark to market
        mtm = cash + sum(p["shares"] * bars.get(s, {}).get("close", p["entry_px"])
                         for s, p in positions.items())
        equity_curve.append({"date": str(d), "equity": round(mtm, 2),
                             "positions": len(positions)})
        if on_progress is not None:
            if on_progress(i + 1, len(dates), str(d), mtm) is False:
                cancelled = True
                break

    # close whatever is still open at the last seen close
    last_d = dates[min(i, len(dates) - 1)]
    last_bars = {r["symbol"]: r for r in by_date.get(last_d, pl.DataFrame()).to_dicts()} \
        if by_date.get(last_d) is not None else {}
    for sym in list(positions):
        px = last_bars.get(sym, {}).get("close", positions[sym]["entry_px"])
        _close_position(sym, px, last_d, "end_of_data")
    if equity_curve:
        equity_curve[-1]["equity"] = round(cash, 2)

    eq = np.array([p["equity"] for p in equity_curve], dtype=float)
    metrics = summary_metrics(eq, trades, cfg.initial_capital)
    return {"config": cfg.__dict__, "metrics": metrics, "trades": trades,
            "equity": equity_curve, "cancelled": cancelled}
