# Claude Code video caption skills

Burn natural, native-feeling captions into a video. You give Claude the **video** (its audio
already has the voiceover) and the **script**. That's the entire input — timing, line breaks,
font size, and placement are all worked out for you.

Two skills, and Claude picks the right one from how you ask:

| Skill | Use when |
|---|---|
| **video-captions** | The video has **no captions** yet. Adds a rounded translucent plate that hugs the text. |
| **video-captions-cover** | The video **already has captions burned into the pixels** that need hiding. Finds the band they sit in and lays an opaque band over it. |

---

## Install

Paste this into Claude Code:

```
Install the video caption skills from
https://github.com/patrick-elevator/claude-video-captions — clone it somewhere sensible,
run install.sh, and tell me when both skills are registered.
```

That's it. Claude clones the repo and runs the installer, which sets up the two skills,
`ffmpeg`, `whisper-cpp`, a small Python env, and downloads the speech model.

Prefer to do it yourself:

```bash
git clone https://github.com/patrick-elevator/claude-video-captions ~/src/claude-video-captions
bash ~/src/claude-video-captions/install.sh
```

Then **restart Claude Code**.

**Needs:** macOS, [Homebrew](https://brew.sh), and a one-time **1.6 GB** model download.
Re-running the installer is safe; it skips whatever is already done.

---

## Use it

Open Claude Code in any folder and ask in plain language.

### Video with no captions yet

```
Add captions to ~/Downloads/ad.mp4 — the German audio is already
in the video. Here's the script:

Was ist das für ein kleines Pflaster, das viral ging, nachdem ein
Phlebologe in einem lokalen Forum darüber schrieb? Letzten Monat war
jede Apotheke in Lansing, Michigan, innerhalb einer Woche leergekauft.
...
```

### Video that already has captions to cover

```
This video has English captions burned in that need covering.
~/Downloads/ad.mp4 — the German audio is already in there. Script:

Was ist das für ein kleines Pflaster, das viral ging, nachdem ein
Phlebologe in einem lokalen Forum darüber schrieb?
...
```

You get back the finished `.mp4`, a matching `.srt`, and a contact sheet showing every
caption over its own frame so you can eyeball it before it ships.

Any language Whisper supports — just say which one, or let Claude infer it from the script.
Any aspect ratio; sizing scales off video width.

---

## Two things to check in Claude's output

**1. The word-match number.**

```
align   368 script tokens, 99.5% exact word match
```

Should be **above 95%**. If it's low, the script doesn't match the audio in that file — wrong
cut, wrong version, or the audio was never swapped to the new language. Fix that first;
captions built on a bad match drift out of sync.

**2. The contact sheet.** Skim it. With `video-captions-cover` you're specifically looking for
any old-language text peeking out around the edges of the band.

---

## One rule that matters

**Paste the script exactly as spoken.** Punctuation, dashes, ellipses, and spoken fillers
("also –", "tja…", "na ja") all go on screen verbatim. That's deliberate — it's what makes
captions read as native rather than machine-generated. Don't hand it a tidied-up written
version of the script.

---

## Good to know

- **Burned-in graphics are not captions.** A banner, logo, or end-card in the old language
  sits outside the caption band and will survive. Claude flags these; replacing them is a
  separate job.
- **Audio is never re-encoded** — the original stream is copied through untouched.
- **Output is H.264 high/4.1 + faststart**, which is what Meta and TikTok want. Default CRF 19
  is visually transparent (SSIM ≈ 0.9999 outside the caption area).
- **Not on a Mac?** The default face is Helvetica Neue Bold. Tell Claude to pass
  `--font /path/to/a-bold-sans.ttf --font-index 0`.

---

## Why the covering band is opaque and full-width

It looks heavier than a neat rounded plate, and that's forced by the pixels rather than taste.
Worth knowing so nobody "fixes" it:

- **Opaque** — a translucent plate over an existing translucent plate double-darkens, so the
  old text ghosts through *and* the old box's edges show as a rectangle inside yours. Tested
  on real footage: even at 88% opacity the old text stays legible on bright shots.
- **Full width** — old caption boxes run essentially edge to edge on long lines (measured
  x 9→1067 of 1080). A rounded inset plate simply cannot contain them.

The result reads as a deliberate subtitle plate, which is a standard VSL/ad look. The only way
to get a lighter treatment is to re-render the video from source without the captions.

---

## Under the hood

1. `ffprobe` for dimensions/fps/duration; all geometry scales off `width ÷ 1080`.
2. Audio → 16 kHz mono → `whisper-cli` with `-ml 1 --split-on-word -dtw large.v3.turbo` for
   per-word timestamps.
3. Your script is aligned onto those word timings with `difflib.SequenceMatcher`. Numerals are
   normalised ("12" ↔ "zwölf") so digits in the script still match spoken words.
4. Cues are cut by dynamic programming **per sentence** — a cue never spans a sentence
   boundary. The cost function balances line fill, 1-vs-2 lines, cue duration, a 21 char/sec
   reading ceiling, and rewards breaking at commas and dashes.
5. Line wrapping refuses to break after a preposition or article, refuses orphan words, and
   prefers balanced line widths.
6. For the covering skill, existing captions are found by sampling frames at 5 fps and keeping
   rows of near-white pixels only when the row is *dashed* — many white→black transitions
   along it. That separates letter strokes from blobs like highlights, white coats, or bright
   skies. The band is the 1st/99th percentile of the detected text extent, padded.
7. One RGBA PNG per cue → chained `overlay ... enable='between(t,s,e)'` filters passed via
   `-/filter_complex`, so cue count isn't limited by argument length.

The engine is a single file: [`video-captions/scripts/caption.py`](video-captions/scripts/caption.py)
(both skills ship an identical copy). Run it with `--help` for every knob, or `--dry-run` to
print the cue list without encoding.
