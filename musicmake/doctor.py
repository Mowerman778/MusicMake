"""`python -m musicmake doctor`: check what this computer can do, and say how to fix what's missing."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys

OK, WARN, MISSING = "ok", "optional", "missing"


def _run(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def checks() -> list[tuple[str, str, str, str]]:
    """(status, name, what was found, how to fix)."""
    out = []
    v = sys.version_info
    out.append((OK if v >= (3, 11) else MISSING, "Python",
                f"{platform.python_version()} at {sys.executable}",
                "" if v >= (3, 11) else "Install Python 3.11 or newer"))

    missing = [m for m in ("fastapi", "uvicorn", "numpy", "httpx", "multipart")
               if importlib.util.find_spec(m) is None]
    out.append((MISSING if missing else OK, "Python packages",
                "missing: " + ", ".join(missing) if missing else "installed",
                "pip install -r requirements.txt" if missing else ""))

    gpu = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    if gpu:
        out.append((OK, "GPU", gpu.splitlines()[0], ""))
    elif sys.platform == "darwin" and platform.machine() == "arm64":
        out.append((OK, "GPU", "Apple Silicon (ACE-Step uses MLX)", ""))
    else:
        out.append((WARN, "GPU", "no NVIDIA GPU found by nvidia-smi",
                    "Install the NVIDIA driver, or use the Sketch engine (no GPU needed)"))

    from .engines.acestep import AceStepEngine

    ok, detail = AceStepEngine().available()
    out.append((OK if ok else WARN, "ACE-Step 1.5 (real vocals)", detail,
                "" if ok else "Start it: in the ACE-Step-1.5 folder run `uv run acestep-api` "
                              "(or start_api_server.bat on Windows). See docs/laptop-setup.md"))

    ff = shutil.which("ffmpeg")
    out.append((OK if ff else WARN, "ffmpeg (MP3 export, uploads)", ff or "not found",
                "" if ff else "Windows: winget install Gyan.FFmpeg · macOS: brew install ffmpeg · Linux: apt install ffmpeg"))

    from . import studio

    ok, detail = studio.available()
    out.append((OK if ok else WARN, "SoundCraft (Studio)", detail if ok else "soundcraft-cli not found",
                "" if ok else "cargo install --git https://github.com/storytold/soundcraft soundcraft-cli "
                              "(needs Rust: https://rustup.rs), or set SOUNDCRAFT_CLI"))

    dm = importlib.util.find_spec("demucs") is not None
    cuda = None
    if dm and importlib.util.find_spec("torch"):
        cuda = _run([sys.executable, "-c", "import torch;print(torch.cuda.is_available())"])
    detail = "not installed" if not dm else f"installed (torch CUDA: {cuda or 'unknown'})"
    fix = "" if dm else "pip install demucs (install a CUDA build of torch first for GPU speed)"
    if dm and cuda == "False" and gpu:
        fix = "Demucs is on CPU: reinstall torch with CUDA from https://pytorch.org/get-started/locally/"
    out.append((OK if dm else WARN, "Demucs (stems for any song)", detail, fix))

    key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    has_sdk = importlib.util.find_spec("anthropic") is not None
    out.append((OK if key and has_sdk else WARN, "Lyric helper (Claude)",
                "API key set" if key else "no ANTHROPIC_API_KEY (offline template is used)",
                "" if key and has_sdk else "pip install anthropic, then set ANTHROPIC_API_KEY"))
    return out


def main() -> int:
    try:  # Windows consoles may not be UTF-8
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    marks = {OK: "✔", WARN: "○", MISSING: "✘"}
    rows = checks()
    print("MusicMake doctor\n")
    for status, name, found, fix in rows:
        print(f" {marks[status]} {name}: {found}")
        if fix:
            print(f"     → {fix}")
    bad = [r for r in rows if r[0] == MISSING]
    print("\n" + ("Ready: run `python -m musicmake` and open http://127.0.0.1:8765" if not bad
                  else "Fix the ✘ items first."))
    print("○ items are optional; MusicMake works without them.")
    return 1 if bad else 0
