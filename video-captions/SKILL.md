---
name: video-captions
description: "Write and burn natural, native-feeling captions into a video whose audio already contains the voiceover. You supply the video + the spoken script; the skill transcribes the audio for word-level timing, aligns the script to it, breaks it into human-quality cues, and bakes them in with ffmpeg. Use for: 'add captions to this video', 'caption this ad', 'burn in subtitles', 'subtitle this VSL/UGC/reel', 'add English/German/Spanish captions'. For a video that ALREADY has captions burned in that must be hidden, use video-captions-cover instead."
---

# Video captions (clean video)

For a video with **no captions burned in yet**. Produces a rounded translucent plate that
hugs the text — the standard DTC / UGC caption look.

Non-negotiable: **the script text is what appears on screen.** The audio is used only for
timing. Never re-word, translate, or "fix" the user's script — spelling, punctuation, ellipses
and and spoken fillers ("look –", "I mean…", "so yeah", or "also –", "tja…" in German) all ship
verbatim, because that is what makes captions read as native rather than machine-made.

## Inputs

1. A video file whose audio track already contains the voiceover.
2. The spoken script as text (usually pasted in the message).

That's it. Everything else is derived.

## Run it

**Step 1 — one-time env** (skip if `~/.cache/caption-venv` exists):

```bash
python3 -m venv ~/.cache/caption-venv && ~/.cache/caption-venv/bin/pip -q install numpy pillow
```

Also needs `ffmpeg` and `whisper-cli` on PATH (`brew install ffmpeg whisper-cpp`). The
1.6 GB whisper model auto-downloads to `~/.cache/whisper-models` on first use.

`$SKILL_DIR` = the folder holding this SKILL.md — normally `~/.claude/skills/video-captions`
(user-level install) or `<repo>/.claude/skills/` if it was vendored into a project.
Resolve it once, then reuse it.

**Step 2 — write the script to a file.** Use a heredoc so quotes/dashes/apostrophes survive.
Keep the user's paragraph breaks; they help the chunker. Put it in your scratchpad dir.

**Step 3 — run:**

```bash
~/.cache/caption-venv/bin/python \
  "$SKILL_DIR/scripts/caption.py" \
  --video "/path/in.mp4" --script script.txt --out "/path/out.mp4" \
  --style hug --lang en \
  --work "$SCRATCH/wk" --srt captions.srt --verify verify.png
```

`--lang` is the language spoken in the audio. Defaults to **`en`**; pass `de`, `fr`, `es`,
`it`, `nl`, `pt`, … for anything else. Infer it from the script the user pasted — don't ask.

**Step 4 — check the two numbers it prints, then look at the sheet.**

- `align   N script tokens, XX% exact word match` — expect **>95%**. Below 80% it warns:
  that means the script does not match the audio. Stop and tell the user rather than
  shipping captions that drift.
- `cues    N  track A -> B` — B should land near where speech ends.

Then `Read` the `verify.png` contact sheet (one frame per cue). Crop it into ~1400px slices
with `magick verify.png -crop x1400+0+OFFSET +repage slice.png` and read those. You are
checking: text matches the moment, no line-break awkwardness, plate not colliding with a
face or an on-screen graphic.

**Step 5 — deliver.** Copy the mp4 + srt into a project folder and give the user the
containing folder as a bare `file://` URL (see master CLAUDE.md), plus a one-line note on
cue count and the sync spot-checks.

## Verify sync properly

Alignment can be confidently wrong. Spot-check 3 points spread across the video by cutting
the audio and re-transcribing that slice — the words should match the cue at that time:

```bash
ffmpeg -y -v error -ss 61.06 -t 2.2 -i "$WK/audio.wav" ck.wav
whisper-cli -m ~/.cache/whisper-models/ggml-large-v3-turbo.bin -f ck.wav -l en -np -nt
```

## Knobs

| Flag | Default | When to touch it |
|---|---|---|
| `--box-bottom-frac` | `0.862` | Vertical placement. For 9:16 this sits just above the Reels/TikTok UI. Raise toward `0.80` if the plate covers a chin or a logo; lower if it clashes with UI. |
| `--box-bottom` | — | Absolute px, overrides the frac. |
| `--max-line-frac` | `0.815` | Max text width as a fraction of video width. Lower = narrower captions, more lines. |
| `--font-size` | `62 × width/1080` | Scales with width automatically; override for a different look. |
| `--alpha` | `0.66` | Plate opacity. |
| `--hold` | `0.80` | Longest speech pause the caption stays up across without blinking. |
| `--crf` | `19` | Quality. 19 is visually transparent; 23 for a smaller file. |
| `--dry-run` | — | Print cues and stop. **Use this first on a long video** to sanity-check breaks before spending an encode. |

Audio is stream-copied, never re-encoded. Video goes to H.264 high/4.1 + faststart, which
is what Meta and TikTok want.

## How it works (so you can debug it)

1. `ffprobe` for dimensions/fps/duration; all geometry scales off width ÷ 1080.
2. Audio → 16 kHz mono → `whisper-cli` with `-ml 1 --split-on-word -dtw large.v3.turbo`
   for per-word timestamps.
3. The script is tokenised and aligned onto those words with `difflib.SequenceMatcher`.
   Numerals are normalised ("12" ↔ "zwölf") so digits in the script still match spoken
   words. Unmatched runs get their timing interpolated.
4. Cues are cut by dynamic programming **per sentence** — a cue never spans a sentence
   boundary. The cost function balances line fill, 1-vs-2 lines, cue duration, a 21
   char/sec reading ceiling, and rewards breaking at commas and dashes.
5. Line wrapping refuses to break after a preposition or article, refuses orphan words,
   and prefers balanced line widths.
6. One RGBA PNG per cue → chained `overlay ... enable='between(t,s,e)'` filters, written to
   a file and passed as `-/filter_complex` so cue count is not limited by arg length.

## Gotchas

- **Wrong script for the audio** is the #1 failure. The match % catches it.
- **A caption is not a graphic.** If the video has burned-in *artwork* in another language
  (a banner, a logo, an end-card), this skill will not touch it. Flag it to the user.
- Helvetica Neue Bold is the default face (macOS). On another machine pass
  `--font /path/to/font.ttf --font-index 0`.
- If the video has no audio track, or the audio is not the language you passed, whisper
  returns garbage and the match % collapses. Read the % before trusting anything.
