# Islands, sleeping, and continuous collision

Two problems every physics engine meets once there are more than a few bodies: most of them are not moving and should cost nothing, and a few move so fast that they pass through walls between steps.

## Islands

An **island** is a group of bodies connected by contacts and joints. Bodies in different islands cannot affect each other this step, so:

- each island can be **solved independently**, which is natural parallelism (one [job](../engine/jobs/index.md) per island);
- an island can **sleep** as a whole.

Static bodies (the ground) do not join islands together. Otherwise everything resting on the ground would be one island.

```text
build_islands():
    union_find = one set per dynamic, awake body
    for contact in touching contacts:
        if both bodies are dynamic: union(a, b)
    for joint in joints:
        if both bodies are dynamic: union(a, b)
    islands = group bodies, contacts, and joints by their set's root
```

Union-find with path compression makes this close to linear. Box2D v3 keeps islands persistent and only merges or splits them when contacts begin and end, which is faster than rebuilding every step.

## Sleeping

A body at rest still costs integration, broadphase updates, contact generation, and solver iterations. **Sleeping** skips all of that until something disturbs it:

```text
after solving each island:
    for body in island:
        if length(body.linear_velocity) < LINEAR_SLEEP and length(body.angular_velocity) < ANGULAR_SLEEP:
            body.sleep_time += dt
        else:
            body.sleep_time = 0
    if min(body.sleep_time for body in island) > TIME_TO_SLEEP:       // e.g. 0.5 s
        for body in island: sleep(body)          // zero velocities, stop simulating
```

- Sleep **whole islands**, never single bodies. A box sleeping under a box that is still settling would let the top one sink into it.
- **Wake** an island when: an awake body starts touching one of its bodies, a joint to it changes, game code applies a force or impulse, teleports a body, or changes its shape or mass, or a body it rests on is removed (the classic "floating crate after the floor was deleted" bug).
- Thresholds that are too high make slowly sliding objects stop abruptly; too low and nothing ever sleeps. Around 0.05 m/s and 2 degrees/s, held for half a second, suits human-scale objects.

## Tunnelling

Discrete simulation checks positions at the end of each step. An object that moves farther than its own thickness in one step can start on one side of a wall and end on the other with no overlap ever seen:

```text
at 60 Hz, a bullet at 400 m/s moves 6.7 m per step
a 0.2 m ball at 30 m/s moves 0.5 m per step: more than its diameter
```

**Continuous collision detection** (CCD) prevents it. Turn it on only for bodies that need it, because it costs much more than discrete collision:

```text
needs_ccd(body) = length(body.velocity) * dt > body.shape.min_extent * 0.5
```

### Speculative contacts

The cheapest approach: in the narrowphase, create contacts for pairs that are **not yet touching** but are closer than they could move this step. The contact's constraint allows the bodies to close the gap, but not to cross it:

```text
gap = closest distance between the shapes (GJK distance; see narrowphase)
if gap < relative_speed * dt + MARGIN:
    add contact with bias = gap / dt          // allow approaching by exactly the gap this step
```

The solver then handles it like any other contact, with no extra pass. The downside is **ghost collisions**: an object passing close by a corner can be stopped by a contact that would not have happened, because the contact assumes straight-line motion towards the closest point. It suits most game objects.

### Time of impact

For objects that must not tunnel and must not snag (projectiles, fast vehicles), find **when** they would first touch, and move them only that far:

```text
time_of_impact(A, B, motion over [0, dt]):
    t = 0
    loop:
        d = distance(A at t, B at t)                 // GJK
        if d < TOLERANCE: return t
        bound = upper bound on how fast the gap can close (linear speed + angular speed × radius)
        t += d / bound                               // conservative advancement: cannot overshoot
        if t > dt: return no hit
```

Conservative advancement steps forward by the largest amount that cannot skip the first contact. On a hit, the body is moved to the time of impact and the rest of its step is handled in a sub-step (or its remaining motion discarded, which loses a little time but is simpler and stable).

### Rays for small, fast objects

A bullet is better modelled as a ray than as a rigid body: cast a ray (or a thin sphere sweep) from its last position to its new one each step, and treat the first hit as the impact. This is exact, cheap, and how most games handle projectiles; see the [tracers](../unity/combat/tracers.md) and [weapons](../unity/combat/weapons.md) pages for the Unity version.

## Bodies at large scales

Very fast or very large objects stress every part of the step: broadphase boxes grow, CCD runs more often, and floating-point precision worsens far from the origin (engines shift the world origin to keep the simulated area near it). Clamp maximum velocities to what the game needs, and keep simulated bodies within a few kilometres of the origin.
