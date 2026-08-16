"""The content state machine.

Deterministic and LLM-free by design. Agents write, judge and analyze; this
decides what may be published and when. The single property everything else
depends on: **no path leads from `drafting` to `published` without passing
through `approved`.**
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class State(str, Enum):
    DRAFTING = "drafting"
    """Writer produced text; critics have not passed it yet."""

    NEEDS_REVISION = "needs_revision"
    """A critic rejected it. Back to the Writer, up to a bounded number of rounds."""

    PENDING_APPROVAL = "pending_approval"
    """Sent to the approver. The only doorway to `approved`."""

    APPROVED = "approved"
    """A human said yes. Frozen — see `Content.frozen`."""

    SCHEDULED = "scheduled"
    """Approved and bound to a slot."""

    PUBLISHED = "published"
    REJECTED = "rejected"
    EXPIRED = "expired"
    """Its slot passed without approval. The backup pool covered it."""


TERMINAL = {State.PUBLISHED, State.REJECTED, State.EXPIRED}

#: Every legal move. Anything absent here raises.
TRANSITIONS: dict[State, set[State]] = {
    State.DRAFTING: {State.NEEDS_REVISION, State.PENDING_APPROVAL, State.REJECTED},
    State.NEEDS_REVISION: {State.DRAFTING, State.REJECTED},
    State.PENDING_APPROVAL: {State.APPROVED, State.NEEDS_REVISION, State.REJECTED, State.EXPIRED},
    State.APPROVED: {State.SCHEDULED, State.REJECTED},
    State.SCHEDULED: {State.PUBLISHED, State.REJECTED, State.EXPIRED},
    State.PUBLISHED: set(),
    State.REJECTED: set(),
    State.EXPIRED: set(),
}


class IllegalTransition(RuntimeError):
    pass


class FrozenContent(RuntimeError):
    """Raised on any attempt to edit approved content.

    If the generator may touch a post after approval, approval means nothing —
    what a human said yes to is not what ships.
    """


@dataclass
class Content:
    slot_key: str
    kind: str
    text: str = ""
    seed_comment: str = ""
    """The bot's own first comment, posted into the thread once Telegram
    announces the auto-forward. The Writer produced one on every draft and it was
    dropped on the floor here — so the mechanism meant to open a comment section
    that has never been used had never actually run."""
    state: State = State.DRAFTING
    revision_rounds: int = 0
    media_paths: list[str] = field(default_factory=list)
    history: list[tuple[State, State, str]] = field(default_factory=list)
    approved_by: int | None = None
    approved_at: datetime | None = None
    published_message_id: int | None = None

    @property
    def frozen(self) -> bool:
        return self.state in {State.APPROVED, State.SCHEDULED, State.PUBLISHED}

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL

    def transition(self, to: State, reason: str = "") -> None:
        if to not in TRANSITIONS[self.state]:
            raise IllegalTransition(
                f"{self.slot_key}: {self.state.value} -> {to.value} is not a legal move"
            )
        self.history.append((self.state, to, reason))
        self.state = to

    def set_text(self, text: str) -> None:
        """Edit the body. Refused once a human has approved it."""
        if self.frozen:
            raise FrozenContent(
                f"{self.slot_key} is {self.state.value}; approved content is immutable. "
                f"Re-open it with request_revision() to change anything."
            )
        self.text = text

    def attach_media(self, path: str) -> None:
        if self.frozen:
            raise FrozenContent(f"{self.slot_key} is {self.state.value}; media is fixed at approval")
        self.media_paths.append(path)

    # --- the moves ----------------------------------------------------------

    def request_revision(self, reason: str, *, max_rounds: int = 3) -> None:
        """A critic rejected the draft. Bounded, so it cannot loop forever."""
        self.transition(State.NEEDS_REVISION, reason)
        self.revision_rounds += 1
        if self.revision_rounds >= max_rounds:
            self.transition(State.REJECTED, f"{reason} (gave up after {max_rounds} rounds)")
        else:
            self.transition(State.DRAFTING, "revising")

    def submit_for_approval(self) -> None:
        self.transition(State.PENDING_APPROVAL, "sent to approver")

    def approve(self, approver_id: int, approver_ids: tuple[int, ...], *, at: datetime) -> None:
        """Approve. Rejects anyone not on the allowlist.

        Callback data is trivially forgeable by anyone who can guess it, so the
        approver is checked here rather than trusted from the button press.
        """
        if approver_ids and approver_id not in approver_ids:
            raise IllegalTransition(f"user {approver_id} is not an approver")
        self.transition(State.APPROVED, f"approved by {approver_id}")
        self.approved_by = approver_id
        self.approved_at = at

    def schedule(self) -> None:
        self.transition(State.SCHEDULED, "bound to slot")

    def publish(self, message_id: int) -> None:
        self.transition(State.PUBLISHED, f"message {message_id}")
        self.published_message_id = message_id

    def expire(self, reason: str = "slot passed without approval") -> None:
        self.transition(State.EXPIRED, reason)

    def reject(self, reason: str = "") -> None:
        self.transition(State.REJECTED, reason)


def publishable(content: Content) -> bool:
    """The only question the publisher ever asks.

    Nothing reaches the channel unless a human approved it and it is bound to a
    slot. An unapproved slot publishes from the backup pool instead.
    """
    return content.state is State.SCHEDULED and content.approved_by is not None
