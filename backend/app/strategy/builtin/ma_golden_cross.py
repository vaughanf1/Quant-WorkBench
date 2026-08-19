"""Classic golden cross: MA50 crosses above MA200."""
import polars as pl

META = {
    "id": "ma_golden_cross",
    "name": "MA Golden Cross",
    "description": "MA50 crosses above MA200 with price above both.",
    "tags": ["trend"],
    "params": [],
    "order_by": "mom_60d", "descending": True, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = ["signal_golden_cross"]
STOP_LOSS = -0.10
MAX_HOLD_DAYS = 60

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.col("signal_golden_cross") & (pl.col("close") > pl.col("ma50"))
