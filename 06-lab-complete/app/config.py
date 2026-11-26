"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    )
    daily_budget_usd: float = field(
        default_factory=lambda: float(os.getenv("DAILY_BUDGET_USD", "1.0"))
    )
    monthly_budget_usd: float = field(
        default_factory=lambda: float(os.getenv("MONTHLY_BUDGET_USD", "10.0"))
    )
    # Optional real LLM config (OpenAI-compatible: OpenAI, Gemini, Groq, OpenRouter...)
    # Nếu để trống, app tự động fallback về mock_llm để chạy offline / grading.
    llm_api_key: str = field(
        default_factory=lambda: os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    )
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    )
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))
    llm_system_prompt: str = field(
        default_factory=lambda: os.getenv(
            "LLM_SYSTEM_PROMPT",
            "Bạn là trợ lý AI hữu ích, trả lời ngắn gọn, rõ ràng và chính xác.",
        )
    )


settings = Settings()
