#!/usr/bin/env python3
"""
slowdown_video.py

Slow down a video to a target speed, with optional horizontal mirror.

Usage:
  python slowdown_video.py --input original.mp4 --speed 0.60
  python slowdown_video.py --input original.mp4 --speed 0.75 --mirror
  python slowdown_video.py --input original.mp4 --speed 0.80 --output slowed.mp4
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found in PATH. Please install ffmpeg first.")


def build_atempo_chain(speed: float) -> str:
    """
    Build an atempo filter chain for the given speed.
    atempo only accepts values in [0.5, 2.0], so we chain multiple filters
    for speeds outside that range (e.g. 0.60 is fine; 0.40 needs two stages).

    Examples:
      0.60  ->  atempo=0.600000
      0.40  ->  atempo=0.5,atempo=0.800000
      0.25  ->  atempo=0.5,atempo=0.5,atempo=1.000000
    """
    filters = []
    s = speed
    while s < 0.5:
        filters.append("atempo=0.5")
        s /= 0.5
    while s > 2.0:
        filters.append("atempo=2.0")
        s /= 2.0
    filters.append(f"atempo={s:.6f}")
    return ",".join(filters)


def default_output_name(input_path: str, speed: float, mirror: bool) -> str:
    base, _ = os.path.splitext(input_path)
    parts = []
    if speed != 1.0:
        parts.append(f"{speed:.0%}")
    if mirror:
        parts.append("mirror")
    suffix = "_" + "_".join(parts) if parts else ""
    return f"{base}{suffix}.mp4"


def slowdown_video(
    input_path: str,
    output_path: str,
    speed: float,
    mirror: bool,
    preset: str = "fast",
    crf: int = 20,
) -> None:
    # Video filter: slow down + optional mirror + scale-and-pad to 1080p
    # 1080p is fast and plenty sharp for practice review; 4K originals take far too long.
    vf_parts = [f"setpts=PTS/{speed:.6f}"]
    if mirror:
        vf_parts.append("hflip")
    vf_parts.append(
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
    )
    vf = ",".join(vf_parts)

    # Audio filter: chained atempo
    af = build_atempo_chain(speed)

    eprint(f"  Video filter : {vf}")
    eprint(f"  Audio filter : {af}")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-vf", vf,
        "-af", af,
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Slow down a video to a target speed, with optional horizontal mirror."
    )
    parser.add_argument("--input",  required=True,       help="Input video path")
    parser.add_argument("--speed",  type=float, default=1.0,
                        help="Target speed as a decimal (e.g. 0.60 for 60%%). "
                             "Default 1.0 (no slowdown — useful with --mirror only).")
    parser.add_argument("--output", default=None,        help="Output path (default: auto-named)")
    parser.add_argument("--mirror", action="store_true", help="Horizontally flip the video")
    parser.add_argument("--preset", default="fast",
                        choices=["ultrafast", "superfast", "veryfast", "faster", "fast",
                                 "medium", "slow", "slower", "veryslow"],
                        help="x264 encoding preset (default: fast). Use 'ultrafast' for "
                             "speed at the cost of bigger file/lower compression.")
    parser.add_argument("--crf", type=int, default=20,
                        help="Constant Rate Factor 0-51 (default 20). Lower = better quality, bigger file.")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        raise FileNotFoundError(f"Input file not found: {args.input}")
    if not (0 < args.speed <= 2.0):
        raise ValueError(f"Speed must be in (0, 2.0], got {args.speed}")
    if args.speed == 1.0 and not args.mirror:
        raise ValueError("Nothing to do — speed is 1.0 and --mirror not set. "
                         "Specify --speed <X> or --mirror (or both).")

    output = args.output or default_output_name(args.input, args.speed, args.mirror)

    check_ffmpeg()

    eprint(f"Input  : {args.input}")
    eprint(f"Speed  : {args.speed:.0%}")
    eprint(f"Mirror : {'yes' if args.mirror else 'no'}")
    eprint(f"Output : {output}")
    eprint("Processing...")

    slowdown_video(args.input, output, args.speed, args.mirror,
                   preset=args.preset, crf=args.crf)

    print(output)   # stdout: just the output path, easy to pipe
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
