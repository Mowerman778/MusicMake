"""SQLite library of songs, plus where each song's files live on disk."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    kind TEXT NOT NULL,              -- create | extend | remix | upload
    parent_id TEXT,
    title TEXT NOT NULL,
    status TEXT NOT NULL,            -- queued | running | done | failed
    error TEXT,
    progress REAL NOT NULL DEFAULT 0,
    message TEXT,
    engine TEXT,
    request TEXT NOT NULL DEFAULT '{}',
    meta TEXT NOT NULL DEFAULT '{}',
    lyrics TEXT NOT NULL DEFAULT '',
    duration REAL,
    peaks TEXT,
    stems TEXT NOT NULL DEFAULT '[]',
    stems_status TEXT,               -- null | running | done | failed
    liked INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS songs_created ON songs(created_at DESC);
"""

JSON_FIELDS = ("request", "meta", "peaks", "stems")


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.songs_dir = self.data_dir / "songs"
        self.songs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.data_dir / "library.db", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)

    # ---------------------------------------------------------------- paths
    def song_dir(self, song_id: str) -> Path:
        d = self.songs_dir / song_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def audio_path(self, song_id: str) -> Path:
        return self.song_dir(song_id) / "song.wav"

    def stem_path(self, song_id: str, stem: str) -> Path:
        d = self.song_dir(song_id) / "stems"
        d.mkdir(exist_ok=True)
        return d / f"{stem}.wav"

    # ---------------------------------------------------------------- rows
    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        for f in JSON_FIELDS:
            if d.get(f) is not None:
                d[f] = json.loads(d[f])
        d["liked"] = bool(d["liked"])
        return d

    def create(self, *, group_id: str, kind: str, title: str, engine: str, request: dict,
               parent_id: str | None = None, lyrics: str = "", status: str = "queued") -> dict:
        song_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._db.execute(
                "INSERT INTO songs (id, group_id, kind, parent_id, title, status, engine, request, lyrics, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (song_id, group_id, kind, parent_id, title, status, engine, json.dumps(request), lyrics, time.time()),
            )
            self._db.commit()
        return self.get(song_id)

    def get(self, song_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
        return self._row(row)

    def list(self, *, liked: bool | None = None, query: str = "", limit: int = 200) -> list[dict]:
        sql = "SELECT * FROM songs WHERE 1=1"
        args: list = []
        if liked:
            sql += " AND liked = 1"
        if query:
            sql += " AND (title LIKE ? OR lyrics LIKE ? OR request LIKE ?)"
            args += [f"%{query}%"] * 3
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        return [self._row(r) for r in rows]

    def update(self, song_id: str, **fields) -> dict | None:
        if not fields:
            return self.get(song_id)
        cols, vals = [], []
        for k, v in fields.items():
            if k in JSON_FIELDS and v is not None:
                v = json.dumps(v)
            if k == "liked":
                v = int(bool(v))
            cols.append(f"{k} = ?")
            vals.append(v)
        vals.append(song_id)
        with self._lock:
            self._db.execute(f"UPDATE songs SET {', '.join(cols)} WHERE id = ?", vals)
            self._db.commit()
        return self.get(song_id)

    def delete(self, song_id: str) -> None:
        import shutil

        with self._lock:
            self._db.execute("DELETE FROM songs WHERE id = ?", (song_id,))
            self._db.commit()
        shutil.rmtree(self.songs_dir / song_id, ignore_errors=True)

    def fail_unfinished(self) -> None:
        """After a restart, jobs that were running can't resume."""
        with self._lock:
            self._db.execute(
                "UPDATE songs SET status = 'failed', error = 'MusicMake restarted before this finished'"
                " WHERE status IN ('queued', 'running')")
            self._db.execute("UPDATE songs SET stems_status = 'failed' WHERE stems_status = 'running'")
            self._db.commit()
