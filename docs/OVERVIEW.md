# Quant Workbench — How It Works

This document explains the whole system: what it does, how data flows through
it, what each component is for, and where everything lives in the code. It is
written to be self-contained — you should be able to understand the project
from this file alone.

---

## 1. What this project is

Quant Workbench is a **self-hosted research tool for US stocks** (the S&P 500).
It answers three questions a trader or researcher asks every day:

1. **"Which stocks match my setup right now?"** → the **Screener**
2. **"If I had traded this setup in the past, would it have made money?"** → the **Backtest**
3. **"Tell me when my setup fires, and track whether it worked."** → the **Monitor**

Everything runs on your own machine in one web app. There is no cloud service,
no account, and no API keys needed for the core features. Data lives in plain
files on disk.

A key design rule: **there is no AI stock picking and no price prediction
anywhere.** Every signal is a transparent, human-readable rule (e.g. "price
crossed above its 50-day average"). The only AI feature is an optional helper
that turns a plain-English description into a rule file — and that file is
checked and shown to you before it can run.

---

## 2. The big picture — how data flows

```
                       (every weekday at 5:30pm New York time,
                        or when you press "Run now")
┌─────────────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────────┐
│  Internet    │   │  Raw prices   │   │  "Enriched"    │   │  Your rules   │
│              │   │  on disk      │   │  table on disk │   │               │
│ Yahoo Finance├──▶│ one file per  ├──▶│ prices + ~40   ├──▶│ screener hits │
│ (via OpenBB) │   │ stock, daily  │   │ indicators per │   │ backtests     │
│ SEC EDGAR    │   │ open/high/    │   │ stock per day  │   │ alerts        │
│ (fundamentals)│  │ low/close/vol │   │                │   │ outcome logs  │
└─────────────┘   └──────────────┘   └───────────────┘   └──────────────┘
```

**Step 1 — Pull prices.** Once a day, after the US market closes, the app
downloads that day's price bar (open, high, low, close, volume) for every
stock in the S&P 500, via the OpenBB library using Yahoo Finance data. Prices
are *adjusted* for stock splits and dividends, which matters: it means a 10-for-1
split doesn't look like a 90% crash.

**Step 2 — Compute indicators.** The app then recomputes the **enriched
table**: for every stock, for every day, it calculates ~40 standard technical
indicators (moving averages, RSI, MACD, Bollinger bands, volatility, volume
ratios, distance from 52-week high, etc.) plus a set of true/false **signal
columns** like "did the 50-day average cross above the 200-day average today?".
This takes about 3 seconds for the whole market because it uses Polars, a very
fast data engine.

**Step 3 — Everything reads that one table.** The screener, the backtester,
and the monitor all work by asking true/false questions of the same enriched
table. That's the core architectural idea: **compute the numbers once, then
every feature is just a filter over them.** It also guarantees the backtest
and the live screener can never disagree about what an indicator's value was.

---

## 3. The four screens

### Dashboard
A read-only summary of the latest market day: how many stocks rose vs fell
(the "breadth tape" at the top), which sectors led, biggest movers, how many
stocks each strategy is flagging today, recent alerts, and the track record
of past signals.

### Screener
A grid of **strategy cards** — each card is one trading setup, e.g. "Pullback
to MA20" (a stock in an uptrend that dipped to its 20-day average and
bounced). The number on the card is how many stocks match today. Click a card
and you get the ranked list of matching stocks.

There are 15 built-in strategies. You can add your own two ways:

- **Custom signal builder (no code):** you pick a field, a comparison, and a
  value from dropdowns — e.g. `rsi14 < 30 AND close > ma200`. The app compiles
  that into a rule. You literally cannot inject anything dangerous because
  only whitelisted field names and six comparison operators exist.
- **AI strategy builder (optional, needs an Anthropic API key):** describe a
  setup in English; the app generates the strategy file, *validates it* (see
  §6), shows you the code, and only saves it if you approve.

### Backtest
Pick a strategy, a date range, and trading assumptions, and the app replays
history: every time the strategy fired on a stock, it simulates buying at
**the next morning's opening price** (never the same day — that would be
cheating, since you couldn't have known the signal before the close), then
holds until one of these happens, checked in this order each day:

1. **Stop loss** — price fell X% below entry → sell (limits damage)
2. **Take profit** — price rose X% above entry → sell (optional)
3. **Max holding period** — N days passed → sell at the close

Each simulated trade is charged **commission** and **slippage** (a realistic
penalty for not getting the exact printed price), both in basis points
(1 bp = 0.01%). The output is an equity curve (your $100k over time), summary
statistics (total return, Sharpe ratio = return per unit of risk, maximum
drawdown = worst peak-to-trough loss, win rate), and the full list of every
individual trade with its entry, exit, and reason.

While a backtest runs, progress streams to the browser live; if you refresh
the page it *reattaches to the same run* instead of restarting it (the server
recognises identical requests by hashing their parameters).

### Monitor
Standing rules that are checked automatically after every daily data update.
A rule is either "alert me when strategy X fires" or a hand-built condition
list ("RSI below 35 **or** above 70, on AAPL/NVDA/TSLA only"). Rules have:

- **severity** (info / warn / critical) — colours the alert,
- **cooldown** — the same rule won't re-fire for the same stock within N
  seconds, so you don't get spammed,
- **track outcome** — the important one, explained next.

**Outcome tracking:** most alert systems fire and forget. Here, when a
tracked rule fires, the app records an open "signal ticket" with the entry
price, a target (e.g. +10%), a stop (e.g. −5%), and an expiry (e.g. 20 days).
Every day afterwards it checks the actual price bars: did the stock hit the
target first, the stop first, or run out of time? The result is written down
permanently, and the **scorecards** aggregate them: "over the last 30 days,
Pullback-to-MA20 signals had a 58% win rate." So you learn whether your
alerts are actually worth acting on.

Alerts appear as pop-up toasts in the browser and, if configured, as Telegram
messages on your phone.

---

## 4. The data layer in more detail

- **Storage is just files.** Prices: one Parquet file per stock
  (`data/prices/AAPL.parquet`). Indicators: one folder per day
  (`data/enriched/date=2026-08-18/`). Your rules, custom signals, and alert
  history: small JSON/JSONL files under `data/user_data/`. Parquet is a
  compressed columnar format — think "a spreadsheet optimised for analytics".
  You can back up or inspect everything with normal tools.
- **DuckDB** is an embedded SQL engine that treats those Parquet files as
  database tables, so the app (or you) can run SQL over them without a
  database server.
- **Fundamentals (company financials)** come from **SEC EDGAR**, the US
  regulator's free filing database, parsed from XBRL (the machine-readable
  format of 10-K/10-Q reports). The parser enforces a strict
  **point-in-time** rule: when you ask "what was Apple's revenue *as known on*
  June 2020", you get the number that had actually been *filed* by June 2020 —
  never a figure that was restated later. This prevents a subtle and very
  common form of backtest cheating where future corrections leak into the
  past. This module was ported intact from an earlier project, with tests
  that prove the restatement behaviour in both directions.
- **Universe:** the S&P 500 member list is bootstrapped from Wikipedia
  (current snapshot). Honest limitation: because it's today's list, deep
  backtests have **survivorship bias** — stocks that were removed from the
  index (often after doing badly) aren't in the sample, which flatters
  results. The file format supports proper add/remove dates, so a real
  historical membership file can be dropped in later.

---

## 5. What a strategy actually is

One small Python file. Example (slightly trimmed):

```python
import polars as pl

META = {
    "id": "trend_breakout",
    "name": "Trend Breakout",
    "description": "Close at a 60-day high, above MA60, with volume expansion.",
    "params": [{"id": "vol_mult", "type": "float", "default": 1.5}],
    "order_by": "mom_20d",       # rank hits by 20-day momentum
}
EXECUTION_BACKEND = "polars_expr"
STOP_LOSS = -0.08                 # default backtest exit: -8%
MAX_HOLD_DAYS = 20

def filter(df, params):
    return (
        pl.col("signal_new_high_60d")            # made a new 60-day high today
        & (pl.col("close") > pl.col("ma60"))     # and is above its 60-day average
        & (pl.col("vol_ratio_20") > params["vol_mult"])  # on heavy volume
    )
```

The `filter` function returns a true/false test that is applied to every
stock on every day. The same file drives all three features: the screener
runs it on today's data, the backtester runs it on all of history, and the
monitor runs it after each daily update. Files are **auto-discovered** — drop
a new file in the folder and it appears as a card; a broken file shows an
error on that one card without affecting the others.

---

## 6. Safety of user/AI-generated strategy code

Strategy files are Python, and Python can normally do anything (read files,
access the network). Before any user- or AI-written strategy file is saved or
loaded, the app parses it into a syntax tree and checks it against an
allowlist: only `polars`/`numpy`/`math`/`datetime` imports, no `open`, `eval`,
`exec`, no network, no "dunder" escape hatches like `__class__`. The check
runs twice — once when the file is saved through the app, and again every
time it is loaded from disk, so hand-editing a file can't skip it. This is
strong defence-in-depth but not a perfect sandbox, hence the rule in the
README: don't load strategy files you haven't read.

---

## 7. Technology glossary

| Term | What it means here |
| --- | --- |
| **FastAPI** | The Python web server that exposes the app's API and serves the UI |
| **Polars** | A very fast dataframe (table-math) library; all indicator math |
| **DuckDB** | Embedded SQL engine reading the Parquet files directly |
| **Parquet** | Compressed column-oriented file format for the data |
| **React / TypeScript / Tailwind** | The browser UI |
| **SSE (server-sent events)** | One-way live stream from server to browser; used for backtest progress and alert toasts |
| **OpenBB** | Open-source market-data toolkit; used with its free Yahoo Finance provider |
| **XBRL** | The machine-readable format of SEC financial filings |
| **APScheduler** | Runs the 17:30 New York daily pipeline job inside the server |
| **basis point (bp)** | 0.01%. "5 bps slippage" = each trade assumed 0.05% worse than the printed price |
| **Sharpe ratio** | Return divided by volatility; >1 is generally considered good |
| **Max drawdown** | The worst peak-to-trough fall of the equity curve |
| **Profit factor** | Gross winnings ÷ gross losses; >1 means profitable |

---

## 8. Where everything lives

```
backend/app/
  config.py                 settings + data paths (env-driven, no secrets in code)
  data/
    prices.py               OpenBB price download + incremental per-stock cache
    universe.py             S&P 500 member list + sectors (Wikipedia bootstrap)
    sec_edgar.py, xbrl_parser.py   SEC fundamentals, point-in-time logic
    store.py                DuckDB views + Polars scans over the Parquet files
  indicators/pipeline.py    the ~40 indicators + signal columns (Polars)
  strategy/
    engine.py               auto-discovers strategy files, isolates errors
    builtin/*.py            the 15 built-in strategies (one file each)
    custom_signals.py       no-code builder → whitelisted Polars expressions
    ai_generator.py         English → strategy file, validated before save
    safety.py               the AST allowlist check
    screener.py             runs a strategy over the enriched table
  backtest/
    engine.py               the day-by-day trade simulator
    metrics.py              Sharpe, drawdown, win rate, etc.
    jobs.py                 background runs, progress streaming, reattach logic
  monitor/
    rules.py, engine.py     rule storage + evaluation (AND/OR, cooldown)
    outcomes.py             the "did the signal work?" tracker
    performance.py          7/30-day scorecards
    telegram.py             phone notifications
    alert_store.py          permanent alert log (append-only file)
  jobs/daily_pipeline.py    the scheduled post-market job tying it all together
  api/routes.py, stream.py  the HTTP API + live event stream
  main.py                   app entry point; also serves the built UI

frontend/src/
  pages/                    Dashboard, Screener, Backtest, Monitor, Data
  lib/api.ts                typed client for every backend endpoint
  lib/backtestTask.ts       the refresh-surviving backtest progress stream
  lib/alertStream.ts        the live alert toast channel
  index.css, tailwind.config.js   the amber-on-black terminal theme

data/                       everything the app learns/stores (never in git)
```

## 9. Credits

The frontend architecture and several backend patterns (strategy-file
contract, signal-column design, streaming-with-reattach, rule engine) are
adapted from [shy3130/tickflow-stock-panel](https://github.com/shy3130/tickflow-stock-panel)
(MIT), originally a Chinese-market tool; all China-specific mechanics were
deliberately dropped. The point-in-time SEC parser, outcome tracker,
scorecards, Telegram sender, and the terminal aesthetic were ported from the
author's own earlier projects.
