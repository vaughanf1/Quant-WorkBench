"""No-code custom signals: field + operator + threshold -> Polars expression.

Safety model (ported from tickflow-stock-panel): a field whitelist plus a
fixed operator set — arbitrary expression injection is impossible by
construction. Right-hand sides are either numeric constants or ``field:<col>``
references (whitelist-checked). ``leftDays``/``rightDays`` shift a side N
trading days back, per symbol.

Compiled signals become ``csg_<id>`` boolean columns, deliberately namespaced
apart from builtin ``signal_*`` columns; because screener, backtest and
monitor all resolve signals by column name, injecting the column makes a
custom signal usable everywhere with zero special-casing.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable

import polars as pl

from app.config import paths
from app.indicators.pipeline import ENRICHED_COLUMNS_BY_CATEGORY, ENRICHED_FIELDS, SIGNAL_COLUMNS

log = logging.getLogger("workbench.custom_signals")

ALLOWED_FIELDS: set[str] = set(ENRICHED_FIELDS)
MAX_DAYS = 60
MAX_CONDITIONS = 8
_ID_RE = re.compile(r"^[a-z0-9_]{1,40}$")

_OP_BUILDERS: dict[str, Callable[[pl.Expr, pl.Expr], pl.Expr]] = {
    ">": lambda c, v: c > v,
    ">=": lambda c, v: c >= v,
    "<": lambda c, v: c < v,
    "<=": lambda c, v: c <= v,
    "==": lambda c, v: c == v,
    "!=": lambda c, v: c != v,
}
OPS = list(_OP_BUILDERS)

_STORE_DIR = paths.user_data / "custom_signals"


def column_name(signal_id: str) -> str:
    return f"csg_{signal_id}"


def validate(signal: dict) -> str | None:
    """Return an error message for an invalid signal definition, else None."""
    if not _ID_RE.match(signal.get("id", "")):
        return "id must match ^[a-z0-9_]{1,40}$"
    conds = signal.get("conditions") or []
    if not conds:
        return "at least one condition is required"
    if len(conds) > MAX_CONDITIONS:
        return f"at most {MAX_CONDITIONS} conditions"
    for c in conds:
        if c.get("left") not in ALLOWED_FIELDS:
            return f"unknown field '{c.get('left')}'"
        if c.get("op") not in _OP_BUILDERS:
            return f"unknown operator '{c.get('op')}'"
        right = str(c.get("right", ""))
        if right.startswith("field:"):
            if right[6:] not in ALLOWED_FIELDS:
                return f"unknown field '{right[6:]}'"
        else:
            try:
                float(right)
            except ValueError:
                return f"right side must be a number or field:<name>, got '{right}'"
        for k in ("leftDays", "rightDays"):
            d = int(c.get(k, 0) or 0)
            if d < 0 or d > MAX_DAYS:
                return f"{k} must be 0..{MAX_DAYS}"
    return None


def _col(name: str, days: int) -> pl.Expr:
    expr = pl.col(name)
    return expr.shift(days).over("symbol") if days else expr


def _condition_expr(c: dict) -> pl.Expr:
    left = _col(c["left"], int(c.get("leftDays", 0) or 0))
    right_raw = str(c["right"])
    if right_raw.startswith("field:"):
        right = _col(right_raw[6:], int(c.get("rightDays", 0) or 0))
    else:
        right = pl.lit(float(right_raw))
    return _OP_BUILDERS[c["op"]](left, right)


def build_expressions(signals: list[dict]) -> dict[str, pl.Expr]:
    """Compile signal definitions to {column_name: boolean expr}.

    Per-signal compile failures are logged and skipped, never fatal.
    """
    out: dict[str, pl.Expr] = {}
    for s in signals:
        if not s.get("enabled", True):
            continue
        try:
            exprs = [_condition_expr(c) for c in s["conditions"]]
            combined = exprs[0]
            for e in exprs[1:]:
                combined = combined & e
            out[column_name(s["id"])] = combined.fill_null(False)
        except Exception as exc:
            log.warning("failed to compile custom signal %s: %s", s.get("id"), exc)
    return out


def inject(df: pl.DataFrame | pl.LazyFrame, signals: list[dict] | None = None):
    """Add csg_* columns for all (or the given) enabled custom signals."""
    exprs = build_expressions(signals if signals is not None else load_all())
    if not exprs:
        return df
    return df.with_columns([e.alias(name) for name, e in exprs.items()])


# ---- persistence: one JSON file per signal --------------------------------
def load_all() -> list[dict]:
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for f in sorted(_STORE_DIR.glob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except Exception as exc:
            log.warning("skipping corrupted custom signal %s: %s", f, exc)
    return out


def save(signal: dict) -> str | None:
    err = validate(signal)
    if err:
        return err
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    (_STORE_DIR / f"{signal['id']}.json").write_text(json.dumps(signal, indent=2))
    return None


def delete(signal_id: str) -> bool:
    f = _STORE_DIR / f"{signal_id}.json"
    if f.exists():
        f.unlink()
        return True
    return False


def options() -> dict:
    """Field/operator vocabulary for the UI builder (server-driven)."""
    groups = {**ENRICHED_COLUMNS_BY_CATEGORY, "Signals": SIGNAL_COLUMNS}
    return {"fields": ENRICHED_FIELDS + SIGNAL_COLUMNS, "groups": groups,
            "operators": OPS, "maxDays": MAX_DAYS, "maxConditions": MAX_CONDITIONS}


# signal_* boolean columns are also legal condition fields
ALLOWED_FIELDS |= set(SIGNAL_COLUMNS)
