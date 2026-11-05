# suno.com: clean-room analysis

*Written 2026-11-04 for MusicMake, a private, non-commercial music maker. Phase D3 of [PLAN.md](../PLAN.md).*

## How this was done

- **Clean room only.** Everything here comes from suno.com's public landing page and terms, read
  once by hand. No page source, scripts, network traffic, APIs or generated songs from Suno were
  read, captured or used.
- **No automation against suno.com.** Suno's Terms forbid reverse engineering, scraping and robots.
  That rule applies whatever the purpose, so it holds even though MusicMake is private.
- **Left out on purpose:** pricing, plans and news coverage. They don't affect MusicMake's design.
- **Recorded in Craft Anything.** The notes are in [`research/sources/`](../research/sources), and
  the brief, plan, evidence, findings, hypotheses and open questions are in the
  [`research/suno.cany`](../research/suno.cany) project. The engine's own report is
  [`research/craft-anything-report.md`](../research/craft-anything-report.md). To re-create it, run
  `python3 research/record_investigation.py <path to craft-anything-cli>`.
- **Not done yet:** Phase B, screenshots of the signed-in app. That needs your own account and
  browser (see [What's left](#whats-left)).

## 1. Feature inventory

| Feature | What it does |
|---|---|
| Create, simple | One description → a full song with vocals, lyrics and production |
| Create, custom | Lyrics, style tags, things to leave out, vocal gender, sliders |
| Two takes | Each create gives more than one result to pick from |
| Extend / Remix | Continue a song, or change its style, lyrics or base recording |
| Stem separation | Split a song into time-aligned parts |
| Voices | Sing new lyrics in your own recorded voice |
| Custom Models | A model tuned on your own recordings |
| Studio | A browser multitrack editor for arranging, editing and mixing |
| Uploads | Bring your own audio to remix or extend |
| Music Library / Explore | Browse songs by genre, mood and occasion; creator profiles |
| Mobile apps | iOS and Android |

## 2. Core user journeys

1. **Prompt → song.** Type a description, press create, get two takes, play, keep the one you like.
2. **Lyrics → song.** Write or paste lyrics with section tags, add styles, create.
3. **Upload → remix or extend.** Bring a recording, then change its style or continue it.
4. **Song → stems → studio.** Split a song, then rearrange and mix it in the multitrack editor.
5. **Share → discover.** Publish, browse others' songs, follow creators.

## 3. UX patterns worth learning from

- **One box first, detail second.** A single prompt gets anyone started; the detailed form is a tab away.
- **Several takes per request.** Generative output varies, and picking from two hides the misses.
- **Plain-language controls.** Sliders named for how the music feels, not for model settings.
- **Everything starts from a track.** Extend, remix, stems and studio all act on a song in the library,
  so the library is the hub.
- **A "leave out" field.** It's easier to say what you *don't* want than to describe everything.
- **Generate, then edit.** A studio for trimming, rearranging and mixing turns a generated take
  into a finished song.

Patterns MusicMake skips: public feeds, profiles and accounts. MusicMake is private and local.

## 4. Generation parameters exposed to people

Styles, exclusions, vocal gender, an adventurousness-type slider, a style-influence slider, an
instrumental switch, lyrics with section tags, and (in custom modes) tempo, key and length. In
MusicMake these map to ACE-Step 1.5 fields, listed in [musicmake-spec.md](musicmake-spec.md#engine-mapping).

## 5. Gaps and opportunities for MusicMake

| Need | MusicMake answer |
|---|---|
| Runs without an account | Local app, songs stored on your disk |
| Works without a GPU | **Sketch** engine: CPU-only arranger and synth (instant ideas, rough "la-la" vocals) |
| Realistic vocals and production | **ACE-Step 1.5** (MIT) through its local REST server; under 4 GB VRAM |
| Stems | Sketch songs have stems built in; anything else uses **Demucs** (MIT) |
| Editing and mixing (a "studio") | **Studio, powered by [SoundCraft](https://github.com/storytold/soundcraft)** (MIT or Apache-2.0): cut, keep, silence, region gain, fades, reverse, pitch shift, offline effects, a mixer with 24 built-in plugins, a loudness target, and `.scraft` sessions for the full SoundCraft app |
| Lyrics help | **Claude** writes structured lyrics when an API key is set; offline template otherwise |
| Own voice / own style | Later: ACE-Step LoRA training from a few of your own songs |

## What's left

1. **Screenshots (Phase B), by you, by hand.** Use Suno normally in your own browser and screenshot
   about 11 screens at 1440, 768 and 390 px wide. Put them in `research/screenshots/`, which is
   git-ignored and stays private. Then record a finding per screen in `research/suno.cany`.
2. **Open questions**, tracked in Craft Anything:
   - time to playable;
   - what the adventurousness slider changes;
   - how extend picks its point;
   - which open model gives the best vocals.
3. **Vocal shoot-out.** Run the same lyrics through ACE-Step 1.5, YuE and DiffRhythm on a GPU.

## Sources

- suno.com and suno.com/terms (public pages, read 2026-11-04)
- [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) and its [API docs](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/API.md)
- [Demucs](https://github.com/facebookresearch/demucs)
- [SoundCraft](https://github.com/storytold/soundcraft) 0.17.0, built from source
- [Craft Anything](https://github.com/storytold/craft-anything#under-the-hood) 0.4.0, built from source
