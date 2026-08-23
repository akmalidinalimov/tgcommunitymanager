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
