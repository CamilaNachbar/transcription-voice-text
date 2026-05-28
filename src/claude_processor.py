from __future__ import annotations

from .config import AppConfig
from .llm_providers import LLMProvider, create_llm_provider
from .transcript_utils import AssistantMode


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
                "ou CURSOR_API_KEY no .env."
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

    def assist_quick(
        self,
        transcript: str,
        action_label: str,
        *,
        user_name: str = "Camila",
        mode: AssistantMode = "summarize",
        summary_context: str | None = None,
    ) -> str:
        """IA acionada pelos botões: resumo e/ou sugestão de resposta."""
        if not transcript.strip():
            return (
                "Ainda não há transcrição suficiente.\n\n"
                "Continue a reunião e tente novamente."
            )
        if not self.provider.available:
            return (
                "Assistente indisponível: configure ANTHROPIC_API_KEY, FLOW_API_KEY "
                "ou CURSOR_API_KEY no .env."
            )

        if mode == "respond":
            summary_block = ""
            if summary_context and summary_context.strip():
                summary_block = (
                    "## Resumo atual (já gerado nesta reunião)\n"
                    f"{summary_context.strip()}\n\n"
                )
            prompt = (
                f"Você apoia {user_name} em uma reunião online. "
                f"Ação: «{action_label}» (sugestão de resposta).\n\n"
                "Com base APENAS no material abaixo, responda em português com exatamente "
                "estas duas seções (use os títulos):\n\n"
                "## Resumo até o momento\n"
                "(atualize se necessário — objetivo)\n\n"
                "## Sugestão de resposta\n"
                f"(texto curto que {user_name} pode falar agora, em 1ª pessoa, "
                "educado e direto; se faltar contexto, diga o que perguntar)\n\n"
                "Não invente fatos que não estejam no material.\n\n"
                f"{summary_block}"
                f"Transcrição completa:\n{transcript}"
            )
        else:
            prompt = (
                f"Você apoia {user_name} em uma reunião online. "
                f"Ação: «{action_label}» (só resumo).\n\n"
                "Com base APENAS na transcrição abaixo, responda em português com exatamente "
                "esta seção (use o título):\n\n"
                "## Resumo até o momento\n"
                "(tópicos em discussão, decisões, pendências — objetivo e claro)\n\n"
                "Não inclua sugestão de resposta. Não invente fatos.\n\n"
                f"Transcrição:\n{transcript}"
            )

        try:
            return self.provider.complete(prompt, max_tokens=1400)
        except Exception as exc:
            return f"Assistente indisponível: {exc}"

    def assist_custom(
        self,
        transcript: str,
        user_request: str,
        *,
        user_name: str = "Camila",
        summary_context: str | None = None,
    ) -> str:
        """Pedido livre sobre a transcrição (listas, pautas, e-mails, etc.)."""
        request = user_request.strip()
        if not request:
            return "Escreva um pedido antes de enviar à IA."
        if not transcript.strip():
            return (
                "Ainda não há transcrição suficiente.\n\n"
                "Continue a reunião e tente novamente."
            )
        if not self.provider.available:
            return (
                "Assistente indisponível: configure ANTHROPIC_API_KEY, FLOW_API_KEY "
                "ou CURSOR_API_KEY no .env."
            )

        summary_block = ""
        if summary_context and summary_context.strip():
            summary_block = (
                "## Resumo parcial já gerado nesta reunião\n"
                f"{summary_context.strip()}\n\n"
            )

        prompt = (
            f"Você apoia {user_name} em reuniões online (Teams, Meet, Zoom, etc.).\n"
            "Regras:\n"
            "- Use APENAS a transcrição e o resumo parcial abaixo; não invente fatos.\n"
            "- Se o pedido exigir dados que não aparecem, diga o que falta e sugira "
            "perguntas objetivas para obter na reunião.\n"
            "- Responda em português, em markdown claro (títulos ##, listas, tabelas se útil).\n"
            "- Seja prático: listas, pautas, rascunhos de mensagens, cronogramas, etc.\n\n"
            f"## Pedido\n{request}\n\n"
            f"{summary_block}"
            f"## Transcrição\n{transcript}"
        )
        try:
            return self.provider.complete(prompt, max_tokens=1800)
        except Exception as exc:
            return f"Assistente indisponível: {exc}"
