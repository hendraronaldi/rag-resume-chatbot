import os
from typing import List, Optional, Sequence, Tuple
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

from app.model_pool import CHAT_MODEL_POOL, RAG_MODEL_POOL, ROUTING_MODEL_POOL


def _parse_pool(raw: Optional[str], default: Sequence[str]) -> Tuple[str, ...]:
    """Parse a comma-separated pool override, falling back to default."""
    if not raw:
        return tuple(default)
    items = [part.strip() for part in raw.split(",") if part.strip()]
    return tuple(items) if items else tuple(default)


def _parse_float(raw: Optional[str], default: float) -> float:
    """Parse a float env override, falling back to default on error."""
    try:
        return float(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


class Settings:
    # Set your Google API key - consider using environment variables
    GOOGLE_API_KEY: Optional[str] = os.getenv('GOOGLE_API_KEY')
    LLM: str = os.getenv('LLM', 'gemini-2.5-flash')
    EMBEDDING_MODEL: str = os.getenv('EMBEDDING_MODEL', 'gemini-embedding-001')
    EMBEDDING_DIMENSIONS: int = int(os.getenv('EMBEDDING_DIMENSIONS', '768'))
    INDEX_PATH: str = './app/data/index'
    RESUME_PATH: str = './app/data/resume.md'
    ROUTING_LLM_POOL: Tuple[str, ...] = _parse_pool(
        os.getenv('ROUTING_LLM_POOL'), ROUTING_MODEL_POOL)
    RAG_LLM_POOL: Tuple[str, ...] = _parse_pool(
        os.getenv('RAG_LLM_POOL'), RAG_MODEL_POOL)
    CHAT_LLM_POOL: Tuple[str, ...] = _parse_pool(
        os.getenv('CHAT_LLM_POOL'), CHAT_MODEL_POOL)
    PROVIDER_REQUEST_TIMEOUT_S: float = _parse_float(
        os.getenv('PROVIDER_REQUEST_TIMEOUT_S'), 10.0)
    LLM_REMAINING_BUDGET_S: float = _parse_float(
        os.getenv('LLM_REMAINING_BUDGET_S'), 60.0)
    PORTFOLIO_TIME_BUDGET_S: float = _parse_float(
        os.getenv('PORTFOLIO_TIME_BUDGET_S'), 60.0)

def get_settings():
    return Settings()