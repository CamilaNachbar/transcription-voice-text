from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .transcriber import TranscriptLine


DEFAULT_WAKE_PHRASES = ("CAMILA", "gatinho de IA")
DEFAULT_WAKE_USER_PHRASE = "CAMILA"
DEFAULT_WAKE_AI_PHRASE = "gatinho de IA"


def build_wake_words(user_phrase: str, ai_phrase: str) -> tuple[str, ...]:
    parts = [p.strip() for p in (user_phrase, ai_phrase) if p and p.strip()]
    return tuple(parts) if parts else DEFAULT_WAKE_PHRASES


def is_ai_wake_phrase(detected: str, ai_phrase: str) -> bool:
    return detected.strip().lower() == ai_phrase.strip().lower()


def parse_wake_words(raw: str) -> list[str]:
    words = [w.strip() for w in raw.split(",") if w.strip()]
    return words or list(DEFAULT_WAKE_PHRASES)


def contains_wake_word(text: str, wake_words: list[str]) -> str | None:
    """Retorna a frase-gatilho detectada (ex.: CAMILA ou gatinho de IA)."""
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    for phrase in sorted(wake_words, key=len, reverse=True):
        if phrase.lower() in normalized:
            return phrase
    return None


def format_wake_phrases_label(wake_words: list[str] | tuple[str, ...]) -> str:
    return "» ou «".join(wake_words)


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
