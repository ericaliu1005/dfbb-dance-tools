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
packages. (`scripts/check_av_sync.py`, used in the verification step below, also needs
`numpy`; `uv run` fetches it automatically.) `uv run` and `python3` both work; `uv run` is used below for consistency
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

The script uses x264 `preset=fast crf=20` by default. For a practice video, prefer
`--preset veryfast` — on a 4-core machine a 3-minute 1080p slowdown finishes in about
75 seconds, which fits inside almost any command timeout. `--preset ultrafast` is
faster still at a noticeable file-size cost.

## Encode in ONE pass — never chunk and concat

**Always encode the whole video in a single command.** Do not split the input into
parts, encode them separately, and stitch them with `ffmpeg -f concat`.

Chunk + concat silently corrupts the result: each chunk contributes roughly one extra
frame, so the picture falls about **1 frame per chunk further behind its own audio**.
A 3-minute video cut into six 30-second chunks comes out ~4 frames (0.13 s) out of
sync by the end, and the slip grows steadily rather than being a constant offset. The
file looks fine on its own — the damage only shows when it is stacked against a
practice recording in an editor, where every section needs a different nudge. This was
measured on real output, not theorized; it is the single worst failure mode of this
skill.

If a full-length encode is too slow for the runtime's command timeout:

1. Add `--preset veryfast` (then `--preset ultrafast`) — usually enough on its own.
2. **Claude Code**: run with `run_in_background`, or raise the Bash `timeout` (max
   10 minutes) and poll.
3. Some sandboxes kill background processes when the tool call returns, and `nohup` /
   `setsid` do not save them. Verify a background job actually survives before relying
   on it; if it does not, raise the timeout instead.
4. If none of that is enough, tell the user the file is too long to encode here and
   give them the single-pass ffmpeg command to run locally. **Shipping a
   chunk-concatenated file is worse than shipping nothing** — it wastes a whole
   practice session before anyone notices.

Sectioning with `--start` / `--duration` is unaffected: one encode, one output, no
concat. That is a legitimate use.

## Verify before handing the file over

After any slowdown, run the checker. It samples frames and audio from the output,
matches them against the source, and fits `source_t = slope * out_t`. Both the video
and audio slopes must equal the intended speed, and the two must agree with each
other.

```bash
uv run scripts/check_av_sync.py --source "original.mp4" \
  --output "original_90%.mp4" --speed 0.9
# add --mirror if the output was mirrored, or the video check is meaningless
```

Passing output (exit 0):

```
  video : source_t = 0.90000 * out_t + +0.000   (max residual 0 ms)
  audio : source_t = 0.90000 * out_t + +0.011   (max residual 4 ms)
  OK — both tracks hold 90.00% within 33 ms over 184 s.
```

A drift report (exit 1) means the file is not usable for side-by-side comparison —
re-encode in a single pass rather than handing it over with a caveat. Report the
result to the user in one line; do not paste the whole output unless it failed.

## atempo edge case

`atempo` accepts speeds in `[0.5, 2.0]`. The script auto-chains atempo filters for
speeds outside that range (e.g., 0.40 → `atempo=0.5,atempo=0.8`).

## Output etiquette

- Save to the workspace folder, not `/tmp`.
- Share the output's absolute path with one short summary line: speed, mirror, section
  (if any), duration. In Cowork, render the path as a `computer://` link.
- Don't dump ffmpeg progress logs.
- Say that the output was sync-verified, in the same line as the summary.
