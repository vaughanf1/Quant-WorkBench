"""Bullish MA alignment appearing fresh (was not aligned yesterday)."""
import polars as pl

META = {
    "id": "bullish_alignment",
    "name": "Bullish Alignment",
    "description": "MA5 > MA10 > MA20 > MA60 stack forming today for the first time.",
    "tags": ["trend"],
    "params": [],
    "order_by": "mom_20d", "descending": True, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = ["signal_bullish_alignment"]
STOP_LOSS = -0.08
MAX_HOLD_DAYS = 30

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    aligned = pl.col("signal_bullish_alignment")
    return aligned & ~aligned.shift(1).over("symbol").fill_null(False)
