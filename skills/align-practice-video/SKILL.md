---
name: align-practice-video
description: |
  Line a practice recording up with the slowed reference video it was danced to, so
  the two can be stacked side by side in an editor (剪映, Premiere, Resolve) with no
  manual nudging. Measures the time offset across the whole song, warns when the two
  files drift apart instead of sitting at a constant offset, and renders a pre-trimmed
  copy of the practice that drops onto the timeline at position 0 already aligned.
  Also converts variable-frame-rate phone footage to constant frame rate on the way
  through. Always trigger when the user says things like "对齐练习视频", "跟原版对不齐",
  "自动对齐之后还是差一点", "帮我把练习视频和降速版对上", "align my practice video",
  "sync my practice to the reference", "they drift apart", "the sync is off in 剪映",
  "每段都要单独对齐", or anything about a practice recording not lining up with the
  video it was danced to.
---

# Align Practice Video

The user recorded themselves dancing to a slowed reference video and now wants the
two side by side in an editor. Editor auto-sync gets close but leaves a visible slip,
so people start cutting the practice into sections and nudging each one. That is
almost always the wrong fix — this skill finds the real number instead.

## When this triggers

- "对齐练习视频" / "跟降速版对不上" / "剪映自动对齐之后还是差一点"
- "我分段对齐了还是不准" (a strong signal something is actually wrong — see below)
- "align my practice with the 90% version"
- "the two clips drift apart toward the end"

## What actually goes wrong (check in this order)

1. **A constant offset.** Normal and expected: the recording starts before the music.
   One trim fixes the whole song. This is what the skill produces.
2. **A drifting offset** (the gap grows steadily). The two files are at different
   speeds. Almost always the reference is at fault — a slowdown encoded in chunks and
   concatenated gains about one frame per chunk, so its picture falls behind its own
   audio. Run `dance-video-tools`' `check_av_sync.py` on the reference and re-render
   it in a single pass before aligning anything.
3. **Variable frame rate in the practice footage.** iPhone recordings with Auto FPS on
   are VFR; an editor conforming them to a constant-rate timeline makes the picture
   slide against its own audio. The render below fixes this.
4. **Nothing is wrong with the files.** At 30 fps a clip can only be placed on whole
   frames, so up to half a frame (17 ms) of error is unavoidable. If the measured
   spread across the song is already under a frame, tell the user to stop nudging —
   every nudge is 33 ms, which is *larger* than the error they are chasing, and
   splitting the clip to nudge sections leaves gaps at the joins.

## Interactive flow

Confirm before running (use `AskUserQuestion` if available):

1. **Practice file** — the recording of the user dancing.
2. **Reference file** — the slowed video that was playing during practice. If the user
   is unsure which speed version they used, that matters: aligning against a different
   render than the one they danced to reintroduces the error.

If the user does not know what speed the practice was danced at, run
`estimate-dance-speed` first.

## Locating the script

Paths here are relative to this skill's directory. The shell's cwd is the user's
workspace, so build an absolute path: take the directory this SKILL.md was loaded
from and append `scripts/...`. In Claude Code plugin installs that is
`${CLAUDE_PLUGIN_ROOT}/skills/align-practice-video/` when the variable is set.

## Running

`scripts/align_practice.py` needs `ffmpeg` plus `numpy` / `scipy` / `librosa`,
declared inline (PEP 723) so `uv run` fetches them.

```bash
# Measure and render the aligned copy (the normal case)
uv run scripts/align_practice.py --practice "IMG_8087.MOV" --reference "MOON_90%.mp4"

# Just the number, no render
uv run scripts/align_practice.py --practice "p.MOV" --reference "r.mp4" --report-only

# Custom output
uv run scripts/align_practice.py --practice "p.MOV" --reference "r.mp4" \
  --output "practice_aligned.mp4"
```

It matches onset envelopes in ~20-second windows spread across the whole song,
discards windows that match poorly (intro, silence, chatter), and takes a robust
median — so one bad window cannot skew the result. A single window at the start is
exactly how this measurement goes wrong; do not replace it with one.

## Reading the output

```
    20s      +730 ms   corr 0.64
    39s      +728 ms   corr 0.78
   ...
 -> median offset +726 ms, spread 12 ms, drift across the song 16 ms
Offset: +726 ms  =  21.77 frames @ 30 fps
```

- **spread** and **drift** both small (under a frame) → constant offset, all good.
- **drift** large and growing monotonically → case 2 above. The script warns; fix the
  reference rather than rendering an aligned file that cannot work.

After rendering, the script re-measures its own output. Leftover error should be a
few milliseconds:

```
Leftover error: -0 ms (0.01 frames), window spread 12 ms
```

## Why the video and audio are trimmed by different amounts

Video is cut on whole frames — `21.77 frames` becomes 22. Audio is cut at the exact
offset, to the sample. That leaves picture and sound inside the rendered file a few
milliseconds apart (well under the ~40 ms anyone can perceive) and buys two things:
the audio waveforms line up perfectly in the editor, which is how the user visually
confirms the sync, and the picture lands as close to correct as a frame grid allows.

## Output etiquette

- Save next to the practice file, not `/tmp`.
- Report the offset, the leftover error after rendering, and where the file is — three
  short lines. In Cowork, render the path as a `computer://` link.
- If the measurement showed drift, lead with that instead of the file: an aligned
  render of a mismatched pair is not usable, and the user needs to know which file to
  re-make.
- If the spread was already sub-frame and the user has been nudging sections, say so
  plainly. Knowing the error is smaller than one frame is the answer, even though it
  means their manual work cannot be improved on.
