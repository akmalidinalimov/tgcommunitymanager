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


def test_founder_assets_live_outside_the_ignored_media_cache():
    """A local asset must be IN the repo, or it is not there at all.

    /data/media/ is gitignored as a cache of regenerable CDN pulls. Seven
    founder-supplied images were filed there, which made this suite pass
    locally — the files existed on that machine — and fail on CI, where they
    had never been committed. They live in /data/assets/ now, which ships.
    """
    for asset in load():
        if asset.local:
            assert asset.local.startswith("data/assets/"), (
                f"{asset.id} is local but sits in {asset.local}; "
                f"only data/assets/ is tracked by git"
            )


def test_a_local_asset_with_a_missing_file_fails_by_name():
    """Not with an httpx protocol error twenty frames down.

    A local asset has no URL to fall back on, so a missing file used to reach
    fetch_image("") and surface as UnsupportedProtocol, naming neither the
    asset nor the path.
    """
    import pytest

    from app.media.library import Asset
    from app.runtime import Runtime

    ghost = Asset(id="ghost", url="", kind="photo", local="data/assets/nope.jpg")
    with pytest.raises(FileNotFoundError, match="ghost"):
        Runtime._album_item(ghost)
