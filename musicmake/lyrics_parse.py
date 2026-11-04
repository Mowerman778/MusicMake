"""Parse lyrics with section tags such as [Verse 1], [Chorus], [Bridge]."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TAG = re.compile(r"^\s*\[([^\]]+)\]\s*$")

SECTION_KINDS = ("intro", "verse", "pre-chorus", "chorus", "bridge", "solo", "outro")


@dataclass
class Section:
    kind: str                 # one of SECTION_KINDS
    label: str                # as written, e.g. "Verse 2"
    lines: list[str] = field(default_factory=list)


def section_kind(label: str) -> str:
    low = label.lower()
    if "pre" in low and "chorus" in low:
        return "pre-chorus"
    for kind in ("intro", "verse", "chorus", "bridge", "outro"):
        if kind in low:
            return kind
    if any(w in low for w in ("hook", "refrain")):
        return "chorus"
    if any(w in low for w in ("solo", "instrumental", "break", "interlude", "drop")):
        return "solo"
    return "verse"


def parse_lyrics(text: str) -> list[Section]:
    """Split lyrics into sections. Untagged lyrics are grouped into verse/chorus pairs."""
    text = (text or "").strip()
    if not text:
        return []
    sections: list[Section] = []
    current: Section | None = None
    tagged = False
    for raw in text.splitlines():
        line = raw.strip()
        m = TAG.match(line)
        if m:
            tagged = True
            label = m.group(1).strip()
            current = Section(section_kind(label), label)
            sections.append(current)
            continue
        if not line:
            continue
        if line.startswith("(") and line.endswith(")"):
            continue  # stage directions like "(guitar solo)"
        if current is None:
            current = Section("verse", "Verse")
            sections.append(current)
        current.lines.append(line)

    if tagged:
        return sections

    # No tags: four lines per block, alternating verse and chorus.
    lines = sections[0].lines
    out: list[Section] = []
    for i in range(0, len(lines), 4):
        kind = "verse" if (i // 4) % 2 == 0 else "chorus"
        out.append(Section(kind, kind.title(), lines[i:i + 4]))
    return out


VOWELS = re.compile(r"[aeiouy]+", re.I)


def syllables(line: str) -> list[str]:
    """Rough syllables for a sung line. Returns the vowel sound of each one (a/e/i/o/u)."""
    out: list[str] = []
    for word in re.findall(r"[A-Za-z']+", line):
        groups = VOWELS.findall(word)
        if len(groups) > 1 and word.lower().endswith("e") and not word.lower().endswith(("le", "ee")):
            groups = groups[:-1]  # silent final e
        if not groups:
            groups = ["a"]
        for g in groups:
            v = g[0].lower()
            out.append("i" if v == "y" else v)
    return out
