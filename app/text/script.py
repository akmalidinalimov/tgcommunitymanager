"""Detect which script a member wrote in, so replies can mirror it.

Measured on the first live post: of 16 text comments, 11 were Uzbek Latin and 5
were Uzbek Cyrillic — one member wrote exclusively in Cyrillic. Answering her in
Latin reads as not listening, so the script is a first-class property of a reply.
"""

from __future__ import annotations

import re
from enum import Enum

CYRILLIC_RANGES = ((0x0400, 0x04FF), (0x0500, 0x052F))
LATIN_RANGES = ((0x0041, 0x005A), (0x0061, 0x007A))

#: URLs, @handles and bare domains are all Latin characters but say nothing about
#: the language someone writes in. A Cyrillic writer posting only a link must not
#: be flipped to a Latin reply — this happened in the real thread, where a member
#: answered a Cyrillic question with nothing but "http://Bfl.ai".
_NOT_LANGUAGE = re.compile(
    r"(https?://\S+|www\.\S+|\b\S+\.(?:ai|com|net|org|io|uz|ru|app|dev)\b|@\w+)",
    re.IGNORECASE,
)


def _strip_non_language(text: str) -> str:
    return _NOT_LANGUAGE.sub(" ", text)


class Script(str, Enum):
    LATIN = "latin"
    CYRILLIC = "cyrillic"
    UNKNOWN = "unknown"
    """Emoji-only, digits-only, or a bare link. Inherit the thread's script."""


def _count(text: str, ranges) -> int:
    return sum(
        1 for ch in text if any(lo <= ord(ch) <= hi for lo, hi in ranges)
    )


def detect_script(text: str | None) -> Script:
    """Return the dominant script of ``text``.

    Mixed text is common — Uzbek writers drop Latin tool names into Cyrillic
    sentences (``омнида``, ``ChatGPT``). The majority wins, because that is what
    the person is actually writing in.
    """
    if not text:
        return Script.UNKNOWN

    cleaned = _strip_non_language(text)
    cyrillic = _count(cleaned, CYRILLIC_RANGES)
    latin = _count(cleaned, LATIN_RANGES)

    if cyrillic == 0 and latin == 0:
        return Script.UNKNOWN
    if cyrillic > latin:
        return Script.CYRILLIC
    if latin > cyrillic:
        return Script.LATIN
    # A genuine tie is vanishingly rare; prefer Cyrillic because a Cyrillic
    # writer receiving Latin is the more jarring failure of the two.
    return Script.CYRILLIC


def reply_script(message_text: str | None, thread_texts: list[str] | None = None) -> Script:
    """Pick the script to reply in.

    Falls back to the member's other messages in the thread when this one carries
    no letters — someone posting a video with no caption still deserves an answer
    in their own script.
    """
    direct = detect_script(message_text)
    if direct is not Script.UNKNOWN:
        return direct

    for text in reversed(thread_texts or []):
        found = detect_script(text)
        if found is not Script.UNKNOWN:
            return found
    return Script.LATIN
