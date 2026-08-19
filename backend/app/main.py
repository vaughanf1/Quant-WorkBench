"""Quant Workbench — FastAPI app.

Serves the JSON API under /api, the SSE channels, and (in the container /
production build) the compiled frontend from frontend/dist.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.api import stream as stream_api
from app.api.routes import router as api_router
from app.config import paths, settings

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("workbench")

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    stream_api.register_loop(asyncio.get_event_loop())
    from app.jobs.daily_pipeline import start_scheduler
    _scheduler = start_scheduler()
    log.info("scheduler started; data dir: %s", paths.root)
    yield
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="Quant Workbench", lifespan=lifespan)
app.include_router(api_router, prefix="/api")
app.include_router(stream_api.router, prefix="/api")


# ---- AI strategy builder (kept here to keep the router import-light) --------
class GenerateBody(BaseModel):
    description: str


class SaveCodeBody(BaseModel):
    code: str


@app.post("/api/strategies/generate")
def generate_strategy(body: GenerateBody):
    from app.strategy import ai_generator

    if not settings.anthropic_api_key:
        raise HTTPException(400, "ANTHROPIC_API_KEY is not configured")
    return ai_generator.generate(body.description)


@app.post("/api/strategies/save-code")
def save_strategy_code(body: SaveCodeBody):
    from app.strategy import ai_generator

    result = ai_generator.save_generated(body.code)
    if not result.get("valid"):
        raise HTTPException(422, result.get("error") or "invalid strategy code")
    return result


# ---- static frontend ---------------------------------------------------------
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = _DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
