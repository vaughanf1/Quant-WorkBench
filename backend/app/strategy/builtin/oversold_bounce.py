"""Oversold bounce: deeply oversold RSI turning up above MA5."""
import polars as pl

META = {
    "id": "oversold_bounce",
    "name": "Oversold Bounce",
    "description": "RSI14 was below the oversold floor yesterday; today closes up and above MA5.",
    "tags": ["reversal"],
    "params": [
        {"id": "rsi_floor", "label": "RSI oversold floor", "type": "float", "default": 30.0, "min": 10.0, "max": 40.0, "step": 1.0},
    ],
    "order_by": "dist_52w_low", "descending": False, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = ["signal_rsi_oversold"]
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 10

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return (
        (pl.col("rsi14").shift(1).over("symbol") < params["rsi_floor"])
        & (pl.col("ret_1d") > 0)
        & (pl.col("close") > pl.col("ma5"))
    )
