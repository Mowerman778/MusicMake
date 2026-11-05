"""Studio (SoundCraft) tests. The end-to-end ones run only when soundcraft-cli is installed
(on PATH, or SOUNDCRAFT_CLI pointing at it)."""

import json
import os
import time

import pytest

from musicmake import studio

FAKE_PLUGINS = [
    {"id": "compressor", "name": "Compressor/Limiter", "category": "Dynamics", "instrument": False,
     "params": [{"id": "threshold", "min": -60.0, "max": 0.0, "default": -20.0, "unit": "Db", "choices": []},
                {"id": "ratio", "min": 1.0, "max": 100.0, "default": 4.0, "unit": "Ratio", "choices": []}]},
    {"id": "maximizer", "name": "Maximizer", "category": "Dynamics", "instrument": False,
     "params": [{"id": "ceiling", "min": -30.0, "max": 0.0, "default": -0.3, "unit": "Db", "choices": []}]},
    {"id": "gain", "name": "Gain", "category": "Other", "instrument": False,
     "params": [{"id": "gain", "min": -96.0, "max": 24.0, "default": 0.0, "unit": "Db", "choices": []}]},
]


@pytest.fixture()
def fake_plugins(monkeypatch):
    monkeypatch.setattr(studio, "plugins", lambda: FAKE_PLUGINS)


def cmds(lines):
    return [(ln.split(" ", 1)[0], json.loads(ln.split(" ", 1)[1])) for ln in lines]


def test_validate_doc_cleans_input(fake_plugins):
    names = ["drums", "bass"]
    doc = studio.validate_doc({
        "tracks": [{"name": "drums", "volume_db": 99, "pan": -5,
                    "inserts": [{"plugin": "compressor", "params": {"threshold": -100, "bogus": 1}}]}],
        "master": {"loudness": -14},
        "edits": [{"op": "gain", "start": 1, "end": 2, "db": -6, "tracks": ["bass"]},
                  {"op": "fade_out", "length": 3, "shape": "nope"}],
    }, names)
    assert [t["name"] for t in doc["tracks"]] == names
    d = doc["tracks"][0]
    assert d["volume_db"] == 12 and d["pan"] == -1
    assert d["inserts"][0]["params"] == {"threshold": -60.0}
    assert doc["master"]["loudness"] == -14
    assert doc["edits"][1]["shape"] == "s-curve"


@pytest.mark.parametrize("edit, msg", [
    ({"op": "explode"}, "Unknown edit"),
    ({"op": "cut", "start": 3, "end": 3}, "Select a range"),
    ({"op": "gain", "start": 1, "end": 2, "tracks": ["nope"]}, "No track named"),
    ({"op": "process", "process": "nope", "start": 1, "end": 2}, "Unknown effect"),
])
def test_validate_doc_rejects(fake_plugins, edit, msg):
    with pytest.raises(studio.StudioError, match=msg):
        studio.validate_doc({"edits": [edit]}, ["drums"])


def test_build_script_timeline_and_mix(fake_plugins, tmp_path):
    doc = studio.validate_doc({
        "tracks": [{"name": "drums", "mute": True, "inserts": [{"plugin": "compressor", "bypass": True}]},
                   {"name": "bass", "volume_db": -3, "pan": 0.5}],
        "edits": [{"op": "cut", "start": 1, "end": 2},
                  {"op": "keep", "start": 0, "end": 5},
                  {"op": "gain", "start": 1, "end": 2, "db": -6, "tracks": ["bass"]},
                  {"op": "fade_in", "length": 1}],
    }, ["drums", "bass"])
    lines = cmds(studio.build_script(doc, [tmp_path / "drums.wav", tmp_path / "bass.wav"], 10.0, tmp_path / "out.wav"))
    ids = [c for c, _ in lines]
    assert ids[:2] == ["session.new", "file.import_audio"]
    # cut 1..2 s ripples; keep 0..5 s cuts the tail (5 s .. 9 s left after the first cut)
    clears = [p for c, p in lines if c == "edit.select"]
    assert {"tracks": ["drums", "bass"], "start": 48000, "end": 96000} in clears
    assert {"tracks": ["drums", "bass"], "start": 240000, "end": 432000} in clears
    assert ("clip.gain", {"delta_db": -6.0}) in lines
    assert ("mix.mute", {"tracks": ["drums"], "value": True}) in lines
    assert ("mix.insert_bypass", {"track": "drums", "slot": 0, "value": True}) in lines
    assert ("mix.pan", {"tracks": ["bass"], "pan": 0.5}) in lines
    fades = [p for c, p in lines if c == "automation.set_point"]
    assert fades[0] == {"track": studio.MASTER, "param": "volume", "at": 0, "value": -80.0}
    assert fades[-1]["at"] == 48000 and fades[-1]["value"] == 0.0
    assert ids[-1] == "file.bounce_mix"


def test_loudness_gain_goes_before_a_limiter(fake_plugins, tmp_path):
    doc = studio.validate_doc({"master": {"inserts": []}}, ["song"])
    lines = cmds(studio.build_script(doc, [tmp_path / "song.wav"], 5.0, tmp_path / "o.wav", master_gain=4.0))
    master = [p["plugin"] for c, p in lines if c == "mix.insert" and p["track"] == studio.MASTER]
    assert master == ["gain", "maximizer"]


def test_fade_points_shapes():
    pts = studio.fade_points("fade_out", "linear", 48000, 480000, -2.0, steps=4)
    assert pts[0] == (432000, -2.0) and pts[-1] == (480000, -80.0)
    assert all(a <= b for (a, _), (b, _) in zip(pts, pts[1:]))


def test_missing_cli(monkeypatch):
    monkeypatch.setenv("SOUNDCRAFT_CLI", "/nonexistent/soundcraft-cli")
    ok, detail = studio.available()
    assert not ok and "cargo install" in detail


# ---------------------------------------------------------------- end to end with SoundCraft

needs_cli = pytest.mark.skipif(not studio.cli_path(), reason="soundcraft-cli not installed")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSICMAKE_ENGINE", "sketch")
    monkeypatch.setenv("ACESTEP_URL", "http://127.0.0.1:9")
    from fastapi.testclient import TestClient

    from musicmake.server import create_app

    app = create_app(tmp_path)
    with TestClient(app) as c:
        c.app_ref = app
        yield c


def make_song(client):
    s = client.post("/api/songs", json={"styles": ["pop"], "lyrics": "[Verse]\nHello there\n[Chorus]\nLa la la",
                                        "duration": 25, "takes": 1, "seed": 2}).json()[0]
    client.app_ref.state.worker.wait_idle()
    return client.get(f"/api/songs/{s['id']}").json()


@needs_cli
def test_studio_render_save_and_session(client):
    song = make_song(client)
    st = client.get(f"/api/songs/{song['id']}/studio").json()
    assert st["tracks"] == ["drums", "bass", "chords", "lead", "vocals"] and st["render"] is None
    doc = st["doc"]
    doc["edits"] = [{"op": "cut", "start": 2, "end": 5},
                    {"op": "process", "process": "reverse", "start": 1, "end": 2, "tracks": ["drums"]},
                    {"op": "fade_out", "length": 2}]
    doc["tracks"][0]["inserts"] = [{"plugin": "compressor", "params": {"ratio": 3}}]
    doc["master"]["loudness"] = -14
    r = client.post(f"/api/songs/{song['id']}/studio/render", json={"doc": doc})
    assert r.status_code == 200, r.text
    st = r.json()
    assert abs(st["duration"] - (st_dur := song["duration"]) + 3) < 0.6, (st["duration"], st_dur)
    assert abs(st["render"]["lufs"] + 14) < 0.6
    assert st["render"]["true_peak_db"] < 0.5
    assert client.get(f"/api/songs/{song['id']}/studio/preview").status_code == 200

    # The edit document is kept, so reopening shows it.
    again = client.get(f"/api/songs/{song['id']}/studio").json()
    assert len(again["doc"]["edits"]) == 3 and again["render"]["lufs"] == st["render"]["lufs"]

    z = client.get(f"/api/songs/{song['id']}/studio/session.zip")
    assert z.status_code == 200 and z.content[:2] == b"PK"

    new = client.post(f"/api/songs/{song['id']}/studio/save", json={"doc": doc, "title": "Shorter"}).json()
    client.app_ref.state.worker.wait_idle()
    new = client.get(f"/api/songs/{new['id']}").json()
    assert new["status"] == "done", new["error"]
    assert new["kind"] == "edit" and new["title"] == "Shorter" and new["parent_id"] == song["id"]
    assert sorted(new["stems"]) == ["bass", "chords", "drums", "lead", "vocals"]
    assert abs(new["meta"]["loudness"]["lufs"] + 14) < 0.6

    reset = client.post(f"/api/songs/{song['id']}/studio/reset").json()
    assert reset["doc"]["edits"] == [] and reset["render"] is None


@needs_cli
def test_studio_mix_source_and_errors(client):
    song = make_song(client)
    st = client.post(f"/api/songs/{song['id']}/studio/render", json={"doc": {"source": "mix"}}).json()
    assert st["tracks"] == ["song"]
    bad = client.post(f"/api/songs/{song['id']}/studio/render",
                      json={"doc": {"source": "mix", "edits": [{"op": "gain", "start": 1, "end": 1}]}})
    assert bad.status_code == 400
    info = client.get("/api/studio").json()
    assert info["available"] and any(p["id"] == "plate_reverb" for p in info["plugins"])
    assert not any(p["id"] == "sampler" for p in info["plugins"])
