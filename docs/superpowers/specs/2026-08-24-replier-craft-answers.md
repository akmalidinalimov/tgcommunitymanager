# Spec — the Replier answers craft questions

**Trigger.** A member asked, under a published post:

> qanaqa promt yozish kere bunaqa realistik chiqishi uchun

The bot escalated it. It should not have. Nothing in that question is about our
prices, our clients or our results — it is craft technique, the thing this
channel exists to teach, and the founders should not be the bottleneck for it.

## The problem, stated precisely

The grounding gate is binary. A fact is either in `data/knowledge/models.yaml`
or the question escalates. That rule is correct and must not be weakened for the
class it was built for: being confidently wrong about Kling's pricing in front of
3,326 people costs more authority than silence.

But the rule is applied to *every* class of question, and craft technique is a
different class:

- It is not proprietary. How light behaves in a photograph is not our secret.
- It is not volatile. A focal length does not change price next month.
- Being wrong is recoverable. A member tries the advice, it works or it does not.
- **We have better evidence than anyone.** This channel has spent a week
  producing tested, written-down findings about exactly this.

So the change is not "loosen the gate". It is "the gate was asking one question
where it should ask two": *is this about something we own or something that
costs money* — and only then, *is the fact present*.

## What must NOT change

Non-negotiable, because these are the reasons the architecture exists:

| Class | Behaviour | Why |
|---|---|---|
| Our own work — which model made our video, our settings, our results | knowledge base or escalate | A guess about our own output is a lie a member can check |
| Prices, credits, subscription plans | research with the strict gate, else escalate | Founder direction, and the main legal exposure |
| Our course, our services, what we charge | escalate, always | Business decisions are not the bot's |
| Anything about a member's own results or earnings | escalate | No testimonial or outcome claims, ever |
| A capability claim about a tool we have not run | say we have not tested it | Already the rule and it holds |

## What becomes answerable

**Craft technique**, from a new knowledge base of what we have actually tested
and published. Not from a general web search, and the distinction matters.

A live search for "how to write a realistic image prompt" returns generic
listicles, often wrong, usually English, and repeating them makes this channel a
translator of other people's advice. The differentiator is *we tested this*. So
the craft base is built from our own worked evidence, and every entry carries
what proved it.

We already own an unusually good corpus of it, produced this month:

- **Light is the biggest single lever.** The dappled-light test: GPT and Nano
  swapped places purely on lighting, and the prompt that worked spent ten
  sentences on light alone.
- **Camera is a position, not an adjective.** Height in centimetres, lens,
  aperture, and whether it moves. "Cinematic" is not an instruction; "40cm above
  the grass, 50mm at f/2, slow push in" is.
- **Build the frame in layers.** Foreground, midground, background as separate
  blocks. The foreground is what most people omit and it is what creates depth.
- **Say what must NOT be there.** Found by looking at output: a camera came back
  stamped with a manufacturer's name, a shoe with a swoosh, ratings of 4.6 and
  4.8 nobody asked for. Every prompt carries an explicit negative list.
- **Models cannot count, but they can compose.** "EXACTLY SIX" produced seven
  then eight; "two rows of three" produced six first time.
- **Text in an image: dictate it.** `reading exactly:` reproduces a string
  verbatim, okina included. Without it the model invents its own words — and
  writes them in correct Uzbek in the wrong register.
- **For video, name the physics.** What must stay in contact, what must
  accelerate, what must not float.
- **A model does not know your city.** Naming a local landmark gets an
  approximation; a real place needs a reference image.

That list is worth more to an Uzbek beginner than any search result, and every
line of it is defensible because we published the evidence.

**Research widens beyond prices.** `is_price_question` is the only trigger today.
It becomes one of several: a question about a tool we do not have, a model
released after our knowledge base was written, a feature we have never run. Same
strict gate — vendor's own page, source and date quoted, high confidence, or it
escalates with the evidence attached.

## The register problem, which is real

The comment register is one sentence, 3–12 words, no closing offer. That rule
came from a blind test that scored 0/3, and every failure was a reply being *too
complete*.

But those failures were **social** replies — to praise, to a sceptic, to "is it
free". A member asking "what should I write to get this look" is asking a
technical question and wants an actual answer. Three words is not warmth there,
it is a brush-off.

So a second register, used only for a direct how-to:

- Up to three short sentences, still no greeting and no closing offer.
- Lead with the single highest-leverage thing, not a list of six.
- Where we have published a worked prompt, point at it rather than paraphrasing.
- Never a numbered listicle in a comment. That is a post, not a reply.

This is a narrow exception and it must stay narrow: the escape hatch that turns
every reply into a paragraph is exactly how the 0/3 happened.

## Build order

1. **`data/knowledge/craft.yaml`** — the craft base, each entry carrying the
   evidence that proved it. Highest value, lowest risk, no code change.
2. **Question classification** — craft / ours / money / capability. A message can
   be more than one; money always wins, then ours, then craft.
3. **The teaching register** in the Replier prompt, gated on the craft class.
4. **Eval cases** for the new behaviour, including the ones that must still
   escalate — the guard against this change quietly becoming "answer everything".
5. **Research beyond prices**, last, because it is the highest-risk piece.

## How we will know it worked

The eval already asserts decisions rather than wording. New cases:

- The real member question answers, cites craft keys, and does not escalate.
- A price question still escalates. A course question still escalates.
- "Which model made your video" still answers only from `our_posts`.
- A craft answer stays inside three sentences and carries no closing offer.
- A question mixing craft and price escalates, because money wins.

Run at `--trials 3`. A case that passes twice in three is not two-thirds safe.
