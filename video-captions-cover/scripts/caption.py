#!/usr/bin/env python3
"""
Burn natural-reading captions into a video whose audio already contains the voiceover.
Any language Whisper supports; --lang defaults to English.

Two styles:
  --style hug    rounded translucent plate that hugs the text (video has no captions)
  --style cover  full-width opaque band sized to cover captions already burned in

Pipeline: probe -> extract audio -> whisper word timestamps -> align the supplied
script onto those timestamps -> DP-chunk into natural cues -> render PNGs -> ffmpeg overlay.

The script text is authoritative for spelling/punctuation; whisper is used only for timing.
"""
import argparse, json, math, os, re, shutil, subprocess, sys, tempfile, difflib

# ---------------------------------------------------------------- deps

def need(binary, hint):
    if shutil.which(binary) is None:
        sys.exit(f"ERROR: `{binary}` not found on PATH. {hint}")

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("ERROR: needs numpy + pillow.\n"
             "  python3 -m venv ~/.cache/caption-venv && "
             "~/.cache/caption-venv/bin/pip -q install numpy pillow\n"
             "then run this script with ~/.cache/caption-venv/bin/python")

MODEL_DIR = os.path.expanduser("~/.cache/whisper-models")
MODEL = os.path.join(MODEL_DIR, "ggml-large-v3-turbo.bin")
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"

FONT_CANDIDATES = [("/System/Library/Fonts/HelveticaNeue.ttc", 1),
                   ("/System/Library/Fonts/Helvetica.ttc", 1),
                   ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
                   ("/Library/Fonts/Arial Bold.ttf", 0)]

# Words a wrapped line must not END on (articles, prepositions, conjunctions, auxiliaries).
# English first, German second — the union is harmless for either language.
FUNC = set("""
the a an and or but so if as of to in on at by for from with without into onto over under
about after before between during through than that this these those which who whom whose
is are was were be been being am do does did done has have had having will would can could
shall should may might must it its his her their our your my me him them us you we they he
she not no just only still even more most much many any some every all
almost very quite really also then when while because though although since both
each either neither what where why how
und oder aber weil dass das die der den dem des wie was wenn als in zu mit auf
für von nach bei ohne sondern sich es ist war wird sind hat habe haben nicht noch nur schon
vor über unter am im ein eine einen einem eines ihr ihre ihnen sie er tja na
""".split())

# ---------------------------------------------------------------- probe / audio

def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration:format=duration",
        "-of", "json", path],
        capture_output=True, text=True).stdout
    d = json.loads(out)
    st = d["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    dur = float(st.get("duration") or d.get("format", {}).get("duration") or 0)
    return int(st["width"]), int(st["height"]), float(num) / float(den), dur

def extract_audio(video, wav):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, "-vn",
                    "-ac", "1", "-ar", "16000", wav], check=True)

def ensure_model():
    if os.path.exists(MODEL):
        return
    os.makedirs(MODEL_DIR, exist_ok=True)
    print(f"downloading whisper model (~1.6 GB) -> {MODEL}", flush=True)
    subprocess.run(["curl", "-L", "--fail", "-o", MODEL, MODEL_URL], check=True)

def transcribe(wav, lang, stem):
    ensure_model()
    subprocess.run(["whisper-cli", "-m", MODEL, "-f", wav, "-l", lang,
                    "-oj", "-of", stem, "-ml", "1", "--split-on-word",
                    "-dtw", "large.v3.turbo", "-np"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    segs = json.load(open(stem + ".json"))["transcription"]
    words = []
    for s in segs:
        t = s["text"].strip()
        if t:
            words.append([s["offsets"]["from"] / 1000.0, s["offsets"]["to"] / 1000.0, t])
    return words

# ---------------------------------------------------------------- alignment

# Spelled-out numbers -> digits, so "12" in the script still matches a spoken "twelve"
# (or "zwoelf"). Both sides of the alignment run through this, so either form canonicalises.
NUM_WORDS = {}
for _seq in (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split(),
    "null eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf dreizehn vierzehn "
    "fünfzehn sechzehn siebzehn achtzehn neunzehn zwanzig".split(),
):
    for _i, _w in enumerate(_seq):
        NUM_WORDS[_w] = str(_i)
NUM_WORDS.update({
    "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
    "eighty": "80", "ninety": "90", "hundred": "100", "thousand": "1000",
    "dreißig": "30", "vierzig": "40", "fünfzig": "50", "sechzig": "60", "siebzig": "70",
    "achtzig": "80", "neunzig": "90", "hundert": "100", "tausend": "1000",
    "zweitausendsechsundzwanzig": "2026", "zweitausendfünfundzwanzig": "2025",
    "vierundzwanzig": "24", "achtundvierzig": "48",
})

def norm(s):
    s = s.lower().replace("’", "'").replace("‘", "'")
    s = re.sub(r"[^0-9a-zäöüßàâçéèêëîïôùûœ]", "", s)
    return NUM_WORDS.get(s, s)

def align(script_text, words):
    toks = [t for t in re.split(r"\s+", script_text.strip()) if t]
    A, B = [norm(w[2]) for w in words], [norm(t) for t in toks]
    sm = difflib.SequenceMatcher(a=A, b=B, autojunk=False)
    tw = [None] * len(toks)
    matched = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            matched += i2 - i1
            for k in range(i2 - i1):
                tw[j1 + k] = (words[i1 + k][0], words[i1 + k][1])
        elif op == "replace" and i2 > i1 and j2 > j1:
            t0, t1, n = words[i1][0], words[i2 - 1][1], j2 - j1
            for k in range(n):
                tw[j1 + k] = (t0 + (t1 - t0) * k / n, t0 + (t1 - t0) * (k + 1) / n)
    for i, x in enumerate(tw):
        if x is None:
            prev = next((tw[j][1] for j in range(i - 1, -1, -1) if tw[j]), 0.0)
            nxt = next((tw[j][0] for j in range(i + 1, len(tw)) if tw[j]), prev + 0.3)
            tw[i] = (prev, max(prev + 0.05, nxt))
    # fold standalone dashes / ellipses onto the previous word
    merged = []
    for t, (a, b) in zip(toks, tw):
        if t in ("–", "—", "-", "…") and merged:
            merged[-1][0] += " " + t
            merged[-1][2] = b
        else:
            merged.append([t, a, b])
    return merged, matched / max(1, len(words))

# ---------------------------------------------------------------- layout + chunking

class Styler:
    def __init__(self, font_path, font_index, size, pitch, maxline):
        self.f = ImageFont.truetype(font_path, size, index=font_index)
        self.pitch, self.maxline, self._c = pitch, maxline, {}

    def inkw(self, s):
        if s in self._c:
            return self._c[s]
        im = Image.new("L", (max(3000, self.maxline * 3), 260), 0)
        ImageDraw.Draw(im).text((80, 200), s, font=self.f, fill=255, anchor="ls")
        bb = im.getbbox()
        v = 0 if bb is None else bb[2] - bb[0]
        self._c[s] = v
        return v

    def wrap(self, words):
        """Return ([1 or 2 lines], penalty) or (None, None) if it cannot fit."""
        s = " ".join(words)
        if self.inkw(s) <= self.maxline:
            return [s], 0.0
        best = None
        for k in range(1, len(words)):
            l1, l2 = " ".join(words[:k]), " ".join(words[k:])
            w1, w2 = self.inkw(l1), self.inkw(l2)
            if w1 > self.maxline or w2 > self.maxline:
                continue
            pen = abs(w1 - w2) * 0.35
            if re.search(r"[,;:–…]$", words[k - 1]):
                pen -= 180
            if words[k].lower().strip("„\"«") in FUNC:
                pen -= 90
            lw = words[k - 1].lower().strip("„\"«")
            if lw in FUNC and not re.search(r"[,;:–….?!]$", words[k - 1]):
                pen += 520                      # don't break after a preposition/article
            if k == len(words) - 1 and self.inkw(words[-1]) < self.maxline * 0.18:
                pen += 350                      # no orphan word on line 2
            if k == 1 and self.inkw(words[0]) < self.maxline * 0.18:
                pen += 350
            if w2 < w1 * 0.45:
                pen += 200
            if best is None or pen < best[0]:
                best = (pen, [l1, l2])
        if best is None:
            return None, None
        return best[1], max(0.0, best[0]) * 0.02

def chunk(W, st, target_frac=0.886):
    """Split words into cues with dynamic programming, never crossing a sentence end."""
    target = st.maxline * target_frac
    sents, cur = [], []
    for i, (t, a, b) in enumerate(W):
        cur.append(i)
        if re.search(r'[.?!]["»)]?$', t):
            sents.append(cur); cur = []
    if cur:
        sents.append(cur)
    cues = []
    for S in sents:
        n = len(S); INF = float("inf")
        cost = [INF] * (n + 1); back = [None] * (n + 1); cost[0] = 0
        for a in range(n):
            if cost[a] == INF:
                continue
            for b in range(a + 1, min(n, a + 15) + 1):
                idxs = S[a:b]; words = [W[i][0] for i in idxs]
                lines, lp = st.wrap(words)
                if lines is None:
                    break
                dur = W[idxs[-1]][2] - W[idxs[0]][1]
                c = lp
                for L in lines:
                    w = st.inkw(L)
                    c += ((target - w) / target) ** 2 * 55 if w < target \
                         else ((w - target) / target) ** 2 * 25
                if len(lines) == 1:
                    c += 12
                if b < n and sum(st.inkw(L) for L in lines) < st.maxline * 0.49:
                    c += 110                     # avoid tiny mid-sentence cues
                if dur < 0.95:
                    c += (0.95 - dur) * 90
                if dur > 2.95:
                    c += (dur - 2.95) * 70
                cps = sum(len(L) for L in lines) / max(dur, 0.2)
                if cps > 21:
                    c += (cps - 21) * 16         # reading-speed ceiling
                if b < n:
                    prev = W[idxs[-1]][0]
                    c += -45 if re.search(r"[,;:–…]$", prev) else 55
                    if prev.lower().strip('„"«.,;:–…!?') in FUNC:
                        c += 260          # never leave a cue hanging on "a" / "the" / "and"
                    if W[S[b]][1] - W[idxs[-1]][2] > 0.28:
                        c -= 35
                if cost[a] + c < cost[b]:
                    cost[b] = cost[a] + c; back[b] = a
        parts, b = [], n
        while b:
            a = back[b]; parts.append(S[a:b]); b = a
        for p in reversed(parts):
            lines, _ = st.wrap([W[i][0] for i in p])
            cues.append({"lines": lines, "ws": W[p[0]][1], "we": W[p[-1]][2]})
    return cues

def timing(cues, hold, must_cover, duration, tail=0.45):
    """hold = max speech pause (s) the caption stays up across without blinking."""
    def hits(a, b):
        return any(a < e and b > s for s, e in must_cover)
    for c in cues:
        c["start"] = max(0.0, c["ws"] - 0.08)
        c["end"] = c["we"] + 0.30
    for i in range(len(cues) - 1):
        gap = cues[i + 1]["ws"] - cues[i]["we"]
        ns = max(0.0, cues[i + 1]["ws"] - 0.08)
        if gap < hold or hits(cues[i]["we"], cues[i + 1]["ws"]):
            cues[i]["end"] = ns
        else:
            cues[i]["end"] = min(cues[i]["we"] + 0.35, ns - 0.15)
    cues[-1]["end"] = min(duration, cues[-1]["we"] + tail)
    if must_cover:
        lo = min(s for s, e in must_cover); hi = max(e for s, e in must_cover)
        cues[0]["start"] = min(cues[0]["start"], max(0.0, lo))
        cues[-1]["end"] = max(cues[-1]["end"], min(duration, hi))
    return [{"start": round(c["start"], 3), "end": round(c["end"], 3), "lines": c["lines"]}
            for c in cues]

# ---------------------------------------------------------------- detect burned-in captions

def detect_existing(video, W, H, duration, fps_sample=5):
    """Find the vertical band occupied by captions already burned into the video,
    plus the time intervals where one is on screen. Looks for rows of white text
    pixels that are 'dashed' (many stroke transitions) — logos and highlights are not."""
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps={fps_sample}",
                          "-pix_fmt", "gray", "-f", "rawvideo", "-"],
                         stdout=subprocess.PIPE)
    fsz = W * H
    ytop = int(H * 0.45)
    y0s, y1s, present, i = [], [], [], 0
    while True:
        buf = p.stdout.read(fsz)
        if len(buf) < fsz:
            break
        f = np.frombuffer(buf, dtype=np.uint8).reshape(H, W)
        wm = f >= 245
        wm[:ytop, :] = False
        cnt = wm.sum(axis=1)
        tr = (np.diff(wm.astype(np.int8), axis=1) == 1).sum(axis=1)
        idx = np.where((cnt >= max(10, W // 100)) & (cnt <= W * 0.68) & (tr >= 7))[0]
        block = None
        if len(idx):
            lines, cur = [], [idx[0]]
            for y in idx[1:]:
                if y - cur[-1] <= 5:
                    cur.append(y)
                else:
                    lines.append((cur[0], cur[-1])); cur = [y]
            lines.append((cur[0], cur[-1]))
            lo, hi = int(H * 0.018), int(H * 0.067)      # plausible single text-line height
            lines = [l for l in lines if lo <= l[1] - l[0] <= hi]
            blocks = []
            for l in lines:
                if blocks and l[0] - blocks[-1][-1][1] <= int(H * 0.045):
                    blocks[-1].append(l)
                else:
                    blocks.append([l])
            blocks = [b for b in blocks if len(b) <= 3]
            if blocks:
                b = max(blocks, key=lambda b: wm[b[0][0]:b[-1][1] + 1].sum())
                block = (int(b[0][0]), int(b[-1][1]))
        if block:
            y0s.append(block[0]); y1s.append(block[1]); present.append(i / fps_sample)
        i += 1
    p.stdout.close(); p.wait()
    if len(y0s) < 5:
        return None
    y0 = int(np.percentile(y0s, 1.0)); y1 = int(np.percentile(y1s, 99.0))
    intervals = []
    for t in present:
        if intervals and t - intervals[-1][1] <= 0.45:
            intervals[-1][1] = t
        else:
            intervals.append([t, t])
    step = 1.0 / fps_sample
    intervals = [(max(0.0, a - 0.25), min(duration, b + step + 0.25)) for a, b in intervals]
    return y0, y1, intervals, len(y0s), i

# ---------------------------------------------------------------- rendering

def render(cues, outdir, style, W, size, pitch, pad, radius, alpha, font_path, font_index,
           box_bottom=None, band=None, boxcol=(14, 14, 16), ss=4):
    f = ImageFont.truetype(font_path, size, index=font_index)
    os.makedirs(outdir, exist_ok=True)
    for p in os.listdir(outdir):
        os.remove(os.path.join(outdir, p))

    def inkw(s):
        im = Image.new("L", (max(3000, W * 3), size * 4), 0)
        ImageDraw.Draw(im).text((80, size * 3), s, font=f, fill=255, anchor="ls")
        bb = im.getbbox()
        return 0 if bb is None else bb[2] - bb[0]

    tops = []
    if style == "cover":
        btop, bbot = band
        bh = bbot - btop
        # text block vertically centred in the band
        for i, c in enumerate(cues):
            n = len(c["lines"])
            im = Image.new("RGBA", (W, bh), boxcol + (255,))
            d = ImageDraw.Draw(im)
            last = int(bh / 2 + size * 0.30) + int(pitch / 2) * (n - 1)
            for k, L in enumerate(c["lines"]):
                d.text((W / 2, last - pitch * (n - 1 - k)), L, font=f,
                       fill=(255, 255, 255, 255), anchor="ms")
            im.save(f"{outdir}/c_{i:03d}.png")
            tops.append(btop)
    else:
        one = int(round(size * 1.60))            # 1-line plate height
        for i, c in enumerate(cues):
            n = len(c["lines"])
            h = one + pitch * (n - 1)
            top = box_bottom - h
            bw = max(inkw(L) for L in c["lines"]) + 2 * pad
            x0 = (W - bw) / 2.0
            big = Image.new("L", (W * ss, h * ss), 0)
            ImageDraw.Draw(big).rounded_rectangle(
                [x0 * ss, 0, (x0 + bw) * ss - 1, h * ss - 1],
                radius=radius * ss, fill=int(alpha * 255))
            im = Image.new("RGBA", (W, h), boxcol + (0,))
            im.putalpha(big.resize((W, h), Image.LANCZOS))
            t = Image.new("RGBA", (W, h), (255, 255, 255, 0))
            d = ImageDraw.Draw(t)
            last = h - int(round(size * 0.565))
            for k, L in enumerate(c["lines"]):
                d.text((W / 2, last - pitch * (n - 1 - k)), L, font=f,
                       fill=(255, 255, 255, 255), anchor="ms")
            Image.alpha_composite(im, t).save(f"{outdir}/c_{i:03d}.png")
            tops.append(top)
    return tops

def encode(video, cues, capdir, tops, out, crf, work):
    inputs = ["-i", video]
    for i in range(len(cues)):
        inputs += ["-i", f"{capdir}/c_{i:03d}.png"]
    parts, cur = [], "[0:v]"
    for i, c in enumerate(cues):
        nxt = f"[v{i}]" if i < len(cues) - 1 else "[vout]"
        parts.append(f"{cur}[{i+1}:v]overlay=0:{tops[i]}:"
                     f"enable='between(t,{c['start']:.3f},{c['end']:.3f})'{nxt}")
        cur = nxt
    fpath = os.path.join(work, "filter.txt")
    open(fpath, "w").write(";".join(parts))
    cmd = (["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + inputs +
           ["-/filter_complex", fpath, "-map", "[vout]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
            "-movflags", "+faststart", "-c:a", "copy", out])
    if subprocess.run(cmd).returncode != 0:
        sys.exit("ERROR: ffmpeg encode failed")

def write_srt(cues, path):
    def ts(s):
        h, m = int(s // 3600), int(s % 3600 // 60)
        return f"{h:02d}:{m:02d}:{s%60:06.3f}".replace(".", ",")
    open(path, "w").write("\n".join(
        f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n" + "\n".join(c["lines"]) + "\n"
        for i, c in enumerate(cues, 1)))

def verify_sheet(video, cues, W, H, y0, y1, path, cols=3, tile=330):
    rows = []
    for c in cues:
        t = (c["start"] + c["end"]) / 2
        p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video,
                            "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                           capture_output=True)
        if len(p.stdout) < W * H * 3:
            continue
        im = Image.frombytes("RGB", (W, H), p.stdout[:W * H * 3]).crop((0, y0, W, y1))
        rows.append((f"{t:.1f}", im))
    if not rows:
        return
    th = int(tile * (y1 - y0) / W)
    sheet = Image.new("RGB", (cols * (tile + 48), ((len(rows) + cols - 1) // cols) * (th + 9) + 9), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    try:
        lf = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13, index=1)
    except Exception:
        lf = ImageFont.load_default()
    for i, (n, im) in enumerate(rows):
        r, c = divmod(i, cols)
        sheet.paste(im.resize((tile, th)), (c * (tile + 48) + 44, r * (th + 9) + 4))
        d.text((c * (tile + 48) + 2, r * (th + 9) + th // 2), n, font=lf, fill=(255, 215, 0))
    sheet.resize((int(sheet.width * 1.9), int(sheet.height * 1.9)), Image.LANCZOS).save(path)

# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--script", required=True, help="text file with the spoken script")
    ap.add_argument("--out", required=True)
    ap.add_argument("--style", choices=["hug", "cover"], default="hug")
    ap.add_argument("--lang", default="en",
                    help="language of the audio: en, de, fr, es, it, nl, pt, ... (default en)")
    ap.add_argument("--crf", type=int, default=19)
    ap.add_argument("--work", default=None)
    ap.add_argument("--srt", default=None)
    ap.add_argument("--verify", default=None)
    ap.add_argument("--font", default=None)
    ap.add_argument("--font-index", type=int, default=None)
    ap.add_argument("--font-size", type=int, default=None)
    ap.add_argument("--max-line-frac", type=float, default=0.815,
                    help="max text width as a fraction of video width")
    ap.add_argument("--box-bottom", type=int, default=None, help="hug: plate bottom, px")
    ap.add_argument("--box-bottom-frac", type=float, default=0.862, help="hug: plate bottom as frac of height")
    ap.add_argument("--alpha", type=float, default=0.66, help="hug: plate opacity")
    ap.add_argument("--band-top", type=int, default=None, help="cover: override detected band")
    ap.add_argument("--band-bottom", type=int, default=None)
    ap.add_argument("--hold", type=float, default=None,
                    help="max speech pause held without blinking (default 0.80 hug / 999 cover)")
    ap.add_argument("--dry-run", action="store_true", help="print cues, do not encode")
    a = ap.parse_args()

    need("ffmpeg", "brew install ffmpeg")
    need("ffprobe", "brew install ffmpeg")
    need("whisper-cli", "brew install whisper-cpp")
    for p in (a.video, a.script):
        if not os.path.isfile(p):
            sys.exit(f"ERROR: no such file: {p}")

    work = a.work or tempfile.mkdtemp(prefix="caption-")
    os.makedirs(work, exist_ok=True)
    W, H, fps, dur = probe(a.video)
    print(f"video   {W}x{H} @{fps:g}fps  {dur:.2f}s")

    font_path, font_index = a.font, a.font_index
    if font_path is None:
        for p, ix in FONT_CANDIDATES:
            if os.path.exists(p):
                font_path, font_index = p, ix
                break
        if font_path is None:
            sys.exit("ERROR: no bold sans font found; pass --font/--font-index")
    if font_index is None:
        font_index = 0

    k = W / 1080.0
    size = a.font_size or max(18, int(round(62 * k)))
    pitch = int(round(size * 72 / 62))
    pad = int(round(21 * k))
    radius = max(6, int(round(16 * k)))
    maxline = int(W * a.max_line_frac)

    wav = os.path.join(work, "audio.wav")
    extract_audio(a.video, wav)
    words = transcribe(wav, a.lang, os.path.join(work, "tr"))
    print(f"whisper {len(words)} words, speech ends {words[-1][1]:.2f}s")

    Wt, cov = align(open(a.script, encoding="utf-8").read(), words)
    print(f"align   {len(Wt)} script tokens, {cov*100:.1f}% exact word match")
    if cov < 0.80:
        print("WARNING: low match — is this the right script for this audio?")

    band = must_cover = None
    if a.style == "cover":
        if a.band_top is not None and a.band_bottom is not None:
            band = (a.band_top, a.band_bottom)
            must_cover = [(0.0, dur)]
            print(f"cover   band y{band} (manual), covering whole video")
        else:
            det = detect_existing(a.video, W, H, dur)
            if det is None:
                sys.exit("ERROR: could not find existing captions. Pass --band-top/--band-bottom.")
            ty0, ty1, must_cover, nf, tot = det
            m = pad + int(round(10 * k))
            band = (max(0, ty0 - m), min(H, ty1 + m))
            span = sum(e - s for s, e in must_cover)
            print(f"cover   existing caption text y[{ty0},{ty1}] on {nf}/{tot} sampled frames")
            print(f"cover   band y{band} ({band[1]-band[0]}px), full width, "
                  f"{len(must_cover)} interval(s) totalling {span:.1f}s")

    st = Styler(font_path, font_index, size, pitch, maxline)
    hold = a.hold if a.hold is not None else (999.0 if a.style == "cover" else 0.80)
    cues = timing(chunk(Wt, st), hold, must_cover or [], dur)

    # coverage assertion
    if must_cover:
        holes = []
        for s, e in must_cover:
            t = s
            while t < e:
                if not any(c["start"] - 1e-6 <= t <= c["end"] + 1e-6 for c in cues):
                    holes.append(round(t, 2))
                t += 0.05
        if holes:
            print(f"WARNING: {len(holes)} uncovered moment(s), first at {holes[0]}s")
        else:
            print("cover   verified: no uncovered moment inside any caption interval")

    print(f"cues    {len(cues)}  track {cues[0]['start']:.2f} -> {cues[-1]['end']:.2f}")
    for c in cues:
        print(f"  {c['start']:7.2f}-{c['end']:7.2f}  " + "  /  ".join(c["lines"]))
    json.dump(cues, open(os.path.join(work, "cues.json"), "w"), ensure_ascii=False, indent=1)
    if a.srt:
        write_srt(cues, a.srt); print(f"srt     {a.srt}")
    if a.dry_run:
        print("dry-run: stopping before render"); return

    box_bottom = a.box_bottom or int(round(H * a.box_bottom_frac))
    tops = render(cues, os.path.join(work, "caps"), a.style, W, size, pitch, pad, radius,
                  a.alpha, font_path, font_index, box_bottom=box_bottom, band=band)
    encode(a.video, cues, os.path.join(work, "caps"), tops, a.out, a.crf, work)
    print(f"out     {a.out}  ({os.path.getsize(a.out)/1e6:.1f} MB)")

    if a.verify:
        if a.style == "cover":
            vy0, vy1 = max(0, band[0] - 34), min(H, band[1] + 34)
        else:
            vy0, vy1 = max(0, min(tops) - 40), min(H, box_bottom + 40)
        verify_sheet(a.out, cues, W, H, vy0, vy1, a.verify)
        print(f"verify  {a.verify}")

if __name__ == "__main__":
    main()
