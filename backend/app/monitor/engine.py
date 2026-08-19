"""Monitor rule engine: evaluate rules against the enriched panel.

AND/OR condition folding as Polars masks, per-(rule, symbol) cooldown
de-duplication, severity carried through to the emitted alert. Ported from
tickflow-stock-panel's MonitorEngine, trimmed to US-relevant rule types.
"""
from __future__ import annotations

import logging
import time

import polars as pl

from app.monitor import rules as rules_store
from app.strategy import custom_signals, screener
from app.strategy.engine import get_engine

log = logging.getLogger("workbench.monitor")


class MonitorEngine:
    def __init__(self) -> None:
        self._last_fire: dict[tuple[str, str], float] = {}  # (rule_id, symbol) -> monotonic

    # ---- cooldown ----------------------------------------------------------
    def _cooled(self, rule: dict, symbol: str) -> bool:
        key = (rule["id"], symbol)
        now = time.monotonic()
        last = self._last_fire.get(key)
        if last is not None and now - last < rule.get("cooldown_seconds", 3600):
            return False
        self._last_fire[key] = now
        return True

    def reset_cooldowns(self, rule_id: str | None = None) -> None:
        if rule_id is None:
            self._last_fire.clear()
        else:
            self._last_fire = {k: v for k, v in self._last_fire.items() if k[0] != rule_id}

    # ---- evaluation --------------------------------------------------------
    def evaluate(self, df: pl.DataFrame, eval_date: str) -> list[dict]:
        """Evaluate all enabled rules against one enriched day (with history
        rows present for shifted conditions). Returns fired alert dicts."""
        alerts: list[dict] = []
        for rule in rules_store.load_all():
            if not rule.get("enabled", True):
                continue
            try:
                alerts.extend(self._evaluate_rule(rule, df, eval_date))
            except Exception as exc:
                log.warning("rule %s failed: %s", rule.get("id"), exc)
        return alerts

    def _scope(self, rule: dict, df: pl.DataFrame) -> pl.DataFrame:
        if rule.get("scope") == "symbols":
            return df.filter(pl.col("symbol").is_in(rule.get("symbols", [])))
        return df

    def _evaluate_rule(self, rule: dict, df: pl.DataFrame, eval_date: str) -> list[dict]:
        scoped = self._scope(rule, df)
        today = pl.col("date") == pl.lit(eval_date).cast(pl.Date)

        if rule["type"] == "strategy":
            sdef = get_engine().get(rule["strategy_id"])
            if sdef is None:
                return []
            mask = sdef.filter_fn(scoped, sdef.defaults())
            hits = scoped.filter(mask & today)
            label = f"strategy '{sdef.name}' hit"
        else:  # signal / price: condition list with AND/OR folding
            exprs = [custom_signals._condition_expr(c) for c in rule["conditions"]]
            combined = exprs[0]
            for e in exprs[1:]:
                combined = (combined | e) if rule.get("logic") == "or" else (combined & e)
            hits = scoped.filter(combined.fill_null(False) & today)
            label = _conditions_text(rule)

        out = []
        for row in hits.select(["symbol", "close", "ret_1d"]).to_dicts():
            if not self._cooled(rule, row["symbol"]):
                continue
            out.append({
                "rule_id": rule["id"], "rule_name": rule.get("name", rule["id"]),
                "type": rule["type"], "severity": rule.get("severity", "info"),
                "symbol": row["symbol"], "close": row["close"],
                "ret_1d": row.get("ret_1d"), "date": eval_date,
                "message": f"{row['symbol']}: {label}",
                "strategy_id": rule.get("strategy_id"),
                "track_outcome": bool(rule.get("track_outcome")),
            })
        return out


def _conditions_text(rule: dict) -> str:
    joiner = " OR " if rule.get("logic") == "or" else " AND "
    parts = []
    for c in rule.get("conditions", []):
        right = c.get("right", "")
        right = right[6:] if str(right).startswith("field:") else right
        parts.append(f"{c.get('left')} {c.get('op')} {right}")
    return joiner.join(parts)


def run_monitor_cycle() -> list[dict]:
    """One full monitor pass over the latest enriched day."""
    df, eval_date = screener._panel()
    if df is None:
        return []
    return _engine.evaluate(df, eval_date)


_engine = MonitorEngine()


def get_monitor() -> MonitorEngine:
    return _engine
