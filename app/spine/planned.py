"""Hand-written posts, keyed by slot.

The Writer drafts every slot by default. That is right for an unattended week,
and wrong for a week the founders have written themselves — there was no way to
put a specific post into a specific slot, so a post crafted with a founder
existed only in a conversation and never reached the channel.

A planned post wins over the Writer for its slot. Everything downstream is
unchanged: it still goes for approval, still passes lint before it is offered,
still publishes through the same path. The only thing that changes is where the
words came from.

Lint runs here rather than at publish time on purpose. A hand-written post can
break the caption cap or carry a banned construction exactly like a generated
one, and finding that out at 10:00 on the day is finding out too late.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.text.lint import blockers, lint
from app.text.orthography import normalize_apostrophes

log = logging.getLogger("planned")

DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "planned_posts.yaml"


@dataclass(frozen=True)
class PlannedPost:
    slot_key: str
    kind: str
    text: str
    seed_comment: str = ""
    asset: str = ""
    """Media library id, or 'card' to render one. Empty means pick automatically."""
    note: str = ""

    @property
    def problems(self) -> list[str]:
        out = [str(p) for p in blockers(lint(self.text))]
        if self.seed_comment:
            out += [f"seed: {p}" for p in blockers(lint(self.seed_comment))]
        return out


def load(path: Path | None = None) -> dict[str, PlannedPost]:
    source = path or DEFAULT_PATH
    if not source.is_file():
        return {}
    import yaml

    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    planned: dict[str, PlannedPost] = {}
    for slot_key, entry in (data.get("posts") or {}).items():
        post = PlannedPost(
            slot_key=slot_key,
            kind=entry.get("kind", "technique"),
            text=normalize_apostrophes((entry.get("text") or "").strip()),
            seed_comment=normalize_apostrophes((entry.get("seed_comment") or "").strip()),
            asset=entry.get("asset", ""),
            note=entry.get("note", ""),
        )
        if not post.text:
            log.warning("planned post %s has no text; ignoring", slot_key)
            continue
        if post.problems:
            # Refused rather than published. A planned post that fails lint is a
            # mistake worth catching in review, not at the slot.
            log.error("planned post %s fails lint: %s", slot_key, "; ".join(post.problems))
            continue
        planned[slot_key] = post
    if planned:
        log.info("%s planned post(s) loaded", len(planned))
    return planned
