"""Look a price up on the open web, and know when not to answer.

Founder direction, 2026-08-15: when a member asks something the open web can
answer — pricing above all — the bot should go and find it rather than deflect,
and raise it to the founders only when the answer is genuinely unclear.

This does NOT relax the rule that a price may never come from model memory. It
satisfies that rule a second way: a price becomes quotable when a live search
returned it *with a source*, and stays unquotable otherwise.

The first probe of this feature is the reason it is built the way it is. Asked
what Kling costs, the web returned:

* two trackers disagreeing materially — one said Standard ≈ $6.99, another $10–15
* not one official vendor page among the results
* and three different prices on the same card: list $10, first-month promo $6.99,
  renewal $8.80

A bot that flattens that into "$6.99" has told 3,326 people a number that is
wrong from the second month onward, and has spent authority it cannot buy back.
So the finding is structured, every gate is explicit, and anything less than a
clean official answer goes to the founders instead of the channel.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from app.net import http_client

log = logging.getLogger("research")

MODEL = "claude-opus-5"

#: Server-side search. Capped low: a price question is answered by the vendor's
#: own page or it is not answered here at all.
SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 4,
}

FINDING_TOOL: dict[str, Any] = {
    "name": "submit_finding",
    "description": (
        "Report what the search actually established. Report honestly — a finding "
        "marked unquotable goes to the founders, which is a good outcome. A wrong "
        "price published to the channel is not."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "found": {"type": "boolean", "description": "A specific current price was located."},
            "subject": {"type": "string", "description": "What was priced, e.g. 'Kling AI'."},
            "plan": {"type": "string", "description": "Plan or tier name, verbatim from the source."},
            "amount": {"type": "string", "description": "The number alone, e.g. '25.99'."},
            "currency": {"type": "string", "description": "USD, EUR, UZS..."},
            "period": {
                "type": "string",
                "description": "What is bought: 'oyiga' (monthly), 'yiliga', 'bir marta', 'kredit'.",
            },
            "source_url": {"type": "string", "description": "The exact page the number came from."},
            "source_is_official": {
                "type": "boolean",
                "description": (
                    "True ONLY if source_url is the vendor's own domain. A review "
                    "site, tracker, blog or aggregator is false."
                ),
            },
            "sources_conflict": {
                "type": "boolean",
                "description": "Different sources gave materially different prices for the same plan.",
            },
            "has_promotional_variants": {
                "type": "boolean",
                "description": (
                    "The vendor shows more than one price for this plan — list vs "
                    "first-time-promo vs renewal, or regional pricing. Almost every "
                    "AI vendor does this, and quoting the promo as 'the price' misleads."
                ),
            },
            "as_of": {"type": "string", "description": "Date the source page was current, YYYY-MM-DD."},
            "caveat": {
                "type": "string",
                "description": "What a member must know to not be surprised at checkout. Uzbek.",
            },
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "summary_for_founders": {
                "type": "string",
                "description": (
                    "Two or three lines for the admin chat when this is not quotable: "
                    "what was found, what conflicted, what to decide."
                ),
            },
        },
        "required": [
            "found", "subject", "source_url", "source_is_official",
            "sources_conflict", "has_promotional_variants", "confidence",
            "summary_for_founders",
        ],
    },
}


@dataclass
class Finding:
    found: bool = False
    subject: str = ""
    plan: str = ""
    amount: str = ""
    currency: str = ""
    period: str = ""
    source_url: str = ""
    source_is_official: bool = False
    sources_conflict: bool = False
    has_promotional_variants: bool = False
    as_of: str = ""
    caveat: str = ""
    confidence: str = "low"
    summary_for_founders: str = ""
    searched: bool = False
    blockers: list[str] = field(default_factory=list)

    @property
    def quotable(self) -> bool:
        """Whether this may be said in the channel rather than raised to a founder.

        Deliberately strict. Every clause here is a way the probe went wrong.
        """
        return not self.blockers

    def as_fact(self) -> str:
        """The grounded line the Replier is allowed to build on."""
        price = " ".join(p for p in (self.amount, self.currency, self.period) if p)
        parts = [f"{self.subject} {self.plan}: {price}".strip()]
        if self.as_of:
            parts.append(f"({self.as_of} holatiga koʻra)")
        if self.caveat:
            parts.append(f"— {self.caveat}")
        parts.append(f"Manba: {self.source_url}")
        return " ".join(parts)


def _gate(finding: Finding) -> list[str]:
    """Why this finding may not be published. Empty means it may."""
    blockers = []
    if not finding.found:
        blockers.append("no specific price located")
    if not finding.source_is_official:
        blockers.append("source is not the vendor's own page")
    if finding.sources_conflict:
        blockers.append("sources disagree on the price")
    if finding.confidence != "high":
        blockers.append(f"confidence is {finding.confidence}")
    if not finding.source_url:
        blockers.append("no source URL")
    return blockers


PROMPT = """A member of an Uzbek AI-education Telegram channel asked about pricing.
Find the CURRENT price from the vendor's own website.

QUESTION: {question}

How to search well here:

1. Go to the vendor's own pricing page. A review site, tracker or blog is not
   good enough — those go stale and disagree with each other, and this answer is
   going in front of 3,326 people.
2. AI vendors routinely show several prices for one plan: a struck-through list
   price, a first-time-subscriber promotion, and a renewal price. If you see
   more than one, set has_promotional_variants and say in `caveat` which number
   a member will actually pay on renewal.
3. If two sources give materially different numbers, set sources_conflict. Do
   not pick one.
4. Regional pricing and currency matter — the audience is in Uzbekistan.

Then call submit_finding. Being unable to confirm a price is a perfectly good
outcome: it goes to the founders, who answer it themselves. Guessing is not.

Write `caveat` and `summary_for_founders` in Uzbek Latin, using the okina ʻ
(U+02BB) in oʻ and gʻ."""


def _client(api_key: str):
    import anthropic

    return anthropic.Anthropic(api_key=api_key, http_client=http_client(timeout=180.0))


def _finding_from(blocks: list) -> Finding | None:
    for block in blocks:
        if getattr(block, "type", "") == "tool_use" and block.name == "submit_finding":
            data = {k: v for k, v in block.input.items() if k in Finding.__annotations__}
            return Finding(**data)
    return None


def lookup_price(question: str, *, api_key: str) -> Finding:
    """Search the web for a price and return a gated finding.

    Never raises on a research failure: a question the bot cannot answer must
    degrade to an escalation, not to a broken reply.
    """
    if not api_key:
        return Finding(blockers=["no API key"], summary_for_founders=question)

    try:
        client = _client(api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            tools=[SEARCH_TOOL, FINDING_TOOL],
            messages=[{"role": "user", "content": PROMPT.format(question=question)}],
        )
        finding = _finding_from(response.content)

        if finding is None:
            # It searched and talked but never filed. Ask again, forcing the tool,
            # with what it already said — cheaper and more reliable than re-searching.
            said = "\n".join(b.text for b in response.content if getattr(b, "type", "") == "text")
            follow = client.messages.create(
                model=MODEL,
                max_tokens=1500,
                tools=[FINDING_TOOL],
                tool_choice={"type": "tool", "name": "submit_finding"},
                messages=[
                    {"role": "user", "content": PROMPT.format(question=question)},
                    {"role": "assistant", "content": said or "(no findings)"},
                    {"role": "user", "content": "Now file that as submit_finding."},
                ],
            )
            finding = _finding_from(follow.content)

        if finding is None:
            return Finding(searched=True, blockers=["the researcher filed nothing"],
                           summary_for_founders=question)

        finding.searched = True
        finding.blockers = _gate(finding)
        log.info("price lookup %r -> found=%s official=%s conflict=%s conf=%s blockers=%s",
                 question[:60], finding.found, finding.source_is_official,
                 finding.sources_conflict, finding.confidence, finding.blockers)
        return finding

    except Exception as exc:
        log.exception("price lookup failed")
        return Finding(blockers=[f"lookup failed: {type(exc).__name__}"],
                       summary_for_founders=question)


#: Words that mean a member is asking what something costs, in both scripts and
#: in the Russian that turns up in this audience's comments.
PRICE_WORDS = (
    "narx", "narxi", "qancha", "qancha turadi", "pul", "toʻlov", "tolov",
    "obuna", "tarif", "bepul", "arzon", "qimmat", "kredit", "нарх", "нархи",
    "қанча", "пул", "обуна", "тариф", "текин", "цена", "сколько", "стоит",
    "price", "cost", "how much", "subscription", "free",
)


def is_price_question(text: str) -> bool:
    """Whether a member's message is asking what something costs."""
    low = (text or "").lower()
    return any(word in low for word in PRICE_WORDS)


def dump(finding: Finding) -> str:
    return json.dumps(asdict(finding), ensure_ascii=False, indent=2)
