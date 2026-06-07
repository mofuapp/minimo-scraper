"""Minimo scraper HTTP API for PWA clients."""
import asyncio
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

_APP_ROOT = Path(__file__).resolve().parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from scraper import scrape_minimo

app = FastAPI(title="Minimo Scraper API", version="1.0.0")

API_KEY = os.environ.get("MINIMO_API_KEY", "")
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "MINIMO_CORS_ORIGINS",
        "https://mofuapp.github.io,http://localhost:8080,http://127.0.0.1:8080",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScrapeRequest(BaseModel):
    categories: Optional[list[str]] = None
    max_likes: int = Field(default=5, ge=1, le=100)
    max_pages: int = Field(default=20, ge=1, le=20)
    fetch_phone: bool = True
    nationwide: bool = False
    prefectures: list[str] = Field(default_factory=list)
    existing_urls: list[str] = Field(default_factory=list)
    filter_updated: bool = False
    update_min_date: Optional[str] = None
    update_max_date: Optional[str] = None


def _check_auth(api_key: Optional[str]) -> None:
    if API_KEY and api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/health")
def health():
    return {"ok": True, "service": "minimo-scraper-api"}


@app.post("/scrape")
async def scrape_endpoint(
    req: ScrapeRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    _check_auth(x_api_key)

    if not req.nationwide and not req.prefectures:
        raise HTTPException(status_code=400, detail="prefectures required unless nationwide")

    min_updated = _parse_date(req.update_min_date) if req.filter_updated else None
    max_updated = _parse_date(req.update_max_date) if req.filter_updated else None
    categories = req.categories if req.categories else None
    existing_urls = set(req.existing_urls)

    async def generate():
        progress_events: list[dict] = []
        result_holder: dict = {"results": None, "error": None}

        def progress(message: str, percent: int = 0):
            progress_events.append({"message": message, "percent": percent})

        async def run_scrape():
            try:
                result_holder["results"] = await scrape_minimo(
                    categories=categories,
                    max_likes=req.max_likes,
                    existing_urls=existing_urls,
                    progress_callback=progress,
                    prefectures=req.prefectures,
                    max_pages=req.max_pages,
                    nationwide=req.nationwide,
                    fetch_phone=req.fetch_phone,
                    min_updated_date=min_updated,
                    max_updated_date=max_updated,
                )
            except Exception as exc:
                result_holder["error"] = str(exc)

        task = asyncio.create_task(run_scrape())
        yield _sse("start", {"ok": True})

        while not task.done() or progress_events:
            while progress_events:
                yield _sse("progress", progress_events.pop(0))
            if not task.done():
                await asyncio.sleep(0.2)

        if result_holder["error"]:
            yield _sse("error", {"message": result_holder["error"]})
            return

        results = result_holder["results"] or []
        yield _sse("done", {"results": results, "count": len(results)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
