# Solver

The solver turns contacts and joints into changes of velocity, so that bodies stop moving into each other, slide with friction, bounce, and stay joined. Most game physics engines use **sequential impulses**: apply a small impulse at each constraint in turn, and repeat a few times until they agree. This page follows the formulation from Erin Catto's GDC talks and Box2D.

## The step

```text
step(dt):
    for body: velocity += dt * (gravity + force * inv_mass)      // forces first
    find contacts (broadphase, narrowphase)
    prepare constraints (effective masses, bias)
    warm start: apply last step's impulses
    repeat ITERATIONS times:
        for each constraint: solve velocity
    for body: position += dt * velocity                           // semi-implicit Euler
```

This is the [semi-implicit Euler](integrators.md#semi-implicit-euler) order: velocities are fixed up first, and positions use the corrected velocities.

## A contact as a velocity constraint

At a contact point with normal `n` (pointing from A to B), the bodies must not move towards each other:

```text
v_rel = (vB + ωB × rB) - (vA + ωA × rA)          // relative velocity of the two points
vn    = dot(v_rel, n)                             // must be >= 0: separating or resting
```

`rA` and `rB` are the contact point relative to each body's centre of mass. If `vn < 0`, apply an impulse `λ` along `n`, pushing A by `-λn` and B by `+λn`, just large enough to make `vn = 0`:

```text
effective_mass = 1 / (inv_mass_A + inv_mass_B
                      + dot(n, cross(invI_A * cross(rA, n), rA))
                      + dot(n, cross(invI_B * cross(rB, n), rB)))

λ = -effective_mass * vn

apply(λ):
    vA -= λ * n * inv_mass_A;   ωA -= invI_A * cross(rA, λ * n)
    vB += λ * n * inv_mass_B;   ωB += invI_B * cross(rB, λ * n)
```

`invI` is the inverse inertia tensor in world space. Static bodies have zero inverse mass and inertia, so they never move. The effective mass depends only on positions, so compute it once per step in the prepare phase.

## Accumulated clamping

A contact can push but never pull. Clamping each impulse to be non-negative is wrong, though: later iterations need to be able to take back some of an earlier push. Clamp the **total** impulse instead:

```text
solve_contact(c):
    vn = relative normal velocity at c
    λ = -c.effective_mass * (vn - c.velocity_bias)
    old = c.normal_impulse
    c.normal_impulse = max(old + λ, 0)            // the total must stay non-negative
    λ = c.normal_impulse - old                    // apply only the change
    apply(λ)
```

This is the single most important detail of the method. Without it, stacks sink and jitter.

## Penetration and bias

Velocity constraints stop bodies moving further in, but do nothing about overlap that already exists (from large steps, or numerical error). Add a **bias** velocity that pushes them apart over the next few steps:

```text
depth = penetration at c (positive when overlapping)
c.velocity_bias = (β / dt) * max(depth - SLOP, 0)        // β ≈ 0.2, SLOP ≈ 0.005 m
```

- **Baumgarte stabilisation** (this bias) is simple, but adds energy: bodies pushed out of overlap keep some of that velocity, and deep overlaps make objects pop apart.
- The **slop** lets bodies rest slightly overlapped, so contacts persist instead of flickering between touching and not touching.
- Better alternatives remove the error without adding velocity: **split impulses** (solve the bias in a separate pseudo-velocity used only for position) or a post-solve position correction pass (Box2D v2's non-linear Gauss–Seidel). Box2D v3 uses **soft constraints** with substepping, which is the current best practice for stability.

## Restitution

Bounciness: the separating velocity after impact should be `−e` times the approaching velocity before it, with restitution `e` from 0 (no bounce) to 1:

```text
prepare(c):
    vn0 = relative normal velocity before solving
    c.velocity_bias = vn0 < -BOUNCE_THRESHOLD ? -e * vn0 : 0         // bounce only on real impacts
    // plus the penetration bias above, if not using a separate position pass
```

The threshold (around 1 m/s) stops resting objects from bouncing forever on tiny velocities.

## Friction

Friction is two more constraints per contact point, along two tangent directions `t1`, `t2` perpendicular to `n`. They try to make the tangential velocity zero, with the total impulse limited by the Coulomb friction cone, approximated as a box:

```text
solve_friction(c, t):
    vt = dot(v_rel, t)
    λ = -c.tangent_mass[t] * vt
    max_friction = c.friction * c.normal_impulse              // μ × normal force
    old = c.tangent_impulse[t]
    c.tangent_impulse[t] = clamp(old + λ, -max_friction, max_friction)
    apply(c.tangent_impulse[t] - old) along t
```

Solve friction **before** the normal constraint in each iteration (as Box2D does), using the normal impulse from the previous iteration as the limit. Combine the two bodies' friction coefficients with the geometric mean, `sqrt(μA × μB)`, or the minimum.

## Warm starting

Resting contacts need about the same impulses every step. Start each step from last step's accumulated impulses, matched through the [persistent manifold](narrowphase.md#persistent-manifolds):

```text
warm_start(c):
    apply(c.normal_impulse * n + c.tangent_impulse[0] * t1 + c.tangent_impulse[1] * t2)
```

With warm starting, the iterations only have to correct the small changes since last step, so a tall stack settles and stays still with 4 to 8 iterations instead of needing dozens.

## Joints

A joint is the same machinery with different constraint rows:

| Joint | Constrains |
| --- | --- |
| Ball and socket | The anchor points on both bodies coincide: 3 rows (x, y, z) |
| Hinge | Ball and socket, plus 2 rows keeping the axes aligned |
| Slider (prismatic) | 2 positional rows perpendicular to the axis, plus 3 angular rows |
| Distance or rope | One row along the line between anchors; a rope only pulls (clamped like a contact) |
| Motor | A target relative velocity, with the impulse clamped to the motor's maximum force |
| Limit | Like a contact on the joint's angle or position: only active at the limit |

Each row has an effective mass and a bias, and is solved and clamped in the same loop. Joints with a large mass ratio (a heavy wrecking ball on a light chain) converge slowly. More iterations, substepping, or solving a joint's rows together as a small matrix (a "block solver") help.

## Iterations and order

- More iterations give stiffer stacks and joints, at a linear cost. 4 to 10 is typical; engines often allow a per-body or per-island override.
- **Substepping** (several small steps per frame, each with fewer iterations) converges better than many iterations in one large step, and is what modern solvers (Box2D v3, the TGS solver in PhysX) do.
- Solving in a fixed order makes the simulation deterministic for the same inputs. Shuffling the order removes bias towards whichever contact was solved last, but needs a seeded order to stay reproducible.
