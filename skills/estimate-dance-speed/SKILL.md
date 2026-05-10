---
name: estimate-dance-speed
description: |
  Estimate what speed (% of original) a dance practice was recorded at, by comparing
  the practice audio to the original song. Always trigger when the user says things
  like "帮我估一下跳了多少速", "我跳了多少速", "estimate my dance speed", "what speed did I
  dance", "compare my practice to the original", or anything about figuring out the
  practice tempo relative to the original. Auto-detects where the music starts in the
  practice — no need to pre-trim. Works with audio or video files.
---

# Estimate Dance Speed

Given an original song/video and a practice recording, figure out what speed (%) the
practice was danced at. Uses cross-correlation of onset envelopes — robust to mic
noise and room echo, and auto-detects the offset (when the music starts in the
practice).

## When this triggers

The user recorded a dance practice and wants to know what speed they were dancing at
relative to the original. Common phrasings:

- "帮我估一下跳了多少速"
- "estimate my dance speed"
- "我跳了多少速"
- "compare practice to original"

## Interactive flow

When this skill triggers, **don't run anything yet**. Confirm these up front (use
`AskUserQuestion` if available — Claude Code / Cowork — otherwise just ask in chat):

1. **Original file** — show detected `.mp4/.MOV/.mp3/.m4a` files in the workspace.
   If only one likely candidate, just confirm.
2. **Practice file** — same.
3. **Speed range** — "Do you have a rough idea of the speed?"
   - 55–90% (slow practice, default)
   - 70–100% (closer to full speed)
   - Custom

Skip questions the user already answered.

## Running

The script is at `scripts/estimate_dance_speed.py`. It depends on `librosa`, `numpy`,
`scipy` (`pip install librosa scipy --break-system-packages` if missing) and `ffmpeg`.

```bash
# Always run on the FULL practice file — no pre-trimming needed
python3 scripts/estimate_dance_speed.py \
  --original "original.mp4" \
  --practice "practice.MOV" \
  --min-speed 0.55 --max-speed 1.0
```

## Output

```
Estimated dance speed: 0.92x       ← report as 92% to the user
Estimated offset:      -9.12 sec   ← original music starts 9.12s into the practice
Confidence:            0.97        ← ≥0.70 reliable, <0.45 something's off
```

### Interpreting the offset

- **Negative offset** (e.g., `-9.12 sec`): practice has ~9 seconds of pre-roll
  before the music starts. The dance starts at that timestamp.
- **Near zero** (e.g., `+0.06 sec`): practice starts right at the music.
- **Positive offset**: original starts before the practice (rare — usually means
  the practice was trimmed mid-song).

You can casually mention the start time to the user — useful to know if they're
about to slowdown/mirror the practice itself.

## When confidence is low

If confidence < 0.45:
- Check both files are the same song
- Try a narrower speed range (e.g., `--min-speed 0.85 --max-speed 1.0`)
- As a last resort, manually trim heavy non-music noise from the start of the
  practice and rerun

## Output etiquette

After running, report concisely. In English:
> You danced at **92% speed** ✅ (confidence 0.97, music starts at 9.12s)

Or in Chinese:
> 你跳了 **92% 速度** ✅ (置信度 0.97, 音乐从 9.12 秒开始)

Match the user's language. Don't dump the full script output. If the user wants to
slow down the original to match, hand off to the `dance-video-tools` skill with the
detected speed.
