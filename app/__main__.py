"""Process entry point.

    python -m app                # run the bot
    python -m app --preflight    # check configuration and exit
    python -m app --dry-run      # run without sending anything

Preflight runs on every start and refuses to boot on a misconfiguration that
would otherwise fail silently — privacy mode enabled, Topics on, the channel
linked to a different group, or a token for the wrong bot. Each of those leaves
a bot that looks healthy while publishing nowhere or hearing nothing.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

from app.config import ConfigError, Settings, preflight  # noqa: E402
from app.runtime import build  # noqa: E402
from app.spine.backups import seed  # noqa: E402


def run_preflight(runtime) -> bool:
    me = runtime.api.get_me()
    result = preflight(
        me=me,
        channel=runtime.api.get_chat(runtime.settings.channel_id),
        group=runtime.api.get_chat(runtime.settings.discussion_group_id),
        channel_member=runtime.api.get_chat_member(runtime.settings.channel_id, me["id"]),
        group_member=runtime.api.get_chat_member(runtime.settings.discussion_group_id, me["id"]),
        settings=runtime.settings,
    )
    print(result.report(), flush=True)
    return result.ok


def main() -> int:
    parser = argparse.ArgumentParser(prog="app")
    parser.add_argument("--preflight", action="store_true", help="check config and exit")
    parser.add_argument("--dry-run", action="store_true", help="run without sending anything")
    parser.add_argument("--db", default="state/bot.db")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # httpx logs the full request URL at INFO, and the bot token lives in the
    # Telegram URL path — so INFO logging writes the credential to stdout on
    # every single call, and on a VPS that lands in persistent container logs.
    for noisy in ("httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)

    try:
        runtime = build(db_path=args.db, dry_run=args.dry_run)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    if not run_preflight(runtime):
        print("\nrefusing to start — fix the failures above", file=sys.stderr)
        return 1
    if args.preflight:
        return 0

    # The pool ships with the image, so a fresh volume is never left without a
    # safety net. Idempotent — restarting does not duplicate anything.
    seed(runtime.store)
    if runtime.store.backup_count() == 0:
        # Not fatal, but the operator should know the safety net is missing: an
        # unapproved slot will go silent rather than falling back.
        logging.getLogger("runtime").warning(
            "backup pool is EMPTY — an unapproved slot will publish nothing"
        )

    settings: Settings = runtime.settings
    logging.getLogger("runtime").info(
        "starting: channel=%s group=%s admin=%s dry_run=%s",
        settings.channel_id, settings.discussion_group_id,
        settings.admin_chat_id, args.dry_run,
    )
    runtime.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
