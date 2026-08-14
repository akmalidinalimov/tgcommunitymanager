"""The media library: what can be attached to a post, and what must not be.

Founder direction: every post ships with a visual. Text alone does not earn a
read — people want to see what the thing can do before they will read about it.

The library is a version-controlled index of assets the founders have approved
for reuse, each tagged with what it actually shows. Matching is by tag, never by
guesswork, because a video that does not match its caption is worse than no
video: it reads as stock filler and undoes the credibility the caption is
building.

Assets live at their Higgsfield CDN URLs. Telegram fetches a URL itself, so
nothing is downloaded or re-uploaded here — but those URLs expire, so anything
relied on long-term must be mirrored. `expires` records that risk per asset.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("media")

DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "media_library.yaml"


@dataclass(frozen=True)
class Asset:
    id: str
    url: str
    kind: str
    """video or photo."""
    shows: tuple[str, ...] = ()
    """What is literally on screen. Used for matching, so be concrete."""
    good_for: tuple[str, ...] = field(default=())
    """Post kinds this asset genuinely illustrates."""
    model: str = ""
    duration: int | None = None
    expires: bool = True
    """True for a vendor CDN URL that will eventually 404."""

    @property
    def is_video(self) -> bool:
        return self.kind == "video"


def load(path: Path | None = None) -> list[Asset]:
    source = path or DEFAULT_PATH
    if not source.is_file():
        return []
    import yaml

    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    return [
        Asset(
            id=entry["id"],
            url=entry["url"],
            kind=entry.get("kind", "video"),
            shows=tuple(entry.get("shows") or ()),
            good_for=tuple(entry.get("good_for") or ()),
            model=entry.get("model", ""),
            duration=entry.get("duration"),
            expires=bool(entry.get("expires", True)),
        )
        for entry in (data.get("assets") or [])
    ]


def get(asset_id: str, *, assets: list[Asset] | None = None) -> Asset | None:
    """Resolve an asset by id.

    Content records the id, never the URL: vendor CDN links expire, and a post
    approved on Monday must still resolve on Friday.
    """
    for asset in (assets if assets is not None else load()):
        if asset.id == asset_id:
            return asset
    log.warning("asset %s is no longer in the library", asset_id)
    return None


def pick(post_kind: str, *, used: set[str] | None = None,
         assets: list[Asset] | None = None) -> Asset | None:
    """Choose an asset that genuinely illustrates ``post_kind``.

    Returns None rather than a loose match. A post going out with no video is a
    smaller loss than a post going out with a video that has nothing to do with
    it — the second actively signals that nobody is paying attention.
    """
    used = used or set()
    candidates = [
        a for a in (assets if assets is not None else load())
        if post_kind in a.good_for and a.id not in used
    ]
    if not candidates:
        log.info("no unused asset tagged for %s; post will go out as text", post_kind)
        return None
    # Prefer the shortest: a five-second clip is watched, a thirty-second one is
    # scrolled past.
    return sorted(candidates, key=lambda a: (a.duration or 999, a.id))[0]
