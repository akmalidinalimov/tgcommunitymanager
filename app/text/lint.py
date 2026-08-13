"""Mechanical checks on generated Uzbek, before any model judges it.

Much of what makes Uzbek read as machine-written is a fixed list: bookish verb
forms, officialese nouns, words this account has never once used. Those are
decidable by string matching, so they are decided here — deterministically,
identically every time, at no token cost.

The LLM critic then handles only what genuinely needs judgement: whether the
thing sounds translated, whether the hook earns attention.

The banned table is parsed from the voice guide at runtime, exactly as the
founders' own pipeline does, so editing the guide changes what is enforced and
the two cannot drift apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.text.orthography import has_wrong_apostrophes

VOICE_PATH = Path(__file__).resolve().parent.parent.parent / ".claude" / "skills" / "humanize-uz" / "SKILL.md"

#: Zero occurrences across the founders' entire corpus. Plausible Uzbek this
#: account does not use, so their appearance means the text came from a grammar
#: book rather than from a person.
NEVER_ATTESTED = ("xullas", "demak", "ya'ni", "yaʼni", "qarang", "aytmoqchi", "biroq", "shuningdek")

#: The bookish present continuous. One of these makes a sentence sound read off
#: a screen, and it is the single fastest way to sound like a machine.
MOQDA = re.compile(r"\w+moqda\b", re.IGNORECASE)

#: Addressing the reader informally. The register is `siz`, always.
SEN = re.compile(r"(?<![\w'ʼʻ])sen(?![\w'ʼʻ])", re.IGNORECASE)

#: Section-announcing scaffolding — English newsletter structure wearing Uzbek
#: words. Native prose does not announce its own sections.
SCAFFOLDING = (
    "ilgari qanday edi", "nimasi muhim", "nima uchun muhim",
    "keling, ko'rib chiqamiz", "keling, koʻrib chiqamiz", "xulosa qilib aytganda",
)


#: Telegram caps a photo/video caption at 1024 characters, against 4096 for a
#: plain text message. Every post ships with media, so a post over the cap cannot
#: be sent in its intended form at all.
CAPTION_CAP = 1024

#: The working ceiling, well under the hard cap. Founder direction: posts were
#: too long to digest. Nobody reads a wall of text on a phone before they have
#: seen what the thing can do.
POST_MAX = 900

#: Where a good post lands. Long enough to teach one idea, short enough to read
#: under a video without scrolling.
POST_TARGET = 600


class Severity(str, Enum):
    BLOCKER = "blocker"
    POLISH = "polish"


@dataclass(frozen=True)
class Issue:
    severity: Severity
    rule: str
    found: str
    fix: str = ""

    def __str__(self) -> str:
        arrow = f" → {self.fix}" if self.fix else ""
        return f"[{self.severity.value}] {self.rule}: {self.found!r}{arrow}"


def load_banned_table(path: Path | None = None) -> dict[str, str]:
    """Parse the banned-construction table out of the voice guide.

    Reading it from the guide rather than duplicating it means a human editing
    the guide changes what the linter enforces, and the two cannot drift.
    """
    source = path or VOICE_PATH
    if not source.is_file():
        return {}

    banned: dict[str, str] = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.count("|") < 3:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        left, right = cells[0], cells[1]
        if not left.startswith("`") or left.lower().startswith("`never"):
            continue
        for term in re.findall(r"`([^`]+)`", left):
            if term.strip() in {"–", "—", "-"}:
                continue
            replacement = ", ".join(re.findall(r"`([^`]+)`", right)) or right
            banned[term.strip().lower()] = replacement
    return banned


def lint(text: str, *, banned: dict[str, str] | None = None) -> list[Issue]:
    """Return every mechanical problem in ``text``. Empty means it passed."""
    issues: list[Issue] = []
    table = banned if banned is not None else load_banned_table()
    lowered = text.lower()

    for match in MOQDA.finditer(text):
        issues.append(Issue(
            Severity.BLOCKER, "bookish -moqda form", match.group(0),
            match.group(0).lower().replace("moqda", "yapti"),
        ))

    if SEN.search(text):
        issues.append(Issue(Severity.BLOCKER, "addresses the reader as sen", "sen", "siz"))

    for term, replacement in table.items():
        if term in lowered:
            issues.append(Issue(Severity.BLOCKER, "banned construction", term, replacement))

    for word in NEVER_ATTESTED:
        if re.search(rf"(?<![\w'ʼʻ]){re.escape(word)}(?![\w'ʼʻ])", lowered):
            issues.append(Issue(
                Severity.BLOCKER, "word this account never uses", word,
                "delete it or rewrite the sentence",
            ))

    for phrase in SCAFFOLDING:
        if phrase in lowered:
            issues.append(Issue(
                Severity.BLOCKER, "translated section scaffolding", phrase,
                "state the thing instead of announcing it",
            ))

    length = len(text)
    if length > CAPTION_CAP:
        issues.append(Issue(
            Severity.BLOCKER, "over Telegram's caption cap", f"{length} chars",
            f"cut to under {POST_TARGET}; it cannot be sent as a caption at all",
        ))
    elif length > POST_MAX:
        issues.append(Issue(
            Severity.BLOCKER, "too long to digest", f"{length} chars",
            f"cut to under {POST_TARGET}",
        ))

    if has_wrong_apostrophes(text):
        issues.append(Issue(
            Severity.POLISH, "apostrophes not normalized", "'",
            "render through normalize_apostrophes()",
        ))

    return issues


def blockers(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity is Severity.BLOCKER]


def passes(text: str, *, banned: dict[str, str] | None = None) -> bool:
    return not blockers(lint(text, banned=banned))


#: A *claim* is a number asserting a result, a price, or how many people did
#: something. Those are the ones that carry legal and credibility risk and must
#: trace to a ledger row.
#:
#: A technical number is not a claim. "10 soniyalik video", "720p", "Kling 3.0"
#: describe the work rather than assert an outcome, and treating them as claims
#: blocks perfectly good posts forever — which is worse than useless, because a
#: guardrail that fires on everything gets switched off.
CLAIM_NUMBER = re.compile(
    r"""(?<![\w.])
        (\d[\d\s.,]*)                       # the figure
        \s*
        (?:ta|nafar|kishilik)?              # Uzbek counter: "5000 ta o'quvchi"
        \s*
        (%|\$|usd|eur|so['ʼʻ]?m|ming|mln|million|milliard
         |odam|kishi|o['ʼʻ]?quvchi|mijoz|obunachi|talaba|bitiruvchi
         |barobar|baravar|foiz|marta\s+ko['ʼʻ]?p)
        """,
    re.IGNORECASE | re.VERBOSE,
)

#: Money or scale stated before the unit — "$1500", "1500 dollar".
CURRENCY_FIRST = re.compile(r"[$€]\s?\d[\d\s.,]*", re.IGNORECASE)


def unsupported_numbers(text: str, ledger: set[str]) -> list[str]:
    """Claim-shaped numbers with no backing row.

    A schema check rather than a model's opinion, which is what makes it the most
    reliable guardrail in the system. Deliberately scoped to claims — earnings,
    prices, headcounts, multiples — and not to every digit in the text.
    """
    found = {m.group(0).strip() for m in CLAIM_NUMBER.finditer(text)}
    found |= {m.group(0).strip() for m in CURRENCY_FIRST.finditer(text)}

    def digits(value: str) -> str:
        return re.sub(r"[^\d]", "", value)

    ledger_digits = {digits(c) for c in ledger if digits(c)}
    ledger_lower = {c.strip().lower() for c in ledger}
    return sorted(
        n for n in found
        if n.lower() not in ledger_lower and digits(n) not in ledger_digits
    )
