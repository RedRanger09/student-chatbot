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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load / build institutional index once at startup; start health monitor."""
    logger.info("Starting Student Support API")
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
    version="0.11.0",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
