"""Configuration and the startup assertions that decide whether we may run.

Two of these assertions exist because the failure they catch is *silent*. A bot
that boots into a misconfigured chat does not crash — it publishes into the wrong
place, or goes deaf, in front of thousands of people. Refusing to start is the
cheaper outcome.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

TASHKENT = ZoneInfo("Asia/Tashkent")

#: Publishing slots, local Tashkent time. Uzbekistan does not observe DST, so
#: these are stable year-round.
POST_SLOTS = ((10, 0), (21, 0))


class ConfigError(RuntimeError):
    """Raised when the environment cannot support a safe run."""


def _load_dotenv(path: Path) -> list[str]:
    """Load .env, which **wins over the ambient environment**.

    Deliberately not ``setdefault``. A stray ``TELEGRAM_BOT_TOKEN`` left in the
    machine's environment by another project silently beat this project's .env
    and pointed at a different bot entirely. On a developer machine the ambient
    environment is untrusted leftovers; the file checked into the project
    directory is the declared intent.

    Returns the names of variables whose ambient value was overridden, so the
    caller can say so out loud rather than swapping credentials silently.
    """
    overridden: list[str] = []
    if not path.is_file():
        return overridden
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key in os.environ and os.environ[key] != value:
            overridden.append(key)
        os.environ[key] = value
    return overridden


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"{name} is not set. Add it to .env at the repository root "
            f"(.env is git-ignored and must never be committed)."
        )
    return value


@dataclass(frozen=True)
class Settings:
    bot_token: str
    bot_username: str
    channel_id: int
    discussion_group_id: int
    channel_username: str
    anthropic_api_key: str | None
    #: Where drafts, escalations and approvals are delivered.
    admin_chat_id: int | None = None
    #: Telegram user ids permitted to approve. Anyone else is ignored.
    approver_ids: tuple[int, ...] = ()

    #: Names whose ambient environment value was overridden by .env.
    overridden_env: tuple[str, ...] = ()

    @classmethod
    def load(cls, root: Path | None = None) -> "Settings":
        root = root or Path(__file__).resolve().parent.parent
        overridden = tuple(_load_dotenv(root / ".env"))
        if overridden:
            print(
                f"note: .env overrode ambient environment for {', '.join(overridden)}",
                flush=True,
            )
        return cls(
            overridden_env=overridden,
            bot_token=_required("TELEGRAM_BOT_TOKEN"),
            bot_username=os.environ.get("TELEGRAM_BOT_USERNAME", "").lstrip("@"),
            channel_id=int(_required("TELEGRAM_CHANNEL_ID")),
            discussion_group_id=int(_required("TELEGRAM_DISCUSSION_GROUP_ID")),
            channel_username=os.environ.get("TELEGRAM_CHANNEL_USERNAME", "").lstrip("@"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
            admin_chat_id=int(os.environ["TELEGRAM_ADMIN_CHAT_ID"])
            if os.environ.get("TELEGRAM_ADMIN_CHAT_ID") else None,
            approver_ids=tuple(
                int(x) for x in os.environ.get("TELEGRAM_APPROVER_IDS", "").split(",") if x.strip()
            ),
        )


def check_resources(root: Path | None = None) -> list[tuple[str, bool, str]]:
    """Assert the read-only content the agents depend on is actually readable.

    These are read at runtime, so a missing or empty file degrades output
    silently instead of crashing: the Replier answers from model memory rather
    than the knowledge base, and an unapproved slot publishes nothing.

    This exists because it happened. The compose file mounted a volume over
    /app/data, which SHADOWED the knowledge base and backup pool baked into the
    image. Every check passed, the bot looked healthy, and the grounding gate was
    guarding an empty file.
    """
    root = root or Path(__file__).resolve().parent.parent
    checks: list[tuple[str, bool, str]] = []

    voice = root / ".claude" / "skills" / "humanize-uz" / "SKILL.md"
    ok = voice.is_file() and voice.stat().st_size > 500
    checks.append((
        "voice guide readable", ok,
        f"{voice.stat().st_size} bytes" if voice.is_file() else f"MISSING at {voice}",
    ))

    knowledge = root / "data" / "knowledge" / "models.yaml"
    models = 0
    if knowledge.is_file():
        import yaml

        models = len((yaml.safe_load(knowledge.read_text(encoding="utf-8")) or {}).get("models") or {})
    checks.append((
        "knowledge base has models", models > 0,
        f"{models} models" if models else
        f"EMPTY OR MISSING at {knowledge} — the grounding gate would be guarding nothing",
    ))

    pool = root / "data" / "backup_pool.yaml"
    posts = 0
    if pool.is_file():
        import yaml

        posts = len((yaml.safe_load(pool.read_text(encoding="utf-8")) or {}).get("posts") or [])
    checks.append((
        "backup pool has posts", posts >= 3,
        f"{posts} posts" if posts >= 3 else
        f"only {posts} at {pool} — an unapproved slot would publish nothing",
    ))
    return checks


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    checks: list[tuple[str, bool, str]]

    def failures(self) -> list[tuple[str, bool, str]]:
        return [c for c in self.checks if not c[1]]

    def report(self) -> str:
        lines = []
        for name, passed, detail in self.checks:
            lines.append(f"  [{'ok' if passed else 'FAIL'}] {name}: {detail}")
        return "\n".join(lines)


def preflight(me: dict, channel: dict, group: dict, channel_member: dict, group_member: dict,
              settings: Settings) -> PreflightResult:
    """Validate live chat state. Pure, so it is testable without the network.

    Callers fetch getMe / getChat / getChatMember and pass the raw results in.
    """
    checks: list[tuple[str, bool, str]] = list(check_resources())

    # Token identity. A stray TELEGRAM_BOT_TOKEN in the machine environment once
    # loaded a completely different bot here. Publishing to 3,326 people under
    # the wrong identity is unrecoverable, so the token must prove it belongs to
    # the bot this project declares.
    if settings.bot_username:
        actual = (me.get("username") or "").lstrip("@")
        expected = settings.bot_username.lstrip("@")
        same = actual.lower() == expected.lower()
        checks.append((
            "token belongs to the configured bot", same,
            f"@{actual}" if same
            else f"token is for @{actual} but TELEGRAM_BOT_USERNAME says @{expected}",
        ))

    # Privacy mode. Without this the bot receives only messages mentioning it,
    # so the comment section is invisible and nothing appears broken.
    can_read = bool(me.get("can_read_all_group_messages"))
    checks.append((
        "privacy mode disabled", can_read,
        "bot sees all group messages" if can_read
        else "BotFather /setprivacy -> Disable, then REMOVE AND RE-ADD the bot to the group",
    ))

    # Forum mode. With Topics on, comments arrive carrying no thread information
    # and no error flag whatsoever. Everything looks fine and nothing works.
    is_forum = bool(group.get("is_forum"))
    checks.append((
        "discussion group is not a forum", not is_forum,
        "topics off" if not is_forum
        else "Topics is ON — comments arrive with no thread data and no error. Disable it.",
    ))

    # The linked group must be the one we think it is, or we seed comments into
    # a chat that has nothing to do with the posts.
    linked = channel.get("linked_chat_id")
    matches = linked == settings.discussion_group_id
    checks.append((
        "channel's linked group matches config", matches,
        f"linked_chat_id={linked}" if matches
        else f"channel links to {linked} but config says {settings.discussion_group_id}",
    ))

    ch_admin = channel_member.get("status") == "administrator"
    can_post = bool(channel_member.get("can_post_messages"))
    checks.append((
        "bot is channel admin able to post", ch_admin and can_post,
        "administrator with can_post_messages" if ch_admin and can_post
        else f"status={channel_member.get('status')} can_post={can_post}",
    ))

    gr_admin = group_member.get("status") == "administrator"
    checks.append((
        "bot is discussion-group admin", gr_admin,
        "administrator" if gr_admin else f"status={group_member.get('status')}",
    ))

    return PreflightResult(ok=all(c[1] for c in checks), checks=checks)
