"""
dance_utils.py

Shared audio processing utilities for the dance comparison toolkit.
Imported by estimate_dance_speed.py and stack_videos.py.
"""

from __future__ import annotations

import math
import subprocess

import numpy as np
import librosa
from scipy.signal import correlate, correlation_lags


DEFAULT_SR  = 16000
DEFAULT_HOP = 512


# ---------------------------------------------------------------------------
# Audio I/O
# ---------------------------------------------------------------------------

def extract_audio_to_wav(
    input_path: str,
    output_wav: str,
    sr: int,
    start: float = 0.0,
    duration: float | None = None,
) -> None:
    """
    Extract mono 16-bit PCM WAV from an audio or video file via ffmpeg.

    `start`    — seek to this many seconds before extracting
    `duration` — only extract this many seconds (None = until end)
    """
    cmd = ["ffmpeg", "-y"]
    if start > 0:
        cmd += ["-ss", str(start)]
    cmd += ["-i", input_path, "-vn", "-ac", "1", "-ar", str(sr), "-sample_fmt", "s16"]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd.append(output_wav)

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {input_path}:\n{proc.stderr}")


def load_audio_mono(path: str, sr: int) -> np.ndarray:
    y, _ = librosa.load(path, sr=sr, mono=True)
    if y.size == 0:
        raise RuntimeError(f"Loaded empty audio from {path}")
    return y


# ---------------------------------------------------------------------------
# Signal processing
# ---------------------------------------------------------------------------

def normalize_audio(y: np.ndarray) -> np.ndarray:
    y = y.astype(np.float32, copy=False)
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    return y / peak if peak > 0 else y


def onset_envelope(y: np.ndarray, sr: int, hop_length: int) -> np.ndarray:
    """
    Z-score-normalized onset strength envelope.
    More robust than raw waveform for rooms with echo or a distant mic.
    """
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    env = env.astype(np.float32, copy=False)
    if env.size == 0:
        raise RuntimeError("Failed to compute onset envelope.")
    std = float(np.std(env))
    return (env - float(np.mean(env))) / std if std > 1e-8 else env - float(np.mean(env))


def normalized_xcorr(a: np.ndarray, b: np.ndarray) -> tuple[float, int]:
    """
    Normalized cross-correlation between two 1-D arrays.

    Returns (best_score, best_lag_frames) where:
      - score is in roughly [-1, 1]
      - positive lag means b should be shifted later to align with a
        (i.e. b starts too early relative to a by `lag` frames)
    """
    if a.size < 8 or b.size < 8:
        return -1.0, 0

    a = a.astype(np.float32, copy=False)
    b = b.astype(np.float32, copy=False)

    a_std = float(np.std(a))
    b_std = float(np.std(b))
    a = (a - np.mean(a)) / a_std if a_std > 1e-8 else a - np.mean(a)
    b = (b - np.mean(b)) / b_std if b_std > 1e-8 else b - np.mean(b)

    corr = correlate(a, b, mode="full", method="auto")
    lags = correlation_lags(len(a), len(b), mode="full")

    denom = math.sqrt(max(1.0, float(np.dot(a, a)) * float(np.dot(b, b))))
    corr = corr / denom

    idx = int(np.argmax(corr))
    return float(corr[idx]), int(lags[idx])


# ---------------------------------------------------------------------------
# High-level sync helper
# ---------------------------------------------------------------------------

def find_sync_offset(
    path_a: str,
    path_b: str,
    start_a: float = 0.0,
    start_b: float = 0.0,
    sr: int = DEFAULT_SR,
    hop_length: int = DEFAULT_HOP,
    probe_seconds: float = 90.0,
) -> tuple[float, float]:
    """
    Find the timing offset between two audio/video files.

    Extracts up to `probe_seconds` of audio from each (starting at the
    given offsets), then cross-correlates their onset envelopes.

    Returns (offset_seconds, score) where:
      offset_seconds > 0  →  b leads a (b is ahead); trim a by offset seconds to catch up
      offset_seconds < 0  →  a leads b (a is ahead); trim b by |offset| seconds to catch up
    """
    import tempfile, os

    with tempfile.TemporaryDirectory(prefix="dance_sync_") as tmpdir:
        wav_a = os.path.join(tmpdir, "a.wav")
        wav_b = os.path.join(tmpdir, "b.wav")

        extract_audio_to_wav(path_a, wav_a, sr, start=start_a, duration=probe_seconds)
        extract_audio_to_wav(path_b, wav_b, sr, start=start_b, duration=probe_seconds)

        y_a = normalize_audio(load_audio_mono(wav_a, sr))
        y_b = normalize_audio(load_audio_mono(wav_b, sr))

    env_a = onset_envelope(y_a, sr, hop_length)
    env_b = onset_envelope(y_b, sr, hop_length)

    score, lag_frames = normalized_xcorr(env_a, env_b)
    offset_seconds = lag_frames * hop_length / sr

    return offset_seconds, score
