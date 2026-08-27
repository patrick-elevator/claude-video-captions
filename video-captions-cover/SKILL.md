---
name: video-captions-cover
description: "Write and burn new captions into a video that ALREADY has captions burned in, sized and positioned to completely hide the old ones. You supply the video (audio already contains the new voiceover) + the spoken script. Use for: 'the old captions are still showing', 'cover the previous captions', 'this video has English/Dutch/Swedish captions on it', 'replace the burned-in subtitles', 'add captions over the existing ones', localising a video whose original captions could not be removed. For a clean video with no captions yet, use video-captions instead."
---

# Video captions (covering burned-in captions)

For a video where the **old captions are baked into the pixels** and cannot be removed. The
skill auto-detects the band they occupy and lays a **full-width opaque band** over it
carrying the new captions.

Non-negotiable: **the script text is what appears on screen.** The audio is used only for
timing. Never re-word or translate the user's script.

## Why the band is opaque and full-width — do not "improve" this

Both properties are forced by the pixels, not by taste. Overriding them reintroduces the bug:

- **Opaque.** A translucent plate over an existing translucent plate double-darkens, so the
  old text ghosts through *and* the old box's edges show as a rectangle inside yours. Tested:
  even at 88% opacity the old text is still legible on bright shots. Only fully opaque is clean.
- **Full width.** Old caption boxes run essentially edge to edge on long lines (measured
  x 9→1067 of 1080 on real footage). A rounded inset plate cannot contain them.

The result reads as a deliberate subtitle plate, which is a standard VSL/ad look. If the user
objects to the weight, the honest answer is that it's the price of hiding baked-in text —
the alternative is re-rendering the video from source.

## Inputs

1. The video, whose audio track already contains the **new** voiceover.
2. The spoken script as text.

## Run it

**Step 1 — one-time env** (skip if `~/.cache/caption-venv` exists):

```bash
python3 -m venv ~/.cache/caption-venv && ~/.cache/caption-venv/bin/pip -q install numpy pillow
```

Needs `ffmpeg` + `whisper-cli` (`brew install ffmpeg whisper-cpp`); the whisper model
auto-downloads on first use.

`$SKILL_DIR` = the folder holding this SKILL.md — normally `~/.claude/skills/video-captions-cover`
(user-level install) or `<repo>/.claude/skills/` if it was vendored into a project.
Resolve it once, then reuse it.

**Step 2 — write the script to a file** with a heredoc, keeping the user's paragraph breaks.

**Step 3 — run.** `--lang` is the language spoken in the audio; it defaults to **`en`**.
Infer it from the script the user pasted — don't ask.


```bash
~/.cache/caption-venv/bin/python \
  "$SKILL_DIR/scripts/caption.py" \
  --video "/path/in.mp4" --script script.txt --out "/path/out.mp4" \
  --style cover --lang en \
  --work "$SCRATCH/wk" --srt captions.srt --verify verify.png
```

**Step 4 — read the four lines it prints:**

```
align   368 script tokens, 99.5% exact word match      <- want >95%; <80% = wrong script, stop
cover   existing caption text y[1052,1225] on 597/597 sampled frames
cover   band y(1021, 1256) (235px), full width, 1 interval(s) totalling 119.4s
cover   verified: no uncovered moment inside any caption interval   <- must say this
```

If it says `WARNING: N uncovered moment(s)` the old captions will flash through. Fix by
raising `--hold` (default is already 999 for this style, so this should not happen) or by
extending the cue track manually.

If detection fails entirely it exits and asks for `--band-top/--band-bottom`.

**Step 5 — look at the verify sheet.** This is the step that actually proves the job.
`Read` `verify.png`, slicing it up:

```bash
magick verify.png -crop x1400+0+0 +repage s1.png     # then +0+1400, +0+2800 …
```

Scan every tile for **any** old-language text peeking above, below, or beside the band. One
leaked frame means the band is too small — nudge with `--band-top`/`--band-bottom`.

**Step 6 — deliver.** mp4 + srt into a project folder; hand the user the folder as a bare
`file://` URL, plus cue count, band geometry, and the sync spot-checks.

## Verify sync properly

Spot-check 3 points across the video — cut the audio and re-transcribe that slice:

```bash
ffmpeg -y -v error -ss 83.18 -t 2.0 -i "$WK/audio.wav" ck.wav
whisper-cli -m ~/.cache/whisper-models/ggml-large-v3-turbo.bin -f ck.wav -l en -np -nt
```

## Knobs

| Flag | Default | When to touch it |
|---|---|---|
| `--band-top` / `--band-bottom` | auto-detected | Override if detection is off or a tile shows a leak. Both must be given together; that also forces coverage across the whole video. |
| `--max-line-frac` | `0.815` | Max text width as a fraction of video width. |
| `--font-size` | `62 × width/1080` | Scales with width automatically. |
| `--hold` | `999` | Kept huge on purpose: the cue track stays continuous so the band never blinks off while an old caption is on screen. |
| `--crf` | `19` | 19 is visually transparent (SSIM ≈ 0.9999 outside the band). |
| `--dry-run` | — | Cues + detected band, no encode. Cheap way to check the band before committing. |

## How detection works

Frames are sampled at 5 fps in greyscale. Rows of near-white pixels are kept only when the
row is *dashed* — many white→black transitions along it — which separates letter strokes
from blobs like highlights, white coats, or bright skies. Surviving rows group into text
lines (filtered to a plausible line height), lines group into blocks of ≤3, and the biggest
block per frame is the caption. The band is the 1st/99th percentile of block top/bottom
across all frames, padded. Frames with a block also give the time intervals that must stay
covered.

The rest of the pipeline (whisper word timings → script alignment → per-sentence DP cue
chunking → PNG overlays via `-/filter_complex`) is identical to `video-captions`; see that
skill's SKILL.md for the detail.

## Gotchas

- **Check the audio is actually the new language before anything else.** A video "already
  swapped to German" that is still English will sail through whisper and produce a fluent
  English transcript — the give-away is the match % against the German script collapsing.
  Read the % first.
- **Graphics are not captions.** Burned-in banners, logos and end-cards in the old language
  sit outside the band and will survive. Always scan a few full frames and flag them; offer
  to overlay replacements as a separate job.
- Old captions can be up to 3 lines where yours are at most 2 — that is fine, the band is
  sized from the detected extent, not from your line count.
