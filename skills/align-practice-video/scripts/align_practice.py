#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["numpy>=1.24", "scipy>=1.10", "librosa>=0.10"]
# ///
"""
align_practice.py

Line a practice recording up with the slowed reference video it was danced to, so
the two can be stacked in an editor with no manual nudging.

What it does:
1. Measures the time offset between the two files by matching onset envelopes in
   several windows across the whole song — not just once at the start. Windows that
   match poorly (intro, silence, applause) are dropped, and the offset is taken as a
   robust median, so one bad window cannot skew the answer.
2. Reports whether the offset is CONSTANT or DRIFTING. A drift means the two files
   are at different speeds and no single offset will ever work — fix that first.
3. Renders a copy of the practice video trimmed by that offset, so it drops onto the
   editor timeline at position 0 already aligned. The re-encode is constant frame
   rate, which also fixes variable-frame-rate phone footage.
4. Re-measures the rendered file and reports the leftover error.

The video can only be cut on whole frames, so its trim is rounded to the nearest
frame (up to 1/60 s of residual). The audio is trimmed to the exact offset, which
keeps the two waveforms lining up perfectly for visual confirmation in the editor.
The resulting few-millisecond gap between picture and sound is far below the ~40 ms
human threshold.

Usage:
  python align_practice.py --practice IMG_8087.MOV --reference "MOON_90%.mp4"
  python align_practice.py --practice p.MOV --reference r.mp4 --report-only
  python align_practice.py --practice p.MOV --reference r.mp4 --output aligned.mp4
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
import librosa

SR = 22050
HOP = 128                 # ~5.8 ms resolution
WINDOW = 20.0             # seconds of reference matched per probe
SEARCH = 3.0              # +/- seconds searched around the expected position
MIN_CORR = 0.45           # windows below this are ignored


def eprint(*a):
    print(*a, file=sys.stderr)


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed:\n{p.stderr}")
    return p.stdout


def probe(path, stream, entries):
    out = run(["ffprobe", "-v", "error", "-select_streams", stream,
               "-show_entries", entries, "-of", "default=nw=1:nk=1", path])
    return [l for l in out.splitlines() if l.strip()]


def frame_rate(path):
    """Nominal fps, plus whether the file is variable frame rate."""
    try:
        r, avg = probe(path, "v:0", "stream=r_frame_rate,avg_frame_rate")[:2]
        def f(x):
            n, d = x.split("/")
            return float(n) / float(d) if float(d) else 0.0
        rr, aa = f(r), f(avg)
        vfr = rr > 0 and aa > 0 and abs(rr - aa) / rr > 0.0005
        return (rr or 30.0), vfr
    except Exception:
        return 30.0, False


def duration(path):
    return float(probe(path, "v:0", "format=duration")[0])


def onset_env(path):
    wav = tempfile.mktemp(suffix=".wav")
    try:
        run(["ffmpeg", "-y", "-v", "error", "-i", path,
             "-vn", "-ac", "1", "-ar", str(SR), wav])
        y, _ = librosa.load(wav, sr=SR)
    finally:
        if os.path.exists(wav):
            os.remove(wav)
    if y.size == 0:
        raise RuntimeError(f"no audio in {path}")
    e = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    return (e - e.mean()) / (e.std() + 1e-9)


def measure(ref_env, prac_env, ref_dur):
    """Offsets (practice_t - reference_t) sampled across the song."""
    fps = SR / HOP
    starts = np.arange(2.0, max(3.0, ref_dur - WINDOW - 1), max(10.0, ref_dur / 10))
    rows = []
    for t in starts:
        a, b = int(t * fps), int((t + WINDOW) * fps)
        seg = ref_env[a:b]
        if len(seg) < WINDOW * fps * 0.8:
            continue
        lo = max(0, int((t - SEARCH) * fps))
        hi = min(len(prac_env), int((t + WINDOW + SEARCH) * fps))
        win = prac_env[lo:hi]
        if len(win) < len(seg) + 4:
            continue
        c = np.correlate(win, seg, mode="valid")
        k = int(np.argmax(c))
        corr = c[k] / (np.linalg.norm(seg) * np.linalg.norm(win[k:k + len(seg)]) + 1e-9)
        if 0 < k < len(c) - 1:                      # sub-hop refinement
            y0, y1, y2 = c[k - 1], c[k], c[k + 1]
            k = k + (y0 - y2) / (2 * (y0 - 2 * y1 + y2) + 1e-12)
        rows.append((t, (lo + k) / fps - t, corr))
    return rows


def summarize(rows, dur, label):
    good = [r for r in rows if r[2] >= MIN_CORR]
    eprint(f"\n  {label}:")
    for t, off, c in rows:
        flag = "" if c >= MIN_CORR else "   (ignored, weak match)"
        eprint(f"    {t:6.0f}s  {off*1000:+8.0f} ms   corr {c:.2f}{flag}")
    if len(good) < 3:
        raise RuntimeError(
            "fewer than 3 windows matched — are these really the same song? "
            "If the practice is at a different speed, run estimate-dance-speed first.")
    T = np.array([r[0] for r in good])
    O = np.array([r[1] for r in good])
    med = float(np.median(O))
    spread = float(O.max() - O.min())
    slope = float(np.polyfit(T, O, 1)[0]) if len(good) > 2 else 0.0
    drift = abs(slope) * dur
    eprint(f"    -> median offset {med*1000:+.0f} ms, spread {spread*1000:.0f} ms, "
           f"drift across the song {drift*1000:.0f} ms")
    return med, spread, drift


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Align a practice recording to the reference video it was danced to.")
    ap.add_argument("--practice", required=True, help="The practice recording")
    ap.add_argument("--reference", required=True,
                    help="The slowed video that was played during practice")
    ap.add_argument("--output", default=None, help="Output path (default: <practice>_aligned.mp4)")
    ap.add_argument("--report-only", action="store_true", help="Measure only, render nothing")
    ap.add_argument("--fps", type=float, default=None, help="Override output frame rate")
    ap.add_argument("--preset", default="veryfast", help="x264 preset (default veryfast)")
    ap.add_argument("--crf", type=int, default=20)
    args = ap.parse_args()

    fps, vfr = frame_rate(args.practice)
    if args.fps:
        fps = args.fps
    if vfr:
        eprint(f"  Practice footage is VARIABLE frame rate (~{fps:.3f} fps nominal).")
        eprint("  The render below converts it to constant frame rate, which is also")
        eprint("  what stops editors re-timing it against its own audio.")

    eprint("  Measuring offset...")
    ref_env = onset_env(args.reference)
    prac_env = onset_env(args.practice)
    ref_dur = duration(args.reference)
    offset, spread, drift = summarize(measure(ref_env, prac_env, ref_dur),
                                      ref_dur, "practice minus reference")

    if drift > 2.0 / fps:
        eprint(f"\n  WARNING: the offset drifts {drift*1000:.0f} ms across the song "
               f"({drift*fps:.1f} frames).")
        eprint("  No single offset can fix that — the two files are at different speeds,")
        eprint("  or one of them was encoded in chunks and concatenated. Check the")
        eprint("  reference with dance-video-tools' check_av_sync.py before going on.")

    v_trim = round(offset * fps) / fps
    a_trim = offset
    print(f"Offset: {offset*1000:+.0f} ms  =  {offset*fps:.2f} frames @ {fps:g} fps")
    print(f"Place the practice clip {abs(offset*fps):.0f} frames "
          f"{'later' if offset < 0 else 'earlier'} than the reference, "
          f"or use the rendered file below.")

    if args.report_only:
        return 0
    if offset <= 0:
        eprint("\n  The practice starts after the reference, so nothing can be trimmed "
               "off its head.\n  Place it manually at the offset above.")
        return 0

    out = args.output or (os.path.splitext(args.practice)[0] + "_aligned.mp4")
    eprint(f"\n  Rendering {out} (single pass, preset {args.preset})...")
    run(["ffmpeg", "-y", "-nostdin", "-v", "error", "-i", args.practice,
         "-filter_complex",
         f"[0:v]trim=start={v_trim:.6f},setpts=PTS-STARTPTS[v];"
         f"[0:a]atrim=start={a_trim:.6f},asetpts=PTS-STARTPTS[a]",
         "-map", "[v]", "-map", "[a]",
         "-vsync", "cfr", "-r", f"{fps:g}",
         "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", out])

    eprint("  Verifying the rendered file...")
    res_off, res_spread, _ = summarize(measure(ref_env, onset_env(out), ref_dur),
                                       ref_dur, "aligned minus reference")
    print(f"\nWrote {out}")
    print(f"Leftover error: {res_off*1000:+.0f} ms "
          f"({abs(res_off)*fps:.2f} frames), window spread {res_spread*1000:.0f} ms")
    print("Drop it at position 0 next to the reference — no nudging needed.")
    if abs(res_off) > 1.0 / fps:
        print("NOTE: leftover is over a frame; check that both files are the same speed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
