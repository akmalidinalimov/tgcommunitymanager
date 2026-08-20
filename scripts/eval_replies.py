"""Score one or more models against data/evals/replies.yaml.

    python scripts/eval_replies.py                                  # the configured model
    python scripts/eval_replies.py --models gpt-5.6-luna gpt-5.6-sol claude-opus-5
    python scripts/eval_replies.py --case price-question            # one case, verbose
    python scripts/eval_replies.py --models gpt-5.6-luna --trials 3 # sample the variance

Nothing is sent to Telegram. Every draft is scored and printed here.

This answers "is this model good enough" with a number instead of an impression,
which is what makes swapping vendors a decision rather than a leap. It is also
the thing that notices when a model changes underneath us: OpenAI and Anthropic
both ship silent updates, and a reply that quietly gets worse fails nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.context import ReplyContext, ThreadMessage  # noqa: E402
from app.agents.llm import ProviderError, provider_for  # noqa: E402
from app.agents.replier import draft_reply  # noqa: E402
from app.config import Settings  # noqa: E402
from app.evals.replies import Case, Report, Result, load, score  # noqa: E402
from app.telegram.classifier import Kind  # noqa: E402
from app.text.script import detect_script  # noqa: E402

#: The post every real case was commented under. Using the actual post rather
#: than a placeholder matters: the Replier is told to answer in the context of
#: what was published, and a blank post makes every case look ambiguous.
POST_TEXT = (
    "Kecha videoning promptini kanalga tashlagandim. Kim sinab koʻrdi? 👀 "
    "Natijangizni izohga tashlang."
)

#: The post those comments were left under, and the key its knowledge-base entry
#: is filed under. In production this comes from store.post_for_root(); the eval
#: must supply it or it tests a context the bot never actually sees.
POST_ID = 606


def context_for(case: Case) -> ReplyContext:
    return ReplyContext(
        target=ThreadMessage(message_id=1, author="Eval", author_id=1,
                             text=case.text, kind=Kind.HUMAN),
        thread_root_id=1,
        post_text=POST_TEXT,
        post_id=POST_ID,
        history=[],
        script=detect_script(case.text),
    )


def run(model: str, cases: list[Case], settings: Settings, *, trials: int = 1) -> Report:
    """Draft every case `trials` times.

    One run is an anecdote. The same model scored 11, then 9, then 10 on this
    exact fixture set in three consecutive runs — sampling, not regression. A
    single number invites a decision the evidence does not support, so a case is
    reported by how often it passes, and only a case that never fails is green.
    """
    results: list[Result] = []
    for case in cases:
        for _ in range(trials):
            try:
                draft = draft_reply(
                    context_for(case),
                    api_key=settings.anthropic_api_key or "",
                    openai_key=settings.openai_api_key or "",
                    model=model,
                )
            except Exception as exc:
                # A vendor error is not a failed case — reporting it as one
                # would blame the model for an outage. It is its own outcome.
                results.append(Result(case=case, action="error", draft="",
                                      error=f"{type(exc).__name__}: {exc}"))
                continue
            results.append(score(
                case, action=draft.action, draft=draft.draft,
                grounded_on=tuple(draft.grounded_on),
            ))
    return Report(model=model, results=results)


def show(report: Report, *, verbose: bool) -> None:
    print(f"\n{'=' * 70}\n{report.model}\n{'=' * 70}")
    for case_id, attempts in report.by_case().items():
        clean = sum(1 for a in attempts if a.passed)
        n = len(attempts)
        mark = "✓" if clean == n else ("~" if clean else "✗")
        count = f"  [{clean}/{n}]" if n > 1 else ""
        print(f"{mark} {case_id}{count}")

        for attempt in attempts:
            if attempt.error:
                print(f"    error: {attempt.error}")
                continue
            if verbose or not attempt.passed:
                print(f"    asked : {attempt.case.text[:88]}")
                print(f"    action: {attempt.action}")
                if attempt.draft:
                    print(f"    draft : {attempt.draft}")
                    print(f"    ground: {', '.join(attempt.grounded_on) or '—'}")
            for failure in attempt.failures:
                print(f"    ✗ {failure}")
    print(f"\n  {report.line()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=None,
                        help="default: whatever REPLY_MODEL/OPENAI_MODEL resolves to")
    parser.add_argument("--case", help="run one case by id, printing everything")
    parser.add_argument("--trials", type=int, default=1,
                        help="draft each case N times; a case is clean only if it "
                             "passes every attempt")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    settings = Settings.load()
    models = args.models or [settings.model]

    for model in models:
        try:
            provider_for(model)
        except ProviderError as exc:
            print(f"! {exc}")
            return 1

    cases = load()
    if args.case:
        cases = [c for c in cases if c.id == args.case]
        if not cases:
            print(f"no case with id {args.case!r}")
            return 1

    reports = [run(model, cases, settings, trials=max(1, args.trials))
               for model in models]
    for report in reports:
        show(report, verbose=args.verbose or bool(args.case))

    print(f"\n{'=' * 70}")
    for report in reports:
        print(f"  {report.line()}")

    # Non-zero when anything failed, so this can gate a vendor switch rather
    # than merely inform one.
    return 0 if all(r.ok for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
