# Seedance 2.0 vs 2.5 — a physics test, not a spec sheet

Founder direction, 2026-08-23: comparing these two on resolution and duration is
spec-sheet trivia and nobody argues with a table. Compare **what the motion
actually does**, and design a shot that makes the difference visible without
anyone needing to read a number.

## What is genuinely known, and what is not

**Known, from the live catalog:**

| | Seedance 2.0 | Seedance 2.5 |
|---|---|---|
| Framing in the catalog | reference-driven, identity-consistent, multi-SKU, e-commerce | text-to-video, omni-reference, video edit, video extension |
| Resolution | to 4K (`mode='std'`) | to 1080p |
| Duration | 4–15s | 4–30s |
| `genre` hint | yes | no |
| Edit / extend an existing clip | no | yes |

**Not known, and not guessable: how the two differ in motion.** Neither the
knowledge base nor the catalog says anything about physics, and there is no
published figure to cite. This document does not claim one is better. It
specifies the test that would tell us.

## Why a physics test discriminates when a pretty shot does not

Both models make a good-looking still frame; Monday's post already showed that
image realism is a wash and depends on the light. Motion is where generators
still diverge, because a plausible frame only has to look right once, while
plausible motion has to stay right across every frame and obey the same rules
throughout.

The failures worth testing are the ones a member can point at without knowing
anything technical:

1. **Fluid continuity and volume** — a pouring stream must stay connected from
   spout to vessel, narrow as it accelerates, and the liquid that leaves must
   arrive. Models break the stream into floating beads or fill a cup from
   nowhere.
2. **Angular momentum** — a spun object wobbles in a characteristic way, and the
   wobble *speeds up* as it flattens. Everyone has watched this happen and
   everyone recognises it when it is wrong.
3. **Ballistic arc** — a thrown object accelerates downward at a constant rate.
   Models float things or vary the rate mid-flight.
4. **Hand–object contact** — fingers must stay attached to what they hold.
   Notoriously the first thing to fail.
5. **Cloth secondary motion** — a sleeve follows the arm a beat late and then
   settles. Models move cloth as though it were rigid.
6. **Temporal drift** — does second 8 hold together as well as second 2? This one
   matters especially here, because 2.5 claims 30 seconds against 2.0's 15.

## The two shots

Both are ordinary Uzbek objects on purpose. The audience should recognise the
action instantly, because the whole test is whether *they* can see something
wrong — and a viewer only spots wrong physics in something they have watched a
thousand times.

### Shot A — the pour

Tests fluid continuity, volume conservation, steam buoyancy, cloth lag, and hand
contact, all in one continuous take.

```
Real-time, no slow motion. One continuous locked-off shot, no cuts.

ACTION, in this order: a hand lifts a small ceramic teapot, tilts it, and pours a
thin unbroken stream of amber tea from about 30cm above a white piala standing on
a wooden table. The stream runs for roughly four seconds. Then the hand tips the
pot upright and the stream cuts off cleanly.

PHYSICS THAT MUST HOLD:
- The stream stays connected from spout to cup for the whole pour. It does not
  break into beads and it does not float.
- The stream narrows as it falls, because it is accelerating.
- The tea level in the piala rises visibly as it fills, and the surface moves
  where the stream lands.
- Steam lifts off the surface and curls upward. It never falls.
- The loose sleeve of her robe follows the arm a moment AFTER the arm moves, then
  settles. It is cloth, not board.
- The fingers stay in contact with the handle for the entire shot.

CAMERA: low, at table level, just below the rim of the piala, looking slightly
up. Mid shot. 50mm at f/2.8. Locked off — the camera does not move at all.

LIGHT: one hard window from camera-left, placed so the falling stream catches a
bright highlight down its edge and the steam is lit from behind.

DETAIL: condensation on the teapot glaze, grain in the wooden table, the meniscus
where tea meets porcelain.

AUDIO: the sound of pouring and the room. No music, no speech.

DO NOT INCLUDE: slow motion, camera movement, cuts, subtitles or any text, brand
names, logos, watermarks, a second person.
```

### Shot B — the spin

A single hard test of angular momentum. Harder than the pour, and the failure is
unmistakable because everybody has spun something on a table.

```
Real-time, no slow motion. One continuous locked-off shot, no cuts.

ACTION: an empty white piala is spinning upside down on a wooden table, already
in motion when the shot begins. Over the shot it loses energy, tips further onto
its rim, and rattles to a stop.

PHYSICS THAT MUST HOLD:
- As the piala flattens toward the table, the rattle gets FASTER and the pitch
  rises. This speeding-up as it settles is the whole point of the shot.
- The contact point travels around the rim; the piala itself barely rotates by
  the end.
- It finishes flat and still. It does not stop abruptly and it does not drift
  sideways.
- The shadow under it stays attached to the rim throughout.

CAMERA: table level, very low, looking straight across the surface. Close mid
shot. 50mm at f/2.8. Locked off.

LIGHT: one hard source from camera-right, raking across the table so the moving
rim throws a long travelling shadow.

AUDIO: the rattle only, rising in pitch as it settles. No music, no speech.

DO NOT INCLUDE: slow motion, camera movement, cuts, subtitles or any text, brand
names, logos, watermarks, hands, a person.
```

## How to run it so the answer means something

- **Same resolution on both.** 720p for each. 2.0 can reach 4K and 2.5 cannot, and
  running them at different resolutions would confound sharpness with physics —
  the post would credit 2.0 with motion quality it was simply given more pixels
  for. That mistake already nearly happened with Veo 3.1, which came back at
  1080p while everything else ran at 720p.
- **Same duration.** 8 seconds, inside 2.0's 15-second ceiling.
- **No speech.** Ambient only. Uzbek pronunciation is unjudged and belongs in its
  own post, not smuggled into a physics comparison.
- **Both shots on both models.** One shot may not discriminate; if both handle the
  pour and only one handles the spin, that is the finding.
- **Run each shot twice per model.** These are sampled, not deterministic. One
  clip is an anecdote — the reply eval taught that the hard way when the same
  model scored 11, then 9, then 10 on identical fixtures.

That is 2 shots × 2 models × 2 takes = 8 clips, roughly 260 credits at 8s.

## What the post becomes

The caption cannot be written until the clips exist, and it must report what
happened rather than what was expected. Monday's post is the model for that: it
was written assuming one model would win, the test said otherwise, and saying so
is what made it worth reading.

What the post CAN commit to in advance is telling the viewer exactly where to
look — "watch where the stream leaves the spout", "listen for the rattle speeding
up". A comparison nobody knows how to judge gets scrolled past.
