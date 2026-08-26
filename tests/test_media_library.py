"""Asset matching. The rule that matters is when it declines to match."""

from __future__ import annotations

import pytest

from app.media.library import Asset, load, pick

ASSETS = [
    Asset(id="uzbek-room-5s", url="https://cdn/a.mp4", kind="video",
          shows=("traditional Uzbek room", "family"),
          good_for=("commercial_craft", "why_content"), duration=5),
    Asset(id="uzbek-room-30s", url="https://cdn/b.mp4", kind="video",
          shows=("traditional Uzbek room",),
          good_for=("commercial_craft",), duration=30),
    Asset(id="storybook-5s", url="https://cdn/c.mp4", kind="video",
          shows=("hand-drawn storybook animation",),
          good_for=("mission",), duration=5),
]


def test_matching_asset_is_returned():
    assert pick("why_content", assets=ASSETS).id == "uzbek-room-5s"


def test_shortest_clip_wins():
    """A five-second clip gets watched; a thirty-second one gets scrolled past."""
    assert pick("commercial_craft", assets=ASSETS).duration == 5


def test_an_already_used_asset_is_not_repeated():
    got = pick("commercial_craft", used={"uzbek-room-5s"}, assets=ASSETS)
    assert got.id == "uzbek-room-30s"


def test_no_loose_matching_when_nothing_fits():
    """A post with no video is a smaller loss than a post with a video that has
    nothing to do with it — the second signals nobody is paying attention."""
    assert pick("news", assets=ASSETS) is None
    assert pick("technique", assets=ASSETS) is None


def test_exhausted_kind_returns_none_rather_than_reusing():
    used = {"uzbek-room-5s", "uzbek-room-30s"}
    assert pick("commercial_craft", used=used, assets=ASSETS) is None


def test_the_shipped_library_parses():
    """Not asserting contents — only that the file is valid and loadable."""
    for asset in load():
        assert asset.id and asset.kind in ("video", "photo")
        # A URL or a local file, but it must have one — an asset with neither
        # resolves to nothing at 21:00 and the slot falls to the backup pool.
        assert asset.url or asset.local, f"{asset.id} has no source"
        if asset.local:
            assert asset.path.is_file(), f"{asset.id} points at a missing file"
        assert asset.good_for, f"{asset.id} has no good_for; it can never be picked"
