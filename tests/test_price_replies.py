"""The reply path when a member asks what something costs.

Founder direction, 2026-08-15: research it rather than deflect, and raise it
only when the answer is genuinely unclear.
"""

from __future__ import annotations

import pytest

from app.agents.replier import Draft, build_prompt
from app.agents.research import Finding, _gate
from app.runtime import NEEDS_YOU, Runtime, _cache_key
from app.spine.store import Store
from tests.test_runtime import BOT, FakeAPI, SETTINGS, auto_forward


@pytest.fixture
def rt(tmp_path):
    r = Runtime(settings=SETTINGS, store=Store(tmp_path / "p.db"),
                api=FakeAPI(), bot_id=BOT)
    r.handle_update(auto_forward())
    return r


def comment(text, message_id=90):
    import time
    return {"update_id": message_id, "message": {
        "message_id": message_id,
        "chat": {"id": SETTINGS.discussion_group_id, "type": "supergroup"},
        "from": {"id": 555, "is_bot": False, "first_name": "Dilnoza"},
        "message_thread_id": 3, "text": text, "date": int(time.time()),
    }}


def quotable() -> Finding:
    f = Finding(found=True, subject="Kling AI", plan="Pro", amount="25.99",
                currency="USD", period="oyiga",
                source_url="https://klingai.com/membership", source_is_official=True,
                as_of="2026-08-15", confidence="high", searched=True)
    f.blockers = _gate(f)
    return f


def unquotable() -> Finding:
    f = Finding(found=False, subject="Kling AI", sources_conflict=True,
                source_url="https://tracker.example/kling", confidence="low",
                searched=True,
                summary_for_founders="Manbalar ziddiyatli: 6.99 va 10-15.")
    f.blockers = _gate(f)
    return f


def test_a_price_question_is_researched_before_being_escalated(rt, monkeypatch):
    calls = []
    monkeypatch.setattr("app.runtime.draft_reply", lambda ctx, **k: (
        calls.append(k.get("extra_facts")),
        Draft(action="escalate", draft="", grounded_on=[], reasoning="no price",
              needs_from_founders="Kling narxi?") if len(calls) == 1 else
        Draft(action="reply", draft="Pro 25.99 USD oyiga", grounded_on=["research.Kling AI"],
              reasoning="researched"))[1])
    monkeypatch.setattr("app.runtime.lookup_price", lambda q, **k: quotable())

    rt.handle_update(comment("Kling qancha turadi?"))

    replies = [s for s in rt.api.sent if s["chat_id"] == SETTINGS.discussion_group_id]
    assert replies, "the member got no answer at all"
    assert "25.99" in replies[0]["text"]
    assert calls[1], "the redraft was not given the researched fact"
    assert "klingai.com" in calls[1][0], "the fact must carry its source"


def test_an_unclear_price_is_raised_to_the_founders_with_the_evidence(rt, monkeypatch):
    monkeypatch.setattr("app.runtime.draft_reply", lambda ctx, **k: Draft(
        action="escalate", draft="", grounded_on=[], reasoning="no price",
        needs_from_founders="Kling narxi?"))
    monkeypatch.setattr("app.runtime.lookup_price", lambda q, **k: unquotable())

    rt.handle_update(comment("Kling narxi qancha?"))

    to_admin = [s for s in rt.api.sent if s["chat_id"] == SETTINGS.admin_chat_id]
    assert to_admin, "nothing reached the founders"
    card = to_admin[0]["text"]
    assert NEEDS_YOU.split(">")[1].split("<")[0] in card, "not marked as needing attention"
    assert "qidirib" in card, "the research was not attached"
    assert "ziddiyatli" in card, "the founders were not told what conflicted"
    assert not [s for s in rt.api.sent if s["chat_id"] == SETTINGS.discussion_group_id]


def test_a_non_price_question_never_pays_for_a_search(rt, monkeypatch):
    monkeypatch.setattr("app.runtime.draft_reply", lambda ctx, **k: Draft(
        action="escalate", draft="", grounded_on=[], reasoning="unknown",
        needs_from_founders="qanday qilingan?"))
    monkeypatch.setattr("app.runtime.lookup_price", lambda q, **k: pytest.fail(
        "searched for a question that was not about price"))

    rt.handle_update(comment("Bu qanday qilingan?"))


def test_the_same_price_question_is_not_researched_twice(rt, monkeypatch):
    searches = []
    monkeypatch.setattr("app.runtime.draft_reply", lambda ctx, **k: Draft(
        action="escalate", draft="", grounded_on=[], reasoning="no price",
        needs_from_founders="Kling narxi?"))
    monkeypatch.setattr("app.runtime.lookup_price",
                        lambda q, **k: (searches.append(q), unquotable())[1])

    rt.handle_update(comment("Kling narxi qancha?", message_id=91))
    rt.handle_update(comment("Kling narxi qancha?", message_id=92))

    assert len(searches) == 1, "a repeated question was paid for twice"
    assert rt.store.get_runtime(f"price:{_cache_key('Kling narxi?')}")


def stub_ctx():
    from types import SimpleNamespace

    from app.text.script import Script

    return SimpleNamespace(
        script=Script.LATIN, history=[], post_text="post", post_id=606,
        target=SimpleNamespace(message_id=1, author="Dilnoza", text="narxi qancha?"),
    )


def test_a_researched_fact_reaches_the_prompt_as_quotable_grounding():
    """The prompt must say these may be quoted, or the grounding gate refuses
    them exactly as it refuses model memory — and the member gets nothing."""
    prompt = build_prompt(stub_ctx(), extra_facts=[quotable().as_fact()])

    assert "VERIFIED JUST NOW" in prompt
    assert "25.99" in prompt and "klingai.com" in prompt
    assert "MUST include the source" in prompt
    assert "convert currencies" in prompt, "extrapolation must be forbidden"
    assert "yearly price from a monthly one" in prompt


def test_without_research_the_prompt_carries_no_such_licence():
    prompt = build_prompt(stub_ctx())
    assert "VERIFIED JUST NOW" not in prompt


def test_previous_drafts_actually_reach_the_prompt():
    """They were accepted by draft_reply and dropped before build_prompt, so the
    anti-repetition guard added after two near-identical replies shipped live
    was inert."""
    prompt = build_prompt(stub_ctx(), previous_drafts=["Kling 3.0 da koʻring"])
    assert "ALREADY SENT IN THIS THREAD" in prompt
    assert "Kling 3.0 da koʻring" in prompt
