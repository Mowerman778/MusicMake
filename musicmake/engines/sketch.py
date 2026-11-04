"""Sketch engine: an offline, CPU-only arranger and synthesiser.

It does not use a neural network. It reads the styles, mood words and lyrics, picks a
tempo, key, chord progression and drum groove, writes melodies, and renders drums, bass,
chords, a lead and a wordless "voice" that sings the syllables of the lyrics. It is meant
for sketching song ideas, for running MusicMake without a GPU, and for tests. For
realistic vocals and production, use the ACE-Step engine.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..audio import crossfade_concat, normalize, read_wav, to_stereo
from ..lyrics_parse import Section, parse_lyrics, syllables
from .base import Engine, EngineError, Progress, SongRequest, Take

SR = 32000

NOTE_NAMES = {"c": 0, "c#": 1, "db": 1, "d": 2, "d#": 3, "eb": 3, "e": 4, "f": 5,
              "f#": 6, "gb": 6, "g": 7, "g#": 8, "ab": 8, "a": 9, "a#": 10, "bb": 10, "b": 11}
NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]

# Chord progressions as scale degrees (0 = tonic).
PROGRESSIONS = {
    "major": [[0, 4, 5, 3], [0, 5, 3, 4], [5, 3, 0, 4], [0, 3, 4, 3], [0, 3, 5, 4]],
    "minor": [[0, 5, 2, 6], [0, 3, 5, 4], [0, 6, 5, 6], [0, 5, 3, 4], [0, 3, 0, 4]],
}


@dataclass
class Style:
    name: str
    bpm: tuple[int, int]
    mode: str = "major"          # default when no mood word decides it
    drums: str = "four"          # four | rock | hiphop | lofi | half | none | shuffle
    bass: str = "root8"          # root8 | pulse | syncop | long | walk
    pad: str = "soft"            # soft | arp | rhodes | strings | power | pluck
    lead: str = "saw"            # saw | square | sine | bell
    swing: float = 0.0
    sevenths: bool = False
    reverb: float = 0.25


STYLES: dict[str, Style] = {
    "pop": Style("pop", (98, 122), pad="arp"),
    "rock": Style("rock", (112, 140), drums="rock", bass="root8", pad="power", lead="square"),
    "metal": Style("metal", (140, 180), mode="minor", drums="rock", bass="root8", pad="power", lead="square", reverb=0.15),
    "punk": Style("punk", (160, 190), drums="rock", bass="root8", pad="power", lead="square", reverb=0.1),
    "edm": Style("edm", (122, 128), drums="four", bass="syncop", pad="soft", lead="saw"),
    "house": Style("house", (120, 126), drums="four", bass="syncop", pad="rhodes", sevenths=True),
    "techno": Style("techno", (126, 134), mode="minor", drums="four", bass="pulse", pad="soft", lead="square"),
    "electronic": Style("electronic", (110, 128), drums="four", bass="syncop", pad="soft"),
    "synthwave": Style("synthwave", (84, 110), mode="minor", drums="rock", bass="root8", pad="soft", lead="saw", reverb=0.35),
    "hip hop": Style("hip hop", (82, 96), drums="hiphop", bass="syncop", pad="rhodes", lead="sine", swing=0.12, sevenths=True),
    "rap": Style("rap", (82, 96), drums="hiphop", bass="syncop", pad="rhodes", lead="sine", swing=0.1),
    "trap": Style("trap", (130, 150), mode="minor", drums="half", bass="long", pad="soft", lead="bell"),
    "lofi": Style("lofi", (70, 88), drums="lofi", bass="pulse", pad="rhodes", lead="sine", swing=0.18, sevenths=True, reverb=0.3),
    "lo-fi": Style("lofi", (70, 88), drums="lofi", bass="pulse", pad="rhodes", lead="sine", swing=0.18, sevenths=True, reverb=0.3),
    "jazz": Style("jazz", (96, 140), drums="shuffle", bass="walk", pad="rhodes", lead="sine", swing=0.3, sevenths=True),
    "blues": Style("blues", (70, 100), drums="shuffle", bass="walk", pad="rhodes", lead="square", swing=0.3, sevenths=True),
    "r&b": Style("r&b", (68, 92), drums="hiphop", bass="syncop", pad="rhodes", lead="sine", swing=0.1, sevenths=True),
    "soul": Style("soul", (72, 100), drums="rock", bass="syncop", pad="rhodes", lead="sine", sevenths=True),
    "funk": Style("funk", (98, 116), drums="rock", bass="syncop", pad="pluck", lead="square", swing=0.08, sevenths=True),
    "disco": Style("disco", (114, 124), drums="four", bass="root8", pad="strings", lead="saw"),
    "folk": Style("folk", (86, 112), drums="none", bass="pulse", pad="pluck", lead="sine", reverb=0.3),
    "acoustic": Style("acoustic", (80, 110), drums="lofi", bass="pulse", pad="pluck", lead="sine", reverb=0.3),
    "country": Style("country", (96, 124), drums="rock", bass="pulse", pad="pluck", lead="square"),
    "reggae": Style("reggae", (70, 84), drums="half", bass="syncop", pad="pluck", lead="sine"),
    "ambient": Style("ambient", (60, 80), drums="none", bass="long", pad="strings", lead="bell", reverb=0.55),
    "cinematic": Style("cinematic", (70, 96), mode="minor", drums="none", bass="long", pad="strings", lead="sine", reverb=0.5),
    "orchestral": Style("orchestral", (72, 100), drums="none", bass="long", pad="strings", lead="sine", reverb=0.5),
    "classical": Style("classical", (66, 96), drums="none", bass="long", pad="strings", lead="sine", reverb=0.45),
    "piano": Style("piano", (66, 96), drums="none", bass="long", pad="rhodes", lead="bell", reverb=0.4),
    "ballad": Style("ballad", (64, 80), drums="lofi", bass="long", pad="strings", lead="sine", reverb=0.4),
    "chiptune": Style("chiptune", (130, 160), drums="rock", bass="root8", pad="arp", lead="square", reverb=0.05),
}

MINOR_WORDS = ("sad", "dark", "melanchol", "moody", "minor", "lonely", "haunting", "angry",
               "heartbreak", "eerie", "night", "rain", "tense", "epic")
MAJOR_WORDS = ("happy", "upbeat", "bright", "sunny", "joy", "major", "summer", "uplifting",
               "cheerful", "playful", "hopeful", "party")
SLOW_WORDS = ("chill", "slow", "relax", "calm", "sleep", "mellow", "gentle", "soft", "lullaby")
FAST_WORDS = ("fast", "energetic", "hype", "driving", "intense", "upbeat", "party", "dance")

ENERGY = {"intro": 0.45, "verse": 0.65, "pre-chorus": 0.75, "chorus": 1.0,
          "bridge": 0.55, "solo": 0.9, "outro": 0.4}

VOWEL_FORMANTS = {
    "a": ((730, 1.0), (1090, 0.5), (2440, 0.25)),
    "e": ((530, 1.0), (1840, 0.45), (2480, 0.25)),
    "i": ((300, 1.0), (2290, 0.4), (3010, 0.2)),
    "o": ((570, 1.0), (840, 0.6), (2410, 0.15)),
    "u": ((320, 1.0), (870, 0.45), (2240, 0.1)),
}


def _stable_hash(text: str) -> int:
    return zlib.crc32(text.encode("utf-8"))


def parse_key(text: str | None) -> tuple[int, str] | None:
    """'C major' -> (0, 'major'); 'Am' / 'A minor' -> (9, 'minor')."""
    if not text:
        return None
    t = text.strip().lower().replace("♯", "#").replace("♭", "b")
    if not t:
        return None
    root = t[:2] if t[:2] in NOTE_NAMES else t[:1]
    if root not in NOTE_NAMES:
        return None
    rest = t[len(root):].strip()
    mode = "minor" if (rest.startswith("m") and not rest.startswith("maj")) or "min" in rest else "major"
    return NOTE_NAMES[root], mode


def midi_to_hz(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


@dataclass
class Plan:
    """Everything decided before rendering. Stored with the song so extend/remix stay coherent."""

    seed: int
    style: str
    bpm: int
    root: int
    mode: str
    progression: list[int]
    sections: list[dict] = field(default_factory=list)   # {kind, label, bars, lines}
    drums: bool = True
    bass: bool = True
    vocals: bool = True
    adventurous: float = 0.5

    def to_meta(self) -> dict:
        return {
            "engine": "sketch", "seed": self.seed, "style": self.style, "bpm": self.bpm,
            "key": f"{NAMES[self.root]} {self.mode}", "root": self.root, "mode": self.mode,
            "progression": self.progression, "drums": self.drums, "bass": self.bass,
            "vocals": self.vocals, "adventurous": self.adventurous,
            "sections": [{k: s[k] for k in ("kind", "label", "bars")} for s in self.sections],
        }


def choose_style(req: SongRequest) -> Style:
    text = " ".join([req.style_text(), req.prompt]).lower()
    best: Style | None = None
    best_pos = 10 ** 9
    for key, style in STYLES.items():
        pos = text.find(key)
        if pos >= 0 and pos < best_pos:   # the first style named wins
            best, best_pos = style, pos
    return best or STYLES["pop"]


def make_plan(req: SongRequest, seed: int) -> Plan:
    style = choose_style(req)
    text = " ".join([req.style_text(), req.prompt]).lower()
    rng = np.random.default_rng([seed, 1])
    exclude = " ".join(req.exclude).lower()

    key = parse_key(req.key)
    if key:
        root, mode = key
    else:
        mode = style.mode
        if any(w in text for w in MINOR_WORDS):
            mode = "minor"
        elif any(w in text for w in MAJOR_WORDS):
            mode = "major"
        root = int(rng.choice([0, 2, 4, 5, 7, 9, 10]))

    if req.bpm:
        bpm = int(np.clip(req.bpm, 40, 220))
    else:
        lo, hi = style.bpm
        if any(w in text for w in SLOW_WORDS):
            hi = lo + (hi - lo) // 3
        elif any(w in text for w in FAST_WORDS):
            lo = hi - (hi - lo) // 3
        bpm = int(rng.integers(lo, hi + 1))

    progression = list(PROGRESSIONS[mode][int(rng.integers(len(PROGRESSIONS[mode])))])

    vocals = bool(req.lyrics.strip()) and not req.instrumental and "vocal" not in exclude
    plan = Plan(seed=seed, style=style.name, bpm=bpm, root=root, mode=mode,
                progression=progression,
                drums=style.drums != "none" and "drum" not in exclude,
                bass="bass" not in exclude, vocals=vocals,
                adventurous=float(np.clip(req.adventurous, 0.0, 1.0)))
    plan.sections = build_sections(req, bpm, vocals)
    return plan


def build_sections(req: SongRequest, bpm: int, vocals: bool) -> list[dict]:
    bar_sec = 240.0 / bpm
    target = max(4, int(round(min(max(req.duration, 10.0), 600.0) / bar_sec)))
    out: list[dict] = []
    if vocals:
        parsed = parse_lyrics(req.lyrics)
        if not parsed or parsed[0].kind != "intro":
            out.append({"kind": "intro", "label": "Intro", "bars": 4, "lines": []})
        for s in parsed:
            bars = max(4, 2 * len(s.lines)) if s.lines else (4 if s.kind in ("intro", "outro") else 8)
            out.append({"kind": s.kind, "label": s.label, "bars": bars, "lines": s.lines})
        if out[-1]["kind"] != "outro":
            out.append({"kind": "outro", "label": "Outro", "bars": 4, "lines": []})
        # Lyrics set the length; pad with an instrumental chorus if the request is longer.
        used = sum(s["bars"] for s in out)
        if target - used >= 8:
            out.insert(-1, {"kind": "solo", "label": "Instrumental", "bars": min(16, (target - used) // 4 * 4), "lines": []})
        return out

    pattern = [("intro", 4), ("verse", 8), ("chorus", 8), ("verse", 8), ("chorus", 8),
               ("bridge", 4), ("solo", 8), ("chorus", 8)]
    used = 4  # outro
    i = 0
    while used < target:
        kind, bars = pattern[i] if i < len(pattern) else pattern[1 + (i - 1) % (len(pattern) - 1)]
        bars = min(bars, target - used)
        if bars < 2:
            break
        out.append({"kind": kind, "label": kind.title(), "bars": bars, "lines": []})
        used += bars
        i += 1
    out.append({"kind": "outro", "label": "Outro", "bars": 4, "lines": []})
    return out


# ---------------------------------------------------------------- synthesis


def _env(n: int, attack: float, release: float, decay: float | None = None) -> np.ndarray:
    t = np.arange(n, dtype=np.float32) / SR
    env = np.ones(n, dtype=np.float32)
    a = min(n, max(1, int(attack * SR)))
    env[:a] = np.linspace(0, 1, a, dtype=np.float32)
    if decay:
        env *= np.exp(-t / decay).astype(np.float32)
    r = min(n, max(1, int(release * SR)))
    env[-r:] *= np.linspace(1, 0, r, dtype=np.float32)
    return env


def harmonic_tone(freq: float, dur: float, harmonics: int, rolloff: float = 1.0,
                  odd_only: bool = False, attack: float = 0.01, release: float = 0.08,
                  decay: float | None = None, detune: float = 0.0) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    sig = np.zeros(n, dtype=np.float32)
    for f in ([freq] if not detune else [freq * (1 - detune), freq * (1 + detune)]):
        for k in range(1, harmonics + 1):
            if odd_only and k % 2 == 0:
                continue
            if f * k > SR * 0.45:
                break
            sig += np.sin(2 * np.pi * f * k * t + k).astype(np.float32) / (k ** rolloff)
    return sig * _env(n, attack, release, decay) / (2.0 if detune else 1.0)


def kick(energy: float) -> np.ndarray:
    n = int(0.38 * SR)
    t = np.arange(n) / SR
    f = 45 + 85 * np.exp(-t / 0.045)
    phase = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(phase) * np.exp(-t / 0.13) * (0.8 + 0.2 * energy)).astype(np.float32)


def snare(rng: np.random.Generator, energy: float) -> np.ndarray:
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    noise = noise - np.convolve(noise, np.ones(6) / 6, mode="same")   # brighten
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.04)
    return ((0.55 * noise * np.exp(-t / 0.06) + 0.5 * body) * (0.6 + 0.4 * energy)).astype(np.float32)


def hat(rng: np.random.Generator, open_: bool = False) -> np.ndarray:
    n = int((0.25 if open_ else 0.05) * SR)
    t = np.arange(n) / SR
    noise = np.diff(rng.standard_normal(n + 1))
    return (0.22 * noise * np.exp(-t / (0.08 if open_ else 0.015))).astype(np.float32)


def voice_note(freq: float, dur: float, vowel: str, rng: np.random.Generator) -> np.ndarray:
    """A sung vowel by additive synthesis: harmonics shaped by vowel formants, with vibrato."""
    n = max(1, int(dur * SR))
    t = np.arange(n) / SR
    vib_depth = 0.011 * np.clip((t - 0.15) / 0.2, 0, 1)
    f0 = freq * (1 + vib_depth * np.sin(2 * np.pi * 5.3 * t))
    # glide in from slightly below the note
    f0 *= 1 - 0.03 * np.exp(-t / 0.035)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    formants = VOWEL_FORMANTS.get(vowel, VOWEL_FORMANTS["a"])
    sig = np.zeros(n)
    for k in range(1, 40):
        fk = freq * k
        if fk > 4500:
            break
        amp = sum(g * np.exp(-((fk - F) / (90 + 0.06 * F)) ** 2) for F, g in formants) + 0.03 / k
        sig += amp * np.sin(k * phase)
    breath = rng.standard_normal(n) * 0.012
    sig = sig + breath
    return (sig * _env(n, 0.04, 0.09)).astype(np.float32)


def pan(mono: np.ndarray, position: float) -> np.ndarray:
    """position -1 (left) .. 1 (right), equal power."""
    angle = (position + 1) * np.pi / 4
    return np.stack([mono * np.cos(angle), mono * np.sin(angle)], axis=1).astype(np.float32)


def fft_convolve(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    n = len(x) + len(ir) - 1
    nfft = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(ir, nfft), nfft)[: len(x)]
    return y.astype(np.float32)


def reverb(stereo: np.ndarray, amount: float, seed: int) -> np.ndarray:
    if amount <= 0 or len(stereo) == 0:
        return stereo
    rng = np.random.default_rng([seed, 99])
    length = int(1.8 * SR)
    t = np.arange(length) / SR
    out = np.empty_like(stereo)
    for ch in range(2):
        ir = rng.standard_normal(length) * np.exp(-t / 0.45)
        ir[: int(0.012 * SR)] = 0  # pre-delay
        ir /= np.sqrt(np.sum(ir ** 2))
        out[:, ch] = fft_convolve(stereo[:, ch], ir.astype(np.float32))
    return stereo + amount * out


class Renderer:
    def __init__(self, plan: Plan, style: Style):
        self.plan = plan
        self.style = style
        self.beat = 60.0 / plan.bpm
        self.bar = 4 * self.beat
        total_bars = sum(s["bars"] for s in plan.sections)
        self.n = int((total_bars * self.bar + 2.5) * SR)
        self.stems = {name: np.zeros((self.n, 2), dtype=np.float32)
                      for name in ("drums", "bass", "chords", "lead", "vocals")}
        self.rng = np.random.default_rng([plan.seed, 2])
        self.motifs: dict[str, list[tuple[float, float, int]]] = {}

    # --- helpers
    def add(self, stem: str, start_s: float, sig: np.ndarray, gain: float = 1.0, position: float = 0.0):
        i = int(start_s * SR)
        if i >= self.n or len(sig) == 0:
            return
        j = min(self.n, i + len(sig))
        self.stems[stem][i:j] += gain * pan(sig[: j - i], position)

    def step_time(self, bar_start: float, step16: int) -> float:
        t = bar_start + step16 * self.beat / 4
        if self.style.swing and step16 % 2 == 1:
            t += self.style.swing * self.beat / 4
        return t

    def scale(self) -> list[int]:
        return MAJOR if self.plan.mode == "major" else MINOR

    def chord(self, degree: int) -> list[int]:
        """MIDI notes for the chord on `degree`, in octave 4."""
        sc = self.scale()
        notes = [sc[(degree + i) % 7] + 12 * ((degree + i) // 7) for i in (0, 2, 4)]
        if self.style.sevenths:
            notes.append(sc[(degree + 6) % 7] + 12 * ((degree + 6) // 7))
        return [60 + self.plan.root + n - (12 if self.plan.root > 6 else 0) for n in notes]

    # --- parts
    def render(self, progress: Progress | None = None) -> None:
        t = 0.0
        total = len(self.plan.sections)
        for idx, sec in enumerate(self.plan.sections):
            energy = ENERGY.get(sec["kind"], 0.7)
            for b in range(sec["bars"]):
                bar_index = b
                degree = self.plan.progression[bar_index % len(self.plan.progression)]
                bar_start = t + b * self.bar
                last_bar = b == sec["bars"] - 1
                fade = 1.0 - (b / max(1, sec["bars"])) * 0.7 if sec["kind"] == "outro" else 1.0
                if self.plan.drums and not (sec["kind"] == "intro" and b < 2):
                    self.drums(bar_start, energy * fade, last_bar and sec["kind"] not in ("outro",))
                if self.plan.bass and sec["kind"] != "intro":
                    self.bassline(bar_start, degree, energy * fade)
                self.chords(bar_start, degree, energy * fade)
                if not self.plan.vocals or sec["kind"] in ("intro", "solo", "outro"):
                    if sec["kind"] in ("chorus", "solo") or (sec["kind"] in ("intro", "outro") and b % 2 == 0):
                        self.lead(bar_start, degree, sec["kind"], b, energy * fade)
            if self.plan.vocals and sec["lines"]:
                self.sing(t, sec)
            t += sec["bars"] * self.bar
            if progress:
                progress(0.1 + 0.7 * (idx + 1) / total, f"Rendering {sec['label']}")

    def drums(self, bar_start: float, energy: float, fill: bool):
        kind = self.style.drums
        patterns = {
            "four": ([0, 4, 8, 12], [4, 12], list(range(0, 16, 2)), [2, 6, 10, 14]),
            "rock": ([0, 8, 10], [4, 12], list(range(0, 16, 2)), []),
            "hiphop": ([0, 7, 10], [4, 12], list(range(0, 16, 2)), []),
            "lofi": ([0, 10], [4, 12], list(range(0, 16, 2)), []),
            "half": ([0, 11], [8], list(range(16)), []),
            "shuffle": ([0, 10], [4, 12], [0, 3, 4, 7, 8, 11, 12, 15], []),
        }
        kicks, snares, hats, opens = patterns.get(kind, patterns["four"])
        if energy < 0.6:
            opens = []
            hats = hats[::2] if kind != "half" else hats
        for s in kicks:
            self.add("drums", self.step_time(bar_start, s), kick(energy), 0.9)
        for s in snares:
            if fill and s >= 12:
                continue
            self.add("drums", self.step_time(bar_start, s), snare(self.rng, energy), 0.55, 0.05)
        for s in hats:
            accent = 1.0 if s % 4 == 0 else 0.7
            self.add("drums", self.step_time(bar_start, s), hat(self.rng), 0.5 * accent * energy, 0.3)
        for s in opens:
            self.add("drums", self.step_time(bar_start, s), hat(self.rng, True), 0.35 * energy, 0.3)
        if fill and energy >= 0.55:
            for s in range(12, 16):
                self.add("drums", self.step_time(bar_start, s), snare(self.rng, energy), 0.35 + 0.08 * (s - 12), -0.1)

    def bassline(self, bar_start: float, degree: int, energy: float):
        root = self.chord(degree)[0] - 24
        hz = midi_to_hz(root)
        kind = self.style.bass
        if kind == "long":
            steps = [(0, 16)]
        elif kind == "pulse":
            steps = [(0, 4), (4, 4), (8, 4), (12, 4)]
        elif kind == "syncop":
            steps = [(0, 3), (3, 3), (6, 4), (10, 2), (12, 4)]
        elif kind == "walk":
            sc = self.scale()
            walk = [0, 2, 4, 5] if self.rng.random() < 0.5 else [0, 4, 2, 6]
            for i, w in enumerate(walk):
                note = root + sc[(degree + w) % 7] - sc[degree % 7]
                tone = harmonic_tone(midi_to_hz(note), self.beat * 0.95, 5, 1.6, attack=0.005, release=0.05, decay=0.5)
                self.add("bass", self.step_time(bar_start, i * 4), tone, 0.55 * (0.7 + 0.3 * energy))
            return
        else:  # root8
            steps = [(s, 2) for s in range(0, 16, 2)]
        for s, length in steps:
            dur = length * self.beat / 4 * 0.92
            tone = harmonic_tone(hz, dur, 6, 1.5, attack=0.004, release=0.04, decay=0.6)
            self.add("bass", self.step_time(bar_start, s), tone, 0.55 * (0.7 + 0.3 * energy))

    def chords(self, bar_start: float, degree: int, energy: float):
        notes = self.chord(degree)
        kind = self.style.pad
        g = 0.16 * (0.6 + 0.4 * energy)
        if kind == "arp" or kind == "pluck":
            order = notes + [notes[1] + 12] if kind == "arp" else [notes[0], notes[2], notes[1], notes[2]] * 2
            for i in range(8):
                n = order[i % len(order)]
                tone = harmonic_tone(midi_to_hz(n), self.beat * 0.9, 6, 1.8, attack=0.003, release=0.1, decay=0.35)
                self.add("chords", self.step_time(bar_start, i * 2), tone, g * 1.4, -0.35 + 0.1 * (i % 3))
            return
        for i, n in enumerate(notes):
            hz = midi_to_hz(n)
            if kind == "rhodes":
                tone = harmonic_tone(hz, self.bar * 0.95, 4, 2.5, attack=0.005, release=0.2, decay=1.2)
            elif kind == "strings":
                tone = harmonic_tone(hz, self.bar * 1.02, 8, 1.2, attack=0.35, release=0.4, detune=0.004)
            elif kind == "power":
                if i > 1:
                    continue
                tone = np.tanh(3 * harmonic_tone(hz / 2, self.bar * 0.48, 8, 1.0, attack=0.005, release=0.05))
                self.add("chords", bar_start, tone, g * 0.9, -0.5)
                self.add("chords", bar_start + self.bar / 2, tone, g * 0.9, 0.5)
                continue
            else:  # soft
                tone = harmonic_tone(hz, self.bar * 1.0, 6, 1.4, attack=0.08, release=0.3, detune=0.003)
            self.add("chords", bar_start, tone, g, -0.4 + 0.4 * i)

    def motif(self, kind: str, rng: np.random.Generator) -> list[tuple[float, float, int]]:
        """A 2-bar rhythm/contour (start beat, length beats, scale step) reused per section kind."""
        if kind not in self.motifs:
            adv = self.plan.adventurous
            notes = []
            beat = 0.0
            step = 0
            while beat < 8:
                length = float(rng.choice([0.5, 1.0, 1.0, 1.5, 2.0] if adv < 0.6 else [0.25, 0.5, 0.5, 0.75, 1.0, 1.5]))
                length = min(length, 8 - beat)
                jump = int(rng.integers(-1 - int(3 * adv), 2 + int(3 * adv)))
                step = int(np.clip(step + jump, -2, 9))
                notes.append((beat, length, step))
                beat += length
            self.motifs[kind] = notes
        return self.motifs[kind]

    def lead(self, bar_start: float, degree: int, kind: str, bar_in_section: int, energy: float):
        if bar_in_section % 2:
            return  # each motif spans two bars
        rng = np.random.default_rng([self.plan.seed, 3, _stable_hash(kind)])
        sc = self.scale()
        base = 72 + self.plan.root - (12 if self.plan.root > 6 else 0)
        for beat, length, step in self.motif(kind, rng):
            note = base + sc[(degree + step) % 7] + 12 * ((degree + step) // 7) - sc[degree % 7]
            dur = length * self.beat * 0.9
            hz = midi_to_hz(note)
            lead = self.style.lead
            if lead == "square":
                tone = harmonic_tone(hz, dur, 12, 1.0, odd_only=True, attack=0.01, release=0.06)
            elif lead == "bell":
                tone = harmonic_tone(hz, dur, 5, 2.2, attack=0.002, release=0.2, decay=0.4)
            elif lead == "sine":
                tone = harmonic_tone(hz, dur, 3, 2.5, attack=0.02, release=0.1)
            else:
                tone = harmonic_tone(hz, dur, 10, 1.0, attack=0.01, release=0.08, detune=0.003)
            self.add("lead", bar_start + beat * self.beat, tone, 0.11 * (0.6 + 0.4 * energy), 0.2)

    def sing(self, section_start: float, sec: dict):
        """Sing each lyric line over two bars, one note per syllable."""
        rng = np.random.default_rng([self.plan.seed, 4, _stable_hash(sec["kind"])])
        sc = self.scale()
        base = 64 + self.plan.root - (12 if self.plan.root > 6 else 0)
        if sec["kind"] == "chorus":
            base += 3
        contour = [int(x) for x in rng.integers(-2, 3, size=64)]
        for li, line in enumerate(sec["lines"]):
            sylls = syllables(line)[:16]
            if not sylls:
                continue
            line_start = section_start + li * 2 * self.bar
            degree = self.plan.progression[(li * 2) % len(self.plan.progression)]
            # Fit syllables into ~7 beats, leaving a breath at the end of the line.
            slot = min(1.0, 7.0 / len(sylls))
            step = 2 + (li % 2)  # alternate lines start on different notes
            for si, vowel in enumerate(sylls):
                step = int(np.clip(step + contour[(si + li * 3) % len(contour)], 0, 7))
                if si == len(sylls) - 1:
                    step = 0 if li % 2 else 2   # resolve phrase ends to chord tones
                note = base + sc[(degree + step) % 7] + 12 * ((degree + step) // 7) - sc[degree % 7]
                length = slot * (1.8 if si == len(sylls) - 1 else 1.0)
                tone = voice_note(midi_to_hz(note), length * self.beat * 0.95, vowel, rng)
                self.add("vocals", line_start + si * slot * self.beat, tone, 0.09, 0.0)

    def mix(self) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        style = self.style
        stems = dict(self.stems)
        stems["chords"] = reverb(stems["chords"], style.reverb, self.plan.seed)
        stems["vocals"] = reverb(stems["vocals"], style.reverb * 0.8 + 0.1, self.plan.seed + 1)
        stems["lead"] = reverb(stems["lead"], style.reverb * 0.6, self.plan.seed + 2)
        mix = sum(stems.values())
        mix = np.tanh(1.3 * mix) / np.tanh(1.3)
        fade_in = int(0.03 * SR)
        mix[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
        tail = int(2.0 * SR)
        mix[-tail:] *= np.linspace(1, 0, tail)[:, None] ** 2
        scale = 0.89 / max(1e-9, float(np.abs(mix).max()))
        mix = (mix * scale).astype(np.float32)
        stems = {k: (v * scale).astype(np.float32) for k, v in stems.items() if np.abs(v).max() > 1e-6}
        return mix, stems


class SketchEngine(Engine):
    name = "sketch"
    label = "Sketch (offline)"

    def render_plan(self, plan: Plan, progress: Progress | None = None) -> Take:
        style = STYLES.get(plan.style, STYLES["pop"])
        r = Renderer(plan, style)
        r.render(progress)
        mix, stems = r.mix()
        return Take(audio=mix, sr=SR, seed=plan.seed, meta=plan.to_meta(), stems=stems)

    def generate(self, req: SongRequest, progress: Progress) -> list[Take]:
        base_seed = req.seed if req.seed is not None else int(np.random.default_rng().integers(1, 2 ** 31 - 1))
        takes = []
        n = max(1, min(int(req.takes), 4))
        for i in range(n):
            seed = int(base_seed) + i * 7919
            plan = make_plan(req, seed)
            sub = (lambda p, msg, i=i: progress((i + p) / n, f"Take {i + 1}: {msg}"))
            sub(0.05, "Arranging")
            takes.append(self.render_plan(plan, sub))
        return takes

    def extend(self, req: SongRequest, source: Path, source_meta: dict,
               seconds: float, progress: Progress) -> Take:
        if source_meta.get("engine") != "sketch":
            raise EngineError("The sketch engine can only extend songs it made. Use ACE-Step for this one.")
        original, sr = read_wav(source)
        cont_req = SongRequest.from_dict({**req.to_dict(), "duration": seconds})
        plan = make_plan(cont_req, int(source_meta["seed"]))
        # Keep the original's musical decisions.
        plan.bpm, plan.root, plan.mode = int(source_meta["bpm"]), int(source_meta["root"]), source_meta["mode"]
        plan.progression = list(source_meta["progression"])
        plan.sections = [s for s in build_sections(cont_req, plan.bpm, plan.vocals) if s["kind"] != "intro"]
        progress(0.1, "Writing the continuation")
        take = self.render_plan(plan, lambda p, m: progress(0.1 + 0.8 * p, m))
        # Drop the original's fade-out tail before joining.
        cut = max(0, len(original) - int(2.0 * sr))
        joined = crossfade_concat(original[:cut], take.audio, sr, 0.25)
        meta = dict(source_meta)
        meta["sections"] = list(source_meta.get("sections", [])) + take.meta["sections"]
        meta["extended_by"] = seconds
        return Take(audio=normalize(joined), sr=sr, seed=plan.seed, meta=meta, stems=None)

    def remix(self, req: SongRequest, source: Path, source_meta: dict,
              strength: float, progress: Progress) -> Take:
        if source_meta.get("engine") != "sketch":
            raise EngineError("The sketch engine can only remix songs it made. Use ACE-Step for uploads and other songs.")
        seed = int(source_meta["seed"])
        plan = make_plan(req, seed)
        if strength < 0.5:   # a light remix keeps the original's key, tempo and chords
            plan.bpm, plan.root, plan.mode = int(source_meta["bpm"]), int(source_meta["root"]), source_meta["mode"]
            plan.progression = list(source_meta["progression"])
        progress(0.05, "Re-arranging")
        return self.render_plan(plan, progress)
