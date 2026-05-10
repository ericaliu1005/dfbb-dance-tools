#!/usr/bin/env python3
"""
estimate_dance_speed.py

Usage:
  python estimate_dance_speed.py --original original.mp4 --practice practice.mp4
  python estimate_dance_speed.py --original original.mp3 --practice practice.mp4 --min-speed 0.55 --max-speed 0.90

What it does:
- Accepts audio or video as input
- Extracts mono audio via ffmpeg
- Builds onset envelopes with librosa
- Searches candidate speed factors (e.g. 0.55x to 1.00x)
- Finds the best speed + offset by normalized cross-correlation

Output example:
  Estimated dance speed: 0.80x
  Estimated offset: +1.37 sec
  Confidence: 0.83
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, asdict

import numpy as np

from dance_utils import (
    DEFAULT_SR, DEFAULT_HOP,
    extract_audio_to_wav, load_audio_mono, normalize_audio,
    onset_envelope, normalized_xcorr,
)


AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found in PATH. Please install ffmpeg first.")


def is_audio_or_video(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in AUDIO_EXTS or ext in VIDEO_EXTS


@dataclass
class EstimateResult:
    speed: float
    offset_seconds: float
    score: float
    confidence: float
    speeds_tested: int
    notes: list[str]


def confidence_from_scores(best: float, second: float) -> float:
    """
    Heuristic confidence in [0, 1].
    Both components are weighted equally and sum to at most 1.
    """
    gap = max(0.0, best - second)
    conf = 0.5 * np.tanh(3.0 * max(0.0, best)) + 0.5 * np.tanh(5.0 * gap)
    return float(np.clip(conf, 0.0, 1.0))


def resample_feature_timeline(x: np.ndarray, speed: float) -> np.ndarray:
    """
    Compress the practice onset timeline by `speed` to match the original's tempo.

    If practice was danced at 0.80x, the recording is longer.
    Compressing by 0.80 brings it back to original timing.
    """
    if speed <= 0:
        raise ValueError("speed must be > 0")
    if x.size < 2:
        return x.copy()
    target_len = max(2, int(round(len(x) * speed)))
    src_idx = np.arange(len(x), dtype=np.float32)
    dst_idx = np.linspace(0, len(x) - 1, num=target_len, dtype=np.float32)
    return np.interp(dst_idx, src_idx, x).astype(np.float32)


def estimate_speed_and_offset(
    original_audio_path: str,
    practice_audio_path: str,
    sr: int,
    hop_length: int,
    min_speed: float,
    max_speed: float,
    step: float,
) -> EstimateResult:
    notes: list[str] = []

    y_orig = normalize_audio(load_audio_mono(original_audio_path, sr))
    y_prac = normalize_audio(load_audio_mono(practice_audio_path, sr))

    env_orig = onset_envelope(y_orig, sr=sr, hop_length=hop_length)
    env_prac = onset_envelope(y_prac, sr=sr, hop_length=hop_length)

    candidate_speeds = np.arange(min_speed, max_speed + step * 0.5, step)
    if candidate_speeds.size == 0:
        raise ValueError("No candidate speeds generated. Check min/max/step.")

    scored: list[tuple[float, float, int]] = []

    n = len(candidate_speeds)
    eprint(f"Testing {n} candidate speeds ({candidate_speeds[0]:.0%}–{candidate_speeds[-1]:.0%})...")
    for i, speed in enumerate(candidate_speeds):
        eprint(f"\r  [{i + 1}/{n}] {speed:.0%}...", end="", flush=True)
        warped_prac = resample_feature_timeline(env_prac, speed=speed)
        score, lag_frames = normalized_xcorr(env_orig, warped_prac)
        scored.append((score, float(speed), int(lag_frames)))
    eprint()

    scored.sort(key=lambda t: t[0], reverse=True)
    best_score, best_speed, best_lag_frames = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else (best_score - 1e-6)

    offset_seconds = best_lag_frames * hop_length / sr
    confidence = confidence_from_scores(best_score, second_score)

    if confidence < 0.45:
        notes.append("Low confidence: practice audio may be noisy, quiet, echo-heavy, or include pauses/restarts.")
    elif confidence < 0.7:
        notes.append("Medium confidence: result is usable, but double-check against a few visible beats.")
    else:
        notes.append("High confidence: strong rhythmic alignment found.")

    if best_speed < 0.75 or best_speed > 1.05:
        notes.append("Estimated speed is somewhat unusual; verify that both clips use the same song/version.")

    return EstimateResult(
        speed=best_speed,
        offset_seconds=offset_seconds,
        score=best_score,
        confidence=confidence,
        speeds_tested=len(candidate_speeds),
        notes=notes,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Estimate rehearsal dance speed relative to original audio/video."
    )
    parser.add_argument("--original",   required=True,                help="Original audio/video path")
    parser.add_argument("--practice",   required=True,                help="Practice audio/video path")
    parser.add_argument("--sr",         type=int,   default=DEFAULT_SR,  help="Audio sample rate for analysis")
    parser.add_argument("--hop-length", type=int,   default=DEFAULT_HOP, help="Hop length for onset envelope")
    parser.add_argument("--min-speed",  type=float, default=0.70,        help="Minimum candidate speed")
    parser.add_argument("--max-speed",  type=float, default=1.00,        help="Maximum candidate speed")
    parser.add_argument("--step",       type=float, default=0.01,        help="Candidate speed step")
    parser.add_argument("--json",       action="store_true",             help="Print JSON output")
    args = parser.parse_args()

    for label, path in [("original", args.original), ("practice", args.practice)]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"{label} file not found: {path}")
        if not is_audio_or_video(path):
            raise ValueError(f"Unsupported {label} file type: {path}")

    if args.min_speed <= 0 or args.max_speed <= 0 or args.step <= 0:
        raise ValueError("min-speed, max-speed, and step must all be > 0")
    if args.min_speed > args.max_speed:
        raise ValueError("min-speed cannot be greater than max-speed")

    check_ffmpeg()

    with tempfile.TemporaryDirectory(prefix="dance_speed_") as tmpdir:
        orig_wav = os.path.join(tmpdir, "original.wav")
        prac_wav = os.path.join(tmpdir, "practice.wav")

        eprint("Extracting audio from original...")
        extract_audio_to_wav(args.original, orig_wav, args.sr)
        eprint("Extracting audio from practice...")
        extract_audio_to_wav(args.practice, prac_wav, args.sr)

        result = estimate_speed_and_offset(
            original_audio_path=orig_wav,
            practice_audio_path=prac_wav,
            sr=args.sr,
            hop_length=args.hop_length,
            min_speed=args.min_speed,
            max_speed=args.max_speed,
            step=args.step,
        )

    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        print(f"Estimated dance speed: {result.speed:.2f}x")
        print(f"Estimated offset:      {result.offset_seconds:+.2f} sec")
        print(f"Score:                 {result.score:.4f}")
        print(f"Confidence:            {result.confidence:.2f}")
        print(f"Speeds tested:         {result.speeds_tested}")
        if result.notes:
            print("Notes:")
            for note in result.notes:
                print(f"  - {note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
