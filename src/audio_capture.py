from __future__ import annotations

import logging
import queue
import warnings
import threading
import time
from dataclasses import dataclass, field

import numpy as np

from .audio_devices import resolve_loopback, resolve_microphone
from .audio_labels import SOURCE_MEETING, SOURCE_MICROPHONE
from .config import AppConfig
from .speech_segmenter import SegmenterParams, SpeechSegmenter

logger = logging.getLogger(__name__)

try:
    from soundcard import SoundcardRuntimeWarning

    warnings.simplefilter("ignore", SoundcardRuntimeWarning)
except ImportError:
    pass


@dataclass
class AudioSegment:
    source: str
    samples: np.ndarray
    sample_rate: int
    start_ts: float
    end_ts: float


@dataclass
class CaptureSourceStatus:
    name: str
    active: bool = False
    error: str | None = None


@dataclass
class CaptureStatus:
    microfone: CaptureSourceStatus = field(default_factory=lambda: CaptureSourceStatus("microfone"))
    sistema: CaptureSourceStatus = field(default_factory=lambda: CaptureSourceStatus("participantes"))


class AudioCaptureService:
    def __init__(
        self,
        config: AppConfig,
        *,
        microphone_device_id: str | None = None,
        loopback_device_id: str | None = None,
        capture_system_audio: bool = True,
    ):
        self.config = config
        self.microphone_device_id = microphone_device_id
        self.loopback_device_id = loopback_device_id
        self.capture_system_audio = capture_system_audio
        self._running = threading.Event()
        self._threads: list[threading.Thread] = []
        self._out_queue: queue.Queue[AudioSegment] = queue.Queue()
        self.status = CaptureStatus()

    def start(self) -> CaptureStatus:
        if self._running.is_set():
            return self.status
        self.status = CaptureStatus()
        self._running.set()
        self._threads = [
            threading.Thread(
                target=self._capture_microphone,
                name="capture-mic",
                daemon=True,
            ),
        ]
        if self.capture_system_audio:
            self._threads.append(
                threading.Thread(
                    target=self._capture_system,
                    name="capture-loopback",
                    daemon=True,
                )
            )
        else:
            self.status.sistema.error = "Captura de sistema desativada"

        for thread in self._threads:
            thread.start()
        return self.status

    def stop(self) -> None:
        self._running.clear()
        for thread in self._threads:
            thread.join(timeout=2.0)
        self._threads.clear()

    def read_segment(self, timeout: float = 0.2) -> AudioSegment | None:
        try:
            return self._out_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _segmenter_params(
        self,
        *,
        silence_threshold: float,
        silence_timeout_seconds: float,
    ) -> SegmenterParams:
        c = self.config
        return SegmenterParams(
            frame_seconds=c.frame_seconds,
            silence_threshold=silence_threshold,
            silence_timeout_seconds=silence_timeout_seconds,
            min_segment_seconds=c.min_segment_seconds,
            max_segment_seconds=c.max_segment_seconds,
            prefix_padding_seconds=c.prefix_padding_seconds,
            speech_hangover_seconds=c.speech_hangover_seconds,
            continue_threshold_ratio=c.continue_threshold_ratio,
        )

    def _capture_microphone(self) -> None:
        self._capture_source(
            source_name=SOURCE_MICROPHONE,
            device=resolve_microphone(self.microphone_device_id),
            status=self.status.microfone,
            segmenter_params=self._segmenter_params(
                silence_threshold=self.config.silence_threshold,
                silence_timeout_seconds=self.config.silence_timeout_seconds,
            ),
        )

    def _capture_system(self) -> None:
        device = resolve_loopback(self.loopback_device_id)
        if device is None:
            import sys

            if sys.platform == "darwin":
                self.status.sistema.error = (
                    "Nenhum BlackHole/Loopback encontrado. "
                    "Instale BlackHole, crie saída múltipla no Áudio MIDI e selecione em «Participantes». "
                    "Aba Áudio → «Ajuda áudio (Mac)»."
                )
            else:
                self.status.sistema.error = (
                    "Nenhum dispositivo de loopback encontrado. "
                    "No Windows, use a lista «Participantes» e o mesmo dispositivo "
                    "definido em Configurações → Som → Saída."
                )
            return
        self._capture_source(
            source_name=SOURCE_MEETING,
            device=device,
            status=self.status.sistema,
            segmenter_params=self._segmenter_params(
                silence_threshold=self.config.system_silence_threshold,
                silence_timeout_seconds=self.config.system_silence_timeout_seconds,
            ),
        )

    def _enqueue_completed(
        self, source_name: str, completed: list, sample_rate: int
    ) -> None:
        for seg in completed:
            self._out_queue.put(
                AudioSegment(
                    source=source_name,
                    samples=seg.samples,
                    sample_rate=sample_rate,
                    start_ts=seg.start_ts,
                    end_ts=seg.end_ts,
                )
            )

    def _capture_source(
        self,
        source_name: str,
        device: object | None,
        status: CaptureSourceStatus,
        *,
        segmenter_params: SegmenterParams,
    ) -> None:
        frame_count = int(self.config.sample_rate * segmenter_params.frame_seconds)
        segmenter = SpeechSegmenter(segmenter_params, self.config.sample_rate)

        if device is None:
            status.error = "Dispositivo de áudio não encontrado."
            return

        try:
            recorder = device.recorder(samplerate=self.config.sample_rate)  # type: ignore[attr-defined]
        except Exception as exc:
            status.error = f"Não foi possível abrir «{getattr(device, 'name', device)}»: {exc}"
            logger.warning("Falha ao abrir %s: %s", source_name, exc)
            return

        status.active = True
        with recorder:
            while self._running.is_set():
                try:
                    chunk = recorder.record(numframes=frame_count)
                except Exception as exc:
                    if self._running.is_set():
                        status.error = str(exc)
                        status.active = False
                        logger.warning("Erro gravando %s: %s", source_name, exc)
                    break

                if chunk.size == 0:
                    time.sleep(0.02)
                    continue

                if chunk.ndim > 1:
                    mono = np.mean(chunk, axis=1).astype(np.float32)
                else:
                    mono = chunk.astype(np.float32)

                rms = float(np.sqrt(np.mean(np.square(mono))))
                now = time.time()
                completed = segmenter.process_frame(mono, rms, now)
                self._enqueue_completed(source_name, completed, self.config.sample_rate)

            # Flush ao parar gravação — não perde a última fala
            flushed = segmenter.flush(time.time())
            if flushed:
                self._enqueue_completed(source_name, [flushed], self.config.sample_rate)
