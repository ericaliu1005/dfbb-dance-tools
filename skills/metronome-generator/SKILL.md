---
name: metronome-generator
description: |
  Generate a 4-eight-count (32 beat, 4/4) metronome / click-track audio file. Always
  trigger this skill when the user wants a metronome, count-in audio, intro click track,
  "节拍器", "导入节拍", "count-in", "count-off", or anything that sounds like "give me
  N beats at X bpm to count me in". Two input modes: (a) the user gives a BPM number
  directly, or (b) the user gives an audio/video file and the skill detects the BPM and
  optionally picks a sound preset that matches the song. Five sound presets available
  (kick_wood, pure_click, woodblock, shaker, cowbell), with an `auto` mode that picks
  from the song's spectral character, and an `--all` mode that generates one file per
  preset for the user to compare. Output is m4a in the user's workspace folder.
---

# Metronome Generator

Generates a 4-eight-count (32-beat, 4/4) metronome audio file with downbeat accents
every 4 beats. The length is fixed because that's the standard dance count-in — keep
it predictable. The script lives in `scripts/generate_metronome.py`.

## When this triggers

The user wants an audio file of clicks at a tempo. Common asks:

- "做一个 130 bpm 的节拍器"
- "give me a count-in for this song"
- "@贱侠.m4a 帮我做个 metronome 配它"
- "generate a click track at 100 bpm"
- "我想要 4 个八拍的导入节拍"

If the user says they want it spliced in front of music, generate the metronome
first, then concat with ffmpeg as a separate step (see "Common follow-ups" below).

## Input modes

The user can specify the tempo two ways:

1. **Direct BPM**: a number like `143.6` or `120`.
2. **Song file**: an audio/video file. The script auto-detects BPM via librosa.

## The 5 presets

| Preset       | Sound                              | Best for                                          |
|--------------|------------------------------------|---------------------------------------------------|
| `kick_wood`  | Kick drum + woodblock (**default**)| Blends with most music — pop, kpop, melodic       |
| `pure_click` | Sharp sine clicks                  | Solo practice, no music, classic digital feel     |
| `woodblock`  | Wooden temple-block                | Warm, organic — for melodic, harmonic music       |
| `shaker`     | Soft filtered noise                | Slow / quiet practice, ambient, non-intrusive     |
| `cowbell`    | Bright bell with metallic ring     | Cuts through loud or percussive music             |

### Two special modes

- **`--preset auto`** — when the user provides a song, the script analyzes its
  spectral character (brightness, harmonic vs percussive ratio, overall energy) and
  picks one preset. Quiet songs → shaker; bright/percussive → cowbell; warm
  melodic → woodblock; default melodic pop → kick_wood. The script logs *why* it
  chose what it chose, so you can pass that explanation along to the user.

- **`--all`** — generate one file per preset (5 files). Useful when the user wants
  to A/B different sounds and pick by ear.

## Workflow

When this skill triggers, **don't run anything yet**. Confirm these up front (use
`AskUserQuestion` if available — Claude Code / Cowork — otherwise just ask in chat).
Combine the unknowns into one batch. Skip questions the user already answered.

1. **Tempo source** (always confirm)
   - "用什么 BPM？直接给个数字 / 用一首歌的文件" → number or file path
   - If detecting from a song: beat trackers often lock onto **half or double time**
     (a 140 BPM kpop track reported as 70). The script prints a `WARN` with the
     octave alternative when the detection falls outside 90–190 BPM. When you see
     it, confirm the tempo with the user before generating, offering both values.
     If they're unsure, generate both (`--bpm 70` and `--bpm 140`) and let them pick.
2. **Preset choice** (only if user didn't already say)
   - Recommend `kick_wood` as default
   - If user gave a song, offer `auto` as an option
   - Mention `--all` if they seem unsure ("让我5种都听一下")
3. **Output filename** — only ask if the default would overwrite something in the
   workspace; otherwise let the script auto-name.

After running, share the file's absolute path (in Cowork, as a `computer://` link)
with a one-line summary: preset name, BPM, duration. Don't dump the ffmpeg log into the chat.

## Locating the script

Paths in this file are relative to this skill's directory (the folder containing this
SKILL.md). The shell's cwd is the user's workspace, **not** that folder, so build an
absolute path before running: take the directory you loaded this SKILL.md from and
append `scripts/...`. In Claude Code plugin installs that directory is
`${CLAUDE_PLUGIN_ROOT}/skills/metronome-generator/` when the variable is set; under Codex it is where
the skill was symlinked or copied (typically `~/.codex/skills/metronome-generator/`).

## Running the script

The script is at `scripts/generate_metronome.py`. Run it with `uv run` — the script
declares its Python dependencies inline and uv installs them into a cached
environment on first run. Only `ffmpeg` and `uv` need to be on PATH. If `uv` is
missing, fall back to `python3` with numpy, scipy and librosa installed manually.

```bash
# Direct BPM, default preset
uv run scripts/generate_metronome.py --bpm 143.6

# Direct BPM, specific preset, custom output path (always save to workspace folder)
uv run scripts/generate_metronome.py --bpm 120 --preset cowbell \
  --output "/Users/me/skills/dance-practice/click_120.m4a"

# From a song — auto-detect BPM, default preset
uv run scripts/generate_metronome.py --song "贱侠.m4a"

# From a song — auto-detect BPM AND auto-pick preset based on song style
uv run scripts/generate_metronome.py --song "贱侠.m4a" --preset auto

# Generate all 5 presets for A/B comparison (BPM detected from song)
uv run scripts/generate_metronome.py --song "贱侠.m4a" --all

# All 5 presets at a fixed BPM, written into a directory
uv run scripts/generate_metronome.py --bpm 130 --all --output ./metronomes/
```

The script prints the BPM source ("specified" vs "detected from <file>") and, for
auto preset, the reason it picked what it did. Surface that to the user — it
helps them trust the result. Any `WARN` line on stderr (half/double-time suspicion,
`--all` ignoring a filename) is meant for you to act on, not to hide.

## Common follow-ups

**"Splice this in front of the song"** — generate the metronome separately first,
then concat:
```bash
ffmpeg -y -i metronome.m4a -i song.m4a \
  -filter_complex "[0:a][1:a]concat=n=2:v=0:a=1[out]" \
  -map "[out]" -c:a aac -b:a 192k song_with_count_in.m4a
```
If the user complains the click sounds "faster/slower" than the music after
splicing, the issue is usually phase — the song's first beat doesn't land at t=0.
Trim the song's pre-beat lead-in (use librosa's `beat_track` to find the offset)
before concat-ing.

**"Make it shorter / longer"** — the length is fixed at 4 eight-counts on purpose.
If the user really needs a different length, generate the file then trim/loop it
with ffmpeg in a separate step. Don't add length flags back to the script unless
asked.

**"Change the time signature"** — the script is 4/4 only. For 3/4 (waltz) or 6/8,
this skill isn't the right tool — say so and offer to write a one-off ffmpeg
recipe instead.

## Output etiquette

- Save outputs to the user's **workspace folder** (the directory currently mounted
  as their project), not `/tmp`. The default filename pattern
  `metronome_<bpm>bpm_<preset>.m4a` is informative — keep it unless the user
  asked for something specific.
- Share the absolute path (Cowork: `computer://` link), not file content dumps.
- One-line post-script: `<path>  <preset> · <bpm> BPM · 4 eight-counts (Xs)`.
