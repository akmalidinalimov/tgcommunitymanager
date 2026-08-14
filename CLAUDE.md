# tgcommunitymanager — project context

Autonomous Telegram community manager for **AI CREATORS** (`@aicreatorsuz`), an Uzbek-language
AI-education channel. It plans, writes, illustrates, publishes, seeds discussion, replies to comments and
reports — while the founders spend **one hour a week** approving a batch.

**Read these first, in order:**
1. `docs/superpowers/specs/2026-08-13-telegram-community-manager-design.md` — the design. Authoritative.
2. `MILESTONES.md` — six milestones with self-verifiable exit criteria, and current pre-flight status.
3. `docs/research/` — three adversarially-verified briefs (~27k words). Consult before making any decision
   about Telegram mechanics, the media pipeline, Uzbek voice, or engagement tactics.

## Non-obvious facts that will cost you a day if you miss them

**Telegram**
- There is **no Bot API call mapping a channel post to its comment thread.** The auto-forwarded copy landing
  in the discussion group is the only link, and it must be caught live. Updates older than 24h are dropped
  server-side and never replayed, so downtime permanently loses those threads.
- **`message_thread_id` is silently ignored on send.** The message posts to the group's main feed instead of
  the thread, with no error, in front of everyone. `reply_parameters.message_id` is the only correct
  mechanism. Cross-chat `reply_parameters` is permanently unusable.
- **Never filter on `from.is_bot`.** Telegram's synthetic senders `1087968824` (anonymous admin) and
  `136817688` (comment-as-channel) carry `is_bot: true` while representing real humans.
- `message_thread_id` on *incoming* messages is not proof of a comment thread either — Telegram sets it on
  any supergroup reply chain. See `app/telegram/classifier.py`.

**Voice** — the founders already own a corpus-measured voice system in a *different repo*:
`carousel-builder/blogs/ai-uz/` (`voice.md`, `voice-brand-archived.md`, `corpus/reels-scripts.md`).
`.claude/skills/humanize-uz/` derives from it. Its **language** rules are universal; its **length and
speaker** metrics measure Instagram carousels and must not be applied to Telegram posts.

**Deployment** — Docker Compose pushed through the **Hostinger API**, not SSH. There is no Hostinger SSH
key. Adapt `freelanceai/deploy/deploy-vps.ps1`. Target is VM `1411263`, as a separate project alongside
`freelanceai`. Compose `content` is capped at 8192 chars, and a known created-not-started flake needs an
explicit project-start call.

**Media** — generated on the laptop via the **Higgsfield MCP** during the weekly batch session, never from
the VPS (the connector is session-bound). The VPS bot only publishes assets already in its store.

## Hard rules

- **Never touch `smmuzbot` on VM 1411263.** It is the founders' live SMM bot and is explicitly off limits —
  do not stop, restart, redeploy, inspect its config, or modify it. Same for `freelanceai`. Deploys must
  always name the `tgcommunitymanager` project explicitly, because the Hostinger docker endpoint replaces
  the project it is given.

- **No LLM decides whether to publish.** The spine is deterministic; agents only write, judge and analyze.
- **No invented numbers.** Every figure must resolve to a claims-ledger row, enforced by schema check.
- **No student or testimonial content** — founder decision, and it removes the main legal exposure.
  Income framing is always *"businesses pay X for deliverable Y"*, never *"you can earn X"*.
- **Never auto-publish unreviewed content.** An unapproved slot publishes from the backup pool instead.
- **AI disclosure is required** (EU AI Act Art. 50, Sweden-based operator): display name, profile
  description, and a `🤖 AI yordamchi` line on the bot's first reply in each thread.
- **Secrets:** `.env` and `.mcp.json` are git-ignored. Gitignore has **no inline comment syntax** — a
  trailing `# comment` silently breaks the pattern. Always verify with `git check-ignore -v <file>`.
- **`.env` deliberately wins over the ambient environment.** This machine has a stray
  `TELEGRAM_BOT_TOKEN` in its Windows environment pointing at a different bot; with `setdefault`
  semantics it silently won and nearly published under the wrong identity. Preflight now also asserts
  `getMe().username` matches `TELEGRAM_BOT_USERNAME`. Do not "fix" the precedence back.
- **This machine sits behind a TLS-intercepting proxy** whose CA OpenSSL rejects. Use `truststore`
  (see `app/telegram/api.py`); certifi's bundle cannot verify `api.telegram.org` here. Never disable
  verification.
- **Windows consoles are cp1252** and crash printing the okina. Reconfigure stdout to UTF-8 in any
  script that prints Uzbek.

## Live configuration (verified 2026-08-13)

| | |
|---|---|
| Channel | `AI CREATORS` · `@aicreatorsuz` · `-1002708742288` · 3,326 members |
| Discussion group | `AI CREATORS Chat` · `-1004430366406` · **3 members** · topics off |
| Bot | `@malikamanager_bot` · `8662504476` · admin in both · privacy mode disabled |
| Approver | Shahlo — **single approver**, posts written in her first-person voice |

The discussion group having 3 members against the channel's 3,326 is the central product fact: Telegram
auto-joins a user on their first comment, so the comment section has effectively **never been used**. The
baseline is zero and bot-seeded first comments are the whole mechanism.

## Commands

```bash
python -m pytest tests/          # 30 tests, no credentials or network needed
```

## Spine traps that already bit us — all one bug, four times

Every one of these was **state committed before the side effect that gives it meaning**, guarded by a
check written as a negation. A slot then sits in a state nothing moves it out of, and the backup pool
covers silently, so the failure is invisible.

- **The approval card was sent after `save_content`.** A send that failed left the slot in
  `PENDING_APPROVAL` forever, because `prepare_upcoming` skipped anything "not REJECTED". Delivery is
  now recorded only on success, and any pending slot with no recorded delivery is resent.
- **`card()` interpolated model-written text into a `parse_mode="HTML"` message.** One `<` or `&`
  and Telegram rejects the card permanently, for that slot. Escape anything the Writer produced.
- **`request_revision` lands content in `DRAFTING`, which is not `REJECTED`.** Pressing
  ✏️ Qayta yozish therefore deleted the slot instead of revising it. Guards over `State` must be
  written **positively** (`NEEDS_DRAFTING = {...}`), never as `is not X` — a state added later falls
  through a negation silently.
- **Seeding the backup pool was additive only.** A post pulled from `backup_pool.yaml` for being
  factually wrong stayed in the live database and, at `times_used=0`, was the *next* post LRU would
  publish unattended. The file is only the source of truth because seeding now retires missing rows.

**Diagnostics.** `report_state()` dumps `last_seen`, per-slot content states and `backup_pool.times_used`
at every boot — the last of those is the only thing that distinguishes "fell back to the pool" from
"never reached `publish_slot`". Container logs do not survive a redeploy, so anything not printed at
boot is unrecoverable. In the admin chat: **`/pending`** resends every waiting card, **`/holat`** reports
next slot, queue depth and pool depth.

## Deployment traps that already bit us

- **A volume mounted over a path SHADOWS what the image baked there.** `tgcm-data` was mounted at
  `/app/data`, hiding the knowledge base and backup pool, so the grounding gate guarded an empty file
  while the bot looked healthy. Read-only content lives at `/app/data`; mutable state at `/app/state`.
  Preflight now refuses to boot if the resources are unreadable.
- **Gitignore matches unanchored directory names at any depth.** A bare `media/` silently excluded
  `app/media/` — the source module — while its tests were committed, so CI failed on an import that
  worked locally. Always `git check-ignore -v <file>`, in both directions.
- **Deploying immediately after a push pulls the previous image.** Wait for the build to go green.

## Current state

**Live on Hostinger VM 1411263** as the `tgcommunitymanager` Compose project, alongside `freelanceai` and
the untouchable `smmuzbot`. All ten preflight checks green. Deploy with `python deploy/deploy.py` — and
**wait for the CI build to go green first**, or it pulls the previous image.

Working: publisher + seeder (proven on post [606](https://t.me/aicreatorsuz/606)) · comment classifier and
thread resolver · Replier with grounding gate, script mirroring and react-instead-of-reply · scheduler with
missed-run recovery · content state machine · SQLite store · day-ahead approval cards · Writer + Voice
Critic + mechanical lint + claims ledger · media library with 9 tagged assets · runtime loop · deployment.

**~240 tests**, no credentials or network needed.

Content standard: posts target 600 chars, hard cap 900 (Telegram truncates captions at 1024). Media is
16:9, stills 2K, video 720p. Every post ships with a visual when one genuinely matches; a mismatch is worse
than none, so it falls back to text.

Not started: M2 Mini App batch review · most of M4 (batch generation, variant contact sheet) · M5 analyst
and the ~87-post shot-vocabulary content spine.

Still needed from the founders: the **Story Bank** (origin story, the Sweden conference, own client work,
portfolio, boundaries), which gates behind-the-scenes content only — the Planner substitutes and flags the
gap rather than inventing anything.

Next visual worth shooting: a **before/after pair** for technique posts — a garbled Uzbek word beside a
clean plate with type overlaid. The café assets are evidence for why-content and commercial-craft, but only
thematic for technique.
