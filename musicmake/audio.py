"""Small audio helpers: WAV in/out, MP3 export, waveform peaks.

Audio arrays are float32, shape (frames, 2), in the range -1..1.
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np


def to_stereo(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 1:
        return np.stack([x, x], axis=1)
    if x.shape[1] == 1:
        return np.repeat(x, 2, axis=1)
    return x[:, :2]


def write_wav(path: str | Path, audio: np.ndarray, sr: int) -> None:
    audio = to_stereo(audio)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Read a 16-bit PCM WAV (the format MusicMake stores)."""
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"expected 16-bit WAV, got {8 * width}-bit")
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    data = data.reshape(-1, ch)
    return to_stereo(data), sr


def duration_of(path: str | Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def convert_to_wav(src: str | Path, dst: str | Path, sr: int = 44100) -> None:
    """Convert any audio file ffmpeg can read into 16-bit stereo WAV."""
    if not has_ffmpeg():
        raise RuntimeError("ffmpeg is needed to import this audio file")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-ac", "2", "-ar", str(sr), "-sample_fmt", "s16", str(dst)],
        check=True,
    )


def export_mp3(src_wav: str | Path, dst_mp3: str | Path, bitrate: str = "192k") -> None:
    if not has_ffmpeg():
        raise RuntimeError("ffmpeg is needed for MP3 export")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src_wav),
         "-codec:a", "libmp3lame", "-b:a", bitrate, str(dst_mp3)],
        check=True,
    )


def peaks(audio: np.ndarray, points: int = 240) -> list[float]:
    """Downsample to `points` peak values in 0..1 for drawing a waveform."""
    mono = np.abs(to_stereo(audio)).max(axis=1)
    if len(mono) == 0:
        return [0.0] * points
    edges = np.linspace(0, len(mono), points + 1).astype(int)
    out = [float(mono[a:b].max()) if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:])]
    top = max(out) or 1.0
    return [round(v / top, 3) for v in out]


def normalize(audio: np.ndarray, peak: float = 0.89) -> np.ndarray:
    top = float(np.abs(audio).max()) if audio.size else 0.0
    if top < 1e-9:
        return audio
    return (audio * (peak / top)).astype(np.float32)


def crossfade_concat(a: np.ndarray, b: np.ndarray, sr: int, seconds: float = 0.5) -> np.ndarray:
    a, b = to_stereo(a), to_stereo(b)
    n = int(min(seconds * sr, len(a), len(b)))
    if n <= 0:
        return np.concatenate([a, b])
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)[:, None]
    mid = a[-n:] * (1.0 - ramp) + b[:n] * ramp
    return np.concatenate([a[:-n], mid, b[n:]]).astype(np.float32)
