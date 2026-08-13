"""Draft evergreen posts for the backup pool.

These publish unattended when a slot goes unapproved, possibly months from now,
so they must carry no dates, no callbacks to other posts, and nothing that stops
being true. Output is printed for human approval — nothing is stored or sent.
"""
from __future__ import annotations
import sys
from pathlib import Path
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8")
    except Exception: pass
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import logging  # noqa: E402
for n in ("httpx", "httpcore", "anthropic"):
    logging.getLogger(n).setLevel(logging.WARNING)
from app.agents.writer import write_post  # noqa: E402
from app.config import Settings  # noqa: E402

EVERGREEN = (
    "This post goes into the BACKUP POOL. It may publish unattended months from "
    "now, so it must contain NO dates, NO references to other posts or recent "
    "events, NO 'yesterday'/'last week', and nothing that stops being true. "
    "Write it so it reads correctly whenever it appears. "
)

BRIEFS = [
    ("technique", EVERGREEN + "Why AI-generated images garble Uzbek text, and the "
     "workaround: generate a clean plate with space reserved, then set the type yourself "
     "in an editor. Teach it as a limitation with a fix, not a complaint."),
    ("why_content", EVERGREEN + "Why a business pays for content at all. It does not buy "
     "a picture; it buys a problem being solved. Explain what changes when you think that way."),
    ("commercial_craft", EVERGREEN + "What separates an image a business pays for from an "
     "image that is merely nice. Concrete: intent, the brief behind it, consistency across a set."),
    ("technique", EVERGREEN + "The parts of a prompt that actually change the output — "
     "subject, light, camera angle, lens — and why piling on adjectives does not."),
    ("mission", EVERGREEN + "Starting from home, with a phone, knowing nothing. Honest about "
     "the work involved. No income promises, no guarantees, no student stories."),
]

def main() -> int:
    s = Settings.load()
    recent: list[str] = []
    ok = 0
    for i, (kind, brief) in enumerate(BRIEFS, 1):
        print(f"--- drafting {i}/{len(BRIEFS)} ({kind}) ---", flush=True)
        p = write_post(kind, api_key=s.anthropic_api_key or "", brief=brief, recent=recent)
        print("=" * 68)
        print(f"BACKUP {i}  ·  {kind}  ·  translationese={p.translationese}  ok={p.ok}")
        print("-" * 68)
        print(p.text or "(none)")
        if not p.ok:
            print(f"!! {p.problem}")
        print("=" * 68 + "\n", flush=True)
        if p.ok:
            recent.append(p.text); ok += 1
    print(f"{ok}/{len(BRIEFS)} publishable")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
