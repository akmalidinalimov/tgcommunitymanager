# Milestones

Every exit criterion here is written so **you can verify it yourself** without taking my word for it.
A milestone is done when every box is checked and you have personally seen the evidence.

Design spec: [`docs/superpowers/specs/2026-08-13-telegram-community-manager-design.md`](docs/superpowers/specs/2026-08-13-telegram-community-manager-design.md)

**Status:** M0 in progress. The publish → auto-forward → seed-comment flow is **proven on the live channel**
([post 606](https://t.me/aicreatorsuz/606), auto-forward caught in 2.7s, seed landed in thread root 3).
Remaining M0 work is deployment.

---

## Pre-flight — needed before M0

| # | Item | Status |
|---|---|---|
| 1 | Topics/forum mode in the discussion group | ✅ **OFF** — M3 unblocked |
| 2 | Bot created — `@malikamanager_bot`, token in `.env`, git-ignored | ✅ |
| 3 | Media generation approach | ✅ Higgsfield MCP on the laptop, weekly batch — no API key needed |
| 4 | Privacy mode disabled — `can_read_all_group_messages: true` | ✅ |
| 5 | Bot renamed to `Malika · AI yordamchi` | ✅ |
| 6 | Bot admin in **both** channel and discussion group, all required rights | ✅ |
| 7 | Channel `@aicreatorsuz` (`-1002708742288`, 3,326) · group `-1004430366406` (3 members) | ✅ |
| 8 | Anthropic API key in `.env`, verified against the API | ✅ |
| 9 | **Restart Claude Code** so the `hostinger` MCP server loads from `.mcp.json` | ⬜ |
| 10 | Shahlo's `telegram_id` (approver) + Akmalidin's, for the Mini App allowlist | ⬜ |
| 11 | Story Bank — **founders only**: origin story, Sweden conference, own client work, portfolio, boundaries | ⬜ |
| 12 | Shahlo's review of the Uzbek in `.claude/skills/humanize-uz/SKILL.md` | ⬜ |

Item 9 blocks deployment only. Item 11 blocks behind-the-scenes content; how-to and why-content need nothing.
**Item 12 is the one thing in this build that cannot be verified without a native speaker** — every post
the system writes inherits those example lines, so an error there compounds rather than staying local.

**No student or testimonial content** (founder decision) — so the conflicting 1500+/1800+/5000+ counts and
Aisha's $1,500 never enter a post, and the claims-reconciliation task is dropped.

---

## M0 · Foundations — day 1–2

**Build:** repo scaffold, Docker Compose project on Hostinger VM 1411263, Postgres, TLS, startup assertions.

- [x] VM 1411263 has headroom *(2.2% CPU, 1.3/8 GB RAM, 13/100 GB disk)*
- [x] Compose file stays under Hostinger's 8192-char `content` cap *(764 chars)*
- [ ] Health endpoint returns green over HTTPS on the Hostinger subdomain
- [x] Bot refuses to boot if the discussion group has Topics enabled *(verify by temporarily enabling it)*
- [x] Bot resolves and caches `linked_chat_id` from the channel at startup
- [x] Test post published to the channel
- [x] **Seed comment lands inside the discussion thread, not the group's main feed** ← the single most
      important check in M0; the wrong implementation looks identical in code and obvious in the group
- [x] Media path proven — sendVideo/sendPhoto with captions, nine assets indexed

## M1 · Publishing spine + voice engine — week 1

**Build:** content state machine, scheduler, backup pool, `humanize-uz` v1, Writer + Voice Critic +
Claims Guard, approval via bot-native inline cards, AI disclosure.

- [ ] **7 consecutive days of posts published on time with zero manual writing**
- [ ] Posts land at 10:00 and 21:00 Asia/Tashkent, verified across a service restart
- [ ] A deliberately unapproved slot publishes from the backup pool — not silence, not unapproved content
- [ ] Claims Guard strips a planted unsupported number before it reaches review
- [ ] Voice Critic rejects a deliberately machine-translated draft
- [ ] AI disclosure visible in bot name and description

**You'll know it worked when:** you stop writing posts and the channel doesn't notice.

## M2 · Mini App batch review — week 2

**Build:** FastAPI + HTMX panel, `initData` auth, week board → decision card, exceptions-first flow.

- [ ] **A full 14-post week approved in under 60 minutes, timed, from your phone**
- [ ] Only Shahlo's and Akmalidin's `telegram_id` can open the panel *(verify with a third account)*
- [ ] Approved posts are immutable — no regeneration can alter them after approval
- [ ] Undo works on every approve for the whole session
- [ ] Decision card renders the exact production post including the "show more" fold

## M3 · Comment engagement — week 3

**Build:** auto-forward detection, thread persistence, seeding, Triage + Replier, escalation queue.

- [ ] Seed comment posted within 5 minutes of every published post
- [ ] **Median reply latency under 10 minutes**
- [ ] **Zero replies to service messages or to the bot itself across 100 updates**
- [ ] A pricing question and a complaint both escalate to the admin group instead of being answered
- [ ] User comments per post measurably above the pre-launch baseline *(record the baseline before M3)*
- [ ] No reply reads as templated — spot-check 20 replies for repeated openers

## M4 · Media pipeline — week 3–4

**Build:** structured prompt object, banned-term transform, pairing validator, laptop-side generation
script driving the Higgsfield MCP, and the upload path into the bot's media store.
*No HTTP client, no API key, no job queue — media is generated in the weekly laptop session.*

- [ ] A full week's media generated in one laptop session and uploaded to the media store
- [ ] **Zero published images contain generated Uzbek text** (plate + overlay, never in-image type)
- [ ] Every published asset stores `{recipe_id, model, seed, prompt, refs, aspect}`
- [ ] Banned-term transform logs both raw and cleaned prompt *(this diff becomes a post)*
- [ ] Pairing validator rejects a deliberately incompatible prompt (24mm lens + extreme close-up)
- [ ] Outputs downloaded immediately — never relied on at the Higgsfield URL, which expires in ~7 days
- [ ] Credit burn per week measured against the 2,173 balance, so the runway is known

## M5 · Analyst + content spine — week 4

**Build:** nightly analysis, weekly report, north-star tracking, shot-vocabulary content spine.

- [ ] Weekly report delivered with artifact count and top objections mined from real comments
- [ ] Next week's plan generated from the previous week's data, not from a static template
- [ ] Shot-vocabulary spine loaded — ~87 evening-slot topics queued
- [ ] **North-star metric visible: member-generated artifacts posted per week**

---

## How to tell the whole thing is working

Beyond any individual checkbox — after four weeks:

1. Shahlo spends **one hour a week** on the channel and nothing more.
2. The discussion group has conversations in it that the founders did not start.
3. Members are posting their own generated images and asking for critique.
4. Not one published post contains a number or claim nobody can substantiate.
