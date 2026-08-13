"""Shot grammar: build prompts that produce photographs, not "AI images".

Everything here comes from the verified research brief. Three findings drive the
design, and the first is counterintuitive enough that vendors get it wrong:

1. **Quality adjectives destroy realism.** "8k", "ultra realistic",
   "hyperdetailed", "masterpiece", "professional" push a model toward its
   average of stock and CGI renders — the exact plastic look people mean when
   they say something looks AI-generated. Higgsfield's own quickstart docs
   recommend these terms; the banned table overrides them.

2. **Specification beats emphasis.** A model cannot act on "cinematic". It can
   act on a 35mm lens at f/2, a key light from camera-left, and a foreground
   element three feet from the lens. Say the setup a photographer would set up.

3. **Physical coherence.** One camera body, one lens, one dominant key light,
   one film stock. Mixing incompatible gear averages two training distributions
   and produces the mushy, uncanny result that reads as fake.

Foreground is called out separately because it is the cheapest realism win
available: a real photograph is taken from somewhere, with something between the
lens and the subject. Generated images tend to float in clean empty space.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Terms that make output look MORE synthetic. Stripped before every call, and
#: the raw-vs-cleaned diff is publishable teaching content in its own right.
BANNED_TERMS = {
    "8k": "", "4k": "", "ultra realistic": "", "ultra-realistic": "",
    "hyperrealistic": "", "hyper realistic": "", "photorealistic": "",
    "highly detailed": "", "hyperdetailed": "", "intricate details": "",
    "masterpiece": "", "best quality": "", "high quality": "", "professional": "",
    "award winning": "", "trending on artstation": "", "stunning": "",
    "beautiful": "", "perfect": "", "flawless": "", "cinematic lighting": "",
    "dramatic lighting": "", "epic": "", "breathtaking": "",
}

SHOT_SIZES = (
    "extreme close-up", "close-up", "medium close-up", "medium shot",
    "medium wide shot", "wide shot", "extreme wide shot",
)
ANGLES = (
    "low angle", "high angle", "eye level", "overhead", "dutch angle",
    "over-the-shoulder", "worm's eye",
)

#: Focal length carries most of the "look". Pairing is enforced because a 24mm
#: extreme close-up is a physical impossibility that produces mush.
LENS_FOR_SHOT = {
    "extreme close-up": ("85mm", "100mm macro"),
    "close-up": ("85mm", "50mm"),
    "medium close-up": ("50mm", "85mm"),
    "medium shot": ("35mm", "50mm"),
    "medium wide shot": ("35mm", "28mm"),
    "wide shot": ("24mm", "35mm"),
    "extreme wide shot": ("16mm", "24mm"),
}

#: Small physical wrongnesses are what separate a photograph from a render.
IMPERFECTIONS = (
    "slight motion blur on the moving hand",
    "a faint smudge on the glass",
    "dust visible in the light beam",
    "uneven crumbs on the table surface",
    "a thumbprint on the cup rim",
    "slightly crooked napkin",
)


class ShotError(ValueError):
    """A physically incoherent shot. Rejected rather than sent."""


@dataclass
class Shot:
    subject: str
    """Who or what, wearing what, doing what. Concrete nouns only."""
    action: str = ""
    environment: str = ""
    """Place plus two specific props. Comes AFTER subject: leading with the
    environment makes the model pull the camera back and shrink the subject."""
    foreground: str = ""
    """Something between lens and subject. The cheapest realism win there is."""
    shot_size: str = "medium close-up"
    angle: str = "eye level"
    lens: str = ""
    aperture: str = "f/2.0"
    light: str = "soft window light from camera-left"
    film: str = "Kodak Portra 400"
    imperfection: str = ""
    negative_space: str = ""
    aspect: str = "4:5"
    camera_move: str = ""
    """Video only. One move, not three."""
    beats: tuple[str, ...] = field(default=())
    """Video only. Two or three beats per five seconds, never more."""

    def validate(self) -> None:
        if self.shot_size not in SHOT_SIZES:
            raise ShotError(f"unknown shot size {self.shot_size!r}")
        if self.angle not in ANGLES:
            raise ShotError(f"unknown angle {self.angle!r}")
        allowed = LENS_FOR_SHOT[self.shot_size]
        if self.lens and self.lens not in allowed:
            raise ShotError(
                f"{self.lens} does not pair with a {self.shot_size} — "
                f"use one of {', '.join(allowed)}. Mixing incompatible gear "
                f"averages two training distributions and produces mush."
            )
        if not self.foreground:
            raise ShotError(
                "no foreground element. A real photograph is taken from "
                "somewhere, with something between lens and subject; without it "
                "the frame floats in empty space and reads as generated."
            )
        if len(self.beats) > 3:
            raise ShotError("more than 3 beats; a 5s clip holds 2-3 at most")

    @property
    def resolved_lens(self) -> str:
        return self.lens or LENS_FOR_SHOT[self.shot_size][0]

    def image_prompt(self) -> str:
        """Ordered subject → action → environment → foreground → light → camera."""
        self.validate()
        parts = [
            f"{self.shot_size} of {self.subject}",
            self.action,
            f"in {self.environment}" if self.environment else "",
            f"{self.foreground} in the immediate foreground, softly out of focus",
            self.light,
            f"shot from a {self.angle} on a {self.resolved_lens} lens at {self.aperture}",
            f"shot on {self.film}, visible grain",
            self.imperfection or IMPERFECTIONS[0],
            f"{self.negative_space} left clear for text" if self.negative_space else "",
            self.aspect,
        ]
        return clean(", ".join(p for p in parts if p))

    def video_prompt(self) -> str:
        """Camera move first, then what changes. Never re-describe a still frame."""
        self.validate()
        if not self.camera_move:
            raise ShotError("video needs exactly one camera move")
        beats = " | ".join(self.beats) if self.beats else self.action
        parts = [
            f"{self.camera_move} on {self.subject}",
            f"in {self.environment}" if self.environment else "",
            f"{self.foreground} passing through the foreground",
            beats,
            self.light,
            f"{self.angle}, {self.resolved_lens} lens at {self.aperture}",
            "real-time motion at natural speed, no slow motion",
            f"shot on {self.film}, visible grain",
        ]
        return clean(", ".join(p for p in parts if p))


def clean(prompt: str) -> str:
    """Strip terms that make output look synthetic. Returns the cleaned prompt."""
    out = prompt
    for term in sorted(BANNED_TERMS, key=len, reverse=True):
        out = re.sub(rf"\b{re.escape(term)}\b,?\s*", "", out, flags=re.IGNORECASE)
    return re.sub(r"\s*,\s*,+", ", ", out).strip(" ,")


def diff(raw: str) -> tuple[str, list[str]]:
    """Return the cleaned prompt and which banned terms were removed.

    The removals are teaching content: here is what you wrote, here is what a
    photographer would have written.
    """
    removed = [t for t in BANNED_TERMS if re.search(rf"\b{re.escape(t)}\b", raw, re.I)]
    return clean(raw), removed
