"""Draft the next N days of posts and send them for approval.

    python scripts/prepare_days.py --days 3            # draft and print
    python scripts/prepare_days.py --days 3 --send     # also send approval cards

Drafts are stored regardless, so a run that fails partway can be resumed without
regenerating what already passed. Nothing is ever published from here.
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.writer import POST_KINDS, write_post  # noqa: E402
from app.config import Settings  # noqa: E402
from app.runtime import kind_for  # noqa: E402
from app.spine import approval  # noqa: E402
from app.spine.scheduler import now_tashkent, slots_between  # noqa: E402
from app.spine.states import Content, State  # noqa: E402
from app.spine.store import Store  # noqa: E402
from app.telegram.api import BotAPI  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--send", action="store_true", help="send approval cards")
    parser.add_argument("--db", default="data/bot.db")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    for noisy in ("httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    settings = Settings.load()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    store = Store(args.db)

    from datetime import timedelta

    now = now_tashkent()
    slots = slots_between(now, now + timedelta(days=args.days))
    print(f"{len(slots)} slots over {args.days} days\n")

    api = BotAPI(settings.bot_token) if args.send else None
    recent = [c.text for c in store.content_in_state(State.PUBLISHED)][-5:]
    ok_count = 0

    try:
        for slot in slots:
            existing = store.get_content(slot.key)
            if existing and existing.state is not State.REJECTED:
                print(f"— {slot.key} already {existing.state.value}, skipping")
                recent.append(existing.text)
                continue

            kind = kind_for(slot)
            print(f"drafting {slot.key}  ({kind}) ...", flush=True)
            post = write_post(
                kind, api_key=settings.anthropic_api_key or "",
                brief=POST_KINDS.get(kind), recent=recent,
            )

            print("=" * 68)
            print(f"{slot.key}  ·  {kind}  ·  rounds={post.rounds}  "
                  f"translationese={post.translationese}  ok={post.ok}")
            print("-" * 68)
            print(post.text or "(no text)")
            if post.seed_comment:
                print("-" * 68)
                print(f"SEED: {post.seed_comment}")
            if not post.ok:
                print(f"!! NOT PUBLISHABLE: {post.problem}")
            print("=" * 68 + "\n")

            content = Content(slot_key=slot.key, kind=kind, text=post.text)
            if post.ok:
                content.submit_for_approval()
                ok_count += 1
                recent.append(post.text)
            else:
                content.reject(post.problem)
            store.save_content(content)

            if api and post.ok and settings.admin_chat_id:
                api.send_message(
                    settings.admin_chat_id, approval.card(content, slot),
                    parse_mode="HTML", reply_markup=approval.keyboard(slot.key),
                )
    finally:
        if api:
            api.close()
        store.close()

    print(f"{ok_count}/{len(slots)} publishable"
          + (" · approval cards sent" if args.send else " · nothing sent"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
