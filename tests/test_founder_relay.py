"""Relaying a founder's answer back into the member's comment thread.

The escalation used to be one-way. The bot asked, the founders answered in the
admin chat, and the answer stopped there — nothing was listening. The member,
who asked in public and waited, got nothing.
"""

from __future__ import annotations

import json

import pytest

from app.agents.replier import AI_DISCLOSURE, Draft
from app.runtime import Runtime
from app.spine.store import Store
from tests.test_runtime import ADMIN, BOT, FakeAPI, GROUP, SETTINGS, auto_forward


@pytest.fixture
def rt(tmp_path):
    r = Runtime(settings=SETTINGS, store=Store(tmp_path / "r.db"), api=FakeAPI(), bot_id=BOT)
    r.handle_update(auto_forward())
    return r


def member_asks(rt, text="Bu qanday qilingan?", message_id=90):
    import time
    rt.handle_update({"update_id": message_id, "message": {
        "message_id": message_id, "chat": {"id": GROUP, "type": "supergroup"},
        "from": {"id": 555, "is_bot": False, "first_name": "Dilnoza"},
        "message_thread_id": 3, "text": text, "date": int(time.time()),
    }})


def admin_replies(card_message_id, text, user_id=ADMIN):
    return {"update_id": 700, "message": {
        "message_id": 701, "chat": {"id": ADMIN, "type": "private"},
        "from": {"id": user_id, "is_bot": False}, "text": text,
        "reply_to_message": {"message_id": card_message_id},
    }}


def escalate(rt, monkeypatch):
    monkeypatch.setattr("app.runtime.draft_reply", lambda ctx, **k: Draft(
        action="escalate", draft="", grounded_on=[], reasoning="unknown",
        needs_from_founders="Qaysi model bilan qilingan?"))
    member_asks(rt)
    card = [s for s in rt.api.sent if s["chat_id"] == ADMIN][-1]
    return card


def test_answering_the_card_delivers_the_answer_to_the_member(rt, monkeypatch):
    card = escalate(rt, monkeypatch)
    rt.api.sent.clear()

    rt.handle_update(admin_replies(card["message_id"], "Seedance 2.5 bilan, bitta rasmdan."))

    to_group = [s for s in rt.api.sent if s["chat_id"] == GROUP]
    assert to_group, "the founder's answer never reached the member"
    assert to_group[0]["text"] == "Seedance 2.5 bilan, bitta rasmdan."
    assert to_group[0]["reply_to_message_id"] == 90, "must reply to the member's own message"


def test_the_answer_is_not_labelled_as_ai(rt, monkeypatch):
    """The disclosure exists so a reader does not mistake machine text for human
    text. This IS human text — labelling it would be the false statement."""
    card = escalate(rt, monkeypatch)
    rt.api.sent.clear()

    rt.handle_update(admin_replies(card["message_id"], "Bitta rasmdan, koʻp sahnali."))

    to_group = [s for s in rt.api.sent if s["chat_id"] == GROUP]
    assert AI_DISCLOSURE not in to_group[0]["text"]


def test_the_answer_is_sent_verbatim_not_rewritten(rt, monkeypatch):
    card = escalate(rt, monkeypatch)
    rt.api.sent.clear()
    exact = "Yoʻq, 3 ta referens rasm ishlatilgan. Kadrlar bitta promptda."

    rt.handle_update(admin_replies(card["message_id"], exact))

    to_group = [s for s in rt.api.sent if s["chat_id"] == GROUP]
    assert to_group[0]["text"] == exact


def test_the_founder_gets_a_confirmation(rt, monkeypatch):
    card = escalate(rt, monkeypatch)
    rt.api.sent.clear()
    rt.handle_update(admin_replies(card["message_id"], "javob"))
    assert any("yuborildi" in s["text"] for s in rt.api.sent if s["chat_id"] == ADMIN)


def test_the_same_card_cannot_be_answered_twice(rt, monkeypatch):
    """Otherwise a second thought typed under the same card posts a duplicate
    into a public thread."""
    card = escalate(rt, monkeypatch)
    rt.handle_update(admin_replies(card["message_id"], "birinchi javob"))
    rt.api.sent.clear()
    rt.handle_update(admin_replies(card["message_id"], "ikkinchi javob"))
    assert not [s for s in rt.api.sent if s["chat_id"] == GROUP]


def test_a_reply_to_something_else_is_not_relayed(rt):
    rt.handle_update(admin_replies(999999, "tasodifiy xabar"))
    assert not [s for s in rt.api.sent if s["chat_id"] == GROUP]


def test_a_stranger_cannot_answer_on_the_founders_behalf(rt, monkeypatch):
    card = escalate(rt, monkeypatch)
    rt.api.sent.clear()
    rt.handle_update(admin_replies(card["message_id"], "men ham bilaman", user_id=4242))
    assert not [s for s in rt.api.sent if s["chat_id"] == GROUP]


def test_the_card_tells_the_founder_how_to_answer(rt, monkeypatch):
    """A feature nobody knows about is not a feature."""
    card = escalate(rt, monkeypatch)
    assert "javob yozing" in card["text"]


def test_commands_still_work_when_not_replying_to_a_card(rt):
    rt.handle_update({"update_id": 800, "message": {
        "message_id": 801, "chat": {"id": ADMIN, "type": "private"},
        "from": {"id": ADMIN, "is_bot": False}, "text": "/holat"}})
    assert any("Keyingi slot" in s["text"] for s in rt.api.sent)


def test_the_link_records_which_member_asked(rt, monkeypatch):
    card = escalate(rt, monkeypatch)
    link = json.loads(rt.store.get_runtime(f"esc:{card['message_id']}"))
    assert link["member_message_id"] == 90
    assert link["author"] == "Dilnoza"
