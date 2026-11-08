# Game-side API

Game code should say **what happened** ("footstep on gravel at this position", "player health is low"), and sound designers should decide **what that sounds like**: which files, how much variation, which effects, how loud. Event-based audio APIs, as in FMOD and Wwise, separate the two, so designers can change the sound of the game without code changes.

## Sound events

```text
SoundEvent (authored by designers) {
    name                    // "footstep", "rifle_fire", "ui_click"
    sources[]               // files, picked randomly (avoiding repeats) or in sequence
    volume, volume_variation       // e.g. -3 dB ± 1.5 dB
    pitch, pitch_variation         // e.g. 1.0 ± 0.05
    attenuation curve, max distance
    bus
    parameters[]            // inputs the game sets, and what they control
    instance_limit, steal_mode
    priority
}
```

```cpp
// Game code
audio.play("footstep", foot_position, { { "surface", surface_id }, { "speed", speed } });

auto engine = audio.start("car_engine", car.position());   // looping: keep the handle
engine.set("rpm", car.rpm());
engine.set_position(car.position(), car.velocity());
engine.stop(0.5f);                                          // fade out over half a second
```

- **Random variation** in pitch and volume, and a pool of several recordings, stop repeated sounds (footsteps, gunfire) sounding mechanical. Avoid picking the same file twice in a row.
- **Parameters** map game values to sound properties: `surface` chooses which set of footstep files to use; `rpm` crossfades between engine recordings and shifts their pitch; `health` controls a low-pass on the music. Designers draw the mapping curves; game code only sets the value.
- Events are referenced by **id or name hash**, not by file, so designers can rename and reorganise files freely.

## Instances and handles

One-shot sounds (footsteps, impacts) are fire-and-forget: `play` returns nothing the caller must keep. Sounds that last or change (engines, loops, music, dialogue) return a **handle**:

```text
SoundHandle { index, generation }      // see handle tables

set_parameter(handle, name, value)
set_position(handle, position, velocity)
stop(handle, fade_time)
is_playing(handle)
```

- Handles are [generational](../../data-structures/handle-table.md): once the sound ends, the handle quietly stops working, instead of controlling whatever reused its slot.
- **Attach** sounds to objects: an instance that follows an entity's transform each frame, and stops (or detaches and finishes) when the entity is destroyed. Most bugs with looping sounds are loops that keep playing after their object was destroyed.
- Parameter changes are **smoothed** on the audio thread (per-parameter seek speed), so a value set once per frame does not cause steps in the sound.

## Snapshots

A **snapshot** is a set of bus and effect settings that can be blended in and out: the pause menu muffles the game with a low-pass and lowers effects; going underwater adds a filter and reverb; a slow-motion moment drops pitch.

```cpp
auto pause = audio.start_snapshot("paused");     // blends in over the snapshot's fade time
...
pause.stop();                                      // blends back out
```

Several snapshots can be active at once, with priorities or blend rules for settings they both change. Designers build them; gameplay starts and stops them.

## Limiting instances

Without limits, a hundred bullets hitting a wall in one second play a hundred impacts, the mix turns to noise, and voices run out.

- **Instance limit per event**: at most N instances of "bullet_impact" at once. When exceeded, either refuse the new one, or steal the oldest, the quietest, or the farthest.
- **Cooldown**: the same event at the same place within a few milliseconds plays once (two physics contacts from one collision).
- **Distance culling before creating anything**: if a one-shot sound is beyond its maximum distance, do not create an instance at all. The cheapest voice is one that never existed.
- **Priority**: dialogue and important cues (low health, objective complete) have a high priority and are never stolen by effects.

## Threading

```text
game thread:   play / set / stop  ->  command queue  ->  audio thread
               handles are created on the game thread, so the call returns at once
audio thread:  executes commands; reports finished instances back
```

Calls from gameplay must be cheap and non-blocking: they only push commands. Everything costly (loading banks, decoding, mixing) happens elsewhere. Loading a level loads its **sound banks** (packages of events and their files) asynchronously alongside its other [resources](../patterns/resources.md), and unloading them waits until no instance from the bank is still playing.

## Middleware or your own

FMOD and Wwise provide everything on these pages, with authoring tools designers already know, profilers that show every voice and bus live, and support for every platform's audio hardware and certification rules. They are free below revenue or budget thresholds and licensed above them (check their current terms). Writing your own audio engine is a large project; the usual reason is a small game that only needs simple playback, or an engine that must avoid licence terms. Even then, keep this API shape (events, parameters, buses, snapshots), so moving to middleware later is a change of backend.
