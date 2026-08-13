# Milestones

Every exit criterion here is written so **you can verify it yourself** without taking my word for it.
A milestone is done when every box is checked and you have personally seen the evidence.

Design spec: [`docs/superpowers/specs/2026-08-13-telegram-community-manager-design.md`](docs/superpowers/specs/2026-08-13-telegram-community-manager-design.md)

**Status:** M0 not started — blocked on pre-flight items below.

---

## Pre-flight — needed before M0

| # | Item | Status |
|---|---|---|
| 1 | **Is Topics/forum mode ON or OFF** in the discussion group? | ⬜ |
| 2 | Channel `@username` and discussion group link | ⬜ |
| 3 | VPS SSH access + Hostinger subdomain hostname | ⬜ |
| 4 | Bot token in `.env`; bot admin in **both** chats; privacy mode disabled **before** joining the group | ⬜ |
| 5 | Higgsfield HTTP API key — **and** confirmation the Creator plan grants server-side access | ⬜ |
| 6 | Anthropic API key | ⬜ |
| 7 | Shahlo's `telegram_id` (approver) + Akmalidin's, for the Mini App allowlist | ⬜ |
| 8 | Story Bank — origin story, Sweden conference, member results with permission, portfolio, boundaries | ⬜ |

Items 1 and 5 each gate an entire milestone (M3 and M4 respectively) — worth resolving first.
Item 8 blocks authority and proof content only; how-to and why-content can be produced without it.

---

## M0 · Foundations — day 1–2

**Build:** repo scaffold, VPS, Postgres, Caddy TLS, systemd unit, startup assertions.

- [ ] Health endpoint returns green over HTTPS on the Hostinger subdomain
- [ ] Bot refuses to boot if the discussion group has Topics enabled *(verify by temporarily enabling it)*
- [ ] Bot resolves and caches `linked_chat_id` from the channel at startup
- [ ] Test post published to the channel
- [ ] **Seed comment lands inside the discussion thread, not the group's main feed** ← the single most
      important check in M0; the wrong implementation looks identical in code and obvious in the group
- [ ] One authenticated Higgsfield HTTP API call returns an image

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

**Build:** Higgsfield client, structured prompt object, banned-term transform, pairing validator, variants.

- [ ] A full week's media generated inside budget
- [ ] **Zero published images contain generated Uzbek text**
- [ ] Every published asset stores `{recipe_id, model, seed, prompt, refs, aspect}`
- [ ] Banned-term transform logs both raw and cleaned prompt *(this diff becomes a post)*
- [ ] Pairing validator rejects a deliberately incompatible prompt (24mm lens + extreme close-up)
- [ ] Generated outputs downloaded locally within minutes — never relied on at the vendor URL

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
