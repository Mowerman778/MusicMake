"""Lyric helper.

With Anthropic credentials available (ANTHROPIC_API_KEY, or an `ant auth login` profile),
Claude writes structured lyrics. Without them, an offline template gives a starting
structure the person can fill in.
"""

from __future__ import annotations

import json
import os
import re

MODEL = os.environ.get("MUSICMAKE_LYRICS_MODEL", "claude-opus-5-5")

SYSTEM = """You write original song lyrics for a private music-making app.

Return lyrics only, using section tags on their own lines, chosen from:
[Intro] [Verse 1] [Verse 2] [Pre-Chorus] [Chorus] [Bridge] [Outro]
Keep lines short and singable (4 to 10 syllables). The chorus repeats and carries the hook.
Never reproduce or closely paraphrase existing copyrighted lyrics, and don't imitate a
named living artist's lyrics. Write something new.

Answer with a JSON object: {"title": "...", "lyrics": "..."}."""


def _claude_available() -> bool:
    if os.environ.get("MUSICMAKE_OFFLINE_LYRICS"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("ANTHROPIC_PROFILE") or os.path.isdir(os.path.expanduser("~/.config/anthropic")))


def write_lyrics(topic: str, styles: str = "", mood: str = "", length: str = "medium",
                 existing: str = "") -> dict:
    """Returns {"title", "lyrics", "source"} where source is "claude" or "template"."""
    if _claude_available():
        try:
            return _with_claude(topic, styles, mood, length, existing)
        except Exception as e:  # noqa: BLE001 - fall back, but say why
            out = _template(topic, mood)
            out["note"] = f"Claude was unavailable ({type(e).__name__}); here is a template instead."
            return out
    return _template(topic, mood)


def _with_claude(topic: str, styles: str, mood: str, length: str, existing: str) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    shape = {"short": "two verses and a chorus", "medium": "two verses, a chorus after each, and a bridge",
             "long": "three verses, pre-choruses, a chorus after each, a bridge and an outro"}.get(length, "two verses and a chorus")
    ask = [f"Topic: {topic or 'anything you like'}"]
    if styles:
        ask.append(f"Musical style: {styles}")
    if mood:
        ask.append(f"Mood: {mood}")
    ask.append(f"Structure: {shape}")
    if existing.strip():
        ask.append("Improve and complete these draft lyrics, keeping the person's best lines:\n" + existing)

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": "\n".join(ask)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("the request was declined")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return _parse_reply(text) | {"source": "claude"}


def _parse_reply(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            if data.get("lyrics"):
                return {"title": str(data.get("title", "")).strip(), "lyrics": str(data["lyrics"]).strip()}
        except json.JSONDecodeError:
            pass
    return {"title": "", "lyrics": text}


def _template(topic: str, mood: str) -> dict:
    subject = (topic or "this feeling").strip().rstrip(".")
    title = subject.title()[:60]
    lyrics = f"""[Verse 1]
(where are we, what do we see)
Thinking about {subject}
(a detail only you would notice)
(a line that sets up the chorus)

[Chorus]
(the hook: say the title here)
{title}
(repeat the hook, change one word)
(a line that lands the feeling{', ' + mood if mood else ''})

[Verse 2]
(time has passed: what changed)
(a new detail about {subject})
(a turn in the story)
(set up the chorus again)

[Chorus]
(the hook: say the title here)
{title}
(repeat the hook, change one word)
(a line that lands the feeling)

[Bridge]
(step back: the bigger picture)
(the one thing left unsaid)
"""
    return {"title": title, "lyrics": lyrics, "source": "template"}
