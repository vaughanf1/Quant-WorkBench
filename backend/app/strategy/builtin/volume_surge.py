"""Volume surge: heavy accumulation day in a non-broken trend."""
import polars as pl

META = {
    "id": "volume_surge",
    "name": "Volume Surge",
    "description": "Volume more than N times its 20-day average on an up day above MA20.",
    "tags": ["volume"],
    "params": [
        {"id": "vol_mult", "label": "Volume multiple", "type": "float", "default": 2.5, "min": 1.5, "max": 8.0, "step": 0.5},
    ],
    "order_by": "vol_ratio_20", "descending": True, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = ["signal_vol_surge"]
STOP_LOSS = -0.06
MAX_HOLD_DAYS = 10

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return (
        (pl.col("vol_ratio_20") > params["vol_mult"])
        & (pl.col("ret_1d") > 0)
        & (pl.col("close") > pl.col("ma20"))
    )
