# dfbb-dance-tools

This repository ships three vendor-agnostic agent skills for dance practice
workflows. Each skill is a self-contained directory under `skills/` with a
`SKILL.md` (YAML frontmatter `name` + `description`) and accompanying Python
scripts under `scripts/`.

## Skills available

- `skills/estimate-dance-speed/` — figure out what speed (% of original) a
  practice was recorded at, by audio cross-correlation
- `skills/dance-video-tools/` — slow down a video, mirror it, or both (always
  outputs 1080p)
- `skills/metronome-generator/` — generate a 4-eight-count metronome / count-in
  audio file at a target BPM (or auto-detect from a song file)

## Format

The SKILL.md format is identical to Anthropic's Claude Code Agent Skills and
OpenAI Codex Agent Skills — both runtimes pick the appropriate skill based on
the user's phrasing matching the skill `description`. Skills do not require any
runtime-specific frontmatter beyond `name` + `description`.

## Dependencies

Scripts depend on:
- `ffmpeg` on PATH
- Python 3 with `numpy`, `librosa`, `scipy` (`pip install librosa scipy`)

If a dependency is missing the script will fail with a clear error message.

## Cross-runtime install

This repo is also a Claude Cowork plugin marketplace (`.claude-plugin/plugin.json`
declares the plugin manifest). For Codex CLI, the recommended install is to
symlink the individual skills into `~/.codex/skills/` — see README.md.
