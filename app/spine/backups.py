"""Seed the backup pool from a version-controlled file.

The pool is the only thing standing between an unapproved slot and a silent
channel, so it must not be something that can be missing. Keeping it in the repo
means it is reviewable in a pull request, approved once rather than through taps
that vanish with the next volume, and present on any fresh deployment.

Seeding is idempotent: a post already in the pool is never added twice, however
often the bot restarts.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.spine.store import Store
from app.text.lint import blockers, lint
from app.text.orthography import normalize_apostrophes

log = logging.getLogger("backups")

DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "backup_pool.yaml"


def load_file(path: Path | None = None) -> list[dict]:
    source = path or DEFAULT_PATH
    if not source.is_file():
        return []
    import yaml

    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    return list(data.get("posts") or [])


def seed(store: Store, path: Path | None = None, *, strict: bool = False) -> int:
    """Add any file post not already in the pool. Returns how many were added.

    Each post is linted before it goes in. A backup publishes unattended, with
    nobody reading it first — it is the last content that should reach the
    channel carrying a banned construction.
    """
    existing = {
        row[0] for row in store._conn.execute("SELECT text FROM backup_pool")
    }
    added = 0
    for entry in load_file(path):
        text = normalize_apostrophes((entry.get("text") or "").strip())
        if not text or text in existing:
            continue

        problems = blockers(lint(text))
        if problems:
            message = f"backup {entry.get('id', '?')} failed lint: " + "; ".join(
                str(p) for p in problems
            )
            if strict:
                raise ValueError(message)
            log.warning("%s — skipped", message)
            continue

        store.add_backup(text, kind=entry.get("kind", "evergreen"))
        existing.add(text)
        added += 1

    if added:
        log.info("seeded %s backup post(s); pool now holds %s", added, store.backup_count())
    return added
