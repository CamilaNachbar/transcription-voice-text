from __future__ import annotations

# Chaves internas usadas em AudioSegment.source
SOURCE_MICROPHONE = "microfone"
SOURCE_MEETING = "sistema"

# Rótulos na transcrição ao vivo e nos .txt
TRANSCRIPT_LABELS: dict[str, str] = {
    SOURCE_MICROPHONE: "Você",
    SOURCE_MEETING: "Participantes (Teams/outros)",
}
