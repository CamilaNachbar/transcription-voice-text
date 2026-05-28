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
            "Você é um assistente de reuniões online (Teams, Meet, Zoom, etc.). "
            "Reescreva a transcrição com boa pontuação. "
            "Linhas «Você» são o microfone local; "
            "«Participante A/B/C…» são vozes distintas detectadas no áudio da reunião. "
            "Mantenha esses rótulos e não invente fatos.\n\nTranscrição:\n"
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

    def assist_on_wake(self, transcript: str, wake_name: str) -> str:
        """Resumo da reunião até o momento + sugestão de resposta para quem foi chamado."""
        if not transcript.strip():
            return (
                "Ainda não há transcrição suficiente.\n\n"
                "Continue a reunião e peça para repetirem a pergunta."
            )
        if not self.provider.available:
            return (
                "Assistente indisponível: configure ANTHROPIC_API_KEY, FLOW_API_KEY "
                "ou CURSOR_API_KEY no .env."
            )
        prompt = (
            f"Na reunião, alguém chamou ou mencionou «{wake_name}» (palavra-gatilho). "
            f"Você apoia {wake_name}, que está participando da call.\n\n"
            "Com base APENAS na transcrição abaixo, responda em português com exatamente "
            "estas duas seções (use os títulos):\n\n"
            "## Resumo até o momento\n"
            "(tópicos em discussão, decisões, pendências — objetivo)\n\n"
            "## Sugestão de resposta\n"
            f"(texto curto que {wake_name} poderia falar agora, em 1ª pessoa, "
            "educado e direto; se faltar contexto, diga o que perguntar para esclarecer)\n\n"
            "Não invente fatos que não estejam na transcrição.\n\n"
            f"Transcrição:\n{transcript}"
        )
        try:
            return self.provider.complete(prompt, max_tokens=1400)
        except Exception as exc:
            return f"Assistente indisponível: {exc}"
