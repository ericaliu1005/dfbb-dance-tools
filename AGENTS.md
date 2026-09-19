# dfbb-dance-tools

This repository ships three vendor-agnostic agent skills for dance practice
workflows. Each skill is a self-contained directory under `skills/` with a
`SKILL.md` (YAML frontmatter `name` + `description`) and accompanying Python
scripts under `scripts/`.

## Skills available

- `skills/estimate-dance-speed/` — figure out what speed (% of original) a
  practice was recorded at, by audio cross-correlation
- `skills/dance-video-tools/` — slow down a video, mirror it, or both (long side
  capped at 1920; portrait stays portrait; never upscaled)
- `skills/metronome-generator/` — generate a 4-eight-count metronome / count-in
  audio file at a target BPM (or auto-detect from a song file)

## Format

The SKILL.md format is identical to Anthropic's Claude Code Agent Skills and
OpenAI Codex Agent Skills — both runtimes pick the appropriate skill based on
the user's phrasing matching the skill `description`. Skills do not require any
runtime-specific frontmatter beyond `name` + `description`.

## Script paths

Each SKILL.md refers to its scripts as `scripts/<name>.py`, relative to the skill
directory. The agent's shell cwd is the user's workspace, so SKILL.md instructs the
agent to resolve an absolute path from wherever the SKILL.md was loaded. Keep that
convention when adding scripts; never assume cwd.

## Dependencies

Every script carries PEP 723 inline metadata (`# /// script` block at the top)
declaring `requires-python` and its Python dependencies. SKILL.md tells the agent
to run scripts with `uv run <script>`, which resolves and caches those dependencies
automatically; the only system prerequisites are `ffmpeg` and `uv` on PATH.
`slowdown_video.py` declares no Python dependencies (ffmpeg only).

When adding a script: include the metadata block, keep `requires-python` in step
with what numba/librosa wheels support (currently `>=3.10,<3.14`), and reference
it in SKILL.md via `uv run`. Plain `python3` remains a documented fallback, so
don't rely on uv-only behavior inside the scripts.

If ffmpeg is missing the script fails with a clear error message.

## Tests

`tests/test_synthetic.py` synthesizes its own audio and video with numpy + ffmpeg,
so there are no fixtures to check in. It checks that speed estimation recovers a
known stretch factor and pre-roll, that the metronome renders the right duration
and detects a known BPM (octave-tolerant), and that video output keeps portrait
orientation. Run `uv run tests/test_synthetic.py` after changing any script. Under
plain `python3` the cases needing `librosa` skip themselves when it is missing.
GitHub Actions (`.github/workflows/test.yml`) runs the same command on every push
to `main` and every pull request.

## Releasing

The plugin version lives in two files that must match:
`.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`. Bump both. Add
a dated entry to `CHANGELOG.md` — marketplace users see the version, not the diff.

## Cross-runtime install

This repo is also a Claude Cowork plugin marketplace (`.claude-plugin/plugin.json`
declares the plugin manifest). For Codex CLI, the recommended install is to
symlink the individual skills into `~/.codex/skills/` — see README.md.
