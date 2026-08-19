"""Pullback to MA20: light-volume touch of MA20 inside an uptrend."""
import polars as pl

META = {
    "id": "pullback_ma20",
    "name": "Pullback to MA20",
    "description": "Uptrend intact (MA20 > MA60), price tags MA20 intraday and recovers, on light volume.",
    "tags": ["trend", "pullback"],
    "params": [
        {"id": "max_vol_ratio", "label": "Max volume ratio", "type": "float", "default": 1.0, "min": 0.3, "max": 2.0, "step": 0.1},
    ],
    "order_by": "mom_60d", "descending": True, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = ["signal_pullback_ma20"]
STOP_LOSS = -0.06
MAX_HOLD_DAYS = 15

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return (
        pl.col("signal_pullback_ma20")
        & (pl.col("ma20") > pl.col("ma60"))
        & (pl.col("vol_ratio_20") < params["max_vol_ratio"])
    )
