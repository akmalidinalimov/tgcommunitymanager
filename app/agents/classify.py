"""What KIND of question is this, before asking whether we know the answer.

The grounding gate has always asked one question — is the fact in the knowledge
base — and applied the same answer to every class of question. That is right for
a price and wrong for craft technique, and it cost us a real one: a member asked
how to write a prompt for a realistic image and the bot went to the founders.

So classification comes first. A question about money or about our own work is
handled exactly as before. A question about craft may be answered from
``data/knowledge/craft.yaml``, which contains only things we tested ourselves.

**Precedence is deliberate and is the safety property.** A message can be more
than one thing at once — "zoʻr chiqibdi, qanday yozdingiz va Kling qancha
turadi?" is craft AND ours AND money. Money wins, then ours, then craft. The
riskiest reading of an ambiguous message is the one that governs, so a mixed
question never gets answered on the strength of its safest half.
"""

from __future__ import annotations

import re
from enum import Enum


class Topic(str, Enum):
    MONEY = "money"
    """Price, credits, plans, our course, what anyone earns. Never guessed."""

    OURS = "ours"
    """Our own output, settings, results. Knowledge base or escalate."""

    CRAFT = "craft"
    """General technique. Answerable from the craft base."""

    OTHER = "other"
    """Everything else — praise, chat, a posted result. Unchanged behaviour."""


#: Money, in both scripts. Deliberately broad: a false MONEY reading costs one
#: escalation, a missed one costs a wrong price in public.
#:
#: Matched with a LEADING word boundary and no trailing one. Uzbek is
#: agglutinative, so "kurs" must also catch "kurslar" and "kursga" — but a bare
#: substring test made "kamera rakursi" a money question, because `rakursi`
#: contains `kurs`. The same shape as the eval's bare `bor`, which is a
#: substring of half the language.
MONEY_WORDS = (
    "narx", "qancha", "pul", "toʻlov", "tolov", "to'lov", "obuna", "tarif",
    "bepul", "tekin", "chegirma", "kredit", "dollar", "soʻm", "so'm", "som",
    "kurs", "oylik", "daromad", "ishlash mumkin", "topish mumkin",
    "нарх", "қанча", "пул", "обуна", "бепул", "текин", "курс", "даромад",
)

MONEY_RE = re.compile(
    "|".join(r"\b" + re.escape(w) for w in MONEY_WORDS), re.IGNORECASE
)

#: Asking about US: what we used, how we did it, our settings, our results.
OURS_PATTERNS = (
    r"\bqanday qil(dingiz|di[zn]|gansiz|ganingiz)",
    r"\bqanaqa qil(dingiz|di[zn])",
    r"\bqaysi (ai|model|dastur|tool|program)",
    r"\bnim[ae] bilan qil",
    r"\bsiz(lar)? (qanday|nima|qaysi)",
    r"\bsozlama",
    r"қандай қил(дингиз|диз|диз|ганиз)",
    r"қайси (аи|модел|дастур)",
    r"нима билан қил",
)

#: Asking how to do something, in general. The class the bot should own.
CRAFT_PATTERNS = (
    r"\bqanaqa promt?\b", r"\bqanday promt?\b", r"\bprompt(ni|da|ga)? qanday",
    r"\bqanday yoz", r"\bnima yoz", r"\bqanday qilib\b",
    r"\brealistik\b", r"\btabiiy chiq", r"\bsifatli chiq",
    r"\byorugʻlik\b", r"\byorug'lik\b", r"\bkamera\b", r"\brakurs\b",
    r"\bkompozitsiya\b", r"\bfon\b",
    r"\bmaslahat ber", r"\boʻrgat", r"\bo'rgat", r"\burgat",
    r"қанақа промт", r"қандай промт", r"қандай ёз", r"реалистик",
    r"ёруғлик", r"камера", r"маслаҳат бер",
)


def _hits(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, text) for p in patterns)


def topic_of(text: str | None) -> Topic:
    """Classify a member's message.

    Order is the whole point. Checked most-dangerous first, so a message that is
    several things at once is governed by its riskiest reading.
    """
    low = (text or "").lower()
    if not low.strip():
        return Topic.OTHER

    if MONEY_RE.search(low):
        return Topic.MONEY
    if _hits(low, OURS_PATTERNS):
        return Topic.OURS
    if _hits(low, CRAFT_PATTERNS):
        return Topic.CRAFT
    return Topic.OTHER


def may_teach(text: str | None) -> bool:
    """Whether the craft base is allowed to answer this one.

    A convenience for the Replier, and a single place to read when asking why a
    message did or did not get a teaching answer.
    """
    return topic_of(text) is Topic.CRAFT
