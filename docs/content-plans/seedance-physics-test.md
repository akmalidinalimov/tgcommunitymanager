# Seedance 2.0 vs 2.5 — a physics test at full capability

Founder direction, 2026-08-23, in two passes. First: comparing these two on
resolution and duration is spec-sheet trivia and nobody argues with a table —
compare what the motion actually does. Then: stop testing with a locked-off
camera and one event. Use the most cinematic camera available, move it, and
stack **simultaneous** difficult physics so the models are run at the limit of
what they can do.

Both corrections were right, and the second one changes the method, not just the
staging.

## What is genuinely known, and what is not

**Known, from the live catalog:**

| | Seedance 2.0 | Seedance 2.5 |
|---|---|---|
| Catalog framing | reference-driven, identity-consistent, multi-SKU, e-commerce | text-to-video, omni-reference, video edit, video extension |
| Resolution | to 4K (`mode='std'`) | to 1080p |
| Duration | 4–15s | 4–30s |
| `genre` hint | yes | no |
| Edit / extend an existing clip | no | yes |

**Not known and not guessable: how the two differ in motion.** Neither the
knowledge base nor the catalog says anything about physics, and there is no
figure to cite. This document specifies the test. It does not predict the result.

## Why a moving camera and simultaneous events

A locked-off camera on a single event is a clean experiment and a weak one.

**A static frame lets a model cheat.** With the viewpoint fixed, plausible motion
can be produced by warping a flat image. Move the camera and that fails
immediately: parallax has to be correct at every depth, things have to occlude
and reveal each other in the right order, and a round object has to stay round
from every angle. A model that survives a moving camera is genuinely holding a
3D scene rather than painting frames.

**A single event flatters the model.** Generators allocate their coherence to
whatever the prompt makes the hero. Give them one pouring stream and they will
usually get the stream right. Give them four independent dynamic systems at once
and the secondary ones drift — which is exactly the failure that ruins a real
commercial shot, because a client notices the thing you were not looking at.

So: one continuous take, camera moving through a compound move, with four
physics systems running concurrently, none of them nameable as *the* subject.

## The format

**IMAX 65mm, 15-perf, for both models.** Not decoration — it changes the picture
in ways that are worth asking for. Large format gives shallow focus at wide
angles, so the shot can be wide enough to hold four simultaneous events and still
isolate the subject; and the IMAX cue pushes the model toward extreme fine detail
and high dynamic range.

Delivered **16:9**. True IMAX is 1.43:1, nearly square, which would fight the
channel's own aspect standard for no gain. Digital IMAX is 1.90:1, close enough
to 16:9 that asking for the look and delivering 16:9 is honest.

## Shot A — the potter's wheel

The hardest physics scene that can be filmed with ordinary objects, and it
continues the Rishtan thread already in the media library.

**Four systems, all running at once, none of them the hero:**

1. **Soft-body deformation under continuous contact** — clay rising between two
   hands, changing shape every frame while the hands never leave it. This is the
   single hardest thing on the list: contact and deformation simultaneously.
2. **Rigid rotation at constant angular velocity** — the wheel and the pot must
   turn at a steady rate. Any wobble in that rate is instantly visible.
3. **Fluid** — water and slip running down the wall of the pot and pooling.
4. **Ballistic particles** — flecks of slip flying off the rim, each on its own
   arc, leaving the rotating surface tangentially.

```
Shot on IMAX 65mm, 15-perf. One continuous take, no cuts. Real time, no slow motion.

CAMERA: 50mm on this large format, which reads wide-normal. T2.8, so focus is
shallow even at this width — the clay is sharp and the workshop behind it falls
away. The camera begins low and to the potter's right, level with her hands, and
performs one compound move over the whole shot: it arcs anticlockwise around the
wheel through roughly forty degrees, pushes in slowly, and descends until it
finishes just above the wheel head, looking slightly up at the rising clay. The
move is slow, weighted and continuous. It never stops, never cuts, never snaps.

SUBJECT: an Uzbek potter's hands throwing a tall pot on a kick wheel in a
workshop. Wet grey clay. Her sleeves are pushed back. Only her hands and forearms
are in frame for most of the shot.

FOUR THINGS HAPPEN AT THE SAME TIME, and none of them is the main event:
1. The clay rises between her hands and narrows as it grows taller.
2. The wheel and the pot turn at a constant steady speed.
3. Water and liquid slip run down the outside of the pot and pool on the wheel head.
4. Flecks of slip fly off the spinning rim.

PHYSICS THAT MUST HOLD:
- Her fingers stay in contact with the clay for the entire shot. The clay deforms
  where they press and keeps the new shape as it rotates round.
- The rotation rate stays constant. It does not surge, stall or reverse.
- The pot stays circular from every angle as the camera arcs around it.
- Slip leaves the rim tangentially, not radially, and each fleck falls on its own arc.
- Water runs downhill, follows the curve of the pot, and pools where it lands. It
  does not appear from nowhere and it does not climb.
- As the camera moves, the workshop behind resolves with correct parallax: near
  shelves travel across the frame faster than far ones, and things that pass
  behind the potter reappear unchanged on the other side.

LIGHT: one high window from camera-left, hard enough to put a bright specular
line down the wet clay that travels as the pot turns. The workshop behind sits
two stops under. Dust hangs in the window light.

DETAIL: wet clay sheen, fingerprints and drag marks left in the surface, grit in
the slip, the grain of the wheel head, water beading on skin.

AUDIO: the wheel, wet clay under hands, water. Room tone. No music, no speech.

DO NOT INCLUDE: slow motion, cuts, subtitles or text of any kind, brand names,
logos, watermarks, a second person, a face.
```

## Shot B — the tandyr

A different class of failure entirely: atmospherics and emissive light rather
than contact and deformation. Running both means a model that wins one and loses
the other is visible as such, instead of averaging into "better".

**Four systems, concurrent:** combustion and the light it throws, heat
refraction, airborne particles under gravity, and adhesion of a soft body to a
vertical surface.

```
Shot on IMAX 65mm, 15-perf. One continuous take, no cuts. Real time, no slow motion.

CAMERA: 40mm on large format, T2.8. The camera starts high, looking down over the
baker's shoulder into the open mouth of the tandyr, and cranes down and forward
in one continuous weighted move, ending low and close beside the rim, looking
across the glowing wall. Slow, deliberate, never stopping.

SUBJECT: a baker at a clay tandyr before dawn, reaching in to slap a round of
raw non dough onto the hot inner wall.

FOUR THINGS HAPPEN AT THE SAME TIME:
1. Coals burn at the base of the tandyr, throwing unsteady orange light upward.
2. The air above the mouth shimmers with heat.
3. Flour dusts off the dough as it moves and drifts down through the light.
4. The dough meets the wall, flattens against it, and sticks.

PHYSICS THAT MUST HOLD:
- The firelight flickers and everything it lights flickers WITH it, in the same
  instant — his forearm, the rim, the smoke. Light and lit must not drift apart.
- Heat shimmer distorts what is seen THROUGH it and nothing else. The rim behind
  the shimmer bends; the rim outside it stays straight.
- Flour particles fall, drift and settle. They do not rise and they do not hang.
- The dough deforms on impact, spreads slightly, and stays where it is put. It
  does not slide down and it does not bounce.
- His hand withdraws without dragging the dough with it.
- As the camera cranes down, the tandyr mouth stays a circle and the coals stay
  in the same place in the world.

LIGHT: the coals are the only source, low and warm and unsteady. Everything above
the rim falls to near black. Cold blue pre-dawn sky just visible at the top of
frame, for contrast against the fire.

DETAIL: flour in the creases of his knuckles, the pitted clay of the tandyr wall,
sparks, the matte surface of raw dough against glossy fired clay.

AUDIO: fire, the slap of dough on hot clay, wind. No music, no speech.

DO NOT INCLUDE: slow motion, cuts, subtitles or text of any kind, brand names,
logos, watermarks, a second person.
```

## Running it so the answer means something

- **Same resolution on both.** 720p each. 2.0 reaches 4K and 2.5 does not, and
  running them differently would credit 2.0 with motion quality it was simply
  handed more pixels for. That mistake nearly shipped once already, when Veo 3.1
  came back at 1080p while everything else ran at 720p.
- **Same duration.** 8 seconds, inside 2.0's 15-second ceiling. Long enough for a
  compound camera move to complete, short enough to be comparable.
- **No speech.** Ambient only. Uzbek pronunciation is still unjudged and belongs
  in its own post rather than smuggled into a physics test.
- **Both shots on both models**, so a split result stays visible.
- **Two takes each.** These are sampled, not deterministic — one clip is an
  anecdote. The reply eval established that when the same model scored 11, then
  9, then 10 on identical fixtures.

2 shots × 2 models × 2 takes = **8 clips, roughly 260 credits.**

## What to watch, and what the post becomes

Six checkable things, ranked by how obvious the failure is to someone with no
technical knowledge:

1. Do the fingers stay attached to the clay for the whole shot?
2. Does the wheel turn at one steady speed?
3. Does the pot stay round as the camera comes around it?
4. Does the firelight flicker and the forearm flicker at the same instant?
5. Does the heat shimmer bend only what is behind it?
6. Does the flour fall, or does it hang?

The caption cannot be written until the clips exist, and it has to report what
happened rather than what was expected. Monday's post is the model for that: it
was written assuming one model would win, the test said otherwise, and saying so
is what made it worth reading.

What the post can commit to in advance is telling the viewer exactly where to
look. A comparison nobody knows how to judge gets scrolled past.
