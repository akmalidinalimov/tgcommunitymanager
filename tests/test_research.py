"""Looking a price up, and knowing when not to answer.

The gate is the feature. Every case below is a way the first live probe went
wrong when asked what Kling costs.
"""

from __future__ import annotations

import pytest

from app.agents.research import Finding, _gate, is_price_question


def clean(**over) -> Finding:
    """A finding that clears every gate, so each test can spoil exactly one."""
    base = dict(
        found=True, subject="Kling AI", plan="Pro", amount="25.99", currency="USD",
        period="oyiga", source_url="https://klingai.com/membership",
        source_is_official=True, sources_conflict=False,
        has_promotional_variants=False, as_of="2026-08-15", confidence="high",
    )
    base.update(over)
    f = Finding(**base)
    f.blockers = _gate(f)
    return f


def test_a_clean_official_price_is_quotable():
    assert clean().quotable


def test_a_third_party_tracker_is_not_good_enough():
    """No official vendor page appeared in the first real probe — only trackers,
    which go stale and disagree."""
    f = clean(source_is_official=False, source_url="https://some-ai-blog.com/kling")
    assert not f.quotable
    assert "vendor's own page" in " ".join(f.blockers)


def test_conflicting_sources_are_never_reconciled_by_guessing():
    """The probe found Standard at $6.99 in one place and $10-15 in another. The
    bot must not pick one."""
    f = clean(sources_conflict=True)
    assert not f.quotable
    assert "disagree" in " ".join(f.blockers)


def test_medium_confidence_is_not_confidence():
    assert not clean(confidence="medium").quotable
    assert not clean(confidence="low").quotable


def test_no_price_found_is_not_an_answer():
    assert not clean(found=False).quotable


def test_a_price_without_a_source_is_refused():
    assert not clean(source_url="").quotable


def test_promotional_variants_do_not_block_but_must_be_disclosed():
    """Kling shows list, first-month promo and renewal on one card. That is not a
    reason to stay silent — it is a reason to say which number they will pay."""
    f = clean(has_promotional_variants=True,
              caveat="Birinchi oy 6.99, uzaytirishda 8.80")
    assert f.quotable, "a disclosed variant should not silence the bot"
    assert "uzaytirishda" in f.as_fact()


def test_the_quotable_fact_carries_its_source_and_date():
    """A price without a date is a price that will be wrong later."""
    fact = clean().as_fact()
    assert "25.99" in fact and "USD" in fact
    assert "2026-08-15" in fact
    assert "klingai.com" in fact


@pytest.mark.parametrize("text", [
    "Kling qancha turadi?",
    "narxi qancha",
    "obuna narxi bormi",
    "Сколько стоит подписка?",
    "қанча пул",
    "is it free?",
    "how much does Seedance cost",
])
def test_price_questions_are_recognised_in_both_scripts_and_in_russian(text):
    assert is_price_question(text)


@pytest.mark.parametrize("text", [
    "Bu qanday qilingan?",
    "Zoʻr chiqibdi",
    "Qaysi model bilan qildingiz?",
])
def test_ordinary_questions_do_not_trigger_a_paid_search(text):
    assert not is_price_question(text)


def test_a_lookup_failure_degrades_to_an_escalation_not_an_exception():
    """A question the bot cannot research must reach a founder, never break the
    reply loop."""
    from app.agents.research import lookup_price

    f = lookup_price("narxi qancha?", api_key="")
    assert not f.quotable
    assert f.blockers
