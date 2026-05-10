# dfbb-dance-tools

Three skills built by [DFBB Dance Crew](https://www.youtube.com/@dfbbdance) for
practicing dance covers — handling speed estimation, video slowdown / mirroring, and
metronome / count-in audio. Cross-compatible: works in Claude Code / Cowork
(Anthropic) and Codex CLI (OpenAI). Shared publicly under MIT.

## What's inside

Three skills that auto-trigger from how you describe what you want:

### `estimate-dance-speed`

You recorded yourself dancing along to an original song — but slowed down. How slow
were you actually going? Compares the practice audio to the original via
cross-correlation of onset envelopes. Auto-detects the offset (when the music starts
in your recording), so no need to pre-trim.

> *"I think I danced at like 80% but I'm not sure"* → `estimate-dance-speed` →
> `0.78x, confidence 0.95`

### `dance-video-tools`

Slow down a video to a target speed and/or horizontally mirror it. Outputs 1080p.
Both transforms are independent — ask for slowdown only, mirror only, or both.

> *"Make me a 75% mirror version of the dance practice video"* →
> `dance-video-tools` → `original_75%_mirror.mp4`

Designed to grow — anything else dance-video-related (trim, stack two videos
side-by-side, add subtitles) belongs here.

### `metronome-generator`

Generate a 4-eight-count (32-beat, 4/4) metronome / count-in audio file. Two input
modes: give a BPM number directly, or hand it a music file and the BPM is
auto-detected. Five sound presets (kick + woodblock, sharp click, woodblock, shaker,
cowbell) plus an `auto` mode that picks based on the music's spectral character.

> *"Make me a count-in for this song"* → BPM detection → metronome at the right
> tempo, in a sound that blends with the song.

## Prerequisites

The scripts shell out to `ffmpeg` and a few Python audio libraries. Install once:

**macOS** (Homebrew):

```bash
brew install ffmpeg
pip3 install numpy librosa scipy
```

**Linux** (Debian / Ubuntu):

```bash
sudo apt install ffmpeg python3-pip
pip3 install numpy librosa scipy
```

**Windows** — install [ffmpeg](https://ffmpeg.org/download.html) and add it to
PATH, then `pip install numpy librosa scipy`.

If something's missing when you run a skill, the error message tells you what to
install.

## Install

### Claude Code (CLI)

```
/plugin marketplace add ericaliu1005/dfbb-dance-tools
/plugin install dfbb-dance-tools@dfbb-dance-tools
```

To pull updates later: `/plugin marketplace update dfbb-dance-tools`.

### Claude Cowork (desktop app)

1. Run `/plugin` to open the plugin manager.
2. In the **Marketplaces** tab, click **Add marketplace** and paste:
   `https://github.com/ericaliu1005/dfbb-dance-tools`
3. Switch to the **Discover** tab and install `dfbb-dance-tools`.

Third-party marketplaces have auto-update **disabled** by default — open the
marketplace in the Marketplaces tab and toggle **Enable auto-update** if you want
new versions to arrive automatically when we push them.

### Codex CLI (OpenAI)

Codex Agent Skills uses the same SKILL.md format. Two install paths:

**User-level (recommended)** — symlink so updates flow through automatically:

```bash
git clone https://github.com/ericaliu1005/dfbb-dance-tools.git ~/dfbb-dance-tools
ln -s ~/dfbb-dance-tools/skills/estimate-dance-speed ~/.codex/skills/
ln -s ~/dfbb-dance-tools/skills/dance-video-tools     ~/.codex/skills/
ln -s ~/dfbb-dance-tools/skills/metronome-generator   ~/.codex/skills/
```

To update later: `cd ~/dfbb-dance-tools && git pull`.

**Project-level** — copy the skills folder into your project:

```bash
cp -r dfbb-dance-tools/skills/* /path/to/your/project/.codex/skills/
```

Once installed, the skills auto-trigger when you describe what you want — no need to
remember command names.

## License

MIT — fork it, modify it, share with your own crew. PRs welcome.
