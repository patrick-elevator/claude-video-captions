# Claude Code video caption skills

**THIS ONLY WORKS FOR CLAUDE CODE**

Claude skill that burns in captions for you into a video, or overlays a video with existing captions.

All you need to give Claude is the **video** (already has the audio you want in it) and the **script/transcript**. 

The timing, line breaks, font size, and placement are all worked out for you.

Two skills, claude has hooks and will choose the right one for you depending on your input.

| Skill | Usecase |
|---|---|
| **video-captions** | The video has **no captions** yet. Adds a rounded translucent plate that hugs the text. |
| **video-captions-cover** | The video **already has captions burned in** that need hiding. Finds the band they sit in and lays an black band over it. |

---

## Install (SUPER EASY GUIDE!)

Paste this into Claude Code:

```
Install the video caption skills from
https://github.com/patrick-elevator/claude-video-captions — clone it somewhere sensible,
run install.sh, and tell me when both skills are registered.
```

All done.

Claude will clone the repo and run the installer, which sets up the two skills,
`ffmpeg`, `whisper-cpp`, a small Python env, and downloads the speech model.


**Needs:** macOS, [Homebrew](https://brew.sh)
if not installed, it may ask you to install it first.

if need to install, please open the terminal.
Command + Space -> type "terminal"
paste the following one liner:
```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

---

## How to use

Open claude code in any folder and ask in plain english

### Video with no captions yet

```
Add captions to ~/Downloads/ad.mp4 — the audio is already
in the video. Here's the script: ...
...
```

### Video that already has captions to cover

```
This video has captions burned in that need covering. Add new captions.
~/Downloads/ad.mp4 — the audio is already in there. Script: ...
...
```

You get back the finished `.mp4`, a matching `.srt`, and a contact sheet showing every
caption over its own frame so you can eyeball it before it ships.

### Other languages

English is the default. For anything else just mention it — Claude works it out from the
script anyway:

```
Add captions to ~/Downloads/ad-de.mp4 — the German audio is already
in the video. Script: ...
```

Any language Whisper supports. Any aspect ratio too — sizing scales off video width.

Any language Whisper supports — just say which one, or let Claude infer it from the script.
Any aspect ratio; sizing scales off video width.

---

## Two things to check in Claude's output

**1. The word-match number.**

```
align   368 script tokens, 99.5% exact word match
```

Should be **above 95%**. If it's low, the script doesn't match the audio in that file — wrong
cut, wrong version. Captions built on a bad match drift out of sync.

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

- **Language:** English by default. Every other language works, just say which one.
- **Output is H.264 high/4.1 + faststart**, which is what Meta and TikTok want. Default CRF 19
  is visually transparent (SSIM ≈ 0.9999 outside the caption area).
- **Not on a Mac?** The default face is Helvetica Neue Bold. Tell Claude to pass or change.
  `for the claude-video-captions skill, please change the font. --font /path/to/a-bold-sans.ttf --font-index 0. To this font: ...enter font name or file location here`.
