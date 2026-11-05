"""MusicMake web server. Run with `python -m musicmake` and open http://127.0.0.1:8765."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, studio
from .audio import duration_of, export_mp3, has_ffmpeg, peaks, read_wav
from .engines import EngineError, SongRequest, engines_status
from .jobs import Worker
from .lyrics import write_lyrics
from .stems import demucs_available
from .store import Store

STATIC = Path(__file__).parent / "static"


class CreateBody(BaseModel):
    prompt: str = ""
    lyrics: str = ""
    styles: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    instrumental: bool = False
    duration: float = Field(120, ge=10, le=600)
    bpm: Optional[int] = Field(None, ge=30, le=300)
    key: Optional[str] = None
    seed: Optional[int] = None
    takes: int = Field(2, ge=1, le=8)
    adventurous: float = Field(0.5, ge=0, le=1)
    title: str = ""
    engine: Optional[str] = None


class ExtendBody(BaseModel):
    seconds: float = Field(30, ge=10, le=240)
    lyrics: str = ""
    engine: Optional[str] = None


class RemixBody(BaseModel):
    styles: list[str] = Field(default_factory=list)
    strength: float = Field(0.5, ge=0, le=1)
    lyrics: Optional[str] = None
    engine: Optional[str] = None


class PatchBody(BaseModel):
    title: Optional[str] = None
    liked: Optional[bool] = None
    lyrics: Optional[str] = None


class LyricsBody(BaseModel):
    topic: str = ""
    styles: str = ""
    mood: str = ""
    length: str = "medium"
    existing: str = ""


def _safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9 _().-]+", "", text).strip()[:80] or "song"


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir or os.environ.get("MUSICMAKE_DATA") or Path.cwd() / "data")
    store = Store(data_dir)
    store.fail_unfinished()
    worker = Worker(store)

    app = FastAPI(title="MusicMake", version=__version__)
    app.state.store = store
    app.state.worker = worker

    def song_or_404(song_id: str) -> dict:
        song = store.get(song_id)
        if not song:
            raise HTTPException(404, "No such song")
        return song

    def ready_or_409(song: dict) -> None:
        if song["status"] != "done":
            raise HTTPException(409, "This song isn't finished yet")

    @app.get("/api/health")
    def health():
        return {"version": __version__, "engines": engines_status(),
                "ffmpeg": has_ffmpeg(), "demucs": demucs_available(), "soundcraft": studio.available()[0], "data_dir": str(data_dir)}

    @app.get("/api/songs")
    def list_songs(liked: bool = False, q: str = ""):
        return store.list(liked=liked, query=q)

    @app.post("/api/songs", status_code=201)
    def create_song(body: CreateBody):
        req = SongRequest.from_dict(body.model_dump())
        if not (req.prompt.strip() or req.lyrics.strip() or req.styles):
            raise HTTPException(422, "Describe the song, add styles, or write lyrics")
        try:
            return worker.submit_create(req, body.engine)
        except EngineError as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/songs/{song_id}")
    def get_song(song_id: str):
        return song_or_404(song_id)

    @app.patch("/api/songs/{song_id}")
    def patch_song(song_id: str, body: PatchBody):
        song_or_404(song_id)
        return store.update(song_id, **body.model_dump(exclude_none=True))

    @app.delete("/api/songs/{song_id}", status_code=204)
    def delete_song(song_id: str):
        song = song_or_404(song_id)
        if song["status"] in ("queued", "running"):
            raise HTTPException(409, "Wait for this song to finish before deleting it")
        store.delete(song_id)

    @app.post("/api/songs/{song_id}/extend", status_code=201)
    def extend_song(song_id: str, body: ExtendBody):
        song = song_or_404(song_id)
        ready_or_409(song)
        try:
            return worker.submit_extend(song, body.seconds, body.lyrics, body.engine)
        except EngineError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/songs/{song_id}/remix", status_code=201)
    def remix_song(song_id: str, body: RemixBody):
        song = song_or_404(song_id)
        ready_or_409(song)
        try:
            return worker.submit_remix(song, body.styles, body.strength, body.lyrics, body.engine)
        except EngineError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/songs/{song_id}/stems")
    def split_stems(song_id: str):
        song = song_or_404(song_id)
        ready_or_409(song)
        if song["stems"]:
            return song
        if not demucs_available():
            raise HTTPException(400, "Stem splitting needs Demucs: run `pip install demucs`, then restart MusicMake")
        return worker.submit_stems(song)

    @app.get("/api/songs/{song_id}/audio")
    def song_audio(song_id: str, format: str = "wav", download: bool = False):
        song = song_or_404(song_id)
        ready_or_409(song)
        wav = store.audio_path(song_id)
        name = _safe_name(song["title"])
        if format == "mp3":
            mp3 = wav.with_suffix(".mp3")
            if not mp3.exists():
                try:
                    export_mp3(wav, mp3)
                except RuntimeError as e:
                    raise HTTPException(400, str(e)) from e
            return FileResponse(mp3, media_type="audio/mpeg", filename=f"{name}.mp3" if download else None)
        if format != "wav":
            raise HTTPException(400, "format must be wav or mp3")
        return FileResponse(wav, media_type="audio/wav", filename=f"{name}.wav" if download else None)

    @app.get("/api/songs/{song_id}/stems/{stem}")
    def stem_audio(song_id: str, stem: str, download: bool = False):
        song = song_or_404(song_id)
        if stem not in song["stems"]:
            raise HTTPException(404, "No such stem")
        name = _safe_name(song["title"])
        return FileResponse(store.stem_path(song_id, stem), media_type="audio/wav",
                            filename=f"{name} - {stem}.wav" if download else None)

    @app.post("/api/uploads", status_code=201)
    async def upload(file: UploadFile = File(...), title: str = Form("")):
        if not has_ffmpeg():
            raise HTTPException(400, "Uploading audio needs ffmpeg installed")
        suffix = Path(file.filename or "upload").suffix[:8] or ".audio"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            size = 0
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > 200 * 1024 * 1024:
                    raise HTTPException(413, "Uploads are limited to 200 MB")
                tmp.write(chunk)
        try:
            return worker.import_upload(Path(tmp.name), title or Path(file.filename or "Upload").stem)
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    # ------------------------------------------------------------ studio (SoundCraft)
    def studio_dir(song_id: str) -> Path:
        d = store.song_dir(song_id) / "studio"
        d.mkdir(exist_ok=True)
        return d

    def studio_doc(song: dict, raw: dict | None = None) -> tuple[dict, list]:
        saved = studio_dir(song["id"]) / "edit.json"
        if raw is None and saved.exists():
            raw = json.loads(saved.read_text())
        source = (raw or {}).get("source") or ("stems" if song["stems"] else "mix")
        if source == "stems" and not song["stems"]:
            source = "mix"
        sources = worker.studio_sources(song, source)
        names = [n for n, _ in sources]
        try:
            doc = studio.validate_doc(raw or studio.default_doc(names, source), names)
        except studio.StudioError as e:
            raise HTTPException(400, str(e)) from e
        doc["source"] = source
        return doc, sources

    def studio_state(song: dict, doc: dict, render: dict | None = None) -> dict:
        d = studio_dir(song["id"])
        preview = d / "preview.wav"
        info = render
        if info is None and (d / "render.json").exists():
            info = json.loads((d / "render.json").read_text())
        wav = preview if preview.exists() and info else store.audio_path(song["id"])
        audio, _ = read_wav(wav)
        return {"doc": doc, "tracks": [t["name"] for t in doc["tracks"]], "has_stems": bool(song["stems"]),
                "render": info, "peaks": peaks(audio, 1600), "duration": round(duration_of(wav), 3),
                "preview": bool(info)}

    @app.get("/api/studio")
    def studio_info():
        ok, detail = studio.available()
        out = {"available": ok, "detail": detail, "processes": list(studio.PROCESSES),
               "fade_shapes": list(studio.FADE_SHAPES), "plugins": []}
        if ok:
            try:
                out["plugins"] = studio.plugins()
            except studio.StudioError as e:
                out.update(available=False, detail=str(e))
        return out

    def studio_ready() -> None:
        ok, detail = studio.available()
        if not ok:
            raise HTTPException(400, detail)

    @app.get("/api/songs/{song_id}/studio")
    def studio_get(song_id: str):
        song = song_or_404(song_id)
        ready_or_409(song)
        studio_ready()
        doc, _ = studio_doc(song)
        return studio_state(song, doc)

    @app.post("/api/songs/{song_id}/studio/render")
    def studio_render(song_id: str, body: dict):
        song = song_or_404(song_id)
        ready_or_409(song)
        studio_ready()
        doc, sources = studio_doc(song, body.get("doc") or {})
        d = studio_dir(song_id)
        (d / "edit.json").write_text(json.dumps(doc, indent=1))
        secs = max(duration_of(p) for _, p in sources)
        try:
            info = studio.render(doc, [p for _, p in sources], secs, d / "preview.wav", key=song_id)
        except studio.StudioError as e:
            raise HTTPException(400, str(e)) from e
        info.pop("path", None)
        (d / "render.json").write_text(json.dumps(info))
        return studio_state(song, doc, info)

    @app.post("/api/songs/{song_id}/studio/reset")
    def studio_reset(song_id: str):
        song = song_or_404(song_id)
        shutil.rmtree(store.song_dir(song_id) / "studio", ignore_errors=True)
        studio_ready()
        doc, _ = studio_doc(song)
        return studio_state(song, doc)

    @app.get("/api/songs/{song_id}/studio/preview")
    def studio_preview(song_id: str):
        song_or_404(song_id)
        f = store.song_dir(song_id) / "studio" / "preview.wav"
        if not f.exists():
            raise HTTPException(404, "Nothing rendered yet")
        return FileResponse(f, media_type="audio/wav")

    @app.get("/api/songs/{song_id}/studio/session.zip")
    def studio_session(song_id: str):
        song = song_or_404(song_id)
        ready_or_409(song)
        studio_ready()
        doc, sources = studio_doc(song)
        d = studio_dir(song_id)
        session = d / "session" / f"{_safe_name(song['title'])}.scraft"
        secs = max(duration_of(p) for _, p in sources)
        try:
            studio.render(doc, [p for _, p in sources], secs, d / "session-mix.wav", session=session, key=song_id)
        except studio.StudioError as e:
            raise HTTPException(400, str(e)) from e
        (d / "session-mix.wav").unlink(missing_ok=True)
        z = studio.zip_session(session, d / "session.zip")
        return FileResponse(z, media_type="application/zip", filename=f"{_safe_name(song['title'])} - SoundCraft.zip")

    @app.post("/api/songs/{song_id}/studio/save", status_code=201)
    def studio_save(song_id: str, body: dict):
        song = song_or_404(song_id)
        ready_or_409(song)
        studio_ready()
        doc, _ = studio_doc(song, body.get("doc") or {})
        (studio_dir(song_id) / "edit.json").write_text(json.dumps(doc, indent=1))
        return worker.submit_studio_save(song, doc, str(body.get("title") or ""))

    @app.post("/api/lyrics")
    def lyrics(body: LyricsBody):
        return write_lyrics(body.topic, body.styles, body.mood, body.length, body.existing)

    @app.get("/")
    def index():
        return RedirectResponse("/app/")

    app.mount("/app", StaticFiles(directory=STATIC, html=True), name="static")
    return app
