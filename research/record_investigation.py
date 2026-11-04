"""Record the suno.com clean-room investigation in Craft Anything (research/suno.cany).

Usage: python3 research/record_investigation.py /path/to/craft-anything-cli

Re-running it rewrites the brief, plan and handoff, and adds the findings, hypotheses and
open questions again, so run it once per fresh project folder.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "suno.cany"
SOURCES = ROOT / "sources"


def call(cli: str, tool: str, params: dict | None = None, deep: bool = False) -> dict:
    cmd = [cli, "--project", str(PROJECT), "--deep" if deep else "--clean-room", "--format", "json", tool]
    if params is not None:
        cmd += ["--json", json.dumps(params)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"{tool} failed:\n{out.stdout}\n{out.stderr}")
    return json.loads(out.stdout) if out.stdout.strip() else {}


def main(cli: str) -> None:
    # Evidence: one triage record per source note. --deep here only lets the engine read
    # OUR OWN notes in research/sources; nothing from suno.com is opened or read.
    ev = {}
    for f in sorted(SOURCES.glob("*.md")):
        rec = call(cli, "core-target-triage", {"path": str(f)}, deep=True)
        ev[f.stem[:2]] = rec["id"]
    landing, pricing, terms, timeline, models = (ev[k] for k in ("01", "02", "03", "04", "05"))

    call(cli, "core-brief-write", {
        "question": "What does suno.com offer, how is its product organised, and what does a private, "
                    "original prompt-to-song app (MusicMake) need in order to cover the same kinds of jobs?",
        "purpose": "Learning, to design and build a private, non-commercial music maker. Not a clone.",
        "targets": ["https://suno.com (public pages only)", str(SOURCES)],
        "constraints": [
            "Clean room for suno.com: public pages read by hand; no page source, scripts, network traffic or APIs",
            "No automated capture, crawling or scraping of suno.com (its Terms forbid robots and scraping)",
            "No Suno names, logos, text, audio or look-alike layout in MusicMake",
            "Deep mode is used only to open our own notes in research/sources",
        ],
        "done_when": "docs/suno-analysis.md and docs/musicmake-spec.md are written, and MusicMake's first "
                     "version covers prompt to song, lyrics, takes, extend, remix, stems and export.",
    })

    call(cli, "core-plan-update", {"steps": [
        {"title": "Set up: doctor, clean room, brief, plan, open questions", "status": "done",
         "why": "craft-anything-cli 0.4.0 built from source; doctor healthy"},
        {"title": "Capture: a person screenshots ~12 screens at 3 widths while using Suno normally", "status": "blocked",
         "why": "Needs the owner's own account and browser; automated capture is not allowed"},
        {"title": "Research: public pages, pricing, terms, release coverage, open models", "status": "done",
         "why": "Notes in research/sources, one evidence record each"},
        {"title": "Synthesis: docs/suno-analysis.md and docs/musicmake-spec.md", "status": "done",
         "why": "Written from the findings below"},
        {"title": "Build: MusicMake MVP (FastAPI + web UI, Sketch and ACE-Step 1.5 engines, Demucs, lyric helper)",
         "status": "done", "why": "musicmake/ package with tests"},
        {"title": "Check: walkthroughs and screenshots of MusicMake itself, spec coverage, originality review",
         "status": "doing", "why": "Automated tests and a browser walkthrough of our own app"},
    ]})

    for q, probes in [
        ("How long from submit to playable, and is audio streamed while it generates?",
         ["Time several generations by hand on the free tier", "Watch whether playback starts before the end"]),
        ("How many credits does each action cost (generate, extend, remix, stems)?",
         ["Read the help centre's credits article", "Note the credit counter before and after each action"]),
        ("What does the 'weirdness' slider change, as far as a listener can tell?",
         ["Make the same prompt at low and high settings and compare by ear"]),
        ("How does extend pick where to continue, and can the user choose the point?",
         ["Use extend on a song and note the options shown"]),
        ("Which open model gives the best vocals on a consumer GPU today?",
         ["Make the same lyrics with ACE-Step 1.5, YuE and DiffRhythm and compare"]),
    ]:
        call(cli, "core-unknown-add", {"question": q, "probes": probes, "domain": "product", "severity": "medium"})

    call(cli, "core-hypothesis-record", {
        "claim": "Generating two takes per prompt lets people pick the better one, which hides the variance of generative models.",
        "prediction": "Each create action shows two results; the pricing counts songs, not prompts.",
        "evidence_for": [landing, pricing],
    })
    call(cli, "core-hypothesis-record", {
        "claim": "A local open model (ACE-Step 1.5) plus Demucs covers the core jobs for a private app.",
        "prediction": "ACE-Step 1.5 offers text2music, cover (remix) and repaint (extend); Demucs gives 4 stems.",
        "evidence_for": [models],
    })

    findings = [
        ("The core job is one prompt in, a complete song with vocals, lyrics and production out; everything "
         "else (Studio, Voices, Remix, Stems, Custom Models) builds on a generated or uploaded track.", [landing], "observed"),
        ("User controls named publicly are: style, things to leave out, vocal gender, an adventurousness-type "
         "slider and a style-influence slider, plus a simple prompt-only mode.", [landing], "observed"),
        ("Pricing is credit-based with a free daily allowance and two paid tiers; downloads, commercial rights, "
         "stem types, Studio and upload length are what separate the tiers.", [pricing], "observed"),
        ("The Terms forbid reverse engineering, scraping, robots and building competing products, so only "
         "public, hand-read information is used and nothing is automated against suno.com.", [terms], "observed"),
        ("Recent direction (third-party coverage): personalisation (own voice, custom models, taste), a "
         "browser DAW (Studio), and a v6 model family with free and paid variants.", [timeline], "inferred"),
        ("ACE-Step 1.5 (MIT) covers text-to-song with vocals, remix (cover) and extend (repaint) through a "
         "local REST API on under 4 GB of VRAM; Demucs (MIT) covers stem splitting.", [models], "observed"),
        ("For a private app, the jobs worth covering first are: prompt to song, lyrics to song, two takes, "
         "extend, remix, stems, download, library with favourites, and a lyric helper.", [landing, pricing, models], "derived"),
    ]
    for statement, ids, conf in findings:
        call(cli, "core-finding-record", {"statement": statement, "evidence_ids": ids, "confidence": conf})

    call(cli, "core-handoff-write", {"text": (
        "Research and MVP are done. Next: (1) the owner captures Suno screens by hand at 3 widths, adds them to "
        "research/screenshots/ (git-ignored) and records findings per screen; (2) run ACE-Step 1.5 on a GPU and "
        "compare vocals against YuE/DiffRhythm; (3) answer the open questions. Trap: don't point web_site_capture, "
        "web_walkthrough_record or any Deep tool at suno.com.")})

    call(cli, "core-report-write", {"format": "markdown", "path": str(ROOT / "craft-anything-report.md")})
    print("recorded; report at", ROOT / "craft-anything-report.md")


if __name__ == "__main__":
    main(sys.argv[1])
