"""Global SSE push channel: /api/stream.

Per-connection subscriber queues (tickflow pattern) so multi-tab clients each
receive every event. Currently carries ``alerts`` and ``pipeline`` events.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

log = logging.getLogger("workbench.stream")

router = APIRouter()

_subscribers: set[asyncio.Queue] = set()
_sub_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None


def register_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


async def publish(event: str, data: dict | list) -> None:
    with _sub_lock:
        queues = list(_subscribers)
    for q in queues:
        try:
            q.put_nowait({"event": event, "data": json.dumps(data)})
        except asyncio.QueueFull:
            pass


def publish_alerts_threadsafe(alerts: list[dict]) -> None:
    """Publish from worker threads (the pipeline runs off the event loop)."""
    if _loop is None or not alerts:
        return
    asyncio.run_coroutine_threadsafe(publish("alerts", alerts), _loop)


def publish_threadsafe(event: str, data: dict | list) -> None:
    if _loop is None:
        return
    asyncio.run_coroutine_threadsafe(publish(event, data), _loop)


@router.get("/stream")
async def stream(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    with _sub_lock:
        _subscribers.add(q)

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15)
                    yield item
                except asyncio.TimeoutError:
                    continue  # EventSourceResponse pings keep the pipe alive
        finally:
            with _sub_lock:
                _subscribers.discard(q)

    return EventSourceResponse(gen())
