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
- **The Replier's model is `REPLY_MODEL` in the environment, not a constant.** `app/agents/llm.py`
  routes by model-id prefix (`claude-*` → Anthropic, `gpt-*`/`o1`/`o3` → OpenAI) and translates the
  Anthropic tool shape into an OpenAI function, so every agent still carries one schema. Structured
  output is **forced** on both vendors — a model answering in prose is a model the grounding gate
  cannot inspect. Switching vendors needs a key and a compose env change, nothing else. Preflight
  refuses to boot if `REPLY_MODEL` names a vendor whose key is missing, because otherwise the bot
  boots green and *every* comment escalates, which reads as caution rather than a missing variable.
  Compare candidates before switching: `scripts/eval_replies.py` scores any model against
  `data/evals/replies.yaml` and exits non-zero on a failure, so it can gate the switch;
  `scripts/compare_replies.py` prints two models' Uzbek side by side for a human to read.
  **Run it with `--trials 3`.** One run is an anecdote — the same model scored 11, then 9,
  then 10 on the same fixtures in three consecutive runs. A case counts as clean only if it
  passes every attempt: a case that passes two runs in three is not two-thirds safe, it is
  one that publishes something wrong every third time it comes up.

  The eval asserts **decisions, not wording** — answered vs escalated, which knowledge keys
  were cited, whether the script mirrored the member, and whether a forbidden thing was said.
  There is no correct sentence for "Promp boyicha qldim", and pinning one makes the eval fail
  good output, which is how an eval gets switched off. Its first run produced three failures
  and **all three were the scorer's fault**, not the models': a regex that matched the negated
  form of the phrase it was banning, an assertion that a safe inline refusal must instead
  escalate, and exact-matching a grounding key against a model that cited a more specific
  sub-key. Each is now a unit test in `tests/test_evals.py`. A false failure is worse than no
  eval.

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
python -m pytest tests/                                   # no credentials or network needed
python scripts/eval_replies.py --trials 3                 # score the configured model
python scripts/eval_replies.py --models gpt-5.6-luna gpt-5.6-sol claude-opus-5 --trials 3
python scripts/compare_replies.py                         # read two models side by side
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

## Writing the week by hand

`data/planned_posts.yaml` keys a hand-written post to a slot and **wins over the Writer**,
replacing whatever it already drafted. Everything downstream is unchanged — still approved by
Shahlo, still published the same way, still covered by the backup pool. Lint runs at LOAD: a slot
whose text fails falls through to the Writer rather than shipping something broken at 10:00.

Its `drafts:` section holds finished copy whose visual does not exist yet. `load()` reads only
`posts:`, so nothing there can publish; move an entry up once its asset is in the library.

**Approval cards are the post** — the visual is bound at DRAFT time and the card is sent as that
image with the caption under it, so what is approved is what ships. Reply to a card with corrected
text to replace the post outright (faster than ✏️, which costs an LLM round-trip). Reply to a
🔴 escalation with an answer and it is relayed into the member's comment thread verbatim.

## Traps found by looking at output, not by reasoning (`COMMERCIAL_GUARDS` in `app/media/shots.py`)

- **The model adds what you did not ask for.** A camera came back stamped *Canon*, a shoe with a
  Nike swoosh, ratings of 4.6 and 4.8 nobody specified. Always forbid explicitly.
- **It reproduces strings faithfully and quantities not at all.** «6 KISHILIK TOʻPLAM» over five
  bowls; saying "EXACTLY SIX" three ways produced seven, then eight. What worked was compositional —
  *two rows of three, spaced apart*. Anything a customer could count belongs in type you set.
- **Nothing checks a headline against its own picture.** Lint reads the caption, the claims ledger
  reads numbers in text, neither can see inside a PNG.
- **Telegram caps a photo fetched from a URL at 5MB.** A 2K card crosses it; the only symptom is
  "failed to get HTTP URL content". `_deliver` now falls back to fetching and uploading the bytes.
- **`editMessageText` refuses a photo.** A card carrying a visual is edited by caption.

## Current state

**Live on Hostinger VM 1411263** as the `tgcommunitymanager` Compose project, alongside `freelanceai` and
the untouchable `smmuzbot`. All eleven preflight checks green. Deploy with `python deploy/deploy.py` — and
**wait for the CI build to go green first**, or it pulls the previous image.

Working: publisher + seeder (proven on post [606](https://t.me/aicreatorsuz/606)) · comment classifier and
thread resolver · Replier with grounding gate, script mirroring and react-instead-of-reply · scheduler with
missed-run recovery · content state machine · SQLite store · day-ahead approval cards · Writer + Voice
Critic + mechanical lint + claims ledger · media library with 15 tagged assets · runtime loop · deployment.

**357 tests**, no credentials or network needed.

Visuals: a library asset when one genuinely matches, otherwise a **card rendered on the VPS**
(`app/media/cards.py`, Pillow). Cards exist because `challenge`, `recognition` and `behind_scenes`
have no photograph that fits and were publishing bare text. The font is asserted at boot — Uzbek
`oʻ`/`gʻ` are U+02BB and plenty of fonts have no glyph for it (Arial Narrow does not, DejaVu does),
so a missing glyph is an invisible blank in a headline. The visual is bound at DRAFT time and the
approval card is sent as that visual with the post as its caption, so what is approved is what ships.

Content standard: posts target 600 chars, hard cap 900 (Telegram truncates captions at 1024). Media is
16:9, stills 2K, video 720p. Every post ships with a visual when one genuinely matches; a mismatch is worse
than none, so it falls back to text.

The recurring bug shape, six times in one session: **state recorded instead of outcome verified.**
The card committed before sending; the revise button moved content to DRAFTING which nothing
redrafted; the pool never retired a disproved post; the Writer's seed comment was generated and
discarded; a plan could not override a draft; a failed send logged itself as sent. Every one looked
healthy and did nothing. Prefer verifying the result over recording the intent.

Not started: M2 Mini App batch review · most of M4 (batch generation, variant contact sheet) · M5 analyst
and the ~87-post shot-vocabulary content spine.

Still needed from the founders: the **Story Bank** (origin story, the Sweden conference, own client work,
portfolio, boundaries), which gates behind-the-scenes content only — the Planner substitutes and flags the
gap rather than inventing anything.

Next visual worth shooting: a **before/after pair** for technique posts — a garbled Uzbek word beside a
clean plate with type overlaid. The café assets are evidence for why-content and commercial-craft, but only
thematic for technique.
