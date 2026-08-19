"""New-high momentum: 52-week high with strong trailing momentum."""
import polars as pl

META = {
    "id": "new_high_momentum",
    "name": "New-High Momentum",
    "description": "Close at a 52-week high with 20-day momentum above threshold.",
    "tags": ["momentum", "breakout"],
    "params": [
        {"id": "min_mom", "label": "Min 20d momentum", "type": "float", "default": 0.05, "min": 0.0, "max": 0.3, "step": 0.01},
    ],
    "order_by": "mom_20d", "descending": True, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = ["signal_new_high_252d"]
STOP_LOSS = -0.08
MAX_HOLD_DAYS = 30

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.col("signal_new_high_252d") & (pl.col("mom_20d") > params["min_mom"])
