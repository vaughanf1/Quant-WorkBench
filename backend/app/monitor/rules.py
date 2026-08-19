"""Monitor rules: model + JSON-per-rule persistence (tickflow pattern).

Rule shape:
    {
      "id": "uuid", "name": "...", "enabled": true,
      "type": "strategy" | "signal" | "price",
      "scope": "all" | "symbols", "symbols": ["AAPL", ...],
      "strategy_id": "trend_breakout",          # type == strategy
      "logic": "and" | "or",                     # condition folding
      "conditions": [{"left","op","right","leftDays","rightDays"}],  # signal/price
      "severity": "info" | "warn" | "critical",
      "cooldown_seconds": 3600,
      "track_outcome": true                       # record target/stop/expiry result
    }
"""
from __future__ import annotations

import json
import logging
import uuid

from app.config import paths

log = logging.getLogger("workbench.monitor.rules")

RULE_TYPES = {"strategy", "signal", "price"}
SCOPES = {"all", "symbols"}
LOGICS = {"and", "or"}
SEVERITIES = {"info", "warn", "critical"}

_DIR = paths.user_data / "monitor_rules"


def _normalize(rule: dict) -> dict:
    rule.setdefault("id", uuid.uuid4().hex[:12])
    rule.setdefault("enabled", True)
    rule.setdefault("scope", "all")
    rule.setdefault("symbols", [])
    rule.setdefault("logic", "and")
    rule.setdefault("conditions", [])
    rule.setdefault("severity", "info")
    rule.setdefault("cooldown_seconds", 3600)
    rule.setdefault("track_outcome", False)
    return rule


def validate(rule: dict) -> str | None:
    if rule.get("type") not in RULE_TYPES:
        return f"type must be one of {sorted(RULE_TYPES)}"
    if rule.get("scope", "all") not in SCOPES:
        return f"scope must be one of {sorted(SCOPES)}"
    if rule.get("logic", "and") not in LOGICS:
        return f"logic must be one of {sorted(LOGICS)}"
    if rule.get("severity", "info") not in SEVERITIES:
        return f"severity must be one of {sorted(SEVERITIES)}"
    if rule["type"] == "strategy" and not rule.get("strategy_id"):
        return "strategy rules need strategy_id"
    if rule["type"] in ("signal", "price") and not rule.get("conditions"):
        return "signal/price rules need at least one condition"
    if rule.get("scope") == "symbols" and not rule.get("symbols"):
        return "scope 'symbols' needs a symbols list"
    return None


def load_all() -> list[dict]:
    _DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for f in sorted(_DIR.glob("*.json")):
        try:
            out.append(_normalize(json.loads(f.read_text())))
        except Exception as exc:
            log.warning("skipping corrupted rule %s: %s", f, exc)
    return out


def save(rule: dict) -> tuple[dict | None, str | None]:
    rule = _normalize(dict(rule))
    err = validate(rule)
    if err:
        return None, err
    _DIR.mkdir(parents=True, exist_ok=True)
    (_DIR / f"{rule['id']}.json").write_text(json.dumps(rule, indent=2))
    return rule, None


def delete(rule_id: str) -> bool:
    f = _DIR / f"{rule_id}.json"
    if f.exists():
        f.unlink()
        return True
    return False
