"""Short-term golden cross with long-term trend filter."""
import polars as pl

META = {
    "id": "ma5_cross_ma20",
    "name": "MA5 x MA20 Cross",
    "description": "MA5 crosses above MA20 while price sits above MA200 (trend filter).",
    "tags": ["trend"],
    "params": [
        {"id": "require_ma200", "label": "Require above MA200", "type": "bool", "default": True},
    ],
    "order_by": "mom_5d", "descending": True, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = ["signal_ma5_cross_ma20"]
STOP_LOSS = -0.06
MAX_HOLD_DAYS = 15

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    base = pl.col("signal_ma5_cross_ma20")
    if params.get("require_ma200"):
        base = base & (pl.col("close") > pl.col("ma200"))
    return base
