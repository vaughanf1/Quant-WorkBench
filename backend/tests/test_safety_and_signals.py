"""AST sandbox, custom-signal compiler, and outcome resolution tests."""
from __future__ import annotations

import polars as pl
import pytest

from app.monitor.outcomes import evaluate_signal
from app.strategy.custom_signals import build_expressions, validate
from app.strategy.safety import validate_safety


# ---- AST safety -------------------------------------------------------------
GOOD = "import polars as pl\nMETA = {'id': 'x'}\ndef filter(df, params):\n    return pl.col('close') > 1\n"


@pytest.mark.parametrize("snippet,fragment", [
    ("import os", "import"),
    ("from subprocess import run", "import"),
    ("open('/etc/passwd')", "open"),
    ("eval('1+1')", "eval"),
    ("__import__('os')", "__import__"),
    ("x = (1).__class__", "__class__"),
    ("d['__builtins__']", "__builtins__"),
    ("getattr(object, 'x')", "getattr"),
])
def test_safety_rejects(snippet, fragment):
    err = validate_safety(GOOD + snippet + "\n")
    assert err is not None and fragment in err


def test_safety_accepts_clean_strategy():
    assert validate_safety(GOOD) is None


# ---- custom signals -----------------------------------------------------------
def test_validate_rejects_unknown_field():
    sig = {"id": "x", "conditions": [{"left": "close; drop", "op": ">", "right": "1"}]}
    assert "unknown field" in validate(sig)


def test_compile_and_evaluate_shifted_field_comparison():
    sig = {"id": "up_vs_yesterday", "enabled": True, "conditions": [
        {"left": "close", "op": ">", "right": "field:close", "leftDays": 0, "rightDays": 1}]}
    exprs = build_expressions([sig])
    assert list(exprs) == ["csg_up_vs_yesterday"]
    df = pl.DataFrame({
        "symbol": ["A", "A", "A", "B", "B", "B"],
        "close": [10.0, 11.0, 9.0, 5.0, 5.0, 6.0],
    })
    out = df.with_columns(exprs["csg_up_vs_yesterday"].alias("hit"))["hit"].to_list()
    assert out == [False, True, False, False, False, True]


def test_bad_signal_skipped_not_fatal():
    good = {"id": "ok", "enabled": True,
            "conditions": [{"left": "close", "op": ">", "right": "1"}]}
    bad = {"id": "broken", "enabled": True, "conditions": [{"left": "close", "op": "???", "right": "1"}]}
    exprs = build_expressions([good, bad])
    assert "csg_ok" in exprs and "csg_broken" not in exprs


# ---- outcome resolution ----------------------------------------------------------
SIG = {"id": "t", "symbol": "AAA", "entry_date": "2024-01-01", "entry_price": 100.0,
       "strategy_id": "s", "source": "test", "target_pct": 0.10, "stop_pct": -0.05,
       "expiry_days": 3}


def bar(date, o, h, l, c):
    return {"date": date, "open": o, "high": h, "low": l, "close": c}


def test_stop_beats_target_same_bar():
    out = evaluate_signal(SIG, [bar("2024-01-02", 100, 112, 94, 100)])
    assert out["result"] == "stop_hit"
    assert out["exit_price"] == 95.0


def test_target_hit_gap_fills_at_open():
    out = evaluate_signal(SIG, [bar("2024-01-02", 115, 116, 114, 115)])
    assert out["result"] == "target_hit"
    assert out["exit_price"] == 115.0


def test_expiry_at_close():
    bars = [bar(f"2024-01-0{i}", 100, 101, 99, 100) for i in (2, 3, 4)]
    out = evaluate_signal(SIG, bars)
    assert out["result"] == "expired"
    assert out["days_held"] == 3


def test_still_open_returns_none():
    assert evaluate_signal(SIG, [bar("2024-01-02", 100, 101, 99, 100)]) is None
