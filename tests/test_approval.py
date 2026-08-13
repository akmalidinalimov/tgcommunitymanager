"""Approval buttons: what a press is allowed to do, and who is allowed to press."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.spine.approval import (
    APPROVE,
    REJECT,
    REVISE,
    callback_data,
    card,
    expire_overdue,
    handle_callback,
    keyboard,
    parse_callback,
)
from app.spine.scheduler import Slot
from app.spine.states import Content, State

TASHKENT = ZoneInfo("Asia/Tashkent")
APPROVERS = (6542876935,)
SLOT = Slot(datetime(2026, 8, 14, 10, 0, tzinfo=TASHKENT))
SLOT_KEY = SLOT.key


def pending(text="Kecha promptni tashlagandim."):
    c = Content(slot_key=SLOT_KEY, kind="technique", text=text)
    c.submit_for_approval()
    return c


def press(action, content, user_id=APPROVERS[0], at=None):
    return handle_callback(
        action, content, user_id=user_id, approver_ids=APPROVERS,
        at=at or datetime(2026, 8, 13, 20, 0, tzinfo=TASHKENT),
    )


# --- callback_data ----------------------------------------------------------


def test_callback_data_fits_telegrams_64_byte_cap():
    data = callback_data(APPROVE, SLOT_KEY)
    assert len(data.encode()) <= 64
    assert parse_callback(data) == (APPROVE, SLOT_KEY)


def test_every_button_fits():
    for button in keyboard(SLOT_KEY)["inline_keyboard"][0]:
        assert len(button["callback_data"].encode()) <= 64


# --- authorisation ----------------------------------------------------------


def test_a_stranger_cannot_approve():
    """callback_data is guessable, so anyone who can reach the bot can send one.
    Authorisation is checked server-side, never inferred from the button."""
    c = pending()
    outcome = press(APPROVE, c, user_id=111222333)
    assert not outcome.handled
    assert c.state is State.PENDING_APPROVAL
    assert c.approved_by is None


def test_the_approver_can_approve_and_it_schedules():
    c = pending()
    outcome = press(APPROVE, c)
    assert outcome.handled
    assert c.state is State.SCHEDULED
    assert c.approved_by == APPROVERS[0]


# --- double taps and stale cards --------------------------------------------


def test_a_second_tap_is_refused_rather_than_re_applied():
    c = pending()
    press(APPROVE, c)
    outcome = press(APPROVE, c)
    assert not outcome.handled
    assert "scheduled" in outcome.toast
    assert c.state is State.SCHEDULED


def test_a_button_for_content_that_no_longer_exists_is_handled_gracefully():
    outcome = press(APPROVE, None)
    assert not outcome.handled
    assert "eskirgan" in outcome.toast


def test_rejecting_after_approving_does_not_unpublish():
    c = pending()
    press(APPROVE, c)
    outcome = press(REJECT, c)
    assert not outcome.handled
    assert c.state is State.SCHEDULED


# --- the other buttons ------------------------------------------------------


def test_reject_terminates_the_content():
    c = pending()
    assert press(REJECT, c).handled
    assert c.state is State.REJECTED


def test_revise_sends_it_back_to_drafting():
    c = pending()
    assert press(REVISE, c).handled
    assert c.state is State.DRAFTING
    assert c.revision_rounds == 1


def test_unknown_action_changes_nothing():
    c = pending()
    outcome = press("zz", c)
    assert not outcome.handled
    assert c.state is State.PENDING_APPROVAL


# --- deadline ---------------------------------------------------------------


def test_content_past_its_deadline_expires_instead_of_publishing():
    """The backup pool covers the slot. Nothing unapproved ever ships."""
    c = pending()
    expired = expire_overdue(
        [c], {SLOT_KEY: SLOT}, now=datetime(2026, 8, 13, 23, 0, tzinfo=TASHKENT)
    )
    assert expired == [c]
    assert c.state is State.EXPIRED


def test_content_still_inside_its_window_is_left_alone():
    c = pending()
    expired = expire_overdue(
        [c], {SLOT_KEY: SLOT}, now=datetime(2026, 8, 13, 18, 0, tzinfo=TASHKENT)
    )
    assert expired == []
    assert c.state is State.PENDING_APPROVAL


# --- the card ---------------------------------------------------------------


def test_card_shows_the_post_verbatim_and_the_deadline():
    """A preview that differs from production is worse than no preview."""
    body = "Kecha promptni tashlagandim.\n\nKim sinab koʻrdi? 👀"
    rendered = card(Content(slot_key=SLOT_KEY, kind="technique", text=body), SLOT)
    assert body in rendered
    assert "14.08 10:00" in rendered
    assert "13.08 22:00" in rendered  # deadline, 12h before


def test_card_flags_attached_media():
    c = Content(slot_key=SLOT_KEY, kind="technique", text="x", media_paths=["a.png", "b.png"])
    assert "2 ta media" in card(c, SLOT)
