#!/usr/bin/env bash
# MusicMake setup for macOS and Linux.
#   ./scripts/setup.sh                 everything
#   ./scripts/setup.sh --no-studio     skip building SoundCraft (needs Rust, ~10 minutes)
#   ./scripts/setup.sh --no-acestep    skip ACE-Step 1.5 (the GPU song engine)
#   ./scripts/setup.sh --no-stems      skip Demucs (stems for any song)
# Set TORCH_INDEX to pick a PyTorch build, e.g. https://download.pytorch.org/whl/cu128
set -euo pipefail

ACESTEP=1; STUDIO=1; STEMS=1
for a in "$@"; do
  case "$a" in
    --no-acestep) ACESTEP=0 ;;
    --no-studio) STUDIO=0 ;;
    --no-stems) STEMS=0 ;;
    -h|--help) sed -n 2,7p "$0"; exit 0 ;;
    *) echo "Unknown option: $a" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
ROOT="$PWD"
step() { printf '\n==> %s\n' "$*"; }

PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || { echo "MusicMake needs Python 3.11 or newer (found $("$PY" --version))." >&2; exit 1; }

step "Python environment (.venv)"
[ -d .venv ] || "$PY" -m venv .venv
VPY="$ROOT/.venv/bin/python"
"$VPY" -m pip install --upgrade pip -q
"$VPY" -m pip install -r requirements.txt pytest -q

if [ "$STEMS" = 1 ]; then
  step "Demucs for stems"
  if [ "$(uname)" = "Linux" ] && command -v nvidia-smi >/dev/null; then
    "$VPY" -m pip install torch torchaudio --index-url "${TORCH_INDEX:-https://download.pytorch.org/whl/cu128}" -q
  fi
  "$VPY" -m pip install demucs -q
fi

if [ "$ACESTEP" = 1 ]; then
  step "ACE-Step 1.5 (in ../ACE-Step-1.5)"
  if ! command -v uv >/dev/null; then
    echo "Installing uv (ACE-Step's package manager)…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
  if [ ! -d ../ACE-Step-1.5 ]; then
    git clone https://github.com/ACE-Step/ACE-Step-1.5.git ../ACE-Step-1.5
  fi
  (cd ../ACE-Step-1.5 && uv sync)
  echo "Models download the first time the server starts (several GB)."
fi

if [ "$STUDIO" = 1 ]; then
  step "SoundCraft command-line tool (Studio)"
  if command -v soundcraft-cli >/dev/null; then
    echo "Already installed: $(soundcraft-cli --version)"
  elif command -v cargo >/dev/null; then
    cargo install --locked --git https://github.com/storytold/soundcraft soundcraft-cli
  else
    echo "Rust isn't installed, so Studio is skipped for now."
    echo "Install Rust from https://rustup.rs, then run:"
    echo "  cargo install --locked --git https://github.com/storytold/soundcraft soundcraft-cli"
  fi
fi

command -v ffmpeg >/dev/null || echo "Tip: install ffmpeg for MP3 export and uploads (brew install ffmpeg / sudo apt install ffmpeg)."

step "Check"
"$VPY" -m musicmake doctor || true
cat <<'MSG'

Next:
  1. Start ACE-Step:   cd ../ACE-Step-1.5 && uv run acestep-api
  2. Start MusicMake:  .venv/bin/python -m musicmake
  3. Open http://127.0.0.1:8765
In VS Code: Terminal → Run Task… → "Start everything".
MSG
