# MusicMake — Plan: Analysing suno.com with Craft Anything

This plan uses the engine described in
[Craft Anything → Under the hood](https://github.com/storytold/craft-anything#under-the-hood).
That engine is a pure-Rust reverse-engineering engine with ~320 tools, and every tool is also a
CLI command (`craft-anything-cli <tool-id-with-dashes>`) and an MCP tool. The plan uses it to
study **suno.com**, an AI music-generation product. The goal is to learn from it and design
**MusicMake**, our own original music-creation app.

## Status (2026-11-04)

MusicMake is a private, non-commercial project.

| Phase | Status | Where |
|---|---|---|
| A. Set up | ✅ Done. Craft Anything 0.4.0 built from source; `doctor` reports healthy; brief and plan recorded | `research/suno.cany` |
| B. Hand-taken screenshots | ⏸ Waiting on you. It needs your own Suno account and browser, and automated capture isn't allowed | `research/screenshots/` (git-ignored) |
| C. Public research | ✅ Done. 3 source notes (landing page, terms, open models), one evidence record each | `research/sources/` |
| D. Synthesis | ✅ Done. 5 findings, 2 hypotheses, 4 open questions, report written | `docs/suno-analysis.md`, `docs/musicmake-spec.md`, `research/craft-anything-report.md` |
| E. Build | ✅ Done. MusicMake v0.2: web app, Sketch (CPU) and ACE-Step 1.5 (GPU) engines, Demucs stems, Claude lyric helper | `musicmake/`, `README.md` |
| F. Check | ✅ Done. 28 tests pass; browser walkthroughs of our own app (library and Studio) at 3 widths plus dark mode; originality review | `tests/`, `docs/images/` |
| G. Studio | ✅ Done. Audio editing and mixing powered by [SoundCraft](https://github.com/storytold/soundcraft) 0.17.0 through its headless CLI | `musicmake/studio.py`, `musicmake/static/studio.js` |

Notes on how the tools were used:

- Clean-room mode refuses to open any file, even our own notes. `--deep` was used **only** to
  open our own notes in `research/sources/`, so they could be cited as evidence. Nothing from
  suno.com was opened by any tool.
- The Check phase drove our own app with Playwright directly, rather than through Craft
  Anything's `web_walkthrough_*` tools.

---

## 0. Ground rules (read first)

Suno's Terms of Service (suno.com/terms) prohibit:

- reverse engineering or trying to discover source code,
- scraping, data mining, "robots" or similar extraction methods,
- getting at content "through any means not intentionally" provided,
- circumventing content protections or blocks,
- using the service "to create, develop or improve any competing products or services",
- getting Outputs any way except Suno's own download channels.

Craft Anything's own Responsible-use rule says the same: use it only on software you own or are
allowed to examine. It never bypasses logins, DRM or anti-cheat.

**What this means for the plan:**

| Allowed in this plan | Not allowed in this plan |
|---|---|
| **Clean-room mode only** (the default) | Deep mode on suno.com (`web_page_js_analyze`, `web_modules_trace`, `js_sources_restore`, `web_coverage_measure`, `web_scripts_save`, …) |
| Screenshots a **person** takes while using Suno normally, added to the project as pictures | Automated crawling or capture of suno.com (`web_site_capture`, `web_walkthrough_record` and `web_page_watch` pointed at suno.com) |
| Suno's public landing page, terms and help-centre articles, read by a person and summarised in our own words | Calling Suno's private APIs, or a stand-in backend copied from its network traffic |
| Music-AI research papers and open-weight models | Copying Suno's name, logo, artwork, text, audio or exact layout |
| Our own original design, inspired by the *genre* of "prompt → song" tools | Training on, or redistributing, Suno outputs |

> Before going further, check with a lawyer if MusicMake will be commercial.
> "Competing product" is in Suno's prohibited-use list. Keeping this analysis
> to *public, human-observed product behaviour*, and building from open research, is the safest path.

```sh
craft-anything-cli settings-set deep_mode false   # stay in Clean room for the whole project
```

---

## 1. Goals

1. **Understand the product surface.** What can a user do on Suno, and how is it organised?
2. **Understand the UX patterns.** Prompt entry, the simple/custom split, lyrics, styles,
   sliders, the track list and player, remix and extend, stems, the studio/DAW.
3. **Understand the technology at a public level only.** What music-AI capabilities are needed,
   and which **open** models and papers can provide them.
4. **Turn all of this into a spec** for MusicMake that is clearly our own.

Not a goal: a pixel or feature clone of Suno.

---

## 2. What we already know (public pages, Nov 2026)

From the public landing page:

- **Navigation:** Products (Studio, MCP, Voices, Stem Separation, Remix, Custom Models, mobile
  apps), Resources (Music Library, AI Music Tools, Help Center).
- **Core flow:** text prompt → full song with vocals, lyrics and production.
- **Controls:** style, exclusions, vocal gender, "weirdness" and style-influence sliders.
- **Features:** Studio (a browser DAW), Voices (sing with your own voice sample), Stem
  Separation, Remix (change style, lyrics or base recording), Custom Models (train on your own
  recordings), Music Library, community sharing and discovery.

---

## 3. Workflow (mapped to Craft Anything's Study → Build → Check → Ready)

### Phase A — Set up the investigation

```sh
craft-anything-cli doctor                         # check install, coding agent, engines
craft-anything-cli settings-show                  # confirm deep_mode = false
```

| Step | Tool | Purpose |
|---|---|---|
| A1 | `core_brief_write` | Brief: "Study suno.com's public product and UX (clean room), to design an original music app." |
| A2 | `core_plan_update` | Load phases B–F below as the plan. |
| A3 | `core_unknown_add` | Seed the open questions (section 4). |

### Phase B — Human-observed capture (clean room)

A person uses Suno normally in their own browser, signed into their own account, at normal speed.
They take screenshots of each screen at **desktop (1440), tablet (768) and phone (390)** widths.
Nothing is automated against suno.com.

Screens to capture:

1. Landing page (public)
2. Create — simple mode (one prompt)
3. Create — custom mode (lyrics, style tags, exclusions, sliders, instrumental toggle)
4. Generation in progress (loading states, two takes per prompt)
5. Library / workspace (track list, filters, playlists)
6. Player (bottom bar, waveform, track page)
7. Track actions menu (extend, remix, cover, stems, download, share)
8. Song editor / Studio (timeline, sections, stems)
9. Voices and Custom Models set-up flows
10. Explore / community feed, and creator profile
11. Mobile app home and create (optional)

Feed them into Craft Anything as **pictures**, the way Clean room supports:

| Step | Tool | Purpose |
|---|---|---|
| B1 | `core_target_open` (on the screenshot folder) | Open the pictures as the target |
| B2 | `core_target_triage` | Classify what each picture shows |
| B3 | `core_finding_record` | One finding per screen: purpose, inputs, outputs, states |
| B4 | `core_hypothesis_record` | e.g. "Two takes per prompt so the user picks one, which lowers bad-output frustration" |
| B5 | `core_person_ask` | Ask the observer about anything the pictures don't show (timings, errors, limits) |

### Phase C — Public-sources research

Read and summarise, in our own words, with links:

- Help-centre articles: limits and supported formats
- Public music-AI research and **open-weight models** we could build on:
  - text-to-music: MusicGen / AudioCraft (Meta), Stable Audio Open, ACE-Step, YuE (lyrics → song with vocals), DiffRhythm
  - stems: Demucs / HT-Demucs
  - lyrics: an LLM (e.g. Claude) for lyric drafting and structure tags
  - voice: open singing-voice conversion (check licences, and **consent only**)

Record each source with `core_finding_record`, and mark open points with `core_unknown_add`.
Check each open-model licence with `core_finding_record` (licence, commercial use: yes or no).

### Phase D — Synthesis

| Step | Tool | Output |
|---|---|---|
| D1 | `core_investigation_show` / `core_evidence_browse` | Review everything collected |
| D2 | `core_unknown_verify` | Close or mark the open questions |
| D3 | `core_report_write` | **`docs/suno-analysis.md`**: feature map, UX patterns, user journeys, gaps |
| D4 | `core_handoff_write` | **`docs/musicmake-spec.md`**: the original MusicMake spec |
| D5 | `core_evidence_export` | Evidence bundle in `research/` for traceability |

Report outline (`docs/suno-analysis.md`):

1. Feature inventory (table: feature, inputs, outputs)
2. Core user journeys: prompt → song, lyrics → song, upload → remix, song → stems → studio
3. UX patterns worth learning from (and ones to avoid)
4. Generation parameters exposed to users
5. Community and discovery loop
6. Gaps and opportunities for MusicMake

### Phase E — Build MusicMake (original design)

Use Craft Anything's builder **from our own spec, not from Suno**:

```sh
craft-anything-cli rebuild - "Build MusicMake from docs/musicmake-spec.md: an original \
  prompt-to-song web app with its own name, look and copy" \
  --project-folder /path/to/MusicMake --existing edit
```

Suggested first slice (MVP):

1. Prompt + optional lyrics + style tags → generate a song with an open model (ACE-Step or
   YuE for vocals, MusicGen for instrumentals), behind a small job queue
2. Library with a player and two takes per prompt
3. Lyric helper (an LLM): write and structure ([Verse], [Chorus], …)
4. Stem split (Demucs)
5. Export to WAV and MP3

Our own, clearly different identity: name, palette, typography, copy and layout.

### Phase F — Check

Craft Anything's Check step normally compares the build *with the original*. Here we
**do not aim for similarity**. Use the checks the other way round:

| Step | Tool | Purpose |
|---|---|---|
| F1 | `web_walkthrough_record` / `web_walkthrough_check` **on our own app** | Our user journeys work end-to-end |
| F2 | `web_page_screenshot_take` on our own app (3 widths) | Responsive layout works |
| F3 | `app_coverage_evaluate` against **our spec** | How much of the spec is built |
| F4 | `app_rebuild_claim_check` | Check the builder's "done" claims |
| F5 | Manual review | No Suno names, assets, text or look-alike layout leaked in |

---

## 4. Open questions to seed (`core_unknown_add`)

- How long is a generation from submit to playable, and is the result streamed or delivered whole?
- How are the takes per prompt shown and picked?
- What is the maximum song length, and how does "extend" choose its continue point?
- What do the "weirdness" and "style influence" sliders change, from what the user can see?
- How are lyrics structure tags shown and edited?
- What does the Studio timeline let a user change (sections, stems, MIDI)?
- Which open models can match the product at each step, and under which licences?

---

## 5. Deliverables (in this repo)

```
PLAN.md                   ← this file
docs/suno-analysis.md     ← Phase D3 report (clean-room, public info only)
docs/musicmake-spec.md    ← Phase D4 original product spec
research/                 ← exported evidence bundle + human screenshots (private; don't commit Suno assets publicly)
app/                      ← MusicMake source (Phase E)
```

> Note: Suno screenshots are for internal reference only. Keep them out of a public repo, or
> add `research/screenshots/` to `.gitignore`.

## 6. Milestones

| # | Milestone | Done when |
|---|---|---|
| 1 | Setup | `doctor` passes; Clean room confirmed; brief, plan and unknowns written |
| 2 | Capture | Every screen in Phase B captured at 3 widths and recorded as findings |
| 3 | Research | Public sources and open-model licences recorded |
| 4 | Report | `docs/suno-analysis.md` and `docs/musicmake-spec.md` written |
| 5 | MVP | Prompt → song → library → stems works in MusicMake |
| 6 | Check | Walkthroughs pass; spec coverage measured; originality review passed |
