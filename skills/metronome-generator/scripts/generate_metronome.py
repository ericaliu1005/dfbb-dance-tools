#!/usr/bin/env python3
"""
Generate a 4-eight-count (32-beat, 4/4) metronome at a target BPM.

Inputs (one of):
  --bpm  N         Use a specific BPM number directly
  --song PATH      Detect BPM from an audio/video file (uses librosa beat_track)

Sound presets:
  kick_wood  (default)  Kick drum + woodblock — blends with most pop/kpop/melodic music
  pure_click            Sharp sine clicks — classic digital metronome, solo practice
  woodblock             Wooden temple-block — warm, organic, doesn't compete with melody
  shaker                Soft filtered noise — subtle, good for slow practice
  cowbell               Bright bell with metallic ring — cuts through loud music

Special preset modes:
  --preset auto         Pick a preset based on the music's spectral character
                        (requires --song; falls back to kick_wood without song)
  --all                 Generate one file per preset (5 files), all at the same BPM

Output is m4a by default. Supports .mp3 and .wav via the output extension.

Examples:
  python3 generate_metronome.py --bpm 143.6
  python3 generate_metronome.py --song "贱侠.m4a"
  python3 generate_metronome.py --song "贱侠.m4a" --preset auto
  python3 generate_metronome.py --song "贱侠.m4a" --all
  python3 generate_metronome.py --bpm 120 --preset cowbell --output click.m4a
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 44100
TOTAL_BEATS = 32          # always 4 eight-counts
BEATS_PER_MEASURE = 4     # always 4/4


# ---------- sound presets ----------

def _kick(duration=0.18):
    n = int(duration * SR); t = np.arange(n) / SR
    freq = 50 + 70 * np.exp(-t * 30)
    body = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 12)
    cn = int(0.005 * SR); body[:cn] += np.random.randn(cn) * np.linspace(1, 0, cn) * 0.3
    return body * 0.95

def _woodblock(duration=0.12, accent=False):
    n = int(duration * SR); t = np.arange(n) / SR
    f1 = 1100 if accent else 850
    tone = (np.sin(2 * np.pi * f1 * t) * np.exp(-t * 35) * 0.6 +
            np.sin(2 * np.pi * f1 * 2 * t) * np.exp(-t * 50) * 0.3)
    nn = int(0.008 * SR); tone[:nn] += np.random.randn(nn) * np.linspace(1, 0, nn) * 0.4
    return tone * (0.7 if accent else 0.55)

def _pure_click(duration=0.05, accent=False):
    n = int(duration * SR); t = np.arange(n) / SR
    freq = 1800 if accent else 1200
    amp = 0.85 if accent else 0.5
    return amp * np.sin(2 * np.pi * freq * t) * np.exp(-t * 60)

def _shaker(duration=0.10, accent=False):
    n = int(duration * SR)
    noise = np.diff(np.random.randn(n), prepend=0) * 2  # crude high-pass
    env = np.exp(-np.arange(n) / SR * (25 if accent else 35))
    return noise * env * (0.7 if accent else 0.4)

def _cowbell(duration=0.18, accent=False):
    n = int(duration * SR); t = np.arange(n) / SR
    f1 = 540 if accent else 440
    partials = [(f1, 1.0), (f1 * 1.51, 0.6), (f1 * 2.13, 0.35), (f1 * 3.07, 0.15)]
    tone = sum(amp * np.sin(2 * np.pi * f * t) for f, amp in partials)
    return tone * np.exp(-t * (10 if accent else 18)) * (0.6 if accent else 0.42)


PRESETS = {
    "kick_wood":   {"downbeat": lambda: _kick(),                "other": lambda: _woodblock(accent=False)},
    "pure_click":  {"downbeat": lambda: _pure_click(accent=True),"other": lambda: _pure_click(accent=False)},
    "woodblock":   {"downbeat": lambda: _woodblock(accent=True),"other": lambda: _woodblock(accent=False)},
    "shaker":      {"downbeat": lambda: _shaker(accent=True),   "other": lambda: _shaker(accent=False)},
    "cowbell":     {"downbeat": lambda: _cowbell(accent=True),  "other": lambda: _cowbell(accent=False)},
}

PRESET_DESCRIPTIONS = {
    "kick_wood":  "kick drum + woodblock — blends with most music",
    "pure_click": "sharp sine clicks — classic digital metronome",
    "woodblock":  "wooden temple-block — warm and organic",
    "shaker":     "soft filtered noise — subtle and ambient",
    "cowbell":    "bright bell with metallic ring — cuts through loud music",
}


# ---------- BPM detection ----------

def detect_bpm(song_path):
    """Use librosa to estimate BPM. Falls back gracefully if the song has tempo drift."""
    import librosa
    y, sr = librosa.load(str(song_path), sr=22050)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    return float(tempo)


# ---------- Auto preset selection ----------

def auto_select_preset(song_path):
    """Pick a preset that complements the song's spectral character.

    Heuristic — we want the metronome audible but not clashing:
      - Quiet/acoustic music   → shaker (subtle)
      - Bright/percussive      → cowbell (cuts through)
      - Warm melodic           → woodblock (organic blend)
      - Default pop/kpop       → kick_wood
    """
    import librosa
    y, sr = librosa.load(str(song_path), sr=22050, duration=60, offset=20)
    if len(y) == 0:
        return "kick_wood", "fallback (couldn't load enough audio)"

    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    rms = float(np.mean(librosa.feature.rms(y=y)))
    y_h, y_p = librosa.effects.hpss(y)
    h_e = float(np.sum(y_h ** 2)); p_e = float(np.sum(y_p ** 2)) + 1e-9
    h_pct = h_e / (h_e + p_e)

    # Decision tree (with reason logged)
    if rms < 0.04:
        return "shaker", f"low energy (rms={rms:.3f}) — subtle preset"
    if centroid > 3800 or h_pct < 0.4:
        return "cowbell", f"bright/percussive (centroid={centroid:.0f}Hz, h_pct={h_pct:.2f}) — cuts through"
    if h_pct > 0.7 and centroid < 2500:
        return "woodblock", f"warm melodic (h_pct={h_pct:.2f}, centroid={centroid:.0f}Hz) — organic blend"
    return "kick_wood", f"default for melodic pop (centroid={centroid:.0f}Hz, h_pct={h_pct:.2f})"


# ---------- render & write ----------

def render(bpm, preset_name):
    p = PRESETS[preset_name]
    beat_dur = 60.0 / bpm
    total_samples = int((TOTAL_BEATS * beat_dur + 0.05) * SR)
    audio = np.zeros(total_samples, dtype=np.float32)
    for i in range(TOTAL_BEATS):
        pos = int(i * beat_dur * SR)
        click = p["downbeat"]() if i % BEATS_PER_MEASURE == 0 else p["other"]()
        end = min(pos + len(click), total_samples)
        audio[pos:end] += click[:end - pos]
    return np.tanh(audio * 0.9)


def write_wav(audio, path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((audio * 32767).astype(np.int16).tobytes())


def encode(wav_path, out_path):
    out_path = Path(out_path); ext = out_path.suffix.lower()
    if ext == ".wav":
        shutil.copyfile(wav_path, out_path); return
    cmd = ["ffmpeg", "-y", "-i", str(wav_path)]
    if ext == ".m4a":  cmd += ["-c:a", "aac", "-b:a", "192k"]
    elif ext == ".mp3": cmd += ["-c:a", "libmp3lame", "-b:a", "192k"]
    else: raise ValueError(f"Unsupported extension: {ext}")
    cmd += [str(out_path)]
    subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)


def render_and_write(bpm, preset_name, output_path):
    audio = render(bpm, preset_name)
    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "out.wav"
        write_wav(audio, wav_path)
        encode(wav_path, output_path)
    return len(audio) / SR


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--bpm", type=float, help="Tempo in BPM (e.g., 120, 143.6)")
    src.add_argument("--song", type=str, help="Path to audio/video file; BPM auto-detected")

    ap.add_argument("--preset", default="kick_wood",
                    choices=list(PRESETS) + ["auto"],
                    help="Sound preset (default kick_wood). Use 'auto' to pick from --song characteristics.")
    ap.add_argument("--all", action="store_true",
                    help="Generate one file per preset (5 files). Overrides --preset.")
    ap.add_argument("--output", "-o", default=None,
                    help="Output path. Extension picks format (.m4a/.mp3/.wav). "
                         "Default: metronome_<bpm>bpm_<preset>.m4a in cwd. "
                         "With --all, used as a directory if it has no extension.")
    args = ap.parse_args()

    # Resolve BPM
    if args.bpm is not None:
        bpm = args.bpm
        bpm_source = f"specified {bpm} BPM"
    else:
        bpm = detect_bpm(args.song)
        bpm_source = f"detected {bpm:.1f} BPM from {Path(args.song).name}"

    # Resolve preset(s)
    if args.all:
        presets = list(PRESETS)
        preset_explain = ""
    elif args.preset == "auto":
        if args.song is None:
            print("WARN: --preset auto requires --song; falling back to kick_wood.", file=sys.stderr)
            presets = ["kick_wood"]
            preset_explain = " (auto fallback: kick_wood)"
        else:
            chosen, reason = auto_select_preset(args.song)
            presets = [chosen]
            preset_explain = f" (auto: {chosen} — {reason})"
    else:
        presets = [args.preset]
        preset_explain = ""

    # Resolve output path(s)
    bpm_str = f"{bpm:g}".replace(".", "p")

    def default_name(preset):
        return f"metronome_{bpm_str}bpm_{preset}.m4a"

    if args.all:
        # If --output looks like a directory, use it; else use cwd
        if args.output and Path(args.output).suffix == "":
            out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
        else:
            out_dir = Path.cwd()
        outputs = [(p, out_dir / default_name(p)) for p in presets]
    else:
        out_path = Path(args.output) if args.output else Path.cwd() / default_name(presets[0])
        outputs = [(presets[0], out_path)]

    # Generate
    print(f"BPM: {bpm_source}{preset_explain}")
    for preset, out_path in outputs:
        duration = render_and_write(bpm, preset, out_path)
        print(f"  [{preset}] {out_path}  ({duration:.2f}s)")


if __name__ == "__main__":
    main()
