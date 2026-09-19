# Changelog

## 0.2.0 — 2026-09-19

### Changed
- **Install:** scripts now declare their Python dependencies inline (PEP 723) and run via `uv run`. Prerequisites are `ffmpeg` + `uv`; no more `pip install`. Plain `python3` still works as a fallback.
- **dance-video-tools:** output caps the long side at 1920 instead of forcing 1920x1080. Portrait phone footage stays portrait (1080x1920) with no black bars; smaller inputs are no longer upscaled.
- **estimate-dance-speed:** default search range widened to 55%–100% (was 70%–100%). Reported offset is now in practice-recording seconds; previously it was scaled by the detected speed.
- **metronome-generator:** ffmpeg failures now surface the ffmpeg error instead of an empty exception.

### Added
- **dance-video-tools:** `--start` / `--duration` to process only a section of the input — practice one chorus at 60%, or chunk a long encode.
- **estimate-dance-speed:** warns when the best match sits at the edge of the search range.
- **metronome-generator:** warns when a detected BPM looks like half- or double-time and prints the octave alternative.
- `tests/test_synthetic.py` — self-contained regression suite (synthesizes its own audio/video).
- GitHub Actions CI running the test suite.
- LICENSE file (MIT, as already stated in README).

## 0.1.0 — 2026-05-10

Initial release: `estimate-dance-speed`, `dance-video-tools`, `metronome-generator`.
