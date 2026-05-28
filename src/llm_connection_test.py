from __future__ import annotations

import os
from dataclasses import dataclass

from .config import AppConfig, LLM_PROVIDER_LABELS
from .llm_providers import AnthropicProvider, CursorProvider, create_llm_provider


@dataclass(frozen=True)
class ProviderTestResult:
    provider_id: str
    label: str
    configured: bool
    success: bool
    detail: str
    reply: str | None = None


_TEST_PROMPT = "Responda apenas com a palavra: ok"


def _mask_secret(value: str | None) -> str:
    if not value:
        return "(não definido)"
    if len(value) <= 12:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


def test_anthropic_provider(config: AppConfig) -> ProviderTestResult:
    label = "Anthropic / Flow LiteLLM"
    api_key = (
        os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("ANTHROPIC_AUTH_TOKEN")
        or os.getenv("FLOW_API_KEY")
    )
    base_url = config.anthropic_base_url or os.getenv("FLOW_LITELLM_PROXY") or "(API oficial)"
    provider = AnthropicProvider(config)

    if not provider.available:
        return ProviderTestResult(
            provider_id="anthropic",
            label=label,
            configured=False,
            success=False,
            detail=(
                f"Chave: {_mask_secret(api_key)}\n"
                f"Base URL: {base_url}\n"
                f"Modelo: {config.anthropic_model}\n\n"
                "Configure FLOW_API_KEY + FLOW_LITELLM_PROXY ou ANTHROPIC_API_KEY no .env."
            ),
        )

    try:
        reply = provider.complete(_TEST_PROMPT, max_tokens=32)
        return ProviderTestResult(
            provider_id="anthropic",
            label=label,
            configured=True,
            success=True,
            detail=(
                f"Chave: {_mask_secret(api_key)}\n"
                f"Base URL: {base_url}\n"
                f"Modelo: {config.anthropic_model}"
            ),
            reply=reply,
        )
    except Exception as exc:
        return ProviderTestResult(
            provider_id="anthropic",
            label=label,
            configured=True,
            success=False,
            detail=(
                f"Chave: {_mask_secret(api_key)}\n"
                f"Base URL: {base_url}\n"
                f"Modelo: {config.anthropic_model}\n\n"
                f"Erro: {exc}"
            ),
        )


def test_cursor_provider(config: AppConfig) -> ProviderTestResult:
    label = "Cursor SDK"
    api_key = os.getenv("CURSOR_API_KEY")
    provider = CursorProvider(config)

    if not provider.available:
        detail = f"Chave: {_mask_secret(api_key)}\nModelo: {config.cursor_model}\n\n"
        if getattr(provider, "_sdk_error", None):
            detail += str(provider._sdk_error)
        else:
            detail += "Configure CURSOR_API_KEY no .env."
        return ProviderTestResult(
            provider_id="cursor",
            label=label,
            configured=False,
            success=False,
            detail=detail,
        )

    try:
        reply = provider.complete(_TEST_PROMPT, max_tokens=32)
        return ProviderTestResult(
            provider_id="cursor",
            label=label,
            configured=True,
            success=True,
            detail=f"Chave: {_mask_secret(api_key)}\nModelo: {config.cursor_model}",
            reply=reply,
        )
    except Exception as exc:
        return ProviderTestResult(
            provider_id="cursor",
            label=label,
            configured=True,
            success=False,
            detail=(
                f"Chave: {_mask_secret(api_key)}\n"
                f"Modelo: {config.cursor_model}\n\n"
                f"Erro: {exc}"
            ),
        )


def test_active_provider(config: AppConfig) -> ProviderTestResult:
    mode = LLM_PROVIDER_LABELS.get(config.llm_provider, config.llm_provider)
    provider = create_llm_provider(config)
    label = f"Provedor em uso ({mode})"

    if not provider.available:
        return ProviderTestResult(
            provider_id="active",
            label=label,
            configured=False,
            success=False,
            detail="Nenhum provedor disponível para o modo selecionado na interface.",
        )

    try:
        reply = provider.complete(_TEST_PROMPT, max_tokens=32)
        return ProviderTestResult(
            provider_id="active",
            label=label,
            configured=True,
            success=True,
            detail=f"Backend: {provider.name}",
            reply=reply,
        )
    except Exception as exc:
        return ProviderTestResult(
            provider_id="active",
            label=label,
            configured=True,
            success=False,
            detail=f"Backend: {provider.name}\n\nErro: {exc}",
        )


def run_all_connection_tests(config: AppConfig) -> list[ProviderTestResult]:
    return [
        test_anthropic_provider(config),
        test_cursor_provider(config),
        test_active_provider(config),
    ]


def format_connection_report(results: list[ProviderTestResult]) -> tuple[str, bool]:
    lines: list[str] = ["Teste de conexão com agentes de IA", "=" * 44, ""]
    any_success = False

    for result in results:
        status = "OK" if result.success else "FALHA"
        lines.append(f"[{status}] {result.label}")
        lines.append(result.detail)
        if result.reply is not None:
            lines.append(f"Resposta: {result.reply!r}")
        lines.append("")
        if result.success:
            any_success = True

    if any_success:
        lines.append("Pelo menos um provedor respondeu com sucesso.")
    else:
        lines.append("Nenhum provedor respondeu. Revise o .env e a VPN.")

    return "\n".join(lines), any_success
