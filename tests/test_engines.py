import json

import httpx
import numpy as np
import pytest

from musicmake.audio import write_wav
from musicmake.engines.acestep import AceStepEngine
from musicmake.engines.base import EngineError, SongRequest
from musicmake.engines.sketch import SR, SketchEngine, make_plan, parse_key
from musicmake.lyrics_parse import parse_lyrics, syllables

LYRICS = """[Verse 1]
Morning trains are rolling by
Coffee steam against the sky
[Chorus]
Take me home, take me home
"""

noop = lambda p, m: None  # noqa: E731


def test_parse_key():
    assert parse_key("C major") == (0, "major")
    assert parse_key("Am") == (9, "minor")
    assert parse_key("F# minor") == (6, "minor")
    assert parse_key("Bb") == (10, "major")
    assert parse_key("nonsense") is None


def test_parse_lyrics_tags_and_untagged():
    secs = parse_lyrics(LYRICS)
    assert [s.kind for s in secs] == ["verse", "chorus"]
    assert len(secs[0].lines) == 2
    untagged = parse_lyrics("\n".join(f"line {i}" for i in range(8)))
    assert [s.kind for s in untagged] == ["verse", "chorus"]


def test_syllables():
    assert syllables("Take me home") == ["a", "e", "o"]


def test_sketch_is_deterministic_and_has_stems():
    req = SongRequest(styles=["lofi"], lyrics=LYRICS, duration=30, takes=1, seed=7)
    a = SketchEngine().generate(req, noop)[0]
    b = SketchEngine().generate(req, noop)[0]
    assert a.sr == SR
    assert np.array_equal(a.audio, b.audio)
    assert {"drums", "bass", "chords", "vocals"} <= set(a.stems)
    assert np.abs(a.audio).max() <= 1.0
    assert a.meta["style"] == "lofi"


def test_sketch_takes_differ_and_respect_excludes():
    req = SongRequest(prompt="sad piano", duration=20, takes=2, seed=1, exclude=["drums"])
    takes = SketchEngine().generate(req, noop)
    assert len(takes) == 2
    assert takes[0].seed != takes[1].seed
    assert "drums" not in takes[0].stems
    assert takes[0].meta["mode"] == "minor"


def test_sketch_duration_tracks_request():
    take = SketchEngine().generate(SongRequest(styles=["house"], duration=60, takes=1, seed=3), noop)[0]
    seconds = len(take.audio) / take.sr
    assert 50 <= seconds <= 75


def test_sketch_extend_and_remix(tmp_path):
    eng = SketchEngine()
    req = SongRequest(styles=["pop"], duration=20, takes=1, seed=11)
    take = eng.generate(req, noop)[0]
    src = tmp_path / "song.wav"
    write_wav(src, take.audio, take.sr)
    longer = eng.extend(req, src, take.meta, 20, noop)
    assert len(longer.audio) > len(take.audio)
    remixed = eng.remix(SongRequest(styles=["jazz"], duration=20, takes=1), src, take.meta, 0.2, noop)
    assert remixed.meta["bpm"] == take.meta["bpm"]          # light remix keeps the tempo
    assert remixed.meta["style"] == "jazz"
    with pytest.raises(EngineError):
        eng.extend(req, src, {"engine": "upload"}, 20, noop)


def test_plan_bpm_override():
    plan = make_plan(SongRequest(styles=["rock"], bpm=90, key="D minor"), seed=5)
    assert plan.bpm == 90 and plan.root == 2 and plan.mode == "minor"


# ---------------------------------------------------------------- ACE-Step adapter

def fake_acestep(wav_bytes: bytes):
    calls = {"release": [], "polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        wrap = lambda data: httpx.Response(200, json={"data": data, "code": 200, "error": None})  # noqa: E731
        if request.url.path == "/health":
            return wrap({"status": "ok", "service": "ACE-Step API"})
        if request.url.path == "/release_task":
            calls["release"].append(json.loads(request.content))
            return wrap({"task_id": "t1", "status": "queued"})
        if request.url.path == "/query_result":
            calls["polls"] += 1
            if calls["polls"] < 2:
                return wrap([{"task_id": "t1", "status": 0}])
            result = [{"file": f"/v1/audio?path=/tmp/{i}.wav", "status": 1, "lyrics": "la",
                       "metas": {"bpm": 100, "keyscale": "C Major"}, "seed_value": "1,2"} for i in range(2)]
            return wrap([{"task_id": "t1", "status": 1, "result": json.dumps(result)}])
        if request.url.path == "/v1/audio":
            return httpx.Response(200, content=wav_bytes)
        return httpx.Response(404)

    return handler, calls


def test_acestep_generate_with_fake_server(tmp_path, monkeypatch):
    src = tmp_path / "x.wav"
    write_wav(src, np.zeros((3200, 2), dtype=np.float32), 32000)
    handler, calls = fake_acestep(src.read_bytes())
    eng = AceStepEngine(url="http://ace.test")
    eng.poll_every = 0
    monkeypatch.setattr(eng, "_client", lambda: httpx.Client(base_url="http://ace.test", transport=httpx.MockTransport(handler)))

    assert eng.available()[0]
    req = SongRequest(styles=["pop"], lyrics="[Verse]\nhi", takes=2, duration=30, adventurous=1.0, seed=4)
    takes = eng.generate(req, noop)
    assert len(takes) == 2 and takes[0].file.exists() and takes[0].seed == 1
    sent = calls["release"][0]
    assert sent["prompt"] == "pop" and sent["batch_size"] == 2 and sent["lm_temperature"] == 1.1
    assert sent["seed"] == 4 and sent["use_random_seed"] is False


def test_acestep_quick_mode_and_instrumental():
    eng = AceStepEngine(url="http://ace.test")
    quick = eng.build_payload(SongRequest(prompt="a calm song about the sea"))
    assert quick["sample_query"].startswith("a calm song") and "lyrics" not in quick
    inst = eng.build_payload(SongRequest(styles=["ambient"], instrumental=True, exclude=["drums"]))
    assert inst["lyrics"] == "[Instrumental]" and inst["lm_negative_prompt"] == "drums"


def test_acestep_unreachable():
    ok, detail = AceStepEngine(url="http://127.0.0.1:9").available()
    assert not ok and "not reachable" in detail
