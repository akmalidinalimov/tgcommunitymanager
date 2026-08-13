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


NUMBER = re.compile(r"(?<![\w])[\d]+(?:[.,]\d+)?\s*(?:%|ming|mln|million|so'm|soʻm|\$|usd)?", re.IGNORECASE)


def unsupported_numbers(text: str, ledger: set[str]) -> list[str]:
    """Numbers in ``text`` that do not appear in the claims ledger.

    The strongest guardrail in the system precisely because it is a schema check
    and not a model's opinion: if the ledger has no row, the number does not ship.
    Years and small counts inside a sentence are still flagged — the writer must
    justify every figure rather than the linter guessing which ones matter.
    """
    found = {m.group(0).strip() for m in NUMBER.finditer(text) if m.group(0).strip()}
    normalized_ledger = {c.strip().lower() for c in ledger}
    return sorted(
        n for n in found
        if n.lower() not in normalized_ledger
        and re.sub(r"[^\d]", "", n) not in {re.sub(r"[^\d]", "", c) for c in normalized_ledger}
    )
