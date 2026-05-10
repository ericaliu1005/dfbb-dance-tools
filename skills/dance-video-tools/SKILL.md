---
name: dance-video-tools
description: |
  Tools for transforming dance videos for practice — slow them down to a target speed
  (% of original), horizontally mirror them, or both. Output is always 1080p. Both
  transforms are independent — the user can ask for slowdown only, mirror only, or
  both. Always trigger when the user says things like "把原版降到 X%", "帮我降速",
  "slowdown the original", "mirror the original", "镜像一下", "把视频翻转", "slow this
  down to 80%", "make me a 60% speed practice video", "give me a mirrored version",
  or anything about adjusting a dance video for practice review. Designed to expand —
  if more video tools (trim, stack, subtitle, etc.) are added later, they'll go here.
---

# Dance Video Tools

Tools for transforming dance videos so they're easier to learn / practice with. Right
now: slow down + mirror. Designed to grow — anything else dance-video-related (trim,
stack two videos side-by-side, add subtitles, etc.) belongs here too.

Slows down a video to a target speed and/or horizontally mirrors it. Both transforms
are independent — the user can ask for slowdown only, mirror only, or both. Always
outputs 1080p — 4K/8K originals take too long to re-encode for practice review
purposes.

## When this triggers

the user wants a slower and/or mirrored version of a dance video to practice with.
Common phrasings:

- "把原版降到 80%"
- "帮我降速"
- "slowdown the original to 60%"
- "mirror this video" / "镜像一下"
- "make a 75% mirror version"
- "just give me a mirrored version" (mirror-only — no slowdown)

If they gave a percentage but aren't sure what speed to use, run
`estimate-dance-speed` first to figure out what speed they danced at.

## Interactive flow

When this skill triggers, **don't run anything yet**. Confirm these up front (use
`AskUserQuestion` if available — Claude Code / Cowork — otherwise just ask in chat):

1. **Input file** — show detected `.mp4/.MOV/.mkv` files in the workspace.
2. **What to do** — slowdown / mirror / both (skip if the user already specified).
3. **Speed** — what % (only if slowdown is part of the ask).
4. **Mirror** — yes / no (only if not already implied).

Skip questions the user already answered. At least one of speed-not-1.0 or mirror must
be set, or the script will refuse (nothing to do).

## Running

The script is at `scripts/slowdown_video.py`. It depends on `ffmpeg` only.

```bash
# Slowdown only
python3 scripts/slowdown_video.py --input "original.mp4" --speed 0.75

# Slowdown + mirror
python3 scripts/slowdown_video.py --input "original.mp4" --speed 0.75 --mirror

# Mirror only (--speed defaults to 1.0)
python3 scripts/slowdown_video.py --input "original.mp4" --mirror

# Custom output path
python3 scripts/slowdown_video.py --input "original.mp4" --speed 0.80 --mirror \
  --output "~/dance-videos/practice_80.mp4"
```

Output is auto-named based on what was applied:

| Speed | Mirror | Output                       |
|-------|--------|------------------------------|
| 60%   | no     | `original_60%.mp4`           |
| 60%   | yes    | `original_60%_mirror.mp4`    |
| 100%  | yes    | `original_mirror.mp4`        |

The script always scales to 1080p and uses x264 `preset=fast crf=20` by default —
good quality with reasonable speed.

## Watch the timeout — chunk for large files

In a sandboxed environment with a ~45-second bash timeout, **a single ffmpeg call can
get killed mid-encode** for videos over ~3 minutes (especially with `preset=fast`).

If that happens, switch to chunked encoding: encode segments separately then concat.
The script doesn't do this automatically because it's typically not needed; do it
manually when needed.

```bash
# Encode first 100 seconds
ffmpeg -y -ss 0 -t 100 -i "original.mp4" \
  -vf "setpts=PTS/0.900000,hflip,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" \
  -af "atempo=0.900000" \
  -c:v libx264 -preset ultrafast -crf 20 \
  -c:a aac -b:a 192k \
  /tmp/part1.mp4

# Encode remainder (from 100s to end)
ffmpeg -y -ss 100 -i "original.mp4" \
  -vf "setpts=PTS/0.900000,hflip,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" \
  -af "atempo=0.900000" \
  -c:v libx264 -preset ultrafast -crf 20 \
  -c:a aac -b:a 192k \
  /tmp/part2.mp4

# Concat
printf "file '/tmp/part1.mp4'\nfile '/tmp/part2.mp4'\n" > /tmp/concat.txt
ffmpeg -y -f concat -safe 0 -i /tmp/concat.txt -c copy "original_90%_mirror.mp4"
```

`preset=ultrafast` is much faster than `preset=fast` at a small file-size cost — fine
for practice videos. Use it when chunking.

## atempo edge case

`atempo` accepts speeds in `[0.5, 2.0]`. The script auto-chains atempo filters for
speeds outside that range (e.g., 0.40 → `atempo=0.5,atempo=0.8`).

## Output etiquette

- Save to the workspace folder, not `/tmp`.
- Share via `computer://` link — one short summary line: speed, mirror, duration.
- Don't dump ffmpeg progress logs.
