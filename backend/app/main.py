"""
FastAPI application entry point.

Exposes existing institutional / session KB services over REST.
No retrieval business logic lives here.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is on sys.path so ``src`` and ``config`` import cleanly
# when uvicorn is started from any working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.api import (  # noqa: E402
    chat,
    conversations,
    health,
    providers,
    search,
    session,
    settings,
    upload,
)
from backend.app.services.kb_service import get_kb_service  # noqa: E402
from backend.app.services.llm.lmstudio_health import get_lmstudio_health_monitor  # noqa: E402
from config.settings import get_settings  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

# Any Vercel deployment / preview hostname (Origin has no trailing slash).
_VERCEL_ORIGIN_REGEX = r"https://[a-z0-9-]+\.vercel\.app"
# Local Next.js (http only).
_LOCAL_ORIGIN_REGEX = r"http://(localhost|127\.0\.0\.1):\d+"
_CORS_ORIGIN_REGEX = rf"({_VERCEL_ORIGIN_REGEX})|({_LOCAL_ORIGIN_REGEX})"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load / build institutional index once at startup; start health monitor."""
    logger.info("Starting Student Support API")
    cfg = get_settings()
    logger.info(
        "CORS allow_origins=%s | allow_origin_regex=%s",
        cfg.cors_origins,
        _CORS_ORIGIN_REGEX,
    )
    service = get_kb_service()
    service.bootstrap_institutional()
    monitor = get_lmstudio_health_monitor()
    monitor.start()
    try:
        yield
    finally:
        monitor.stop()
        logger.info("Shutting down Student Support API")


app = FastAPI(
    title="Student Support Services AI Chatbot API",
    description=(
        "Hybrid RAG student support API: institutional FAQ, uploaded notes, "
        "general educational answers, multi-turn memory, and safety escalation."
    ),
    version="0.11.1",
    lifespan=lifespan,
)

_settings = get_settings()
# Explicit list (from CORS_ORIGINS) + regex so Vercel preview URLs keep working
# even when the env var has a stale hostname, trailing slash, or quotes.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_origin_regex=_CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(health.router)
app.include_router(session.router)
app.include_router(upload.router)
app.include_router(search.router)
app.include_router(conversations.router)
app.include_router(chat.router)
app.include_router(settings.router)
app.include_router(providers.router)


@app.get("/")
def root() -> dict[str, str]:
    """Simple root probe."""
    return {
        "service": "student-support-chatbot-api",
        "docs": "/docs",
        "health": "/health",
        "providers": "/api/providers/status",
    }
