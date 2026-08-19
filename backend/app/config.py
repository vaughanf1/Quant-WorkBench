"""Central configuration: frozen settings + canonical data paths.

Nothing outside this module reads ``os.environ``. Keys are optional at
import time; network paths that need one call ``settings.require(...)``
so offline tests never need credentials.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_REPO_ROOT = Path(os.environ.get("APP_ROOT", Path(__file__).resolve().parents[2]))
_DATA_DIR = Path(os.environ.get("DATA_DIR", _REPO_ROOT / "data"))


@dataclass(frozen=True)
class Paths:
    root: Path = _DATA_DIR
    prices: Path = _DATA_DIR / "prices"                    # raw EOD bars, per-ticker parquet
    enriched: Path = _DATA_DIR / "enriched"                # date=YYYY-MM-DD/part.parquet
    fundamentals: Path = _DATA_DIR / "fundamentals"        # tidy XBRL history, per-ticker parquet
    universe: Path = _DATA_DIR / "universe"                # membership + sectors csv
    backtests: Path = _DATA_DIR / "backtests"
    user_data: Path = _DATA_DIR / "user_data"              # rules, custom signals, alerts
    strategies_custom: Path = _DATA_DIR / "strategies" / "custom"
    strategies_ai: Path = _DATA_DIR / "strategies" / "ai"

    def ensure(self) -> "Paths":
        for p in (self.prices, self.enriched, self.fundamentals, self.universe,
                  self.backtests, self.user_data, self.strategies_custom, self.strategies_ai):
            p.mkdir(parents=True, exist_ok=True)
        return self


@dataclass(frozen=True)
class Settings:
    # SEC EDGAR requires a descriptive User-Agent with a contact address.
    sec_user_agent: str = field(default_factory=lambda: os.environ.get(
        "SEC_USER_AGENT", "quant-workbench research contact@example.com"))
    sec_rate_per_sec: float = field(default_factory=lambda: float(
        os.environ.get("SEC_RATE_PER_SEC", "8")))
    telegram_bot_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    fundamentals_max_age_days: int = field(default_factory=lambda: int(
        os.environ.get("FUNDAMENTALS_MAX_AGE_DAYS", "7")))
    port: int = field(default_factory=lambda: int(os.environ.get("PORT", "3018")))

    def require(self, *names: str) -> None:
        missing = [n for n in names if not getattr(self, n)]
        if missing:
            raise RuntimeError(
                f"Missing required settings: {', '.join(missing)}. "
                "Set them in the environment or a .env file.")


settings = Settings()
paths = Paths().ensure()
