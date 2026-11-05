# Investigation report

**Question:** What does suno.com offer, how is its product organised, and what does a private, original prompt-to-song app (MusicMake) need in order to cover the same kinds of jobs?

**Purpose:** Learning, to design and build a private, non-commercial music maker. Not a clone.

**Done when:** docs/suno-analysis.md and docs/musicmake-spec.md are written, and MusicMake's first version covers prompt to song, lyrics, takes, extend, remix, stems and export.

## What we looked at

- 01-landing-page.md (unknown)
- 02-terms.md (unknown)
- 03-open-models.md (unknown)
- https://suno.com (public pages only)
- /home/user/MusicMake/research/sources

## What we found

### The core job is one prompt in, a complete song with vocals, lyrics and production out; everything else (Studio, Voices, Remix, Stems, Custom Models) builds on a generated or uploaded track.

- **Confidence:** Seen it (observed)
- **Evidence:**
  - `ev_08a832f4737e9f011324add0afd1932e510c44dbc7089086d68ec3da4a9bfd77` — 01-landing-page.md isn't a format we recognise yet.

### User controls named publicly are: style, things to leave out, vocal gender, an adventurousness-type slider and a style-influence slider, plus a simple prompt-only mode.

- **Confidence:** Seen it (observed)
- **Evidence:**
  - `ev_08a832f4737e9f011324add0afd1932e510c44dbc7089086d68ec3da4a9bfd77` — 01-landing-page.md isn't a format we recognise yet.

### The Terms forbid reverse engineering, scraping, robots and building competing products, so only public, hand-read information is used and nothing is automated against suno.com.

- **Confidence:** Seen it (observed)
- **Evidence:**
  - `ev_b3ac72c5a6aab7a79b2cd0f06ab5db7f641ac3304602df5822fc938b8ee2631a` — 02-terms.md isn't a format we recognise yet.

### ACE-Step 1.5 (MIT) covers text-to-song with vocals, remix (cover) and extend (repaint) through a local REST API on under 4 GB of VRAM; Demucs (MIT) covers stem splitting.

- **Confidence:** Seen it (observed)
- **Evidence:**
  - `ev_139a998f33b4ee253ceaf84275996bf30ec40320784cb338883c8a18fb411fdd` — 03-open-models.md isn't a format we recognise yet.

### For a private app, the jobs worth covering first are: prompt to song, lyrics to song, two takes, extend, remix, stems, download, library with favourites, and a lyric helper.

- **Confidence:** Worked it out (derived)
- **Evidence:**
  - `ev_08a832f4737e9f011324add0afd1932e510c44dbc7089086d68ec3da4a9bfd77` — 01-landing-page.md isn't a format we recognise yet.
  - `ev_139a998f33b4ee253ceaf84275996bf30ec40320784cb338883c8a18fb411fdd` — 03-open-models.md isn't a format we recognise yet.

## Open questions

- What does the 'weirdness' slider change, as far as a listener can tell? _(severity Medium, Open)_
  - would settle it: Make the same prompt at low and high settings and compare by ear
- How does extend pick where to continue, and can the user choose the point? _(severity Medium, Open)_
  - would settle it: Use extend on a song and note the options shown
- Which open model gives the best vocals on a consumer GPU today? _(severity Medium, Open)_
  - would settle it: Make the same lyrics with ACE-Step 1.5, YuE and DiffRhythm and compare
- How long from submit to playable, and is audio streamed while it generates? _(severity Medium, Open)_
  - would settle it: Time several generations by hand
  - would settle it: Watch whether playback starts before the end
- (hypothesis, still testing) Generating two takes per prompt lets people pick the better one, which hides the variance of generative models.
- (hypothesis, still testing) A local open model (ACE-Step 1.5) plus Demucs covers the core jobs for a private app.

## How this was done

- **Mode:** Clean room (nothing inside the original was read)
- **Engines:** builtin
- **Limitations:**
  - the kind is detected from the first bytes and, to break ties, the file name

## Handoff

Research and MVP are done. Next: (1) the owner captures Suno screens by hand at 3 widths, adds them to research/screenshots/ (git-ignored) and records findings per screen; (2) run ACE-Step 1.5 on a GPU and compare vocals against YuE/DiffRhythm; (3) answer the open questions. Trap: don't point web_site_capture, web_walkthrough_record or any Deep tool at suno.com.

## Evidence ledger

- `ev_08a832f4737e9f011324add0afd1932e510c44dbc7089086d68ec3da4a9bfd77` **core_target_triage** — 01-landing-page.md isn't a format we recognise yet. (Best guess)
- `ev_b3ac72c5a6aab7a79b2cd0f06ab5db7f641ac3304602df5822fc938b8ee2631a` **core_target_triage** — 02-terms.md isn't a format we recognise yet. (Best guess)
- `ev_139a998f33b4ee253ceaf84275996bf30ec40320784cb338883c8a18fb411fdd` **core_target_triage** — 03-open-models.md isn't a format we recognise yet. (Best guess)

