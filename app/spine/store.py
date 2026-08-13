"""SQLite persistence for the spine.

WAL mode, one file, no server. At 14 posts and a few hundred comments a week this
is the right size of tool, and a backup is a file copy. The VM already runs a
Postgres for another project; a second one would be more moving parts than the
workload justifies.

Everything the runtime needs to survive a restart lives here — most critically
the channel-post-to-thread-root mapping, which Telegram will not tell us twice.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from app.spine.states import Content, State

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS content (
    slot_key              TEXT PRIMARY KEY,
    kind                  TEXT NOT NULL,
    text                  TEXT NOT NULL DEFAULT '',
    state                 TEXT NOT NULL,
    revision_rounds       INTEGER NOT NULL DEFAULT 0,
    media_paths           TEXT NOT NULL DEFAULT '[]',
    history               TEXT NOT NULL DEFAULT '[]',
    approved_by           INTEGER,
    approved_at           TEXT,
    published_message_id  INTEGER,
    updated_at            TEXT NOT NULL
);

-- The only record of which channel post owns which comment thread. Telegram
-- provides this exactly once, in a live update, and never again.
CREATE TABLE IF NOT EXISTS threads (
    channel_message_id  INTEGER PRIMARY KEY,
    group_root_id       INTEGER NOT NULL UNIQUE,
    slot_key            TEXT,
    seeded_message_id   INTEGER,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comments (
    message_id      INTEGER PRIMARY KEY,
    group_root_id   INTEGER NOT NULL,
    author_id       INTEGER,
    author_name     TEXT,
    text            TEXT,
    script          TEXT,
    decision        TEXT,
    handled_at      TEXT,
    reply_message_id INTEGER,
    -- The bot's own reply. Distinct from `text`, which is the MEMBER's message.
    -- Conflating the two fed anti-repetition the questions instead of its own
    -- answers, and it shipped two near-identical replies into a live thread.
    reply_text      TEXT
);
CREATE INDEX IF NOT EXISTS idx_comments_root ON comments(group_root_id);

-- Pre-approved evergreen posts. An unapproved slot publishes from here rather
-- than publishing something unreviewed or going silent.
CREATE TABLE IF NOT EXISTS backup_pool (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    text        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'evergreen',
    times_used  INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        # WAL survives a hard kill without corrupting, and lets the reply loop
        # read while the scheduler writes.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def _migrate(self) -> None:
        """Additive migrations. SQLite has no IF NOT EXISTS for columns."""
        existing = {r[1] for r in self._conn.execute("PRAGMA table_info(comments)")}
        if "reply_text" not in existing:
            self._conn.execute("ALTER TABLE comments ADD COLUMN reply_text TEXT")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        self._conn.execute("BEGIN")
        try:
            yield self._conn
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    # --- content ------------------------------------------------------------

    def save_content(self, c: Content) -> None:
        self._conn.execute(
            """INSERT INTO content (slot_key, kind, text, state, revision_rounds,
                   media_paths, history, approved_by, approved_at,
                   published_message_id, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(slot_key) DO UPDATE SET
                   kind=excluded.kind, text=excluded.text, state=excluded.state,
                   revision_rounds=excluded.revision_rounds,
                   media_paths=excluded.media_paths, history=excluded.history,
                   approved_by=excluded.approved_by, approved_at=excluded.approved_at,
                   published_message_id=excluded.published_message_id,
                   updated_at=excluded.updated_at""",
            (
                c.slot_key, c.kind, c.text, c.state.value, c.revision_rounds,
                json.dumps(c.media_paths),
                json.dumps([[a.value, b.value, r] for a, b, r in c.history]),
                c.approved_by,
                c.approved_at.isoformat() if c.approved_at else None,
                c.published_message_id,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

    def get_content(self, slot_key: str) -> Content | None:
        row = self._conn.execute(
            "SELECT * FROM content WHERE slot_key=?", (slot_key,)
        ).fetchone()
        return self._to_content(row) if row else None

    def content_in_state(self, state: State) -> list[Content]:
        rows = self._conn.execute(
            "SELECT * FROM content WHERE state=? ORDER BY slot_key", (state.value,)
        ).fetchall()
        return [self._to_content(r) for r in rows]

    @staticmethod
    def _to_content(row: sqlite3.Row) -> Content:
        return Content(
            slot_key=row["slot_key"],
            kind=row["kind"],
            text=row["text"],
            state=State(row["state"]),
            revision_rounds=row["revision_rounds"],
            media_paths=json.loads(row["media_paths"]),
            history=[(State(a), State(b), r) for a, b, r in json.loads(row["history"])],
            approved_by=row["approved_by"],
            approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
            published_message_id=row["published_message_id"],
        )

    # --- threads ------------------------------------------------------------

    def record_thread(
        self, channel_message_id: int, group_root_id: int,
        *, slot_key: str | None = None, seeded_message_id: int | None = None,
    ) -> None:
        """Persist the post-to-thread mapping the moment it is learned.

        Telegram sends the auto-forward once and drops updates older than 24h, so
        losing this before it is written loses the thread permanently.
        """
        self._conn.execute(
            """INSERT INTO threads (channel_message_id, group_root_id, slot_key,
                   seeded_message_id, created_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(channel_message_id) DO UPDATE SET
                   group_root_id=excluded.group_root_id,
                   slot_key=COALESCE(excluded.slot_key, threads.slot_key),
                   seeded_message_id=COALESCE(excluded.seeded_message_id,
                                              threads.seeded_message_id)""",
            (channel_message_id, group_root_id, slot_key, seeded_message_id,
             datetime.now().isoformat(timespec="seconds")),
        )

    def known_roots(self) -> set[int]:
        """Every thread root seen. The only valid keys for thread resolution."""
        return {r[0] for r in self._conn.execute("SELECT group_root_id FROM threads")}

    def root_for_post(self, channel_message_id: int) -> int | None:
        row = self._conn.execute(
            "SELECT group_root_id FROM threads WHERE channel_message_id=?",
            (channel_message_id,),
        ).fetchone()
        return row["group_root_id"] if row else None

    # --- comments -----------------------------------------------------------

    def seen_comment(self, message_id: int) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM comments WHERE message_id=?", (message_id,)
        ).fetchone() is not None

    def record_comment(
        self, message_id: int, group_root_id: int, *, author_id: int | None,
        author_name: str, text: str, script: str, decision: str,
        reply_message_id: int | None = None, reply_text: str | None = None,
    ) -> None:
        """Record a handled comment.

        ``text`` is the MEMBER's message; ``reply_text`` is what the bot said
        back. Keeping them distinct matters — conflating them fed anti-repetition
        the questions instead of its own answers.
        """
        self._conn.execute(
            """INSERT INTO comments (message_id, group_root_id, author_id, author_name,
                   text, script, decision, handled_at, reply_message_id, reply_text)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(message_id) DO UPDATE SET
                   decision=excluded.decision, handled_at=excluded.handled_at,
                   reply_message_id=excluded.reply_message_id,
                   reply_text=excluded.reply_text""",
            (message_id, group_root_id, author_id, author_name, text, script,
             decision, datetime.now().isoformat(timespec="seconds"), reply_message_id,
             reply_text),
        )

    def replies_in_thread(self, group_root_id: int) -> list[str]:
        """The bot's own reply TEXTS in this thread, for anti-repetition.

        Must read reply_text, not text. `text` holds the member's message, and
        feeding those back as "what you already said" is why two near-identical
        replies reached a live thread.
        """
        rows = self._conn.execute(
            """SELECT reply_text AS text FROM comments
               WHERE group_root_id=? AND reply_text IS NOT NULL AND reply_text != ''
               ORDER BY message_id""",
            (group_root_id,),
        ).fetchall()
        return [r["text"] for r in rows if r["text"]]

    def artifacts_posted(self, group_root_id: int | None = None) -> int:
        """North-star metric: member-generated artifacts posted."""
        sql = "SELECT COUNT(*) FROM comments WHERE decision='react'"
        args: tuple = ()
        if group_root_id is not None:
            sql += " AND group_root_id=?"
            args = (group_root_id,)
        return self._conn.execute(sql, args).fetchone()[0]

    # --- backup pool --------------------------------------------------------

    def add_backup(self, text: str, kind: str = "evergreen") -> int:
        cur = self._conn.execute(
            "INSERT INTO backup_pool (text, kind, created_at) VALUES (?,?,?)",
            (text, kind, datetime.now().isoformat(timespec="seconds")),
        )
        return int(cur.lastrowid)

    def take_backup(self) -> tuple[int, str] | None:
        """Least-recently-used backup post, so the pool rotates rather than
        repeating the same post every time a slot goes unapproved."""
        row = self._conn.execute(
            """SELECT id, text FROM backup_pool
               ORDER BY times_used ASC, COALESCE(last_used_at, '') ASC, id ASC
               LIMIT 1"""
        ).fetchone()
        if not row:
            return None
        self._conn.execute(
            "UPDATE backup_pool SET times_used=times_used+1, last_used_at=? WHERE id=?",
            (datetime.now().isoformat(timespec="seconds"), row["id"]),
        )
        return int(row["id"]), row["text"]

    def backup_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM backup_pool").fetchone()[0]

    # --- runtime ------------------------------------------------------------

    def set_runtime(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO runtime (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def get_runtime(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM runtime WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    @property
    def last_seen(self) -> datetime | None:
        raw = self.get_runtime("last_seen")
        return datetime.fromisoformat(raw) if raw else None

    @last_seen.setter
    def last_seen(self, when: datetime) -> None:
        self.set_runtime("last_seen", when.isoformat())
