"""Draft a comment reply, or refuse to.

Two properties matter more than fluency:

1. **Grounding.** Model facts change monthly. The Replier may only state facts
   present in ``data/knowledge/models.yaml`` and must name which entries it used.
   Anything else escalates to the founders. Being confidently wrong about Kling
   or Seedance in front of 3,326 members costs more authority than silence.

2. **Register.** A blind test scored 4/4 on posts and 0/3 on comment replies —
   every failure caused by replies being too complete. The voice rules live in
   ``.claude/skills/humanize-uz/SKILL.md`` and are read from there so the guide a
   human edits is the guide the bot obeys.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.context import ReplyContext
from app.text.orthography import normalize_apostrophes
from app.text.script import Script

MODEL = "claude-opus-5"
ROOT = Path(__file__).resolve().parent.parent.parent
KNOWLEDGE_PATH = ROOT / "data" / "knowledge" / "models.yaml"
VOICE_PATH = ROOT / ".claude" / "skills" / "humanize-uz" / "SKILL.md"

DRAFT_TOOL: dict[str, Any] = {
    "name": "submit_reply",
    "description": "Submit a drafted comment reply, or escalate instead of guessing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["reply", "escalate"],
                "description": (
                    "'reply' only when every factual claim is grounded in the knowledge "
                    "base. 'escalate' whenever a fact is needed that is not there."
                ),
            },
            "draft": {
                "type": "string",
                "description": (
                    "The reply, in the member's script. One sentence, often a fragment. "
                    "No greeting, no sign-off, no closing offer. Empty when escalating."
                ),
            },
            "grounded_on": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Knowledge-base keys used, e.g. ['models.kling3_0']. Empty if none needed.",
            },
            "needs_from_founders": {
                "type": "string",
                "description": "When escalating: the exact question the founders must answer.",
            },
            "reasoning": {"type": "string", "description": "One line, for the audit trail."},
        },
        "required": ["action", "draft", "grounded_on", "reasoning"],
    },
}


@dataclass
class Draft:
    action: str
    draft: str
    grounded_on: list[str]
    reasoning: str
    needs_from_founders: str = ""

    @property
    def is_reply(self) -> bool:
        return self.action == "reply" and bool(self.draft.strip())


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def build_prompt(ctx: ReplyContext, previous_drafts: list[str] | None = None) -> str:
    script_name = "Uzbek Cyrillic" if ctx.script is Script.CYRILLIC else "Uzbek Latin"
    history = "\n".join(
        f"  [{m.message_id}] {m.author}: {m.text or '(posted a video)'}"
        for m in ctx.history
    ) or "  (no other messages yet)"

    # Without this the model drafts each reply blind to its siblings and produces
    # three variations of the same sentence in one thread. Repetition is the
    # loudest bot tell there is — roughly half of people distrust a templated
    # reply, so a repeated opener is worse than not replying at all.
    if previous_drafts:
        already = "\n".join(f"  - {d}" for d in previous_drafts)
        variety = f"""
=== REPLIES YOU HAVE ALREADY SENT IN THIS THREAD ===
{already}

Anyone reading the thread sees all of these together. Do NOT reuse their opening
word, their sentence shape, or their emoji. If your reply would be a variation of
one of them, write something genuinely different or say nothing. Three replies
that start the same way read as a machine, and no amount of correct information
buys that credibility back."""
    else:
        variety = ""

    return f"""You write comment replies for an Uzbek AI-education Telegram channel, as its
openly-AI assistant "Malika · AI yordamchi".

=== VOICE GUIDE (authoritative) ===
{_read(VOICE_PATH)}

=== KNOWLEDGE BASE — the ONLY source you may cite for model facts ===
{_read(KNOWLEDGE_PATH)}

=== THE CHANNEL POST BEING DISCUSSED ===
{ctx.post_text}

=== THE THREAD SO FAR ===
{history}

=== THE MESSAGE YOU ARE ANSWERING ===
[{ctx.target.message_id}] {ctx.target.author}: {ctx.target.text or '(posted a video, no caption)'}
{variety}

=== YOUR TASK ===
Write ONE reply in {script_name}, matching the script this member wrote in.

Hard constraints:
- Comment register. One sentence, often a fragment. 3-12 words.
- No greeting, no sign-off, and NEVER a closing offer like "savolingiz bo'lsa yozing".
- Never repeat the question back. Never say "yaxshi savol".
- At most one emoji, at the end only.
- Do not claim personal experience. You have never generated anything. Never write
  "menda shunday bo'ldi" or anything implying you tried something yourself.
- Every factual claim about a model, price or capability MUST come from the
  knowledge base, and you must list the keys you used in grounded_on.
- If you need a fact that is not in the knowledge base, set action="escalate" and
  say exactly what you need from the founders. Do not guess. Do not hedge into a
  vague answer to avoid escalating — a vague reply is worse than an escalation.
- If the member posted their own generated video, react to the fact they made
  something. Short, specific, warm. Do not review quality you cannot see.

Call submit_reply with your decision."""


def draft_reply(
    ctx: ReplyContext,
    *,
    api_key: str,
    model: str = MODEL,
    previous_drafts: list[str] | None = None,
) -> Draft:
    """Produce a draft, or an escalation. Never sends anything.

    ``previous_drafts`` are the bot's own replies already placed in this thread;
    passing them is what stops three near-identical sentences appearing together.
    """
    import anthropic

    from app.net import http_client

    # The SDK builds its own httpx client, which hits the same TLS-proxy wall as
    # everything else here, so hand it one wired to the OS trust store.
    client = anthropic.Anthropic(api_key=api_key, http_client=http_client(timeout=120.0))
    response = client.messages.create(
        model=model,
        max_tokens=1200,
        tools=[DRAFT_TOOL],
        tool_choice={"type": "tool", "name": "submit_reply"},
        messages=[{"role": "user", "content": build_prompt(ctx)}],
    )

    payload: dict[str, Any] = {}
    for block in response.content:
        if block.type == "tool_use":
            payload = block.input
            break
    if not payload:
        raise RuntimeError(f"model returned no tool call: {response.content!r}")

    text = (payload.get("draft") or "").strip()
    # Latin output carries okina/tutuq; Cyrillic has no apostrophe convention.
    if ctx.script is not Script.CYRILLIC:
        text = normalize_apostrophes(text)

    return Draft(
        action=payload.get("action", "escalate"),
        draft=text,
        grounded_on=list(payload.get("grounded_on") or []),
        reasoning=payload.get("reasoning", ""),
        needs_from_founders=payload.get("needs_from_founders", ""),
    )


def to_admin_card(ctx: ReplyContext, draft: Draft) -> str:
    """Render the shadow-mode card the founders see before anyone else does."""
    header = "🟡 <b>Javob tayyor</b>" if draft.is_reply else "🔴 <b>Sizning javobingiz kerak</b>"
    grounded = ", ".join(draft.grounded_on) if draft.grounded_on else "—"
    body = [
        header,
        "",
        f"<b>{ctx.target.author}</b> ({ctx.script.value}):",
        f"<i>{ctx.target.text or '(video, izohsiz)'}</i>",
        "",
    ]
    if draft.is_reply:
        body += [f"<b>Javob:</b>\n{draft.draft}", "", f"<code>grounded: {grounded}</code>"]
    else:
        body += [f"<b>Nima kerak:</b>\n{draft.needs_from_founders}"]
    return "\n".join(body)


def dump(ctx: ReplyContext, draft: Draft) -> str:
    """Compact JSON line for the audit trail."""
    return json.dumps(
        {
            "message_id": ctx.target.message_id,
            "author": ctx.target.author,
            "script": ctx.script.value,
            "action": draft.action,
            "draft": draft.draft,
            "grounded_on": draft.grounded_on,
            "reasoning": draft.reasoning,
        },
        ensure_ascii=False,
    )
