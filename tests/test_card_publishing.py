"""Publishing a rendered card, for the post kinds no photograph fits.

`challenge`, `recognition` and `behind_scenes` have no asset tagged for them in
the media library, so they were publishing as bare text — quietly breaking the
founder rule that every post ships with a visual.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.runtime import Runtime
from app.spine.scheduler import Slot
from app.spine.states import Content
from app.spine.store import Store
from tests.test_runtime import ADMIN, BOT, CHANNEL, FakeAPI, SETTINGS, TASHKENT, pending_content

pytest.importorskip("PIL")


@pytest.fixture
def rt(tmp_path):
    return Runtime(settings=SETTINGS, store=Store(tmp_path / "c.db"),
                   api=FakeAPI(), bot_id=BOT)


def approved_card(store, slot_key, kind, text):
    c = Content(slot_key=slot_key, kind=kind, text=text)
    c.attach_media("card")
    c.submit_for_approval()
    c.approve(ADMIN, (ADMIN,), at=datetime(2026, 8, 13, 20, 0, tzinfo=TASHKENT))
    c.schedule()
    store.save_content(c)
    return c


POST = "Bitta kadr oling\nDeraza yorugʻida suratga oling.\nNatijangizni tashlang 👇"


def test_a_kind_with_no_photograph_publishes_a_rendered_card(rt, monkeypatch):
    monkeypatch.setattr("app.runtime.pick_asset", lambda kind, used=None: None)
    approved_card(rt.store, "2026-08-14_21:00", "challenge", POST)

    rt.publish_slot(Slot(datetime(2026, 8, 14, 21, 0, tzinfo=TASHKENT)))

    sent = rt.api.sent[0]
    assert sent["media_kind"] == "card", "published as bare text instead of a card"
    assert sent["card_bytes"] > 1000, "the card looks empty"
    assert "Bitta kadr oling" in sent["text"], "the full post must still be the caption"


def test_drafting_binds_a_card_when_no_photograph_matches(rt, monkeypatch):
    slot = Slot(datetime(2026, 8, 14, 21, 0, tzinfo=TASHKENT))
    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [slot])
    monkeypatch.setattr("app.runtime.pick_asset", lambda kind, used=None: None)
    monkeypatch.setattr("app.runtime.write_post",
                        lambda kind, **k: SimpleNamespace(
                            ok=True, text=POST, kind=kind, problem=""))

    rt.prepare_upcoming()

    assert rt.store.get_content(slot.key).media_paths == ["card"]
    assert any(s.get("media_kind") == "card" for s in rt.api.sent), (
        "the approval card should preview the rendered card")


def test_an_unapproved_backup_still_gets_a_visual(rt, monkeypatch):
    """The every-post-has-a-visual rule holds on the fallback path too — a
    backup nobody previewed is exactly when the channel can least afford to
    look unattended."""
    monkeypatch.setattr("app.runtime.pick_asset", lambda kind, used=None: None)
    rt.store.add_backup("Zaxira post matni\nIkkinchi qator.")
    pending_content(rt.store, "2026-08-14_21:00")

    rt.publish_slot(Slot(datetime(2026, 8, 14, 21, 0, tzinfo=TASHKENT)))

    published = [s for s in rt.api.sent if s["chat_id"] == CHANNEL]
    assert published[0]["media_kind"] == "card"
    assert published[0]["text"].startswith("Zaxira post matni")


def test_a_broken_renderer_never_costs_the_slot(rt, monkeypatch):
    """A card is a nice-to-have; the post is not."""
    def boom(*a, **k):
        raise RuntimeError("no font")

    monkeypatch.setattr("app.runtime.pick_asset", lambda kind, used=None: None)
    monkeypatch.setattr("app.media.cards.render", boom)
    rt.store.add_backup("zaxira post")
    pending_content(rt.store, "2026-08-14_21:00")

    rt.publish_slot(Slot(datetime(2026, 8, 14, 21, 0, tzinfo=TASHKENT)))

    published = [s for s in rt.api.sent if s["chat_id"] == CHANNEL]
    assert published and published[0]["text"] == "zaxira post"
    assert not published[0].get("media_kind"), "should have degraded to text"
