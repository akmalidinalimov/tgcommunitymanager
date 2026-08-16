"""Everything the founders do from the admin chat.

Two jobs the Mini App will eventually own, built here because the bot chat is
where the founders already are: editing a post by typing the correction, and
being told when the community is waiting.
"""

from __future__ import annotations

import pytest

from app.agents.replier import Draft
from app.runtime import Runtime
from app.spine.states import Content, State
from app.spine.store import Store
from tests.test_runtime import ADMIN, BOT, FakeAPI, GROUP, SETTINGS, auto_forward


@pytest.fixture
def rt(tmp_path):
    r = Runtime(settings=SETTINGS, store=Store(tmp_path / "a.db"), api=FakeAPI(), bot_id=BOT)
    r.handle_update(auto_forward())
    return r


def reply_in_admin_chat(card_message_id, text, user_id=ADMIN):
    return {"update_id": 600, "message": {
        "message_id": 601, "chat": {"id": ADMIN, "type": "private"},
        "from": {"id": user_id, "is_bot": False}, "text": text,
        "reply_to_message": {"message_id": card_message_id},
    }}


def card_for(rt, slot_key="2026-08-16_21:00", text="Dastlabki matn"):
    from app.spine.scheduler import slot_from_key

    c = Content(slot_key=slot_key, kind="technique", text=text)
    c.attach_media("card")
    c.submit_for_approval()
    rt.store.save_content(c)
    rt._send_for_approval(c, slot_from_key(slot_key))
    return [s for s in rt.api.sent if s["chat_id"] == ADMIN][-1]


# --- inline edit ------------------------------------------------------------


def test_replying_to_a_card_replaces_the_post_text(rt):
    """Revise costs an LLM round-trip and returns something Shahlo did not
    write. When one line is wrong, typing it is faster and exact."""
    card = card_for(rt)
    rt.api.sent.clear()

    rt.handle_update(reply_in_admin_chat(card["message_id"], "Men yozgan yangi matn"))

    content = rt.store.get_content("2026-08-16_21:00")
    assert content.text == "Men yozgan yangi matn"
    assert content.state is State.PENDING_APPROVAL, "an edit still needs approving"


def test_an_edit_is_sent_back_for_approval(rt):
    card = card_for(rt)
    rt.api.sent.clear()
    rt.handle_update(reply_in_admin_chat(card["message_id"], "Yangi matn"))
    assert any(s.get("reply_markup") for s in rt.api.sent), "no fresh card to approve"


def test_a_hand_typed_post_goes_through_the_same_lint(rt):
    """A typed post publishes to 3,326 people exactly like a generated one, and
    can break the caption cap just as easily."""
    card = card_for(rt)
    rt.api.sent.clear()

    rt.handle_update(reply_in_admin_chat(card["message_id"], "x" * 2000))

    assert rt.store.get_content("2026-08-16_21:00").text == "Dastlabki matn"
    assert any("qabul qilinmadi" in s["text"] for s in rt.api.sent)


def test_an_already_approved_post_cannot_be_edited_by_reply(rt):
    """Approved content is immutable — otherwise what a human said yes to is not
    what ships."""
    card = card_for(rt)
    content = rt.store.get_content("2026-08-16_21:00")
    content.approve(ADMIN, (ADMIN,), at=__import__("datetime").datetime.now(
        __import__("zoneinfo").ZoneInfo("Asia/Tashkent")))
    content.schedule()
    rt.store.save_content(content)
    rt.api.sent.clear()

    rt.handle_update(reply_in_admin_chat(card["message_id"], "kech boʻldi"))

    assert rt.store.get_content("2026-08-16_21:00").text == "Dastlabki matn"
    assert any("tahrirlab boʻlmaydi" in s["text"] for s in rt.api.sent)


def test_a_stranger_cannot_edit_a_post(rt):
    card = card_for(rt)
    rt.handle_update(reply_in_admin_chat(card["message_id"], "buzaman", user_id=4242))
    assert rt.store.get_content("2026-08-16_21:00").text == "Dastlabki matn"


# --- the waiting-questions nudge -------------------------------------------


def escalate(rt, monkeypatch, message_id=90):
    import time
    monkeypatch.setattr("app.runtime.draft_reply", lambda ctx, **k: Draft(
        action="escalate", draft="", grounded_on=[], reasoning="unknown",
        needs_from_founders="savol"))
    rt.handle_update({"update_id": message_id, "message": {
        "message_id": message_id, "chat": {"id": GROUP, "type": "supergroup"},
        "from": {"id": 555, "is_bot": False, "first_name": "Dilnoza"},
        "message_thread_id": 3, "text": "savol?", "date": int(time.time()),
    }})


def test_the_founders_are_told_when_questions_are_waiting(rt, monkeypatch):
    escalate(rt, monkeypatch, 90)
    escalate(rt, monkeypatch, 91)
    rt.api.sent.clear()

    assert rt.ping_if_questions_are_waiting() is True
    assert any("2 ta savol" in s["text"] for s in rt.api.sent)


def test_the_nudge_is_rate_limited(rt, monkeypatch):
    """A reminder every fifteen minutes is noise, and noise is how a real alert
    gets ignored."""
    escalate(rt, monkeypatch)
    assert rt.ping_if_questions_are_waiting() is True
    rt.api.sent.clear()
    assert rt.ping_if_questions_are_waiting() is False
    assert rt.api.sent == []


def test_no_nudge_when_nothing_is_waiting(rt):
    assert rt.ping_if_questions_are_waiting() is False


def test_answering_clears_the_question_from_the_count(rt, monkeypatch):
    escalate(rt, monkeypatch)
    card = [s for s in rt.api.sent if s["chat_id"] == ADMIN][-1]
    assert rt.unanswered_questions() == 1

    rt.handle_update(reply_in_admin_chat(card["message_id"], "javobim"))

    assert rt.unanswered_questions() == 0


def test_status_reports_the_waiting_count(rt, monkeypatch):
    escalate(rt, monkeypatch)
    rt.api.sent.clear()
    rt.handle_update({"update_id": 800, "message": {
        "message_id": 801, "chat": {"id": ADMIN, "type": "private"},
        "from": {"id": ADMIN, "is_bot": False}, "text": "/holat"}})
    assert any("Javobsiz savollar" in s["text"] for s in rt.api.sent)
