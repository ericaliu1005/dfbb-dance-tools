#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["numpy>=1.24"]
# ///
"""
check_av_sync.py

Verify that a slowed-down (and/or mirrored) video still maps onto its source at
exactly the intended speed — in BOTH the video track and the audio track.

Why this exists: a re-encode can come out with the right audio but a picture that
slips behind it (or vice versa). Chunked encode + `concat` is the classic cause —
each chunk contributes an extra frame, so the picture falls ~1 frame further
behind its own audio per chunk. Nobody notices until the output is stacked
against the original in an editor, by which point the practice session is wasted.

What it does:
- Samples frames from the output, finds the matching source frame by pixel
  distance (downscaled grayscale), and fits output_t -> source_t.
- Does the same with a crude audio onset envelope.
- Both fitted slopes must equal the intended speed, and the two intercepts must
  agree, or the file has internal A/V drift.

Usage:
  python check_av_sync.py --source original.mp4 --output original_90%.mp4 --speed 0.9
  python check_av_sync.py --source original.mp4 --output original_90%_mirror.mp4 --speed 0.9 --mirror

Exit code 0 = within tolerance, 1 = drift detected.
"""

import argparse
import subprocess
import sys

import numpy as np

GW, GH = 64, 36          # grayscale probe size
SR, HOP = 8000, 80       # audio: 8 kHz, 10 ms hops


def eprint(*a):
    print(*a, file=sys.stderr)


def video_frames(path, start, dur=None, n=None, mirror=False):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.4f}"]
    if dur is not None:
        cmd += ["-t", f"{dur:.4f}"]
    vf = f"scale={GW}:{GH},format=gray"
    if mirror:
        vf = "hflip," + vf
    cmd += ["-i", path, "-vf", vf]
    if n:
        cmd += ["-frames:v", str(n)]
    cmd += ["-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    a = np.frombuffer(raw, dtype=np.uint8)
    k = len(a) // (GW * GH)
    return a[: k * GW * GH].reshape(k, GH, GW).astype(np.float32)


def audio_envelope(path):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True,
    ).stdout
    y = np.frombuffer(raw, dtype=np.float32)
    n = len(y) // HOP
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    e = np.abs(y[: n * HOP].reshape(n, HOP)).max(axis=1)
    e = np.maximum(np.diff(e, prepend=e[0]), 0)
    return (e - e.mean()) / (e.std() + 1e-9)


def probe_times(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True,
    ).stdout.strip()
    dur = float(out)
    # six probes spread over the file, avoiding the very ends
    return [round(dur * f, 2) for f in (0.03, 0.18, 0.33, 0.50, 0.68, 0.85)], dur


def fit(pairs):
    T = np.array([p[0] for p in pairs], dtype=float)
    S = np.array([p[1] for p in pairs], dtype=float)
    slope, intercept = np.polyfit(T, S, 1)
    resid = S - (slope * T + intercept)
    return slope, intercept, resid


def check_video(source, output, speed, mirror, times):
    pairs = []
    for t in times:
        f = video_frames(output, t, n=1)
        if len(f) == 0:
            continue
        exp = speed * t
        start = max(0.0, exp - 1.0)
        cand = video_frames(source, start, dur=2.0, mirror=mirror)
        if len(cand) < 5:
            continue
        # candidate frame rate within the window
        fps = len(cand) / 2.0
        d = np.abs(cand - f[0]).mean(axis=(1, 2))
        i = int(np.argmin(d))
        pairs.append((t, start + i / fps))
    return pairs


def check_audio(source, output, speed, times):
    eo, es = audio_envelope(source), audio_envelope(output)
    if len(eo) == 0 or len(es) == 0:
        return []
    fps = SR / HOP
    pairs = []
    for t in times:
        a, b = int(t * fps), int((t + 4) * fps)
        seg = es[a:b]
        if len(seg) < fps:
            continue
        ns = max(2, int(len(seg) * speed))
        seg_s = np.interp(np.linspace(0, len(seg) - 1, ns), np.arange(len(seg)), seg)
        exp = speed * t
        lo = max(0, int((exp - 1.0) * fps))
        hi = min(len(eo), int((exp + 4 + 1.0) * fps))
        win = eo[lo:hi]
        if len(win) < len(seg_s) + 5:
            continue
        c = np.correlate(win, seg_s, mode="valid")
        pairs.append((t, (lo + int(np.argmax(c))) / fps))
    return pairs


def main() -> int:
    p = argparse.ArgumentParser(description="Verify a slowed video against its source.")
    p.add_argument("--source", required=True, help="The original video the output was made from")
    p.add_argument("--output", required=True, help="The slowed / mirrored output to check")
    p.add_argument("--speed", type=float, required=True, help="Intended speed (0.9 = 90%%)")
    p.add_argument("--mirror", action="store_true", help="Output was mirrored")
    p.add_argument("--tolerance-frames", type=float, default=1.0,
                   help="Max acceptable end-to-end slip, in frames (default 1)")
    args = p.parse_args()

    times, dur = probe_times(args.output)
    tol = args.tolerance_frames / 30.0

    vp = check_video(args.source, args.output, args.speed, args.mirror, times)
    ap = check_audio(args.source, args.output, args.speed, times)
    if len(vp) < 3 or len(ap) < 3:
        eprint("Not enough probe points matched — is --source really the file this was made from?")
        return 1

    vs, vi, vr = fit(vp)
    as_, ai, ar = fit(ap)

    print(f"  video : source_t = {vs:.5f} * out_t + {vi:+.3f}   (max residual {np.abs(vr).max()*1000:.0f} ms)")
    print(f"  audio : source_t = {as_:.5f} * out_t + {ai:+.3f}   (max residual {np.abs(ar).max()*1000:.0f} ms)")

    # End-to-end slip each track accumulates against the intended speed.
    v_slip = abs((vs - args.speed) * dur)
    a_slip = abs((as_ - args.speed) * dur)
    av_gap = abs((vs - as_) * dur)

    ok = True
    for label, slip in (("video", v_slip), ("audio", a_slip)):
        if slip > tol:
            print(f"  DRIFT: {label} track slips {slip*1000:.0f} ms ({slip*30:.1f} frames) end to end")
            ok = False
    if av_gap > tol:
        print(f"  DRIFT: picture and sound pull apart by {av_gap*1000:.0f} ms ({av_gap*30:.1f} frames) end to end")
        ok = False

    if ok:
        print(f"  OK — both tracks hold {args.speed*100:.2f}% within {tol*1000:.0f} ms over {dur:.0f} s.")
        return 0
    print("  Re-encode in a SINGLE pass (no chunk + concat). See SKILL.md.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
