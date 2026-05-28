from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .transcriber import TranscriptLine

AssistantMode = Literal["summarize", "respond"]


def extract_summary_section(assistant_text: str) -> str | None:
    """Extrai o bloco «Resumo até o momento» da resposta da IA."""
    match = re.search(
        r"##\s*Resumo até o momento\s*\n+(.*?)(?=\n##|\Z)",
        assistant_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if match:
        body = match.group(1).strip()
        return body or None
    stripped = assistant_text.strip()
    return stripped or None


def format_transcript(lines: list[TranscriptLine], *, max_lines: int = 80) -> str:
    chunk = lines[-max_lines:] if len(lines) > max_lines else lines
    return "\n".join(
        f"[{line.when.strftime('%H:%M:%S')}] {line.speaker}: {line.text}" for line in chunk
    )


@dataclass
class AssistantBusyState:
    busy: bool = False

    def mark_started(self) -> None:
        self.busy = True

    def mark_finished(self) -> None:
        self.busy = False
