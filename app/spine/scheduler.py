"""Publishing slots in Asia/Tashkent, and what to do about the ones we missed.

Pure functions over an injected clock, so restarts, downtime and end-of-day edges
are all testable without waiting for a real 10:00.

Uzbekistan has not observed DST since 2005, so Asia/Tashkent is a fixed UTC+5.
That removes the usual class of scheduler bug — but only if every comparison
happens in the channel's timezone rather than the server's, which is why nothing
here takes a naive datetime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TASHKENT = ZoneInfo("Asia/Tashkent")

#: (hour, minute) in Tashkent local time.
SLOTS: tuple[tuple[int, int], ...] = ((10, 0), (21, 0))

#: A slot older than this is not worth publishing late — a "good morning" post
#: landing at midnight is worse than no post. It is skipped and recorded.
MAX_LATENESS = timedelta(hours=3)


@dataclass(frozen=True, order=True)
class Slot:
    """One publishing opportunity, identified by its local date and time."""

    at: datetime

    @property
    def key(self) -> str:
        return self.at.strftime("%Y-%m-%d_%H:%M")

    @property
    def local_date(self) -> date:
        return self.at.date()

    def __str__(self) -> str:
        return self.key


def _slots_on(day: date) -> list[Slot]:
    return [
        Slot(datetime(day.year, day.month, day.day, h, m, tzinfo=TASHKENT))
        for h, m in SLOTS
    ]


def now_tashkent(clock: datetime | None = None) -> datetime:
    """Current time in Tashkent. An aware datetime in any zone is converted."""
    if clock is None:
        return datetime.now(TASHKENT)
    if clock.tzinfo is None:
        raise ValueError("naive datetime rejected — pass an aware one")
    return clock.astimezone(TASHKENT)


def slots_between(start: datetime, end: datetime) -> list[Slot]:
    """Every slot in ``(start, end]``, ascending."""
    start, end = now_tashkent(start), now_tashkent(end)
    out: list[Slot] = []
    day = start.date()
    while day <= end.date():
        out.extend(s for s in _slots_on(day) if start < s.at <= end)
        day += timedelta(days=1)
    return sorted(out)


def slot_from_key(key: str) -> Slot:
    """Rebuild a Slot from its stored key. Inverse of ``Slot.key``."""
    return Slot(datetime.strptime(key, "%Y-%m-%d_%H:%M").replace(tzinfo=TASHKENT))


def next_slot(clock: datetime | None = None) -> Slot:
    """The next slot strictly after now."""
    now = now_tashkent(clock)
    day = now.date()
    for _ in range(3):
        for slot in _slots_on(day):
            if slot.at > now:
                return slot
        day += timedelta(days=1)
    raise RuntimeError("no slot found — SLOTS is empty")


def due_slots(
    last_seen: datetime | None,
    *,
    clock: datetime | None = None,
    max_lateness: timedelta = MAX_LATENESS,
) -> tuple[list[Slot], list[Slot]]:
    """Return ``(publish_now, missed_too_late)`` after downtime.

    ``last_seen`` is when the scheduler last ran. On a first-ever start it is
    None and nothing historical is published — booting a new deployment must
    never dump a backlog of yesterday's posts into the channel.
    """
    now = now_tashkent(clock)
    if last_seen is None:
        return [], []

    publish, too_late = [], []
    for slot in slots_between(last_seen, now):
        (publish if now - slot.at <= max_lateness else too_late).append(slot)
    return publish, too_late


def approval_deadline(slot: Slot, *, hours_before: int = 12) -> datetime:
    """When a slot's content must be approved by.

    Content is sent for approval a day ahead; this is the moment the spine stops
    waiting and falls back to the backup pool.
    """
    return slot.at - timedelta(hours=hours_before)


def slots_needing_approval(
    clock: datetime | None = None,
    *,
    horizon_hours: int = 36,
) -> list[Slot]:
    """Slots close enough that their content should already be in review."""
    now = now_tashkent(clock)
    return slots_between(now, now + timedelta(hours=horizon_hours))
