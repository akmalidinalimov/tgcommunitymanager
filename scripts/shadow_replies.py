"""Shadow mode: draft replies to the real thread and show them, sending nothing.

    python scripts/shadow_replies.py            # print drafts locally
    python scripts/shadow_replies.py --to-admin # also deliver cards to the admin chat

Nothing is ever posted to the discussion group by this script. Every draft is
either printed or delivered to the founders for judgement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.context import build_context  # noqa: E402
from app.agents.replier import draft_reply, dump, to_admin_card  # noqa: E402
from app.config import Settings  # noqa: E402
from app.telegram.api import BotAPI  # noqa: E402

CORPUS = Path(__file__).resolve().parent.parent / "data" / "corpus" / "updates-606-raw.json"
THREAD_ROOT = 3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--to-admin", action="store_true",
                        help="deliver the cards to the admin chat")
    args = parser.parse_args()

    settings = Settings.load()
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY missing from .env")
        return 1
    if not CORPUS.is_file():
        print(f"corpus not found at {CORPUS}")
        return 1

    updates = json.loads(CORPUS.read_text(encoding="utf-8"))
    messages = [u["message"] for u in updates if "message" in u]
    bot = settings.bot_token.split(":")[0]

    targets = []
    for m in messages:
        ctx = build_context(
            m["message_id"], messages,
            bot_id=int(bot), channel_id=settings.channel_id, thread_root_id=THREAD_ROOT,
        )
        if ctx.should_reply:
            targets.append(ctx)

    print(f"{len(messages)} messages in thread · {len(targets)} selected for reply\n")

    api = BotAPI(settings.bot_token) if args.to_admin else None
    sent_in_thread: list[str] = []
    try:
        for ctx in targets:
            draft = draft_reply(
                ctx,
                api_key=settings.anthropic_api_key,
                previous_drafts=sent_in_thread,
            )
            if draft.is_reply:
                sent_in_thread.append(draft.draft)
            print("=" * 66)
            print(f"[{ctx.target.message_id}] {ctx.target.author} ({ctx.script.value})")
            print(f"  asked : {ctx.target.text or '(video, no caption)'}")
            print(f"  action: {draft.action}")
            if draft.is_reply:
                print(f"  DRAFT : {draft.draft}")
                print(f"  ground: {', '.join(draft.grounded_on) or '—'}")
            else:
                print(f"  needs : {draft.needs_from_founders}")
            print(f"  why   : {draft.reasoning}")

            if api and settings.admin_chat_id:
                api.send_message(settings.admin_chat_id, to_admin_card(ctx, draft),
                                 parse_mode="HTML")
            print(dump(ctx, draft))
        print("=" * 66)
        if args.to_admin:
            print("cards delivered to the admin chat. Nothing was posted to the group.")
        else:
            print("dry run. Nothing sent anywhere.")
    finally:
        if api:
            api.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
