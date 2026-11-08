# Blending and graphs

A character rarely plays one clip: it walks while aiming, its run speeds up smoothly from the walk, and every change of action fades from one movement to the next. All of these are pose blends, organised by a graph that decides which clips play and with what weights.

## Blending two poses

```text
blend(a, b, w, out result):                     // w = 0 gives a, w = 1 gives b
    for bone:
        result.translation[bone] = lerp(a.translation[bone], b.translation[bone], w)
        result.rotation[bone]    = nlerp_shortest(a.rotation[bone], b.rotation[bone], w)
        result.scale[bone]       = lerp(a.scale[bone], b.scale[bone], w)
```

Blending is per bone, in **local space**. Blending several poses is a weighted sum with weights adding to 1: accumulate `w × value` for translations, and for rotations, flip each quaternion into the same hemisphere as the first before accumulating, then normalise.

## Additive layers

An **additive** clip stores a difference from a reference pose, not a full pose: "lean left", "breathe", "recoil". It is computed once, when the clip is imported:

```text
make_additive(clip_pose, reference_pose):
    translation = clip.translation - ref.translation
    rotation    = inverse(ref.rotation) * clip.rotation
    scale       = clip.scale / ref.scale

apply_additive(base, additive, w):
    base.translation += additive.translation * w
    base.rotation     = base.rotation * slerp(identity, additive.rotation, w)
    base.scale       *= lerp(1, additive.scale, w)
```

The same "recoil" applies on top of standing, walking, or crouching, instead of needing a recoil version of each. The reference pose is usually the clip's first frame, or a neutral pose; it must match the pose the additive was authored against, or the result drifts.

## Masks and layers

A **mask** weights each bone separately. An upper-body layer plays "reload" on the spine and arms, while the lower body keeps running:

```text
layer { pose source, weight, mask[bone] in 0..1, mode = override or additive }

evaluate layers:
    result = base layer's pose
    for layer in remaining layers:
        for bone:
            w = layer.weight * layer.mask[bone]
            override: blend bone towards layer's pose by w
            additive: apply layer's additive pose to the bone with w
```

Blend the mask's edge over a few bones (spine 0.3, chest 0.7, shoulders 1.0) rather than switching from 0 to 1 at one joint, which shows a visible twist.

## Blend spaces

A **blend space** places clips at points in a parameter space, and blends the nearest ones for the current parameters:

```text
1D: walk at speed 1.5, jog at 3.5, run at 6.0
    speed 4.5 -> blend jog and run with w = (4.5 - 3.5) / (6.0 - 3.5)

2D: clips at (direction x, direction z) for strafing: forward, back, left, right, diagonals
    triangulate the points (once, offline)
    find the triangle containing the parameter, blend its three clips with barycentric weights
```

The parameter should be something the clips actually differ by, measured from the clips themselves: give each clip its real speed (from its root motion), not a guess, or the feet slide.

## Synchronising cycles

Blending a walk with a run only works if their feet are in step: left foot down in both at the same time. Clips of different lengths drift apart. Play them in **normalised time** (0 to 1 over each cycle), advanced at the blended rate:

```text
cycle_rate = Σ weight_i / duration_i
phase = fract(phase + dt * cycle_rate)
sample each clip at phase * clip.duration
```

All blended clips stay at the same point in their cycle, whatever their lengths. For clips whose cycles start on different feet, mark the foot-down moments as **sync markers** and align by marker instead of by normalised time.

## State machines

The graph's top level is usually a state machine. Each state is a pose source (a clip, a blend space, or a nested graph), and transitions say when and how to move between states:

```text
State      { name, source }
Transition { from, to, condition, duration, interrupt_rules }

update(dt):
    for t in transitions from current state:
        if t.condition(parameters):
            start crossfade from current to t.to over t.duration
            break
    evaluate active states, blend by the crossfade weight
```

- **Parameters** (speed, grounded, aiming, a trigger for "attack") are set by gameplay each frame. The graph only reads them.
- During a crossfade both states are evaluated, which doubles their cost. Keep crossfades short, and avoid chains of overlapping fades.
- Decide what happens when a transition is triggered **during** a crossfade: restart from the current blended pose, or ignore it until the fade ends.

### Inertialization

A crossfade evaluates both the old and new animation until the fade is done. **Inertialization** (described by David Bollo in "Inertialization: High-Performance Animation Transitions in Gears of War", GDC 2018) instead switches to the new animation immediately, and adds a decaying offset per bone that starts at the difference between the old and new poses, and smoothly fades to zero:

```text
on transition:
    offset[bone] = old_pose[bone] - new_pose[bone]          // and the velocity difference
    each frame: output = new_pose + offset decayed along a smooth curve that reaches zero at the blend time
```

Only one animation is evaluated, so transitions cost almost nothing, and the result respects the old motion's velocity, which looks more natural than a linear crossfade. Many current engines use it as their default transition.

## Running the graph

Evaluate the graph into a list of **tasks** (sample this clip into pose buffer 3, blend buffers 3 and 4 into 5, apply additive 6 to 5), then run the list. Pose buffers come from a per-frame pool, so a graph uses only as many buffers as its deepest blend needs at once, and the task list for each character can run as a [job](../jobs/index.md).

Skip work with zero weight: a clip with weight 0 is not sampled, and a layer with weight 0 is not evaluated. With a large state machine, most of the graph is inactive at any moment.
