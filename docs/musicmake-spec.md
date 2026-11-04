# MusicMake: product spec

*Phase D4 of [PLAN.md](../PLAN.md). This is an original design, informed by
[the analysis](suno-analysis.md). It uses no Suno names, assets, text or layout.*

## What it is

MusicMake is a private music maker that runs on your own computer. You describe a song or write
lyrics, and it makes takes you can play, keep, extend, remix, split into stems and download.
It's for personal use: no accounts, no sharing feed, and no credits.

## Principles

1. **Private and local.** It binds to 127.0.0.1, keeps songs in a folder you choose, and sends nothing
   anywhere. The only exception is the optional lyric helper, which calls Claude.
2. **Works on any computer.** Without a GPU, the Sketch engine still makes complete arrangements.
   With a GPU, ACE-Step 1.5 makes realistic songs.
3. **Quick first, detailed when you want it.** It has two tabs: Quick (one description) and Detailed
   (lyrics, styles, tempo, key and the rest).
4. **The library is the hub.** Every action starts from a song in it, and every result is a new song
   linked to the one it came from. Nothing is overwritten.
5. **Reproducible.** The same seed with the same settings gives the same Sketch song.

## Features (v0.1, built)

| Area | Feature |
|---|---|
| Create | **Quick:** a description. **Detailed:** title, lyrics with [Section] tags, styles (with suggestion chips), "leave out", tempo, key, adventurousness (safe to wild), seed. **Shared:** instrumental, length (15 s–8 min), 1–4 takes, engine choice |
| Lyrics | "Help me write": Claude (`claude-opus-5-5`, low effort, refusal fallback on) writes or completes structured lyrics; offline it gives a template instead |
| Library | Search, favourites, rename, delete, waveform per song, live progress for jobs that are running |
| Actions | Extend (10–240 s, optional new lyrics), Remix (new styles, how different), Stems, Download WAV or MP3, "Use these settings" |
| Uploads | Import your own audio (any format ffmpeg reads) to remix or split |
| Player | Play and pause, previous and next, click the waveform to seek, volume, autoplays the next song |
| Details | A drawer with engine, styles, tempo, key, length, seed, lyrics and stems (play or download each) |
| Look | Its own warm paper-and-amber theme with dark mode; works at phone width |

## Architecture

```
browser (musicmake/static: HTML/CSS/JS, no build step)
   │  JSON over HTTP
FastAPI (musicmake/server.py) ── Store: SQLite + data/songs/<id>/{song.wav,song.mp3,stems/}
   │
Worker thread (musicmake/jobs.py): one job at a time
   ├── Sketch engine   (musicmake/engines/sketch.py): numpy only, CPU
   ├── ACE-Step engine (musicmake/engines/acestep.py): local REST server, GPU
   ├── Demucs          (musicmake/stems.py): optional, pip install demucs
   └── Lyric helper    (musicmake/lyrics.py): Anthropic SDK, optional
```

The **Auto** engine uses ACE-Step when its server answers `/health`, and Sketch otherwise.

## Engine mapping

| MusicMake control | ACE-Step 1.5 `/release_task` field | Sketch engine |
|---|---|---|
| Quick description (no styles or lyrics) | `sample_query` + `sample_mode` (its LM writes caption, lyrics and metadata) | Style and mood words pick genre, tempo range and major/minor |
| Styles + description | `prompt` (caption) | First style named picks the arrangement |
| Lyrics | `lyrics` (`[Instrumental]` when instrumental) | Sections and lines → melody; syllables sung as vowels |
| Leave out | `lm_negative_prompt` | "drums", "bass" and "vocals" remove those parts |
| Length | `audio_duration` (10–600 s) | Fits sections to the length |
| Tempo / Key | `bpm` / `key_scale` | Used directly |
| Takes | `batch_size` (1–8) | Separate seeds per take (1–4) |
| Adventurousness | `lm_temperature` 0.6–1.1 | Melody leap size and rhythm variety |
| Seed | `seed` + `use_random_seed=false` | Seeds every random choice |
| Extend | `task_type=repaint` from the end of the source, `src_audio` uploaded | Continues with the same key, tempo and chords; crossfaded |
| Remix | `task_type=cover`, `audio_cover_strength` = 1 − 0.8 × "how different" | Re-arranges in new styles; below 50% keeps tempo, key and chords |

## Not in v0.1 (next)

1. Train your own style: an ACE-Step LoRA from a few of your own songs (ACE-Step supports this).
2. Section editing: repaint a time range of a song (ACE-Step `repaint` with a chosen start and end).
3. Lyric timestamps: show karaoke-style lyrics from ACE-Step's LRC output.
4. A vocal shoot-out between ACE-Step 1.5, YuE and DiffRhythm, then possibly more engines.
5. Playlists, and export to a folder of stems that opens in any DAW.

## Checks

- `pytest`: 17 tests cover engines, the ACE-Step adapter (against a fake server), API flows,
  uploads and lyrics.
- Browser walkthrough (Playwright): create in Quick and Detailed modes, the lyric helper, play,
  details drawer, menu, extend. Checked at 1440, 768 and 390 px wide and in dark mode, with no
  console errors and no sideways scrolling.
- Originality review: the name, palette, copy, icons and layout are MusicMake's own, and no Suno
  assets or text are in the repo except the clean-room notes in `research/`.
