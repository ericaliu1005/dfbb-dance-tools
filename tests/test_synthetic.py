#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["numpy>=1.24", "scipy>=1.10", "librosa>=0.10"]
# ///
"""
Regression tests using synthetic audio/video — no fixtures to check in.

Run directly:   python3 tests/test_synthetic.py
Or via pytest:  pytest tests/

Needs ffmpeg/ffprobe on PATH. Tests that need librosa skip when it is missing.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "skills/estimate-dance-speed/scripts/estimate_dance_speed.py"
MET = ROOT / "skills/metronome-generator/scripts/generate_metronome.py"
VID = ROOT / "skills/dance-video-tools/scripts/slowdown_video.py"
SR = 22050

try:
    import librosa  # noqa: F401
    HAVE_LIBROSA = True
except ImportError:
    HAVE_LIBROSA = False


class Skip(Exception):
    pass


# ---------- helpers ----------

def run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)


def run_ok(cmd):
    proc = run(cmd)
    assert proc.returncode == 0, f"{cmd[0]} failed:\n{proc.stdout}\n{proc.stderr}"
    return proc


def probe(path, entries):
    out = run_ok(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", entries,
                  "-of", "csv=p=0", path]).stdout
    return [x for x in re.split(r"[,\n]", out.strip()) if x]


def duration_of(path):
    return float(run_ok(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "csv=p=0", path]).stdout.strip())


def write_wav(path, y, sr=SR):
    y = np.clip(y, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((y * 32767).astype(np.int16).tobytes())


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32767


def click(freq, dur=0.03, amp=1.0):
    t = np.arange(int(dur * SR)) / SR
    return amp * np.sin(2 * np.pi * freq * t) * np.exp(-t * 80)


def mix(*parts):
    n = max(len(p) for p in parts)
    return sum(np.pad(p, (0, n - len(p))) for p in parts)


def synth_rhythm(bpm, seconds, seed=0):
    """Aperiodic rhythm on a 16th-note grid: strong downbeats, random fills.
    Random fills make the cross-correlation peak unambiguous, unlike a pure click track."""
    rng = np.random.default_rng(seed)
    y = np.zeros(int(seconds * SR), dtype=np.float32)
    step = 60.0 / bpm / 4
    n_slots = int(seconds / step)
    for i in range(n_slots):
        pos = int(i * step * SR)
        if i % 16 == 0:
            c = mix(click(180, 0.08, 1.0), click(900, 0.03, 0.6))
        elif i % 4 == 0:
            c = click(700, 0.04, 0.7)
        elif rng.random() < 0.45:
            c = click(rng.uniform(1000, 3000), 0.02, rng.uniform(0.2, 0.6))
        else:
            continue
        end = min(pos + len(c), len(y))
        y[pos:end] += c[: end - pos]
    return np.tanh(y)


# ---------- tests ----------

def test_estimate_speed_and_offset(tmp: Path):
    if not HAVE_LIBROSA:
        raise Skip("librosa not installed")
    true_speed, preroll = 0.80, 3.0
    orig = tmp / "orig.wav"
    write_wav(orig, synth_rhythm(128, 40))

    stretched = tmp / "stretched.wav"
    run_ok(["ffmpeg", "-y", "-loglevel", "error", "-i", orig, "-af", f"atempo={true_speed}", stretched])
    noise = np.random.default_rng(1).normal(0, 0.02, int(preroll * SR)).astype(np.float32)
    prac = tmp / "prac.wav"
    write_wav(prac, np.concatenate([noise, read_wav(stretched)]))

    out = run_ok([sys.executable, EST, "--original", orig, "--practice", prac, "--json"]).stdout
    r = json.loads(out)
    assert abs(r["speed"] - true_speed) <= 0.015, r
    assert abs(r["offset_seconds"] + preroll) <= 0.4, f"offset should be ≈ -{preroll}s in practice time: {r}"
    assert r["confidence"] >= 0.7, r


def test_estimate_flags_edge_of_range(tmp: Path):
    if not HAVE_LIBROSA:
        raise Skip("librosa not installed")
    orig = tmp / "orig.wav"
    write_wav(orig, synth_rhythm(128, 30))
    stretched = tmp / "prac.wav"
    # True speed sits exactly on the lower bound, so the best match must be the edge candidate.
    run_ok(["ffmpeg", "-y", "-loglevel", "error", "-i", orig, "-af", "atempo=0.7", stretched])
    r = json.loads(run_ok([sys.executable, EST, "--original", orig, "--practice", stretched,
                           "--min-speed", "0.7", "--max-speed", "1.0", "--json"]).stdout)
    assert abs(r["speed"] - 0.7) < 0.005, r
    assert any("edge of the search range" in n for n in r["notes"]), r


def test_metronome_duration_and_formats(tmp: Path):
    bpm = 120
    for ext in ("wav", "m4a"):
        out = tmp / f"m.{ext}"
        run_ok([sys.executable, MET, "--bpm", bpm, "--output", out])
        expected = 32 * 60 / bpm
        assert abs(duration_of(out) - expected) <= 0.15, (ext, duration_of(out), expected)


def test_metronome_all_writes_five(tmp: Path):
    proc = run_ok([sys.executable, MET, "--bpm", 100, "--all", "--output", tmp / "ignored.m4a"])
    files = sorted(p.name for p in tmp.glob("metronome_100bpm_*.m4a"))
    assert len(files) == 5, files
    assert "WARN" in proc.stderr, "expected a warning that the filename was ignored"


def test_metronome_detects_bpm(tmp: Path):
    if not HAVE_LIBROSA:
        raise Skip("librosa not installed")
    song = tmp / "song.wav"
    write_wav(song, synth_rhythm(128, 30, seed=3))
    proc = run_ok([sys.executable, MET, "--song", song, "--output", tmp / "d.wav"])
    m = re.search(r"detected ([\d.]+) BPM", proc.stdout)
    assert m, proc.stdout
    bpm = float(m.group(1))
    octaves = [128 / 2, 128, 128 * 2]
    assert any(abs(bpm - o) <= 3 for o in octaves), bpm
    if bpm < 90 or bpm > 190:
        assert "WARN" in proc.stderr, "out-of-band detection must warn about the octave alternative"


def test_video_keeps_portrait_and_slows(tmp: Path):
    src = tmp / "port.mp4"
    run_ok(["ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=30:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src])
    out = Path(run_ok([sys.executable, VID, "--input", src, "--speed", "0.8", "--mirror",
                       "--preset", "ultrafast"]).stdout.strip())
    assert out.name == "port_80%_mirror.mp4", out
    assert probe(out, "stream=width,height") == ["1080", "1920"], probe(out, "stream=width,height")
    assert abs(duration_of(out) - 1.25) <= 0.1, duration_of(out)


def test_video_downscales_landscape_4k(tmp: Path):
    src = tmp / "land.mp4"
    run_ok(["ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=3840x2160:rate=30:duration=0.5",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an", src])
    # --mirror only, no audio stream: exercises the mirror-only path too
    out = Path(run_ok([sys.executable, VID, "--input", src, "--mirror", "--preset", "ultrafast"]).stdout.strip())
    assert probe(out, "stream=width,height") == ["1920", "1080"]


def test_video_chunk_uses_input_time(tmp: Path):
    src = tmp / "clip.mp4"
    run_ok(["ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src])
    out = tmp / "chunk.mp4"
    run_ok([sys.executable, VID, "--input", src, "--speed", "0.5", "--start", "1", "--duration", "0.5",
            "--preset", "ultrafast", "--output", out])
    assert abs(duration_of(out) - 1.0) <= 0.1, duration_of(out)  # 0.5 s of input at half speed


# ---------- runner ----------

def main() -> int:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        print("ffmpeg/ffprobe not on PATH — cannot run tests")
        return 2
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        with tempfile.TemporaryDirectory(prefix="dfbb_test_") as td:
            try:
                fn(Path(td))
                print(f"PASS  {name}")
            except Skip as e:
                print(f"SKIP  {name} ({e})")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"FAIL  {name}\n      {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
