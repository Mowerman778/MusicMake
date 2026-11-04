# Investigation report

**Question:** What does suno.com offer, how is its product organised, and what does a private, original prompt-to-song app (MusicMake) need in order to cover the same kinds of jobs?

**Purpose:** Learning, to design and build a private, non-commercial music maker. Not a clone.

**Done when:** docs/suno-analysis.md and docs/musicmake-spec.md are written, and MusicMake's first version covers prompt to song, lyrics, takes, extend, remix, stems and export.

## What we looked at

- 01-landing-page.md (unknown)
- 02-pricing.md (unknown)
- 03-terms.md (unknown)
- 04-release-timeline.md (unknown)
- 05-open-models.md (unknown)
- https://suno.com (public pages only)
- /home/user/MusicMake/research/sources

## What we found

### The core job is one prompt in, a complete song with vocals, lyrics and production out; everything else (Studio, Voices, Remix, Stems, Custom Models) builds on a generated or uploaded track.

- **Confidence:** Seen it (observed)
- **Evidence:**
  - `ev_7d4c5590c94411e26ce88f6b4ba252b852de408f6b9f907f3523affedd27b555` — 01-landing-page.md isn't a format we recognise yet.

### User controls named publicly are: style, things to leave out, vocal gender, an adventurousness-type slider and a style-influence slider, plus a simple prompt-only mode.

- **Confidence:** Seen it (observed)
- **Evidence:**
  - `ev_7d4c5590c94411e26ce88f6b4ba252b852de408f6b9f907f3523affedd27b555` — 01-landing-page.md isn't a format we recognise yet.

### Pricing is credit-based with a free daily allowance and two paid tiers; downloads, commercial rights, stem types, Studio and upload length are what separate the tiers.

- **Confidence:** Seen it (observed)
- **Evidence:**
  - `ev_9aa2e6e8d7234afb70b04fd187fe382a653dd7ffaabe657e5b912a3dfddf6cdc` — 02-pricing.md isn't a format we recognise yet.

### The Terms forbid reverse engineering, scraping, robots and building competing products, so only public, hand-read information is used and nothing is automated against suno.com.

- **Confidence:** Seen it (observed)
- **Evidence:**
  - `ev_0ed7b49a322a85cfef2227f15e76e5a99c4ed44579fb0a54f2e5963eb4e92836` — 03-terms.md isn't a format we recognise yet.

### Recent direction (third-party coverage): personalisation (own voice, custom models, taste), a browser DAW (Studio), and a v6 model family with free and paid variants.

- **Confidence:** Best guess (inferred)
- **Evidence:**
  - `ev_aeda28e90a1566472eb7b25bb863c7d2e34875b3afc89cb6d3c701195ec78ca9` — 04-release-timeline.md isn't a format we recognise yet.

### ACE-Step 1.5 (MIT) covers text-to-song with vocals, remix (cover) and extend (repaint) through a local REST API on under 4 GB of VRAM; Demucs (MIT) covers stem splitting.

- **Confidence:** Seen it (observed)
- **Evidence:**
  - `ev_62e5efca72852bf136a23d3f821f4b2d7ea1c869fa674f88ca1c17428710a281` — 05-open-models.md isn't a format we recognise yet.

### For a private app, the jobs worth covering first are: prompt to song, lyrics to song, two takes, extend, remix, stems, download, library with favourites, and a lyric helper.

- **Confidence:** Worked it out (derived)
- **Evidence:**
  - `ev_7d4c5590c94411e26ce88f6b4ba252b852de408f6b9f907f3523affedd27b555` — 01-landing-page.md isn't a format we recognise yet.
  - `ev_9aa2e6e8d7234afb70b04fd187fe382a653dd7ffaabe657e5b912a3dfddf6cdc` — 02-pricing.md isn't a format we recognise yet.
  - `ev_62e5efca72852bf136a23d3f821f4b2d7ea1c869fa674f88ca1c17428710a281` — 05-open-models.md isn't a format we recognise yet.

## Open questions

- What does the 'weirdness' slider change, as far as a listener can tell? _(severity Medium, Open)_
  - would settle it: Make the same prompt at low and high settings and compare by ear
- How does extend pick where to continue, and can the user choose the point? _(severity Medium, Open)_
  - would settle it: Use extend on a song and note the options shown
- Which open model gives the best vocals on a consumer GPU today? _(severity Medium, Open)_
  - would settle it: Make the same lyrics with ACE-Step 1.5, YuE and DiffRhythm and compare
- How many credits does each action cost (generate, extend, remix, stems)? _(severity Medium, Open)_
  - would settle it: Read the help centre's credits article
  - would settle it: Note the credit counter before and after each action
- How long from submit to playable, and is audio streamed while it generates? _(severity Medium, Open)_
  - would settle it: Time several generations by hand on the free tier
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

- `ev_7d4c5590c94411e26ce88f6b4ba252b852de408f6b9f907f3523affedd27b555` **core_target_triage** — 01-landing-page.md isn't a format we recognise yet. (Best guess)
- `ev_9aa2e6e8d7234afb70b04fd187fe382a653dd7ffaabe657e5b912a3dfddf6cdc` **core_target_triage** — 02-pricing.md isn't a format we recognise yet. (Best guess)
- `ev_0ed7b49a322a85cfef2227f15e76e5a99c4ed44579fb0a54f2e5963eb4e92836` **core_target_triage** — 03-terms.md isn't a format we recognise yet. (Best guess)
- `ev_aeda28e90a1566472eb7b25bb863c7d2e34875b3afc89cb6d3c701195ec78ca9` **core_target_triage** — 04-release-timeline.md isn't a format we recognise yet. (Best guess)
- `ev_62e5efca72852bf136a23d3f821f4b2d7ea1c869fa674f88ca1c17428710a281` **core_target_triage** — 05-open-models.md isn't a format we recognise yet. (Best guess)

