"""Mean reversion at the lower Bollinger band."""
import polars as pl

META = {
    "id": "mean_reversion_boll",
    "name": "Bollinger Mean Reversion",
    "description": "Close below the lower band with washed-out RSI — bounce candidate back to the mid-band.",
    "tags": ["reversal", "mean-reversion"],
    "params": [
        {"id": "max_rsi", "label": "Max RSI14", "type": "float", "default": 35.0, "min": 15.0, "max": 45.0, "step": 1.0},
    ],
    "order_by": "rsi14", "descending": False, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = []
STOP_LOSS = -0.05
TAKE_PROFIT = 0.06
MAX_HOLD_DAYS = 10

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return (pl.col("close") < pl.col("boll_low")) & (pl.col("rsi14") < params["max_rsi"])
