"""Preflight refuses to boot on exactly the misconfigurations that fail silently.

Every case here was observed or narrowly avoided during setup, so these are
regression tests rather than hypotheticals.
"""

from __future__ import annotations

from app.config import Settings, preflight

CHANNEL_ID = -1002708742288
GROUP_ID = -1004430366406

SETTINGS = Settings(
    bot_token="x",
    bot_username="malikamanager_bot",
    channel_id=CHANNEL_ID,
    discussion_group_id=GROUP_ID,
    channel_username="aicreatorsuz",
    anthropic_api_key=None,
)

# The live values verified on 2026-08-13.
GOOD_ME = {
    "id": 8662504476,
    "username": "malikamanager_bot",
    "can_read_all_group_messages": True,
}
GOOD_CHANNEL = {"id": CHANNEL_ID, "linked_chat_id": GROUP_ID, "title": "AI CREATORS"}
GOOD_GROUP = {"id": GROUP_ID, "title": "AI CREATORS Chat"}  # is_forum absent = off
GOOD_CH_MEMBER = {"status": "administrator", "can_post_messages": True}
GOOD_GR_MEMBER = {"status": "administrator", "can_delete_messages": True}


def run(**overrides):
    args = {
        "me": GOOD_ME,
        "channel": GOOD_CHANNEL,
        "group": GOOD_GROUP,
        "channel_member": GOOD_CH_MEMBER,
        "group_member": GOOD_GR_MEMBER,
    }
    args.update(overrides)
    return preflight(settings=SETTINGS, **args)


def test_the_real_verified_configuration_passes():
    result = run()
    assert result.ok, result.report()


def test_privacy_mode_enabled_blocks_boot():
    """The state the bot was actually in at creation: admin everywhere, looks
    healthy, and silently receives no comments."""
    result = run(me={"id": 1, "can_read_all_group_messages": False})
    assert not result.ok
    assert any("privacy" in name for name, _, _ in result.failures())


def test_forum_mode_blocks_boot():
    """Topics on means comments carry no thread data AND no error signal."""
    result = run(group={"id": GROUP_ID, "is_forum": True})
    assert not result.ok
    assert any("forum" in name for name, _, _ in result.failures())


def test_linked_group_mismatch_blocks_boot():
    """Guards against seeding comments into an unrelated chat after someone
    relinks the channel to a different group."""
    result = run(channel={"id": CHANNEL_ID, "linked_chat_id": -1009999999999})
    assert not result.ok
    assert any("linked" in name for name, _, _ in result.failures())


def test_admin_without_post_rights_blocks_boot():
    result = run(channel_member={"status": "administrator", "can_post_messages": False})
    assert not result.ok


def test_demoted_in_discussion_group_blocks_boot():
    result = run(group_member={"status": "member"})
    assert not result.ok


def test_report_names_every_check():
    report = run().report()
    for fragment in ("privacy mode", "forum", "linked group", "channel admin", "discussion-group admin"):
        assert fragment in report


# --- token identity: the stray-ambient-token class of bug --------------------

def test_token_for_a_different_bot_blocks_boot():
    """A stray TELEGRAM_BOT_TOKEN in the machine environment once loaded bot
    8282699405 instead of the configured 8662504476. Publishing under the wrong
    identity to 3,326 people is unrecoverable, so this must never pass."""
    result = run(me=dict(GOOD_ME, username="some_other_bot"))
    assert not result.ok
    assert any("token belongs" in name for name, _, _ in result.failures())


def test_matching_token_passes():
    assert run(me=GOOD_ME).ok


def test_username_match_is_case_insensitive():
    assert run(me=dict(GOOD_ME, username="MalikaManager_Bot")).ok


# --- resource visibility: the volume-shadowing bug --------------------------

def test_resource_checks_pass_in_the_repo():
    from app.config import check_resources
    for name, ok, detail in check_resources():
        assert ok, f"{name}: {detail}"


def test_a_shadowed_knowledge_base_fails(tmp_path):
    """A volume mounted over /app/data hid the knowledge base and backup pool.
    Every other check passed, the bot looked healthy, and the grounding gate was
    guarding an empty file while the Replier answered from model memory."""
    from app.config import check_resources
    (tmp_path / ".claude/skills/humanize-uz").mkdir(parents=True)
    (tmp_path / ".claude/skills/humanize-uz/SKILL.md").write_text("x" * 600, encoding="utf-8")
    results = dict((name, ok) for name, ok, _ in check_resources(tmp_path))
    assert results["voice guide readable"]
    assert not results["knowledge base has models"]
    assert not results["backup pool has posts"]


def test_boot_refuses_when_resources_are_missing(tmp_path):
    from app.config import check_resources, preflight
    result = preflight(me=GOOD_ME, channel=GOOD_CHANNEL, group=GOOD_GROUP,
                       channel_member=GOOD_CH_MEMBER, group_member=GOOD_GR_MEMBER,
                       settings=SETTINGS)
    assert any("knowledge base" in name for name, _, _ in result.checks), \
        "resource checks are not part of preflight"
