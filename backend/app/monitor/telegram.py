"""Telegram delivery, ported from QuantLive's notifier.

Raw Bot API over httpx with HTML parse mode (dodges MarkdownV2 escaping),
~1 msg/sec rate limiting, retry on transport errors, and a clean no-op when
credentials are absent. All notify_* calls are fire-and-forget: they log
failures and never raise into the caller.
"""
from __future__ import annotations

import asyncio
import html
import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

log = logging.getLogger("workbench.telegram")

_SEVERITY_ICON = {"info": "ℹ️", "warn": "⚠️", "critical": "\U0001f6a8"}


class TelegramNotifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self._token = token if token is not None else settings.telegram_bot_token
        self._chat_id = chat_id if chat_id is not None else settings.telegram_chat_id
        self._send_lock = asyncio.Lock()
        self._last_send = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    async def _rate_limit(self) -> None:
        loop = asyncio.get_event_loop()
        async with self._send_lock:
            wait = 1.0 - (loop.time() - self._last_send)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_send = loop.time()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8),
           retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout)))
    async def _post(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json={
                "chat_id": self._chat_id, "text": text,
                "parse_mode": "HTML", "disable_web_page_preview": True})
            resp.raise_for_status()

    async def send(self, text: str) -> bool:
        """Send raw HTML text. Returns False (never raises) on any failure."""
        if not self.enabled:
            return False
        try:
            await self._rate_limit()
            await self._post(text)
            return True
        except Exception as exc:
            log.warning("telegram send failed: %s", exc)
            return False

    # ---- formatted messages -------------------------------------------------
    async def notify_alerts(self, alerts: list[dict]) -> None:
        if not self.enabled or not alerts:
            return
        # batch into one message per rule so a wide strategy hit is one message
        by_rule: dict[str, list[dict]] = {}
        for a in alerts:
            by_rule.setdefault(a.get("rule_name", "alert"), []).append(a)
        for rule_name, group in by_rule.items():
            icon = _SEVERITY_ICON.get(group[0].get("severity", "info"), "")
            lines = [f"{icon} <b>{html.escape(rule_name)}</b> ({group[0].get('date', '')})"]
            for a in group[:20]:
                px = f" @ {a['close']:.2f}" if a.get("close") else ""
                lines.append(f"  <code>{html.escape(a['symbol'])}</code>{px}")
            if len(group) > 20:
                lines.append(f"  …and {len(group) - 20} more")
            await self.send("\n".join(lines))

    async def notify_outcome(self, outcome: dict) -> None:
        icon = {"target_hit": "✅", "stop_hit": "❌", "expired": "⏳"}.get(
            outcome.get("result", ""), "")
        await self.send(
            f"{icon} <b>{html.escape(outcome.get('symbol', ''))}</b> "
            f"{outcome.get('result', '')} ({outcome.get('ret', 0):+.2%}) "
            f"after {outcome.get('days_held', '?')}d "
            f"[{html.escape(str(outcome.get('strategy_id', '')))}]")


_notifier = TelegramNotifier()


def get_notifier() -> TelegramNotifier:
    return _notifier
