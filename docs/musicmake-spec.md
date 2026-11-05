# MusicMake: product spec

*Phase D4 of [PLAN.md](../PLAN.md). This is an original design, informed by
[the analysis](suno-analysis.md). It uses no Suno names, assets, text or layout.*

## What it is

MusicMake is a private music maker that runs on your own computer. You describe a song or write
lyrics, and it makes takes you can play, keep, extend, remix, split into stems and download.
It's for personal use: no accounts and no sharing feed. A built-in Studio, powered by
[SoundCraft](https://github.com/storytold/soundcraft), edits and mixes any song.

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

## Features (v0.2, built)

| Area | Feature |
|---|---|
| Create | **Quick:** a description. **Detailed:** title, lyrics with [Section] tags, styles (with suggestion chips), "leave out", tempo, key, adventurousness (safe to wild), seed. **Shared:** instrumental, length (15 s–8 min), 1–4 takes, engine choice |
| Lyrics | "Help me write": Claude (`claude-opus-5-5`, low effort, refusal fallback on) writes or completes structured lyrics; offline it gives a template instead |
| Library | Search, favourites, rename, delete, waveform per song, live progress for jobs that are running |
| Actions | Extend (10–240 s, optional new lyrics), Remix (new styles, how different), Stems, Download WAV or MP3, "Use these settings" |
| Uploads | Import your own audio (any format ffmpeg reads) to remix or split |
| Player | Play and pause, previous and next, click the waveform to seek, volume, autoplays the next song |
| Details | A drawer with engine, styles, tempo, key, length, seed, lyrics and stems (play or download each) |
| Studio | See [Studio](#studio-soundcraft) below |
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
   ├── Studio          (musicmake/studio.py): soundcraft-cli, optional
   └── Lyric helper    (musicmake/lyrics.py): Anthropic SDK, optional
```

The **Auto** engine uses ACE-Step when its server answers `/health`, and Sketch otherwise.

## Studio (SoundCraft)

Studio is MusicMake's audio editor and mixer. It doesn't do its own signal processing:
everything runs through [SoundCraft](https://github.com/storytold/soundcraft), an open-source
Rust DAW (MIT or Apache-2.0), via its headless `soundcraft-cli`. MusicMake keeps an **edit
document** for each song, turns it into SoundCraft engine commands (`ID JSON` per line), and runs
`soundcraft-cli script`. That makes every edit **non-destructive**: each render starts from the
original files, so any step can be removed in any order.

| Area | What you can do | SoundCraft commands used |
|---|---|---|
| Source | Work on the song's **stems** (one track each) or the **full mix** | `session.new`, `file.import_audio` |
| Timeline edits | Drag to select on the waveform (or type times). **Cut** (closes the gap), **Keep only**, **Silence** | `edit.select`, `edit.mode shuffle`, `edit.clear` |
| Level | **Gain** on a region (±dB), **Normalize** a region | `edit.separate`, `clip.gain`, `audiosuite.process normalize` |
| Process | **Reverse**, **Pitch shift** (±24 semitones), or **any built-in effect rendered onto a region** with its own settings | `audiosuite.process` |
| Fades | Fade in / fade out of the whole song or one track, in 5 shapes (linear, equal power, S-curve, exponential, logarithmic) | `automation.set_point` (volume curves) |
| Mixer | Per track: volume, pan, mute, solo, and up to 10 inserts with bypass and reordering. Every parameter has a control generated from SoundCraft's own parameter list (ranges, units, choices; frequencies on a log scale) | `mix.volume`, `mix.pan`, `mix.mute`, `mix.solo`, `mix.insert`, `mix.insert_bypass` |
| Effects | 24 built-in processors: EQ (1- and 7-band), compressor/limiter, expander/gate, de-esser, maximizer, channel strip, room and plate reverb, mod delay, auto pan, chorus, flanger, phaser, ring mod, saturator, lo-fi, rectifier, subharmonic, pitch shifter, gain, trim, invert, DC removal | `engine.plugins` |
| Master | Volume and inserts. New sessions start with a safety limiter at −1 dB. **Loudness target** (−16, −14, −11 or −9 LUFS): Studio measures, then adds gain before a limiter and renders again | `track.new kind=master`, `file.bounce_mix` |
| Metering | Integrated loudness (LUFS), sample peak and true peak of every render | `file.bounce_mix` result |
| History | Undo and redo (Ctrl+Z, Ctrl+Shift+Z), an edit list where any step can be removed, and Start over | (re-render) |
| Output | **Save as new song** (mix plus bounced stems, linked to the original) or **download a SoundCraft session** (`.scraft` plus audio, zipped) to keep working in the SoundCraft app | `file.bounce_stems`, `session.save` |

Times in the edit list refer to the timeline as it stands after the edits above them, as in a
DAW. Renders run at 48 kHz; a 5-track, 80-second song takes about 3–7 seconds.

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

## Not built yet (next)

1. Train your own style: an ACE-Step LoRA from a few of your own songs (ACE-Step supports this).
2. Section editing: repaint a time range of a song (ACE-Step `repaint` with a chosen start and end).
3. Lyric timestamps: show karaoke-style lyrics from ACE-Step's LRC output.
4. A vocal shoot-out between ACE-Step 1.5, YuE and DiffRhythm, then possibly more engines.
5. Playlists.
6. Studio: clip moves and copy/paste between songs, automation drawing, and sends and busses
   (all of which SoundCraft's engine already has).

## Checks

- `pytest`: 28 tests cover engines, the ACE-Step adapter (against a fake server), API flows,
  uploads, lyrics, Studio script building, and Studio end to end through `soundcraft-cli`.
  The last two skip when SoundCraft isn't installed.
- Browser walkthrough (Playwright): create in Quick and Detailed modes, the lyric helper, play,
  details drawer, menu, extend; Studio: drag-select, cut, region gain, a reverb insert, a loudness
  target, a fade, undo/redo, playback, and save as a new song. Checked at 1440, 768 and 390 px wide and in dark mode, with no
  console errors and no sideways scrolling.
- Originality review: the name, palette, copy, icons and layout are MusicMake's own, and no Suno
  assets or text are in the repo except the clean-room notes in `research/`.
