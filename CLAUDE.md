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

Branch `docs/design-spec`. **55 tests pass** (`python -m pytest tests/`) with no credentials or network.

**M0's hardest criterion is proven live.** Post [606](https://t.me/aicreatorsuz/606) published to the real
channel, the auto-forward was caught in 2.7s, and the seed comment landed inside thread root 3. Channel-side
id 606 against group-side 3 is the concrete proof that the two id spaces are unrelated.

Built: spec · milestones · research base · `humanize-uz` v1 · comment classifier + thread resolver ·
config + preflight (incl. bot-identity guard) · publisher + seeder · Uzbek apostrophe normalizer ·
`scripts/smoke_publish.py`.

**The founders have approved the Uzbek voice output** — the published post and seed comment were accepted
as-is, so `humanize-uz` v1 is validated in production and no native-speaker review is pending.

**Next:** M1 — the content state machine, the scheduler at 10:00/21:00 Asia/Tashkent with missed-run
recovery, and the backup pool. Then the Writer / Voice Critic / Claims Guard agents, then deployment.

Still needed from the founders: their two `telegram_id`s for the Mini App allowlist, and the **Story Bank**
(founder origin story, the Sweden conference, own client work, portfolio, boundaries) which gates
behind-the-scenes content only.

Watch post 606 for real member comments — actual Uzbek from members is far better material for building
Triage and the Replier than anything invented.
