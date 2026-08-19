"""Backtest engine correctness: no lookahead, cost drag, stop/hold mechanics."""
from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from app.backtest.engine import BacktestConfig, run_backtest


def make_panel(closes: dict[str, list[float]], signal_days: dict[str, list[int]]) -> pl.DataFrame:
    """Synthetic panel: one row per symbol/day; open=high=low=close unless noted."""
    rows = []
    for sym, series in closes.items():
        for i, px in enumerate(series):
            rows.append({
                "symbol": sym,
                "date": dt.date(2024, 1, 1) + dt.timedelta(days=i),
                "open": px, "high": px * 1.001, "low": px * 0.999, "close": px,
                "sig": i in signal_days.get(sym, []),
            })
    return pl.DataFrame(rows)


CFG = dict(start="2024-01-01", end="2024-03-01", stop_loss=None, max_hold_days=5)


def test_entry_fills_next_day_open_no_lookahead():
    # signal on day 2; price jumps on day 3 — entry must be at day-3 open, not day-2 close
    panel = make_panel({"AAA": [100, 100, 100, 120, 121, 122, 123, 124]}, {"AAA": [2]})
    res = run_backtest(panel, pl.col("sig"), BacktestConfig(**CFG, commission_bps=0, slippage_bps=0))
    assert len(res["trades"]) == 1
    t = res["trades"][0]
    assert t["entry_date"] == "2024-01-04"        # day index 3
    assert t["entry_price"] == pytest.approx(120)


def test_costs_drag_returns():
    closes = {"AAA": [100, 100, 100, 105, 110, 115, 120, 125, 130]}
    panel = make_panel(closes, {"AAA": [1]})
    zero = run_backtest(panel, pl.col("sig"), BacktestConfig(**CFG, commission_bps=0, slippage_bps=0))
    real = run_backtest(panel, pl.col("sig"), BacktestConfig(**CFG, commission_bps=5, slippage_bps=20))
    assert real["metrics"]["total_return"] < zero["metrics"]["total_return"]


def test_stop_loss_exits_at_stop_price():
    # entry at 100 (day 2 open), then a -20% crash day: stop at -8% must fill at 92
    rows = make_panel({"AAA": [100, 100, 100, 100, 80, 80, 80]}, {"AAA": [1]})
    rows = rows.with_columns(
        pl.when(pl.col("date") == dt.date(2024, 1, 5))
        .then(95.0).otherwise(pl.col("open")).alias("open"))
    cfg = BacktestConfig(start="2024-01-01", end="2024-03-01", commission_bps=0,
                         slippage_bps=0, stop_loss=-0.08, max_hold_days=30)
    res = run_backtest(rows, pl.col("sig"), cfg)
    t = res["trades"][0]
    assert t["exit_reason"] == "stop_loss"
    assert t["exit_price"] == pytest.approx(92.0)  # min(open=95, stop=92)... gap logic


def test_gap_through_stop_fills_at_open():
    rows = make_panel({"AAA": [100, 100, 100, 100, 70, 70, 70]}, {"AAA": [1]})
    cfg = BacktestConfig(start="2024-01-01", end="2024-03-01", commission_bps=0,
                         slippage_bps=0, stop_loss=-0.08, max_hold_days=30)
    res = run_backtest(rows, pl.col("sig"), cfg)
    t = res["trades"][0]
    assert t["exit_reason"] == "stop_loss"
    assert t["exit_price"] == pytest.approx(70.0)  # gapped below stop: fill at open


def test_max_hold_days_enforced():
    closes = {"AAA": [100.0] * 20}
    res = run_backtest(make_panel(closes, {"AAA": [1]}), pl.col("sig"),
                       BacktestConfig(start="2024-01-01", end="2024-03-01",
                                      commission_bps=0, slippage_bps=0,
                                      stop_loss=None, max_hold_days=4))
    t = res["trades"][0]
    assert t["exit_reason"] == "max_hold"
    assert t["hold_days"] == 4


def test_take_profit_gap_fills_at_open():
    rows = make_panel({"AAA": [100, 100, 100, 100, 130, 130]}, {"AAA": [1]})
    cfg = BacktestConfig(start="2024-01-01", end="2024-03-01", commission_bps=0,
                         slippage_bps=0, stop_loss=None, take_profit=0.10, max_hold_days=30)
    res = run_backtest(rows, pl.col("sig"), cfg)
    t = res["trades"][0]
    assert t["exit_reason"] == "take_profit"
    assert t["exit_price"] == pytest.approx(130.0)  # gapped above target: fill at open
