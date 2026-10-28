# Fixed timestep and the accumulator

Running the simulation in steps of a constant size, however long each rendered frame took, and then drawing a pose blended between the last two steps so the motion still looks smooth. This is the loop behind Unity's `FixedUpdate`, Godot's `_physics_process`, and most hand-written engines. The standard write-up is Glenn Fiedler's [Fix Your Timestep!](https://gafferongames.com/post/fix_your_timestep/). This page is the short version, with the parts that usually go wrong.

Throughout, \(h\) is the fixed step in seconds, \(\Delta t\) is the measured length of the rendered frame, and \(A\) is the accumulator: simulated time that is owed but not yet stepped.

## Why not step by the frame time

Passing \(\Delta t\) straight into the simulation is simple, and it works until frame times vary. Then three things break:

- **Results depend on the frame rate.** Any integrator other than an exact solution gives a slightly different answer for a different step. A jump that peaks at 2.0 m at 60 fps can peak a few centimetres higher or lower at 144 fps, and a networked or replayed game drifts out of sync.
- **Long frames explode.** Springs, stiff contacts, and drag become unstable once the step is too large. One 200 ms hitch while a level streams in is enough to launch a ragdoll.
- **Collision misses.** A fast body moves further per step on a slow frame, so it can pass through a thin wall that it would have hit at a higher frame rate.

A fixed \(h\) makes every step identical, so tuning holds at any frame rate, and a recorded input stream replays to the same result on the same build.

## The accumulator loop

Each rendered frame adds its real duration to the accumulator. The simulation then takes as many whole steps as fit, and carries the remainder to the next frame:

```text
accumulator += frameTime

while accumulator >= h:
    previous = current
    current  = simulate(current, h)
    accumulator -= h

alpha = accumulator / h
render(blend(previous, current, alpha))
```

The number of steps per frame is not constant. With \(h = 1/50\) and a 144 Hz display, most frames take no step and roughly one in three takes one. At 30 fps the same clock takes one or two steps per frame. Gameplay code that assumes "one step per frame" is wrong in both directions.

Worked through with \(h = 20\) ms and frames of 7 ms (about 143 Hz):

| Frame | \(A\) after adding 7 ms | Steps taken | \(A\) left | \(\alpha = A / h\) |
| --- | --- | --- | --- | --- |
| 1 | 7 | 0 | 7 | 0.35 |
| 2 | 14 | 0 | 14 | 0.70 |
| 3 | 21 | 1 | 1 | 0.05 |
| 4 | 8 | 0 | 8 | 0.40 |
| 5 | 15 | 0 | 15 | 0.75 |
| 6 | 22 | 1 | 2 | 0.10 |

## Interpolating the render pose

Without the blend, the drawn position only changes on frames that took a step. At 144 Hz with a 50 Hz step, the body holds still for two or three frames and then jumps, which reads as judder even though the simulation is perfectly smooth.

The fix is to keep the previous state as well as the current one, and draw between them using the leftover fraction:

\[
\alpha = \frac{A}{h}, \qquad
p_{\text{render}} = \operatorname{lerp}(p_{\text{previous}}, p_{\text{current}}, \alpha)
\]

\(\alpha\) is always in \([0, 1)\) after the loop. Rotations blend with a slerp or a normalised lerp, not a component-wise lerp of the quaternion. The [interpolation](../maths/interpolation.md#lerp) page has the formulas.

The cost is latency. The drawn pose is always between the last two steps, so it is up to one step behind the simulation: 20 ms at 50 Hz. For most games that is invisible. For a fast first-person aim it is one reason to run the step at 60 Hz or higher.

The alternative is **extrapolation**: draw \(p_{\text{current}} + v \cdot A\), predicting forward from the current state. It has no latency, but a prediction that is wrong, such as a body about to hit a wall, draws a pose that never happens and then snaps back.

!!! warning "Teleports"
    A teleport sets `current` but leaves `previous` at the old place, so the next frame draws the body sliding across the map. When you move a body instantly, write both states, or skip interpolation for that one frame.

## The spiral of death

If one simulation step costs more real time than \(h\), each frame owes more steps than the last. The loop then runs more steps, which makes the frame longer, which owes even more steps, and the game locks up.

Two guards stop this. Use either or both:

- **Clamp the frame time** before adding it, for example to 0.25 s. A hitch longer than that is simply dropped.
- **Cap the steps per frame**, for example to 8, and throw away any whole steps still owed once the cap is reached.

Either guard means the simulation runs slower than real time while the machine cannot keep up. That is the intended failure: the game slows down instead of freezing. It does break the assumption that simulated time matches the wall clock, so a server or a replay must count steps, not seconds.

## Input and the step

Input is sampled once per rendered frame, but it is consumed by steps, and the two do not line up:

- A button **press** that lasts one rendered frame can land on a frame with no step, and be missed. Or it can land on a frame with two steps, and fire twice. Record presses as events or timestamps in the frame loop, and let the next step consume them once. The [Rigidbody movement](../unity/mechanics/rigidbody-movement.md) page does this with its jump buffer.
- A **held** value, such as a stick direction, can just be read by each step. Use the latest value.

Code that only affects what is drawn, such as cameras, UI, and particles, runs per frame and reads the interpolated pose. A camera that follows `current` instead of the blended pose brings the judder back.

## Choosing the step

| Step | Rate | Notes |
| --- | --- | --- |
| \(1/30\) | 30 Hz | Cheap. Visible lag on the interpolated pose, and fast bodies tunnel more easily. Strategy games and large crowds. |
| \(1/50\) | 50 Hz | Unity's default `Fixed Timestep` of `0.02`. |
| \(1/60\) | 60 Hz | Godot's default, and a common choice for action games and network ticks. |
| \(1/120\) and up | 120 Hz+ | Racing, fighting games, stiff ropes and vehicles. Each extra step costs CPU on every frame. |

Pick the largest step at which the simulation is stable and responsive enough, and change it early. Every tuned speed, spring, and jump height was tuned at that rate, and gravity and drag may need retuning if it changes later.

!!! note "Floating-point drift"
    Keep the accumulator in double precision, or as an integer count of ticks. A `float` that has accumulated hours of play loses enough precision that `A >= h` starts to misbehave. The same applies to a long-running simulation clock.

## In each engine

| Engine | Step setting | Catch-up guard | Interpolation |
| --- | --- | --- | --- |
| Unity 6 | **Project Settings → Time → Fixed Timestep**, `Time.fixedDeltaTime` (default `0.02`) | **Maximum Allowed Timestep**, `Time.maximumDeltaTime` (default `0.3333`) | Per body: `Rigidbody.interpolation = RigidbodyInterpolation.Interpolate`, and the same on `Rigidbody2D` |
| Godot 4 | **Physics → Common → Physics Ticks Per Second** (default `60`) | **Max Physics Steps Per Frame** (default `8`) | **Physics → Common → Physics Interpolation** (2D from 4.3, 3D from 4.4) |

Unity details that are easy to miss:

- Inside `FixedUpdate`, `Time.deltaTime` returns `Time.fixedDeltaTime`. Code shared between `Update` and `FixedUpdate` can use `Time.deltaTime` in both.
- `Time.timeScale` scales the step count, not the step size. At `0.5`, steps stay `0.02` simulated seconds but run half as often. At `0`, `FixedUpdate` stops.
- Interpolation only applies when the body is moved by physics or by `MovePosition` and `MoveRotation`. Writing `transform.position` on an interpolated body bypasses it, and is also the teleport case above.

## Reference implementation

An engine-agnostic clock in C#. It owns the accumulator and both guards. The caller owns the two states and the blend, because only the caller knows what a state is.

```csharp
using System;

/// <summary>
/// Turns variable frame times into a whole number of fixed steps.
/// Call Advance once per rendered frame, then draw using Alpha.
/// </summary>
public sealed class FixedStepClock
{
    double _accumulator;

    public FixedStepClock(double step, double maxFrameTime = 0.25, int maxStepsPerFrame = 8)
    {
        if (step <= 0) throw new ArgumentOutOfRangeException(nameof(step));
        Step = step;
        MaxFrameTime = maxFrameTime;
        MaxStepsPerFrame = maxStepsPerFrame;
    }

    public double Step { get; }
    public double MaxFrameTime { get; }
    public int MaxStepsPerFrame { get; }

    /// <summary>Total steps taken. Use this, not seconds, for replays and networking.</summary>
    public long Tick { get; private set; }

    /// <summary>Blend weight between the previous and current state, in [0, 1).</summary>
    public double Alpha => _accumulator / Step;

    /// <summary>
    /// Adds one frame's real duration and runs as many fixed steps as are owed.
    /// Returns the number of steps taken this frame, which may be zero.
    /// </summary>
    public int Advance(double frameTime, Action<double> step)
    {
        _accumulator += Math.Clamp(frameTime, 0, MaxFrameTime);

        int taken = 0;
        while (_accumulator >= Step && taken < MaxStepsPerFrame)
        {
            step(Step);
            _accumulator -= Step;
            taken++;
            Tick++;
        }

        // Still behind after the cap: drop the whole steps, keep the fraction.
        if (_accumulator >= Step)
            _accumulator %= Step;

        return taken;
    }
}
```

A body that uses it keeps both states and copies `current` into `previous` before each step:

```csharp
using System.Numerics;

public struct BodyState
{
    public Vector3 Position;
    public Vector3 Velocity;
}

public sealed class Ball
{
    static readonly Vector3 Gravity = new(0, -9.81f, 0);

    BodyState _previous;
    BodyState _current;

    public void Simulate(double h)
    {
        _previous = _current;
        var dt = (float)h;
        // Semi-implicit Euler: update velocity first, then move with the new velocity.
        _current.Velocity += Gravity * dt;
        _current.Position += _current.Velocity * dt;
    }

    public Vector3 RenderPosition(double alpha) =>
        Vector3.Lerp(_previous.Position, _current.Position, (float)alpha);

    /// <summary>Move without interpolating across the gap.</summary>
    public void Teleport(Vector3 position)
    {
        _current.Position = position;
        _previous.Position = position;
    }
}
```

The frame loop:

```csharp
var clock = new FixedStepClock(1.0 / 60.0);
var ball = new Ball();

// Once per rendered frame:
clock.Advance(frameTime, ball.Simulate);
Draw(ball.RenderPosition(clock.Alpha));
```

The step method in `Ball` is semi-implicit Euler. Why that ordering matters, and when a different integrator is worth it, is on [integrators](integrators.md).
