"""Branded cards rendered on the VPS, for posts no photograph fits.

Founder direction is that every post ships with a visual, but three post kinds —
`challenge`, `recognition`, `behind_scenes` — have no photograph that genuinely
illustrates them, so they were publishing as bare text. A generated photo would
be worse: a stock-feeling image that has nothing to do with the caption reads as
filler and costs more credibility than no image at all.

A typeset card is the honest answer. It carries the words themselves, on brand,
and it is *supposed* to look designed rather than photographed.

Two properties matter more than the drawing:

**It runs on the server.** Every other visual in this project is generated on the
founders' laptop through the Higgsfield MCP, which is bound to an interactive
session and cannot run from the VPS. That makes those posts dependent on a batch
session having happened. This has no such dependency and costs nothing per image.

**It is identical every time.** Same geometry, same colour, same type. A reader
recognises the channel in a feed before reading a word, which a differently
generated image can never do.

The okina is the sharp edge here. Uzbek `oʻ` and `gʻ` use U+02BB, and plenty of
fonts have no glyph for it — Arial Narrow does not, while Arial Nova does. A
missing glyph renders as a blank or a box, silently, in a headline. So the font
is not assumed: `check_font()` proves the glyph exists and preflight refuses to
boot without it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

log = logging.getLogger("cards")

#: The Uzbek okina — MODIFIER LETTER TURNED COMMA, not an apostrophe.
OKINA = "\u02BB"
#: The tutuq belgisi, used everywhere the okina is not.
TUTUQ = "\u02BC"
#: Private-use codepoint no real font defines. Rendering any character to the
#: same bitmap as this one proves the font is drawing .notdef.
_NOTDEF = "\uE000"

#: Brand tokens, shared verbatim with the warm-up bot so both look like one studio.
CORAL = "#DC6D55"
INK = "#242323"
PAPER = "#FCF8F6"
MUTED = "#8A8180"

#: 16:9, matching every other visual the channel publishes.
SIZE = (1920, 1080)
MARGIN = 130

#: Regular and bold, most specific first. The container gets DejaVu from apt;
#: the Windows entries are for running this on the founders' laptop. Arial
#: Narrow is deliberately absent — it has no okina.
FONT_CANDIDATES: dict[str, tuple[str, ...]] = {
    "bold": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/ArialNova-Bold.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
    ),
    "regular": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/ArialNova.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ),
}


class FontError(RuntimeError):
    """No available font can draw Uzbek. Rendering is refused rather than
    producing a headline full of empty boxes."""


def _renders(path: str, size: int = 48) -> bool:
    """True when this font draws the okina and the tutuq as real glyphs."""
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.truetype(path, size)
    except OSError:
        return False

    def bitmap(ch: str) -> bytes:
        img = Image.new("L", (size + 24, size + 32), 0)
        ImageDraw.Draw(img).text((6, 6), ch, font=font, fill=255)
        return img.tobytes()

    notdef, blank = bitmap(_NOTDEF), bitmap(" ")
    return all(bitmap(c) not in (notdef, blank) for c in (OKINA, TUTUQ))


def resolve_font(weight: str = "regular") -> str:
    for path in FONT_CANDIDATES[weight]:
        if Path(path).is_file() and _renders(path):
            return path
    raise FontError(
        f"no {weight} font on this system renders {OKINA!r} and {TUTUQ!r}. "
        f"Install fonts-dejavu-core, or add a font that covers U+02BB to "
        f"FONT_CANDIDATES. A missing glyph is invisible until it is in a headline."
    )


def check_font() -> tuple[bool, str]:
    """Preflight probe. Returns (ok, detail)."""
    try:
        regular, bold = resolve_font("regular"), resolve_font("bold")
    except FontError as exc:
        return False, str(exc)
    return True, f"{Path(bold).name} / {Path(regular).name} render {OKINA} and {TUTUQ}"


@dataclass(frozen=True)
class CardStyle:
    """What each post kind's card says about itself."""

    label: str
    accent: str = CORAL


#: Uzbek eyebrow per kind. Deliberately plain — the card's job is to carry the
#: words, not to announce itself.
STYLES: dict[str, CardStyle] = {
    "challenge": CardStyle("BUGUNGI VAZIFA"),
    "recognition": CardStyle("JAMOAMIZDAN"),
    "behind_scenes": CardStyle("ORQA TOMONDA"),
    "recap": CardStyle("HAFTA YAKUNI"),
    "mission": CardStyle("NEGA BUNI QILAMIZ"),
    "poll": CardStyle("SOʻROVNOMA"),
    "technique": CardStyle("USUL"),
    "news": CardStyle("AI YANGILIKLARI"),
    "commercial_craft": CardStyle("BIZNES UCHUN"),
    "why_content": CardStyle("NEGA SHUNDAY"),
}
DEFAULT_STYLE = CardStyle("AI CREATORS")

FOOTER_LEFT = "Shahlo Alikhanova & Akmalidin Alimov · Shvetsiyadan AI ekspertlar"
FOOTER_RIGHT = "AI CREATORS"


def _wrap(draw, text: str, font, width: int) -> list[str]:
    """Greedy wrap on real measured widths, preserving the author's own breaks."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        current = ""
        for word in paragraph.split():
            trial = f"{current} {word}".strip()
            if draw.textlength(trial, font=font) <= width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


#: Telegram accepts a 10MB photo upload, against 5MB for one it fetches from a
#: URL itself. Staying under 9MB leaves room for the multipart envelope.
MAX_UPLOAD_BYTES = 9_000_000


def fetch_image(url: str, *, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    """Download an asset, shrinking it only if Telegram would refuse the size.

    Re-encoded as JPEG on the way down: these are 2K PNGs of photographic
    content, where PNG costs several megabytes for no visible benefit.
    """
    from io import BytesIO

    from PIL import Image

    from app.net import http_client

    raw = http_client(timeout=120.0).get(url).content
    if len(raw) <= max_bytes:
        return raw

    image = Image.open(BytesIO(raw)).convert("RGB")
    for quality in (88, 80, 70, 60):
        out = BytesIO()
        image.save(out, format="JPEG", quality=quality, optimize=True)
        if out.tell() <= max_bytes:
            log.info("re-encoded %s bytes to %s at q%s", len(raw), out.tell(), quality)
            return out.getvalue()

    image.thumbnail((2048, 2048))
    out = BytesIO()
    image.save(out, format="JPEG", quality=80, optimize=True)
    log.warning("downscaled a very large asset to %s bytes", out.tell())
    return out.getvalue()


def card_copy(text: str) -> tuple[str, str]:
    """Split a post into (body, headline) for a card.

    The first line is the hook and becomes the headline. The trailing CTA is
    dropped: the caption underneath already carries it, and asking twice in one
    post is the two-asks-means-neither-happens failure the format rules forbid.
    """
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    if not lines:
        return "", ""
    headline, rest = lines[0], lines[1:]
    if rest and ("👇" in rest[-1] or rest[-1].endswith("?")):
        rest = rest[:-1]
    return "\n".join(rest), headline


def render_post(kind: str, text: str, *, credit: str = "") -> bytes:
    """Render a whole post as a card. The one entry point callers should use."""
    body, headline = card_copy(text)
    return render(kind, body, headline=headline, credit=credit)


def render(kind: str, body: str, *, headline: str = "", credit: str = "") -> bytes:
    """Draw a card and return PNG bytes.

    ``body`` is the post's own words. The card shrinks its type until the text
    fits rather than truncating it — a cut-off sentence in a headline is worse
    than slightly smaller type, and the caption still carries the full post.
    """
    from PIL import Image, ImageDraw, ImageFont

    style = STYLES.get(kind, DEFAULT_STYLE)
    bold_path, regular_path = resolve_font("bold"), resolve_font("regular")

    image = Image.new("RGB", SIZE, PAPER)
    draw = ImageDraw.Draw(image)

    # A coral rule down the left edge: the cheapest mark that makes a card
    # recognisable at thumbnail size.
    draw.rectangle([0, 0, 14, SIZE[1]], fill=style.accent)

    eyebrow = ImageFont.truetype(bold_path, 34)
    draw.text((MARGIN, 96), style.label, font=eyebrow, fill=style.accent)

    top = 190
    inner = SIZE[0] - MARGIN * 2

    if headline:
        hf = ImageFont.truetype(bold_path, 84)
        for line in _wrap(draw, headline, hf, inner)[:2]:
            draw.text((MARGIN, top), line, font=hf, fill=INK)
            top += 100
        top += 24

    # Fit the body by measurement, never by guessing a character count.
    floor = SIZE[1] - 190
    for pt in (64, 58, 52, 46, 42, 38, 34):
        bf = ImageFont.truetype(regular_path, pt)
        lines = _wrap(draw, body, bf, inner)
        step = int(pt * 1.42)
        if top + len(lines) * step <= floor:
            break
    for line in lines:
        draw.text((MARGIN, top), line, font=bf, fill=INK)
        top += step

    if credit:
        cf = ImageFont.truetype(bold_path, 44)
        draw.text((MARGIN, min(top + 30, floor - 50)), credit, font=cf, fill=style.accent)

    rule_y = SIZE[1] - 132
    draw.line([MARGIN, rule_y, SIZE[0] - MARGIN, rule_y], fill=MUTED, width=2)

    ff = ImageFont.truetype(regular_path, 28)
    draw.text((MARGIN, rule_y + 34), FOOTER_LEFT, font=ff, fill=MUTED)
    fr = ImageFont.truetype(bold_path, 28)
    draw.text((SIZE[0] - MARGIN - draw.textlength(FOOTER_RIGHT, font=fr), rule_y + 34),
              FOOTER_RIGHT, font=fr, fill=INK)

    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
