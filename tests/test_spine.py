"""The deterministic spine: slots, missed-run recovery, and the state machine.

The property under test throughout is that nothing unapproved can ever reach the
channel, and that downtime degrades into a backup post rather than into silence
or a stale post landing at the wrong hour.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.spine.scheduler import (
    TASHKENT,
    Slot,
    approval_deadline,
    due_slots,
    next_slot,
    slots_between,
)
from app.spine.states import (
    Content,
    FrozenContent,
    IllegalTransition,
    State,
    publishable,
)

UTC = ZoneInfo("UTC")
APPROVERS = (6542876935,)


def tk(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TASHKENT)


# --- slots ------------------------------------------------------------------


def test_one_slot_a_day_at_twentyone():
    """One post a day. Two slots made the second one a liability: a day with one
    written post left the other with nothing approved, and an unapproved slot
    publishes from the backup pool — five pool posts against seven empty slots
    a week, draining while every log line still said "published"."""
    slots = slots_between(tk(2026, 8, 13, 0, 0), tk(2026, 8, 13, 23, 59))
    assert [s.at.hour for s in slots] == [21]


def test_next_slot_crosses_midnight():
    assert next_slot(tk(2026, 8, 13, 22, 0)).at == tk(2026, 8, 14, 21, 0)


def test_next_slot_is_strictly_after_now():
    """Standing exactly on 21:00 must not re-fire the slot being published."""
    assert next_slot(tk(2026, 8, 13, 21, 0)).at == tk(2026, 8, 14, 21, 0)


def test_server_in_another_timezone_still_resolves_tashkent_slots():
    """The VPS is not in Tashkent. 06:30 UTC is 11:30 Tashkent, so the next slot
    is the same evening, not the following morning."""
    utc_now = datetime(2026, 8, 13, 6, 30, tzinfo=UTC)
    assert next_slot(utc_now).at == tk(2026, 8, 13, 21, 0)


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError):
        next_slot(datetime(2026, 8, 13, 10, 0))


# --- missed-run recovery ----------------------------------------------------


def test_short_outage_publishes_the_missed_slot():
    publish, too_late = due_slots(tk(2026, 8, 13, 20, 55), clock=tk(2026, 8, 13, 22, 0))
    assert [s.at.hour for s in publish] == [21]
    assert too_late == []


def test_long_outage_skips_stale_slots_instead_of_dumping_them():
    """Three days down. Publishing three backdated posts at once would be worse
    than having published none — only a slot still within its window goes out."""
    publish, too_late = due_slots(tk(2026, 8, 10, 20, 0), clock=tk(2026, 8, 13, 22, 30))
    assert [s.key for s in publish] == ["2026-08-13_21:00"]
    assert len(too_late) == 3


def test_an_evening_post_never_lands_in_the_small_hours():
    publish, too_late = due_slots(tk(2026, 8, 13, 20, 0), clock=tk(2026, 8, 14, 1, 30))
    assert publish == []
    assert [s.key for s in too_late] == ["2026-08-13_21:00"]


def test_first_ever_boot_publishes_nothing():
    """A fresh deployment must not dump history into a live channel."""
    publish, too_late = due_slots(None, clock=tk(2026, 8, 13, 23, 0))
    assert publish == [] and too_late == []


def test_no_missed_slots_when_nothing_elapsed():
    publish, too_late = due_slots(tk(2026, 8, 13, 21, 1), clock=tk(2026, 8, 13, 21, 2))
    assert publish == [] and too_late == []


def test_approval_deadline_precedes_the_slot():
    slot = Slot(tk(2026, 8, 14, 21, 0))
    assert approval_deadline(slot) == tk(2026, 8, 14, 9, 0)


# --- state machine ----------------------------------------------------------


def content(**kw):
    return Content(slot_key="2026-08-14_10:00", kind="technique", **kw)


def approved_content():
    c = content(text="draft")
    c.submit_for_approval()
    c.approve(APPROVERS[0], APPROVERS, at=tk(2026, 8, 13, 20, 0))
    return c


def test_the_happy_path():
    c = approved_content()
    c.schedule()
    assert publishable(c)
    c.publish(message_id=607)
    assert c.state is State.PUBLISHED and c.published_message_id == 607


def test_drafting_can_never_reach_published_directly():
    """The property the whole design rests on."""
    c = content(text="unreviewed")
    with pytest.raises(IllegalTransition):
        c.transition(State.PUBLISHED)
    with pytest.raises(IllegalTransition):
        c.transition(State.SCHEDULED)
    assert not publishable(c)


def test_pending_approval_is_not_publishable():
    c = content(text="draft")
    c.submit_for_approval()
    assert not publishable(c)


def test_approved_content_is_immutable():
    """If the generator can touch a post after approval, approval is meaningless."""
    c = approved_content()
    with pytest.raises(FrozenContent):
        c.set_text("sneaky rewrite")
    with pytest.raises(FrozenContent):
        c.attach_media("new.png")


def test_only_an_allowlisted_user_can_approve():
    """Callback data is forgeable, so the approver is verified server-side."""
    c = content(text="draft")
    c.submit_for_approval()
    with pytest.raises(IllegalTransition):
        c.approve(999999, APPROVERS, at=tk(2026, 8, 13, 20, 0))
    assert c.state is State.PENDING_APPROVAL


def test_revision_rounds_are_bounded():
    """A critic and a writer disagreeing forever must not burn tokens all night."""
    c = content(text="translationese")
    for _ in range(3):
        if c.is_terminal:
            break
        c.request_revision("sounds translated", max_rounds=3)
    assert c.state is State.REJECTED
    assert c.revision_rounds == 3


def test_unapproved_slot_expires_rather_than_publishing():
    c = content(text="draft")
    c.submit_for_approval()
    c.expire()
    assert c.state is State.EXPIRED
    assert not publishable(c)


def test_scheduled_content_can_still_expire_if_the_slot_passes():
    c = approved_content()
    c.schedule()
    c.expire("publisher was down past the window")
    assert not publishable(c)


def test_history_records_every_move():
    c = approved_content()
    c.schedule()
    c.publish(607)
    moves = [(a.value, b.value) for a, b, _ in c.history]
    assert moves == [
        ("drafting", "pending_approval"),
        ("pending_approval", "approved"),
        ("approved", "scheduled"),
        ("scheduled", "published"),
    ]


def test_terminal_states_are_final():
    c = approved_content()
    c.schedule()
    c.publish(607)
    for target in (State.DRAFTING, State.APPROVED, State.SCHEDULED, State.REJECTED):
        with pytest.raises(IllegalTransition):
            c.transition(target)
