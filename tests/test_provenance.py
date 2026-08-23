"""The media library must agree with the knowledge base and with reality.

Both halves of this were wrong at once on 2026-08-16, found only by reading the
live Higgsfield records:

* `potter-portrait-nano` claimed `nano_banana_pro`; it was made with
  `nano_banana_2`. The bot would have described that image using a different
  model's characteristics — a confidently wrong answer with a source.
* six clips claimed `9:16` against a 16:9 channel standard. They were 16:9 all
  along, and a whole regeneration round was queued to "fix" them.

Neither was visible from the repo. These tests make the next drift visible.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "data" / "media_library.yaml"
KNOWLEDGE = ROOT / "data" / "knowledge" / "models.yaml"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@pytest.fixture(scope="module")
def assets() -> list[dict]:
    return load(LIBRARY)["assets"]


@pytest.fixture(scope="module")
def known_models() -> set[str]:
    return set(load(KNOWLEDGE)["models"])


def test_every_model_named_in_the_library_exists_in_the_knowledge_base(assets, known_models):
    """A library naming a model the knowledge base does not have means the bot
    can answer "what made this" with a model that is not the one that made it."""
    named = {a["model"] for a in assets if a.get("model")}
    unknown = sorted(named - known_models)
    assert not unknown, (
        f"media_library names models absent from the knowledge base: {unknown}. "
        f"Either the label is wrong or the model needs a knowledge-base entry."
    )


#: The two shapes this channel publishes. 16:9 was the original founder
#: direction and is still the default. 9:16 was added on 2026-08-23, when the
#: founders asked for vertical portrait comparisons — a phone-first audience
#: gives a vertical image roughly three times the screen a landscape one gets.
#:
#: Still a closed set on purpose. The failure this catches was never "an unusual
#: ratio", it was a 3:2 asset that had been *mislabelled* 16:9 and would have
#: published cropped.
CHANNEL_ASPECTS = {"16:9", "9:16"}


def test_every_asset_is_one_of_the_channel_aspect_ratios(assets):
    wrong = [(a["id"], a.get("aspect")) for a in assets
             if a.get("aspect") and a["aspect"] not in CHANNEL_ASPECTS]
    assert not wrong, f"assets outside {sorted(CHANNEL_ASPECTS)}: {wrong}"


def test_provenance_is_recorded_for_every_asset(assets):
    """The VPS cannot query Higgsfield — the connector is session-bound — so an
    asset whose parameters were never written down is a question the bot can
    never answer."""
    missing = [a["id"] for a in assets if not a.get("provenance")]
    assert not missing, f"assets with no recorded provenance: {missing}"


def test_reference_counts_are_recorded(assets):
    """"Was it made from one image?" is the most asked question under our video
    posts, and it is unanswerable without this."""
    missing = [a["id"] for a in assets if a.get("refs") is None]
    assert not missing, f"assets with no reference count: {missing}"


def test_videos_record_whether_multi_shot_was_used(assets):
    videos = [a for a in assets if a.get("kind") == "video"]
    assert videos, "no videos in the library"
    missing = [a["id"] for a in videos if a.get("multi_shots") is None]
    assert not missing, f"videos with no multi_shots flag: {missing}"


def test_the_knowledge_base_distinguishes_the_two_nano_banana_models(known_models):
    """They are different models and the library confused them once already."""
    assert {"nano_banana_pro", "nano_banana_2"} <= known_models
