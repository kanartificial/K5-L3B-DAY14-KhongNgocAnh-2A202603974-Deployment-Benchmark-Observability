"""
Rate limiting (tiêu chí 7) — Sliding window 60s lưu trên Redis Sorted Set.
"""
import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60
_fallback_windows: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str) -> None:
    """Kiểm tra giới hạn request/phút theo API key (stateless với Redis)."""
    limit = settings.rate_limit_per_minute
    now = time.time()
    window_start = now - WINDOW_SECONDS
    redis_key = f"ratelimit:{key}"

    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zcard(redis_key)
            _, current_count = pipe.execute()

            if current_count >= limit:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Try again later.",
                    headers={"Retry-After": str(WINDOW_SECONDS)},
                )

            member = f"{now}:{uuid.uuid4().hex}"
            pipe = r.pipeline()
            pipe.zadd(redis_key, {member: now})
            pipe.expire(redis_key, WINDOW_SECONDS + 5)
            pipe.execute()
            return
        except HTTPException:
            raise
        except Exception:
            pass

    # Fallback in-memory chỉ khi Redis tạm thời không khả dụng
    dq = _fallback_windows[key]
    while dq and dq[0] <= window_start:
        dq.popleft()
    if len(dq) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(WINDOW_SECONDS)},
        )
    dq.append(now)
