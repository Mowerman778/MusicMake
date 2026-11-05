"""Background worker: runs generation, extend, remix and stem jobs one at a time."""

from __future__ import annotations

import queue
import threading
import traceback
import uuid
from pathlib import Path
from typing import Callable

import numpy as np

from . import stems as stem_split
from .audio import convert_to_wav, duration_of, has_ffmpeg, peaks, read_wav, write_wav
from .engines import EngineError, SongRequest, Take, get_engine
from .store import Store


def default_title(req: SongRequest) -> str:
    if req.title.strip():
        return req.title.strip()[:80]
    for line in req.lyrics.splitlines():
        line = line.strip()
        if line and not line.startswith("[") and not line.startswith("("):
            return line[:60]
    words = (req.prompt or req.style_text() or "Untitled").strip().split()
    return " ".join(words[:6]).capitalize()[:60] or "Untitled"


class Worker:
    def __init__(self, store: Store):
        self.store = store
        self.q: queue.Queue[Callable[[], None]] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="musicmake-worker", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while True:
            job = self.q.get()
            try:
                job()
            except Exception:  # noqa: BLE001 - a job never kills the worker
                traceback.print_exc()
            finally:
                self.q.task_done()

    def wait_idle(self) -> None:
        self.q.join()

    # ---------------------------------------------------------------- saving
    def _save_take(self, song_id: str, take: Take, keep_stems: bool = True) -> None:
        dst = self.store.audio_path(song_id)
        if take.file is not None:
            src = Path(take.file)
            if src.suffix.lower() == ".wav" and not has_ffmpeg():
                src.replace(dst)
            else:
                convert_to_wav(src, dst)
                src.unlink(missing_ok=True)
            audio, _ = read_wav(dst)
        else:
            audio = take.audio
            write_wav(dst, audio, take.sr)
        stem_names = []
        if keep_stems and take.stems:
            for name, data in take.stems.items():
                write_wav(self.store.stem_path(song_id, name), data, take.sr)
                stem_names.append(name)
        fields = dict(status="done", progress=1.0, message="Ready", meta=take.meta,
                      duration=round(duration_of(dst), 2), peaks=peaks(audio),
                      stems=stem_names, stems_status="done" if stem_names else None)
        if take.lyrics:
            fields["lyrics"] = take.lyrics
        self.store.update(song_id, **fields)

    def _progress(self, ids: list[str]):
        def report(p: float, msg: str) -> None:
            for i in ids:
                self.store.update(i, status="running", progress=round(float(np.clip(p, 0, 1)), 3), message=msg)
        return report

    def _fail(self, ids: list[str], err: Exception) -> None:
        msg = str(err) if isinstance(err, (EngineError, RuntimeError)) else f"{type(err).__name__}: {err}"
        for i in ids:
            self.store.update(i, status="failed", error=msg[:500], message="Failed")

    # ---------------------------------------------------------------- jobs
    def submit_create(self, req: SongRequest, engine_name: str | None) -> list[dict]:
        engine = get_engine(engine_name)
        group = uuid.uuid4().hex[:12]
        title = default_title(req)
        n = max(1, min(int(req.takes), 4 if engine.name == "sketch" else 8))
        songs = [self.store.create(group_id=group, kind="create", title=title if n == 1 else f"{title} ({chr(65 + i)})",
                                   engine=engine.name, request=req.to_dict(), lyrics=req.lyrics)
                 for i in range(n)]
        ids = [s["id"] for s in songs]

        def job() -> None:
            try:
                takes = engine.generate(req, self._progress(ids))
                for song_id, take in zip(ids, takes):
                    self._save_take(song_id, take)
                for song_id in ids[len(takes):]:
                    self.store.update(song_id, status="failed", error="The engine returned fewer takes than asked")
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self._fail(ids, e)

        self.q.put(job)
        return songs

    def _submit_edit(self, kind: str, parent: dict, req: SongRequest, engine_name: str | None,
                     run: Callable) -> dict:
        made_by = parent.get("engine") if parent.get("engine") in ("sketch", "acestep") else None
        engine = get_engine(engine_name or made_by)
        suffix = {"extend": "extended", "remix": "remix"}[kind]
        song = self.store.create(group_id=uuid.uuid4().hex[:12], kind=kind, parent_id=parent["id"],
                                 title=f"{parent['title']} ({suffix})", engine=engine.name,
                                 request=req.to_dict(), lyrics=req.lyrics or parent.get("lyrics", ""))

        def job() -> None:
            try:
                take = run(engine, self.store.audio_path(parent["id"]), parent.get("meta") or {},
                           self._progress([song["id"]]))
                self._save_take(song["id"], take, keep_stems=kind == "remix")
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self._fail([song["id"]], e)

        self.q.put(job)
        return song

    def submit_extend(self, parent: dict, seconds: float, lyrics: str, engine_name: str | None) -> dict:
        req = SongRequest.from_dict({**(parent.get("request") or {}), "lyrics": lyrics, "takes": 1})
        seconds = float(min(max(seconds, 10), 240))
        return self._submit_edit("extend", parent, req, engine_name,
                                 lambda eng, src, meta, prog: eng.extend(req, src, meta, seconds, prog))

    def submit_remix(self, parent: dict, styles: list[str], strength: float, lyrics: str | None,
                     engine_name: str | None) -> dict:
        base = dict(parent.get("request") or {})
        base.update({"styles": styles or base.get("styles", []), "takes": 1})
        if lyrics is not None:
            base["lyrics"] = lyrics
        req = SongRequest.from_dict(base)
        return self._submit_edit("remix", parent, req, engine_name,
                                 lambda eng, src, meta, prog: eng.remix(req, src, meta, strength, prog))

    def submit_stems(self, song: dict) -> dict:
        song_id = song["id"]
        self.store.update(song_id, stems_status="running")

        def job() -> None:
            try:
                out = stem_split.separate(self.store.audio_path(song_id), self.store.song_dir(song_id) / "stems")
                self.store.update(song_id, stems=sorted(out), stems_status="done")
            except Exception as e:  # noqa: BLE001
                self.store.update(song_id, stems_status="failed", error=f"Stems: {e}"[:500])

        self.q.put(job)
        return self.store.get(song_id)

    # ---------------------------------------------------------------- studio (SoundCraft)
    def studio_sources(self, song: dict, source: str) -> list[tuple[str, Path]]:
        """(track name, file) pairs for the studio. Track names are the file names SoundCraft uses."""
        if source == "stems" and song.get("stems"):
            return [(n, self.store.stem_path(song["id"], n)) for n in song["stems"]]
        return [("song", self.store.audio_path(song["id"]))]

    def submit_studio_save(self, parent: dict, doc: dict, title: str) -> dict:
        from . import studio

        sources = self.studio_sources(parent, doc["source"])
        song = self.store.create(group_id=uuid.uuid4().hex[:12], kind="edit", parent_id=parent["id"],
                                 title=(title or f"{parent['title']} (edited)")[:80], engine="soundcraft",
                                 request=parent.get("request") or {}, lyrics=parent.get("lyrics", ""))
        song_id = song["id"]

        def job() -> None:
            try:
                self.store.update(song_id, status="running", progress=0.3, message="Rendering in SoundCraft")
                stems_dir = self.store.song_dir(song_id) / "stems"
                secs = max(duration_of(p) for _, p in sources)
                info = studio.render(doc, [p for _, p in sources], secs, self.store.audio_path(song_id),
                                     stems_dir=stems_dir, key=song_id)
                names = []
                for f in sorted(stems_dir.glob("*.wav")):
                    name = f.stem.split(" - ", 1)[-1]
                    f.rename(stems_dir / f"{name}.wav")
                    names.append(name)
                audio, _ = read_wav(self.store.audio_path(song_id))
                meta = {**(parent.get("meta") or {}), "engine": "soundcraft",
                        "made_with": parent.get("engine"), "loudness": info, "studio": doc}
                self.store.update(song_id, status="done", progress=1.0, message="Ready", meta=meta,
                                  duration=round(duration_of(self.store.audio_path(song_id)), 2),
                                  peaks=peaks(audio), stems=names, stems_status="done" if names else None)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self._fail([song_id], e)

        self.q.put(job)
        return song

    def import_upload(self, src: Path, title: str) -> dict:
        song = self.store.create(group_id=uuid.uuid4().hex[:12], kind="upload", title=title[:80] or "Upload",
                                 engine="upload", request={}, status="running")
        try:
            convert_to_wav(src, self.store.audio_path(song["id"]))
            audio, _ = read_wav(self.store.audio_path(song["id"]))
            return self.store.update(song["id"], status="done", progress=1.0, message="Ready",
                                     meta={"engine": "upload"}, peaks=peaks(audio),
                                     duration=round(duration_of(self.store.audio_path(song["id"])), 2))
        except Exception as e:  # noqa: BLE001
            self._fail([song["id"]], e)
            return self.store.get(song["id"])
