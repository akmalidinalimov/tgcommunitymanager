"""Normalize Uzbek apostrophes at render time.

Writers type whatever the keyboard gives them — nobody reaches for U+02BB on a
phone. Published text must still carry the correct glyphs, because a post spelled
``Yo'nalish`` is invisible to anyone searching for ``Yoʻnalish``.

The rule is unambiguous: between two letters, an Uzbek apostrophe is only ever
one of two characters. After ``o`` or ``g`` it is the okina ``ʻ`` (U+02BB);
everywhere else it is the tutuq belgisi ``ʼ`` (U+02BC).

This is a rendering step, not a writing constraint. Never block a draft for
typing a straight quote.
"""

from __future__ import annotations

import re

OKINA = "ʻ"  # ʻ — modifier letter turned comma, used in oʻ and gʻ
TUTUQ = "ʼ"  # ʼ — modifier letter apostrophe, used everywhere else

#: Every character a keyboard, phone or word processor might produce here.
APOSTROPHES = "'‘’´`" + OKINA + TUTUQ

_BETWEEN_LETTERS = re.compile(rf"(?<=[^\W\d_])[{re.escape(APOSTROPHES)}](?=[^\W\d_])", re.UNICODE)


def normalize_apostrophes(text: str) -> str:
    """Return ``text`` with Uzbek apostrophes rendered as the correct glyphs.

    Only apostrophes *between two letters* are touched. A quotation mark or a
    trailing apostrophe is left exactly as written, since those are not Uzbek
    orthography and guessing at them would corrupt real punctuation.
    """

    def replace(match: re.Match[str]) -> str:
        preceding = match.string[match.start() - 1]
        return OKINA if preceding.lower() in ("o", "g") else TUTUQ

    return _BETWEEN_LETTERS.sub(replace, text)


def has_wrong_apostrophes(text: str) -> bool:
    """True if rendering would change the text — i.e. it is not publish-ready."""
    return normalize_apostrophes(text) != text
