# Clips, sampling, and compression

An animation clip stores how each bone of a skeleton moves over time. Sampling it at a time gives a **pose**: one transform per bone. This page covers how skeletons and poses are stored, sampling a clip, and keeping clips small enough to have hundreds in memory.

## Skeletons and poses

```text
Skeleton {
    bone_count
    parent[]            // parent bone index, -1 for the root; parent[i] < i
    bind_local[]        // each bone's local transform in the bind pose
    names[]             // for tools and lookup, not for the runtime
}

Pose {
    translation[bone_count]
    rotation[bone_count]       // unit quaternions
    scale[bone_count]
}
```

- Bones are stored **parents before children**, so converting the whole pose to model space is one forward loop, exactly like the [transform hierarchy](../scene-hierarchy.md#parent-indices-in-update-order).
- Poses are in **local space** (each bone relative to its parent). Blending happens in local space, because blending model-space transforms makes limbs shrink and stretch.
- Store the pose as separate arrays (structure of arrays). Sampling and blending then run over plain arrays of quaternions and vectors, which vectorise well.
- Most bones never scale. Many runtimes drop per-bone scale or store a single uniform scale, saving a third of the data.

## Clips

```text
Clip {
    duration
    tracks[]            // per bone: translation keys, rotation keys, scale keys
    events[]            // { time, name }: footsteps, hit frames
}

Track<T> { times[], values[] }
```

A track with a single key holds that value for the whole clip; most bones' translation and scale tracks look like this, and cost almost nothing.

## Sampling

```text
sample_track(track, t) -> value:
    if track has one key: return track.values[0]
    i = index of the last key with time <= t        // binary search, or the cached index from last frame
    f = (t - times[i]) / (times[i + 1] - times[i])
    return interpolate(values[i], values[i + 1], f)

sample_clip(clip, t, out pose):
    for bone in skeleton:
        pose.translation[bone] = sample_track(clip.translation[bone], t)
        pose.rotation[bone]    = sample_track(clip.rotation[bone], t)
        pose.scale[bone]       = sample_track(clip.scale[bone], t)
```

- Interpolate translations and scales with `lerp`, and rotations with normalised lerp: `normalize(lerp(q0, q1, f))`, after flipping `q1` if `dot(q0, q1) < 0` so the shorter way round is taken (see [quaternions](../../maths/quaternions.md)). Keys are close together, so nlerp is indistinguishable from slerp and much cheaper.
- A playing clip moves forward a little each frame, so the right key is usually the same as last frame or the next one. Cache the last index per track (or per clip instance) and step forward from it instead of searching.
- **Looping**: wrap `t` with `fmod(t, duration)`. For seamless loops, the first and last keys must match, and the pose between the last key and the wrap must interpolate back to the first.

### Uniform keys

Clips exported at a fixed rate (30 keys per second) can be stored as **uniform** tracks: no times array, and the key index is `floor(t * rate)`. No search, no cache, and better compression (below). The cost is storing keys even where nothing changes, which compression mostly removes anyway.

## Compression

A 60-bone character at 30 keys per second, with 40 bytes per bone per key, is 72 KB per second of animation. A game with hours of animation needs it much smaller.

### Key reduction

Remove keys that can be reconstructed by interpolating their neighbours, within an error tolerance:

```text
reduce(track, tolerance):
    keep the first and last keys
    for each key k between them:
        if interpolating its kept neighbours reproduces k within tolerance: remove it
```

Measure the error where it matters: **in model space, at the end of the chain**. A tiny rotation error at the hip moves the foot by centimetres, while the same error at a finger joint is invisible. Good compressors measure each bone's error at a "virtual vertex" some distance from the joint (around 10 cm to 1 m), accumulated through the hierarchy.

### Quantisation

Store values in fewer bits:

| Value | Encoding | Size |
| --- | --- | --- |
| Rotation | "Smallest three": drop the largest component (recomputed from the others, since the quaternion is unit length), store the other three in 15 bits each, plus 2 bits for which was dropped | 48 bits |
| Translation | Each component as 16 bits, relative to the track's own minimum and range | 48 bits |
| Scale | As translation, or omitted when constant | 0 to 48 bits |

Quantising relative to each track's **range** keeps precision where it is needed: a finger bone's translation varies over millimetres, so its 16 bits cover only that.

### Libraries

Writing a good compressor is a project of its own. The open-source **Animation Compression Library** (ACL, by Nicholas Frechette) is used in several commercial engines, including as a plug-in for Unreal. It compresses per-clip with a target error in model space and decompresses very quickly. Use it, or study its documentation before writing your own.

## Events

Clips carry **events** at given times: footsteps, the frame a sword hit becomes active, a sound cue. When a clip advances from `t0` to `t1`, fire every event in `(t0, t1]`, handling the wrap for looping clips (fire the events in `(t0, duration]` and then `[0, t1]`).

When several clips are blended, fire events only from the clip with the highest weight, or only from clips above a weight threshold. Otherwise a crossfade between two walk cycles plays two footsteps for each step.
