"""Cards rendered on the server, for posts no photograph fits."""

from __future__ import annotations

import struct

import pytest

from app.media import cards

pytest.importorskip("PIL")


def png_size(data: bytes) -> tuple[int, int]:
    """Read width and height straight out of the IHDR chunk."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_the_resolved_font_actually_draws_the_okina():
    """The whole reason this check exists: a font without U+02BB renders oʻ as a
    blank or a box, silently, and nobody notices until it is in a headline.
    Arial Narrow has no okina; Arial Nova does. Never assume — measure."""
    ok, detail = cards.check_font()
    assert ok, detail


def test_a_font_without_the_okina_is_refused_rather_than_drawing_boxes(monkeypatch):
    monkeypatch.setattr(cards, "FONT_CANDIDATES",
                        {"regular": ("/nonexistent.ttf",), "bold": ("/nonexistent.ttf",)})
    ok, detail = cards.check_font()
    assert not ok
    assert "U+02BB" in detail or "renders" in detail

    with pytest.raises(cards.FontError):
        cards.resolve_font("bold")


def test_a_card_is_a_16_9_png():
    png = cards.render("challenge", "Bugun bitta kadr oling.", headline="Bitta kadr")
    width, height = png_size(png)
    assert (width, height) == cards.SIZE
    assert round(width / height, 2) == 1.78, "channel visuals are 16:9"


def test_long_uzbek_text_shrinks_to_fit_rather_than_being_cut():
    """A truncated sentence in a headline is worse than smaller type, and the
    caption underneath carries the full post anyway."""
    long_body = ("Mijoz sizdan chiroyli rasm emas, sotadigan rasm soʻraydi. "
                 "Shuning uchun brifni birinchi oʻqiysiz. ") * 8
    png = cards.render("why_content", long_body, headline="Brif — bu ish")
    assert png_size(png) == cards.SIZE


def test_the_cta_line_is_left_to_the_caption():
    """Two asks in one post means neither happens, so the card drops the CTA the
    caption is already making."""
    body, headline = cards.card_copy(
        "Bitta kadr oling\nDeraza yorugʻida suratga oling.\nNatijangizni tashlang 👇")
    assert headline == "Bitta kadr oling"
    assert "👇" not in body


def test_card_copy_survives_a_single_line_post():
    body, headline = cards.card_copy("Faqat bitta qator.")
    assert headline == "Faqat bitta qator."
    assert body == ""


def test_every_scheduled_post_kind_has_a_card_style():
    """A kind with no style falls back to a generic eyebrow. Every kind the
    weekly grid can schedule now has its own."""
    from app.runtime import WEEKLY_PLAN

    missing = sorted({k for k in WEEKLY_PLAN.values() if k not in cards.STYLES})
    assert not missing, f"kinds with no card style: {missing}"


def test_a_card_renders_for_the_kinds_that_have_no_photograph():
    """challenge, recognition and behind_scenes have no tagged asset in the
    library, which is why they were publishing as bare text."""
    from app.media.library import load

    lib = load()
    for kind in ("challenge", "recognition", "behind_scenes"):
        assert not [a for a in lib if kind in a.good_for], f"{kind} now has an asset"
        assert png_size(cards.render(kind, "Matn", headline="Sarlavha")) == cards.SIZE
