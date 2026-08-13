"""Reply decisions, tested against the real recorded thread from post 606.

Message ids and authors are the actual ones. These are the situations the bot
will meet on every post, so the decisions are locked to real evidence.
"""

from __future__ import annotations

from app.agents.context import Decision, build_context
from app.text.script import Script

BOT_ID = 8662504476
CHANNEL_ID = -1002708742288
GROUP_ID = -1004430366406
ROOT = 3
ANON_ADMIN = 1087968824


def msg(mid, uid, name, text="", reply_to=None, media=False, anon=False):
    m = {
        "message_id": mid,
        "chat": {"id": GROUP_ID, "type": "supergroup"},
        "from": {"id": ANON_ADMIN if anon else uid, "is_bot": anon, "first_name": name},
        "message_thread_id": ROOT,
    }
    if anon:
        m["sender_chat"] = {"id": GROUP_ID, "type": "supergroup"}
    if text:
        m["text"] = text
    if reply_to:
        m["reply_to_message"] = {"message_id": reply_to}
    if media:
        m["video"] = {"file_id": "x"}
    return m


ROOT_MSG = {
    "message_id": ROOT,
    "chat": {"id": GROUP_ID, "type": "supergroup"},
    "from": {"id": 777000, "is_bot": False, "first_name": "Telegram"},
    "is_automatic_forward": True,
    "forward_origin": {"type": "channel", "chat": {"id": CHANNEL_ID}, "message_id": 606},
    "text": "Kecha videoning promptini kanalga tashlagandim. Kim sinab ko'rdi?",
}

# The real thread, reconstructed.
THREAD = [
    ROOT_MSG,
    msg(5, 2399190, "Kamoliddin", "Qaysi AIdan foydalaniladi videolaga?", reply_to=ROOT),
    msg(6, 8218164792, "Abdumalik", "Omni flash (flow) ham qiberoliydimi shunaqa qib?", reply_to=ROOT),
    msg(7, None, "Group", "Seedance 2.5 yoki Kling 3.0 dan foydalanishingiz mumkin", reply_to=5, anon=True),
    msg(8, 6184382670, "Фотима", "Қандай қилганизнм хам кўрсатиб беринг", reply_to=ROOT),
    msg(11, 8454060495, "Euro work", reply_to=ROOT, media=True),
    msg(14, 6184382670, "Фотима", "қандай қилдиз", reply_to=11),
    msg(16, 8454060495, "Euro work", "Promp boyicha qldim", reply_to=14),
    msg(21, 6184382670, "Фотима", "линкини ташлаб бера оласизми", reply_to=20),
    msg(22, 8218164792, "Abdumalik", "http://Bfl.ai", reply_to=21),
    msg(23, 6184382670, "Фотима", "Рахмат", reply_to=22),
]


def ctx_for(target_id, thread=None):
    return build_context(
        target_id, thread or THREAD,
        bot_id=BOT_ID, channel_id=CHANNEL_ID, thread_root_id=ROOT,
    )


def test_open_question_gets_a_reply():
    c = ctx_for(6)
    assert c.should_reply
    assert c.script is Script.LATIN
    assert "Omni flash" in c.target.text


def test_question_a_founder_already_answered_is_skipped():
    """Kamoliddin's question was answered by the founders as anonymous admin.
    Replying again would talk over them in their own channel."""
    c = ctx_for(5)
    assert c.decision is Decision.SKIP_ALREADY_ANSWERED
    assert "founder" in c.decision_reason


def test_question_another_member_already_answered_is_skipped():
    """Abdumalik answered Фотима's link request himself. This is the behaviour
    the channel exists to produce, so the bot must not crowd it out."""
    c = ctx_for(21)
    assert c.decision is Decision.SKIP_ALREADY_ANSWERED
    assert "another member" in c.decision_reason


def test_cyrillic_member_is_answered_in_cyrillic():
    c = ctx_for(8)
    assert c.should_reply
    assert c.script is Script.CYRILLIC


def test_member_posting_their_own_video_gets_a_reaction_not_a_sentence():
    """Member-generated artifacts are the north-star metric and must never be
    ignored — but three text replies under three videos read as a machine however
    the wording is varied. A reaction is what a person actually does."""
    thread = [ROOT_MSG, msg(50, 8454060495, "Euro work", reply_to=ROOT, media=True)]
    c = ctx_for(50, thread)
    assert c.should_react
    assert not c.should_reply
    assert "generated media" in c.decision_reason


def test_video_that_sparked_a_conversation_is_left_alone():
    """Euro work's video drew a follow-up question from Фотима, and he answered
    her. That exchange between two members is exactly what the channel is for —
    the bot stays out even though the video itself is north-star behaviour."""
    c = ctx_for(11)
    assert c.decision is Decision.SKIP_ALREADY_ANSWERED
    assert "already engaging" in c.decision_reason


def test_video_with_no_caption_inherits_the_author_s_script():
    thread = THREAD + [msg(30, 6184382670, "Фотима", reply_to=ROOT, media=True)]
    c = ctx_for(30, thread)
    assert c.script is Script.CYRILLIC


def test_bare_thanks_is_not_answered():
    """Replying 'you're welcome' to every thanks is what makes a bot feel like a bot."""
    thread = [ROOT_MSG, msg(40, 6184382670, "Фотима", "Рахмат", reply_to=ROOT)]
    c = ctx_for(40, thread)
    assert c.decision is Decision.SKIP_NOT_A_QUESTION


def test_the_bot_never_answers_the_thread_root():
    c = ctx_for(ROOT)
    assert c.decision is Decision.SKIP_NOT_HUMAN


def test_context_carries_the_post_and_the_history():
    c = ctx_for(6)
    assert "promptini kanalga tashlagandim" in c.post_text
    assert any(m.author == "Kamoliddin" for m in c.history)
    assert all(m.message_id != ROOT for m in c.history)


def test_question_detected_without_a_question_mark():
    """Uzbek marks questions with -mi/-ми, and people skip punctuation on phones."""
    thread = [ROOT_MSG, msg(41, 999, "X", "Bu bepulmi", reply_to=ROOT)]
    assert ctx_for(41, thread).should_reply
    thread = [ROOT_MSG, msg(42, 999, "X", "Қанча туради", reply_to=ROOT)]
    assert ctx_for(42, thread).should_reply
