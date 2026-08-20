"""Assemble the context a reply decision needs, and decide whether to reply at all.

Pure functions over raw Bot API messages, so every rule below is testable against
the recorded thread from post 606 without touching the network or an LLM.

The rule that matters most here is the one that says *don't*. On post 606 a member
answered another member's question unprompted, and members posted their own
generated videos. That peer-to-peer behaviour is the entire point of the channel;
a bot that jumps into every question crowds it out and replaces a community with
a helpdesk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.telegram.classifier import Kind, classify
from app.text.script import Script, reply_script


class Decision(str, Enum):
    REPLY = "reply"
    REACT = "react"
    """Acknowledge with an emoji reaction instead of text.

    Three text replies under three member videos read as a machine however the
    sentences are varied — the repetition is structural, not a prompting problem.
    A reaction is what a person actually does, costs nothing, and still tells the
    member they were seen."""
    SKIP_ALREADY_ANSWERED = "skip_already_answered"
    SKIP_NOT_A_QUESTION = "skip_not_a_question"
    SKIP_NOT_HUMAN = "skip_not_human"
    SKIP_OWN_THREAD_NOISE = "skip_own_thread_noise"


@dataclass
class ThreadMessage:
    message_id: int
    author: str
    author_id: int | None
    text: str
    kind: Kind
    reply_to: int | None = None
    has_media: bool = False


@dataclass
class ReplyContext:
    target: ThreadMessage
    thread_root_id: int
    post_text: str
    post_id: int | None = None
    """The channel post number, which is how `our_posts` is keyed.

    Without it the Replier can be told the channel post is a trusted source and
    still not know which entry describes it, so it escalates a question the
    knowledge base already answers."""
    history: list[ThreadMessage] = field(default_factory=list)
    script: Script = Script.LATIN
    decision: Decision = Decision.REPLY
    decision_reason: str = ""

    @property
    def should_reply(self) -> bool:
        return self.decision is Decision.REPLY

    @property
    def should_react(self) -> bool:
        return self.decision is Decision.REACT


MEDIA_FIELDS = ("photo", "video", "animation", "document", "video_note", "voice", "sticker")


def to_thread_message(message: dict, *, bot_id: int, channel_id: int) -> ThreadMessage:
    result = classify(message, bot_id=bot_id, channel_id=channel_id)
    frm = message.get("from") or {}
    sender_chat = message.get("sender_chat") or {}
    return ThreadMessage(
        message_id=message["message_id"],
        author=frm.get("first_name") or sender_chat.get("title") or "?",
        author_id=frm.get("id"),
        text=(message.get("text") or message.get("caption") or "").strip(),
        kind=result.kind,
        reply_to=(message.get("reply_to_message") or {}).get("message_id"),
        has_media=any(f in message for f in MEDIA_FIELDS),
    )


def _looks_like_a_question(text: str) -> bool:
    if "?" in text:
        return True
    lowered = text.lower()
    # Uzbek interrogatives and the -mi question particle, in both scripts.
    markers = (
        "qanday", "qaysi", "nima", "qancha", "qayer", "nega", "mumkinmi", "bormi",
        "qanaqa", "kerak", "oladi", "qanday qilib",
        "қандай", "қайси", "нима", "қанча", "қаер", "нега", "мумкинми", "борми", "қанақа",
    )
    if any(m in lowered for m in markers):
        return True
    return lowered.rstrip("!. ").endswith(("mi", "ми"))


def build_context(
    target_id: int,
    messages: list[dict],
    *,
    bot_id: int,
    channel_id: int,
    thread_root_id: int,
    post_id: int | None = None,
) -> ReplyContext:
    """Build reply context for ``target_id`` and decide whether to answer it."""
    parsed = [to_thread_message(m, bot_id=bot_id, channel_id=channel_id) for m in messages]
    by_id = {m.message_id: m for m in parsed}
    target = by_id[target_id]

    root = by_id.get(thread_root_id)
    post_text = root.text if root else ""

    history = [m for m in parsed if m.message_id != thread_root_id]
    ctx = ReplyContext(
        target=target,
        thread_root_id=thread_root_id,
        post_text=post_text,
        post_id=post_id,
        history=history,
        script=reply_script(
            target.text,
            [m.text for m in history if m.author_id == target.author_id and m.text],
        ),
    )

    if target.kind is not Kind.HUMAN:
        ctx.decision = Decision.SKIP_NOT_HUMAN
        ctx.decision_reason = f"sender is {target.kind.value}"
        return ctx

    # Someone is already engaging with this message — answering it, or asking the
    # author a follow-up. Either way a conversation is happening between people,
    # which is worth more than anything the bot can add, and the founders replying
    # directly settles it outright.
    responders = [
        m for m in parsed
        if m.reply_to == target_id and m.message_id != target_id
        and m.kind in (Kind.HUMAN, Kind.ANONYMOUS_ADMIN)
    ]
    if responders:
        who = "a founder" if any(r.kind is Kind.ANONYMOUS_ADMIN for r in responders) else "another member"
        ctx.decision = Decision.SKIP_ALREADY_ANSWERED
        ctx.decision_reason = f"{who} is already engaging ({responders[0].author})"
        return ctx

    if not target.text and target.has_media:
        # A member posting their own generated result is the north-star event —
        # never ignore one. But acknowledge it with a reaction, not a sentence.
        ctx.decision = Decision.REACT
        ctx.decision_reason = "member posted their own generated media"
        return ctx

    if not target.text:
        ctx.decision = Decision.SKIP_OWN_THREAD_NOISE
        ctx.decision_reason = "no text and no media"
        return ctx

    if not _looks_like_a_question(target.text) and len(target.text.split()) <= 2:
        ctx.decision = Decision.SKIP_NOT_A_QUESTION
        ctx.decision_reason = "short acknowledgement, nothing to answer"
        return ctx

    ctx.decision_reason = "open question from a member"
    return ctx
