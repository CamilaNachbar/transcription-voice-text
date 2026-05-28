from __future__ import annotations

from .config import AppConfig
from .llm_providers import LLMProvider, create_llm_provider


class ClaudePostProcessor:
    def __init__(self, config: AppConfig):
        self.config = config
        self.provider: LLMProvider = create_llm_provider(config)

    def reload(self, config: AppConfig) -> None:
        self.config = config
        self.provider = create_llm_provider(config)

    def refine_transcript(self, raw_transcript: str) -> str:
        if not raw_transcript.strip():
            return raw_transcript
        if not self.provider.available:
            return raw_transcript
        prompt = (
            "Você é um assistente de reuniões. Reescreva a transcrição com boa pontuação, "
            "separe os participantes por blocos e mantenha fidelidade ao conteúdo. "
            "Não invente fatos.\n\nTranscrição:\n"
            f"{raw_transcript}"
        )
        try:
            return self.provider.complete(prompt, max_tokens=1800)
        except Exception:
            return raw_transcript

    def summarize(self, formatted_transcript: str) -> str:
        if not formatted_transcript.strip():
            return "Resumo indisponível: transcrição vazia."
        if not self.provider.available:
            return (
                "Resumo indisponível: configure ANTHROPIC_API_KEY ou FLOW_API_KEY "
                "(cliente/gateway) ou CURSOR_API_KEY (Cursor SDK). Veja .env.example."
            )
        prompt = (
            "Gere um resumo objetivo de reunião em português com:\n"
            "- tópicos principais\n"
            "- decisões tomadas\n"
            "- próximos passos com responsáveis quando possível\n\n"
            f"Transcrição formatada:\n{formatted_transcript}"
        )
        try:
            return self.provider.complete(prompt, max_tokens=1200)
        except Exception as exc:
            return f"Resumo indisponível: {exc}"
