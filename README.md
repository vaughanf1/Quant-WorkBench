# Quant Workbench

A self-hosted quant research workbench for **US equities**: screening,
backtesting, and post-market monitoring in one amber-on-black terminal panel.

- **Screener** — 15 built-in strategies (one self-contained Polars file each,
  auto-discovered), a no-code custom signal builder (field + operator +
  threshold, compiled to Polars expressions), and an AI strategy builder
  (natural language → AST-validated strategy file).
- **Indicators** — vectorised Polars pipeline over the full universe:
  MA/EMA, MACD, RSI, KDJ, Bollinger, ATR, realised volatility, volume ratios,
  momentum, 52-week extremes, plus atomic cross/breakout signal columns.
  Prices are split- and dividend-adjusted at the source so backtests and
  indicators always agree.
- **Backtest** — per-trade engine with commission + slippage in basis points,
  stop loss, take profit, max holding period, next-day-open fills (no
  lookahead by construction). Streams progress over SSE; a page refresh
  reattaches to the running job. Outputs equity curve, Sharpe, max drawdown,
  per-trade win rate, and full per-trade detail.
- **Monitor** — rule engine (strategy hits, per-symbol signal/price conditions,
  AND/OR logic, cooldown de-duplication, severities) with in-browser SSE
  toasts and Telegram delivery. Fired signals are **tracked to an outcome**
  (target / stop / expiry) and rolled into 7/30-day scorecards per strategy.
- **Data** — OpenBB (yfinance provider, keyless) for EOD bars; SEC EDGAR XBRL
  with **point-in-time resolution** for fundamentals (a value is retrievable
  exactly as it was known on a date — restatements never leak backwards);
  Parquet storage with DuckDB SQL views and Polars lazy scans on top.
  A scheduled post-market pipeline (17:30 New York, weekdays) pulls bars,
  rebuilds the enriched tables, resolves outcomes, and runs monitor rules.

## Run it

```bash
# single container
docker compose up

# or for development (backend :3018 + vite :3011)
./dev.sh
```

Open http://localhost:3018 (or :3011 in dev). First use: go to **Data → Run
now** to bootstrap the S&P 500 universe, pull EOD history, and build the
enriched tables. No API keys are required for market data or fundamentals;
see `.env.example` for optional Telegram and Anthropic keys.

## Stack

Python 3.12 · FastAPI · Polars · DuckDB · Parquet · APScheduler —
React 18 · TypeScript · Vite · Tailwind · TanStack Query.

## Strategy files

One Python file per strategy in `backend/app/strategy/builtin/` (user and
AI-generated files land in `data/strategies/`). The contract:

```python
import polars as pl

META = {
    "id": "trend_breakout",          # == filename stem
    "name": "Trend Breakout",
    "description": "...",
    "tags": ["trend"],
    "params": [{"id": "vol_mult", "label": "Volume multiple", "type": "float",
                "default": 1.5, "min": 1.0, "max": 5.0, "step": 0.1}],
    "order_by": "mom_20d", "descending": True, "limit": 50,
}
EXECUTION_BACKEND = "polars_expr"
STOP_LOSS = -0.08          # backtest defaults
MAX_HOLD_DAYS = 20

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.col("signal_new_high_60d") & (pl.col("vol_ratio_20") > params["vol_mult"])
```

Files are exec'd behind an AST allowlist (Polars-only imports, no I/O, no
dunder escapes) — validated at save time and again by the loader on every
load. A broken file records a load error without breaking the rest.

## Provenance

- Frontend architecture and UX patterns (strategy card grid, custom signal
  builder, SSE job streaming with reconnect-on-refresh, monitor rule engine,
  alert centre, DuckDB-over-Parquet layout, strategy-file contract) are
  adapted from **[shy3130/tickflow-stock-panel](https://github.com/shy3130/tickflow-stock-panel)**
  (MIT), an A-share workbench. All Chinese-market mechanics (price limits,
  limit-up ladders) were deliberately not ported.
- The amber/black terminal aesthetic and the OpenBB data typing come from the
  author's BB-Terminal project.
- The SEC EDGAR XBRL point-in-time parser (with its restatement test suite)
  is ported verbatim from the author's Personal-Hedge-fund project.
- The outcome detector, rolling scorecards, and Telegram notifier are adapted
  from the author's QuantLive project.

## Notes and honest limitations

- The universe bootstrap is a **current S&P 500 snapshot** (Wikipedia), so
  deep backtests carry survivorship bias. The membership CSV format supports
  `date_added`/`date_removed` — drop in a real historical membership file at
  `data/universe/sp500_membership.csv` to fix this properly.
- The PIT fundamentals resolver returns each concept's most recent reported
  period independently; shortly after a company migrates XBRL tags, the
  newest tag may briefly resolve to a quarterly value. This is the original
  (well-tested) behaviour, ported intact.
- The AST allowlist is defence in depth, not a true sandbox — strategy files
  execute in-process. Don't load strategy files you haven't read.
- No AI stock picking, no price prediction. AI is limited to generating
  strategy code from a description, validated before it can run.

MIT — see [LICENSE](LICENSE).
