from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

from .config import AppConfig

ProviderName = Literal["anthropic", "cursor", "none"]


class LLMProvider(ABC):
    name: ProviderName

    @abstractmethod
    def complete(self, prompt: str, max_tokens: int) -> str:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        return True


class AnthropicProvider(LLMProvider):
    name: ProviderName = "anthropic"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client = None
        api_key = (
            os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("ANTHROPIC_AUTH_TOKEN")
            or os.getenv("FLOW_API_KEY")
        )
        if not api_key:
            return
        try:
            from anthropic import Anthropic

            kwargs: dict = {"api_key": api_key}
            if config.anthropic_base_url:
                kwargs["base_url"] = config.anthropic_base_url
            self._client = Anthropic(**kwargs)
        except Exception:
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def complete(self, prompt: str, max_tokens: int) -> str:
        if not self._client:
            raise RuntimeError(
                "Anthropic indisponível: configure ANTHROPIC_API_KEY, "
                "ANTHROPIC_AUTH_TOKEN ou FLOW_API_KEY."
            )
        resp = self._client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ).strip()


class CursorProvider(LLMProvider):
    """Claude via Cursor SDK (agente local — útil quando a VPN bloqueia api.anthropic.com)."""

    name: ProviderName = "cursor"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._api_key = os.getenv("CURSOR_API_KEY")
        self._sdk_error: str | None = None
        try:
            from cursor_sdk import Agent  # noqa: F401

            self._agent_cls = Agent
        except ImportError:
            self._agent_cls = None
            self._sdk_error = "Instale cursor-sdk: pip install cursor-sdk"

    @property
    def available(self) -> bool:
        return bool(self._api_key and self._agent_cls)

    def complete(self, prompt: str, max_tokens: int) -> str:
        if self._sdk_error:
            raise RuntimeError(self._sdk_error)
        if not self._api_key or not self._agent_cls:
            raise RuntimeError("Cursor indisponível: configure CURSOR_API_KEY.")
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

        options = AgentOptions(
            api_key=self._api_key,
            model=self.config.cursor_model,
            local=LocalAgentOptions(cwd=str(self.config.project_root)),
        )
        result = Agent.prompt(
            f"{prompt}\n\n(Responda apenas com o texto solicitado, sem explicações extras. "
            f"Limite aproximado: {max_tokens} tokens.)",
            options,
        )
        if getattr(result, "status", None) == "error":
            raise RuntimeError(f"Cursor agent falhou: {getattr(result, 'id', 'unknown')}")
        text = getattr(result, "result", None) or ""
        return str(text).strip()


class NoneProvider(LLMProvider):
    name: ProviderName = "none"

    @property
    def available(self) -> bool:
        return True

    def complete(self, prompt: str, max_tokens: int) -> str:
        raise RuntimeError("Nenhum provedor LLM configurado.")


class ChainedLLMProvider(LLMProvider):
    """Tenta provedores em ordem (fallback para ambientes com VPN restritiva)."""

    def __init__(self, providers: list[LLMProvider]) -> None:
        self.providers = [p for p in providers if p.available]
        self.name = self.providers[0].name if self.providers else "none"

    @property
    def available(self) -> bool:
        return bool(self.providers)

    def complete(self, prompt: str, max_tokens: int) -> str:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return provider.complete(prompt, max_tokens)
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
        raise RuntimeError("Todos os provedores falharam. " + " | ".join(errors))


def resolve_provider_order(config: AppConfig) -> list[str]:
    if config.llm_provider != "auto":
        return [config.llm_provider]
    order = config.llm_fallback_order.strip()
    if order:
        return [p.strip() for p in order.split(",") if p.strip()]
    return ["anthropic", "cursor"]


def create_llm_provider(config: AppConfig) -> LLMProvider:
    registry: dict[str, LLMProvider] = {
        "anthropic": AnthropicProvider(config),
        "cursor": CursorProvider(config),
    }
    names = resolve_provider_order(config)
    selected = [registry[n] for n in names if n in registry and registry[n].available]
    if not selected:
        return NoneProvider()
    if len(selected) == 1:
        return selected[0]
    return ChainedLLMProvider(selected)
