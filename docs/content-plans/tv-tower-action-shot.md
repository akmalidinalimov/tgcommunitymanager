# Tashkent TV Tower — a 5-second action shot

Founder direction, 2026-08-23: an action scene at the Toshkent teleminorasi,
five seconds, built to show what Seedance 2.0 and 2.5 can actually do.

## Why this location is a good test as well as a good shot

A landmark is a rigid body with a memorable silhouette. Under a fast camera move
the model has to keep it the *same object* from every angle — same number of
legs, same proportions, same deck — while the city behind it reprojects
correctly. Most generators quietly redesign a building mid-shot, and with a
tower the audience knows, that failure is obvious to every single viewer.

So the shot is spectacle first and a test second, which is the right order here:
the brief is to show power, not to find faults.

## The concept: the dive

Five seconds is not enough for a story. It is exactly enough for one continuous
fall.

A golden eagle — burgut — drops from the observation deck and dives down the
face of the tower with the camera falling alongside it, both pulling out over
the city at the last moment.

Why this and not a car or a runner:

- **Vertical action reads instantly.** In five seconds a viewer has no time to
  work out what they are looking at. Falling is understood in one frame.
- **The eagle is the hardest thing in the shot** — articulated wings, individual
  feathers, a body that changes shape as it tucks and flares. If a model holds
  that at speed, it has shown something real.
- **It stresses exactly what breaks.** Extreme camera motion against a rigid
  structure with correct parallax, plus organic articulation, plus atmospheric
  depth, all at once.
- **The burgut is a national symbol.** The shot belongs to this audience rather
  than being generic drone footage that could be anywhere.

### The five seconds, beat by beat

| Time | What happens |
|---|---|
| 0.0–1.2s | High beside the observation deck, golden hour. The eagle drops off the rail into frame. |
| 1.2–3.6s | Both dive. The tower shaft rushes past camera-left, the city rotates below, the eagle tucks its wings tight. |
| 3.6–5.0s | The eagle flares hard, the camera pulls up, the three splayed legs of the base sweep past underneath. |

## The prompt

Identical for both models. The only variable is the model.

```
Shot on IMAX 65mm. One continuous take, no cuts. Five seconds. Real time, no slow motion.

LOCATION: the Tashkent Television Tower — a 375-metre steel lattice tower with
three splayed angled legs at its base, a slender tapering shaft, a wide circular
observation deck about two thirds of the way up carried on a ring of angled
struts beneath it, and a thin antenna spire at the top. Tashkent city spreads out
below in golden late-afternoon haze.

ACTION, one continuous fall:
- The shot opens high beside the observation deck. A golden eagle is perched on
  the outer rail. It drops off the rail into frame.
- The eagle and the camera dive together down the face of the tower. The shaft
  rushes past on camera-left. The city turns below.
- The eagle tucks its wings tight against its body as it accelerates.
- At the end it flares its wings hard and banks. The camera pulls up with it and
  the three splayed legs of the base sweep past underneath.

CAMERA: 35mm on large format, T2.8. The camera falls with the bird the whole way,
holding it at frame-right while the tower fills the left of frame. Fast but
controlled and weighted, like a heavy drone, not a jerky handheld. One
continuous descent, then a rising bank at the end. No cuts.

PHYSICS THAT MUST HOLD:
- The tower is the same structure from every angle. Three legs at the base for
  the whole shot, one observation deck, one spire. It does not gain floors,
  change proportion or redesign itself as the camera falls.
- Parallax is correct: the tower's near edge travels across frame far faster
  than the city behind it, and the horizon stays level except where the camera
  deliberately banks.
- The eagle accelerates as it falls and its wings genuinely fold — the silhouette
  narrows. When it flares, the wings catch air and the body slows and rises.
- Individual flight feathers separate at the wingtips and move against the
  airflow.
- The eagle's shadow travels across the tower's surface as it passes.

LIGHT: low golden sun from camera-right, raking across the tower so the lattice
throws long shadows down its own shaft. The city below sits in warm haze with
depth — near buildings clear, far ones dissolving. A little lens flare when the
sun clips the structure.

DETAIL: rivets and steel lattice, weathered paint, glass of the observation deck
catching the sun, individual feathers, dust haze in the air.

AUDIO: wind rushing, one eagle cry. No music, no speech.

DO NOT INCLUDE: slow motion, cuts, subtitles or text of any kind, brand names,
logos, signage, watermarks, other aircraft or drones, a falling person, a second
bird.
```

## Settings

Same on both, so the only difference is the model:

- **Duration** 5s — inside 2.0's 15s ceiling, above 2.5's 4s floor.
- **Resolution** 720p on both. 2.0 reaches 4K and 2.5 does not; running them
  differently would let extra pixels read as better motion.
- **Aspect** 16:9.
- **Mode** `std` for 2.0, `t2v` for 2.5.
- **Two takes each.** Fast camera moves fail intermittently, and one clip is an
  anecdote.

Four clips, roughly 130 credits.

**Decline the preset.** Higgsfield substituted a preset called "IN THE DARK" for
every job in the last batch and had to be refused explicitly. It will replace the
camera move and the physics list if allowed, which is the whole shot.

## What to watch

1. Does the tower keep three legs and one deck for all five seconds?
2. Does the near edge of the tower move faster than the city behind it?
3. Do the wings actually fold, so the silhouette narrows in the dive?
4. Does the flare slow the bird, or does it keep falling at the same rate?
5. Does the eagle's shadow land on the tower?

## The risk, stated before spending anything

An eagle at speed is the hardest organic motion in any of these tests, harder
than the potter's clay. There is a real chance both models produce a bird with
smeared wings or a tower that redesigns itself mid-fall.

That is still a usable post — "we asked for the hardest shot we could think of
and here is where it broke" is honest and interesting. But the brief was to show
power, so if both fail badly the fallback is the same dive **without the eagle**:
a pure camera fall down the tower into the plaza. Far more likely to look
spectacular, and it still tests structural coherence and parallax under extreme
motion. Worth knowing that fallback exists before the first take comes back.
