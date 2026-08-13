"""Persistence, including the one record that cannot be recovered if lost."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.spine.states import Content, State
from app.spine.store import Store

TASHKENT = ZoneInfo("Asia/Tashkent")
APPROVERS = (6542876935,)


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as s:
        yield s


def test_wal_mode_is_on(store):
    """WAL survives a hard kill without corrupting, and lets the reply loop read
    while the scheduler writes."""
    mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_content_round_trips_with_full_history(store):
    c = Content(slot_key="2026-08-14_10:00", kind="technique", text="salom")
    c.submit_for_approval()
    c.approve(APPROVERS[0], APPROVERS, at=datetime(2026, 8, 13, 20, 0, tzinfo=TASHKENT))
    c.schedule()
    c.publish(607)
    store.save_content(c)

    back = store.get_content("2026-08-14_10:00")
    assert back.state is State.PUBLISHED
    assert back.published_message_id == 607
    assert back.approved_by == APPROVERS[0]
    assert back.approved_at == c.approved_at
    assert [(a.value, b.value) for a, b, _ in back.history] == [
        ("drafting", "pending_approval"),
        ("pending_approval", "approved"),
        ("approved", "scheduled"),
        ("scheduled", "published"),
    ]


def test_saving_twice_updates_rather_than_duplicating(store):
    c = Content(slot_key="2026-08-14_10:00", kind="technique", text="v1")
    store.save_content(c)
    c.set_text("v2")
    store.save_content(c)
    assert store.get_content("2026-08-14_10:00").text == "v2"
    assert len(store.content_in_state(State.DRAFTING)) == 1


def test_thread_mapping_survives_a_restart(store, tmp_path):
    """Telegram sends the auto-forward once and drops updates older than 24h.
    If this mapping is lost, the thread is unreachable forever."""
    store.record_thread(606, 3, slot_key="2026-08-13_21:00", seeded_message_id=4)
    store.close()

    with Store(tmp_path / "test.db") as reopened:
        assert reopened.root_for_post(606) == 3
        assert reopened.known_roots() == {3}


def test_known_roots_is_what_thread_resolution_trusts(store):
    store.record_thread(606, 3)
    store.record_thread(607, 58)
    assert store.known_roots() == {3, 58}
    assert store.root_for_post(999) is None


def test_recording_a_thread_twice_does_not_lose_the_seed_id(store):
    store.record_thread(606, 3, seeded_message_id=4)
    store.record_thread(606, 3, slot_key="2026-08-13_21:00")
    row = store._conn.execute(
        "SELECT * FROM threads WHERE channel_message_id=606"
    ).fetchone()
    assert row["seeded_message_id"] == 4
    assert row["slot_key"] == "2026-08-13_21:00"


def test_comments_are_deduplicated_so_a_replay_cannot_double_reply(store):
    assert not store.seen_comment(8)
    store.record_comment(8, 3, author_id=6184382670, author_name="Фотима",
                         text="Қандай қилганизнм", script="cyrillic", decision="escalate")
    assert store.seen_comment(8)
    store.record_comment(8, 3, author_id=6184382670, author_name="Фотима",
                         text="Қандай қилганизнм", script="cyrillic", decision="reply")
    assert store._conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 1


def test_anti_repetition_gets_the_bots_replies_not_the_members_questions(store):
    """Regression. This returned the `text` column — the MEMBER's message — so
    anti-repetition was comparing new drafts against the questions rather than
    against what the bot had already said. Two near-identical replies reached a
    live thread before it was caught."""
    store.record_comment(16, 3, author_id=1, author_name="A", text="Qaysi AI ishlatiladi?",
                         script="latin", decision="reply", reply_message_id=100,
                         reply_text="Seedance 2.5 va Kling 3.0")
    store.record_comment(17, 3, author_id=2, author_name="B", text="Omni-chi?",
                         script="latin", decision="reply", reply_message_id=101,
                         reply_text="Omni bunday darajada qilib bermaydi")
    store.record_comment(18, 3, author_id=3, author_name="C", text="unanswered",
                         script="latin", decision="skip")

    prior = store.replies_in_thread(3)
    assert prior == ["Seedance 2.5 va Kling 3.0", "Omni bunday darajada qilib bermaydi"]
    assert not any("Qaysi AI" in p or "Omni-chi" in p for p in prior)


def test_artifacts_posted_is_the_north_star_counter(store):
    for mid in (11, 17, 18):
        store.record_comment(mid, 3, author_id=mid, author_name="member",
                             text="", script="latin", decision="react")
    store.record_comment(19, 3, author_id=19, author_name="member",
                         text="savol", script="latin", decision="reply")
    assert store.artifacts_posted() == 3
    assert store.artifacts_posted(group_root_id=3) == 3
    assert store.artifacts_posted(group_root_id=99) == 0


def test_backup_pool_rotates_least_recently_used(store):
    """Falling back to the same post every time would be worse than the silence
    it is meant to prevent."""
    for text in ("backup A", "backup B", "backup C"):
        store.add_backup(text)
    picks = [store.take_backup()[1] for _ in range(4)]
    assert picks[:3] == ["backup A", "backup B", "backup C"]
    assert picks[3] == "backup A"  # wrapped around, not stuck


def test_empty_backup_pool_returns_nothing_rather_than_failing(store):
    assert store.backup_count() == 0
    assert store.take_backup() is None


def test_last_seen_persists_for_missed_run_recovery(store, tmp_path):
    when = datetime(2026, 8, 13, 21, 5, tzinfo=TASHKENT)
    store.last_seen = when
    store.close()
    with Store(tmp_path / "test.db") as reopened:
        assert reopened.last_seen == when


def test_last_seen_is_none_on_a_fresh_database(store):
    """Which is what makes a first-ever boot publish nothing."""
    assert store.last_seen is None
