from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .audio_capture import AudioSegment
from .audio_labels import SOURCE_MICROPHONE
from .config import AppConfig

logger = logging.getLogger(__name__)

_ENCODER = None
_DIARIZATION_OK: bool | None = None


def diarization_available() -> bool:
    global _DIARIZATION_OK
    if _DIARIZATION_OK is None:
        try:
            from speechbrain.inference.speaker import EncoderClassifier  # noqa: F401

            _DIARIZATION_OK = True
        except ImportError:
            _DIARIZATION_OK = False
    return _DIARIZATION_OK


# Compatibilidade com código que checava resemblyzer
resemblyzer_available = diarization_available


@dataclass
class SpeakerProfile:
    profile_id: str
    label: str
    centroid: np.ndarray
    hits: int = 1


@dataclass
class SpeakerSlice:
    samples: np.ndarray
    sample_rate: int
    start_ts: float
    end_ts: float
    speaker_label: str


@dataclass
class SpeakerRegistry:
    """Perfis de voz estáveis na sessão (Participante A, B, C…)."""

    config: AppConfig
    profiles: list[SpeakerProfile] = field(default_factory=list)
    _encoder: object | None = field(default=None, repr=False)

    @property
    def active(self) -> bool:
        return self.config.diarization_enabled and diarization_available()

    def _model_dir(self) -> Path:
        return self.config.project_root / "data" / "models" / "spkrec-ecapa"

    def _get_encoder(self):
        if self._encoder is None:
            from speechbrain.inference.speaker import EncoderClassifier
            from speechbrain.utils.fetching import LocalStrategy

            self._model_dir().mkdir(parents=True, exist_ok=True)
            self._encoder = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir=str(self._model_dir()),
                run_opts={"device": "cpu"},
                local_strategy=LocalStrategy.COPY,
            )
        return self._encoder

    def _to_mono_16k(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        wav = np.asarray(samples, dtype=np.float32)
        if wav.ndim > 1:
            wav = np.mean(wav, axis=1)
        if sample_rate != 16000:
            duration = len(wav) / sample_rate
            target_len = max(1, int(duration * 16000))
            wav = np.interp(
                np.linspace(0, len(wav) - 1, target_len),
                np.arange(len(wav)),
                wav,
            ).astype(np.float32)
        return wav

    def embed(self, samples: np.ndarray, sample_rate: int) -> np.ndarray | None:
        if not self.active:
            return None
        wav = self._to_mono_16k(samples, sample_rate)
        if len(wav) < int(0.35 * 16000):
            return None
        rms = float(np.sqrt(np.mean(np.square(wav))))
        if rms < self.config.diarization_min_rms:
            return None
        try:
            import torch

            signal = torch.from_numpy(wav).unsqueeze(0)
            with torch.no_grad():
                emb = self._get_encoder().encode_batch(signal)
            return emb.squeeze().cpu().numpy().astype(np.float32)
        except Exception as exc:
            logger.debug("embed falhou: %s", exc)
            return None

    def _cosine(self, a: np.ndarray, b: np.ndarray) -> float:
        denom = float(np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8
        return float(np.dot(a, b) / denom)

    def _next_label(self) -> str:
        idx = len(self.profiles)
        if idx >= self.config.max_speakers:
            return f"Participante {chr(65 + self.config.max_speakers - 1)}"
        return f"Participante {chr(65 + idx)}"

    def match_or_create(self, embedding: np.ndarray) -> str:
        best_sim = -1.0
        best_idx = -1
        for i, profile in enumerate(self.profiles):
            sim = self._cosine(embedding, profile.centroid)
            if sim > best_sim:
                best_sim = sim
                best_idx = i

        if best_idx >= 0 and best_sim >= self.config.speaker_match_threshold:
            profile = self.profiles[best_idx]
            n = profile.hits
            profile.centroid = (profile.centroid * n + embedding) / (n + 1)
            profile.hits += 1
            return profile.label

        label = self._next_label()
        pid = label.split()[-1]
        self.profiles.append(
            SpeakerProfile(profile_id=pid, label=label, centroid=embedding.copy(), hits=1)
        )
        return label

    def _cluster_local(self, embeddings: np.ndarray) -> np.ndarray:
        threshold = self.config.within_segment_threshold
        centroids: list[np.ndarray] = []
        counts: list[int] = []
        labels: list[int] = []

        for emb in embeddings:
            best_sim = -1.0
            best_idx = -1
            for i, cent in enumerate(centroids):
                sim = self._cosine(emb, cent)
                if sim > best_sim:
                    best_sim = sim
                    best_idx = i
            if best_idx >= 0 and best_sim >= threshold:
                labels.append(best_idx)
                n = counts[best_idx]
                centroids[best_idx] = (centroids[best_idx] * n + emb) / (n + 1)
                counts[best_idx] += 1
            else:
                labels.append(len(centroids))
                centroids.append(emb.copy())
                counts.append(1)
        return np.asarray(labels, dtype=int)

    def _window_spans(
        self, samples: np.ndarray, sample_rate: int
    ) -> list[tuple[int, int, np.ndarray]]:
        window = int(self.config.diarization_window_seconds * sample_rate)
        hop = int(self.config.diarization_hop_seconds * sample_rate)
        if window <= 0 or len(samples) < window:
            return []

        spans: list[tuple[int, int, np.ndarray]] = []
        max_windows = self.config.diarization_max_windows
        starts = list(range(0, len(samples) - window + 1, hop))
        if len(starts) > max_windows:
            step = max(1, len(starts) // max_windows)
            starts = starts[::step][:max_windows]

        for start in starts:
            chunk = samples[start : start + window]
            rms = float(np.sqrt(np.mean(np.square(chunk))))
            if rms < self.config.diarization_min_rms:
                continue
            emb = self.embed(chunk, sample_rate)
            if emb is not None:
                spans.append((start, start + window, emb))
        return spans

    def split_meeting_segment(self, segment: AudioSegment) -> list[SpeakerSlice]:
        duration = len(segment.samples) / segment.sample_rate
        fallback_label = "Participantes (reunião)"

        if not self.active or duration < self.config.diarization_min_seconds:
            emb = self.embed(segment.samples, segment.sample_rate)
            label = self.match_or_create(emb) if emb is not None else fallback_label
            return [
                SpeakerSlice(
                    samples=segment.samples,
                    sample_rate=segment.sample_rate,
                    start_ts=segment.start_ts,
                    end_ts=segment.end_ts,
                    speaker_label=label,
                )
            ]

        windows = self._window_spans(segment.samples, segment.sample_rate)
        if len(windows) < 2:
            emb = self.embed(segment.samples, segment.sample_rate)
            label = self.match_or_create(emb) if emb is not None else fallback_label
            return [
                SpeakerSlice(
                    samples=segment.samples,
                    sample_rate=segment.sample_rate,
                    start_ts=segment.start_ts,
                    end_ts=segment.end_ts,
                    speaker_label=label,
                )
            ]

        embeddings = np.stack([w[2] for w in windows])
        local_labels = self._cluster_local(embeddings)

        if len(np.unique(local_labels)) < 2:
            emb = np.mean(embeddings, axis=0)
            label = self.match_or_create(emb)
            return [
                SpeakerSlice(
                    samples=segment.samples,
                    sample_rate=segment.sample_rate,
                    start_ts=segment.start_ts,
                    end_ts=segment.end_ts,
                    speaker_label=label,
                )
            ]

        cluster_to_label: dict[int, str] = {}
        for cluster_id in np.unique(local_labels):
            mask = local_labels == cluster_id
            centroid = np.mean(embeddings[mask], axis=0)
            cluster_to_label[int(cluster_id)] = self.match_or_create(centroid)

        sr = segment.sample_rate
        hop = int(self.config.diarization_hop_seconds * sr)
        timeline: list[tuple[int, int, str]] = []
        for (start, end, _emb), local_id in zip(windows, local_labels):
            label = cluster_to_label[int(local_id)]
            timeline.append((start, end, label))

        timeline.sort(key=lambda x: x[0])
        merged: list[tuple[int, int, str]] = []
        for start, end, label in timeline:
            if merged and merged[-1][2] == label and start <= merged[-1][1] + hop:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end), label)
            else:
                merged.append((start, end, label))

        min_samples = int(self.config.min_speaker_slice_seconds * sr)
        slices: list[SpeakerSlice] = []
        for start, end, label in merged:
            if end - start < min_samples:
                continue
            start = max(0, start)
            end = min(len(segment.samples), end)
            t0 = segment.start_ts + start / sr
            t1 = segment.start_ts + end / sr
            slices.append(
                SpeakerSlice(
                    samples=segment.samples[start:end],
                    sample_rate=sr,
                    start_ts=t0,
                    end_ts=t1,
                    speaker_label=label,
                )
            )

        if not slices:
            emb = self.embed(segment.samples, segment.sample_rate)
            label = self.match_or_create(emb) if emb is not None else fallback_label
            return [
                SpeakerSlice(
                    samples=segment.samples,
                    sample_rate=segment.sample_rate,
                    start_ts=segment.start_ts,
                    end_ts=segment.end_ts,
                    speaker_label=label,
                )
            ]
        return slices

    def summary(self) -> list[dict]:
        return [
            {"id": p.profile_id, "label": p.label, "segments": p.hits}
            for p in self.profiles
        ]
