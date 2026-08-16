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
                            ok=True, text=POST, kind=kind, problem="", seed_comment="birinchi izoh"))

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


# --- Telegram's URL size ceiling --------------------------------------------


def test_an_oversized_url_photo_is_fetched_and_uploaded_instead(rt, monkeypatch):
    """Telegram fetches a URL itself and caps photos sent that way at 5MB. A 2K
    card crosses it, and the only symptom is "failed to get HTTP URL content" —
    which is why Monday's 10:00 card never arrived."""
    from app.media.library import Asset
    from app.telegram.api import TelegramError

    asset = Asset(id="big", url="https://cdn/big.png", kind="photo",
                  good_for=("technique",))
    monkeypatch.setattr("app.runtime.asset_by_id", lambda aid, **k: asset)
    monkeypatch.setattr("app.runtime.fetch_image", lambda url, **k: b"\x89PNG" + b"x" * 900)

    def refuse_url(chat_id, photo, **kw):
        raise TelegramError("sendPhoto", "Bad Request: failed to get HTTP URL content", 400)

    monkeypatch.setattr(rt.api, "send_photo", refuse_url)

    c = Content(slot_key="2026-08-17_10:00", kind="technique", text="matn")
    c.attach_media("big")
    c.submit_for_approval()
    rt.store.save_content(c)

    assert rt._send_for_approval(c, Slot(datetime(2026, 8, 17, 10, 0, tzinfo=TASHKENT)))
    assert any(s.get("media_kind") == "card" for s in rt.api.sent), (
        "should have fallen back to a byte upload")


def test_a_failed_card_is_reported_as_failed(rt, monkeypatch):
    """prepare_upcoming logged 'approval card sent' unconditionally, so a card
    that never arrived reported success."""
    monkeypatch.setattr(rt, "_send_for_approval", lambda *a, **k: False)
    slot = Slot(datetime(2026, 8, 17, 10, 0, tzinfo=TASHKENT))
    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [slot])
    monkeypatch.setattr("app.runtime.load_planned", lambda: {})
    monkeypatch.setattr("app.runtime.write_post", lambda kind, **k: SimpleNamespace(
        ok=True, text="matn", kind=kind, problem="", seed_comment=""))

    rt.prepare_upcoming()
    assert rt.store.get_runtime(f"card_sent:{slot.key}") is None


def test_approving_a_media_card_edits_its_caption_not_its_text(rt):
    """editMessageText refuses a photo, so the card could never show its verdict."""
    from tests.test_runtime import ADMIN, callback, pending_content

    edited = []
    rt.api.edit_message_caption = lambda cid, mid, cap, **kw: edited.append(cap) or {}
    pending_content(rt.store, "2026-08-17_10:00")

    query = callback("2026-08-17_10:00")
    query["callback_query"]["message"]["photo"] = [{"file_id": "p"}]
    rt.handle_update(query)

    assert edited, "a media card must be edited by caption"
    assert "Tasdiqlandi" in edited[0]
