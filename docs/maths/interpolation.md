# Interpolation and easing

Blending two values, rebuilding a blend parameter, and approaching a target by a fraction that does not depend on the frame rate. The [orbit camera](../unity/orbit-camera.md) uses the damping step at the bottom for its zoom and for the way it eases back out after a collision.

Throughout, \(t\) is a blend weight. Outside a function that says it saturates, \(t\) is whatever the caller passed in. Easing polynomials below assume \(t \in [0, 1]\).

## Lerp

Linear interpolation from \(a\) toward \(b\):

\[
\operatorname{lerp}(a, b, t) = (1 - t)\, a + t\, b = a + (b - a)\, t
\]

The two writings are the same algebra. The second is the one to use in code: it is one multiply. `Lerp(2, 10, 0.25)` is `4`.

On a vector, the same formula is applied per component. That traces a straight line in space at constant speed in \(t\). It is the wrong tool for an angle that wraps, and for a rotation, where the constant-speed path is a slerp.

## Inverse lerp

Recover the weight that would produce a value \(v\) between \(a\) and \(b\):

\[
\operatorname{invlerp}(a, b, v) = \frac{v - a}{b - a}
\]

This is undefined when \(a = b\). The helpers below return `0` in that case, which matches `Mathf.InverseLerp`. `InverseLerp(2, 10, 4)` is `0.25`.

The result is outside \([0, 1]\) when \(v\) is outside \([a, b]\). That is what you want for an extrapolation. Clamp it only when a later step must stay inside the range.

## Remap

Run inverse lerp on one interval and lerp on another:

\[
\operatorname{remap}(v; a_1, b_1; a_2, b_2)
  = \operatorname{lerp}\!\left(a_2, b_2, \operatorname{invlerp}(a_1, b_1, v)\right)
\]

`Remap(4, 2, 10, 0, 100)` is `25`. A health value of 40 on a scale of 0 to 100 becomes `0.4` with `Remap(40, 0, 100, 0, 1)`. Because inverse lerp is not clamped here, an input past the end of the source range continues past the end of the destination range.

## Smoothstep

Hermite interpolation on \([0, 1]\). The value matches \(t\) at the ends, and the first derivative is zero at both ends, so a motion that starts and stops on this curve has no velocity pop:

\[
\operatorname{smoothstep}(t) = t^{2} (3 - 2t) = 3t^{2} - 2t^{3}
\]

\[
\frac{d}{dt}\operatorname{smoothstep}(t) = 6t(1 - t)
\]

Ken Perlin’s smootherstep also zeroes the second derivative at the ends, which is the version to reach for when the *acceleration* at the join was the thing you could see:

\[
\operatorname{smootherstep}(t) = t^{3}\,(6t^{2} - 15t + 10) = 6t^{5} - 15t^{4} + 10t^{3}
\]

Both are meant to be fed a saturated parameter. HLSL’s built-in `smoothstep(edge0, edge1, x)` saturates, remaps \(x\) from \([\textit{edge0}, \textit{edge1}]\) into \([0, 1]\), then applies the cubic above. `Mathf.SmoothStep` takes the two ends and the value, not a bare \(t\), and it clamps.

## A few easing curves

Robert Penner’s polynomial eases, the subset that covers most UI and gameplay motion. Each one takes \(t \in [0, 1]\) and returns a value in \([0, 1]\). “In” is slow at the start. “Out” is slow at the end. “In-out” is slow at both.

\[
\begin{aligned}
\text{easeInQuad}(t) &= t^{2} \\
\text{easeOutQuad}(t) &= 1 - (1 - t)^{2} \\
\text{easeInOutQuad}(t) &=
  \begin{cases}
    2t^{2} & t < \tfrac{1}{2} \\
    1 - 2(1 - t)^{2} & t \ge \tfrac{1}{2}
  \end{cases} \\[1em]
\text{easeInCubic}(t) &= t^{3} \\
\text{easeOutCubic}(t) &= 1 - (1 - t)^{3} \\
\text{easeInOutCubic}(t) &=
  \begin{cases}
    4t^{3} & t < \tfrac{1}{2} \\
    1 - \tfrac{1}{2}(-2t + 2)^{3} & t \ge \tfrac{1}{2}
  \end{cases}
\end{aligned}
\]

Smoothstep is an ease-in-out with a particularly tidy derivative. It is not a substitute for the exponential approach below: smoothstep needs a known start, a known end, and a \(t\) you advance yourself.

## Frame-rate-independent damping

Approach a goal \(g\) by solving \(\dot{x} = -k\,(x - g)\) with \(k > 0\). While \(g\) and \(k\) are constant the solution is

\[
x(t) = g + \bigl(x(0) - g\bigr)\, e^{-kt}
\]

Over one frame of length \(\Delta t\), with the goal held constant during the step, that is

\[
x \leftarrow \operatorname{lerp}\!\left(x,\, g,\, 1 - e^{-k \Delta t}\right)
\]

\(k\) is a rate in units of \(1/\text{seconds}\). Larger \(k\) closes the gap faster. Tuning \(k\) directly is awkward, so pick a half-life \(t_{1/2}\), the time in which the remaining error halves, and convert:

\[
e^{-k t_{1/2}} = \tfrac{1}{2}
\qquad\Rightarrow\qquad
k = \frac{\ln 2}{t_{1/2}}
\]

A half-life of a tenth of a second is \(k = \ln 2 / 0.1 \approx 6.93\). After \(0.1\,\text{s}\) the error is half of what it was, whether that interval was one frame or several.

It is frame-rate independent because the error is multiplied by \(e^{-k\Delta t}\) per step, and those factors compose exactly. \(n\) steps of \(\Delta t / n\) give

\[
\left(e^{-k\Delta t / n}\right)^{n} = e^{-k\Delta t}
\]

which is the factor from a single step of \(\Delta t\). The derivation assumed the goal did not move during the interval. A goal that changes every frame is still stable; it is simply no longer the exact continuous solution.

The same weight works per component on a vector. It does not work on an angle that wraps unless the lerp itself takes the short way around, and it does not work on a quaternion: use `Quaternion.Slerp` with this weight.

!!! warning "Do not scale a lerp by frame time"

    `Lerp(current, target, speed * dt)` is not this differential equation, and it is not frame-rate independent.

    `speed * dt` is only accidentally a blend weight. Once it exceeds 1, a clamped lerp freezes on the target and an unclamped lerp overshoots and can oscillate. Two frame rates also close a different fraction of the remaining gap over the same wall-clock second, so a value tuned at 60 Hz feels different at 30 Hz and at 120 Hz.

    Use \(1 - e^{-k\Delta t}\) as the weight. If a half-life is easier to tune, set \(k = \ln 2 / t_{1/2}\).

!!! info "Unity clamps the helpers you already know"

    `Mathf.Lerp` and `Mathf.SmoothStep` clamp their blend into \([0, 1]\). `Mathf.InverseLerp` does too, and it returns `0` when the two ends are equal instead of dividing by zero. The weight from the exponential formula already lies in \((0, 1)\), so the clamp does not change it. A remap that must extrapolate needs `Mathf.LerpUnclamped`, or the unclamped helpers below.

    `Mathf.SmoothDamp` is a different tool: a critically damped spring with a maximum speed, not smoothstep and not this exponential. Angles that wrap need `Mathf.LerpAngle`. Rotations need `Quaternion.Slerp`.

## Reference implementation

The C# is plain `.NET` (`System.MathF`), so it does not pick up Unity’s clamping. The HLSL is the same set of scalars; `lerp`, `saturate`, `exp`, and `log` are the built-ins. `log` is the natural logarithm in both languages.

=== "C#"

    ```csharp
    using System;

    public static class Interpolation
    {
        public static float Lerp(float a, float b, float t) => a + (b - a) * t;

        public static float InverseLerp(float a, float b, float value)
        {
            float span = b - a;
            return MathF.Abs(span) > 1e-8f ? (value - a) / span : 0f;
        }

        public static float Remap(
            float value, float inMin, float inMax, float outMin, float outMax)
        {
            return Lerp(outMin, outMax, InverseLerp(inMin, inMax, value));
        }

        public static float SmoothStep(float t)
        {
            t = Saturate(t);
            return t * t * (3f - 2f * t);
        }

        public static float SmootherStep(float t)
        {
            t = Saturate(t);
            return t * t * t * (t * (t * 6f - 15f) + 10f);
        }

        public static float EaseInQuad(float t) => t * t;

        public static float EaseOutQuad(float t)
        {
            float u = 1f - t;
            return 1f - u * u;
        }

        public static float EaseInOutQuad(float t)
        {
            if (t < 0.5f)
                return 2f * t * t;

            float u = -2f * t + 2f;
            return 1f - (u * u) * 0.5f;
        }

        public static float EaseInCubic(float t) => t * t * t;

        public static float EaseOutCubic(float t)
        {
            float u = 1f - t;
            return 1f - u * u * u;
        }

        public static float EaseInOutCubic(float t)
        {
            if (t < 0.5f)
                return 4f * t * t * t;

            float u = -2f * t + 2f;
            return 1f - (u * u * u) * 0.5f;
        }

        // Exact step of dx/dt = -sharpness (x - target).
        // Half-life in seconds is ln(2) / sharpness.
        public static float ExpDamp(float current, float target, float sharpness, float dt)
        {
            float weight = 1f - MathF.Exp(-sharpness * dt);
            return Lerp(current, target, weight);
        }

        public static float SharpnessFromHalfLife(float halfLifeSeconds)
        {
            return MathF.Log(2f) / halfLifeSeconds;
        }

        static float Saturate(float t) => t < 0f ? 0f : (t > 1f ? 1f : t);
    }
    ```

=== "HLSL"

    ```hlsl
    float InverseLerp(float a, float b, float value)
    {
        float span = b - a;
        return abs(span) > 1e-8 ? (value - a) / span : 0.0;
    }

    float Remap(float value, float inMin, float inMax, float outMin, float outMax)
    {
        return lerp(outMin, outMax, InverseLerp(inMin, inMax, value));
    }

    // smoothstep(0, 1, t) is this polynomial, and it also saturates.
    float SmoothStep01(float t)
    {
        t = saturate(t);
        return t * t * (3.0 - 2.0 * t);
    }

    float SmootherStep(float t)
    {
        t = saturate(t);
        return t * t * t * (t * (t * 6.0 - 15.0) + 10.0);
    }

    float EaseInQuad(float t) { return t * t; }

    float EaseOutQuad(float t)
    {
        float u = 1.0 - t;
        return 1.0 - u * u;
    }

    float EaseInOutQuad(float t)
    {
        if (t < 0.5)
            return 2.0 * t * t;
        float u = -2.0 * t + 2.0;
        return 1.0 - u * u * 0.5;
    }

    float EaseInCubic(float t) { return t * t * t; }

    float EaseOutCubic(float t)
    {
        float u = 1.0 - t;
        return 1.0 - u * u * u;
    }

    float EaseInOutCubic(float t)
    {
        if (t < 0.5)
            return 4.0 * t * t * t;
        float u = -2.0 * t + 2.0;
        return 1.0 - u * u * u * 0.5;
    }

    float ExpDamp(float current, float target, float sharpness, float dt)
    {
        float weight = 1.0 - exp(-sharpness * dt);
        return lerp(current, target, weight);
    }

    float SharpnessFromHalfLife(float halfLifeSeconds)
    {
        return log(2.0) / halfLifeSeconds;
    }
    ```
