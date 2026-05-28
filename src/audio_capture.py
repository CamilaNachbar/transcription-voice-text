from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

import numpy as np
import soundcard as sc

from .config import AppConfig


@dataclass
class AudioSegment:
    source: str
    samples: np.ndarray
    sample_rate: int
    start_ts: float
    end_ts: float


class AudioCaptureService:
    def __init__(self, config: AppConfig):
        self.config = config
        self._running = threading.Event()
        self._threads: list[threading.Thread] = []
        self._out_queue: queue.Queue[AudioSegment] = queue.Queue()

    def start(self) -> None:
        if self._running.is_set():
            return
        self._running.set()
        self._threads = [
            threading.Thread(target=self._capture_source, args=("microfone", False), daemon=True),
            threading.Thread(target=self._capture_source, args=("sistema", True), daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._running.clear()
        for thread in self._threads:
            thread.join(timeout=1.0)
        self._threads.clear()

    def read_segment(self, timeout: float = 0.2) -> AudioSegment | None:
        try:
            return self._out_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _capture_source(self, source_name: str, loopback: bool) -> None:
        frame_count = int(self.config.sample_rate * self.config.frame_seconds)
        silence_frames = 0.0
        active_chunks: list[np.ndarray] = []
        segment_start = 0.0

        try:
            if loopback:
                speaker = sc.default_speaker()
                if speaker is None:
                    return
                recorder = speaker.recorder(samplerate=self.config.sample_rate)
            else:
                mic = sc.default_microphone()
                if mic is None:
                    return
                recorder = mic.recorder(samplerate=self.config.sample_rate)
        except Exception:
            return

        with recorder:
            while self._running.is_set():
                chunk = recorder.record(numframes=frame_count)
                if chunk.size == 0:
                    time.sleep(0.05)
                    continue

                mono = np.mean(chunk, axis=1).astype(np.float32)
                rms = float(np.sqrt(np.mean(np.square(mono))))
                now = time.time()

                if rms > self.config.silence_threshold:
                    if not active_chunks:
                        segment_start = now
                    active_chunks.append(mono)
                    silence_frames = 0.0
                    continue

                if active_chunks:
                    silence_frames += self.config.frame_seconds
                    if silence_frames >= self.config.silence_timeout_seconds:
                        segment_samples = np.concatenate(active_chunks)
                        self._out_queue.put(
                            AudioSegment(
                                source=source_name,
                                samples=segment_samples,
                                sample_rate=self.config.sample_rate,
                                start_ts=segment_start,
                                end_ts=now,
                            )
                        )
                        active_chunks.clear()
                        silence_frames = 0.0
