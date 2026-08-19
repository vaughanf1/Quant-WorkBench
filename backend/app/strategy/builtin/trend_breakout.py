"""Trend breakout: new 60-day high in an established uptrend, on volume."""
import polars as pl

META = {
    "id": "trend_breakout",
    "name": "Trend Breakout",
    "description": "Close at a 60-day high, above MA60, with volume expansion.",
    "tags": ["trend", "breakout"],
    "params": [
        {"id": "vol_mult", "label": "Volume multiple", "type": "float", "default": 1.5, "min": 1.0, "max": 5.0, "step": 0.1},
    ],
    "order_by": "mom_20d", "descending": True, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = ["signal_new_high_60d"]
STOP_LOSS = -0.08
MAX_HOLD_DAYS = 20

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return (
        pl.col("signal_new_high_60d")
        & (pl.col("close") > pl.col("ma60"))
        & (pl.col("vol_ratio_20") > params["vol_mult"])
    )
