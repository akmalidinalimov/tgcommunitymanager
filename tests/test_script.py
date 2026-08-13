"""Script detection, tested against the real comments from post 606."""

from __future__ import annotations

import pytest

from app.text.script import Script, detect_script, reply_script


@pytest.mark.parametrize(
    "text, expected",
    [
        # Verbatim from the live thread.
        ("Qaysi AIdan foydalaniladi videolaga?", Script.LATIN),
        ("Omni flash (flow) ham qiberoliydimi shunaqa qib?", Script.LATIN),
        ("Ha yaxshi kling o'zi avvaldan zo'r edi. Obunasi qimmatde uni", Script.LATIN),
        ("Қандай қилганизнм хам кўрсатиб беринг", Script.CYRILLIC),
        ("мен омнида қилиб кўрсам у асл видеодан ўзгартириб қўйябти", Script.CYRILLIC),
        ("линкини ташлаб бера оласизми", Script.CYRILLIC),
        ("Рахмат", Script.CYRILLIC),
    ],
)
def test_real_comments_are_classified_correctly(text, expected):
    assert detect_script(text) == expected


def test_cyrillic_sentence_carrying_a_latin_tool_name_stays_cyrillic():
    """Uzbek writers drop Latin product names into Cyrillic sentences constantly.
    A few Latin characters must not flip the whole reply into the wrong script."""
    assert detect_script("Kling 3.0 да қилиб кўрдим, зўр чиқди") == Script.CYRILLIC


def test_latin_sentence_with_a_cyrillic_word_stays_latin():
    assert detect_script("Men кино uslubida qilmoqchiman") == Script.LATIN


@pytest.mark.parametrize("text", ["", None, "🔥🔥🔥", "2026", "https://bfl.ai", "!!!"])
def test_textless_messages_are_unknown(text):
    assert detect_script(text) == Script.UNKNOWN


def test_video_with_no_caption_inherits_the_member_s_earlier_script():
    """Four members posted videos with no caption on post 606. They still get
    answered in the script they were writing in."""
    assert reply_script(None, ["Қандай қилганизнм хам кўрсатиб беринг"]) == Script.CYRILLIC
    assert reply_script("🔥", ["Omni flash ham qiberoliydimi?"]) == Script.LATIN


def test_reply_script_prefers_the_message_over_thread_history():
    assert reply_script("Рахмат", ["Qaysi AIdan foydalaniladi?"]) == Script.CYRILLIC


def test_reply_script_defaults_to_latin_with_nothing_to_go_on():
    assert reply_script(None, []) == Script.LATIN
    assert reply_script("🔥", ["👍", "🙏"]) == Script.LATIN
