"""Shot grammar. The rejections matter more than the acceptances."""

from __future__ import annotations

import pytest

from app.media.shots import BANNED_TERMS, Shot, ShotError, clean, diff


def cafe(**kw):
    base = dict(
        subject="a ceramic cup of coffee with crema still settling",
        environment="a small Tashkent cafe, wooden counter, brass grinder behind",
        foreground="the blurred edge of a menu card",
        shot_size="close-up", angle="low angle", lens="85mm",
        light="warm window light from camera-right",
    )
    base.update(kw)
    return Shot(**base)


def test_a_valid_shot_builds_an_ordered_prompt():
    p = cafe().image_prompt()
    assert p.index("ceramic cup") < p.index("Tashkent cafe"), \
        "environment before subject makes the model pull the camera back"
    assert "low angle" in p and "85mm" in p and "foreground" in p


def test_incompatible_lens_and_shot_size_is_rejected():
    """A 24mm extreme close-up is physically impossible and produces mush."""
    with pytest.raises(ShotError, match="does not pair"):
        cafe(shot_size="extreme close-up", lens="24mm").image_prompt()


def test_a_shot_without_foreground_is_rejected():
    """The cheapest realism win there is. A frame with nothing between lens and
    subject floats in empty space and reads as generated."""
    with pytest.raises(ShotError, match="foreground"):
        cafe(foreground="").image_prompt()


def test_lens_defaults_to_one_that_pairs():
    assert "85mm" in cafe(lens="").image_prompt()


@pytest.mark.parametrize("term", ["8k", "ultra realistic", "masterpiece",
                                  "highly detailed", "professional", "photorealistic"])
def test_quality_adjectives_are_stripped(term):
    """These push a model toward its average of stock and CGI renders — the
    plastic look people mean by 'looks AI-generated'. Higgsfield's own docs
    recommend several of them."""
    assert term.lower() not in clean(f"a cup of coffee, {term}, on a table").lower()


def test_the_diff_is_reportable_as_teaching_content():
    cleaned, removed = diff("a cup of coffee, 8k, ultra realistic, masterpiece")
    assert set(removed) >= {"8k", "ultra realistic", "masterpiece"}
    assert "coffee" in cleaned


def test_clean_leaves_real_specification_alone():
    spec = "close-up of a cup, 85mm lens at f/2.0, shot on Kodak Portra 400"
    assert clean(spec) == spec


def test_video_requires_exactly_one_camera_move():
    with pytest.raises(ShotError, match="camera move"):
        cafe().video_prompt()
    assert "slow push-in" in cafe(camera_move="slow push-in").video_prompt()


def test_video_beats_are_capped():
    """Two or three beats per five seconds. More and the model rushes them."""
    with pytest.raises(ShotError, match="3 beats"):
        cafe(camera_move="slow push-in",
             beats=("a", "b", "c", "d")).video_prompt()


def test_video_prompt_does_not_restate_a_still_frame():
    p = cafe(camera_move="slow push-in", beats=("steam rises", "hand enters frame")).video_prompt()
    assert "real-time motion" in p
    assert "steam rises | hand enters frame" in p


def test_every_banned_term_has_a_word_boundary_match():
    """Guards against a substring rule silently mangling legitimate words."""
    assert clean("a 4k monitor on the desk") != "a 4k monitor on the desk"
    assert "darkroom" in clean("a darkroom with red light")


# --- output format, fixed by founder direction 2026-08-14 -------------------

def test_frames_default_to_16_9():
    """Consistent across the channel rather than per-request."""
    from app.media.shots import DEFAULT_ASPECT
    assert DEFAULT_ASPECT == "16:9"
    assert "16:9" in cafe().image_prompt()


def test_negative_space_defaults_to_a_side_third():
    """A 16:9 frame has horizontal room and almost no vertical headroom, so
    reserving the top third would leave type nowhere usable to sit."""
    assert "left third" in cafe().image_prompt()


def test_resolutions_are_pinned():
    from app.media.shots import IMAGE_RESOLUTION, VIDEO_RESOLUTION
    assert IMAGE_RESOLUTION == "2k"
    assert VIDEO_RESOLUTION == "720p"


def test_the_cinematic_rules_are_documented():
    """These were learned by shipping a forgettable image first. Keeping them in
    code rather than in a chat log is the point."""
    from app.media.shots import CINEMATIC
    for key in ("one_source", "someone_working", "skin_as_surface",
                "locally_legible", "depth_in_three_layers"):
        assert key in CINEMATIC and len(CINEMATIC[key]) > 40
