#!/usr/bin/env bash
# Installs the video-captions + video-captions-cover Claude Code skills and their deps.
# Safe to re-run: everything is idempotent.
set -euo pipefail

SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
VENV="$HOME/.cache/caption-venv"
MODEL_DIR="$HOME/.cache/whisper-models"
MODEL="$MODEL_DIR/ggml-large-v3-turbo.bin"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn(){ printf '  \033[33m!\033[0m %s\n' "$*"; }

[[ "$(uname)" == "Darwin" ]] || warn "Not macOS. The default font (Helvetica Neue Bold) will be missing — see README."

say "1/4  Skills"
mkdir -p "$SKILLS_DIR"
for s in video-captions video-captions-cover; do
  [[ -d "$SRC/$s" ]] || { echo "missing $SRC/$s — run this from inside the cloned repo"; exit 1; }
  rm -rf "$SKILLS_DIR/$s"
  cp -R "$SRC/$s" "$SKILLS_DIR/$s"
  ok "$SKILLS_DIR/$s"
done

say "2/4  ffmpeg + whisper-cpp"
missing=()
command -v ffmpeg      >/dev/null || missing+=(ffmpeg)
command -v whisper-cli >/dev/null || missing+=(whisper-cpp)
if ((${#missing[@]})); then
  if command -v brew >/dev/null; then
    echo "  installing: ${missing[*]}"
    brew install "${missing[@]}"
  else
    warn "Homebrew not found. Install it from https://brew.sh then re-run, or install manually: ${missing[*]}"
  fi
fi
command -v ffmpeg      >/dev/null && ok "ffmpeg      $(ffmpeg -version | head -1 | cut -d' ' -f3)"
command -v whisper-cli >/dev/null && ok "whisper-cli present"

say "3/4  Python env"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" -q install --upgrade pip >/dev/null 2>&1 || true
"$VENV/bin/pip" -q install numpy pillow
"$VENV/bin/python" -c "import numpy,PIL" && ok "$VENV (numpy, pillow)"

say "4/4  Speech model (1.6 GB, one time)"
mkdir -p "$MODEL_DIR"
if [[ -s "$MODEL" ]]; then
  ok "already downloaded"
else
  echo "  downloading — this is the slow part, grab a coffee"
  curl -L --fail --progress-bar -o "$MODEL.part" "$MODEL_URL"
  mv "$MODEL.part" "$MODEL"
  ok "$MODEL"
fi

cat <<'DONE'

────────────────────────────────────────────────────────
Done. Two skills are installed:

  video-captions          video has NO captions yet
  video-captions-cover    video already has captions to hide

Restart Claude Code, then just ask in plain language, e.g.

  Add captions to ~/Downloads/ad.mp4 — the German audio is
  already in the video. Here's the script:
  <paste script>

Claude picks the right skill. Full usage in the README.
────────────────────────────────────────────────────────
DONE
