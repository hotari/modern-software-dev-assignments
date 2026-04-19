from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .routers import action_items, notes


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load .env, create tables; paths from config.get_settings()."""
    load_dotenv()
    init_db()
    yield


app = FastAPI(title="Action Item Extractor", lifespan=lifespan)


@app.exception_handler(sqlite3.Error)
async def _sqlite_error_handler(_request: Request, _exc: sqlite3.Error) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "Database error"})


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    html_path = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
    return html_path.read_text(encoding="utf-8")


app.include_router(notes.router)
app.include_router(action_items.router)

static_dir = Path(__file__).resolve().parents[1] / "frontend"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
