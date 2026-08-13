"""Mechanical Uzbek checks, including against the founders' own published text."""

from __future__ import annotations

import pytest

from app.text.lint import (
    Severity,
    blockers,
    lint,
    load_banned_table,
    passes,
    unsupported_numbers,
)

BANNED = {"amalga oshirish": "qilish", "foydalanuvchi": "siz", "mazkur": "bu",
          "hisoblanadi": "-", "shuningdek": "yana", "natijasida": "shuning uchun"}


def rules(text):
    return {i.rule for i in lint(text, banned=BANNED)}


# --- the banned table is read from the voice guide, not duplicated ----------


def test_banned_table_parses_out_of_the_voice_guide():
    table = load_banned_table()
    assert table, "voice guide table did not parse — the linter would enforce nothing"
    for term in ("amalga oshirish", "foydalanuvchi", "mazkur"):
        assert term in table
    assert table["amalga oshirish"] == "qilish"


def test_placeholder_rows_are_not_treated_as_terms():
    """The table uses – for 'just delete it'. Banning a dash would flag everything."""
    table = load_banned_table()
    assert "–" not in table and "—" not in table and "-" not in table


# --- verb forms -------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "Video tayyorlash amalga oshirilmoqda",
    "AI bozorda tez o'smoqda",
])
def test_moqda_is_a_blocker(text):
    assert "bookish -moqda form" in rules(text)
    assert not passes(text, banned=BANNED)


def test_moqda_gets_a_usable_replacement():
    issue = next(i for i in lint("ishlamoqda", banned=BANNED) if "moqda" in i.rule)
    assert issue.fix == "ishlayapti"


def test_yapti_is_fine():
    assert "bookish -moqda form" not in rules("AI bozorda tez o'syapti")


# --- register ---------------------------------------------------------------


def test_sen_is_a_blocker():
    assert "addresses the reader as sen" in rules("Sen buni qila olasan")


def test_words_containing_sen_are_not_false_positives():
    """'sensor' and 'sen'gа-like forms must not trip the check."""
    for safe in ("Bu sensor yaxshi", "Tushunasiz", "Sizga kerak"):
        assert "addresses the reader as sen" not in rules(safe)


# --- officialese ------------------------------------------------------------


@pytest.mark.parametrize("term", ["amalga oshirish", "foydalanuvchi", "mazkur", "hisoblanadi"])
def test_every_banned_construction_is_caught(term):
    assert "banned construction" in rules(f"Bu {term} kerak")


@pytest.mark.parametrize("word", ["xullas", "demak", "qarang", "biroq", "aytmoqchi"])
def test_never_attested_words_are_caught(word):
    assert "word this account never uses" in rules(f"{word.capitalize()}, bu muhim")


def test_never_attested_check_respects_word_boundaries():
    """'demak' must not fire inside a longer word."""
    assert "word this account never uses" not in rules("Bu demakchi emas")


# --- translated scaffolding -------------------------------------------------


def test_section_announcing_scaffolding_is_caught():
    """This exact pattern failed the first blind voice test."""
    text = "Ilgari qanday edi: hammasi qo'lda edi.\n\nNimasi muhim? Endi tez."
    assert "translated section scaffolding" in rules(text)


# --- the founders' own writing should pass ----------------------------------


def test_real_published_post_passes():
    """From the live channel. If the linter rejects the founders' own voice, the
    linter is wrong, not the voice."""
    text = (
        "Koʻpchilik ChatGPT'dan foydalanadi, lekin bitta katta xatoga yoʻl qoʻyadi.\n\n"
        "ChatGPT koʻpincha sizning fikringizni tasdiqlaydi.\n\n"
        "Shu muammoni hal qiladigan promptni vaʼda qilgandim."
    )
    assert passes(text, banned=BANNED), [str(i) for i in lint(text, banned=BANNED)]


def test_the_post_we_actually_published_passes():
    text = (
        "Kecha videoning promptini kanalga tashlagandim.\n\n"
        "Kim sinab koʻrdi? 👀\n\n"
        "Chiqmagan boʻlsa ham yozing. Koʻpincha muammo promptda emas, bitta sozlamada boʻladi."
    )
    assert passes(text, banned=BANNED), [str(i) for i in lint(text, banned=BANNED)]


# --- apostrophes ------------------------------------------------------------


def test_unnormalized_apostrophes_are_polish_not_a_blocker():
    """Writers type straight quotes; the renderer fixes them. Blocking a draft
    for this would reject correct copy."""
    issues = lint("bo'ladi", banned=BANNED)
    assert issues and all(i.severity is Severity.POLISH for i in issues)
    assert passes("bo'ladi", banned=BANNED)


# --- the claims ledger ------------------------------------------------------


def test_numbers_absent_from_the_ledger_are_flagged():
    """The strongest guardrail in the system, precisely because it is a schema
    check rather than a model's opinion."""
    text = "5000 ta o'quvchi, oyiga 1500$ ishlashadi"
    assert unsupported_numbers(text, ledger=set()) != []


def test_ledger_backed_numbers_pass():
    text = "720p sifatida ancha arzon"
    assert unsupported_numbers(text, ledger={"720"}) == []


def test_clean_text_has_no_numbers_to_justify():
    assert unsupported_numbers("Kim sinab koʻrdi?", ledger=set()) == []


def test_blockers_filters_out_polish():
    issues = lint("bo'ladi va amalga oshirish", banned=BANNED)
    assert len(blockers(issues)) == 1
    assert len(issues) == 2


# --- claim-shaped numbers vs technical numbers ------------------------------


@pytest.mark.parametrize("text", [
    "5000 ta o'quvchi bor",
    "oyiga 1500$ ishlashadi",
    "$1500 topdi",
    "daromad 3 barobar oshdi",
    "1 200 000 so'm",
    "konversiya 40% oshdi",
])
def test_claim_shaped_numbers_are_flagged(text):
    assert unsupported_numbers(text, ledger=set()), text


@pytest.mark.parametrize("text", [
    "10 soniyalik video chiqaring",
    "Kling 3.0 da sinab ko'ring",
    "720p sifatida ancha arzon",
    "3 ta rasm tayyorlang",
    "2026-yil",
])
def test_technical_numbers_are_not_claims(text):
    """A duration, a resolution or a version describes the work rather than
    asserting an outcome. Flagging these blocks good posts forever, and a
    guardrail that fires on everything gets switched off."""
    assert unsupported_numbers(text, ledger=set()) == [], text


def test_a_claim_backed_by_the_ledger_passes():
    assert unsupported_numbers("5000 ta o'quvchi", ledger={"5000"}) == []
