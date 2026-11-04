import os
import time

import pytest
from fastapi.testclient import TestClient

os.environ["MUSICMAKE_ENGINE"] = "sketch"
os.environ["MUSICMAKE_OFFLINE_LYRICS"] = "1"
os.environ["ACESTEP_URL"] = "http://127.0.0.1:9"

from musicmake.audio import has_ffmpeg  # noqa: E402
from musicmake.server import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as c:
        c.app_ref = app
        yield c


def wait_done(client, ids, timeout=60):
    client.app_ref.state.worker.wait_idle()
    deadline = time.time() + timeout
    while time.time() < deadline:
        songs = [client.get(f"/api/songs/{i}").json() for i in ids]
        if all(s["status"] in ("done", "failed") for s in songs):
            return songs
        time.sleep(0.2)
    raise AssertionError("songs did not finish")


def test_health(client):
    h = client.get("/api/health").json()
    names = {e["name"]: e for e in h["engines"]}
    assert names["sketch"]["available"] and not names["acestep"]["available"]


def test_create_validation(client):
    assert client.post("/api/songs", json={}).status_code == 422
    assert client.post("/api/songs", json={"prompt": "x", "duration": 5}).status_code == 422


def test_full_flow(client):
    r = client.post("/api/songs", json={"styles": ["lofi"], "lyrics": "[Verse]\nHello there\n[Chorus]\nLa la la",
                                         "duration": 20, "takes": 2, "seed": 3, "title": "Test"})
    assert r.status_code == 201
    songs = r.json()
    assert [s["title"] for s in songs] == ["Test (A)", "Test (B)"]
    done = wait_done(client, [s["id"] for s in songs])
    a = done[0]
    assert a["status"] == "done", a["error"]
    assert a["duration"] > 15 and len(a["peaks"]) == 240 and "vocals" in a["stems"]

    wav = client.get(f"/api/songs/{a['id']}/audio")
    assert wav.status_code == 200 and wav.content[:4] == b"RIFF"
    stem = client.get(f"/api/songs/{a['id']}/stems/drums?download=true")
    assert stem.status_code == 200 and "attachment" in stem.headers["content-disposition"]
    if has_ffmpeg():
        mp3 = client.get(f"/api/songs/{a['id']}/audio?format=mp3")
        assert mp3.status_code == 200 and mp3.headers["content-type"] == "audio/mpeg"

    liked = client.patch(f"/api/songs/{a['id']}", json={"liked": True, "title": "Renamed"}).json()
    assert liked["liked"] and liked["title"] == "Renamed"
    assert [s["id"] for s in client.get("/api/songs?liked=true").json()] == [a["id"]]

    ext = client.post(f"/api/songs/{a['id']}/extend", json={"seconds": 15}).json()
    rmx = client.post(f"/api/songs/{a['id']}/remix", json={"styles": ["jazz"], "strength": 0.8}).json()
    ext, rmx = wait_done(client, [ext["id"], rmx["id"]])
    assert ext["status"] == "done" and ext["duration"] > a["duration"] and ext["parent_id"] == a["id"]
    assert rmx["status"] == "done" and rmx["meta"]["style"] == "jazz"

    assert client.delete(f"/api/songs/{a['id']}").status_code == 204
    assert client.get(f"/api/songs/{a['id']}").status_code == 404


def test_upload_and_sketch_cannot_remix_it(client, tmp_path):
    if not has_ffmpeg():
        pytest.skip("ffmpeg not installed")
    import numpy as np

    from musicmake.audio import write_wav

    src = tmp_path / "mine.wav"
    write_wav(src, np.zeros((16000, 2), dtype=np.float32), 16000)
    with open(src, "rb") as f:
        up = client.post("/api/uploads", files={"file": ("mine.wav", f, "audio/wav")}).json()
    assert up["status"] == "done" and up["kind"] == "upload"
    rmx = client.post(f"/api/songs/{up['id']}/remix", json={"styles": ["rock"]}).json()
    (rmx,) = wait_done(client, [rmx["id"]])
    assert rmx["status"] == "failed" and "ACE-Step" in rmx["error"]


def test_lyrics_template(client):
    r = client.post("/api/lyrics", json={"topic": "night buses", "mood": "wistful"}).json()
    assert r["source"] == "template" and "[Chorus]" in r["lyrics"]


def test_static_ui(client):
    r = client.get("/app/")
    assert r.status_code == 200 and "MusicMake" in r.text
