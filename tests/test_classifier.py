"""Classification is proven against recorded-shape fixtures, never the live API.

Each fixture mirrors a real Bot API Message. If Telegram changes the contract,
these fail loudly here rather than in front of 3,000 members.
"""

from __future__ import annotations

import pytest

from app.telegram.classifier import (
    ANONYMOUS_ADMIN_ID,
    CHANNEL_IDENTITY_ID,
    TELEGRAM_SERVICE_ID,
    TEST_DC_IDS,
    Kind,
    classify,
    thread_key,
)

BOT_ID = 8662504476
CHANNEL_ID = -1001111111111
GROUP_ID = -1002222222222
OTHER_CHANNEL_ID = -1009999999999


def _classify(message):
    return classify(message, bot_id=BOT_ID, channel_id=CHANNEL_ID)


# --- the auto-forwarded channel post: the only link to a comment thread ------


def test_auto_forward_is_the_thread_root_and_carries_the_channel_message_id():
    msg = {
        "message_id": 5001,
        "chat": {"id": GROUP_ID, "type": "supergroup"},
        "from": {"id": TELEGRAM_SERVICE_ID, "is_bot": False, "first_name": "Telegram"},
        "sender_chat": {"id": CHANNEL_ID, "type": "channel"},
        "is_automatic_forward": True,
        "forward_origin": {
            "type": "channel",
            "chat": {"id": CHANNEL_ID, "type": "channel"},
            "message_id": 42,
        },
        "message_thread_id": 5001,
        "text": "Bir xil rasm. Ikki xil natija.",
    }
    result = _classify(msg)
    assert result.kind is Kind.THREAD_ROOT
    # 42 is the channel-side id. It bears no arithmetic relation to 5001 —
    # forward_origin is the only way to connect them.
    assert result.origin_message_id == 42
    assert not result.routes_to_agents


def test_auto_forward_from_a_different_channel_is_not_our_thread_root():
    """A linked group can receive forwards from elsewhere. Claiming one as our
    root would attach every later comment to the wrong post."""
    msg = {
        "message_id": 5002,
        "chat": {"id": GROUP_ID, "type": "supergroup"},
        "from": {"id": TELEGRAM_SERVICE_ID, "is_bot": False},
        "is_automatic_forward": True,
        "forward_origin": {
            "type": "channel",
            "chat": {"id": OTHER_CHANNEL_ID, "type": "channel"},
            "message_id": 7,
        },
    }
    assert _classify(msg).kind is Kind.SERVICE


# --- service noise ----------------------------------------------------------


def test_auto_pin_of_the_forwarded_post_is_service():
    """Every channel post produces a pin event as well as the forward. Replying
    to one would post a non-sequitur under every single post."""
    msg = {
        "message_id": 5003,
        "chat": {"id": GROUP_ID, "type": "supergroup"},
        "from": {"id": TELEGRAM_SERVICE_ID, "is_bot": False},
        "pinned_message": {"message_id": 5001, "text": "Bir xil rasm."},
    }
    assert _classify(msg).kind is Kind.SERVICE


@pytest.mark.parametrize(
    "field, value",
    [
        ("new_chat_members", [{"id": 1, "is_bot": False, "first_name": "Aziza"}]),
        ("left_chat_member", {"id": 1, "is_bot": False, "first_name": "Aziza"}),
        ("new_chat_title", "AI Creators — muhokama"),
        ("video_chat_started", {}),
        ("forum_topic_created", {"name": "General"}),
        ("boost_added", {"boost_count": 1}),
    ],
)
def test_every_service_field_is_dropped(field, value):
    msg = {
        "message_id": 5004,
        "chat": {"id": GROUP_ID, "type": "supergroup"},
        "from": {"id": 555, "is_bot": False, "first_name": "Aziza"},
        field: value,
    }
    assert _classify(msg).kind is Kind.SERVICE


def test_service_sender_without_auto_forward_is_dropped():
    msg = {
        "message_id": 5005,
        "chat": {"id": GROUP_ID, "type": "supergroup"},
        "from": {"id": TELEGRAM_SERVICE_ID, "is_bot": False, "first_name": "Telegram"},
        "text": "Telegram notification",
    }
    assert _classify(msg).kind is Kind.SERVICE


def test_our_own_message_never_triggers_a_reply():
    msg = {
        "message_id": 5006,
        "chat": {"id": GROUP_ID, "type": "supergroup"},
        "from": {"id": BOT_ID, "is_bot": True, "first_name": "Malika"},
        "text": "Menimcha birinchi kiyim do'konlari to'laydi — sizda-chi?",
    }
    assert _classify(msg).kind is Kind.OWN


# --- chat-backed senders ----------------------------------------------------


def test_anonymous_admin_is_recognised_by_sender_chat_matching_the_group():
    msg = {
        "message_id": 5007,
        "chat": {"id": GROUP_ID, "type": "supergroup"},
        "from": {"id": ANONYMOUS_ADMIN_ID, "is_bot": True, "first_name": "Group"},
        "sender_chat": {"id": GROUP_ID, "type": "supergroup"},
        "text": "Admin izohi",
    }
    result = _classify(msg)
    assert result.kind is Kind.ANONYMOUS_ADMIN
    assert result.sender_chat_id == GROUP_ID


def test_commenting_as_a_channel_exposes_no_user_id():
    """Only ban_chat_sender_chat can act on these — ban/restrict_chat_member
    have no user to target."""
    msg = {
        "message_id": 5008,
        "chat": {"id": GROUP_ID, "type": "supergroup"},
        "from": {"id": CHANNEL_IDENTITY_ID, "is_bot": True, "first_name": "Channel"},
        "sender_chat": {"id": OTHER_CHANNEL_ID, "type": "channel"},
        "text": "Zo'r",
    }
    result = _classify(msg)
    assert result.kind is Kind.CHANNEL_IDENTITY
    assert result.sender_chat_id == OTHER_CHANNEL_ID


def test_unmodelled_chat_sender_escalates_instead_of_being_treated_as_human():
    msg = {
        "message_id": 5009,
        "chat": {"id": GROUP_ID, "type": "supergroup"},
        "from": {"id": 999999999, "is_bot": True, "first_name": "Future"},
        "sender_chat": {"id": OTHER_CHANNEL_ID, "type": "channel"},
        "text": "?",
    }
    assert _classify(msg).kind is Kind.CHANNEL_IDENTITY


@pytest.mark.parametrize("canonical", [ANONYMOUS_ADMIN_ID, CHANNEL_IDENTITY_ID])
def test_test_dc_sender_ids_classify_identically(canonical):
    """Fixtures recorded against a test DC must not silently fall through to
    HUMAN, which would send an LLM reply to a synthetic sender."""
    msg = {
        "message_id": 5010,
        "chat": {"id": GROUP_ID, "type": "supergroup"},
        "from": {"id": TEST_DC_IDS[canonical], "is_bot": True},
        "sender_chat": {
            "id": GROUP_ID if canonical == ANONYMOUS_ADMIN_ID else OTHER_CHANNEL_ID,
            "type": "supergroup" if canonical == ANONYMOUS_ADMIN_ID else "channel",
        },
        "text": "x",
    }
    assert _classify(msg).kind is not Kind.HUMAN


# --- the actual audience ----------------------------------------------------


def test_ordinary_person_reaches_the_agents():
    msg = {
        "message_id": 5011,
        "chat": {"id": GROUP_ID, "type": "supergroup"},
        "from": {"id": 777888, "is_bot": False, "first_name": "Aziza"},
        "message_thread_id": 5001,
        "reply_to_message": {"message_id": 5001, "is_automatic_forward": True},
        "text": "Bu bepulmi?",
    }
    result = _classify(msg)
    assert result.kind is Kind.HUMAN
    assert result.routes_to_agents


def test_is_bot_is_never_the_filter():
    """Regression guard. Both synthetic senders carry is_bot=True while
    representing real humans; filtering on it would silence real members."""
    for synthetic in (ANONYMOUS_ADMIN_ID, CHANNEL_IDENTITY_ID):
        msg = {
            "message_id": 5012,
            "chat": {"id": GROUP_ID, "type": "supergroup"},
            "from": {"id": synthetic, "is_bot": True},
            "sender_chat": {
                "id": GROUP_ID if synthetic == ANONYMOUS_ADMIN_ID else OTHER_CHANNEL_ID,
                "type": "supergroup" if synthetic == ANONYMOUS_ADMIN_ID else "channel",
            },
            "text": "real person typed this",
        }
        assert _classify(msg).kind is not Kind.SERVICE


# --- thread resolution: where the subtle bug lives --------------------------

KNOWN_ROOTS = {5001, 6001}


def test_thread_id_matching_a_known_root_resolves():
    msg = {"message_id": 5100, "message_thread_id": 5001}
    assert thread_key(msg, known_roots=KNOWN_ROOTS) == 5001


def test_user_to_user_reply_chain_is_not_a_comment_thread():
    """The trap. Telegram sets message_thread_id on ANY supergroup reply chain.
    Trusting it blindly attaches unrelated group chatter to a post's comments."""
    msg = {"message_id": 5101, "message_thread_id": 4242}
    assert thread_key(msg, known_roots=KNOWN_ROOTS) is None


def test_reply_to_the_auto_forward_resolves_even_without_a_thread_id():
    msg = {
        "message_id": 5102,
        "reply_to_message": {"message_id": 7777, "is_automatic_forward": True},
    }
    assert thread_key(msg, known_roots=KNOWN_ROOTS) == 7777


def test_reply_to_a_known_root_resolves():
    msg = {"message_id": 5103, "reply_to_message": {"message_id": 6001}}
    assert thread_key(msg, known_roots=KNOWN_ROOTS) == 6001


def test_bare_group_message_has_no_thread():
    assert thread_key({"message_id": 5104}, known_roots=KNOWN_ROOTS) is None
