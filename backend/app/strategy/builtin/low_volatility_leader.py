"""Low-volatility leader: quiet names in long uptrends."""
import polars as pl

META = {
    "id": "low_volatility_leader",
    "name": "Low-Volatility Leader",
    "description": "Realised vol in the bottom tercile of the day's cross-section, above MA200, positive 60d momentum.",
    "tags": ["quality", "low-vol"],
    "params": [
        {"id": "vol_quantile", "label": "Vol quantile ceiling", "type": "float", "default": 0.3, "min": 0.1, "max": 0.5, "step": 0.05},
    ],
    "order_by": "mom_60d", "descending": True, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
ENTRY_SIGNALS = []
STOP_LOSS = -0.10
MAX_HOLD_DAYS = 60

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return (
        (pl.col("rvol_20d") < pl.col("rvol_20d").quantile(params["vol_quantile"]).over("date"))
        & (pl.col("close") > pl.col("ma200"))
        & (pl.col("mom_60d") > 0)
    )
