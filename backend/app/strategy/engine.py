"""Strategy auto-discovery engine (pattern from tickflow-stock-panel).

One self-contained Python file per strategy. Contract:

    META = {
        "id": "...",            # must equal the filename stem
        "name": "...",
        "description": "...",
        "tags": ["trend"],
        "params": [{"id","label","type","default","min","max","step"}],
        "order_by": "mom_20d",  # enriched column used to rank hits
        "descending": True,
        "limit": 50,
    }
    EXECUTION_BACKEND = "polars_expr"
    ENTRY_SIGNALS = ["signal_new_high_60d"]   # informational, shown in UI
    STOP_LOSS = -0.08                          # backtest default, negative fraction
    TAKE_PROFIT = 0.15                         # optional, positive fraction
    MAX_HOLD_DAYS = 20                         # backtest default

    def filter(df: pl.DataFrame, params: dict) -> pl.Expr: ...

``filter`` returns a boolean Polars expression evaluated against the enriched
panel (all history rows, per-symbol windows allowed via ``.over("symbol")``).

Files are globbed from the builtin dir plus user dirs; each file is exec'd in
isolation after an AST safety re-check, and a broken file records an error
instead of breaking the rest.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import polars as pl

from app.config import paths
from app.strategy.safety import validate_safety

log = logging.getLogger("workbench.strategy")

BUILTIN_DIR = Path(__file__).parent / "builtin"

_PARAM_TYPES = {"float", "int", "bool", "select"}


def _normalize_params(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for p in raw:
        if isinstance(p, dict) and p.get("id") and p.get("type") in _PARAM_TYPES:
            out.append({"label": p.get("id"), "default": None, **p})
    return out


@dataclass
class StrategyDef:
    id: str
    name: str
    description: str
    tags: list[str]
    params: list[dict]
    order_by: str | None
    descending: bool
    limit: int
    entry_signals: list[str]
    stop_loss: float | None
    take_profit: float | None
    max_hold_days: int | None
    filter_fn: Callable[[pl.DataFrame, dict], pl.Expr]
    source: str  # builtin | custom | ai
    file_path: str

    def defaults(self) -> dict:
        return {p["id"]: p.get("default") for p in self.params}

    def meta_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "tags": self.tags, "params": self.params, "order_by": self.order_by,
            "descending": self.descending, "limit": self.limit,
            "entry_signals": self.entry_signals, "stop_loss": self.stop_loss,
            "take_profit": self.take_profit, "max_hold_days": self.max_hold_days,
            "source": self.source,
        }


class StrategyEngine:
    def __init__(self, dirs: list[Path] | None = None) -> None:
        self._dirs = dirs or [BUILTIN_DIR, paths.strategies_custom, paths.strategies_ai]
        self._lock = threading.RLock()
        self._strategies: dict[str, StrategyDef] = {}
        self._load_errors: list[dict] = []
        self.reload()

    # ---- loading ---------------------------------------------------------
    def reload(self) -> None:
        with self._lock:
            self._strategies.clear()
            self._load_errors.clear()
            for d in self._dirs:
                if not d.exists():
                    continue
                for f in sorted(d.glob("*.py")):
                    if f.name.startswith("_"):
                        continue
                    self._load_file(f)

    def _source_for(self, f: Path) -> str:
        if f.parent == BUILTIN_DIR:
            return "builtin"
        return "ai" if f.parent == paths.strategies_ai else "custom"

    def _load_file(self, f: Path) -> None:
        source = self._source_for(f)
        try:
            code = f.read_text()
            if source != "builtin":
                err = validate_safety(code)
                if err:
                    raise ValueError(f"safety check failed: {err}")
            spec = importlib.util.spec_from_file_location(f"_strategy_{f.stem}", f)
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            sys.modules.pop(f"_strategy_{f.stem}", None)

            meta = getattr(mod, "META", None)
            if not isinstance(meta, dict) or meta.get("id") != f.stem:
                raise ValueError("META missing or META['id'] != filename stem")
            if getattr(mod, "EXECUTION_BACKEND", None) != "polars_expr":
                raise ValueError("EXECUTION_BACKEND must be 'polars_expr'")
            filter_fn = getattr(mod, "filter", None)
            if not callable(filter_fn):
                raise ValueError("strategy must define filter(df, params) -> pl.Expr")

            sdef = StrategyDef(
                id=meta["id"],
                name=meta.get("name", meta["id"]),
                description=meta.get("description", ""),
                tags=list(meta.get("tags", [])),
                params=_normalize_params(meta.get("params")),
                order_by=meta.get("order_by"),
                descending=bool(meta.get("descending", True)),
                limit=int(meta.get("limit", 50)),
                entry_signals=list(getattr(mod, "ENTRY_SIGNALS", [])),
                stop_loss=getattr(mod, "STOP_LOSS", None),
                take_profit=getattr(mod, "TAKE_PROFIT", None),
                max_hold_days=getattr(mod, "MAX_HOLD_DAYS", None),
                filter_fn=filter_fn,
                source=source,
                file_path=str(f),
            )
            if sdef.id in self._strategies:
                prev = self._strategies.pop(sdef.id)
                self._load_errors.append(
                    {"file": str(f), "error": f"duplicate id '{sdef.id}' (also in {prev.file_path})"})
                return
            self._strategies[sdef.id] = sdef
        except Exception as exc:
            log.warning("failed to load strategy %s: %s", f, exc)
            self._load_errors.append({"file": str(f), "error": str(exc)})

    # ---- access ----------------------------------------------------------
    def all(self) -> list[StrategyDef]:
        with self._lock:
            return list(self._strategies.values())

    def get(self, sid: str) -> StrategyDef | None:
        with self._lock:
            return self._strategies.get(sid)

    def load_errors(self) -> list[dict]:
        with self._lock:
            return list(self._load_errors)


_engine: StrategyEngine | None = None
_engine_lock = threading.Lock()


def get_engine() -> StrategyEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = StrategyEngine()
        return _engine
