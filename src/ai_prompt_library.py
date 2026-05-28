"""Modelos de pedido à IA sobre a transcrição da reunião."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AiPromptPreset:
    label: str
    instruction: str


AI_USAGE_GUIDE = (
    "Durante a gravação, descreva o que você quer (ou escolha um modelo) e clique em "
    "«Enviar pedido à IA». A resposta usa só o que já foi transcrito — se faltar contexto, "
    "a IA indicará o que perguntar na reunião."
)

# Texto inicial no campo de pedido (pode ser editado livremente).
DEFAULT_CUSTOM_PROMPT = (
    "Analise a transcrição desta reunião e me ajude com o tema discutido. "
    "Se precisar de mais dados, diga quais perguntas fazer antes de concluir."
)

AI_PROMPT_PRESETS: tuple[AiPromptPreset, ...] = (
    AiPromptPreset(
        "Lista de tarefas",
        "Com base na transcrição, crie uma lista de tarefas (action items). "
        "Para cada item use: descrição, responsável (se foi dito), prazo (se foi dito) "
        "e prioridade (alta/média/baixa). Itens incertos marque como «a confirmar».",
    ),
    AiPromptPreset(
        "Pauta da próxima reunião",
        "Monte uma pauta objetiva para a próxima reunião sobre o mesmo tema: "
        "tópicos em ordem lógica, tempo sugerido por item (minutos) e objetivo de cada ponto. "
        "Inclua apenas assuntos derivados da transcrição ou pendências explícitas.",
    ),
    AiPromptPreset(
        "Decisões e pendências",
        "Liste o que já foi decidido e o que ficou pendente ou sem dono definido. "
        "Separe em duas seções: «Decisões tomadas» e «Pendências / em aberto».",
    ),
    AiPromptPreset(
        "E-mail de follow-up",
        "Redija um rascunho de e-mail de follow-up da reunião (tom profissional, em português): "
        "saudação, resumo curto, decisões, próximos passos com responsáveis e encerramento. "
        "Não invente nomes, datas ou compromissos que não apareçam na transcrição.",
    ),
    AiPromptPreset(
        "Perguntas em aberto",
        "Quais perguntas importantes ficaram sem resposta na reunião? "
        "Liste por tema e sugira como esclarecer cada uma na próxima conversa.",
    ),
    AiPromptPreset(
        "Riscos e bloqueios",
        "Identifique riscos, impedimentos ou preocupações mencionados na call. "
        "Para cada um: descrição, impacto provável e sugestão de mitigação alinhada ao que foi dito.",
    ),
    AiPromptPreset(
        "Cronograma do tema",
        "Com o que foi discutido, proponha um cronograma simples (marcos e entregas) "
        "para o tema da reunião. Deixe claro o que é hipótese por falta de datas na transcrição.",
    ),
    AiPromptPreset(
        "Resumo para quem não participou",
        "Escreva um resumo em até 10 linhas para alguém que não esteve na reunião: "
        "contexto, principais pontos, decisões e o que essa pessoa precisa saber ou fazer.",
    ),
)

PRESET_LABELS: tuple[str, ...] = tuple(p.label for p in AI_PROMPT_PRESETS)


def preset_by_label(label: str) -> AiPromptPreset | None:
    for preset in AI_PROMPT_PRESETS:
        if preset.label == label:
            return preset
    return None
