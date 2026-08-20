"""Score a drafted reply against what that comment is supposed to produce.

Until now the answer to "is this model good enough" was someone reading three
replies and saying they looked fine. That does not survive a vendor swap, a
silent model update, or an edit to the voice guide — none of which fail loudly.
Replies would just get quietly worse, in a language the founders read and the
audience is 3,326 people.

**Decisions are scored, wording is not.** There is no correct sentence for
"Promp boyicha qldim", and asserting one would fail every time a model phrased
something differently but well — an eval that cries wolf gets switched off. What
is objective is whether the bot answered or escalated, whether it cited the
knowledge base, whether it mirrored the member's script, and whether it said
something it is not allowed to say.

Everything here is pure. The model call happens in `scripts/eval_replies.py`, so
the scoring can be tested without a network or an account.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.text.script import Script, detect_script

DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "evals" / "replies.yaml"


@dataclass(frozen=True)
class Forbidden:
    pattern: str
    reason: str


@dataclass(frozen=True)
class Case:
    id: str
    text: str
    expect: str = "either"
    """reply | escalate | either."""
    script: str = ""
    grounded_any: tuple[str, ...] = ()
    forbid: tuple[Forbidden, ...] = ()
    why: str = ""


@dataclass
class Result:
    case: Case
    action: str
    draft: str
    grounded_on: tuple[str, ...] = ()
    failures: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def passed(self) -> bool:
        return not self.failures and not self.error


def load(path: Path | None = None) -> list[Case]:
    import yaml

    source = path or DEFAULT_PATH
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    cases: list[Case] = []
    for entry in data.get("cases") or []:
        cases.append(Case(
            id=entry["id"],
            text=(entry.get("text") or "").strip(),
            expect=entry.get("expect", "either"),
            script=entry.get("script", ""),
            grounded_any=tuple(entry.get("grounded_any") or ()),
            forbid=tuple(
                Forbidden(pattern=f["pattern"], reason=f.get("reason", ""))
                for f in entry.get("forbid") or []
            ),
            why=(entry.get("why") or "").strip(),
        ))
    return cases


def satisfies(cited: tuple[str, ...], required: tuple[str, ...]) -> bool:
    """Does any cited key answer any required one, allowing for depth?

    Knowledge keys are hierarchical. A case asking for `our_posts.606` is asking
    "did you read the post record", and `our_posts.606.referenced_video.made_with`
    is a *more* precise answer to that, not a wrong one. Exact set intersection
    failed gpt-5.6-sol for citing its source too specifically — the eval
    punishing better behaviour, which is the worst thing an eval can do.

    One-directional, like the script rule: a citation deeper than the requirement
    counts, a shallower one does not. Asking for `models.kling3_0` and getting
    `models` back is not evidence that the right entry was read.
    """
    return any(
        c == r or c.startswith(f"{r}.")
        for c in cited for r in required
    )


def score(case: Case, *, action: str, draft: str,
          grounded_on: tuple[str, ...] = ()) -> Result:
    """Check one drafted reply against one case. Empty failures means it passed."""
    result = Result(case=case, action=action, draft=draft, grounded_on=tuple(grounded_on))
    replied = action == "reply" and bool(draft.strip())

    if case.expect == "reply" and not replied:
        result.failures.append(f"expected a reply, got {action}")
    elif case.expect == "escalate" and replied:
        # The dangerous direction. An escalation that should have been a reply
        # costs a founder a minute; a reply that should have escalated is a
        # guess published to the channel.
        result.failures.append("expected an escalation, it answered")

    # Everything below inspects the draft, so a case that correctly escalated
    # has nothing left to check — there is no text to be wrong.
    if not replied:
        return result

    if case.script:
        got = detect_script(draft)
        want = Script.CYRILLIC if case.script == "cyrillic" else Script.LATIN
        # UNKNOWN is emoji, digits or a bare link. It mirrors nothing and
        # accusing it of the wrong script would be a false alarm.
        if got is not Script.UNKNOWN and got is not want:
            result.failures.append(f"replied in {got.value}, member wrote {case.script}")

    if case.grounded_any and not satisfies(grounded_on, case.grounded_any):
        result.failures.append(
            f"cited {', '.join(grounded_on) or 'nothing'}; "
            f"needed one of {', '.join(case.grounded_any)}"
        )

    for rule in case.forbid:
        if re.search(rule.pattern, draft):
            result.failures.append(f"{rule.reason.strip()} — matched /{rule.pattern}/")

    return result


@dataclass
class Report:
    model: str
    results: list[Result]

    def by_case(self) -> dict[str, list[Result]]:
        """Every attempt at each case, in fixture order."""
        grouped: dict[str, list[Result]] = {}
        for r in self.results:
            grouped.setdefault(r.case.id, []).append(r)
        return grouped

    @property
    def passed(self) -> int:
        """Cases that passed EVERY attempt.

        Not the raw attempt count. A case that passes two runs in three is not
        two-thirds safe — it is a case that publishes something wrong roughly
        every third time it comes up, in front of 3,326 people. Averaging it
        into a percentage hides exactly the thing worth seeing.
        """
        return sum(1 for rs in self.by_case().values() if all(r.passed for r in rs))

    @property
    def total(self) -> int:
        return len(self.by_case())

    @property
    def ok(self) -> bool:
        return self.total > 0 and self.passed == self.total

    @property
    def trials(self) -> int:
        grouped = self.by_case()
        return max((len(v) for v in grouped.values()), default=0)

    def line(self) -> str:
        suffix = f" (×{self.trials} trials)" if self.trials > 1 else ""
        return f"{self.model}: {self.passed}/{self.total} cases clean{suffix}"
