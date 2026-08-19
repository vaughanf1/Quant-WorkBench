"""Gap-up strength: opening gap that holds into the close."""
import polars as pl

META = {
    "id": "gap_up_strength",
    "name": "Gap-Up Strength",
    "description": "Opens up more than the gap threshold and closes above the open (gap-and-go).",
    "tags": ["momentum", "gap"],
    "params": [
        {"id": "min_gap", "label": "Min gap pct", "type": "float", "default": 0.03, "min": 0.01, "max": 0.10, "step": 0.005},
    ],
    "order_by": "gap_pct", "descending": True, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = ["signal_gap_up"]
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 5

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return (pl.col("gap_pct") > params["min_gap"]) & (pl.col("close") > pl.col("open"))
