# 3D audio

A sound with a position in the world should sound like it comes from there: quieter with distance, from the right direction, muffled behind walls, and with the echo of the space it is in. All of it is computed per voice from the source's position and the **listener's**.

## Attenuation

```text
inverse_distance(d, min_distance, max_distance):
    d = clamp(d, min_distance, max_distance)
    return min_distance / d                         // 1 at min_distance, halving with each doubling

linear(d, min_distance, max_distance):
    return 1 - clamp((d - min_distance) / (max_distance - min_distance), 0, 1)
```

- **Inverse distance** is physically correct (−6 dB per doubling of distance), but never reaches zero, so distant sounds stay faintly audible and keep using voices.
- **Custom curves** drawn by sound designers per sound are the norm in games: full volume to a short distance, a natural fall-off, and exactly zero at the maximum, where the voice can be culled or virtualised.
- Give each sound its **own range**: a gunshot is audible at 200 m, a footstep at 20 m. A global range makes small sounds carry absurdly far.
- **Distance filtering**: air absorbs high frequencies over distance. A low-pass filter whose cutoff falls with distance makes distant sounds read as far away, not just quiet.

## Panning

The direction to the source, in the listener's space, decides how much of it goes to each speaker:

```text
// Stereo, equal power: the total power stays constant as the sound moves across.
pan = dot(normalize(direction_in_listener_space), listener_right)     // -1 left .. 1 right
angle = (pan + 1) * π / 4                                              // 0 .. π/2
left_gain  = cos(angle)
right_gain = sin(angle)
```

- **Equal power** (`cos`/`sin`) keeps a sound in the centre at the same loudness as at the sides. Linear panning (`(1 − p)/2`, `(1 + p)/2`) makes it dip in the middle.
- **Surround** layouts (5.1, 7.1) pan between the two speakers either side of the source direction, by the same rule (vector base amplitude panning).
- **Spread**: a large source (a river, a crowd) should not be a point. Widen the panning as the listener gets close, until the sound surrounds them.

### HRTF

On headphones, stereo panning only gives left and right. A **head-related transfer function** filters the sound the way a head and ears do for each direction, so sources are heard above, below, and behind. It costs a convolution per voice, so apply it to the important nearby voices and pan the rest. Steam Audio, the Meta XR audio SDK, and platform spatialisers (Windows Sonic, PlayStation's Tempest) provide HRTF processing.

## Doppler

A source moving towards the listener sounds higher in pitch, and lower moving away:

```text
doppler(listener, source, speed_of_sound = 343):
    dir = normalize(source.position - listener.position)
    v_listener = dot(listener.velocity, dir)          // towards the source is positive
    v_source   = dot(source.velocity, dir)            // away from the listener is positive
    return (speed_of_sound + v_listener) / (speed_of_sound + v_source)
```

Multiply the voice's pitch by the result. Real Doppler is subtle at game speeds and extreme for fast projectiles, so scale its effect per sound (a Doppler factor), clamp the result (for example 0.5 to 2.0), and smooth velocities, which teleports and frame spikes otherwise turn into pitch jumps.

## Occlusion and obstruction

A sound behind a wall should be quieter and muffled:

```text
every few frames, per audible voice:
    hits = raycast(listener, source) against geometry marked as acoustic
    occlusion = clamp(sum of each hit's material absorption, 0, 1)
    target_lowpass = lerp(22 kHz, 800 Hz, occlusion)
    target_gain = lerp(1, 0.3, occlusion)
smooth gain and filter cutoff towards the targets over ~0.2 s
```

- Spread the raycasts over frames (a few voices per frame), and only for voices that are audible. Occlusion does not need to update at frame rate.
- Smooth the result. A sound that snaps to muffled as a thin post crosses the line between source and listener is worse than no occlusion.
- Use several rays (to the source and around it) and average, so the edge of a doorway gives partial occlusion instead of flipping.
- **Obstruction** (something in the way, but the sound can get round it, like a pillar) muffles the direct sound but leaves the reverb. **Occlusion** (a closed wall) affects both. Many games treat them the same way and accept the difference.
- Proper **sound propagation** routes sound through doorways and around corners using a graph of rooms and portals, or a precomputed acoustic simulation (Steam Audio, Microsoft's Project Acoustics). It costs more to set up, and is the difference between "muffled behind the wall" and "comes from the door".

## Reverb

The space around a sound changes how it sounds: a cathedral, a tiled corridor, a forest. Model it with a few shared reverb buses, and **reverb zones** in the level:

```text
ReverbZone { volume (a box or sphere), preset (decay time, early reflections, damping), blend distance }

each frame:
    for zone the listener is in (or near): weight by how far inside
    set each reverb bus's preset and send level from the weighted zones
```

- Voices send to the reverb bus at a level that grows with distance (distant sounds are mostly reverberation). Dialogue and UI usually send nothing.
- Blend between zones as the listener moves from a cave into the open, rather than switching.
- Convolution reverb with recorded impulse responses sounds realistic but costs much more than algorithmic reverb. Use it sparingly, on one or two buses.

## Where the listener is

In first person, the listener is the camera. In third person, the camera is behind and above the character, so a sound beside the character sounds off to one side of the camera, and distances feel wrong. Common choices:

- **Position** at the character (or between character and camera), so attenuation matches what the character would hear.
- **Orientation** from the camera, so a sound on the left of the screen is heard on the left.

Pick per game, and test with a sound source orbiting the character: it should move around the speakers in step with the screen.
