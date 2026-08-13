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

- **No LLM decides whether to publish.** The spine is deterministic; agents only write, judge and analyze.
- **No invented numbers.** Every figure must resolve to a claims-ledger row, enforced by schema check.
- **No student or testimonial content** — founder decision, and it removes the main legal exposure.
  Income framing is always *"businesses pay X for deliverable Y"*, never *"you can earn X"*.
- **Never auto-publish unreviewed content.** An unapproved slot publishes from the backup pool instead.
- **AI disclosure is required** (EU AI Act Art. 50, Sweden-based operator): display name, profile
  description, and a `🤖 AI yordamchi` line on the bot's first reply in each thread.
- **Secrets:** `.env` and `.mcp.json` are git-ignored. Gitignore has **no inline comment syntax** — a
  trailing `# comment` silently breaks the pattern. Always verify with `git check-ignore -v <file>`.

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

## Current state

Done: spec, milestones, research base, `humanize-uz` v1, comment classifier + thread resolver, config +
startup preflight. All on branch `docs/design-spec`.

Next: publisher → auto-forward listener → seed-comment flow, then the scheduler and backup pool.

Blocked on the founders: a private **test channel + linked group** (so the seed-comment flow can be proven
without posting to 3,326 people), the **Anthropic API key**, the **bot rename** to `Malika · AI yordamchi`,
and **Shahlo's review of the Uzbek** in `humanize-uz` — the one thing in this build that cannot be verified
without a native speaker.
