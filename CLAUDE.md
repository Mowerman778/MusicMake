# MusicMake: notes for Claude

A private, local prompt-to-song music maker. Python (FastAPI) backend, plain HTML/CSS/JS frontend
with no build step. The owner runs it on a laptop with a GPU from VS Code.

## Run and check

- Set up: `./scripts/setup.sh` (macOS/Linux) or `scripts\setup.ps1` (Windows). It creates `.venv`.
- Check the machine: `python -m musicmake doctor`. It reports GPU, ACE-Step, SoundCraft, ffmpeg, Demucs and Claude.
- Start: ACE-Step first (`uv run acestep-api` in `../ACE-Step-1.5`), then `python -m musicmake`,
  then open http://127.0.0.1:8765. VS Code task "Start everything" does both.
- Tests: `python -m pytest -q`. The Studio end-to-end tests skip without `soundcraft-cli`.
  Run the tests after every change.
- Sketch-only mode (no GPU): `python -m musicmake --engine sketch`.

## Layout

| Path | What it is |
|---|---|
| `musicmake/server.py` | FastAPI app and every `/api/...` route |
| `musicmake/jobs.py` | Background worker: create, extend, remix, stems, Studio save |
| `musicmake/store.py` | SQLite library; files in `data/songs/<id>/` |
| `musicmake/engines/` | `sketch.py` (CPU synth), `acestep.py` (ACE-Step 1.5 REST client), `base.py` (types) |
| `musicmake/studio.py` | Studio: edit document → SoundCraft engine commands → `soundcraft-cli script` |
| `musicmake/stems.py` | Demucs stem splitting |
| `musicmake/lyrics.py` | Lyric helper (Claude via the Anthropic SDK, or an offline template) |
| `musicmake/doctor.py` | `python -m musicmake doctor` |
| `musicmake/static/` | `index.html`, `app.js` (library, player), `studio.js` (Studio), `style.css` |
| `tests/` | pytest |
| `docs/` | `musicmake-spec.md` (the spec), `laptop-setup.md`, `suno-analysis.md` |
| `research/` | Clean-room study notes and the Craft Anything project |

## External engines

- **ACE-Step 1.5** (MIT): a separate server on port 8001, in its own uv environment, never imported.
  API: `POST /release_task`, `POST /query_result`, `GET /v1/audio`. Docs:
  https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/API.md
- **SoundCraft** (MIT or Apache-2.0): `soundcraft-cli` (on PATH, or `SOUNDCRAFT_CLI`). List its
  commands with `soundcraft-cli commands`; show one's parameters with
  `soundcraft-cli describe <id>`. Positions are in samples at 48 kHz. Clip ids change after
  edits, so Studio works by selection (`edit.select` → `edit.separate` → `edit.select`).
- **Demucs**: run as `python -m demucs`; it uses CUDA if torch has it.

## Rules for this project

- Keep it private and local: bind to 127.0.0.1, and don't add accounts or telemetry.
- The Suno study is clean-room only. Never automate, scrape or read the code of suno.com, and
  don't copy Suno's names, text, assets or layout. Pricing and news are deliberately left out.
- Frontend stays build-free (no npm). It must work at 390 px wide and in dark mode.
- Studio edits stay non-destructive: change the edit document and re-render. Never modify a
  song's original files.
