"""KDJ golden cross from a low level."""
import polars as pl

META = {
    "id": "kdj_golden_low",
    "name": "KDJ Golden Cross (Low)",
    "description": "K crosses above D while K is still below the low-zone ceiling.",
    "tags": ["reversal", "oscillator"],
    "params": [
        {"id": "k_ceiling", "label": "Max K at cross", "type": "float", "default": 40.0, "min": 20.0, "max": 60.0, "step": 5.0},
    ],
    "order_by": "kdj_j", "descending": False, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = ["signal_kdj_golden"]
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 10

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.col("signal_kdj_golden") & (pl.col("kdj_k") < params["k_ceiling"])
