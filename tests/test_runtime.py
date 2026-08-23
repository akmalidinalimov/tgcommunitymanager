"""Runtime routing and the disclosure obligation, with a fake Telegram."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agents.replier import AI_DISCLOSURE, with_disclosure
from app.config import Settings
from types import SimpleNamespace

from app.runtime import MAX_REDRAFTS, Runtime, kind_for
from app.spine import approval
from app.spine.scheduler import Slot
from app.telegram.api import TelegramError
from app.spine.states import Content, State
from app.spine.store import Store

TASHKENT = ZoneInfo("Asia/Tashkent")
CHANNEL, GROUP, BOT, ADMIN = -1002708742288, -1004430366406, 8662504476, 6542876935

SETTINGS = Settings(
    bot_token="1:x", bot_username="malikamanager_bot", channel_id=CHANNEL,
    discussion_group_id=GROUP, channel_username="aicreatorsuz",
    anthropic_api_key="k", admin_chat_id=ADMIN, approver_ids=(ADMIN,),
)


class FakeAPI:
    """Records calls instead of making them."""

    def __init__(self):
        self.sent, self.reactions, self.answered, self.edits = [], [], [], []
        self._next_id = 500

    def send_message(self, chat_id, text, **kw):
        self._next_id += 1
        # Record the id Telegram would have assigned: the escalation link is
        # keyed on it, so a fake that drops it cannot exercise the relay.
        self.sent.append({"chat_id": chat_id, "text": text,
                          "message_id": self._next_id, **kw})
        return {"message_id": self._next_id}

    def upload_photo(self, chat_id, image, **kw):
        self._next_id += 1
        self.sent.append({"chat_id": chat_id, "media": "<rendered card>",
                          "media_kind": "card", "card_bytes": len(image),
                          "message_id": self._next_id,
                          "text": kw.get("caption") or "", **kw})
        return {"message_id": self._next_id}

    def send_media_group(self, chat_id, images, **kw):
        """An album. Returns a LIST, as Telegram does — a caller expecting a
        dict here is the bug this shape exists to expose."""
        self._next_id += 1
        first = self._next_id
        self.sent.append({"chat_id": chat_id, "media": f"<album of {len(images)}>",
                          "media_kind": "album", "album_size": len(images),
                          "message_id": first, "text": kw.get("caption") or "", **kw})
        self._next_id += len(images) - 1
        return [{"message_id": first + i} for i in range(len(images))]

    def send_photo(self, chat_id, photo, **kw):
        return self._media(chat_id, photo, "photo", **kw)

    def send_video(self, chat_id, video, **kw):
        return self._media(chat_id, video, "video", **kw)

    def _media(self, chat_id, url, kind, **kw):
        self._next_id += 1
        self.sent.append({"chat_id": chat_id, "media": url, "media_kind": kind,
                          "message_id": self._next_id,
                          "text": kw.get("caption") or "", **kw})
        return {"message_id": self._next_id}

    def set_message_reaction(self, chat_id, message_id, emoji, **kw):
        self.reactions.append((chat_id, message_id, emoji))
        return True

    def answer_callback_query(self, cid, text=None, **kw):
        self.answered.append((cid, text))
        return True

    def edit_message_text(self, chat_id, message_id, text, **kw):
        self.edits.append((chat_id, message_id, text))
        return {}

    def get_updates(self, **kw):
        return []


@pytest.fixture
def rt(tmp_path):
    return Runtime(settings=SETTINGS, store=Store(tmp_path / "t.db"),
                   api=FakeAPI(), bot_id=BOT)


def auto_forward(group_msg_id=3, channel_msg_id=606):
    return {"update_id": 1, "message": {
        "message_id": group_msg_id,
        "chat": {"id": GROUP, "type": "supergroup"},
        "from": {"id": 777000, "is_bot": False, "first_name": "Telegram"},
        "is_automatic_forward": True,
        "forward_origin": {"type": "channel", "chat": {"id": CHANNEL},
                           "message_id": channel_msg_id},
        "text": "post body",
    }}


# --- AI Act disclosure ------------------------------------------------------


def test_first_reply_in_a_thread_carries_the_ai_disclosure():
    """EU AI Act Art. 50, applicable since 2 August 2026, for a Sweden-based
    operator. A member scrolling straight into a thread must still be told."""
    out = with_disclosure("Kling 3.0 da sinab koʻring", first_in_thread=True)
    assert out.endswith(AI_DISCLOSURE)


def test_later_replies_do_not_repeat_it():
    """The obligation is that the member is told, not told repeatedly."""
    assert with_disclosure("Ha, shunaqa", first_in_thread=False) == "Ha, shunaqa"


def test_disclosure_is_not_duplicated_if_already_present():
    text = f"Javob\n\n{AI_DISCLOSURE}"
    assert with_disclosure(text, first_in_thread=True).count(AI_DISCLOSURE) == 1


def test_empty_draft_gets_no_disclosure():
    assert with_disclosure("", first_in_thread=True) == ""


# --- routing ----------------------------------------------------------------


def test_auto_forward_is_persisted_immediately(rt):
    """Telegram announces this once and drops updates after 24h. Losing it before
    it is written loses the thread permanently."""
    rt.handle_update(auto_forward())
    assert rt.store.root_for_post(606) == 3
    assert rt.store.known_roots() == {3}


def test_the_bot_does_not_reply_to_the_thread_root(rt):
    rt.handle_update(auto_forward())
    assert rt.api.sent == []


def test_service_messages_are_ignored(rt):
    rt.handle_update({"update_id": 2, "message": {
        "message_id": 4, "chat": {"id": GROUP, "type": "supergroup"},
        "from": {"id": 777000, "is_bot": False},
        "pinned_message": {"message_id": 3},
    }})
    assert rt.api.sent == [] and rt.store.known_roots() == set()


def test_messages_from_other_chats_are_ignored(rt):
    rt.handle_update({"update_id": 3, "message": {
        "message_id": 9, "chat": {"id": -1009999999, "type": "supergroup"},
        "from": {"id": 42, "is_bot": False, "first_name": "X"}, "text": "salom",
    }})
    assert rt.api.sent == []


def test_member_media_gets_a_reaction_not_a_message(rt):
    rt.handle_update(auto_forward())
    rt.handle_update({"update_id": 4, "message": {
        "message_id": 11, "chat": {"id": GROUP, "type": "supergroup"},
        "from": {"id": 8454060495, "is_bot": False, "first_name": "Euro work"},
        "message_thread_id": 3, "video": {"file_id": "v"},
    }})
    assert rt.api.reactions == [(GROUP, 11, "🔥")]
    assert rt.api.sent == []
    assert rt.store.artifacts_posted() == 1


def test_a_comment_is_only_handled_once(rt):
    """A replayed update must not produce a second reply to the same person."""
    rt.handle_update(auto_forward())
    comment = {"update_id": 5, "message": {
        "message_id": 12, "chat": {"id": GROUP, "type": "supergroup"},
        "from": {"id": 555, "is_bot": False, "first_name": "A"},
        "message_thread_id": 3, "video": {"file_id": "v"},
    }}
    rt.handle_update(comment)
    rt.handle_update(comment)
    assert len(rt.api.reactions) == 1


# --- approval callbacks -----------------------------------------------------


def pending_content(store, slot_key):
    c = Content(slot_key=slot_key, kind="technique", text="tayyor post")
    c.submit_for_approval()
    store.save_content(c)
    return c


def callback(slot_key, user_id=ADMIN, action="ok"):
    return {"callback_query": {
        "id": "cb1", "from": {"id": user_id}, "data": f"{action}:{slot_key}",
        "message": {"message_id": 77, "chat": {"id": ADMIN}},
    }}


def test_approving_schedules_the_content(rt):
    pending_content(rt.store, "2026-08-14_10:00")
    rt.handle_update(callback("2026-08-14_10:00"))
    assert rt.store.get_content("2026-08-14_10:00").state is State.SCHEDULED
    assert rt.api.answered and rt.api.edits


def test_a_stranger_pressing_approve_changes_nothing(rt):
    pending_content(rt.store, "2026-08-14_10:00")
    rt.handle_update(callback("2026-08-14_10:00", user_id=999))
    assert rt.store.get_content("2026-08-14_10:00").state is State.PENDING_APPROVAL
    assert rt.api.edits == []


def test_every_press_is_answered_even_when_refused(rt):
    """An unanswered callback spins forever on the approver's phone."""
    rt.handle_update(callback("nonexistent"))
    assert len(rt.api.answered) == 1


# --- publishing -------------------------------------------------------------


def test_unapproved_slot_publishes_a_backup_not_the_draft(rt, monkeypatch):
    # Pinned to no asset: this asserts publish behaviour, not media selection,
    # and it silently inverted once when a matching asset was added.
    monkeypatch.setattr("app.runtime.pick_asset", lambda kind, used=None: None)
    rt.store.add_backup("evergreen post")
    c = pending_content(rt.store, "2026-08-14_10:00")
    rt.publish_slot(Slot(datetime(2026, 8, 14, 10, 0, tzinfo=TASHKENT)))
    assert rt.api.sent[0]["text"] == "evergreen post"
    assert rt.store.get_content(c.slot_key).state is State.EXPIRED


def test_approved_slot_publishes_the_approved_text(rt, monkeypatch):
    monkeypatch.setattr("app.runtime.pick_asset", lambda kind, used=None: None)
    c = pending_content(rt.store, "2026-08-14_10:00")
    c.approve(ADMIN, (ADMIN,), at=datetime(2026, 8, 13, 20, 0, tzinfo=TASHKENT))
    c.schedule()
    rt.store.save_content(c)
    rt.publish_slot(Slot(datetime(2026, 8, 14, 10, 0, tzinfo=TASHKENT)))
    assert rt.api.sent[0]["text"] == "tayyor post"
    assert rt.store.get_content(c.slot_key).state is State.PUBLISHED


def test_empty_backup_pool_stays_silent_rather_than_publishing_unapproved(rt):
    """The pool being empty is an operational failure, but publishing something
    a human never approved would be a worse one."""
    pending_content(rt.store, "2026-08-14_10:00")
    rt.publish_slot(Slot(datetime(2026, 8, 14, 10, 0, tzinfo=TASHKENT)))
    assert [s for s in rt.api.sent if s["chat_id"] == CHANNEL] == []
    assert any("jim qoldi" in s["text"] for s in rt.api.sent), "silence went unreported"


# --- the weekly grid --------------------------------------------------------


def test_the_grid_covers_every_slot_of_the_week():
    for weekday in range(7):
        for hour in (10, 21):
            slot = Slot(datetime(2026, 8, 10 + weekday, hour, 0, tzinfo=TASHKENT))
            assert kind_for(slot)


def test_monday_morning_is_a_technique_post():
    assert kind_for(Slot(datetime(2026, 8, 10, 10, 0, tzinfo=TASHKENT))) == "technique"


# --- the first live deployment's failure, encoded ---------------------------

import time as _time  # noqa: E402

from app.runtime import MAX_REPLIES_PER_THREAD_PER_RUN  # noqa: E402


class BacklogAPI(FakeAPI):
    """Telegram handing over a queue of hours-old updates, as on first boot."""

    def __init__(self, updates):
        super().__init__()
        self._updates = updates
        self.get_updates_calls = []

    def get_updates(self, **kw):
        self.get_updates_calls.append(kw)
        if kw.get("offset") == -1:
            return self._updates[-1:]
        return self._updates


def old_comment(mid, uid, text, age_s=6 * 3600):
    return {"update_id": mid, "message": {
        "message_id": mid, "date": int(_time.time() - age_s),
        "chat": {"id": GROUP, "type": "supergroup"},
        "from": {"id": uid, "is_bot": False, "first_name": f"M{uid}"},
        "message_thread_id": 3, "text": text,
    }}


def test_cold_start_skips_the_queued_backlog(tmp_path):
    """The first deployment drained 20 hours-old updates and answered a whole
    stale thread in 30 seconds. A cold start now establishes an offset and
    discards the queue."""
    updates = [old_comment(i, 500 + i, f"savol {i}") for i in range(5, 12)]
    rt = Runtime(settings=SETTINGS, store=Store(tmp_path / "cold.db"),
                 api=BacklogAPI(updates), bot_id=BOT)
    handled = rt.drain_updates()
    assert handled == 0
    assert rt.api.sent == []
    assert rt.store.get_runtime("update_offset") == str(updates[-1]["update_id"] + 1)


def test_old_messages_are_recorded_but_never_answered(rt):
    rt.handle_update(auto_forward())
    rt.handle_update(old_comment(50, 999, "eski savol?"))
    assert rt.api.sent == []
    assert rt.store.seen_comment(50)


def test_a_thread_cannot_receive_more_than_the_per_run_cap(rt, monkeypatch):
    """However large the backlog, a bad run costs two odd replies, not eight."""
    rt.handle_update(auto_forward())
    rt._replied_this_run[3] = MAX_REPLIES_PER_THREAD_PER_RUN
    rt.handle_update({"update_id": 60, "message": {
        "message_id": 60, "date": int(_time.time()),
        "chat": {"id": GROUP, "type": "supergroup"},
        "from": {"id": 777, "is_bot": False, "first_name": "X"},
        "message_thread_id": 3, "text": "Bu qanday ishlaydi?",
    }})
    assert rt.api.sent == []


def test_already_answered_is_detected_from_the_batch_on_an_empty_store(rt):
    """The rule that failed live. Storage was empty, so the founders' answer was
    invisible and the bot talked over it. Siblings now come from the batch too."""
    rt.handle_update(auto_forward())
    question = {"message_id": 5, "date": int(_time.time()),
                "chat": {"id": GROUP, "type": "supergroup"},
                "from": {"id": 2399190, "is_bot": False, "first_name": "Kamoliddin"},
                "message_thread_id": 3, "text": "Qaysi AIdan foydalaniladi?"}
    founder_answer = {"message_id": 7, "date": int(_time.time()),
                      "chat": {"id": GROUP, "type": "supergroup"},
                      "from": {"id": 1087968824, "is_bot": True, "first_name": "Group"},
                      "sender_chat": {"id": GROUP, "type": "supergroup"},
                      "message_thread_id": 3, "reply_to_message": {"message_id": 5},
                      "text": "Seedance 2.5 yoki Kling 3.0"}
    rt.handle_comment(question, [question, founder_answer])
    assert rt.api.sent == []


# --- media attachment -------------------------------------------------------

class MediaAPI(FakeAPI):
    def __init__(self, fail_media=False):
        super().__init__()
        self.videos = []
        self._fail = fail_media

    def send_video(self, chat_id, video, *, caption=None, **kw):
        if self._fail:
            from app.telegram.api import TelegramError
            raise TelegramError("sendVideo", "wrong file identifier")
        self._next_id += 1
        self.videos.append({"url": video, "caption": caption})
        return {"message_id": self._next_id}


def approved_with_media(store, slot_key, asset_id, text="post matni"):
    c = Content(slot_key=slot_key, kind="commercial_craft", text=text)
    c.attach_media(asset_id)
    c.submit_for_approval()
    c.approve(ADMIN, (ADMIN,), at=datetime(2026, 8, 13, 20, 0, tzinfo=TASHKENT))
    c.schedule()
    store.save_content(c)
    return c


def approved(store, slot_key, text="post matni"):
    c = Content(slot_key=slot_key, kind="commercial_craft", text=text)
    c.submit_for_approval()
    c.approve(ADMIN, (ADMIN,), at=datetime(2026, 8, 13, 20, 0, tzinfo=TASHKENT))
    c.schedule()
    store.save_content(c)
    return c


def test_an_expired_media_url_does_not_cost_the_slot(tmp_path):
    """Higgsfield CDN URLs expire. A dead link must degrade to a text post, not
    to a missed slot."""
    rt = Runtime(settings=SETTINGS, store=Store(tmp_path / "m.db"),
                 api=MediaAPI(fail_media=True), bot_id=BOT)
    rt.store.add_backup("evergreen")
    approved(rt.store, "2026-08-10_21:00")
    rt.publish_slot(Slot(datetime(2026, 8, 10, 21, 0, tzinfo=TASHKENT)))
    assert rt.api.sent, "slot was lost when media failed"
    assert rt.api.sent[0]["text"] == "post matni"


def test_a_post_with_no_matching_asset_still_publishes(rt, monkeypatch):
    """A slot is never lost for want of a visual. Pinned to an empty library so
    the assertion does not silently invert when a matching asset is added — an
    earlier version broke exactly that way."""
    monkeypatch.setattr("app.runtime.pick_asset", lambda kind, used=None: None)
    approved(rt.store, "2026-08-16_21:00")
    rt.publish_slot(Slot(datetime(2026, 8, 16, 21, 0, tzinfo=TASHKENT)))
    assert rt.api.sent[0]["text"] == "post matni"


def _clip():
    from app.media.library import Asset
    return Asset(id="clip", url="https://cdn/x.mp4", kind="video",
                 good_for=("commercial_craft",), duration=5)


def test_a_post_with_a_matching_asset_ships_as_a_caption(tmp_path, monkeypatch):
    """Founder direction: every post carries a visual. The text becomes the
    caption rather than a separate message."""
    api = MediaAPI()
    rt = Runtime(settings=SETTINGS, store=Store(tmp_path / "v.db"), api=api, bot_id=BOT)
    monkeypatch.setattr("app.runtime.asset_by_id", lambda aid, **k: _clip())

    c = approved_with_media(rt.store, "2026-08-10_21:00", "clip")
    rt.publish_slot(Slot(datetime(2026, 8, 10, 21, 0, tzinfo=TASHKENT)))

    assert api.videos and api.videos[0]["caption"] == "post matni"
    assert api.sent == [], "text was sent separately instead of as a caption"
    assert c.media_paths == ["clip"]


def test_approved_content_publishes_the_visual_it_was_approved_with(rt, monkeypatch):
    """The asset used to be chosen at publish time, so what shipped was not what
    anyone said yes to. Approved content now publishes its bound asset and
    nothing else."""
    monkeypatch.setattr("app.runtime.asset_by_id", lambda aid, **k: _clip())
    monkeypatch.setattr("app.runtime.pick_asset",
                        lambda kind, used=None: pytest.fail(
                            "approved content must not re-pick its visual"))
    approved_with_media(rt.store, "2026-08-10_21:00", "clip")
    rt.publish_slot(Slot(datetime(2026, 8, 10, 21, 0, tzinfo=TASHKENT)))
    assert rt.api.sent[0]["media"] == "https://cdn/x.mp4"


def test_the_approval_card_carries_the_visual_and_the_buttons(rt, monkeypatch):
    """The founders were approving captions with no idea what image would go
    out. The card is now the post itself: visual, caption under it, buttons."""
    monkeypatch.setattr("app.runtime.asset_by_id", lambda aid, **k: _clip())
    c = Content(slot_key="2026-08-16_21:00", kind="commercial_craft", text="matn")
    c.attach_media("clip")
    c.submit_for_approval()
    rt.store.save_content(c)

    rt._send_for_approval(c, Slot(datetime(2026, 8, 16, 21, 0, tzinfo=TASHKENT)))

    card = rt.api.sent[0]
    assert card["media"] == "https://cdn/x.mp4"
    assert "matn" in card["text"], "the post text must ride as the caption"
    assert card.get("reply_markup"), "the card lost its approve/revise buttons"


# --- rejected drafts must not poison their slot ----------------------------

def test_a_rejected_draft_does_not_block_its_slot_forever(rt, monkeypatch):
    """The check was "does content exist" rather than "is it still viable", so
    one bad draft — produced while the knowledge base was missing — meant that
    slot silently never produced an approval card again. No card, no error, no
    log line."""
    from app.runtime import MAX_REDRAFTS
    from app.spine.scheduler import slots_needing_approval

    monkeypatch.setattr("app.runtime.load_planned", lambda: {})
    slot = slots_needing_approval()[0]
    dead = Content(slot_key=slot.key, kind="technique", text="bad")
    dead.reject("critic never passed it")
    rt.store.save_content(dead)

    drafted = []
    import app.runtime as mod
    original = mod.write_post
    mod.write_post = lambda kind, **kw: drafted.append(kind) or _ok_post(kind)
    try:
        rt.prepare_upcoming()
    finally:
        mod.write_post = original
    assert drafted, "a rejected slot was skipped instead of redrafted"


def test_redrafting_is_bounded(rt, monkeypatch):
    """A genuinely impossible brief must not burn tokens every fifteen minutes."""
    from app.runtime import MAX_REDRAFTS
    from app.spine.scheduler import slots_needing_approval

    monkeypatch.setattr("app.runtime.load_planned", lambda: {})
    slot = slots_needing_approval()[0]
    dead = Content(slot_key=slot.key, kind="technique", text="bad")
    dead.reject("nope")
    rt.store.save_content(dead)
    rt.store.set_runtime(f"redraft:{slot.key}", str(MAX_REDRAFTS))

    drafted = []
    import app.runtime as mod
    original = mod.write_post
    mod.write_post = lambda kind, **kw: drafted.append(kind) or _ok_post(kind)
    try:
        rt.prepare_upcoming()
    finally:
        mod.write_post = original
    assert slot.key not in [c for c in drafted], "exhausted slot was redrafted again"


def _ok_post(kind):
    from app.agents.writer import Post
    p = Post(text="yangi post", seed_comment="savol?", kind=kind)
    p.critic_passed = True
    return p


# --- a silent slot must never be silent to the founders ---------------------
#
# The 2026-08-14 10:00 slot published nothing and nobody noticed for hours,
# because a missed slot produced no signal anywhere. These pin the two ways a
# slot can go quiet.


def test_failing_slot_alerts_and_does_not_block_the_next_one(rt, monkeypatch):
    from app.spine.scheduler import Slot, TASHKENT
    import datetime

    a = Slot(datetime.datetime(2026, 8, 14, 10, 0, tzinfo=TASHKENT))
    b = Slot(datetime.datetime(2026, 8, 14, 21, 0, tzinfo=TASHKENT))
    done = []

    def flaky(slot):
        if slot.key == a.key:
            raise RuntimeError("send_photo blew up")
        done.append(slot.key)

    monkeypatch.setattr(rt, "publish_slot", flaky)
    monkeypatch.setattr("app.runtime.due_slots", lambda *_, **__: ([a, b], []))
    rt.publish_due()

    assert done == [b.key], "a failing slot must not take the next slot down"
    assert rt.store.last_seen is not None, "last_seen must advance despite failure"
    assert any("chiqmadi" in s["text"] for s in rt.api.sent), "founders were not told"


# --- approval cards must actually arrive ------------------------------------
#
# Cards stopped reaching the founders on 2026-08-14 and no slot recovered on its
# own: the state was committed before the send, and the guard in
# prepare_upcoming skips anything not REJECTED, so a card that failed to send
# was never retried.


class RefusingAPI(FakeAPI):
    """Telegram rejecting the card, the way a parse-entities error does."""

    def __init__(self, fail_times=1):
        super().__init__()
        self.left = fail_times

    def send_message(self, chat_id, text, **kw):
        if self.left and kw.get("reply_markup"):
            self.left -= 1
            raise TelegramError("sendMessage", "Bad Request: can't parse entities")
        return super().send_message(chat_id, text, **kw)


def test_a_card_that_fails_to_send_is_retried_not_lost(rt):
    rt.api = RefusingAPI(fail_times=1)
    c = pending_content(rt.store, "2026-08-14_21:00")
    slot = Slot(datetime(2026, 8, 14, 21, 0, tzinfo=TASHKENT))

    assert rt._send_for_approval(c, slot) is False
    assert rt.store.get_runtime("card_sent:2026-08-14_21:00") is None, (
        "a failed send must not be recorded as delivered")

    assert rt._send_for_approval(c, slot) is True
    assert rt.store.get_runtime("card_sent:2026-08-14_21:00")


def test_pending_slot_with_no_delivered_card_gets_one_on_the_next_pass(rt, monkeypatch):
    """The exact shape of the outage: content is PENDING_APPROVAL, no card ever
    reached anyone, and drafting is skipped because the slot is not REJECTED."""
    slot = Slot(datetime(2026, 8, 14, 21, 0, tzinfo=TASHKENT))
    pending_content(rt.store, slot.key)
    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [slot])
    monkeypatch.setattr("app.runtime.write_post",
                        lambda *a, **k: pytest.fail("must not redraft an approved-pending slot"))

    rt.prepare_upcoming()
    assert any(s.get("reply_markup") for s in rt.api.sent), "card was not resent"


def test_post_text_with_html_characters_does_not_break_the_card():
    """Model-written text goes into a parse_mode=HTML message. One '<' used to
    make Telegram reject the card, permanently orphaning that slot."""
    c = Content(slot_key="2026-08-14_21:00", kind="technique",
                text="Prompt: <lighting> & 2 > 1")
    body = approval.card(c, Slot(datetime(2026, 8, 14, 21, 0, tzinfo=TASHKENT)))
    assert "<lighting>" not in body
    assert "&lt;lighting&gt;" in body and "&amp;" in body


def test_pending_digest_resends_every_waiting_card(rt):
    for key in ("2026-08-15_10:00", "2026-08-14_21:00"):
        pending_content(rt.store, key)

    assert rt.send_pending_digest() == 2
    cards = [s for s in rt.api.sent if s.get("reply_markup")]
    assert len(cards) == 2
    assert "21:00" in cards[0]["text"], "earliest deadline first"


def test_pending_command_from_the_approver_pulls_the_queue(rt):
    pending_content(rt.store, "2026-08-14_21:00")
    rt.handle_update({"update_id": 9, "message": {
        "message_id": 1, "chat": {"id": ADMIN, "type": "private"},
        "from": {"id": ADMIN, "is_bot": False}, "text": "/pending"}})
    assert any(s.get("reply_markup") for s in rt.api.sent)


def test_pending_command_from_a_stranger_is_ignored(rt):
    pending_content(rt.store, "2026-08-14_21:00")
    rt.handle_update({"update_id": 9, "message": {
        "message_id": 1, "chat": {"id": ADMIN, "type": "private"},
        "from": {"id": 4242, "is_bot": False}, "text": "/pending"}})
    assert rt.api.sent == []


# --- the revise button must produce a revision ------------------------------


def test_asking_for_a_rewrite_actually_redrafts_the_slot(rt, monkeypatch):
    """✏️ Qayta yozish moves content to DRAFTING. prepare_upcoming skipped
    anything that was not REJECTED, so pressing it silently killed the slot —
    no rewrite, no card, and the backup pool covered for it. Observed live on
    2026-08-15_10:00."""
    slot = Slot(datetime(2026, 8, 15, 10, 0, tzinfo=TASHKENT))
    pending_content(rt.store, slot.key)

    rt.handle_update(callback(slot.key, action="rv"))
    assert rt.store.get_content(slot.key).state is State.DRAFTING

    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [slot])
    monkeypatch.setattr("app.runtime.write_post",
                        lambda kind, **k: SimpleNamespace(
                            ok=True, text="qayta yozilgan post", kind=kind, problem="", seed_comment=""))

    rt.prepare_upcoming()
    assert rt.store.get_content(slot.key).state is State.PENDING_APPROVAL
    assert rt.store.get_content(slot.key).text == "qayta yozilgan post"


def test_a_rewrite_loop_is_bounded_by_max_redrafts(rt, monkeypatch):
    slot = Slot(datetime(2026, 8, 15, 10, 0, tzinfo=TASHKENT))
    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [slot])
    calls = []
    monkeypatch.setattr("app.runtime.write_post",
                        lambda kind, **k: (calls.append(kind), SimpleNamespace(
                            ok=False, text="yomon", kind=kind, problem="lint", seed_comment=""))[1])

    for _ in range(MAX_REDRAFTS + 3):
        rt.prepare_upcoming()

    assert len(calls) == MAX_REDRAFTS + 1, "redrafting must not burn tokens forever"


def test_resending_binds_a_visual_to_a_card_drafted_without_one(rt, monkeypatch):
    """Everything already queued was written when the asset was chosen at publish
    time, so it carries none. Resending those as bare text would reproduce the
    exact problem being fixed."""
    monkeypatch.setattr("app.runtime.pick_asset", lambda kind, used=None: _clip())
    monkeypatch.setattr("app.runtime.asset_by_id", lambda aid, **k: _clip())
    c = Content(slot_key="2026-08-16_21:00", kind="commercial_craft", text="matn")
    c.submit_for_approval()
    rt.store.save_content(c)
    assert c.media_paths == []

    rt.send_pending_digest()

    assert rt.store.get_content("2026-08-16_21:00").media_paths == ["clip"]
    assert any(s.get("media") for s in rt.api.sent), "resent card still had no visual"


def test_every_button_press_is_logged(rt, caplog):
    """A press decides what reaches 3,326 people. Content state appears only in
    the boot dump, so without this the only way to answer "did that get
    approved" was to restart a live bot."""
    import logging

    pending_content(rt.store, "2026-08-18_21:00")
    with caplog.at_level(logging.INFO, logger="runtime"):
        rt.handle_update(callback("2026-08-18_21:00"))

    line = " ".join(r.message for r in caplog.records)
    assert "approval:" in line
    assert "2026-08-18_21:00" in line
    assert str(ADMIN) in line
    assert "scheduled" in line


def test_a_refused_press_is_logged_too(rt, caplog):
    import logging

    pending_content(rt.store, "2026-08-18_21:00")
    with caplog.at_level(logging.INFO, logger="runtime"):
        rt.handle_update(callback("2026-08-18_21:00", user_id=4242))

    assert "approval refused" in " ".join(r.message for r in caplog.records)
