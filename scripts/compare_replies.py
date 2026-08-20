"""Run the same real comments through two models and print the Uzbek side by side.

    python scripts/compare_replies.py
    python scripts/compare_replies.py --models claude-opus-5 gpt-5.6-luna gpt-5.6-sol
    python scripts/compare_replies.py --comment "Bu bepulmi?"

Nothing is sent anywhere. This exists because "which model writes better casual
Uzbek" is not a question anyone can answer from a spec sheet, and switching the
Replier blind means finding out in front of 3,326 people.

The mechanical column is not a quality score. It counts the tells the linter can
see — a `-moqda`, a banned construction, a second sentence, a closing offer. A
model can pass every one of them and still sound like a textbook, which is why
the drafts are printed in full for a human to read. It is the reverse that the
counter is for: a draft with three tells does not need reading.
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

from app.agents.context import ReplyContext, build_context  # noqa: E402
from app.agents.llm import ProviderError, provider_for  # noqa: E402
from app.agents.replier import Draft, draft_reply  # noqa: E402
from app.config import Settings  # noqa: E402
from app.telegram.classifier import Kind  # noqa: E402
from app.text.lint import blockers, lint  # noqa: E402

CORPUS = Path(__file__).resolve().parent.parent / "data" / "corpus" / "updates-606-raw.json"
THREAD_ROOT = 3

#: Comment register, from .claude/skills/humanize-uz §4. These are the habits
#: that scored 0/3 in the blind test — every one of them a way of being *too
#: complete*, which is the failure mode of a helpful assistant, not of a person
#: typing into a comment box.
OFFERS = (
    "savolingiz bo", "yozing", "murojaat qil", "bemalol", "yordam bera",
    "batafsil ma", "quyidagi",
)
GREETINGS = ("salom", "assalom", "hurmatli", "yaxshi savol", "rahmat, ")


def register_tells(text: str) -> list[str]:
    """Comment-register problems the post linter does not look for."""
    out: list[str] = []
    stripped = text.strip()
    lowered = stripped.lower()

    sentences = [s for s in stripped.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    if len(sentences) > 1:
        out.append(f"{len(sentences)} sentences (comment register is one)")

    words = len(stripped.split())
    if words > 12:
        out.append(f"{words} words (over 12)")

    for phrase in OFFERS:
        if phrase in lowered:
            out.append(f"closing offer: {phrase!r}")
            break
    for phrase in GREETINGS:
        if lowered.startswith(phrase):
            out.append(f"greeting: {phrase!r}")
            break

    emoji = sum(1 for ch in stripped if ord(ch) > 0x2500)
    if emoji > 1:
        out.append(f"{emoji} emoji (0 or 1, at the end)")
    return out


def one(ctx: ReplyContext, model: str, settings: Settings) -> tuple[str, Draft | None, str]:
    try:
        draft = draft_reply(
            ctx,
            api_key=settings.anthropic_api_key or "",
            openai_key=settings.openai_api_key or "",
            model=model,
        )
    except ProviderError as exc:
        return model, None, str(exc)
    except Exception as exc:  # a vendor outage must not lose the other column
        return model, None, f"{type(exc).__name__}: {exc}"
    return model, draft, ""


def show(model: str, draft: Draft | None, error: str) -> None:
    print(f"  ── {model} " + "─" * max(0, 58 - len(model)))
    if draft is None:
        print(f"     unavailable: {error}")
        return
    if not draft.is_reply:
        print(f"     escalated: {draft.needs_from_founders or draft.reasoning}")
        return

    print(f"     {draft.draft}")
    tells = [str(i) for i in blockers(lint(draft.draft))] + register_tells(draft.draft)
    print(f"     grounded: {', '.join(draft.grounded_on) or '—'}")
    if tells:
        for tell in tells:
            print(f"     ✗ {tell}")
    else:
        print("     ✓ no mechanical tells")


def ad_hoc(text: str) -> ReplyContext:
    from app.agents.context import ThreadMessage
    from app.text.script import detect_script

    return ReplyContext(
        target=ThreadMessage(message_id=1, author="Test", author_id=1, text=text, kind=Kind.HUMAN),
        thread_root_id=THREAD_ROOT,
        post_text="(ad-hoc question, no post context)",
        history=[],
        script=detect_script(text),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=["claude-opus-5", "gpt-5.6-luna"])
    parser.add_argument("--comment", help="ask one question instead of replaying the corpus")
    parser.add_argument("--limit", type=int, default=0, help="only the first N corpus comments")
    args = parser.parse_args()

    settings = Settings.load()

    # Say up front which columns cannot run. Discovering it one draft at a time
    # reads as a model failing when it is a key that was never set.
    for model in args.models:
        try:
            which = provider_for(model)
        except ProviderError as exc:
            print(f"! {exc}")
            return 1
        key = settings.anthropic_api_key if which == "anthropic" else settings.openai_api_key
        if not key:
            var = "ANTHROPIC_API_KEY" if which == "anthropic" else "OPENAI_API_KEY"
            print(f"! {model} needs {var} in .env — that column will be blank")

    if args.comment:
        targets = [ad_hoc(args.comment)]
    else:
        if not CORPUS.is_file():
            print(f"corpus not found at {CORPUS}")
            return 1
        updates = json.loads(CORPUS.read_text(encoding="utf-8"))
        messages = [u["message"] for u in updates if "message" in u]
        bot = int(settings.bot_token.split(":")[0])
        targets = [
            ctx for m in messages
            if (ctx := build_context(
                m["message_id"], messages, bot_id=bot,
                channel_id=settings.channel_id, thread_root_id=THREAD_ROOT,
            )).should_reply
        ]
        if args.limit:
            targets = targets[: args.limit]

    print(f"\n{len(targets)} comment(s) × {len(args.models)} model(s). Nothing is sent.\n")

    for ctx in targets:
        print("=" * 66)
        print(f"[{ctx.target.message_id}] {ctx.target.author} ({ctx.script.value})")
        print(f"  asked: {ctx.target.text or '(video, no caption)'}")
        for model in args.models:
            show(*one(ctx, model, settings))
        print()

    print("=" * 66)
    print("Read them. The counter finds tells; only you can hear the register.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
