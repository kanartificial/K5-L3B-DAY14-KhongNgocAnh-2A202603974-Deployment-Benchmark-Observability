"""
Cost guard (tiêu chí 8) — Theo dõi và giới hạn chi phí LLM trên Redis.
"""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_fallback_spend: dict[str, float] = {}


def _daily_key() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"cost:daily:{today}"


def _effective_budget() -> float:
    return min(settings.daily_budget_usd, settings.monthly_budget_usd)


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    key = _daily_key()
    budget = _effective_budget()
    current = 0.0

    if r is not None:
        try:
            raw = r.get(key)
            current = float(raw) if raw is not None else 0.0
        except Exception:
            current = _fallback_spend.get(key, 0.0)
    else:
        current = _fallback_spend.get(key, 0.0)

    if current >= budget:
        raise HTTPException(
            status_code=402,
            detail="Daily/monthly LLM budget exceeded.",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    key = _daily_key()

    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.incrbyfloat(key, cost)
            pipe.expire(key, 86400 * 2)
            pipe.execute()
            return cost
        except Exception:
            pass

    _fallback_spend[key] = _fallback_spend.get(key, 0.0) + cost
    return cost
