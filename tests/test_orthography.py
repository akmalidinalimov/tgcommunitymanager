from __future__ import annotations

import pytest

from app.text.orthography import OKINA, TUTUQ, has_wrong_apostrophes, normalize_apostrophes


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("to'g'ri", f"to{OKINA}g{OKINA}ri"),
        ("bo'ladi", f"bo{OKINA}ladi"),
        ("so'z", f"so{OKINA}z"),
        ("ko'rganlar", f"ko{OKINA}rganlar"),
        ("O'zbekiston", f"O{OKINA}zbekiston"),
        ("sun'iy", f"sun{TUTUQ}iy"),
        ("ma'noli", f"ma{TUTUQ}noli"),
        ("ta'sirli", f"ta{TUTUQ}sirli"),
        # Latin abbreviations take the tutuq, since the preceding letter is not o/g.
        ("ChatGPT'dan", f"ChatGPT{TUTUQ}dan"),
    ],
)
def test_glyph_is_chosen_by_the_preceding_letter(raw, expected):
    assert normalize_apostrophes(raw) == expected


def test_curly_and_typographic_apostrophes_are_normalized_too():
    """Phones and word processors substitute these silently."""
    for variant in ("bo’ladi", "bo‘ladi", "bo´ladi"):
        assert normalize_apostrophes(variant) == f"bo{OKINA}ladi"


def test_already_correct_text_is_untouched():
    text = f"to{OKINA}g{OKINA}ri sun{TUTUQ}iy"
    assert normalize_apostrophes(text) == text
    assert not has_wrong_apostrophes(text)


def test_quotation_marks_are_not_uzbek_orthography_and_are_left_alone():
    """Guessing at real punctuation would corrupt it."""
    assert normalize_apostrophes("'salom'") == "'salom'"
    assert normalize_apostrophes("bolalar' ") == "bolalar' "


def test_digits_and_symbols_do_not_trigger_replacement():
    assert normalize_apostrophes("5'000") == "5'000"


def test_detects_text_that_is_not_publish_ready():
    assert has_wrong_apostrophes("bo'ladi")
    assert not has_wrong_apostrophes("Kim sinab ko" + OKINA + "rdi?")


def test_full_post_normalizes_end_to_end():
    raw = "Kim sinab ko'rdi? Chiqmagan bo'lsa ham yozing."
    out = normalize_apostrophes(raw)
    assert "'" not in out
    assert f"ko{OKINA}rdi" in out and f"bo{OKINA}lsa" in out
