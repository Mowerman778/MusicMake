"""Studio: audio editing and mixing powered by SoundCraft.

SoundCraft (https://github.com/storytold/soundcraft, MIT or Apache-2.0) is an open-source
digital audio workstation written in Rust. Its command-line tool, `soundcraft-cli`, runs the
full editing and mix engine without a window. MusicMake drives it to:

- edit the timeline: cut (closing the gap), keep only a range, silence, region gain, fades;
- process regions offline (AudioSuite): reverse, pitch shift, normalize, or any built-in plugin;
- mix: per-track volume, pan, mute, solo and up to ten plugin inserts (EQ, compressor, gate,
  de-esser, reverbs, delay, chorus, saturator and more), plus a master track;
- bounce the result and measure peak, true peak and integrated loudness (LUFS);
- save a `.scraft` session you can open in the SoundCraft app for detailed work.

Edits are non-destructive: MusicMake keeps an *edit document* (JSON) for each song and renders
it from the original files every time, so any step can be removed later.

Edit document:
{
  "source": "stems" | "mix",
  "tracks": [{"name", "volume_db", "pan", "mute", "solo",
              "inserts": [{"plugin", "params": {...}, "bypass": false}]}],
  "master": {"volume_db": 0, "inserts": [...], "loudness": null | -14.0, "normalize": false},
  "edits":  [{"op": "cut"|"keep"|"silence"|"gain"|"fade_in"|"fade_out"|"process",
              "start": s, "end": s, "tracks": [names] | null, ...}]
}
Times are seconds on the timeline as it stands after the edits before them, as in a DAW.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

RATE = 48000
MASTER = "Master 1"   # the name SoundCraft gives the first master track
OPS = ("cut", "keep", "silence", "gain", "fade_in", "fade_out", "process")
PROCESSES = ("reverse", "pitch_shift", "normalize", "invert")
FADE_SHAPES = ("linear", "equal power", "s-curve", "exponential", "logarithmic")
# Built-in plugins that make sound rather than process it, or that don't make sense here.
SKIP_PLUGINS = {"signal_generator", "subtractive_synth", "drum_synth", "sampler", "dither", "time_shift"}
INSTALL_HINT = ("Studio needs SoundCraft's command-line tool. Install it with "
                "`cargo install --git https://github.com/storytold/soundcraft soundcraft-cli` "
                "(Rust 1.90+), or set SOUNDCRAFT_CLI to its path.")


class StudioError(RuntimeError):
    pass


# ------------------------------------------------------------------ the CLI

def cli_path() -> str | None:
    env = os.environ.get("SOUNDCRAFT_CLI")
    if env:
        return env if Path(env).exists() else None
    return shutil.which("soundcraft-cli")


def available() -> tuple[bool, str]:
    cli = cli_path()
    if not cli:
        return False, INSTALL_HINT
    try:
        out = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=10)
        return True, out.stdout.strip() or "soundcraft-cli"
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"soundcraft-cli didn't run ({e})"


def _run(args: list[str], timeout: float = 600) -> str:
    cli = cli_path()
    if not cli:
        raise StudioError(INSTALL_HINT)
    with tempfile.TemporaryDirectory() as tmp:   # no stray files in the working directory
        out = subprocess.run([cli, *args], capture_output=True, text=True, timeout=timeout, cwd=tmp)
    if out.returncode != 0:
        errs = [ln.split(": ", 1)[-1] for ln in out.stderr.splitlines()
                if ln.strip() and "script finished with command errors" not in ln]
        raise StudioError("SoundCraft: " + ("; ".join(errs[-3:]) or f"exit code {out.returncode}"))
    return out.stdout


@lru_cache(maxsize=1)
def plugins() -> list[dict]:
    """SoundCraft's built-in processors with their parameters (id, name, min, max, default, unit, choices)."""
    out = _run(["run", "--cmd", "engine.plugins={}"])
    line = next(ln for ln in out.splitlines() if ln.startswith("engine.plugins:"))
    data = json.loads(line.split(": ", 1)[1])
    return [p for p in data if not p.get("instrument") and p["id"] not in SKIP_PLUGINS]


def _plugin(pid: str) -> dict:
    for p in plugins():
        if p["id"] == pid:
            return p
    raise StudioError(f"Unknown effect '{pid}'")


def clean_params(pid: str, params: dict | None) -> dict:
    """Keep only known parameters, clamped to their ranges."""
    spec = {q["id"]: q for q in _plugin(pid)["params"]}
    out = {}
    for k, v in (params or {}).items():
        if k in spec:
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            q = spec[k]
            out[k] = min(max(v, q["min"]), q["max"])
    return out


# ------------------------------------------------------------------ edit documents

def default_doc(track_names: list[str], source: str) -> dict:
    return {
        "source": source,
        "tracks": [{"name": n, "volume_db": 0.0, "pan": 0.0, "mute": False, "solo": False, "inserts": []}
                   for n in track_names],
        # A transparent safety limiter: stems can add up louder than the original mix.
        "master": {"volume_db": 0.0, "loudness": None, "normalize": False,
                   "inserts": [{"plugin": "maximizer", "params": {"ceiling": -1.0}, "bypass": False}]},
        "edits": [],
    }


def _num(v, lo: float, hi: float, default: float = 0.0) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return min(max(v, lo), hi)


def validate_doc(doc: dict, track_names: list[str]) -> dict:
    """Check and normalise an edit document from the browser. Raises StudioError on bad input."""
    if not isinstance(doc, dict):
        raise StudioError("The edit document must be an object")
    by_name = {t.get("name"): t for t in doc.get("tracks") or [] if isinstance(t, dict)}
    tracks = []
    for name in track_names:
        t = by_name.get(name, {})
        tracks.append({
            "name": name,
            "volume_db": _num(t.get("volume_db"), -60, 12),
            "pan": _num(t.get("pan"), -1, 1),
            "mute": bool(t.get("mute")),
            "solo": bool(t.get("solo")),
            "inserts": _inserts(t.get("inserts")),
        })
    m = doc.get("master") or {}
    loud = m.get("loudness")
    master = {
        "volume_db": _num(m.get("volume_db"), -60, 12),
        "inserts": _inserts(m.get("inserts"))[:8],   # room for the loudness gain and limiter
        "loudness": None if loud in (None, "", "off") else _num(loud, -30, -6, -14),
        "normalize": bool(m.get("normalize")),
    }
    edits = []
    for e in doc.get("edits") or []:
        if not isinstance(e, dict) or e.get("op") not in OPS:
            raise StudioError(f"Unknown edit {e!r}")
        e2 = {"op": e["op"]}
        if e["op"] in ("fade_in", "fade_out"):
            e2["length"] = _num(e.get("length"), 0.01, 600, 2.0)
            e2["shape"] = e.get("shape") if e.get("shape") in FADE_SHAPES else "s-curve"
        else:
            e2["start"] = _num(e.get("start"), 0, 3600)
            e2["end"] = _num(e.get("end"), 0, 3600)
            if e2["end"] - e2["start"] < 0.005:
                raise StudioError("Select a range first")
        if e["op"] in ("silence", "gain", "process", "fade_in", "fade_out"):
            sel = e.get("tracks")
            if sel:
                bad = [n for n in sel if n not in track_names]
                if bad:
                    raise StudioError(f"No track named {bad[0]}")
                e2["tracks"] = list(sel)
        if e["op"] == "gain":
            e2["db"] = _num(e.get("db"), -60, 24)
        if e["op"] == "process":
            proc = e.get("process")
            if proc in PROCESSES:
                e2["process"] = proc
                if proc == "pitch_shift":
                    e2["params"] = {"semitones": _num((e.get("params") or {}).get("semitones"), -24, 24)}
            else:
                _plugin(str(proc))
                e2["process"] = proc
                e2["params"] = clean_params(proc, e.get("params"))
        edits.append(e2)
    return {"source": doc.get("source", "stems"), "tracks": tracks, "master": master, "edits": edits}


def _inserts(items) -> list[dict]:
    out = []
    for ins in (items or [])[:10]:
        if not isinstance(ins, dict):
            continue
        pid = str(ins.get("plugin", ""))
        _plugin(pid)
        out.append({"plugin": pid, "params": clean_params(pid, ins.get("params")), "bypass": bool(ins.get("bypass"))})
    return out


# ------------------------------------------------------------------ script building

def _cmd(cid: str, params: dict) -> str:
    return f"{cid} {json.dumps(params, separators=(',', ':'))}"


def _s(seconds: float) -> int:
    return int(round(seconds * RATE))


def build_script(doc: dict, sources: list[Path], source_seconds: float, bounce: Path,
                 stems_dir: Path | None = None, master_gain: float = 0.0) -> list[str]:
    """Turn an edit document into SoundCraft engine commands, one `ID JSON` per line."""
    names = [t["name"] for t in doc["tracks"]]
    lines = [_cmd("session.new", {"sample_rate": RATE, "name": "MusicMake"}),
             _cmd("file.import_audio", {"paths": [str(p) for p in sources]})]
    length = _s(source_seconds)
    fades: list[dict] = []

    def region(tracks, a, b):
        sel = {"tracks": tracks, "start": a, "end": b}
        return [_cmd("edit.select", sel), _cmd("edit.separate", {}), _cmd("edit.select", sel)]

    def cut(a, b):
        return [_cmd("edit.mode", {"mode": "shuffle"}), _cmd("edit.select", {"tracks": names, "start": a, "end": b}),
                _cmd("edit.clear", {}), _cmd("edit.mode", {"mode": "slip"})]

    for e in doc["edits"]:
        op = e["op"]
        tracks = e.get("tracks") or names
        if op in ("fade_in", "fade_out"):
            fades.append(e)   # drawn as volume automation on the finished timeline, below
            continue
        a, b = min(_s(e["start"]), length), min(_s(e["end"]), length)
        if b <= a:
            continue
        if op == "cut":
            lines += cut(a, b)
            length -= b - a
        elif op == "keep":
            if b < length:
                lines += cut(b, length)
            if a > 0:
                lines += cut(0, a)
            length = b - a
        elif op == "silence":
            lines += [_cmd("edit.select", {"tracks": tracks, "start": a, "end": b}), _cmd("edit.clear", {})]
        elif op == "gain":
            lines += region(tracks, a, b) + [_cmd("clip.gain", {"delta_db": e["db"]})]
        elif op == "process":
            params = {"process": e["process"]}
            if e.get("params"):
                params["params"] = e["params"]
            lines += region(tracks, a, b) + [_cmd("audiosuite.process", params)]
    lines.append(_cmd("edit.select_none", {}))

    for t in doc["tracks"]:
        n = t["name"]
        if t["volume_db"]:
            lines.append(_cmd("mix.volume", {"tracks": [n], "db": t["volume_db"]}))
        if t["pan"]:
            lines.append(_cmd("mix.pan", {"tracks": [n], "pan": t["pan"]}))
        if t["mute"]:
            lines.append(_cmd("mix.mute", {"tracks": [n], "value": True}))
        if t["solo"]:
            lines.append(_cmd("mix.solo", {"tracks": [n], "value": True}))
        lines += _insert_lines(n, t["inserts"])

    m = doc["master"]
    lines.append(_cmd("track.new", {"kind": "master"}))
    gain = m["volume_db"]
    if gain:
        lines.append(_cmd("mix.volume", {"tracks": [MASTER], "db": gain}))
    inserts = list(m["inserts"])
    if master_gain:
        # Reaching a loudness target: gain first in the chain, then a limiter last so the
        # boost can't clip (the fader comes after the inserts, so it can't be used for this).
        inserts = [{"plugin": "gain", "params": {"gain": max(-24.0, min(24.0, master_gain))}, "bypass": False}] + inserts
        if master_gain > 0 and not (inserts[-1]["plugin"] == "maximizer" and not inserts[-1]["bypass"]):
            inserts.append({"plugin": "maximizer", "params": {"ceiling": -1.0}, "bypass": False})
    lines += _insert_lines(MASTER, inserts[:10])

    # Fades: volume automation on the chosen tracks, or on the master for the whole song.
    levels = {t["name"]: t["volume_db"] for t in doc["tracks"]}
    levels[MASTER] = gain
    for e in fades:
        for target in (e.get("tracks") or [MASTER]):
            for at, value in fade_points(e["op"], e["shape"], min(_s(e["length"]), length), length, levels[target]):
                lines.append(_cmd("automation.set_point", {"track": target, "param": "volume", "at": at, "value": value}))

    lines.append(_cmd("file.bounce_mix", {"path": str(bounce), "bit_depth": "16", "normalize": m["normalize"]}))
    if stems_dir is not None:
        lines.append(_cmd("file.bounce_stems", {"dir": str(stems_dir), "bit_depth": "16"}))
    return lines


def fade_points(op: str, shape: str, n: int, length: int, base_db: float, steps: int = 24) -> list[tuple[int, float]]:
    """Automation points (sample, dB) for a fade of `n` samples at the start or end of the song."""
    import math

    curves = {
        "linear": lambda x: x,
        "equal power": lambda x: math.sin(x * math.pi / 2),
        "s-curve": lambda x: (1 - math.cos(math.pi * x)) / 2,
        "exponential": lambda x: x * x,
        "logarithmic": lambda x: math.sqrt(x),
    }
    curve = curves.get(shape, curves["s-curve"])
    pts = []
    for i in range(steps + 1):
        x = i / steps
        g = curve(x) if op == "fade_in" else curve(1 - x)
        at = int(round(x * n)) if op == "fade_in" else length - n + int(round(x * n))
        db = base_db + 20 * math.log10(g) if g > 1e-4 else -80.0
        pts.append((max(0, at), round(max(-80.0, db), 2)))
    return pts


def _insert_lines(track: str, inserts: list[dict]) -> list[str]:
    out = []
    for slot, ins in enumerate(inserts[:10]):
        p = {"track": track, "slot": slot, "plugin": ins["plugin"]}
        if ins["params"]:
            p["params"] = ins["params"]
        out.append(_cmd("mix.insert", p))
        if ins["bypass"]:
            out.append(_cmd("mix.insert_bypass", {"track": track, "slot": slot, "value": True}))
    return out


# ------------------------------------------------------------------ rendering

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def render(doc: dict, sources: list[Path], source_seconds: float, out_wav: Path, *,
           session: Path | None = None, stems_dir: Path | None = None, key: str = "") -> dict:
    """Render the edit document. Returns {lufs, peak_db, true_peak_db, seconds, path}."""
    with _lock(key or str(out_wav)):
        result = _render_once(doc, sources, source_seconds, out_wav, session, stems_dir, 0.0)
        target = doc["master"].get("loudness")
        if target is not None and result["lufs"] > -100:
            delta = round(target - result["lufs"], 2)
            if abs(delta) >= 0.2:
                result = _render_once(doc, sources, source_seconds, out_wav, session, stems_dir, delta)
                result["loudness_gain_db"] = delta
        return result


def _render_once(doc, sources, source_seconds, out_wav, session, stems_dir, master_gain) -> dict:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    if stems_dir is not None:
        shutil.rmtree(stems_dir, ignore_errors=True)
        stems_dir.mkdir(parents=True)
    lines = build_script(doc, sources, source_seconds, out_wav, stems_dir, master_gain)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(lines) + "\n")
        script = f.name
    try:
        args = ["script", script]
        if session is not None:
            if session.parent.exists():
                shutil.rmtree(session.parent)
            session.parent.mkdir(parents=True)
            args += ["--save", str(session)]
        out = _run(args)
    finally:
        os.unlink(script)
    bounce = next((ln for ln in out.splitlines() if ln.startswith("file.bounce_mix:")), None)
    if bounce is None:
        raise StudioError("SoundCraft didn't bounce the mix")
    info = json.loads(bounce.split(": ", 1)[1])
    return {k: info.get(k) for k in ("lufs", "peak_db", "true_peak_db", "seconds", "path")}


def zip_session(session: Path, dst_zip: Path) -> Path:
    """Zip a saved session folder (the .scraft file and its Audio Files)."""
    base = dst_zip.with_suffix("")
    return Path(shutil.make_archive(str(base), "zip", root_dir=session.parent))
