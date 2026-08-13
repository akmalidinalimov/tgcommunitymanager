"""Auto-forward matching, tested without the network.

The rule these lock down: the group-side message id is unrelated to the
channel-side one, so ``forward_origin.message_id`` is the only valid match key.
"""

from __future__ import annotations

from app.telegram.publisher import find_thread_root

CHANNEL_ID = -1002708742288
GROUP_ID = -1004430366406
OTHER_CHANNEL_ID = -1009999999999
BOT_ID = 8662504476


def forward_update(update_id: int, *, group_msg_id: int, origin_msg_id: int,
                   origin_chat_id: int = CHANNEL_ID, chat_id: int = GROUP_ID) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": group_msg_id,
            "chat": {"id": chat_id, "type": "supergroup"},
            "from": {"id": 777000, "is_bot": False, "first_name": "Telegram"},
            "sender_chat": {"id": origin_chat_id, "type": "channel"},
            "is_automatic_forward": True,
            "forward_origin": {
                "type": "channel",
                "chat": {"id": origin_chat_id, "type": "channel"},
                "message_id": origin_msg_id,
            },
            "message_thread_id": group_msg_id,
            "text": "post body",
        },
    }


def find(updates, channel_message_id=42):
    return find_thread_root(
        updates,
        channel_message_id=channel_message_id,
        group_id=GROUP_ID,
        channel_id=CHANNEL_ID,
        bot_id=BOT_ID,
    )


def test_matches_on_forward_origin_not_on_message_id():
    """Group id 5001 vs channel id 42: unrelated numbers, matched via origin."""
    assert find([forward_update(1, group_msg_id=5001, origin_msg_id=42)]) == 5001


def test_ignores_a_forward_of_a_different_post():
    """Two posts published close together must not cross-seed each other."""
    assert find([forward_update(1, group_msg_id=5001, origin_msg_id=41)]) is None


def test_picks_ours_out_of_a_busy_batch():
    updates = [
        forward_update(1, group_msg_id=5001, origin_msg_id=40),
        {
            "update_id": 2,
            "message": {
                "message_id": 5002,
                "chat": {"id": GROUP_ID, "type": "supergroup"},
                "from": {"id": 777000, "is_bot": False},
                "pinned_message": {"message_id": 5001},
            },
        },
        {
            "update_id": 3,
            "message": {
                "message_id": 5003,
                "chat": {"id": GROUP_ID, "type": "supergroup"},
                "from": {"id": 555, "is_bot": False, "first_name": "Aziza"},
                "text": "salom",
            },
        },
        forward_update(4, group_msg_id=5004, origin_msg_id=42),
    ]
    assert find(updates) == 5004


def test_ignores_forwards_into_a_different_chat():
    updates = [forward_update(1, group_msg_id=5001, origin_msg_id=42, chat_id=-1005555555555)]
    assert find(updates) is None


def test_ignores_a_forward_from_another_channel_with_a_colliding_id():
    """Another channel's post 42 must not be mistaken for ours."""
    updates = [forward_update(1, group_msg_id=5001, origin_msg_id=42,
                              origin_chat_id=OTHER_CHANNEL_ID)]
    assert find(updates) is None


def test_ordinary_comment_is_never_a_thread_root():
    updates = [{
        "update_id": 1,
        "message": {
            "message_id": 5010,
            "chat": {"id": GROUP_ID, "type": "supergroup"},
            "from": {"id": 555, "is_bot": False, "first_name": "Aziza"},
            "message_thread_id": 5001,
            "text": "Sinab ko'rdim",
        },
    }]
    assert find(updates) is None


def test_empty_batch():
    assert find([]) is None
