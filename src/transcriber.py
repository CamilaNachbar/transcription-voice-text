from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import soundfile as sf
from faster_whisper import WhisperModel

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

    def transcribe_audio(
        self,
        samples,
        sample_rate: int,
        *,
        speaker: str,
        when: datetime,
    ) -> TranscriptLine | None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            sf.write(tmp_path, samples, sample_rate)
            result, _ = self.model.transcribe(
                str(tmp_path),
                language="pt",
                vad_filter=False,
                beam_size=1,
                condition_on_previous_text=False,
            )
            text = " ".join([piece.text.strip() for piece in result]).strip()
            if not text:
                return None
            return TranscriptLine(when=when, speaker=speaker, text=text)
        finally:
            tmp_path.unlink(missing_ok=True)
