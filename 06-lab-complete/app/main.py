"""
Production AI Agent — Part 6 Final Project.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import signal
import sys
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.llm_client import generate_answer
from app.rate_limiter import check_rate_limit
from app.redis_client import close_redis, redis_healthy

STATIC_INDEX = Path(__file__).resolve().parent / "static" / "index.html"


class JsonFormatter(logging.Formatter):
    """Xuất mỗi dòng log của app thành 1 JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "env": settings.environment,
        }
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        return json.dumps(payload, ensure_ascii=False)


def _setup_logger() -> logging.Logger:
    log = logging.getLogger("agent")
    log.setLevel(logging.INFO)
    log.propagate = False
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        log.addHandler(handler)
    return log


logger = _setup_logger()

START_TIME = time.time()
_is_ready = False

_previous_sigterm = signal.getsignal(signal.SIGTERM)


def _on_sigterm(signum, frame):
    global _is_ready
    _is_ready = False
    logger.info("SIGTERM received, initiating graceful shutdown", extra={"extra_fields": {"event": "sigterm"}})
    if callable(_previous_sigterm):
        _previous_sigterm(signum, frame)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    _is_ready = True
    logger.info(
        "Agent startup complete",
        extra={
            "extra_fields": {
                "event": "startup",
                "port": settings.port,
                "llm_mode": "live" if settings.llm_api_key else "mock",
            }
        },
    )
    yield
    _is_ready = False
    logger.info("Agent graceful shutdown complete", extra={"extra_fields": {"event": "shutdown"}})
    close_redis()


app = FastAPI(title="Production AI Agent", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.error(
            "Unhandled server error",
            extra={
                "extra_fields": {
                    "event": "error",
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "ms": elapsed_ms,
                    "error_type": type(exc).__name__,
                }
            },
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "HTTP request completed",
        extra={
            "extra_fields": {
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": elapsed_ms,
            }
        },
    )
    return response


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)


@app.get("/", response_class=HTMLResponse)
def demo_ui():
    """Demo Web UI đơn giản để thử trực tiếp /health, /ready và /ask."""
    return HTMLResponse(content=STATIC_INDEX.read_text(encoding="utf-8"))


@app.get("/health")
def health():
    """Liveness probe — luôn trả 200 khi process còn chạy (không phụ thuộc Redis)."""
    return {
        "status": "ok",
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "llm_mode": "live" if settings.llm_api_key else "mock",
        "model": settings.llm_model if settings.llm_api_key else "mock-llm",
    }


@app.get("/ready")
def ready():
    """Readiness probe — 200 khi sẵn sàng, 503 khi Redis không kết nối được."""
    if not _is_ready or not redis_healthy():
        raise HTTPException(status_code=503, detail="Service not ready: Redis unavailable")
    return {"status": "ready", "redis": "connected"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()

    result = generate_answer(body.question)
    cost_usd = record_cost(result["input_tokens"], result["output_tokens"])

    return {
        "question": body.question,
        "answer": result["answer"],
        "model": result["model"],
        "provider": result["provider"],
        "usage": {
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "cost_usd": round(cost_usd, 6),
        },
    }
