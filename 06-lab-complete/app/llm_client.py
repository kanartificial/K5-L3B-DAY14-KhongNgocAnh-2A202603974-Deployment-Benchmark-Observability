"""
LLM Client — Hỗ trợ gọi AI API thật (OpenAI-compatible: OpenAI, Gemini, Groq, OpenRouter...)
và tự động fallback về mock_llm khi không đặt LLM_API_KEY / OPENAI_API_KEY.
"""
import json
import urllib.error
import urllib.request

from fastapi import HTTPException

from app.config import settings
from utils.mock_llm import ask as mock_ask


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()) * 2)


def generate_answer(question: str) -> dict:
    """Trả về dict gồm answer, model, provider, input_tokens, output_tokens."""
    if not settings.llm_api_key:
        answer = mock_ask(question)
        return {
            "answer": answer,
            "model": "mock-llm",
            "provider": "mock",
            "input_tokens": _estimate_tokens(question),
            "output_tokens": _estimate_tokens(answer),
        }

    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": settings.llm_system_prompt},
            {"role": "user", "content": question},
        ],
        "temperature": 0.7,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.llm_api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail_msg = f"Upstream AI API error (HTTP {exc.code})"
        try:
            err_body = json.loads(exc.read().decode("utf-8", errors="replace"))
            if isinstance(err_body, dict) and "error" in err_body:
                err_obj = err_body["error"]
                msg = err_obj.get("message") if isinstance(err_obj, dict) else str(err_obj)
                if msg:
                    detail_msg = f"Upstream AI API error ({exc.code}): {msg[:200]}"
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=detail_msg)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise HTTPException(status_code=502, detail="Could not reach upstream AI API")

    try:
        answer = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        raise HTTPException(status_code=502, detail="Unexpected response format from AI API")

    usage = data.get("usage") or {}
    in_tokens = int(usage.get("prompt_tokens") or _estimate_tokens(question))
    out_tokens = int(usage.get("completion_tokens") or _estimate_tokens(answer))

    return {
        "answer": answer,
        "model": data.get("model") or settings.llm_model,
        "provider": "live",
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
    }
