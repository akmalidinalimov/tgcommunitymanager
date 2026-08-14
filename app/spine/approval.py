"""Day-ahead approval: card, buttons, and what a button press is allowed to do.

The flow the founders asked for: content is drafted and sent for approval a day
before its slot; on approval the slot is released and publishes at its scheduled
time; without approval by the deadline the backup pool covers it.

Everything here is pure except the two functions that take an API client, so the
authorisation rules are tested without Telegram.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape

from app.spine.scheduler import Slot, approval_deadline
from app.spine.states import Content, IllegalTransition, State

APPROVE = "ok"
REJECT = "no"
REVISE = "rv"

#: callback_data is capped at 64 bytes by Telegram. "ok:2026-08-14_10:00" is 19,
#: so the slot key fits directly and no lookup table is needed.
SEPARATOR = ":"


def callback_data(action: str, slot_key: str) -> str:
    data = f"{action}{SEPARATOR}{slot_key}"
    if len(data.encode()) > 64:
        raise ValueError(f"callback_data too long: {data!r}")
    return data


def parse_callback(data: str) -> tuple[str, str]:
    action, _, slot_key = data.partition(SEPARATOR)
    return action, slot_key


def keyboard(slot_key: str) -> dict:
    return {
        "inline_keyboard": [[
            {"text": "✅ Tasdiqlash", "callback_data": callback_data(APPROVE, slot_key)},
            {"text": "✏️ Qayta yozish", "callback_data": callback_data(REVISE, slot_key)},
            {"text": "🚫 Bekor qilish", "callback_data": callback_data(REJECT, slot_key)},
        ]]
    }


def card(content: Content, slot: Slot) -> str:
    """The approval card. Shows the post exactly as it will appear, because a
    preview that differs from production is worse than no preview.

    The post body is escaped. It is model-written text going into a message sent
    with parse_mode=HTML, so a single ``<`` or ``&`` makes Telegram reject the
    whole card with "can't parse entities" — and a card that fails to send is a
    slot the founders never see.
    """
    deadline = approval_deadline(slot)
    media = f"\n📎 {len(content.media_paths)} ta media" if content.media_paths else ""
    return (
        f"🗓 <b>{slot.at.strftime('%d.%m %H:%M')}</b> · {escape(content.kind)}{media}\n"
        f"<i>tasdiqlash muddati: {deadline.strftime('%d.%m %H:%M')}</i>\n"
        f"{'─' * 22}\n"
        f"{escape(content.text)}\n"
        f"{'─' * 22}"
    )


def decided_card(content: Content, slot: Slot, verdict: str) -> str:
    return f"{verdict}\n\n{card(content, slot)}"


@dataclass
class CallbackOutcome:
    handled: bool
    toast: str
    new_state: State | None = None
    verdict_line: str = ""


def handle_callback(
    action: str,
    content: Content | None,
    *,
    user_id: int,
    approver_ids: tuple[int, ...],
    at: datetime,
) -> CallbackOutcome:
    """Apply a button press. Pure — the caller performs the Telegram side effects.

    Authorisation happens here rather than being inferred from the button, because
    callback_data is guessable and anyone who can reach the bot can send one.
    """
    if approver_ids and user_id not in approver_ids:
        return CallbackOutcome(False, "Sizda ruxsat yo'q")

    if content is None:
        return CallbackOutcome(False, "Topilmadi — eskirgan tugma")

    if content.state is not State.PENDING_APPROVAL:
        # The usual cause is a double tap, or a second approver reaching a card
        # already decided. Say so plainly instead of transitioning again.
        return CallbackOutcome(False, f"Allaqachon: {content.state.value}")

    if action == APPROVE:
        try:
            content.approve(user_id, approver_ids, at=at)
        except IllegalTransition as exc:
            return CallbackOutcome(False, str(exc))
        content.schedule()
        return CallbackOutcome(True, "Tasdiqlandi ✅", State.SCHEDULED, "✅ <b>Tasdiqlandi</b>")

    if action == REJECT:
        content.reject(f"rejected by {user_id}")
        return CallbackOutcome(True, "Bekor qilindi", State.REJECTED, "🚫 <b>Bekor qilindi</b>")

    if action == REVISE:
        content.request_revision(f"revision asked by {user_id}")
        return CallbackOutcome(True, "Qayta yozilmoqda", content.state, "✏️ <b>Qayta yozilmoqda</b>")

    return CallbackOutcome(False, "Noma'lum amal")


def expire_overdue(
    pending: list[Content], slots: dict[str, Slot], *, now: datetime
) -> list[Content]:
    """Expire anything past its approval deadline.

    Returning them rather than publishing anything is deliberate: the caller
    substitutes a backup post. Nothing unapproved ever reaches the channel.
    """
    expired = []
    for content in pending:
        slot = slots.get(content.slot_key)
        if slot and now >= approval_deadline(slot):
            content.expire()
            expired.append(content)
    return expired
