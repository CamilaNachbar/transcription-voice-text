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
    frame_seconds: float = 0.4
    silence_threshold: float = 0.01
    silence_timeout_seconds: float = 0.75
    # Áudio remoto (Teams, Meet, Zoom) — pausa um pouco maior, limiar mais baixo
    system_silence_threshold: float = 0.006
    system_silence_timeout_seconds: float = 1.15
    # Segmentação: pré-buffer, hangover e teto para não esperar pausa longa
    min_segment_seconds: float = 0.35
    max_segment_seconds: float = 12.0
    prefix_padding_seconds: float = 0.45
    speech_hangover_seconds: float = 0.4
    continue_threshold_ratio: float = 0.55
    whisper_model: str = "small"
    # Diarização (perfis Participante A, B, C… no áudio da reunião)
    diarization_enabled: bool = True
    diarization_min_seconds: float = 2.0
    diarization_window_seconds: float = 1.0
    diarization_hop_seconds: float = 0.45
    diarization_max_windows: int = 14
    diarization_min_rms: float = 0.004
    min_speaker_slice_seconds: float = 0.55
    speaker_match_threshold: float = 0.72
    within_segment_threshold: float = 0.68
    max_speakers: int = 8
    # Nome usado nas sugestões de resposta da IA
    assistant_user_name: str = "Camila"
    # URL aberta pelo botão «Chrome + gravar»
    chrome_meeting_url: str = "https://meet.google.com/new"
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
        object.__setattr__(
            self,
            "system_silence_threshold",
            float(os.getenv("SYSTEM_SILENCE_THRESHOLD", "0.006")),
        )
        object.__setattr__(
            self,
            "system_silence_timeout_seconds",
            float(os.getenv("SYSTEM_SILENCE_TIMEOUT_SECONDS", "1.15")),
        )
        object.__setattr__(self, "frame_seconds", float(os.getenv("FRAME_SECONDS", "0.4")))
        object.__setattr__(
            self, "silence_timeout_seconds", float(os.getenv("SILENCE_TIMEOUT_SECONDS", "0.75"))
        )
        object.__setattr__(
            self, "max_segment_seconds", float(os.getenv("MAX_SEGMENT_SECONDS", "12.0"))
        )
        object.__setattr__(
            self, "prefix_padding_seconds", float(os.getenv("PREFIX_PADDING_SECONDS", "0.45"))
        )
        object.__setattr__(
            self, "speech_hangover_seconds", float(os.getenv("SPEECH_HANGOVER_SECONDS", "0.4"))
        )
        object.__setattr__(
            self,
            "diarization_enabled",
            os.getenv("DIARIZATION_ENABLED", "true").strip().lower() in ("1", "true", "yes"),
        )
        object.__setattr__(
            self,
            "diarization_min_seconds",
            float(os.getenv("DIARIZATION_MIN_SECONDS", "2.0")),
        )
        object.__setattr__(
            self,
            "speaker_match_threshold",
            float(os.getenv("SPEAKER_MATCH_THRESHOLD", "0.72")),
        )
        assistant_name = (
            os.getenv("ASSISTANT_USER_NAME")
            or os.getenv("WAKE_ASSISTANT_USER_NAME")
            or "Camila"
        ).strip() or "Camila"
        object.__setattr__(self, "assistant_user_name", assistant_name)
        object.__setattr__(
            self,
            "chrome_meeting_url",
            os.getenv("CHROME_MEETING_URL", "https://meet.google.com/new").strip()
            or "https://meet.google.com/new",
        )


def _env_llm_provider() -> LLMProviderMode:
    raw = (os.getenv("LLM_PROVIDER") or "auto").strip().lower()
    if raw in ("auto", "anthropic", "cursor"):
        return raw  # type: ignore[return-value]
    return "auto"


def load_app_config() -> AppConfig:
    """Config base (.env) com preferência da UI, se existir."""
    from .user_settings import load_chrome_meeting_url, load_llm_provider

    config = AppConfig()
    chrome_url = load_chrome_meeting_url()
    if chrome_url is not None:
        config = replace(config, chrome_meeting_url=chrome_url)
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
