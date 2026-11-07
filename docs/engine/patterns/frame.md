# The frame

What happens between one image and the next, and the patterns that keep it ordered: a loop with explicit phases, clocks the game can pause, state that two threads can read without locks, changes that wait for a safe point, and memory that lives for exactly one frame.

## The loop

```text
run():
    previous = now()
    accumulator = 0
    while running:
        current = now()
        dt = min(current - previous, MAX_FRAME_TIME)     // a breakpoint must not cause a 30-second step
        previous = current

        poll_input()
        accumulator += dt * time_scale
        while accumulator >= STEP:
            fixed_update(STEP)                           // physics and gameplay that must be deterministic
            accumulator -= STEP
        alpha = accumulator / STEP

        update(dt)                                       // animation, cameras, UI, audio
        late_update(dt)
        render(alpha)                                    // interpolate fixed-step state by alpha
        end_frame()                                      // deferred commands, frame allocator reset
```

The accumulator, interpolation, and the "spiral of death" cap are covered on the [fixed timestep](../../physics/fixed-timestep.md) page. This page is about what goes around it.

## Phases

Order matters: the camera must move after the player it follows, and the UI must read health after damage is applied. Make the order **explicit**, as a list of phases, instead of depending on the order systems were registered in:

```text
phases = [
    Input,            // read devices, map to actions
    FixedUpdate,      // repeated 0..n times per frame
    Update,           // gameplay
    Animation,        // pose from animator state
    PostAnimation,    // IK, attachments that read bones
    Camera,
    UI,
    RenderPrepare,    // build the frame packet (below)
    EndFrame,         // apply deferred commands, reset frame memory
]

register(system, phase, after = [], before = [])
```

Within a phase, systems declare `after` and `before` constraints, and the engine sorts them once at start-up with a topological sort. A cycle is an error reported at start-up, naming the systems involved, not a bug found later in the frame order.

## Clocks

One time value is not enough:

| Clock | Advances | Used by |
| --- | --- | --- |
| Real time | Always, wall-clock | Profiling, network timeouts, frame pacing |
| Game time | By `dt * time_scale`; stops when paused | Gameplay, AI, physics, animation |
| Unscaled time | By `dt`; ignores pause and slow motion | UI, menus, pause screen animation |

```text
Clock { time, delta, scale, paused }

tick(clock, real_dt):
    clock.delta = clock.paused ? 0 : real_dt * clock.scale
    clock.time += clock.delta
```

Give each system the clock it should use, instead of a global `delta_time`. Then pausing is setting `game_clock.paused`, and the pause menu keeps animating because it runs on the unscaled clock. Hit-stop (freezing for a few frames on a heavy hit) and bullet time are a scale on the game clock, or on a per-entity clock for "everything slows except the player".

Store game time as a 64-bit integer count of ticks, or as a double. A 32-bit float second counter loses millisecond precision after about 4.5 hours, and timers and shader animations that read it start to stutter.

## Double-buffered state

With a render thread, simulation of frame N+1 runs while frame N is drawn. The two must not share mutable data. Hand the renderer a **frame packet**: a copy of everything it needs, built at the end of each simulation frame.

```text
FramePacket {
    camera
    draws[]           // { mesh, material, transform, sort_key }
    lights[]
    debug_lines[]
}

packets[2]
write = 0

simulation_thread:
    simulate()
    build packets[write]              // RenderPrepare phase
    wait until render thread has finished with packets[1 - write]
    signal render thread: packets[write] is ready
    write = 1 - write

render_thread:
    wait for a ready packet
    draw it
    signal: done with it
```

- The packet holds **copies** (transforms, handles, parameters), never pointers into simulation data that could change while it is drawn.
- Two packets give one frame of overlap. A third lets the simulation run ahead when a single render frame is slow, at the cost of a frame of latency.
- The same idea works inside one thread for state that many systems read while others write: keep `current` and `next`, read only `current`, write only `next`, and swap at a fixed point. Cellular automata and some AI blackboards work this way, so the result does not depend on update order.

## Deferred commands

Destroying an entity, spawning one, or changing its components while systems are iterating breaks the iteration. Record the change instead, and apply it at a known point:

```text
CommandBuffer { commands[] }

destroy(cmd, entity)                 = append { Destroy, entity }
spawn(cmd, prefab, position)         = append { Spawn, prefab, position }
add_component(cmd, entity, value)    = append { Add, entity, value }

apply(world, cmd):
    for c in cmd.commands: perform c on world
    clear cmd.commands
```

- Give each worker thread its own buffer. No locks while recording; merge them when applying, in a fixed order (by thread index, or by a sort key recorded with each command) so the result is the same every run.
- Pick the sync points: the end of each phase, or only the end of the frame. Later sync points mean fewer stalls, and a longer delay before a destroyed entity disappears.
- A spawn command cannot return the real entity. Return a placeholder id that `apply` maps to the real one, and let later commands in the same buffer use it.
- The [ECS entities](../ecs/entities.md#deferred-commands) page shows the entity side of this.

## Frame allocators

A lot of memory is needed for only one frame: the frame packet, temporary arrays in systems, strings for debug text. A **linear allocator** gives it out by bumping a pointer, and frees all of it at once by resetting the pointer:

```text
FrameArena { base, size, offset }

alloc(arena, bytes, align):
    start = round_up(arena.offset, align)
    if start + bytes > arena.size: fail        // or fall back to the heap and log it
    arena.offset = start + bytes
    return arena.base + start

reset(arena) = arena.offset = 0                // in EndFrame
```

- Allocation is a few instructions, and nothing is freed individually, so there is no fragmentation and no bookkeeping.
- Memory from the arena must not be kept past the end of the frame. Debug builds can fill the arena with a pattern (such as `0xCD`) on reset, so a stale pointer reads obvious garbage instead of last frame's valid-looking data.
- Data that the render thread reads one frame later needs **two** arenas, alternating with the frame packets, so a frame's memory is only reset after the renderer has finished with it.
- Size the arena from the peak use, which the arena can track itself (`max(offset)`), plus a margin.

## What may stall

Work in the frame either blocks the frame, or runs beside it:

| Must finish this frame | Can run over several frames |
| --- | --- |
| Input, simulation, animation, render submission | Asset loading and decompression |
| Physics steps | Pathfinding requests |
| Applying deferred commands | Procedural generation, navmesh baking |
| | Saving, network sends |

Anything in the right column goes to worker threads or is time-sliced (a budget in milliseconds per frame), and reports back through a queue or a [load state](resources.md#load-states). A frame that waits for one of them is a hitch.
