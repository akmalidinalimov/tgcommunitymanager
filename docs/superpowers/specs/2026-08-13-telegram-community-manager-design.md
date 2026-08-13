# Telegram Community Manager — Design Spec

**Date:** 2026-08-13
**Status:** Approved for implementation
**Evidence base:** [`docs/research/`](../../research/) — three verified briefs (~27,000 words)

---

## 1. Problem

An Uzbek-language AI-education Telegram channel (3,000+ members) is run by a couple based in Sweden. They
teach AI image and video generation. Their differentiator is specific and defensible:

> Anyone can generate an image now. Very few can generate what a business will **pay** for.

The channel is alive but manual, and its linked discussion group is quiet. The founders don't have time to
write daily posts, illustrate them, publish them on schedule, and answer comments — so the channel
under-performs its audience.

## 2. Goal

An autonomous community manager that plans, writes, illustrates, publishes, seeds discussion, replies to
comments, and reports — while the founders spend **one hour per week** approving a batch.

**Near-term objective is trust and authority, not sales.** Content must deliver real value and explain
*why* commercial content works, not only *how*. A course exists in the founders' future but is explicitly
out of scope for this system.

### Success criteria

| Metric | Target |
|---|---|
| **North star** — member-generated artifacts posted in the discussion group per week | Trending up from a baseline of ~0 |
| Founder time spent per week | ≤ 1 hour |
| Posts published on schedule with no manual writing | 14/week |
| Weekly batch review duration | < 60 minutes, measured |
| Median comment reply latency | < 10 minutes |
| Unapproved content published | **Zero, ever** |

The north-star metric is deliberate: it is simultaneously the mission metric (people gaining self-efficacy),
the engagement metric, and the future supply of authentic proof. Member count is not a goal.

## 3. Non-goals

- Selling courses, lead capture, or payment handling — CHATPLACE already owns DM funnels
- Replacing the founders' own voice on Instagram or elsewhere
- Any userbot / MTProto account automation
- Post view counts and channel statistics — **not exposed by the Bot API at all**
- DMing channel members — impossible unless they press Start on the bot first

## 4. System overview

**The spine is deterministic Python. No LLM decides whether to publish.** Agents write, judge and analyze;
the spine decides, times and publishes. This is the property that makes autonomy safe at 3,000 readers.

```
                    ┌──────────── deterministic spine ────────────┐
   scheduler ─────▶ │  content state machine  │  media job queue   │
   (10:00/21:00     │                         │                    │
    Asia/Tashkent)  │  Postgres  │  media store on disk            │
                    └──────┬──────────────────────────────┬────────┘
                           │                              │
              ┌────────────▼──────────┐        ┌──────────▼─────────┐
              │  Telegram I/O          │        │  Mini App panel     │
              │  channel · group ·     │        │  weekly batch       │
              │  admin group           │        │  review             │
              └────────────────────────┘        └────────────────────┘
                           │
              ┌────────────▼───────────────────────────────┐
              │  agents: prompt + strict schema, swappable │
              └────────────────────────────────────────────┘
```

One FastAPI process serves both the aiogram webhook and the Mini App, under one systemd unit, behind Caddy
for automatic TLS.

### Agents

Each agent is one prompt plus one strict output schema, independently replaceable.

| Agent | Responsibility | Cadence |
|---|---|---|
| **Strategist** | Reads the commitment ladder; sets the week's narrative arc and pillar allocation | Weekly |
| **Planner** | Turns the Strategist brief into 14 dated, typed slots | Weekly |
| **News Curator** | Whitelisted sources only; every news post carries a source URL | Per news slot |
| **Writer** | Post-register Uzbek: hook, body, CTA, and the seed comment | Per post |
| **Voice Critic** | Rejects translationese, over-formality, AI-slop; ≤3 rounds then escalates | Per post |
| **Claims Guard** | Schema check — every number resolves to a claims-ledger row or is stripped | Per post |
| **Shot Director** | Structured prompt object → per-model dialect; banned-term transform; pairing validator | Per media |
| **Poll Maker** | Quizzes with correct answer and explanation | Per poll |
| **Triage** | Classifies each comment: auto / escalate / ignore / moderate | Per comment |
| **Replier** | Comment-register Uzbek — short, reactive, never templated | Per comment |
| **Analyst** | Vibe, objections, artifact count, what performed | Nightly + weekly |

## 5. Content pipeline

```
topic → theme-approved → written → critic-passed → claims-cleared → media-attached
      → post-approved → scheduled → published → measured
```

**Weekly rhythm** — fixed so the founders always know what's coming:

| | 10:00 | 21:00 |
|---|---|---|
| Mon | Practical technique | Commercial craft — *what businesses pay for* |
| Tue | AI news + opportunity angle | Member transformation story |
| Wed | Practical technique | Poll / quiz |
| Thu | Commercial craft | Behind the scenes |
| Fri | AI news + opportunity angle | Challenge launch |
| Sat | Mission / perspective | Practical technique |
| Sun | Challenge results + recognition | Weekly recap |

*Commercial craft* is the bridge pillar — technique and income in one post, which holds the 50/50 balance
without every second post being about money.

**Dependency:** the Tue 21:00 transformation slot and the Thu 21:00 behind-the-scenes slot both require
Story Bank entries. Until those exist, the Planner substitutes commercial-craft posts and flags the gap in
the weekly report rather than inventing a story.

### The commitment ladder

The Strategist allocates posts against where members actually sit, not evenly. Progression is driven by
foot-in-the-door: one small prior commitment raises later compliance sharply (76% vs 17%, Freedman & Fraser
1966). Each rung is a **Telegram-native action**, so rung position is measured rather than guessed, and
doubles as the member's engagement score.

| Rung | Observable action | What moves them up |
|---|---|---|
| 0 Lurker | none | Competence proof. **Never vulnerability content here.** |
| 1 Reactor | emoji reaction | A poll asking something genuinely diagnostic, not a vanity question |
| 2 Voter | poll vote | A mastery task — a real artifact in ≤30 min tonight, exact settings given |
| 3 Commenter | first comment | A personalised, non-templated reply |
| 4 Producer | posts their own generated result | Public, non-dismissive critique of their output |
| 5 Advocate | shares or brings someone in | Recognition, and a role in the community |

Rung 4 is the north-star metric. Everything upstream exists to manufacture it.

**Ordering constraint:** behind-the-scenes and vulnerability content must not run before competence is
established. The pratfall effect *reverses* for an unproven communicator — the same self-deprecating post
that endears an established expert damages an unestablished one.

**Backup pool.** If a slot is unapproved at publish time, the spine publishes a pre-approved evergreen post.
It never auto-publishes unreviewed content and never goes silent.

## 6. Engagement pipeline

Comment threads can only be learned by **listening**, never by asking — there is no Bot API call mapping a
channel post to its thread. The only link is the auto-forwarded copy arriving in the discussion group.

```
publish to channel ─▶ persist message_id ─▶ await auto-forward in group
   ─▶ match forward_origin.message_id ─▶ persist thread root
   ─▶ seed first comment via reply_parameters.message_id
```

**Seeding is the primary job**, not replying. The group is quiet, so the bot posts the opening comment
under its own post — a question, a hot take, a "who's tried this?" — so no member has to be first to speak.

Incoming comments run through an ordered classifier *before any LLM sees them*, then Triage routes them:
auto-reply, escalate to the admin group, ignore, or moderate. Replies attach to the commenter's message,
not the thread root.

## 7. Voice system

**Two registers, kept strictly separate.** A blind test scored 4/4 on long-form posts and **0/3 on comment
replies** — the replies failed because they were too complete: well-formed, correctly punctuated paragraphs
ending in a helpful offer. That is customer-support voice, not comment voice.

| | Post register | Comment register |
|---|---|---|
| Length | Multi-paragraph | One or two clauses |
| Structure | Hook → body → payoff line | Fragment |
| Completeness | Fully resolved | Deliberately unresolved |
| Closing offer | Sometimes | **Never** |

Both live in `.claude/skills/humanize-uz/`, distilled from `docs/research/research-voice-and-engagement.md`
§1–§5 plus the founders' real posts.

**Voice DNA** extracted from real channel posts: emoji as structural bullets (📌 ✅ ❗️ 👇 💸), CAPS for
emphasis, reader-question openers (`- ... - degan savol kelibdi`), callback continuity between posts
(`va'da qilgandim`), transformation payoff lines (`Endi X emas, balki Y`), and raw English tech terms with
Uzbek suffixes (`ChatGPT'dan`, `Custom Instructions'ga`).

**Language:** clean standard Uzbek Latin, polite-casual, `siz`. **Voice:** Shahlo's first person.

**News must not be translated.** Rewriting foreign coverage into Uzbek produces translationese — the
News Curator extracts the bare fact and the Writer composes a native reaction from scratch, never seeing the
English phrasing.

## 8. Media pipeline

Higgsfield via HTTP API (the MCP connector is session-bound and unusable from a server). Async submit →
poll or webhook → **download immediately**, since outputs expire in roughly 7 days.

The Shot Director holds a **structured prompt object** — subject, action, environment, lighting, camera,
lens, aspect, negative space, brand hex, recipe id, seed — rendered into each model's dialect at call time.

Three enforced rules:
1. **Banned-term pre-flight transform.** Strip "8k / ultra detailed / masterpiece"-class terms, log raw and
   transformed. *The diff is publishable teaching content.*
2. **Pairing validator.** Shot size ↔ focal length ↔ aperture must be consistent; one camera body, one lens,
   one dominant key light, one film stock. Physically incompatible combinations average two training
   distributions and produce uncanny output.
3. **Never generate in-image Uzbek text.** Models garble Latin diacritics. Generate a plate with reserved
   negative space; overlay type afterwards. This is taught explicitly as a limitation-plus-workaround.

Every published asset stores `{recipe_id, model, seed, prompt, refs, aspect}` — over time this becomes a
proprietary dataset of what works for this specific market.

## 9. Guardrails

These are load-bearing. The business is trust; a single fabricated claim costs more than the system earns.

**Claims ledger — no invented numbers, enforced by schema.** Every figure in every post must resolve to a
ledger row. If there is no row, the post ships without the number. This is a deterministic check, not an
LLM judgement, which makes it the most reliable guardrail in the system.

**Income framing.** Never *"you can earn X"*. Always *"businesses pay X for deliverable Y"*. Market prices
are third-party verifiable facts; personal earnings are outcome claims. This preserves the entire
differentiator while removing the legal exposure — income claims are the primary regulatory risk in this
market.

**AI disclosure — three layers**, required under EU AI Act Art. 50 for a Sweden-based operator:
display name marker, profile description, and a `🤖 AI yordamchi` line on the bot's first reply in each
thread. AI-generated photoreal media carries a visible synthetic-content label.

**Escalation.** Anything touching pricing, complaints, refunds, politics or religion goes to the admin
group instead of being answered.

**Never templated.** Roughly half of consumers distrust templated replies — a templated response is worse
than no response.

## 10. Data model (core tables)

`content_slots` · `post_versions` (immutable once approved) · `media_assets` · `claims_ledger` ·
`threads` (channel msg id ↔ group root id) · `comments` · `members` (ladder rung, opt-in state) ·
`engagement_events` · `review_sessions` (revision chips, decision times).

`post_versions` retains every revision plus the reason that produced it. When one revision reason fires
repeatedly, that is a generator bug, not a review problem.

## 11. Admin surface

A FastAPI + Jinja2 + HTMX panel served over HTTPS and opened as a Telegram Mini App from the bot's menu
button. Auth: HMAC over `initData` against a two-person allowlist, then an 8-hour session token.

Two-level UI: a **week board** (7×2 grid, thumbnails, status pills, flag icons) for triage, then a
**decision card** per post rendered as the exact production post including where Telegram's "show more"
fold lands. Exceptions first, then one "approve remaining N" with undo. Revision chips in Uzbek rather than
free typing. Media variants as a contact sheet — choosing a different variant *is* the revision for most
media problems.

**Single approver: Shahlo.** Two approvers on 14 posts a week generates review ping-pong.

## 12. Failure modes

| Failure | Handling |
|---|---|
| Bot offline when a post publishes | Thread root never learned; Telegram drops updates >24h and never replays. **Uptime monitoring is core.** |
| Discussion group has Topics enabled | Comments arrive with no thread data and no error. **Startup assertion refuses to boot.** |
| Week not approved by deadline | Backup pool publishes. Never auto-approve. |
| Higgsfield job fails or times out | Post publishes text-only rather than missing its slot |
| Voice Critic can't pass a draft in 3 rounds | Escalates to the admin group as a flagged exception |
| LLM proposes a number with no ledger row | Claims Guard strips it before a human ever sees the draft |

## 13. Boundaries

**CHATPLACE keeps the DM funnels.** It has 11 bots, but no channel is linked to any of them, its AI agent's
training errored, and comment replies are disabled. It is a lead-funnel tool that was never wired to the
channel. This system owns the **channel and discussion group**; CTAs point at `@lidcollect_bot` and
`@shalikhanova_bot` rather than reimplementing lead capture.

**Out of scope entirely:** Uzbek business registration, education-licensing status, and Payme/Click merchant
eligibility for Sweden residents. These affect the future course business and belong with a professional.

## 14. What the research killed

Recorded so it doesn't get reintroduced later: the 80/20 and 4-1-1 content ratios (citation-free folklore),
"inoculation decays after 13 days" (refuted at primary source — the original study reports the difference as
*not statistically significant*), the Schwartz attribution of "enter the conversation already occurring in
the prospect's mind" (it is Robert Collier, 1931), Jeff Walker's "$1B in launches" (contradicted by the
vendor's own two sites), Wyzowl's video-trust statistics (n=266, self-reported belief about influence), and
**Higgsfield's own documentation recommending "8k / highly detailed / professional"** — precisely the terms
that destroy photorealism.

What survived and is built on: foot-in-the-door (76% vs 17%, Freedman & Fraser 1966), Bandura's mastery
experiences as the strongest source of self-efficacy, the reversed pratfall effect for unestablished
competence, and the harm of templated replies.
