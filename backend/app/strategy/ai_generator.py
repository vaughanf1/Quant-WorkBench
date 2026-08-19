"""AI strategy generation: natural language -> validated strategy file.

The only AI feature in the app, by design. Generated code must pass the AST
safety check plus structural validation (META shape, one filter entrypoint,
polars-only imports) before it can be saved into data/strategies/ai/, and the
loader re-validates on every exec. One-shot self-repair on structural errors.
"""
from __future__ import annotations

import ast
import logging
import re

from app.config import paths, settings
from app.strategy.engine import get_engine
from app.strategy.safety import validate_safety
from app.indicators.pipeline import ENRICHED_FIELDS, SIGNAL_COLUMNS

log = logging.getLogger("workbench.ai")

_GUIDE = f"""You write one self-contained Python strategy file for a US equities screener.
Contract (follow EXACTLY):
- imports: ONLY `import polars as pl` (numpy/datetime/math also allowed if needed)
- META dict with keys: id (snake_case, will become the filename), name, description,
  tags (list), params (list of {{id,label,type,default,min,max,step}} with type in
  float|int|bool), order_by (one enriched column), descending (bool), limit (int)
- EXECUTION_BACKEND = "polars_expr"
- optional: ENTRY_SIGNALS (list of signal column names), STOP_LOSS (negative float),
  TAKE_PROFIT (positive float), MAX_HOLD_DAYS (int)
- def filter(df: pl.DataFrame, params: dict) -> pl.Expr  — returns a BOOLEAN expression.
  The frame is a long panel (symbol, date, ...); use .shift(n).over("symbol") for
  "n days ago"; never call collect/read/write; no file or network access.
Available numeric columns: {", ".join(ENRICHED_FIELDS)}
Available boolean signal columns: {", ".join(SIGNAL_COLUMNS)}
Respond with ONLY the Python code, no fences, no commentary."""

_META_KEYS = {"id", "name", "description"}


def validate_code(code: str) -> dict:
    """Full validation pipeline. Returns {code, meta, valid, error}."""
    code = _strip_fences(code)
    err = validate_safety(code)
    if err:
        return {"code": code, "meta": None, "valid": False, "error": err}
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"code": code, "meta": None, "valid": False, "error": f"syntax: {exc}"}

    meta = _extract_meta(tree)
    if not isinstance(meta, dict) or not _META_KEYS <= set(meta):
        return {"code": code, "meta": meta, "valid": False,
                "error": "META must be a literal dict with id/name/description"}
    if not re.match(r"^[a-z0-9_]{1,40}$", str(meta.get("id", ""))):
        return {"code": code, "meta": meta, "valid": False,
                "error": "META['id'] must be snake_case [a-z0-9_]"}
    has_filter = any(isinstance(n, ast.FunctionDef) and n.name == "filter"
                     for n in ast.walk(tree))
    if not has_filter:
        return {"code": code, "meta": meta, "valid": False,
                "error": "missing def filter(df, params)"}
    backend = _module_constant(tree, "EXECUTION_BACKEND")
    if backend != "polars_expr":
        return {"code": code, "meta": meta, "valid": False,
                "error": "EXECUTION_BACKEND must be the string 'polars_expr'"}
    return {"code": code, "meta": meta, "valid": True, "error": None}


def _strip_fences(code: str) -> str:
    m = re.search(r"```(?:python)?\n(.*?)```", code, re.DOTALL)
    return (m.group(1) if m else code).strip() + "\n"


def _extract_meta(tree: ast.Module) -> dict | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "META":
                    try:
                        return ast.literal_eval(node.value)
                    except (ValueError, SyntaxError):
                        return None
    return None


def _module_constant(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name \
                        and isinstance(node.value, ast.Constant):
                    return node.value.value
    return None


def _call_llm(messages: list[dict]) -> str:
    settings.require("anthropic_api_key")
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(model="claude-sonnet-5", max_tokens=4000,
                                  system=_GUIDE, messages=messages)
    return "".join(b.text for b in resp.content if b.type == "text")


def generate(description: str) -> dict:
    """Generate, validate, and (if valid) one-shot self-repair a strategy."""
    code = _call_llm([{"role": "user", "content": description}])
    result = validate_code(code)
    if not result["valid"]:
        repaired = _call_llm([
            {"role": "user", "content": description},
            {"role": "assistant", "content": result["code"]},
            {"role": "user", "content":
                f"That file failed validation: {result['error']}. "
                "Return the corrected full file, code only."}])
        result = validate_code(repaired)
    return result


def save_generated(code: str) -> dict:
    """Validate and persist to data/strategies/ai/<id>.py, then hot-reload."""
    result = validate_code(code)
    if not result["valid"]:
        return result
    sid = result["meta"]["id"]
    (paths.strategies_ai / f"{sid}.py").write_text(result["code"])
    get_engine().reload()
    loaded = get_engine().get(sid)
    if loaded is None:
        errs = [e for e in get_engine().load_errors() if sid in e["file"]]
        return {**result, "valid": False,
                "error": errs[0]["error"] if errs else "failed to load after save"}
    return {**result, "saved": True, "strategy": loaded.meta_dict()}
