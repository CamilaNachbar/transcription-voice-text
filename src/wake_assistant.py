from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .transcriber import TranscriptLine


def parse_wake_words(raw: str) -> list[str]:
    words = [w.strip() for w in raw.split(",") if w.strip()]
    return words or ["CAMILA"]


def contains_wake_word(text: str, wake_words: list[str]) -> str | None:
    """Retorna a palavra detectada ou None."""
    normalized = text.lower()
    for word in wake_words:
        pattern = rf"\b{re.escape(word.lower())}\b"
        if re.search(pattern, normalized):
            return word
    return None


def format_transcript(lines: list[TranscriptLine], *, max_lines: int = 80) -> str:
    chunk = lines[-max_lines:] if len(lines) > max_lines else lines
    return "\n".join(
        f"[{line.when.strftime('%H:%M:%S')}] {line.speaker}: {line.text}" for line in chunk
    )


@dataclass
class WakeTriggerState:
    last_trigger_ts: float = 0.0
    busy: bool = False
    trigger_count: int = 0

    def can_trigger(self, cooldown_seconds: float) -> bool:
        if self.busy:
            return False
        return (time.time() - self.last_trigger_ts) >= cooldown_seconds

    def mark_started(self) -> None:
        self.busy = True
        self.last_trigger_ts = time.time()
        self.trigger_count += 1

    def mark_finished(self) -> None:
        self.busy = False
