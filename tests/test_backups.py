"""Seeding the backup pool from the repo."""

from __future__ import annotations

import pytest

from app.spine.backups import seed
from app.spine.store import Store


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "b.db") as s:
        yield s


def write(tmp_path, body):
    p = tmp_path / "pool.yaml"
    p.write_text(body, encoding="utf-8")
    return p


GOOD = """
posts:
  - id: plate-and-overlay
    kind: technique
    text: |
      Rasm ichida o'zbekcha yozuv buziladi.

      Toza rasm chiqaring, yozuvni montajda ustiga qo'ying.
  - id: what-business-buys
    kind: why_content
    text: |
      Biznes rasm sotib olmaydi.

      Biznes muammosi yechilishini xohlaydi.
"""


def test_posts_are_seeded_from_the_file(store, tmp_path):
    assert seed(store, write(tmp_path, GOOD)) == 2
    assert store.backup_count() == 2


def test_seeding_twice_adds_nothing(store, tmp_path):
    """The bot restarts often; the pool must not grow a duplicate each time."""
    path = write(tmp_path, GOOD)
    seed(store, path)
    assert seed(store, path) == 0
    assert store.backup_count() == 2


def test_apostrophes_are_normalized_on_the_way_in(store, tmp_path):
    seed(store, write(tmp_path, GOOD))
    _, text = store.take_backup()
    assert "'" not in text


def test_a_backup_that_fails_lint_is_refused(store, tmp_path):
    """Backups publish unattended with nobody reading them first. They are the
    last content that should carry a banned construction."""
    bad = """
posts:
  - id: officialese
    text: |
      Mazkur vosita orqali kontent yaratish amalga oshiriladi.
"""
    assert seed(store, write(tmp_path, bad)) == 0
    assert store.backup_count() == 0


def test_strict_mode_raises_so_ci_can_catch_it(store, tmp_path):
    bad = "posts:\n  - id: x\n    text: Bu ishlamoqda\n"
    with pytest.raises(ValueError, match="failed lint"):
        seed(store, write(tmp_path, bad), strict=True)


def test_a_missing_file_is_not_an_error(store, tmp_path):
    assert seed(store, tmp_path / "absent.yaml") == 0


def test_seeded_posts_rotate_least_recently_used(store, tmp_path):
    seed(store, write(tmp_path, GOOD))
    first = store.take_backup()[1]
    second = store.take_backup()[1]
    assert first != second


def test_the_shipped_pool_seeds_cleanly(store):
    """The real data/backup_pool.yaml, not a fixture. These publish unattended
    with nobody reading them first, so a rule change that silently invalidates
    them must fail here rather than on the VPS at 10:00."""
    from app.spine.backups import DEFAULT_PATH, load_file

    entries = load_file()
    assert len(entries) >= 3, "pool too small to be a safety net"
    seeded = seed(store, DEFAULT_PATH, strict=True)
    assert seeded == len(entries), "some shipped posts failed lint"


def test_a_post_pulled_from_the_file_is_retired_from_the_pool(tmp_path):
    """Seeding used to be additive only. A backup post pulled for teaching a
    claim we had disproved stayed in the live pool and kept its turn to publish
    unattended, because deleting it from the file did nothing to the database."""
    store = Store(tmp_path / "b.db")
    pool = tmp_path / "pool.yaml"

    pool.write_text(
        "posts:\n"
        "  - id: keep\n    text: |\n      Birinchi post shu yerda qoladi.\n"
        "  - id: wrong\n    text: |\n      Bu post notoʻgʻri maʼlumot beradi.\n",
        encoding="utf-8")
    assert seed(store, pool) == 2
    assert store.backup_count() == 2

    # The post is pulled from version control.
    pool.write_text(
        "posts:\n  - id: keep\n    text: |\n      Birinchi post shu yerda qoladi.\n",
        encoding="utf-8")
    seed(store, pool)

    assert store.backup_count() == 1
    remaining = store.take_backup()
    assert remaining and "notoʻgʻri" not in remaining[1]


def test_retiring_is_idempotent_and_leaves_a_matching_pool_alone(tmp_path):
    store = Store(tmp_path / "b.db")
    pool = tmp_path / "pool.yaml"
    pool.write_text("posts:\n  - id: a\n    text: |\n      Yagona post.\n", encoding="utf-8")

    seed(store, pool)
    seed(store, pool)
    seed(store, pool)
    assert store.backup_count() == 1
