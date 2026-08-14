# What the warm-up bot spec gives the community manager

Source: `webinar-warmup-bot-spec.md` — the 7-day gamified warm-up built to lift live webinar
show-up rate from ~10% toward 25–30%, and to convert a free week into course sales.

The two bots share an audience, a channel, a voice and a pair of founders. They do **not** share a
goal. The warm-up bot is a sprint that ends in a sale. This one is an evergreen channel whose entire
value proposition is that it is *not* selling. So the spec splits cleanly into three piles: things
worth taking now, things worth taking with adaptation, and things that would actively damage this
channel if copied across.

---

## The one thing to settle first: they share a message budget

The spec's law #2 is measured, not folklore: **3+ marketing messages a day cost ~30% reach** on the
founders' own channel, which is why the warm-up runs two posts a day.

This bot also posts twice a day. **If both bots run on `@aicreatorsuz` at once, that is four posts a
day into an audience the founders' own data says tolerates two.** The reach penalty lands on both,
and the community manager — which has no launch deadline to justify the cost — loses more.

Three ways out, in order of preference:

1. **Pause this bot's cadence during the warm-up week.** The backup pool and the scheduler already
   support a slot going quiet; it needs a documented switch rather than a code change.
2. **Hand the slots to the warm-up bot for those seven days** — this bot keeps replying to comments
   and seeding threads, and stops publishing.
3. Run the warm-up on a separate channel and accept the lead cost of building an audience twice.

There is a second collision underneath it: **two bots replying in one discussion group.** The
CHATPLACE boundary is already documented — CHATPLACE owns DM funnels, this bot owns the channel and
group. The warm-up bot needs the same explicit line drawn before it ships, or members get two
different automated voices answering the same comment.

---

## Adopt now

### 1. Render cards server-side — HTML or Pillow → PNG

The single highest-value item in the spec, and it closes a gap that is live today.

Founder direction is that **every post ships with a visual**. Three post kinds currently have no
asset tagged for them at all — `challenge`, `recognition`, `behind_scenes` — so they publish as bare
text, quietly breaking that rule. Media is also generated on the laptop through the Higgsfield MCP,
which is session-bound and cannot run from the VPS; that makes every visual dependent on a batch
session having happened.

A template renderer fixes both. It costs nothing per image, runs on the VPS, and is pixel-identical
every time, which is how a channel becomes recognisable at a glance.

What it unlocks immediately:

| Post kind | Today | With a renderer |
|---|---|---|
| `recognition` | bare text | a member's work credited by name on a branded card |
| `challenge` | bare text | the brief as a card, with the prompt legible |
| `recap` | reuses the news banner | a real weekly summary card |
| `news` | one reused banner image | headline typeset per story |
| `technique` | photo + caption | the prompt itself as a readable card |

**Where I'd differ from the spec: use Pillow, not Playwright.** The warm-up bot renders ~3,000
scorecards a night, which justifies a headless Chromium. This bot renders two cards a day. Chromium
adds roughly 400MB to an image that is currently small enough to deploy through the Hostinger API in
seconds; Pillow adds about 3MB. If typography later demands real CSS, swapping the renderer behind
one function is a contained change.

Brand tokens are already specified and should be reused verbatim so both bots look like one studio:
Coral `#DC6D55` · Ink `#242323` · Paper `#FCF8F6`, with the 🇸🇪 founder footer and the AI Creators
Studio wordmark.

**Uzbek caveat:** the font must carry `oʻ` and `gʻ` — the okina is U+02BB, not an apostrophe. Pick and
pin a TTF that renders it, and test it before trusting it. This is the same class of assumption that
produced the "AI cannot write Uzbek" claim that turned out to be false.

### 2. Inline Edit in the approval flow

The spec's §8 offers **Approve / Edit / Reject**, where Edit means the admin sends corrected text and
the bot posts *that*.

This bot only has Approve / Revise / Reject, and Revise triggers a full LLM redraft — a round-trip of
a minute or two that returns something Shahlo did not write. When a card is 90% right and one line is
wrong, retyping the line is faster than re-rolling the post and hoping.

The admin DM routing added today is the missing piece; this now sits directly on top of it. Press
Edit, send the replacement text, the bot stores it as approved content.

### 3. "N unanswered questions are waiting for you"

Spec §13.2: the bot flags to the admin when the community is owed a human answer.

There is already an escalation queue for pricing, complaints and sensitive topics, but nothing that
tells the founders *the community is waiting*. This is the smallest feature in the document with the
most direct line to the one-hour-a-week goal — it converts "check the channel in case" into "the bot
told me there are three."

---

## Adopt with adaptation

### 4. The DM asset — the spec's most important technical insight

Spec §14: **a Telegram bot cannot message a user who has not started it first. No setting changes
this.** Once a member taps start, the bot can DM them freely, forever.

This bot currently ignores every DM that is not from the admin. Every member who has ever written to
it privately has been dropped. That is a standing asset going unclaimed — and it is the only channel
that survives a member muting the channel, which the spec says 90% of leads do.

**But the obvious way to get the tap is forbidden here.** `data/post_formats.yaml` states plainly that
withholding a post's prompt to drive engagement is the bait pattern this channel does not use. So the
tap has to be bought with something genuinely additional, never with the thing the post already
promised:

- the *variant pack* — four alternate framings of tonight's prompt, when the post already gave one
- a weekly digest of everything published, for people who mute channels but read DMs
- "send me your result and I'll tell you which part of the prompt did the work"

The third is the strongest, because it produces exactly the member-generated artifacts that are this
channel's north-star metric, and it happens in private where a beginner is not embarrassed.

### 5. The segment model, as instrumentation

Spec §4's S0–S4 and the S3 "quiet / cooling" nudge with a **new angle rather than a repeated pitch**
are sound and match the research base already in this repo.

**Honest caveat: it is premature.** The discussion group has 3 members against the channel's 3,326.
Segmenting three people is theatre. This belongs with the M5 Analyst, after the comment section has
any population at all, and the spec's own framing supports waiting — every feature is justified only
by whether it serves the one metric.

What *is* worth doing now is the cheap half: record which rung of the commitment ladder each
commenter has reached — reacted, commented, asked, posted work. That is a column, not a subsystem,
and it makes the segmentation trivial later.

### 6. Peer connection, and rewarding it

Spec §13.4 and the 3-point peer-encouragement action in §5 target the thing that separates a
community from a broadcast: members talking **to each other**.

The Replier already has the defensive half — `do_not_interrupt_members` keeps the bot out of the way
when a member has answered another member. The missing half is the active one: CTAs and thread seeds
that ask members to respond to *each other's* results rather than to the founders.

Given a comment section that has effectively never been used, this is the mechanism that decides
whether it becomes a room or stays a suggestion box.

### 7. Latecomer welcome — one line of plumbing away

Spec §13.3: warmly onboard people who arrive mid-stream so they do not feel lost and quit.

This bot subscribes to `["message", "channel_post", "callback_query"]`, so **joins are invisible to
it**. Adding `chat_member` makes new members visible. The DM rule still blocks a private welcome
until they tap, which is another reason item 4 matters.

### 8. Their measured data validates three choices already made here

Worth recording in `docs/research/` as *measured*, because the research base is otherwise strict
about separating verified findings from folklore — and several plausible-sounding claims were already
killed for lacking a source.

- **≤2 posts/day; 3+ measured −30% reach.** Validates the 10:00/21:00 cadence, and sets it as a
  ceiling rather than a starting point.
- **One message = one job = one CTA.** Twelve near-duplicate closing messages once collapsed
  reactions from 300+ to 3–8 on their own channel. This is the strongest evidence yet for the
  one-CTA rule in `post_formats.yaml`.
- **Demonstrate before claiming.** An AI-character video out-engaged everything at 680+ reactions.
  Direct support for the visual-first direction.

---

## Do not adopt

### Law #7 — "every proof has a name, age, and number"

The spec requires social proof in the form *"Shahzoda — 8,000,000 soʻm", "44 yoshda — $240"*.

This is the clearest conflict in the document, and it is not a close call. Two hard rules here forbid
it: **no student or testimonial content** — a founder decision that removes the main legal exposure —
and **no invented numbers**, enforced by a schema check against the claims ledger. Income framing is
always *"businesses pay X for deliverable Y"*, never *"you can earn X"*.

The warm-up bot can carry a different risk posture because it is a time-boxed launch with the
founders' direct attention on every message. This bot publishes unattended, twice a day, forever. The
asymmetry is the whole reason the rule exists.

### Points, tiers, discount codes

Course selling is explicitly out of scope. Bolting a currency onto a trust-building channel changes
what people think the channel is for — and the spec's own reward design points every point at a
purchase, which is exactly the framing being avoided here.

### The public leaderboard

Two reasons. It ranks three people, which is worse than not having one. And public ranking sets
members against each other in a channel whose product is trust — a beginner who places last in front
of 3,326 people does not come back.

Take §13.1 instead: **spotlight by name**, which is already the `recognition` post kind and needs
only the card from item 1 to become real.

### Manufactured deadlines

Law #3 is right that a deadline must actually execute — but a 7-day sprint earns urgency honestly
because it genuinely ends. An evergreen channel running countdowns is the pattern that trains an
audience to ignore countdowns.

---

## Suggested order

1. **Card renderer** — closes a live gap, removes the laptop dependency, unlocks four post kinds
2. **Inline Edit** — the largest reduction in founder review time available for the effort
3. **Unanswered-questions ping** — smallest build, direct line to the weekly-hour goal
4. **Settle the shared message budget** before the warm-up bot ships, not after
5. **The DM ladder** — design the earned tap, then build it
6. Peer-connection CTAs, then `chat_member`, then the ladder column
7. Segmentation and nudges with M5, once there are people to segment
