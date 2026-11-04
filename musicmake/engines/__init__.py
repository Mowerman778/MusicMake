"""Music engines. `get_engine("auto")` picks ACE-Step when its server is up, else Sketch."""

from __future__ import annotations

import os

from .acestep import AceStepEngine
from .base import Engine, EngineError, SongRequest, Take
from .sketch import SketchEngine

__all__ = ["Engine", "EngineError", "SongRequest", "Take", "get_engine", "engines_status"]

_ENGINES: dict[str, Engine] = {}


def _all() -> dict[str, Engine]:
    if not _ENGINES:
        _ENGINES["sketch"] = SketchEngine()
        _ENGINES["acestep"] = AceStepEngine()
    return _ENGINES


def get_engine(name: str | None = None) -> Engine:
    name = (name or os.environ.get("MUSICMAKE_ENGINE") or "auto").lower()
    engines = _all()
    if name == "auto":
        ok, _ = engines["acestep"].available()
        return engines["acestep"] if ok else engines["sketch"]
    if name not in engines:
        raise EngineError(f"Unknown engine '{name}'. Choose: auto, {', '.join(engines)}")
    return engines[name]


def engines_status() -> list[dict]:
    out = []
    for name, e in _all().items():
        ok, detail = e.available()
        out.append({"name": name, "label": e.label, "available": ok, "detail": detail})
    return out
