"""Hand-written posts, and the seed comment that was being thrown away."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.runtime import Runtime
from app.spine.planned import PlannedPost, load
from app.spine.scheduler import Slot
from app.spine.states import Content, State
from app.spine.store import Store
from tests.test_runtime import BOT, CHANNEL, FakeAPI, GROUP, SETTINGS, TASHKENT, auto_forward


@pytest.fixture
def rt(tmp_path):
    return Runtime(settings=SETTINGS, store=Store(tmp_path / "p.db"),
                   api=FakeAPI(), bot_id=BOT)


def write_plan(tmp_path, body: str):
    p = tmp_path / "planned.yaml"
    p.write_text(body, encoding="utf-8")
    return p


# --- loading ----------------------------------------------------------------


def test_a_planned_post_is_loaded_for_its_slot(tmp_path):
    plan = write_plan(tmp_path, """
posts:
  "2026-08-17_10:00":
    kind: technique
    asset: uzum-tea-set-card
    text: |
      Bugun bitta kadr oling.
    seed_comment: |
      Prompt shu yerda.
""")
    got = load(plan)
    assert set(got) == {"2026-08-17_10:00"}
    assert got["2026-08-17_10:00"].asset == "uzum-tea-set-card"
    assert got["2026-08-17_10:00"].seed_comment.startswith("Prompt")


def test_a_planned_post_that_fails_lint_is_refused_not_published(tmp_path):
    """A hand-typed post reaches 3,326 people exactly like a generated one.
    Refusing at load means the slot falls through to the Writer instead of
    publishing something over the caption cap at 10:00 on the day."""
    plan = write_plan(tmp_path, 'posts:\n  "2026-08-17_10:00":\n    text: |\n      '
                                + ("x" * 2000) + "\n")
    assert load(plan) == {}


def test_an_empty_planned_post_is_ignored(tmp_path):
    assert load(write_plan(tmp_path, 'posts:\n  "2026-08-17_10:00":\n    text: ""\n')) == {}


def test_a_missing_file_is_not_an_error():
    assert load(__import__("pathlib").Path("nope.yaml")) == {}


def test_the_shipped_plan_is_valid():
    """The real file, so a typo in it fails here rather than in the channel."""
    for key, post in load().items():
        assert not post.problems, f"{key}: {post.problems}"
        assert post.text and post.kind


# --- using one --------------------------------------------------------------


def test_a_planned_slot_skips_the_writer(rt, monkeypatch):
    slot = Slot(datetime(2026, 8, 17, 10, 0, tzinfo=TASHKENT))
    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [slot])
    monkeypatch.setattr("app.runtime.load_planned", lambda: {
        slot.key: PlannedPost(slot_key=slot.key, kind="technique",
                              text="Rejalashtirilgan matn", seed_comment="Izoh",
                              asset="uzum-tea-set-card")})
    monkeypatch.setattr("app.runtime.write_post",
                        lambda *a, **k: pytest.fail("the Writer must not run for a planned slot"))

    rt.prepare_upcoming()

    content = rt.store.get_content(slot.key)
    assert content.text == "Rejalashtirilgan matn"
    assert content.state is State.PENDING_APPROVAL
    assert content.media_paths == ["uzum-tea-set-card"]
    assert content.seed_comment == "Izoh"


def test_an_unplanned_slot_still_uses_the_writer(rt, monkeypatch):
    slot = Slot(datetime(2026, 8, 18, 10, 0, tzinfo=TASHKENT))
    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [slot])
    monkeypatch.setattr("app.runtime.load_planned", lambda: {})
    monkeypatch.setattr("app.runtime.write_post", lambda kind, **k: SimpleNamespace(
        ok=True, text="yozilgan", kind=kind, problem="", seed_comment="izoh"))

    rt.prepare_upcoming()
    assert rt.store.get_content(slot.key).text == "yozilgan"


# --- seeding ----------------------------------------------------------------


def published(store, slot_key="2026-08-17_10:00", seed="Birinchi izoh"):
    c = Content(slot_key=slot_key, kind="technique", text="post", seed_comment=seed)
    store.save_content(c)
    store.record_thread(606, 0, slot_key=slot_key)
    return c


def test_the_seed_comment_is_posted_when_the_thread_opens(rt):
    """The auto-forward is the only moment the thread mapping exists, so it is
    the only moment the seed can be placed."""
    published(rt.store)
    rt.handle_update(auto_forward(group_msg_id=3, channel_msg_id=606))

    seeded = [s for s in rt.api.sent if s["chat_id"] == GROUP]
    assert seeded, "the thread was never seeded"
    assert "Birinchi izoh" in seeded[0]["text"]
    assert seeded[0]["reply_to_message_id"] == 3, (
        "must reply to the forwarded message — message_thread_id is ignored on send")


def test_the_seed_carries_the_ai_disclosure(rt):
    """It is the bot's first message in the thread, so Art. 50 applies."""
    from app.agents.replier import AI_DISCLOSURE

    published(rt.store)
    rt.handle_update(auto_forward(group_msg_id=3, channel_msg_id=606))
    assert AI_DISCLOSURE in [s for s in rt.api.sent if s["chat_id"] == GROUP][0]["text"]


def test_a_post_with_no_seed_comment_opens_no_thread_chatter(rt):
    published(rt.store, seed="")
    rt.handle_update(auto_forward(group_msg_id=3, channel_msg_id=606))
    assert not [s for s in rt.api.sent if s["chat_id"] == GROUP]


def test_a_forward_we_did_not_publish_is_not_seeded(rt):
    """Founders post to the channel by hand too. Those threads are not ours."""
    rt.handle_update(auto_forward(group_msg_id=3, channel_msg_id=999))
    assert not [s for s in rt.api.sent if s["chat_id"] == GROUP]


def test_the_seeded_message_id_is_recorded(rt):
    published(rt.store)
    rt.handle_update(auto_forward(group_msg_id=3, channel_msg_id=606))
    row = rt.store._conn.execute(
        "SELECT seeded_message_id FROM threads WHERE channel_message_id=606").fetchone()
    assert row["seeded_message_id"]


def test_the_seed_survives_a_restart(tmp_path):
    """It is written at draft time and read at publish time, hours apart."""
    path = tmp_path / "s.db"
    with Store(path) as s:
        s.save_content(Content(slot_key="2026-08-17_10:00", kind="technique",
                               text="post", seed_comment="saqlangan izoh"))
    with Store(path) as s:
        assert s.get_content("2026-08-17_10:00").seed_comment == "saqlangan izoh"


def test_a_planned_post_replaces_what_the_writer_already_drafted(rt, monkeypatch):
    """By the time a plan is written the Writer has usually already drafted and
    sent a card. Without this the plan silently never applies."""
    slot = Slot(datetime(2026, 8, 17, 10, 0, tzinfo=TASHKENT))
    stale = Content(slot_key=slot.key, kind="technique", text="Writer yozgan matn")
    stale.submit_for_approval()
    rt.store.save_content(stale)

    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [slot])
    monkeypatch.setattr("app.runtime.load_planned", lambda: {
        slot.key: PlannedPost(slot_key=slot.key, kind="technique",
                              text="Rejadagi matn", asset="uzum-tea-set-card")})
    monkeypatch.setattr("app.runtime.write_post",
                        lambda *a, **k: pytest.fail("must not redraft a planned slot"))

    rt.prepare_upcoming()
    assert rt.store.get_content(slot.key).text == "Rejadagi matn"


def test_an_approved_post_is_never_replaced_by_a_plan(rt, monkeypatch):
    """Approved content is immutable — what a human said yes to is what ships."""
    slot = Slot(datetime(2026, 8, 17, 10, 0, tzinfo=TASHKENT))
    c = Content(slot_key=slot.key, kind="technique", text="Tasdiqlangan matn")
    c.submit_for_approval()
    c.approve(6542876935, (6542876935,), at=datetime(2026, 8, 16, 20, 0, tzinfo=TASHKENT))
    c.schedule()
    rt.store.save_content(c)

    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [slot])
    monkeypatch.setattr("app.runtime.load_planned", lambda: {
        slot.key: PlannedPost(slot_key=slot.key, kind="technique", text="Kech keldi")})

    rt.prepare_upcoming()
    assert rt.store.get_content(slot.key).text == "Tasdiqlangan matn"


def test_a_plan_already_applied_is_not_resent_every_pass(rt, monkeypatch):
    slot = Slot(datetime(2026, 8, 17, 10, 0, tzinfo=TASHKENT))
    plan = PlannedPost(slot_key=slot.key, kind="technique", text="Bir xil matn",
                       asset="uzum-tea-set-card")
    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [slot])
    monkeypatch.setattr("app.runtime.load_planned", lambda: {slot.key: plan})

    rt.prepare_upcoming()
    first = len(rt.api.sent)
    rt.prepare_upcoming()
    assert len(rt.api.sent) == first, "the same plan was sent twice"


def test_a_planned_post_can_say_what_its_card_carries(tmp_path):
    """Without this the card is derived from the post, whose first line becomes
    the headline — right for a technique post, wrong for a poll."""
    plan = write_plan(tmp_path, """
posts:
  "2026-08-19_21:00":
    kind: poll
    asset: card
    card_text: |
      Sizni nima toʻxtatyapti?
      1  Hali oʻrganyapman
    text: |
      Menda bitta savol bor.
""")
    post = load(plan)["2026-08-19_21:00"]
    assert post.card_text.startswith("Sizni nima")
    assert post.asset == "card"


def test_the_card_uses_the_planned_card_text_not_the_post(rt, monkeypatch):
    pytest.importorskip("PIL")
    from app.spine.planned import PlannedPost

    slot_key = "2026-08-19_21:00"
    monkeypatch.setattr("app.runtime.load_planned", lambda: {
        slot_key: PlannedPost(slot_key=slot_key, kind="poll", text="Menda savol bor.",
                              asset="card", card_text="Sizni nima toʻxtatyapti?\n1  Birinchi")})
    captured = {}
    monkeypatch.setattr("app.media.cards.render_post",
                        lambda kind, text, **k: captured.setdefault("text", text) and b"" or b"x" * 2000)

    c = Content(slot_key=slot_key, kind="poll", text="Menda savol bor.")
    c.attach_media("card")
    rt.visual(c, "poll", c.text)

    assert captured["text"].startswith("Sizni nima"), "the card ignored its planned text"


def test_a_planned_card_text_renders():
    """`card_text` exists because a poll's card must carry the question rather
    than the post's first line.

    Built here rather than loaded from a dated slot. This used to pin the
    19 August poll and broke the day that post was archived — a test that fails
    when history scrolls is testing the wrong thing.
    """
    pytest.importorskip("PIL")
    from app.media import cards
    from app.spine.planned import PlannedPost

    post = PlannedPost(
        slot_key="2026-01-01_21:00", kind="poll", text="Savol matni.",
        card_text="Sizni nima toʻxtatyapti?\n1  Hali oʻrganyapman\n2  Mijoz topolmayman",
    )
    assert post.card_text, "the poll needs its own card text"
    png = cards.render_post(post.kind, post.card_text)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5000


def test_a_planned_slot_beyond_the_horizon_still_gets_its_card(rt, monkeypatch):
    """The 36-hour horizon bounds drafting cost. A planned post is already
    written, so waiting only delays the card and shortens review time."""
    from app.spine.planned import PlannedPost

    far = Slot(datetime(2026, 8, 25, 21, 0, tzinfo=TASHKENT))   # a week out
    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [])
    monkeypatch.setattr("app.runtime.now_tashkent",
                        lambda *a, **k: datetime(2026, 8, 17, 14, 0, tzinfo=TASHKENT))
    monkeypatch.setattr("app.runtime.load_planned", lambda: {
        far.key: PlannedPost(slot_key=far.key, kind="poll", text="Uzoq post",
                             asset="uzum-tea-set-card")})
    monkeypatch.setattr("app.runtime.write_post",
                        lambda *a, **k: pytest.fail("must not draft a planned slot"))

    rt.prepare_upcoming()
    assert rt.store.get_content(far.key) is not None, "the planned slot was skipped"
    assert any(s.get("reply_markup") for s in rt.api.sent), "no card was sent"


def test_a_planned_slot_in_the_past_is_not_resurrected(rt, monkeypatch):
    """Yesterday's plan entry must not produce a card today."""
    from app.spine.planned import PlannedPost

    past = Slot(datetime(2026, 8, 10, 21, 0, tzinfo=TASHKENT))
    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [])
    monkeypatch.setattr("app.runtime.now_tashkent",
                        lambda *a, **k: datetime(2026, 8, 17, 14, 0, tzinfo=TASHKENT))
    monkeypatch.setattr("app.runtime.load_planned", lambda: {
        past.key: PlannedPost(slot_key=past.key, kind="poll", text="Eski post")})

    rt.prepare_upcoming()
    assert rt.store.get_content(past.key) is None


def test_a_seed_only_edit_still_replaces_stored_content(rt, monkeypatch):
    """Editing just the first comment must reach the box.

    The override compared text alone, so changing only a seed left the stored
    copy in place and the old comment published anyway. Same shape as the
    original "a plan could not override a draft" bug, through a narrower door,
    and found the hard way: a duplicated seed was corrected in the file and
    nothing changed on the VPS.
    """
    slot = Slot(datetime(2026, 8, 17, 10, 0, tzinfo=TASHKENT))
    stored = Content(slot_key=slot.key, kind="technique", text="BIR XIL MATN",
                     seed_comment="eski izoh")
    stored.submit_for_approval()
    rt.store.save_content(stored)
    rt.store.set_runtime(f"card_sent:{slot.key}", "yes")

    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [slot])
    monkeypatch.setattr("app.runtime.load_planned", lambda: {
        slot.key: PlannedPost(slot_key=slot.key, kind="technique",
                              text="BIR XIL MATN", seed_comment="toʻgʻrilangan izoh")})
    monkeypatch.setattr("app.runtime.write_post",
                        lambda *a, **k: pytest.fail("must not redraft a planned slot"))

    rt.prepare_upcoming()

    after = rt.store.get_content(slot.key)
    assert after.seed_comment == "toʻgʻrilangan izoh"
    assert after.text == "BIR XIL MATN"


def test_an_approved_seed_is_never_replaced_by_a_plan_edit(rt, monkeypatch):
    """What a human said yes to stays said yes to, seed included."""
    slot = Slot(datetime(2026, 8, 17, 10, 0, tzinfo=TASHKENT))
    c = Content(slot_key=slot.key, kind="technique", text="BIR XIL MATN",
                seed_comment="tasdiqlangan izoh")
    c.submit_for_approval()
    c.approve(6542876935, (6542876935,), at=datetime(2026, 8, 16, 20, 0, tzinfo=TASHKENT))
    c.schedule()
    rt.store.save_content(c)

    monkeypatch.setattr("app.runtime.slots_needing_approval", lambda *a, **k: [slot])
    monkeypatch.setattr("app.runtime.load_planned", lambda: {
        slot.key: PlannedPost(slot_key=slot.key, kind="technique",
                              text="BIR XIL MATN", seed_comment="kech kelgan izoh")})

    rt.prepare_upcoming()
    assert rt.store.get_content(slot.key).seed_comment == "tasdiqlangan izoh"
