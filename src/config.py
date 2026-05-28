from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

# Carrega .env na raiz do projeto (se existir)
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

LLMProviderMode = Literal["auto", "anthropic", "cursor"]

LLM_PROVIDER_LABELS: dict[LLMProviderMode, str] = {
    "auto": "Automático (fallback)",
    "anthropic": "Anthropic (cliente)",
    "cursor": "Cursor SDK",
}


@dataclass(frozen=True)
class AppConfig:
    sample_rate: int = 16000
    frame_seconds: float = 1.0
    silence_threshold: float = 0.01
    silence_timeout_seconds: float = 1.8
    whisper_model: str = "small"
    session_root: Path = Path("data") / "sessions"
    project_root: Path = Path(__file__).resolve().parent.parent

    # Anthropic (cliente / gateway corporativo)
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_base_url: str | None = None

    # Cursor SDK (Claude via agente Cursor)
    cursor_model: str = "composer-2.5"

    # auto | anthropic | cursor — auto usa LLM_FALLBACK_ORDER ou anthropic,cursor
    llm_provider: LLMProviderMode = "auto"
    llm_fallback_order: str = "anthropic,cursor"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "anthropic_base_url",
            os.getenv("ANTHROPIC_BASE_URL") or os.getenv("FLOW_LITELLM_PROXY") or None,
        )
        object.__setattr__(self, "llm_provider", _env_llm_provider())
        object.__setattr__(self, "llm_fallback_order", os.getenv("LLM_FALLBACK_ORDER", "anthropic,cursor"))
        object.__setattr__(self, "cursor_model", os.getenv("CURSOR_MODEL", "composer-2.5"))
        object.__setattr__(
            self,
            "anthropic_model",
            os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        )


def _env_llm_provider() -> LLMProviderMode:
    raw = (os.getenv("LLM_PROVIDER") or "auto").strip().lower()
    if raw in ("auto", "anthropic", "cursor"):
        return raw  # type: ignore[return-value]
    return "auto"


def load_app_config() -> AppConfig:
    """Config base (.env) com preferência da UI, se existir."""
    from .user_settings import load_llm_provider

    config = AppConfig()
    override = load_llm_provider()
    if override is not None:
        return replace(config, llm_provider=override)
    return config


def get_active_llm_label(config: AppConfig) -> str:
    from .llm_providers import create_llm_provider

    provider = create_llm_provider(config)
    if not provider.available:
        return "nenhum (apenas transcrição local)"
    return provider.name


def get_llm_status_detail(config: AppConfig) -> str:
    from .llm_providers import AnthropicProvider, CursorProvider, create_llm_provider

    mode = LLM_PROVIDER_LABELS.get(config.llm_provider, config.llm_provider)
    active = create_llm_provider(config)
    active_name = active.name if active.available else "indisponível"
    anthropic_ok = AnthropicProvider(config).available
    cursor_ok = CursorProvider(config).available
    return (
        f"Modo: {mode} | Em uso: {active_name} | "
        f"Anthropic: {'ok' if anthropic_ok else '—'} | Cursor: {'ok' if cursor_ok else '—'}"
    )
