---
name: dance-video-tools
description: |
  Tools for transforming dance videos for practice — slow them down to a target speed
  (% of original), horizontally mirror them, or both. Output long side is capped at
  1920 (1080p landscape, 1080x1920 portrait), never upscaled. Both transforms are independent — the user can ask for slowdown only, mirror only, or
  both. Always trigger when the user says things like "把原版降到 X%", "帮我降速",
  "slowdown the original", "mirror the original", "镜像一下", "把视频翻转", "slow this
  down to 80%", "make me a 60% speed practice video", "give me a mirrored version",
  "just the chorus at 70%", "从 1:05 到 1:30 降到 60%", "只要这一段", or anything about
  adjusting a dance video (or a section of one) for practice review. Designed to expand —
  if more video tools (trim, stack, subtitle, etc.) are added later, they'll go here.
---

# Dance Video Tools

Tools for transforming dance videos so they're easier to learn / practice with. Right
now: slow down + mirror. Designed to grow — anything else dance-video-related (trim,
stack two videos side-by-side, add subtitles, etc.) belongs here too.

Slows down a video to a target speed and/or horizontally mirrors it. Both transforms
are independent — the user can ask for slowdown only, mirror only, or both. The long
side is capped at 1920, so landscape comes out 1920x1080 and portrait phone footage
stays portrait at 1080x1920. Smaller inputs are never upscaled. 4K/8K originals take
too long to re-encode for practice review purposes.

## When this triggers

the user wants a slower and/or mirrored version of a dance video to practice with.
Common phrasings:

- "把原版降到 80%"
- "帮我降速"
- "slowdown the original to 60%"
- "mirror this video" / "镜像一下"
- "make a 75% mirror version"
- "just give me a mirrored version" (mirror-only — no slowdown)
- "1:05 到 1:30 这一段降到 60%" / "just the chorus at 70%" (section only)

If they gave a percentage but aren't sure what speed to use, run
`estimate-dance-speed` first to figure out what speed they danced at.

## Interactive flow

When this skill triggers, **don't run anything yet**. Confirm these up front (use
`AskUserQuestion` if available — Claude Code / Cowork — otherwise just ask in chat):

1. **Input file** — show detected `.mp4/.MOV/.mkv` files in the workspace.
2. **What to do** — slowdown / mirror / both (skip if the user already specified).
3. **Speed** — what % (only if slowdown is part of the ask).
4. **Mirror** — yes / no (only if not already implied).
5. **Section** — only if the user mentioned a part of the song ("the chorus", "from
   1:05"). Get start and end timestamps in the **original** video's time. If they
   name a part but not timestamps, ask for them; don't guess.

Skip questions the user already answered. At least one of speed-not-1.0 or mirror must
be set, or the script will refuse (nothing to do).

## Locating the script

Paths in this file are relative to this skill's directory (the folder containing this
SKILL.md). The shell's cwd is the user's workspace, **not** that folder, so build an
absolute path before running: take the directory you loaded this SKILL.md from and
append `scripts/...`. In Claude Code plugin installs that directory is
`${CLAUDE_PLUGIN_ROOT}/skills/dance-video-tools/` when the variable is set; under Codex it is where
the skill was symlinked or copied (typically `~/.codex/skills/dance-video-tools/`).

## Running

The script is at `scripts/slowdown_video.py`. It depends on `ffmpeg` only — no Python
packages. `uv run` and `python3` both work; `uv run` is used below for consistency
with the other skills.

```bash
# Slowdown only
uv run scripts/slowdown_video.py --input "original.mp4" --speed 0.75

# Slowdown + mirror
uv run scripts/slowdown_video.py --input "original.mp4" --speed 0.75 --mirror

# Mirror only (--speed defaults to 1.0)
uv run scripts/slowdown_video.py --input "original.mp4" --mirror

# Custom output path
uv run scripts/slowdown_video.py --input "original.mp4" --speed 0.80 --mirror \
  --output "~/dance-videos/practice_80.mp4"

# Only a section: 1:05–1:30 of the original at 60% (--duration is INPUT seconds,
# so 25 s of source becomes ~41.7 s of output). Name the output yourself — the
# auto-name doesn't encode the section.
uv run scripts/slowdown_video.py --input "original.mp4" --speed 0.60 \
  --start 65 --duration 25 --output "original_chorus_60%.mp4"
```

`--start` / `--duration` take seconds in the original's timeline; convert `m:ss`
before passing (1:05 → 65). Omit `--duration` to run to the end.

Output is auto-named based on what was applied:

| Speed | Mirror | Output                       |
|-------|--------|------------------------------|
| 60%   | no     | `original_60%.mp4`           |
| 60%   | yes    | `original_60%_mirror.mp4`    |
| 100%  | yes    | `original_mirror.mp4`        |

The script uses x264 `preset=fast crf=20` by default — good quality with reasonable
speed. `--preset ultrafast` is several times faster at a small file-size cost, fine
for practice videos.

## Long videos and shell timeouts

A full re-encode of a 3–4 minute video takes a few minutes. Before reaching for
chunking, use the runtime's own tools:

- **Claude Code**: run the script with `run_in_background` (or raise the Bash
  `timeout` — max 10 minutes) and add `--preset ultrafast`.
- **Codex**: run it in the background and poll, or add `--preset ultrafast`.

Only if the runtime hard-kills long commands (some sandboxes cap at ~45 s) fall back
to chunked encoding. Use the script's own `--start` / `--duration` (input seconds) so
every chunk shares the exact same filter chain, then concat:

```bash
S=/abs/path/to/skills/dance-video-tools/scripts/slowdown_video.py
uv run "$S" --input original.mp4 --speed 0.9 --mirror --preset ultrafast --start 0   --duration 100 --output /tmp/part1.mp4
uv run "$S" --input original.mp4 --speed 0.9 --mirror --preset ultrafast --start 100 --duration 100 --output /tmp/part2.mp4
uv run "$S" --input original.mp4 --speed 0.9 --mirror --preset ultrafast --start 200                --output /tmp/part3.mp4
printf "file '/tmp/part1.mp4'\nfile '/tmp/part2.mp4'\nfile '/tmp/part3.mp4'\n" > /tmp/concat.txt
ffmpeg -y -f concat -safe 0 -i /tmp/concat.txt -c copy "original_90%_mirror.mp4"
```

Don't hand-write the ffmpeg filter chain — the script owns it.

## atempo edge case

`atempo` accepts speeds in `[0.5, 2.0]`. The script auto-chains atempo filters for
speeds outside that range (e.g., 0.40 → `atempo=0.5,atempo=0.8`).

## Output etiquette

- Save to the workspace folder, not `/tmp`.
- Share the output's absolute path with one short summary line: speed, mirror, section
  (if any), duration. In Cowork, render the path as a `computer://` link.
- Don't dump ffmpeg progress logs.
