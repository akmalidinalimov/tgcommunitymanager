"""Publish a channel post and seed the first comment under it.

The whole difficulty is that a channel post and its comment thread are connected
by exactly one event and nothing else: the copy Telegram auto-forwards into the
linked discussion group a moment after publishing. No API call can look that
mapping up afterwards, and updates older than 24h are dropped server-side and
never replayed. So publishing and seeding are one flow, and if the listener is
not running at publish time the thread is unreachable forever.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.telegram.api import BotAPI
from app.telegram.classifier import Kind, classify


@dataclass(frozen=True)
class SeededPost:
    channel_message_id: int
    thread_root_id: int
    seed_comment_id: int
    seconds_to_forward: float


class ForwardNotSeen(RuntimeError):
    """The auto-forward never arrived, so this post has no reachable thread."""


def find_thread_root(
    updates: list[dict],
    *,
    channel_message_id: int,
    group_id: int,
    channel_id: int,
    bot_id: int,
) -> int | None:
    """Return the group-side message id of the auto-forwarded copy, if present.

    Pure, so the matching rule is testable without the network. The group-side id
    bears no arithmetic relation to the channel-side id — ``forward_origin`` is
    the only thing that connects them.
    """
    for update in updates:
        message = update.get("message") or update.get("channel_post")
        if not message:
            continue
        if (message.get("chat") or {}).get("id") != group_id:
            continue

        result = classify(message, bot_id=bot_id, channel_id=channel_id)
        if result.kind is not Kind.THREAD_ROOT:
            continue
        if result.origin_message_id == channel_message_id:
            return message["message_id"]
    return None


def publish_and_seed(
    api: BotAPI,
    *,
    channel_id: int,
    group_id: int,
    bot_id: int,
    text: str,
    seed_comment: str,
    wait_seconds: float = 60.0,
    poll_timeout: int = 5,
) -> SeededPost:
    """Publish to the channel, wait for the auto-forward, then seed the thread.

    Raises ForwardNotSeen if the copy never arrives, leaving the channel post in
    place — a post without a seeded comment is a far smaller problem than a
    comment posted into the group's main feed.
    """
    # Drain anything already queued, so a stale update cannot be mistaken for
    # ours and so our own forward is not skipped by a leftover offset.
    offset: int | None = None
    for update in api.get_updates(timeout=0):
        offset = update["update_id"] + 1

    posted = api.send_message(channel_id, text)
    channel_message_id = posted["message_id"]
    started = time.monotonic()

    root_id: int | None = None
    while time.monotonic() - started < wait_seconds:
        updates = api.get_updates(offset=offset, timeout=poll_timeout)
        if updates:
            offset = updates[-1]["update_id"] + 1
        root_id = find_thread_root(
            updates,
            channel_message_id=channel_message_id,
            group_id=group_id,
            channel_id=channel_id,
            bot_id=bot_id,
        )
        if root_id is not None:
            break

    elapsed = time.monotonic() - started
    if root_id is None:
        raise ForwardNotSeen(
            f"channel post {channel_message_id} published, but no auto-forward "
            f"arrived in {group_id} within {wait_seconds:.0f}s. The post stands; "
            f"its comment thread cannot be seeded."
        )

    seeded = api.send_message(group_id, seed_comment, reply_to_message_id=root_id)

    # Telegram echoes the thread the message actually landed in. If this does not
    # match the root we targeted, the comment is sitting in the group's main feed
    # where everyone can see it, and we want to know immediately rather than by
    # someone noticing.
    landed_in = seeded.get("message_thread_id")
    if landed_in is not None and landed_in != root_id:
        raise RuntimeError(
            f"seed comment landed in thread {landed_in}, expected {root_id} — "
            f"it is in the group's main feed. Delete message {seeded['message_id']}."
        )

    return SeededPost(
        channel_message_id=channel_message_id,
        thread_root_id=root_id,
        seed_comment_id=seeded["message_id"],
        seconds_to_forward=elapsed,
    )
