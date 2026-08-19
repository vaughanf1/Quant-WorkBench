"""MACD golden cross confirmed by volume."""
import polars as pl

META = {
    "id": "macd_cross_volume",
    "name": "MACD Cross + Volume",
    "description": "MACD DIF crosses above DEA below the zero line, with volume confirmation.",
    "tags": ["momentum"],
    "params": [
        {"id": "vol_mult", "label": "Volume multiple", "type": "float", "default": 1.2, "min": 1.0, "max": 3.0, "step": 0.1},
        {"id": "below_zero", "label": "Require cross below zero", "type": "bool", "default": True},
    ],
    "order_by": "macd_hist", "descending": True, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = ["signal_macd_golden"]
STOP_LOSS = -0.07
MAX_HOLD_DAYS = 15

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    base = pl.col("signal_macd_golden") & (pl.col("vol_ratio_20") > params["vol_mult"])
    if params.get("below_zero"):
        base = base & (pl.col("macd_dif") < 0)
    return base
