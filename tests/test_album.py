"""Two pictures in one post.

A comparison is one post with two images, not two posts. Telegram calls that a
media group, and it behaves differently enough from sendPhoto to be worth
pinning: the caption only counts on the first item, an inline keyboard is
refused outright, and the images have to be uploaded rather than linked because
a URL-fetched photo caps at 5MB while a 2K render routinely exceeds it.
"""

from __future__ import annotations

import json
import types

import pytest

from app.spine.states import Content
from app.telegram.api import BotAPI


class _Recorder:
    """Captures the multipart POST without touching the network."""

    def __init__(self):
        self.sent: dict = {}

    def post(self, url, data=None, files=None, json=None):
        self.sent = {"url": url, "data": data, "files": files, "json": json}
        return types.SimpleNamespace(
            json=lambda: {"ok": True, "result": [{"message_id": 11}, {"message_id": 12}]},
            text="",
        )


def api_with(recorder) -> BotAPI:
    api = BotAPI.__new__(BotAPI)
    api._client = recorder
    api._base = "https://api.telegram.org/botTEST/"
    return api


IMAGES = [("a.jpg", b"\xff\xd8aaa"), ("b.jpg", b"\xff\xd8bbb")]


class TestSendMediaGroup:
    def test_the_caption_rides_on_the_first_item_only(self):
        rec = _Recorder()
        api_with(rec).send_media_group(-100, IMAGES, caption="matn", parse_mode="HTML")

        media = json.loads(rec.sent["data"]["media"])
        assert media[0]["caption"] == "matn"
        assert media[0]["parse_mode"] == "HTML"
        # A caption on a later item is accepted by Telegram and then never
        # displayed, which is a silent way to lose the whole post text.
        assert "caption" not in media[1]

    def test_each_image_is_attached_not_linked(self):
        # Telegram fetches a URL itself and refuses over 5MB. The GPT half of
        # the first comparison is 6.2MB, so linking would have failed with
        # "failed to get HTTP URL content" and nothing else.
        rec = _Recorder()
        api_with(rec).send_media_group(-100, IMAGES)

        media = json.loads(rec.sent["data"]["media"])
        assert [m["media"] for m in media] == ["attach://file0", "attach://file1"]
        assert set(rec.sent["files"]) == {"file0", "file1"}
        assert rec.sent["files"]["file0"][1] == b"\xff\xd8aaa"

    def test_every_item_is_declared_a_photo(self):
        rec = _Recorder()
        api_with(rec).send_media_group(-100, IMAGES)
        assert all(m["type"] == "photo" for m in json.loads(rec.sent["data"]["media"]))

    def test_a_reply_uses_reply_parameters(self):
        # The same rule as every other send here: message_thread_id is silently
        # ignored and the post lands in the group's main feed.
        rec = _Recorder()
        api_with(rec).send_media_group(-100, IMAGES, reply_to_message_id=7)
        assert json.loads(rec.sent["data"]["reply_parameters"]) == {"message_id": 7}

    def test_no_reply_parameters_when_not_replying(self):
        rec = _Recorder()
        api_with(rec).send_media_group(-100, IMAGES)
        assert "reply_parameters" not in rec.sent["data"]

    @pytest.mark.parametrize("count", [0, 1, 11])
    def test_a_group_outside_two_to_ten_is_refused(self, count):
        # One image is a sendPhoto, not an album, and Telegram rejects both
        # ends of the range. Failing here beats failing at 21:00.
        rec = _Recorder()
        with pytest.raises(ValueError, match="2-10"):
            api_with(rec).send_media_group(-100, [("x.jpg", b"x")] * count)


class TestBindingTwoAssets:
    """media_paths was already a list, so this needed no schema change."""

    def _runtime(self):
        from app.runtime import Runtime

        return Runtime.__new__(Runtime)

    def test_two_bound_assets_become_an_album(self):
        rt = self._runtime()
        content = Content(slot_key="2026-08-24_21:00", kind="technique", text="x")
        content.attach_media("tree-portrait-gpt")
        content.attach_media("tree-portrait-nano")

        shape, ref = rt.visual(content, "technique", "x")
        assert shape == "album"
        assert [a.id for a in ref] == ["tree-portrait-gpt", "tree-portrait-nano"]

    def test_one_bound_asset_is_still_a_plain_photo(self):
        rt = self._runtime()
        content = Content(slot_key="s", kind="technique", text="x")
        content.attach_media("tree-portrait-gpt")

        shape, ref = rt.visual(content, "technique", "x")
        assert shape == "asset"
        assert ref.id == "tree-portrait-gpt"

    def test_an_unknown_id_does_not_become_a_one_item_album(self):
        # A typo'd id must degrade to the surviving asset, not to an album of
        # one, which Telegram would reject at send time.
        rt = self._runtime()
        content = Content(slot_key="s", kind="technique", text="x")
        content.attach_media("tree-portrait-gpt")
        content.attach_media("does-not-exist")

        shape, ref = rt.visual(content, "technique", "x")
        assert shape == "asset"
        assert ref.id == "tree-portrait-gpt"


class TestMondayIsWiredUp:
    """The post the founders approved, as the spine will actually read it."""

    def _monday(self):
        from app.spine.planned import load

        return load()["2026-08-24_21:00"]

    def test_it_carries_both_halves_of_the_comparison(self):
        assert self._monday().assets == ("tree-portrait-gpt", "tree-portrait-nano")

    def test_both_assets_resolve_in_the_library(self):
        from app.media.library import get

        assert all(get(i) for i in self._monday().assets)

    def test_the_caption_fits_telegrams_cap(self):
        from app.text.lint import CAPTION_CAP

        assert len(self._monday().text) <= CAPTION_CAP

    def test_it_names_the_model_that_actually_ran(self):
        # Requested nano_banana_2, the generation record said
        # nano_banana_flash. Publishing the requested name would tell 3,326
        # people the wrong model made the picture.
        from app.media.library import get

        monday = self._monday()
        assert "Nano Banana Flash" in monday.text
        assert get("tree-portrait-nano").model == "nano_banana_flash"

    def test_the_named_models_have_knowledge_base_entries(self):
        # Otherwise the Replier escalates every "which model was that" question
        # about a post that names the model in its own text.
        import yaml
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        kb = yaml.safe_load((root / "data" / "knowledge" / "models.yaml").read_text("utf-8"))
        assert {"gpt_image_2", "nano_banana_flash"} <= set(kb["models"])


class TestTheAlbumReturnShape:
    """sendMediaGroup returns a list; every other send returns a dict.

    This is the project's recurring bug wearing a new hat: `posted["message_id"]`
    on a list raises TypeError *after* the album has already reached the channel.
    The post goes out, the thread mapping is never written, the seed comment is
    never placed, and Telegram drops the auto-forward after 24h — so the comment
    thread for that post is gone permanently. Every symptom says "published".
    """

    def test_a_list_collapses_to_its_first_message(self):
        from app.runtime import anchor

        assert anchor([{"message_id": 11}, {"message_id": 12}]) == {"message_id": 11}

    def test_a_plain_dict_passes_through(self):
        from app.runtime import anchor

        assert anchor({"message_id": 9}) == {"message_id": 9}

    def test_the_anchor_is_usable_as_a_message(self):
        from app.runtime import anchor

        assert anchor([{"message_id": 11}, {"message_id": 12}])["message_id"] == 11


class TestVideoAlbums:
    """A comparison of two clips must publish as two clips.

    visual() originally filtered an album to photos only, on the reasoning that
    every case we had was two stills. The moment Tuesday bound two videos, that
    filter dropped the album to the single-asset branch and would have published
    HALF the comparison with no error anywhere — the project's recurring shape,
    a side effect succeeding while the thing that gave it meaning quietly went
    missing.
    """

    def _runtime(self):
        from app.runtime import Runtime

        return Runtime.__new__(Runtime)

    def test_two_videos_make_an_album(self):
        rt = self._runtime()
        content = Content(slot_key="2026-08-25_21:00", kind="technique", text="x")
        content.attach_media("phys-tandyr-2-0")
        content.attach_media("phys-tandyr-2-5")

        shape, ref = rt.visual(content, "technique", "x")
        assert shape == "album"
        assert [a.id for a in ref] == ["phys-tandyr-2-0", "phys-tandyr-2-5"]
        assert all(a.is_video for a in ref)

    def test_a_video_item_is_declared_video_and_typed_mp4(self):
        rec = _Recorder()
        api_with(rec).send_media_group(
            -100, [("a.mp4", b"\x00\x00moov", "video"), ("b.mp4", b"\x00\x00moof", "video")],
            caption="matn")

        media = json.loads(rec.sent["data"]["media"])
        assert [m["type"] for m in media] == ["video", "video"]
        assert rec.sent["files"]["file0"][2] == "video/mp4"

    def test_a_two_tuple_still_means_photo(self):
        # Backwards compatible: Monday's still comparison passes 2-tuples.
        rec = _Recorder()
        api_with(rec).send_media_group(-100, IMAGES)
        media = json.loads(rec.sent["data"]["media"])
        assert [m["type"] for m in media] == ["photo", "photo"]
        assert rec.sent["files"]["file0"][2] == "image/jpeg"

    def test_video_bytes_are_not_re_encoded(self):
        # fetch_image re-encodes to JPEG, which is right for a 2K still and
        # would hand Telegram a corrupted mp4. Videos must use fetch_bytes.
        import inspect

        from app import runtime

        source = inspect.getsource(runtime.Runtime._deliver)
        assert "fetch_bytes" in source
        video_line = next(l for l in source.split("\n") if "mp4" in l and "fetch" in l)
        assert "fetch_bytes" in video_line and "fetch_image" not in video_line


class TestTuesdayIsWiredUp:
    def _tuesday(self):
        from app.spine.planned import load

        return load()["2026-08-25_21:00"]

    def test_it_binds_exactly_two_clips(self):
        """Two, because a comparison of one is not a comparison.

        This used to assert the specific asset ids and broke the moment the
        founder chose different clips for the slot — the same mistake as the
        poll-card test that pinned a dated post. Assert the invariant: two
        assets, one per model, same shot. WHICH two is an editorial decision
        and not a thing tests should hold still.
        """
        assert len(self._tuesday().assets) == 2

    def test_both_clips_are_videos_in_the_library(self):
        from app.media.library import get

        assert all(get(i).is_video for i in self._tuesday().assets)

    def test_one_clip_per_model_and_matched_settings(self):
        """The comparison is meaningless if anything but the model differs.

        aspect and resolution live in the library YAML and are not loaded onto
        Asset, so they are read from source here. That is the point: the guard
        has to hold on what actually ships, not on a convenient subset.
        """
        import yaml
        from pathlib import Path

        from app.media.library import get

        a, b = (get(i) for i in self._tuesday().assets)
        assert {a.model, b.model} == {"seedance_2_0", "seedance_2_5"}
        assert a.duration == b.duration

        root = Path(__file__).resolve().parent.parent
        raw = yaml.safe_load((root / "data" / "media_library.yaml").read_text("utf-8"))
        by_id = {x["id"]: x for x in raw["assets"]}
        ra, rb = by_id[a.id], by_id[b.id]
        assert ra["aspect"] == rb["aspect"]
        assert ra["resolution"] == rb["resolution"], (
            "different resolutions would let extra pixels read as better motion"
        )

    def test_the_caption_fits_and_leads_with_a_hook(self):
        from app.text.lint import CAPTION_CAP, blockers, opening_problems

        t = self._tuesday()
        assert len(t.text) <= CAPTION_CAP
        assert not blockers(opening_problems(t.text))
