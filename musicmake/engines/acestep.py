"""ACE-Step 1.5 engine: talks to a local ACE-Step REST server (`uv run acestep-api`).

ACE-Step 1.5 (MIT licence) generates full songs with vocals from a caption and lyrics, and
runs on GPUs with less than 4 GB of VRAM. API reference:
https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/API.md

Flow: POST /release_task -> poll POST /query_result -> GET /v1/audio?path=...
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import httpx

from ..audio import duration_of
from .base import Engine, EngineError, Progress, SongRequest, Take

DEFAULT_URL = "http://127.0.0.1:8001"


class AceStepEngine(Engine):
    name = "acestep"
    label = "ACE-Step 1.5"

    def __init__(self, url: str | None = None, api_key: str | None = None,
                 model: str | None = None, timeout: float = 900.0):
        self.url = (url or os.environ.get("ACESTEP_URL") or DEFAULT_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("ACESTEP_API_KEY", "")
        self.model = model or os.environ.get("ACESTEP_MODEL") or None
        self.timeout = timeout
        self.poll_every = 1.5

    # ------------------------------------------------------------- plumbing
    def _client(self) -> httpx.Client:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        return httpx.Client(base_url=self.url, headers=headers, timeout=60.0)

    @staticmethod
    def _unwrap(resp: httpx.Response):
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, dict) and "code" in body and "data" in body:
            if body.get("code") != 200 or body.get("error"):
                raise EngineError(f"ACE-Step: {body.get('error') or 'request failed'}")
            return body["data"]
        return body

    def available(self) -> tuple[bool, str]:
        try:
            with self._client() as c:
                data = self._unwrap(c.get("/health", timeout=3.0))
            return True, f"connected to {self.url} ({data.get('service', 'ACE-Step')})"
        except Exception as e:  # noqa: BLE001 - any failure means "not reachable"
            return False, f"not reachable at {self.url} ({type(e).__name__})"

    # ------------------------------------------------------------- request building
    def build_payload(self, req: SongRequest) -> dict:
        """Map a MusicMake request to ACE-Step's /release_task fields."""
        p: dict = {
            "thinking": True,
            "batch_size": max(1, min(int(req.takes), 8)),
            "audio_format": "wav",
            "audio_duration": float(min(max(req.duration, 10.0), 600.0)),
            # Adventurousness -> LM sampling temperature (0.6 safe .. 1.1 wild).
            "lm_temperature": round(0.6 + 0.5 * max(0.0, min(1.0, req.adventurous)), 3),
        }
        if self.model:
            p["model"] = self.model
        styles = req.style_text()
        has_lyrics = bool(req.lyrics.strip())
        if not styles and not has_lyrics and req.prompt.strip():
            # Quick mode: let ACE-Step's LM write caption, lyrics and metadata from a description.
            p["sample_query"] = req.prompt.strip() + (" (instrumental)" if req.instrumental else "")
            p["sample_mode"] = True
        else:
            caption = ", ".join(x for x in (styles, req.prompt.strip()) if x)
            p["prompt"] = caption
            p["lyrics"] = "[Instrumental]" if req.instrumental or not has_lyrics else req.lyrics
        if req.exclude:
            p["lm_negative_prompt"] = ", ".join(req.exclude)
        if req.bpm:
            p["bpm"] = int(min(max(req.bpm, 30), 300))
        if req.key:
            p["key_scale"] = req.key
        if req.seed is not None:
            p["use_random_seed"] = False
            p["seed"] = int(req.seed)
        return p

    # ------------------------------------------------------------- task lifecycle
    def _submit(self, c: httpx.Client, payload: dict, files: dict | None = None) -> str:
        if files:
            form = {k: (json.dumps(v) if isinstance(v, (dict, list)) else str(v).lower() if isinstance(v, bool) else str(v))
                    for k, v in payload.items()}
            data = self._unwrap(c.post("/release_task", data=form, files=files))
        else:
            data = self._unwrap(c.post("/release_task", json=payload))
        task_id = data.get("task_id")
        if not task_id:
            raise EngineError("ACE-Step did not return a task id")
        return task_id

    def _wait(self, c: httpx.Client, task_id: str, progress: Progress) -> list[dict]:
        start = time.monotonic()
        while True:
            items = self._unwrap(c.post("/query_result", json={"task_id_list": [task_id]}))
            item = next((x for x in items if x.get("task_id") == task_id), None) if isinstance(items, list) else None
            status = item.get("status") if item else 0
            if status == 1:
                result = item.get("result") or "[]"
                return json.loads(result) if isinstance(result, str) else result
            if status == 2:
                detail = item.get("result") or item.get("error") or "generation failed"
                raise EngineError(f"ACE-Step failed: {str(detail)[:300]}")
            elapsed = time.monotonic() - start
            if elapsed > self.timeout:
                raise EngineError("ACE-Step took too long; check the server's log")
            progress(min(0.9, 0.1 + elapsed / 120.0), "Generating on ACE-Step")
            time.sleep(self.poll_every)

    def _download(self, c: httpx.Client, file_url: str) -> Path:
        fd, tmp = tempfile.mkstemp(suffix=Path(file_url.split("?")[0]).suffix or ".wav")
        os.close(fd)
        with c.stream("GET", file_url) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        return Path(tmp)

    def _takes(self, c: httpx.Client, results: list[dict], req: SongRequest) -> list[Take]:
        takes = []
        seeds = []
        for r in results:
            seeds.extend(str(r.get("seed_value", "")).split(","))
        for i, r in enumerate(results):
            if r.get("status", 1) == 2 or not r.get("file"):
                continue
            path = self._download(c, r["file"])
            metas = r.get("metas") or {}
            try:
                seed = int(seeds[i])
            except (ValueError, IndexError):
                seed = -1
            meta = {
                "engine": "acestep", "bpm": metas.get("bpm"), "key": metas.get("keyscale"),
                "time_signature": metas.get("timesignature"), "genres": metas.get("genres"),
                "caption": r.get("prompt"), "dit_model": r.get("dit_model"), "lm_model": r.get("lm_model"),
            }
            takes.append(Take(audio=None, sr=0, seed=seed, meta=meta, file=path,
                              lyrics=r.get("lyrics") or None))
        if not takes:
            raise EngineError("ACE-Step returned no audio")
        return takes

    # ------------------------------------------------------------- engine API
    def generate(self, req: SongRequest, progress: Progress) -> list[Take]:
        with self._client() as c:
            progress(0.02, "Sending to ACE-Step")
            task = self._submit(c, self.build_payload(req))
            results = self._wait(c, task, progress)
            progress(0.92, "Downloading")
            return self._takes(c, results, req)

    def _edit(self, req: SongRequest, source: Path, extra: dict, progress: Progress) -> Take:
        payload = self.build_payload(SongRequest.from_dict({**req.to_dict(), "takes": 1}))
        payload.pop("sample_query", None)
        payload.pop("sample_mode", None)
        payload.setdefault("prompt", req.style_text() or req.prompt)
        payload.update(extra)
        with self._client() as c, open(source, "rb") as f:
            progress(0.02, "Uploading to ACE-Step")
            task = self._submit(c, payload, files={"src_audio": (source.name, f, "audio/wav")})
            results = self._wait(c, task, progress)
            progress(0.92, "Downloading")
            return self._takes(c, results, req)[0]

    def extend(self, req: SongRequest, source: Path, source_meta: dict,
               seconds: float, progress: Progress) -> Take:
        # Repaint a region that starts at the end of the source and runs past it.
        length = duration_of(source)
        return self._edit(req, source, {
            "task_type": "repaint",
            "repainting_start": round(length, 2),
            "repainting_end": round(length + seconds, 2),
            "audio_duration": round(length + seconds, 2),
            "chunk_mask_mode": "explicit",
        }, progress)

    def remix(self, req: SongRequest, source: Path, source_meta: dict,
              strength: float, progress: Progress) -> Take:
        # "cover": keep the source's structure, change style/lyrics. Lower strength = freer.
        return self._edit(req, source, {
            "task_type": "cover",
            "audio_cover_strength": round(1.0 - 0.8 * max(0.0, min(1.0, strength)), 3),
            "audio_duration": round(duration_of(source), 2),
        }, progress)
