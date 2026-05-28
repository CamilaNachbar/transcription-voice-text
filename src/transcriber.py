from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import soundfile as sf
from faster_whisper import WhisperModel

from .audio_capture import AudioSegment
from .config import AppConfig


@dataclass
class TranscriptLine:
    when: datetime
    speaker: str
    text: str


class WhisperTranscriber:
    def __init__(self, config: AppConfig):
        self.config = config
        self.model = WhisperModel(config.whisper_model, compute_type="int8")

    def transcribe_segment(self, segment: AudioSegment) -> TranscriptLine | None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            sf.write(tmp_path, segment.samples, segment.sample_rate)
            result, _ = self.model.transcribe(str(tmp_path), language="pt")
            text = " ".join([piece.text.strip() for piece in result]).strip()
            if not text:
                return None
            return TranscriptLine(
                when=datetime.fromtimestamp(segment.start_ts),
                speaker="Participante (local)" if segment.source == "microfone" else "Participante (sistema)",
                text=text,
            )
        finally:
            tmp_path.unlink(missing_ok=True)
