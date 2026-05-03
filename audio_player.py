from __future__ import annotations

from pathlib import Path
import threading
from typing import Callable, Optional

import numpy as np
from pydub import AudioSegment
import sounddevice as sd
import soundfile as sf


AudioFinishedCallback = Callable[[bool], None]
AudioErrorCallback = Callable[[Exception], None]


class AudioPlayerError(RuntimeError):
    """Raised when audio playback fails."""


def _normalize_pcm_data(samples: np.ndarray, sample_width: int) -> np.ndarray:
    if sample_width == 1:
        return (samples.astype(np.float32) - 128.0) / 128.0

    peak = float(1 << (8 * sample_width - 1))
    return samples.astype(np.float32) / peak


def load_audio(file_path: str) -> tuple[np.ndarray, int]:
    source = Path(file_path)
    if not source.exists():
        raise AudioPlayerError(f"Audio file was not found: {source}")

    extension = source.suffix.lower()
    if extension in {".wav", ".flac", ".ogg"}:
        data, sample_rate = sf.read(str(source), dtype="float32", always_2d=True)
        return data, sample_rate

    try:
        segment = AudioSegment.from_file(source)
    except Exception as exc:
        raise AudioPlayerError(
            "Unable to decode the selected audio file. Install ffmpeg for MP3 and AAC support."
        ) from exc

    samples = np.array(segment.get_array_of_samples())
    if segment.channels > 1:
        samples = samples.reshape((-1, segment.channels))
    else:
        samples = samples.reshape((-1, 1))

    data = _normalize_pcm_data(samples, segment.sample_width)
    return data, segment.frame_rate


def find_output_device_index(name_hint: str = "CABLE Input") -> tuple[int, str]:
    normalized_hint = name_hint.strip().lower()

    for index, device in enumerate(sd.query_devices()):
        device_name = device["name"]
        if device["max_output_channels"] <= 0:
            continue
        if normalized_hint in device_name.lower():
            return index, device_name

    raise AudioPlayerError(
        "VB-Cable playback device was not found. Install VB-Audio Virtual Cable and make sure CABLE Input is enabled."
    )


def find_default_speaker_index(exclude_hint: str = "cable") -> tuple[int, str] | None:
    """Return the system's default output device index, excluding VB-Cable.

    Falls back to the first available output device that does not match
    the exclude hint. Returns ``None`` if no suitable speaker is found.
    """
    normalized_exclude = exclude_hint.strip().lower()

    try:
        default_output = sd.default.device[1]
    except Exception:
        default_output = None

    if isinstance(default_output, int) and default_output >= 0:
        try:
            info = sd.query_devices(default_output)
            if (
                info.get("max_output_channels", 0) > 0
                and normalized_exclude not in info["name"].lower()
            ):
                return default_output, info["name"]
        except Exception:
            pass

    for index, device in enumerate(sd.query_devices()):
        if device["max_output_channels"] <= 0:
            continue
        if normalized_exclude in device["name"].lower():
            continue
        return index, device["name"]

    return None


class AudioPlayer:
    def __init__(self) -> None:
        self._audio_data: Optional[np.ndarray] = None
        self._sample_rate: Optional[int] = None
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._stop_requested = threading.Event()

    def load_audio(self, file_path: str) -> None:
        audio_data, sample_rate = load_audio(file_path)
        with self._lock:
            self._audio_data = audio_data
            self._sample_rate = sample_rate

    def is_playing(self) -> bool:
        with self._lock:
            return self._worker is not None and self._worker.is_alive()

    def play(
        self,
        device_indices: list[int],
        volume: float = 1.0,
        on_finished: Optional[AudioFinishedCallback] = None,
        on_error: Optional[AudioErrorCallback] = None,
    ) -> None:
        with self._lock:
            if self.is_playing():
                raise AudioPlayerError("Audio is already playing.")
            if self._audio_data is None or self._sample_rate is None:
                raise AudioPlayerError("Load an audio file before starting playback.")
            if not device_indices:
                raise AudioPlayerError("At least one output device is required.")

            audio_data = np.clip(self._audio_data * volume, -1.0, 1.0).astype(np.float32)
            sample_rate = self._sample_rate
            self._stop_requested.clear()
            self._worker = threading.Thread(
                target=self._playback_worker,
                args=(audio_data, sample_rate, list(device_indices), on_finished, on_error),
                daemon=True,
            )
            self._worker.start()

    def stop(self) -> None:
        if not self.is_playing():
            return

        self._stop_requested.set()

    def _stream_to_device(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        device_index: int,
        errors: list[Exception],
    ) -> None:
        try:
            channels = audio_data.shape[1]
            block_size = 2048
            with sd.OutputStream(
                samplerate=sample_rate,
                channels=channels,
                device=device_index,
                dtype="float32",
                blocksize=block_size,
            ) as stream:
                total_frames = audio_data.shape[0]
                offset = 0
                while offset < total_frames:
                    if self._stop_requested.is_set():
                        break
                    end = min(offset + block_size, total_frames)
                    stream.write(audio_data[offset:end])
                    offset = end
        except Exception as exc:
            if not self._stop_requested.is_set():
                errors.append(exc)

    def _playback_worker(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        device_indices: list[int],
        on_finished: Optional[AudioFinishedCallback],
        on_error: Optional[AudioErrorCallback],
    ) -> None:
        errors: list[Exception] = []
        threads: list[threading.Thread] = []
        try:
            for device_index in device_indices:
                thread = threading.Thread(
                    target=self._stream_to_device,
                    args=(audio_data, sample_rate, device_index, errors),
                    daemon=True,
                )
                thread.start()
                threads.append(thread)

            for thread in threads:
                thread.join()

            interrupted = self._stop_requested.is_set()
            if errors and not interrupted:
                if on_error is not None:
                    on_error(errors[0])
            elif on_finished is not None:
                on_finished(interrupted)
        finally:
            with self._lock:
                self._worker = None
                self._stop_requested.clear()
