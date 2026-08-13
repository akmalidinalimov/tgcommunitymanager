"""Write a channel post, then let a critic try to reject it.

The loop is deliberately three-stage and cheap-to-expensive:

1. **Lint** — deterministic string checks. Free, identical every time, and
   catches most of what makes Uzbek read as machine-written.
2. **Claims ledger** — a schema check. No number ships unless a ledger row
   backs it.
3. **Critic** — an LLM, given only what genuinely needs judgement.

A draft that fails 1 or 2 never reaches 3, because paying a model to notice
`amalga oshirish` is waste, and because a string match cannot have an off day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.text.lint import Issue, blockers, lint, unsupported_numbers
from app.text.orthography import normalize_apostrophes

MODEL = "claude-opus-5"
ROOT = Path(__file__).resolve().parent.parent.parent
KNOWLEDGE_PATH = ROOT / "data" / "knowledge" / "models.yaml"
VOICE_PATH = ROOT / ".claude" / "skills" / "humanize-uz" / "SKILL.md"

#: The weekly grid. Each kind carries the brief that makes it that kind of post.
POST_KINDS: dict[str, str] = {
    "technique": "A practical technique the reader can use today. Concrete, one idea, immediately actionable.",
    "commercial_craft": "What businesses actually pay for and why. The differentiator: anyone can generate an image, few can generate what a business buys.",
    "why_content": "Why this kind of content sells. Explain the thinking behind commercial work, not the button-pressing.",
    "news": "One AI development, framed as an opportunity. Extract the bare fact and react to it natively — never translate foreign coverage.",
    "poll": "An opinion or diagnostic question worth answering in one tap.",
    "challenge": "Invite members to make something and post it in the comments.",
    "recognition": "Celebrate what members made this week. Never invent a result.",
    "mission": "Perspective on what this skill changes for someone. Honest, no false promises.",
    "behind_scenes": "Something real from the founders' own work or week. Requires Story Bank facts.",
    "recap": "What happened this week, and one thing to try next.",
}

WRITER_TOOL: dict[str, Any] = {
    "name": "submit_post",
    "description": "Submit a channel post draft, or report that facts are missing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": (
                    "The complete post in Uzbek Latin, ready to publish. Blank lines "
                    "between paragraphs, emoji as line-leading bullets where natural."
                ),
            },
            "seed_comment": {
                "type": "string",
                "description": (
                    "The first comment the bot posts under this post to open the thread. "
                    "One short question, answerable in a word. Never claims personal experience."
                ),
            },
            "needs_facts": {
                "type": "string",
                "description": (
                    "Non-empty ONLY if the brief cannot be written without a fact that is "
                    "in neither the knowledge base nor the brief. Leave blank otherwise."
                ),
            },
            "numbers_used": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Every figure in the post, each traceable to the brief or knowledge base.",
            },
        },
        "required": ["text", "seed_comment", "numbers_used"],
    },
}

CRITIC_TOOL: dict[str, Any] = {
    "name": "judge",
    "description": "Judge a draft against the voice guide. Assume it has problems.",
    "input_schema": {
        "type": "object",
        "properties": {
            "translationese": {
                "type": "integer",
                "description": "0-100. Above 30 is a blocker. Be honest; generosity here helps nobody.",
            },
            "passed": {"type": "boolean"},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["blocker", "polish"],
                            "description": (
                                "blocker = must not publish: translationese above 30, a dead "
                                "opening, an untrue or unusable claim, a paragraph with nothing "
                                "to act on. polish = genuinely better if changed, fine to ship "
                                "as is. Most issues are polish. Reserve blocker for real damage."
                            ),
                        },
                        "what": {"type": "string"},
                        "fix": {"type": "string", "description": "The replacement text, in Uzbek, ready to drop in."},
                    },
                    "required": ["severity", "what", "fix"],
                },
            },
            "summary": {"type": "string"},
        },
        "required": ["translationese", "passed", "issues", "summary"],
    },
}


@dataclass
class Post:
    text: str
    seed_comment: str
    kind: str
    rounds: int = 0
    lint_issues: list[Issue] = field(default_factory=list)
    critic_notes: list[str] = field(default_factory=list)
    needs_facts: str = ""
    translationese: int | None = None
    unsupported: list[str] = field(default_factory=list)
    critic_passed: bool = False
    exhausted: bool = False
    """Ran out of revision rounds without the critic passing it."""

    @property
    def ok(self) -> bool:
        """Publishable-quality. Anything else goes to a human, never to the channel.

        An earlier version checked only lint issues, so a draft that failed the
        claims-ledger check and then exhausted its rounds still reported ok.
        """
        return (
            bool(self.text)
            and not self.needs_facts
            and not self.unsupported
            and not blockers(self.lint_issues)
            and self.critic_passed
        )

    @property
    def problem(self) -> str:
        """Why this is not publishable, for the escalation card."""
        if self.needs_facts:
            return f"missing facts: {self.needs_facts}"
        if self.unsupported:
            return f"unsupported claims: {', '.join(self.unsupported)}"
        if blockers(self.lint_issues):
            return "; ".join(str(i) for i in blockers(self.lint_issues))
        if self.exhausted:
            return f"critic never passed it in {self.rounds} rounds (translationese {self.translationese})"
        return ""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _client(api_key: str):
    import anthropic

    from app.net import http_client

    return anthropic.Anthropic(api_key=api_key, http_client=http_client(timeout=120.0))


def _call(client, tool: dict, prompt: str, model: str) -> dict:
    response = client.messages.create(
        model=model, max_tokens=2000, tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("model returned no tool call")


def writer_prompt(kind: str, brief: str, recent: list[str], feedback: str = "") -> str:
    recent_block = "\n".join(f"  - {t[:90]}" for t in recent) or "  (nothing recent)"
    correction = f"""
=== YOUR PREVIOUS DRAFT WAS REJECTED ===
{feedback}

Fix exactly these problems. Do not rewrite what was not criticised.""" if feedback else ""

    return f"""You write posts for an Uzbek-language AI-education Telegram channel, in the
founder Shahlo's first-person voice.

=== VOICE GUIDE (authoritative) ===
{_read(VOICE_PATH)}

=== KNOWLEDGE BASE — the only source for model facts ===
{_read(KNOWLEDGE_PATH)}

=== THIS POST ===
Kind: {kind}
Brief: {brief}

=== RECENT POSTS — do not repeat these topics or openings ===
{recent_block}
{correction}

=== RULES THAT OVERRIDE EVERYTHING ===
- Uzbek Latin, polite-casual, `siz`. Never `sen`.
- NO invented numbers. Every figure must come from the brief or the knowledge
  base, and you must list them in numbers_used. If you want a number you cannot
  source, write the sentence without it.
- NO student names, testimonials, or claims about what anyone earned.
- Income framing is always "businesses pay X for deliverable Y", never
  "you can earn X".
- Lead with the outcome, then the artifact, then the tool. Never open on a tool name.
- End on what the reader gets.
- If the brief needs a fact you do not have, set needs_facts and stop. Do not
  invent a plausible one.

Call submit_post."""


def critic_prompt(text: str, kind: str) -> str:
    return f"""You are a hard-to-please Uzbek editor. Another writer produced the post below.
Your job is to find what is wrong with it.

You did not write this and have no stake in defending it. Assume it has problems
and go looking for them. A draft you pass gets published to 3,326 real people
under a real person's name.

=== VOICE GUIDE ===
{_read(VOICE_PATH)}

=== THE DRAFT ({kind}) ===
{text}

=== WHAT YOU ARE CHECKING ===
1. Does it sound translated? Read every line aloud in your head. Uzbek thought in
   English and rendered into Uzbek has a shape: English word order preserved,
   abstract nouns where verbs belong, connectives nobody says out loud, sentences
   that are grammatically correct and completely lifeless. Score honestly —
   above 30 is a blocker, and being generous here helps nobody.
2. Does the opening earn attention in three seconds?
3. Is there something concrete on every paragraph, or is it motivation with no
   instruction?
4. Is the ending a payoff for the reader, or a description of how something works?
5. Anything a reader could not act on, or that is not true.

Every issue needs `fix` as the actual replacement text in Uzbek, ready to drop
in — not "make this punchier". An issue without a usable fix is an opinion, and
opinions do not improve a draft.

=== SEVERITY, AND THE BAR FOR PASSING ===
Mark each issue `blocker` or `polish`.

- `blocker` — must not publish. Translationese above 30, a dead opening, a claim
  that is untrue or unusable, a paragraph with nothing to act on.
- `polish` — genuinely better if changed, fine to ship if not.

**Most issues are polish.** Reserve `blocker` for real damage. Set `passed` true
when there are zero blockers — do not withhold it because the draft could be
better, since every draft could be better. A post held back forever helps nobody,
and the alternative to shipping this is a channel that publishes nothing at all.

Call judge."""


def write_post(
    kind: str,
    *,
    api_key: str,
    brief: str | None = None,
    recent: list[str] | None = None,
    ledger: set[str] | None = None,
    max_rounds: int = 3,
    model: str = MODEL,
) -> Post:
    """Draft, check, and revise until it passes or the rounds run out."""
    client = _client(api_key)
    brief = brief or POST_KINDS.get(kind, kind)
    ledger = ledger or set()
    feedback = ""
    post = Post(text="", seed_comment="", kind=kind)

    for attempt in range(1, max_rounds + 1):
        post.rounds = attempt
        drafted = _call(client, WRITER_TOOL, writer_prompt(kind, brief, recent or [], feedback), model)

        post.needs_facts = (drafted.get("needs_facts") or "").strip()
        if post.needs_facts:
            return post

        post.text = normalize_apostrophes((drafted.get("text") or "").strip())
        post.seed_comment = normalize_apostrophes((drafted.get("seed_comment") or "").strip())

        # Cheap checks first — never pay a model to notice `amalga oshirish`.
        post.lint_issues = lint(post.text)
        problems = [str(i) for i in blockers(post.lint_issues)]

        allowed = set(ledger) | {str(n) for n in drafted.get("numbers_used") or []}
        post.unsupported = unsupported_numbers(post.text, allowed)
        if post.unsupported:
            problems.append(
                f"claims with no ledger row: {', '.join(post.unsupported)}. "
                f"Remove them or rewrite without figures."
            )

        if problems:
            feedback = "\n".join(problems)
            continue

        verdict = _call(client, CRITIC_TOOL, critic_prompt(post.text, kind), model)

        # The model does not always fill this field even though the schema
        # requires it. Treating a missing score as 0 would be fail-open on the
        # single most important quality signal — a post with no score would look
        # like a perfect one. Absent means unknown, and unknown is not evidence.
        raw = verdict.get("translationese")
        try:
            post.translationese = int(raw) if raw is not None else None
        except (TypeError, ValueError):
            post.translationese = None

        issues = verdict.get("issues") or []
        hard = [i for i in issues if i.get("severity") == "blocker"]
        too_translated = post.translationese is not None and post.translationese > 30

        # The verdict is computed from the issues rather than taken from the
        # model's own boolean. An adversarial critic told to assume problems will
        # keep finding them, and a first version of this trusted `passed` and so
        # rejected six perfectly good posts in a row — every draft can be better,
        # which is not the same as every draft being unpublishable.
        post.critic_passed = not hard and not too_translated
        post.critic_notes = [
            f"[{i.get('severity', 'polish')}] {i.get('what')} → {i.get('fix')}" for i in issues
        ]
        if post.critic_passed:
            return post

        feedback = (
            f"translationese score {post.translationese}. {verdict.get('summary', '')}\n"
            + "\n".join(f"{i.get('what')} → {i.get('fix')}" for i in hard)
        )

    # Rounds exhausted. Returning it as publishable would defeat the point of
    # having a critic — it goes to a human instead.
    post.exhausted = True
    return post
