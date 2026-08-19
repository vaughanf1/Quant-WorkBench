"""Bollinger breakout: close pushes through the upper band."""
import polars as pl

META = {
    "id": "boll_breakout",
    "name": "Bollinger Breakout",
    "description": "Close crosses above the upper Bollinger band after a quiet squeeze.",
    "tags": ["breakout", "volatility"],
    "params": [
        {"id": "max_band_width", "label": "Max band width (pct)", "type": "float", "default": 0.12, "min": 0.02, "max": 0.5, "step": 0.01},
    ],
    "order_by": "vol_ratio_20", "descending": True, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = ["signal_boll_break_up"]
STOP_LOSS = -0.06
MAX_HOLD_DAYS = 10

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    width = (pl.col("boll_up") - pl.col("boll_low")) / pl.col("boll_mid")
    squeeze = width.shift(1).over("symbol") < params["max_band_width"]
    return pl.col("signal_boll_break_up") & squeeze
