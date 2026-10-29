# Quaternions and rotations

A rotation stored as four numbers, which composes without gimbal lock and interpolates smoothly. You rarely need the algebra. You do need to know which way round a product applies, why a blend can take the long way, and why reading Euler angles back is a trap.

## What the four numbers are

A rotation by angle \(\theta\) about a unit axis \(\hat{\mathbf{a}}\) is the unit quaternion

\[
q = \left(\hat{\mathbf{a}}\sin\tfrac{\theta}{2},\; \cos\tfrac{\theta}{2}\right) = (x, y, z, w)
\]

Two facts follow from the half angle:

- \(q\) and \(-q\) are the same rotation. Rotating by \(\theta\) about \(\hat{\mathbf{a}}\) and by \(\theta - 360°\) about it give opposite signs and the same result.
- The identity is \((0, 0, 0, 1)\). A zero quaternion is not a rotation. In Unity, `default(Quaternion)` is all zeros, and using it is an error until it is set, usually to `Quaternion.identity`.

Only unit quaternions are rotations. Each product adds a little rounding error, so a rotation built by multiplying in a delta every frame for an hour should be normalised now and then.

## Composition

The product \(q_2 q_1\) is "rotate by \(q_1\), then by \(q_2\)", with both read in the same, world, frame. That is the same right-to-left order as matrices on column vectors.

The same product read the other way is "rotate by \(q_2\), then by \(q_1\) about the axes \(q_2\) produced", which is the local frame. In Unity terms:

```csharp
transform.rotation = delta * transform.rotation;   // delta about world axes
transform.rotation = transform.rotation * delta;   // delta about the object's own axes
```

That one line is the practical rule. Yaw about world up goes on the left. Pitch about the object's own right axis goes on the right.

Rotating a vector is `q * v` in Unity. In maths it is \(q\,\mathbf{v}\,q^{*}\), with \(\mathbf{v}\) as a quaternion with \(w = 0\).

## Inverse and relative rotation

For a unit quaternion, the inverse is the conjugate, which negates \(x, y, z\):

\[
q^{-1} = q^{*} = (-x, -y, -z, w)
\]

The rotation that takes orientation \(a\) to orientation \(b\), in world axes, is

\[
\Delta = b\, a^{-1} \qquad\text{so that}\qquad \Delta\, a = b
\]

and in \(a\)'s local axes it is \(a^{-1} b\). Unity: `Quaternion.Inverse`, and `Quaternion.Angle(a, b)` for the size of that difference in degrees.

## Interpolation

### Shortest path

Because \(q\) and \(-q\) are the same rotation, a blend from \(q_0\) to \(q_1\) can go either way round. If \(q_0 \cdot q_1 < 0\), the 4D dot product, negate \(q_1\) before blending, or the result spins the long way. Unity's `Slerp` and `Lerp` do this already. A blend written by hand, or in a shader, must do it itself.

### Slerp and nlerp

\[
\operatorname{slerp}(q_0, q_1, t) = \frac{\sin\bigl((1-t)\Omega\bigr)}{\sin\Omega}\, q_0 + \frac{\sin(t\Omega)}{\sin\Omega}\, q_1
\qquad
\cos\Omega = q_0 \cdot q_1
\]

\[
\operatorname{nlerp}(q_0, q_1, t) = \frac{(1-t)\,q_0 + t\,q_1}{\bigl|(1-t)\,q_0 + t\,q_1\bigr|}
\]

| | Slerp | Nlerp |
| --- | --- | --- |
| Path | Shortest arc | Shortest arc |
| Speed along it | Constant in \(t\) | Faster in the middle, by up to about 27% for a 180° blend, far less for small ones |
| Cost | Trig functions | A lerp and a normalise |
| Near-identical inputs | Divides by \(\sin\Omega \approx 0\); falls back to nlerp | Fine |
| Blending more than two | No direct form | Weighted sum, then normalise |

Use slerp when the speed of a long blend is visible, such as a camera swinging round. Use nlerp for small steps per frame, where the two match to within rounding, and for blending several poses, as animation systems do. Unity's `Quaternion.Lerp` is nlerp.

### Turning towards a target

Two frame-rate-independent forms:

```csharp
// Constant angular speed, in degrees per second. Arrives exactly.
rotation = Quaternion.RotateTowards(rotation, target, degreesPerSecond * Time.deltaTime);

// Eases in, with a half-life. Never quite arrives.
float k = Mathf.Log(2f) / halfLife;
rotation = Quaternion.Slerp(rotation, target, 1f - Mathf.Exp(-k * Time.deltaTime));
```

The second is the [damping step](interpolation.md#frame-rate-independent-damping) on a rotation. `Slerp(rotation, target, speed * Time.deltaTime)` is the same mistake as the scaled lerp warned about there.

## Building rotations

| Need | Unity | Notes |
| --- | --- | --- |
| Face a direction | `Quaternion.LookRotation(forward, up)` | Fails when `forward` is parallel to `up`, because the cross product it builds the frame from is zero. |
| Smallest rotation from one direction to another | `Quaternion.FromToRotation(from, to)` | Free to pick any roll. Aligning a character's up to a slope normal is a typical use. |
| Angle about an axis | `Quaternion.AngleAxis(degrees, axis)` | Degrees, like the rest of `Quaternion`. |
| From Euler angles | `Quaternion.Euler(x, y, z)` | Applies \(z\), then \(x\), then \(y\), each about the world axes. |

`FromToRotation` followed by a separate yaw is how to align to a slope and still face a direction: `Quaternion.FromToRotation(Vector3.up, normal) * Quaternion.Euler(0, yaw, 0)`.

## Avoiding Euler angles

Euler angles are fine as an input, such as a yaw and pitch you store and clamp yourself. They are a poor representation to read back and modify:

- **Gimbal lock.** At a pitch of \(\pm 90°\), yaw and roll rotate about the same axis, and one degree of freedom is lost. Any blend that passes through that pitch can twist.
- **Many answers.** \((180, 0, 180)\) and \((0, 180, 0)\) are the same rotation. Unity's `eulerAngles` returns one of them, in \([0, 360)\), not the one you set. Code that reads `eulerAngles.x`, adds to it, and clamps to \([-85, 85]\) breaks when the read value is 350.
- **Blending per component** goes the wrong way round at the wrap, and through odd intermediate orientations even when it does not.

Store the angles you control as floats, clamp them, and build the rotation from them each frame. The [first-person camera](../unity/cameras/first-person.md) does exactly that with its yaw and pitch.

## Swing and twist

Splitting a rotation into a twist about an axis and a swing of that axis answers "how far has this forearm rolled", or limits a joint's roll without touching its bend:

```text
decompose(q, axis):                     // axis is unit length
    p = dot(q.xyz, axis) * axis         // the part of the vector part along axis
    twist = normalise(p.x, p.y, p.z, q.w)
    swing = q * inverse(twist)
    return swing, twist
```

When the vector part along the axis and \(w\) are both near zero, the rotation is a 180° swing with no defined twist. Return identity for the twist in that case.

## Language tips

=== "Unity C#"

    - `Quaternion * Vector3` rotates the vector. `Vector3 * Quaternion` does not compile.
    - `Quaternion.Slerp` and `Quaternion.Lerp` clamp `t` to \([0, 1]\). The `Unclamped` versions exist for overshoot.
    - `Quaternion.Euler` and `eulerAngles` use degrees. `Unity.Mathematics` uses radians: `quaternion.EulerZXY` matches `Quaternion.Euler`'s order, and `quaternion.Euler` defaults to the same `ZXY` order.
    - Inspector rotation fields show Euler angles derived from the stored quaternion. Values typed there round-trip through the same ambiguity.

=== "HLSL"

    - There is no quaternion type. Pass rotations as a `float4` and rotate with the expanded form: `v + 2 * cross(q.xyz, cross(q.xyz, v) + q.w * v)`.
    - Blending skinning or instance rotations in a shader needs the shortest-path sign flip by hand.

!!! warning "Common pitfalls"

    `a * b` and `b * a` are different rotations. Left multiplies about world axes, right about local ones.

    A hand-written blend without the sign check spins the long way round on roughly half of all inputs.

    Reading `eulerAngles`, changing one component, and writing it back jumps when the read value crosses 360 or the pole. Store and clamp your own angles.

    `default(Quaternion)` is zero, not identity. A rotation field that was never assigned breaks the first rotation that uses it.

    `Slerp` by `speed * deltaTime` is frame-rate dependent. Use `RotateTowards`, or the exponential weight.
