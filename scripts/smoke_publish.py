"""M0 smoke test: publish a real post and seed the first comment inside its thread.

Proves the one thing that looks identical in code and obvious in Telegram — that
the seed lands *inside the comment thread* rather than the discussion group's
main feed.

    python scripts/smoke_publish.py           # preflight only, publishes nothing
    python scripts/smoke_publish.py --publish # actually posts to the channel
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows consoles default to cp1252, which cannot render the okina (U+02BB) this
# text is full of. Display-only concern — the bytes sent to Telegram are UTF-8
# regardless — but a crash here would look like a pipeline failure.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings, preflight  # noqa: E402
from app.telegram.api import BotAPI  # noqa: E402
from app.telegram.publisher import ForwardNotSeen, publish_and_seed  # noqa: E402
from app.text.orthography import normalize_apostrophes  # noqa: E402

POST = """Kecha videoning promptini kanalga tashlagandim.

Kim sinab ko'rdi? 👀

Natijangizni izohga tashlang — qanday chiqqanini ko'raylik.

Chiqmagan bo'lsa ham yozing. Ko'pincha muammo promptda emas, bitta sozlamada bo'ladi.

👇 Izohlarda kutaman"""

SEED = """Sinab ko'rganlar, chiqdimi? Bitta so'z bilan yozsangiz ham bo'ladi 🙂

🤖 AI yordamchi"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true",
                        help="actually post to the live channel")
    args = parser.parse_args()

    settings = Settings.load()

    with BotAPI(settings.bot_token) as api:
        me = api.get_me()
        channel = api.get_chat(settings.channel_id)
        group = api.get_chat(settings.discussion_group_id)
        result = preflight(
            me=me,
            channel=channel,
            group=group,
            channel_member=api.get_chat_member(settings.channel_id, me["id"]),
            group_member=api.get_chat_member(settings.discussion_group_id, me["id"]),
            settings=settings,
        )

        print("PREFLIGHT")
        print(result.report())
        if not result.ok:
            print("\nrefusing to publish — fix the failures above")
            return 1

        post = normalize_apostrophes(POST)
        seed = normalize_apostrophes(SEED)

        print("\nPOST (normalized, exactly as it will appear)")
        print("-" * 60)
        print(post)
        print("-" * 60)
        print("\nSEED COMMENT")
        print("-" * 60)
        print(seed)
        print("-" * 60)

        if not args.publish:
            print("\ndry run — nothing published. Re-run with --publish to send.")
            return 0

        print(f"\npublishing to {channel.get('title')} ...")
        try:
            seeded = publish_and_seed(
                api,
                channel_id=settings.channel_id,
                group_id=settings.discussion_group_id,
                bot_id=me["id"],
                text=post,
                seed_comment=seed,
            )
        except ForwardNotSeen as exc:
            print(f"\nFAILED: {exc}")
            return 1

        print("\nSUCCESS")
        print(f"  channel post id   : {seeded.channel_message_id}")
        print(f"  thread root id    : {seeded.thread_root_id}")
        print(f"  seed comment id   : {seeded.seed_comment_id}")
        print(f"  auto-forward took : {seeded.seconds_to_forward:.1f}s")
        if settings.channel_username:
            print(f"  post URL          : https://t.me/{settings.channel_username}/"
                  f"{seeded.channel_message_id}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
