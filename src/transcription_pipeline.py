from __future__ import annotations

from datetime import datetime

from .audio_capture import AudioSegment
from .audio_labels import SOURCE_MICROPHONE, TRANSCRIPT_LABELS
from .config import AppConfig
from .speaker_registry import SpeakerRegistry, diarization_available
from .transcriber import TranscriptLine, WhisperTranscriber


class TranscriptionPipeline:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.registry: SpeakerRegistry | None = None

    def start_session(self) -> None:
        self.registry = SpeakerRegistry(self.config)

    def diarization_status(self) -> str:
        if not self.config.diarization_enabled:
            return "identificação de vozes desativada"
        if not diarization_available():
            return "instale speechbrain para perfis de voz"
        if self.registry and self.registry.active:
            n = len(self.registry.profiles)
            return f"perfis de voz ativos ({n} participante(s))"
        return "perfis de voz indisponíveis"

    def process_segment(
        self, segment: AudioSegment, transcriber: WhisperTranscriber
    ) -> list[TranscriptLine]:
        registry = self.registry or SpeakerRegistry(self.config)

        if segment.source == SOURCE_MICROPHONE:
            line = transcriber.transcribe_audio(
                segment.samples,
                segment.sample_rate,
                speaker=TRANSCRIPT_LABELS[SOURCE_MICROPHONE],
                when=datetime.fromtimestamp(segment.start_ts),
            )
            return [line] if line else []

        slices = registry.split_meeting_segment(segment)
        lines: list[TranscriptLine] = []
        for slc in slices:
            line = transcriber.transcribe_audio(
                slc.samples,
                slc.sample_rate,
                speaker=slc.speaker_label,
                when=datetime.fromtimestamp(slc.start_ts),
            )
            if line:
                lines.append(line)
        return lines
