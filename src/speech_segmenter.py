from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CompletedSegment:
    samples: np.ndarray
    start_ts: float
    end_ts: float


@dataclass
class SegmenterParams:
    frame_seconds: float
    silence_threshold: float
    silence_timeout_seconds: float
    min_segment_seconds: float = 0.35
    max_segment_seconds: float = 12.0
    prefix_padding_seconds: float = 0.45
    speech_hangover_seconds: float = 0.4
    continue_threshold_ratio: float = 0.55


class SpeechSegmenter:
    """Detecta fim de fala com pré-buffer (não perde início) e flush por tempo máximo."""

    def __init__(self, params: SegmenterParams, sample_rate: int) -> None:
        self.params = params
        self.sample_rate = sample_rate
        self._ring: deque[tuple[np.ndarray, float]] = deque(
            maxlen=max(1, int(params.prefix_padding_seconds / params.frame_seconds) + 1)
        )
        self._chunks: list[np.ndarray] = []
        self._segment_start = 0.0
        self._in_speech = False
        self._silence_seconds = 0.0
        self._hangover_seconds = 0.0

    def _continue_threshold(self) -> float:
        return self.params.silence_threshold * self.params.continue_threshold_ratio

    def _segment_duration(self, now: float) -> float:
        if not self._chunks:
            return 0.0
        return now - self._segment_start

    def _emit(self, now: float) -> CompletedSegment | None:
        if not self._chunks:
            return None
        duration = self._segment_duration(now)
        if duration < self.params.min_segment_seconds:
            self._reset_segment()
            return None
        samples = np.concatenate(self._chunks)
        segment = CompletedSegment(
            samples=samples,
            start_ts=self._segment_start,
            end_ts=now,
        )
        self._reset_segment()
        return segment

    def _reset_segment(self) -> None:
        self._chunks.clear()
        self._in_speech = False
        self._silence_seconds = 0.0
        self._hangover_seconds = 0.0

    def _start_speech(self, now: float) -> None:
        self._in_speech = True
        self._silence_seconds = 0.0
        self._hangover_seconds = self.params.speech_hangover_seconds
        if self._ring:
            self._segment_start = self._ring[0][1]
            for chunk, _ in self._ring:
                self._chunks.append(chunk)
        else:
            self._segment_start = now

    def _maybe_split_max_length(self, now: float) -> CompletedSegment | None:
        if self._segment_duration(now) < self.params.max_segment_seconds:
            return None
        emitted = self._emit(now)
        if emitted is None:
            return None
        # Mantém um pouco do final para não cortar palavra na junção
        tail_samples = int(self.params.prefix_padding_seconds * self.sample_rate)
        if tail_samples > 0 and len(emitted.samples) > tail_samples:
            tail = emitted.samples[-tail_samples:].copy()
            self._in_speech = True
            self._chunks = [tail]
            self._segment_start = now - (len(tail) / self.sample_rate)
            self._hangover_seconds = self.params.speech_hangover_seconds
        return emitted

    def process_frame(self, mono: np.ndarray, rms: float, now: float) -> list[CompletedSegment]:
        p = self.params
        completed: list[CompletedSegment] = []
        is_loud = rms > p.silence_threshold
        is_continuing = self._in_speech and rms > self._continue_threshold()

        if is_loud or is_continuing:
            if not self._in_speech:
                self._start_speech(now)
            self._chunks.append(mono)
            self._silence_seconds = 0.0
            self._hangover_seconds = p.speech_hangover_seconds
            split = self._maybe_split_max_length(now)
            if split:
                completed.append(split)
            self._ring.clear()
            return completed

        if self._in_speech:
            if self._hangover_seconds > 0:
                self._chunks.append(mono)
                self._hangover_seconds = max(0.0, self._hangover_seconds - p.frame_seconds)
                self._silence_seconds = 0.0
            else:
                self._silence_seconds += p.frame_seconds
                if self._silence_seconds >= p.silence_timeout_seconds:
                    emitted = self._emit(now)
                    if emitted:
                        completed.append(emitted)
            return completed

        self._ring.append((mono, now))
        return completed

    def flush(self, now: float) -> CompletedSegment | None:
        if not self._chunks:
            return None
        return self._emit(now)
