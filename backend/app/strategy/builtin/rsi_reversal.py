"""RSI reversal: RSI14 crosses back up through 30."""
import polars as pl

META = {
    "id": "rsi_reversal",
    "name": "RSI Reversal",
    "description": "RSI14 crosses up through 30 while price holds above the 60-day low.",
    "tags": ["reversal"],
    "params": [],
    "order_by": "rsi14", "descending": False, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = ["signal_rsi_cross_30_up"]
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 10

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.col("signal_rsi_cross_30_up") & (pl.col("close") > pl.col("low_60d"))
