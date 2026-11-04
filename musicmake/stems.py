"""Stem separation with Demucs (MIT licence, https://github.com/facebookresearch/demucs).

Install it with `pip install demucs` (a GPU helps but isn't required). Songs made by the
sketch engine already come with stems, so they don't need Demucs.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEMUCS_MODEL = "htdemucs"
STEM_NAMES = ("vocals", "drums", "bass", "other")


def demucs_available() -> bool:
    return importlib.util.find_spec("demucs") is not None


def separate(src: Path, out_dir: Path) -> dict[str, Path]:
    """Split `src` into vocals/drums/bass/other WAVs in `out_dir`."""
    if not demucs_available():
        raise RuntimeError("Stem splitting needs Demucs: run `pip install demucs`")
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [sys.executable, "-m", "demucs", "-n", DEMUCS_MODEL, "-o", tmp, str(src)],
            check=True, capture_output=True,
        )
        found = Path(tmp) / DEMUCS_MODEL / src.stem
        result = {}
        for name in STEM_NAMES:
            f = found / f"{name}.wav"
            if f.exists():
                dst = out_dir / f"{name}.wav"
                shutil.move(str(f), dst)
                result[name] = dst
    if not result:
        raise RuntimeError("Demucs finished but wrote no stems")
    return result
