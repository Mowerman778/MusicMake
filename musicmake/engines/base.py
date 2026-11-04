"""Shared types for music engines."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

Progress = Callable[[float, str], None]


@dataclass
class SongRequest:
    """Everything the Create panel can ask for. Engines ignore what they can't use."""

    prompt: str = ""            # free description ("a rainy-day lo-fi tune about trains")
    lyrics: str = ""            # may contain [Verse] / [Chorus] tags
    styles: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    instrumental: bool = False
    duration: float = 120.0     # seconds (10..600)
    bpm: Optional[int] = None
    key: Optional[str] = None   # "C major", "Am", "F# minor"
    seed: Optional[int] = None
    takes: int = 2
    adventurous: float = 0.5    # 0 = safe and predictable, 1 = wild
    title: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SongRequest":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)

    def style_text(self) -> str:
        return ", ".join(s.strip() for s in self.styles if s.strip())


@dataclass
class Take:
    audio: Optional[np.ndarray]          # (frames, 2) float32, or None if `file` is set
    sr: int
    seed: int
    meta: dict = field(default_factory=dict)
    stems: Optional[dict[str, np.ndarray]] = None
    file: Optional[Path] = None          # engines that hand back a file instead of samples
    lyrics: Optional[str] = None         # final lyrics, if the engine wrote or changed them


class EngineError(RuntimeError):
    """A problem the person should see, worded plainly."""


class Engine:
    name = "base"
    label = "Base"

    def available(self) -> tuple[bool, str]:
        return True, "ready"

    def generate(self, req: SongRequest, progress: Progress) -> list[Take]:
        raise NotImplementedError

    def extend(self, req: SongRequest, source: Path, source_meta: dict,
               seconds: float, progress: Progress) -> Take:
        raise EngineError(f"{self.label} can't extend songs")

    def remix(self, req: SongRequest, source: Path, source_meta: dict,
              strength: float, progress: Progress) -> Take:
        raise EngineError(f"{self.label} can't remix songs")
