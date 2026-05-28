#!/usr/bin/env python3
"""Testa conexão com CI&T Flow LiteLLM (mesmas variáveis do .env do app)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_app_config  # noqa: E402
from src.llm_providers import AnthropicProvider  # noqa: E402


def _mask(value: str | None) -> str:
    if not value:
        return "(não definido)"
    if len(value) <= 12:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


def main() -> int:
    config = load_app_config()
    provider = AnthropicProvider(config)

    base_url = config.anthropic_base_url or os.getenv("FLOW_LITELLM_PROXY")
    api_key = (
        os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("ANTHROPIC_AUTH_TOKEN")
        or os.getenv("FLOW_API_KEY")
    )

    print("=== Teste Flow LiteLLM ===")
    print(f"Base URL : {base_url or '(não definido — use FLOW_LITELLM_PROXY ou ANTHROPIC_BASE_URL)'}")
    print(f"Modelo   : {config.anthropic_model}")
    print(f"API key  : {_mask(api_key)}")

    if not provider.available:
        print("\nFalha: provedor Anthropic indisponível.")
        print("Configure FLOW_API_KEY (JWT) e FLOW_LITELLM_PROXY no .env — veja README.")
        return 1

    print("\nEnviando mensagem de teste...")
    try:
        reply = provider.complete("Responda apenas com a palavra: ok", max_tokens=32)
    except Exception as exc:
        print(f"\nFalha na requisição: {exc}")
        print("\nDicas: JWT válido? VPN ativa? SSL_CERT_FILE se usar NetSkope?")
        return 1

    print(f"\nResposta: {reply!r}")
    print("\nSucesso — Flow LiteLLM está acessível para este app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
