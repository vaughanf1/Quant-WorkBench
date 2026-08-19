"""Vectorised indicator pipeline: OHLCV panel -> enriched panel (Polars).

Everything is computed per-symbol with window expressions over the long
panel, then written to hive-partitioned parquet (enriched/date=.../part.parquet).
Boolean ``signal_*`` columns are the atomic building blocks that strategies,
the screener, the backtester and the monitor all resolve *by column name* —
the pattern from tickflow-stock-panel that lets custom ``csg_*`` signals slot
in with zero special-casing.
"""
from __future__ import annotations

import logging

import polars as pl

log = logging.getLogger("workbench.indicators")

S = pl.col


def _over(expr: pl.Expr) -> pl.Expr:
    return expr.over("symbol")


def _rsi(period: int) -> pl.Expr:
    delta = S("close").diff()
    gain = pl.when(delta > 0).then(delta).otherwise(0.0)
    loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
    avg_gain = gain.ewm_mean(alpha=1 / period, adjust=False)
    avg_loss = loss.ewm_mean(alpha=1 / period, adjust=False)
    return (100 - 100 / (1 + avg_gain / avg_loss)).alias(f"rsi{period}")


def _cross_up(a: str, b: str) -> pl.Expr:
    """True on the bar where a crosses from <= b to > b (per symbol)."""
    return ((S(a) > S(b)) & (S(a).shift(1).over("symbol") <= S(b).shift(1).over("symbol"))).fill_null(False)


def build_enriched(panel: pl.LazyFrame) -> pl.DataFrame:
    """Compute the full enriched panel from a long OHLCV panel.

    ``panel`` must have columns: symbol, date, open, high, low, close, volume.
    """
    lf = panel.sort(["symbol", "date"])

    # --- pass 1: base indicators -----------------------------------------
    lf = lf.with_columns([
        _over(S("close").pct_change()).alias("ret_1d"),
        *[_over(S("close").rolling_mean(n)).alias(f"ma{n}") for n in (5, 10, 20, 50, 60, 200)],
        _over(S("close").ewm_mean(span=12, adjust=False)).alias("ema12"),
        _over(S("close").ewm_mean(span=26, adjust=False)).alias("ema26"),
        _over(S("volume").rolling_mean(20)).alias("vol_ma20"),
        _over(S("high").rolling_max(60)).alias("high_60d"),
        _over(S("low").rolling_min(60)).alias("low_60d"),
        _over(S("high").rolling_max(252)).alias("high_252d"),
        _over(S("low").rolling_min(252)).alias("low_252d"),
        _over(S("close").rolling_std(20)).alias("_std20"),
        _over(_rsi(14)),
        _over(_rsi(6)),
        # true range needs previous close
        _over(S("close").shift(1)).alias("_prev_close"),
        _over(S("high").rolling_max(9)).alias("_hh9"),
        _over(S("low").rolling_min(9)).alias("_ll9"),
    ])

    # --- pass 2: derived from pass 1 ---------------------------------------
    lf = lf.with_columns([
        (S("ema12") - S("ema26")).alias("macd_dif"),
        (S("ma20") + 2 * S("_std20")).alias("boll_up"),
        (S("ma20") - 2 * S("_std20")).alias("boll_low"),
        S("ma20").alias("boll_mid"),
        pl.max_horizontal(S("high") - S("low"),
                          (S("high") - S("_prev_close")).abs(),
                          (S("low") - S("_prev_close")).abs()).alias("_tr"),
        (S("volume") / S("vol_ma20")).alias("vol_ratio_20"),
        _over(S("ret_1d").rolling_std(20)).mul(252 ** 0.5).alias("rvol_20d"),
        _over(S("close").pct_change(5)).alias("mom_5d"),
        _over(S("close").pct_change(20)).alias("mom_20d"),
        _over(S("close").pct_change(60)).alias("mom_60d"),
        (S("close") / S("high_252d") - 1).alias("dist_52w_high"),
        (S("close") / S("low_252d") - 1).alias("dist_52w_low"),
        (S("open") / S("_prev_close") - 1).alias("gap_pct"),
        ((S("close") - S("_ll9")) / (S("_hh9") - S("_ll9")) * 100).alias("_rsv"),
    ])

    lf = lf.with_columns([
        _over(S("macd_dif").ewm_mean(span=9, adjust=False)).alias("macd_dea"),
        _over(S("_tr").ewm_mean(alpha=1 / 14, adjust=False)).alias("atr14"),
        _over(S("_rsv").ewm_mean(alpha=1 / 3, adjust=False)).alias("kdj_k"),
    ])
    lf = lf.with_columns([
        (2 * (S("macd_dif") - S("macd_dea"))).alias("macd_hist"),
        _over(S("kdj_k").ewm_mean(alpha=1 / 3, adjust=False)).alias("kdj_d"),
        (S("atr14") / S("close")).alias("atr_pct"),
    ])
    lf = lf.with_columns((3 * S("kdj_k") - 2 * S("kdj_d")).alias("kdj_j"))

    # --- atomic signals ----------------------------------------------------
    lf = lf.with_columns([
        _cross_up("ma5", "ma20").alias("signal_ma5_cross_ma20"),
        _cross_up("ma50", "ma200").alias("signal_golden_cross"),
        _cross_up("macd_dif", "macd_dea").alias("signal_macd_golden"),
        _cross_up("macd_dea", "macd_dif").alias("signal_macd_dead"),
        _cross_up("close", "boll_up").alias("signal_boll_break_up"),
        _cross_up("kdj_k", "kdj_d").alias("signal_kdj_golden"),
        ((S("rsi14") > 30) & (S("rsi14").shift(1).over("symbol") <= 30)).fill_null(False)
                                                          .alias("signal_rsi_cross_30_up"),
        (S("rsi14") < 30).fill_null(False).alias("signal_rsi_oversold"),
        (S("close") >= S("high_60d")).fill_null(False).alias("signal_new_high_60d"),
        (S("close") >= S("high_252d")).fill_null(False).alias("signal_new_high_252d"),
        (S("close") <= S("low_60d")).fill_null(False).alias("signal_new_low_60d"),
        ((S("vol_ratio_20") > 2.0) & (S("ret_1d") > 0)).fill_null(False).alias("signal_vol_surge"),
        ((S("gap_pct") > 0.02) & (S("close") > S("open"))).fill_null(False).alias("signal_gap_up"),
        ((S("low") <= S("ma20")) & (S("close") > S("ma20"))).fill_null(False)
                                                            .alias("signal_pullback_ma20"),
        ((S("ma5") > S("ma10")) & (S("ma10") > S("ma20")) & (S("ma20") > S("ma60")))
            .fill_null(False).alias("signal_bullish_alignment"),
    ])

    drop = [c for c in ("_std20", "_prev_close", "_tr", "_hh9", "_ll9", "_rsv")]
    return lf.drop(drop).collect()


# Field catalogue served to the custom-signal builder UI.
ENRICHED_COLUMNS_BY_CATEGORY: dict[str, list[str]] = {
    "Price": ["open", "high", "low", "close", "volume", "ret_1d", "gap_pct"],
    "Moving averages": ["ma5", "ma10", "ma20", "ma50", "ma60", "ma200", "ema12", "ema26"],
    "MACD": ["macd_dif", "macd_dea", "macd_hist"],
    "RSI": ["rsi6", "rsi14"],
    "KDJ": ["kdj_k", "kdj_d", "kdj_j"],
    "Bollinger": ["boll_up", "boll_mid", "boll_low"],
    "Volatility": ["atr14", "atr_pct", "rvol_20d"],
    "Volume": ["vol_ma20", "vol_ratio_20"],
    "Momentum": ["mom_5d", "mom_20d", "mom_60d"],
    "Extremes": ["high_60d", "low_60d", "high_252d", "low_252d",
                 "dist_52w_high", "dist_52w_low"],
}
ENRICHED_FIELDS: list[str] = [c for cols in ENRICHED_COLUMNS_BY_CATEGORY.values() for c in cols]
SIGNAL_COLUMNS: list[str] = [
    "signal_ma5_cross_ma20", "signal_golden_cross", "signal_macd_golden", "signal_macd_dead",
    "signal_boll_break_up", "signal_kdj_golden", "signal_rsi_cross_30_up", "signal_rsi_oversold",
    "signal_new_high_60d", "signal_new_high_252d", "signal_new_low_60d", "signal_vol_surge",
    "signal_gap_up", "signal_pullback_ma20", "signal_bullish_alignment",
]
