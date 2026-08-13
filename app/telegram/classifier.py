"""Classify incoming discussion-group messages before any LLM sees them.

The rules here are not guesswork. Telegram's Bot API server assigns a synthetic
``from`` user whenever the real sender is a chat, and the mapping is fixed:

    sender is a chat, in a non-channel chat →
        sender_chat.id == chat.id  ⇒ from = 1087968824   (anonymous group admin)
        is_automatic_forward       ⇒ from = 777000       (the channel post copy)
        otherwise                  ⇒ from = 136817688    (commenting as a channel)

Two consequences that are easy to get wrong:

* **Never filter on ``from.is_bot``.** ``1087968824`` and ``136817688`` are bots
  representing real humans. Dropping bots drops real people.
* **``message_thread_id`` is not proof of a comment thread.** Telegram sets it on
  *any* reply chain in a supergroup, so an ordinary user-to-user reply carries one
  too. It only identifies a comment thread when it matches a known auto-forward
  root id.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

# --- Telegram's synthetic sender ids (production values) ---------------------
TELEGRAM_SERVICE_ID = 777000
ANONYMOUS_ADMIN_ID = 1087968824
CHANNEL_IDENTITY_ID = 136817688

# Test-DC equivalents, accepted so fixtures recorded against a test DC classify
# identically rather than silently falling through to "human".
TEST_DC_IDS = {
    ANONYMOUS_ADMIN_ID: 552888,
    CHANNEL_IDENTITY_ID: 936174,
}

#: Presence of any of these fields means the update is a service event, not a
#: message a person wrote. Replying to one is the classic public embarrassment.
SERVICE_FIELDS = (
    "pinned_message",
    "new_chat_members",
    "left_chat_member",
    "new_chat_title",
    "new_chat_photo",
    "delete_chat_photo",
    "group_chat_created",
    "supergroup_chat_created",
    "channel_chat_created",
    "migrate_to_chat_id",
    "migrate_from_chat_id",
    "message_auto_delete_timer_changed",
    "video_chat_scheduled",
    "video_chat_started",
    "video_chat_ended",
    "video_chat_participants_invited",
    "forum_topic_created",
    "forum_topic_edited",
    "forum_topic_closed",
    "forum_topic_reopened",
    "general_forum_topic_hidden",
    "general_forum_topic_unhidden",
    "successful_payment",
    "users_shared",
    "chat_shared",
    "proximity_alert_triggered",
    "write_access_allowed",
    "giveaway_created",
    "giveaway_completed",
    "boost_added",
)


class Kind(str, Enum):
    """What an incoming discussion-group message actually is."""

    THREAD_ROOT = "thread_root"
    """The channel post auto-forwarded into the group. Seed replies against it.
    Never reply *to it as if a person wrote it*, and never delete it — deleting
    the root permanently disables comments for that post."""

    SERVICE = "service"
    """A join/leave/pin/etc. event. Drop silently."""

    OWN = "own"
    """Sent by this bot. Defensive only; Telegram does not echo our own sends."""

    ANONYMOUS_ADMIN = "anonymous_admin"
    """A staff member posting anonymously. Exempt from moderation, and no
    per-user identity exists, so reputation cannot be tracked."""

    CHANNEL_IDENTITY = "channel_identity"
    """Someone commenting under a channel's identity. No human user id exists
    anywhere in the update: only ban_chat_sender_chat can act on them."""

    HUMAN = "human"
    """An ordinary person. The only kind that reaches the agents."""


@dataclass(frozen=True)
class Classification:
    kind: Kind
    reason: str
    #: Set for THREAD_ROOT: the channel-side message id this copy came from.
    origin_message_id: int | None = None
    #: Set for CHANNEL_IDENTITY / ANONYMOUS_ADMIN: the acting chat's id.
    sender_chat_id: int | None = None

    @property
    def routes_to_agents(self) -> bool:
        return self.kind is Kind.HUMAN


def _is(from_id: int | None, canonical: int) -> bool:
    """True if ``from_id`` is the given synthetic sender, on production or test DC."""
    return from_id is not None and from_id in (canonical, TEST_DC_IDS.get(canonical))


def classify(
    message: dict[str, Any],
    *,
    bot_id: int,
    channel_id: int,
) -> Classification:
    """Classify one discussion-group message. Order is load-bearing.

    ``message`` is a raw Bot API Message object as a dict, so fixtures recorded
    from the wire can be replayed verbatim without model drift.
    """
    from_id = (message.get("from") or {}).get("id")
    sender_chat = message.get("sender_chat") or {}
    sender_chat_id = sender_chat.get("id")
    chat_id = (message.get("chat") or {}).get("id")

    # 1. Service events first: a pin or join can otherwise look like a message.
    for field in SERVICE_FIELDS:
        if field in message:
            return Classification(Kind.SERVICE, f"service field: {field}")

    # 2. The auto-forwarded channel post. Checked before the 777000 test, because
    #    this is the one message from that sender we must keep.
    if message.get("is_automatic_forward"):
        origin = message.get("forward_origin") or {}
        origin_chat_id = (origin.get("chat") or {}).get("id")
        if origin_chat_id is not None and origin_chat_id != channel_id:
            return Classification(
                Kind.SERVICE, f"auto-forward from a foreign channel: {origin_chat_id}"
            )
        return Classification(
            Kind.THREAD_ROOT,
            "auto-forwarded channel post",
            origin_message_id=origin.get("message_id"),
        )

    # 3. Telegram service notifications that are not the auto-forward.
    if _is(from_id, TELEGRAM_SERVICE_ID):
        return Classification(Kind.SERVICE, "Telegram service notification (777000)")

    # 4. Ourselves. Structurally unreachable, kept so a future change cannot
    #    create a self-reply loop in public.
    if from_id == bot_id:
        return Classification(Kind.OWN, "sent by this bot")

    # 5. Anonymous group admin: the sender chat IS this chat.
    if sender_chat_id is not None and sender_chat_id == chat_id and _is(from_id, ANONYMOUS_ADMIN_ID):
        return Classification(
            Kind.ANONYMOUS_ADMIN, "anonymous group admin", sender_chat_id=sender_chat_id
        )

    # 6. Commenting under a channel identity.
    if sender_chat_id is not None and _is(from_id, CHANNEL_IDENTITY_ID):
        return Classification(
            Kind.CHANNEL_IDENTITY, "commenting as a channel", sender_chat_id=sender_chat_id
        )

    # 7. Anything else with a sender_chat is an identity we have not modelled.
    #    Escalate rather than guess: a wrong reply here is public.
    if sender_chat_id is not None:
        return Classification(
            Kind.CHANNEL_IDENTITY,
            f"unmodelled chat sender (from={from_id})",
            sender_chat_id=sender_chat_id,
        )

    if from_id is None:
        return Classification(Kind.SERVICE, "no sender")

    return Classification(Kind.HUMAN, "ordinary user")


def thread_key(
    message: dict[str, Any],
    *,
    known_roots: Iterable[int],
) -> int | None:
    """Return the comment-thread root id, or ``None`` if this is not a comment.

    ``message_thread_id`` alone is not sufficient: Telegram sets it for any reply
    chain in a supergroup. It only means "comment thread" when it points at a root
    we have actually seen arrive as an auto-forward.
    """
    roots = set(known_roots)

    tid = message.get("message_thread_id")
    if tid is not None and tid in roots:
        return tid

    # Bot API synthesizes reply_to_message for top-level comments, so a direct
    # reply to the auto-forward identifies the thread even when the id above is
    # missing or belongs to an unrelated reply chain.
    replied = message.get("reply_to_message") or {}
    if replied.get("is_automatic_forward"):
        return replied.get("message_id")
    replied_id = replied.get("message_id")
    if replied_id is not None and replied_id in roots:
        return replied_id

    return None
