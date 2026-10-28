# Integrators

How one simulation step turns an acceleration into a new velocity and position. The choice decides whether a jump reaches the height you tuned, and whether a spring settles or explodes. It is usually two lines of code, and the order of those two lines is most of the decision.

Throughout, \(h\) is the step in seconds, \(x\) is position, \(v\) is velocity, and \(a(x, v)\) is the acceleration from forces divided by mass. The step is assumed fixed, as on the [fixed timestep](fixed-timestep.md) page.

## Explicit Euler

Advance position with the old velocity, then velocity with the old acceleration:

\[
x_{n+1} = x_n + v_n h, \qquad v_{n+1} = v_n + a(x_n)\, h
\]

It is the obvious version, and it is the one to avoid. It adds energy on every step to anything that oscillates. A spring with \(\omega = 10\) rad/s at 50 Hz grows to about 18,000 times its starting energy in five seconds.

## Semi-implicit Euler

Swap the order. Update velocity first, then move with the **new** velocity:

\[
v_{n+1} = v_n + a(x_n)\, h, \qquad x_{n+1} = x_n + v_{n+1} h
\]

It costs the same as explicit Euler, but the energy of an oscillator stays bounded instead of growing. The same spring's energy swings within about 11% of where it started, and never drifts further. This is the default in game physics: Box2D and PhysX both integrate velocity, then position. It is also what `velocity += gravity * dt; position += velocity * dt` does in most gameplay code.

It is stable for a spring while \(\omega h < 2\), that is, a stiffness \(k < 4m / h^2\). At 50 Hz that is \(\omega < 100\) rad/s. A stiffer spring needs a smaller step, a damper, or a constraint solver.

Use it for: anything with forces and contacts, which is most of a game.

## Constant acceleration, exactly

When the acceleration is constant over the step, as with gravity on a jump, there is no need to approximate:

\[
x_{n+1} = x_n + v_n h + \tfrac{1}{2} a h^2, \qquad v_{n+1} = v_n + a h
\]

This is exact for any \(h\), so a jump reaches the same peak at every frame rate. Both Euler forms miss it by about \(v_0 h / 2\):

| Integrator | Peak of a 1.4 m jump, \(g = 25\), 50 Hz |
| --- | --- |
| Explicit Euler | 1.485 m (8.5 cm high) |
| Semi-implicit Euler | 1.317 m (8.3 cm low) |
| Exact | 1.400 m |

!!! warning "Variable steps change the jump"
    The error depends on \(h\). A controller that integrates in `Update` with `Time.deltaTime` jumps to a different height at each frame rate. [Character movement](../unity/mechanics/character-movement.md) does this: with its defaults, the peak is about 7 cm high at 60 fps and 3 cm high at 144 fps. It overshoots rather than falling short because the take-off frame moves at the full jump speed before gravity is applied. Use the exact form above for the vertical move, or integrate on a fixed step.

## Verlet

Two forms, for different jobs.

**Velocity Verlet** carries velocity explicitly and averages the acceleration at both ends of the step:

\[
x_{n+1} = x_n + v_n h + \tfrac{1}{2} a_n h^2, \qquad
v_{n+1} = v_n + \tfrac{1}{2}\left(a_n + a_{n+1}\right) h
\]

It is second-order accurate and keeps energy bounded, at one force evaluation per step, because \(a_{n+1}\) is reused as the next step's \(a_n\). The catch is that \(a_{n+1}\) must depend only on \(x_{n+1}\). Drag, or anything else that depends on velocity, does not fit cleanly. Use it for orbits, springs, and N-body sims without much drag.

**Position Verlet** stores the previous position instead of a velocity:

\[
x_{n+1} = 2 x_n - x_{n-1} + a_n h^2
\]

Velocity is implied by \(x_n - x_{n-1}\). That makes it the form for ropes, cloth, and soft bodies built from particles. A constraint can move a particle directly, and the implied velocity follows without a separate correction. The step must stay fixed, because a change of \(h\) changes the implied velocity.

## RK4

Fourth-order Runge–Kutta evaluates the acceleration four times per step and blends them. On smooth problems it is very accurate: the same spring is within 0.02% after five seconds. It slowly loses energy rather than keeping it bounded, and its accuracy comes from assuming forces vary smoothly within the step. A contact, which switches on suddenly, breaks that assumption. Four evaluations per step is rarely worth it for gameplay. It is worth it for an orbit you need to predict accurately, or an offline trajectory preview.

## Which one

| Integrator | Cost per step | Energy over time | Use for |
| --- | --- | --- | --- |
| Explicit Euler | 1 evaluation | Grows | Nothing that oscillates |
| Semi-implicit Euler | 1 | Bounded | The default: bodies, contacts, gameplay motion |
| Exact constant acceleration | 1 | Exact for constant \(a\) | Jumps, projectiles, anything under gravity alone |
| Velocity Verlet | 1 | Bounded | Springs and orbits with position-only forces |
| Position Verlet | 1 | Bounded | Ropes, cloth, particle constraints |
| RK4 | 4 | Slow loss | Smooth, contact-free problems that need accuracy |

Damping that is just a decay toward rest, \(v \leftarrow v\, e^{-c h}\), is exact on its own, and is on the [interpolation](../maths/interpolation.md#frame-rate-independent-damping) page. Apply it as a separate multiply rather than folding \(-c v\) into the acceleration.

## Reference implementation

Engine-agnostic C#, one method per integrator. `Accel` is the force model: given a position and velocity, return the acceleration.

```csharp
using System.Numerics;

public delegate Vector3 Accel(Vector3 position, Vector3 velocity);

public static class Integrate
{
    /// <summary>Velocity first, then position with the new velocity. The default.</summary>
    public static void SemiImplicitEuler(ref Vector3 x, ref Vector3 v, Accel accel, float h)
    {
        v += accel(x, v) * h;
        x += v * h;
    }

    /// <summary>Exact for a constant acceleration such as gravity, at any step size.</summary>
    public static void ConstantAcceleration(ref Vector3 x, ref Vector3 v, Vector3 a, float h)
    {
        x += v * h + 0.5f * a * h * h;
        v += a * h;
    }

    /// <summary>
    /// Velocity Verlet. Pass in the acceleration from the previous step; the new one is
    /// returned for the next. The force model must not depend on velocity.
    /// </summary>
    public static Vector3 VelocityVerlet(ref Vector3 x, ref Vector3 v, Vector3 a, Accel accel, float h)
    {
        x += v * h + 0.5f * a * h * h;
        Vector3 next = accel(x, Vector3.Zero);
        v += 0.5f * (a + next) * h;
        return next;
    }

    /// <summary>
    /// Position Verlet. Stores the previous position instead of a velocity.
    /// The step must stay fixed.
    /// </summary>
    public static void PositionVerlet(ref Vector3 x, ref Vector3 previous, Vector3 a, float h)
    {
        Vector3 current = x;
        x = 2f * x - previous + a * h * h;
        previous = current;
    }
}
```

!!! note "Starting position Verlet"
    Position Verlet needs \(x_{-1}\) on the first step. Set `previous = x - v0 * h` to start with velocity `v0`, or `previous = x` to start at rest. Leaving it at zero gives the particle a velocity of `x / h` on the first step.
