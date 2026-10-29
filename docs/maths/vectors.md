# Vectors, dot and cross products

The two products that answer most gameplay geometry questions: is it in front of me, how far along this direction, which side is it on, and what are its coordinates in my frame. Formulas are engine-agnostic. Unity names follow each one, since Unity's left-handed axes change how a cross product looks, not how it is computed.

## Dot product

\[
\mathbf{a} \cdot \mathbf{b} = a_x b_x + a_y b_y + a_z b_z = |\mathbf{a}|\,|\mathbf{b}|\cos\theta
\]

\(\theta\) is the angle between the two vectors. With both normalised, the dot product is \(\cos\theta\) directly: \(1\) for the same direction, \(0\) for perpendicular, \(-1\) for opposite. Its sign needs no normalising at all.

### Facing tests

| Question | Test |
| --- | --- |
| Is the target in front of me? | \(\mathbf{f} \cdot (\mathbf{p}_{\text{target}} - \mathbf{p}_{\text{self}}) > 0\) |
| Is it inside a view cone of half-angle \(\alpha\)? | \(\mathbf{f} \cdot \hat{\mathbf{d}} \ge \cos\alpha\), with \(\hat{\mathbf{d}}\) the normalised direction to it |
| Is the surface facing the light? | \(\mathbf{n} \cdot \hat{\mathbf{l}} > 0\) |
| Is the ground walkable? | \(\mathbf{n} \cdot \mathbf{up} \ge \cos(\text{max slope})\) |

\(\mathbf{f}\) is a unit forward vector. Compute \(\cos\alpha\) once, not per test: comparing cosines replaces an `acos` per target with a multiply-add. A cone test needs \(\hat{\mathbf{d}}\) normalised, or a target twice as far away passes twice as easily.

To avoid the square root in that normalise, compare squares, keeping the sign:

\[
\mathbf{f} \cdot \mathbf{d} \ge 0 \quad\text{and}\quad (\mathbf{f} \cdot \mathbf{d})^2 \ge \cos^2\alpha \; |\mathbf{d}|^2
\]

That form only holds for \(\alpha \le 90°\). A wider cone needs the normalised form.

### Projection

The length of \(\mathbf{a}\) along a unit direction \(\hat{\mathbf{u}}\) is \(\mathbf{a} \cdot \hat{\mathbf{u}}\). The vector part of \(\mathbf{a}\) along it, and the part left over, are

\[
\mathbf{a}_{\parallel} = (\mathbf{a} \cdot \hat{\mathbf{u}})\,\hat{\mathbf{u}}
\qquad
\mathbf{a}_{\perp} = \mathbf{a} - \mathbf{a}_{\parallel}
\]

Projecting onto a plane with unit normal \(\hat{\mathbf{n}}\) is the second one: \(\mathbf{a} - (\mathbf{a} \cdot \hat{\mathbf{n}})\,\hat{\mathbf{n}}\). Movement along a slope is the input direction projected onto the ground plane, then renormalised so a steep slope is not slower.

Unity: `Vector3.Dot`, `Vector3.Project`, and `Vector3.ProjectOnPlane`. Both projection helpers accept a normal that is not unit length, and divide by its squared length.

### Reflection

Bouncing \(\mathbf{v}\) off a surface with unit normal \(\hat{\mathbf{n}}\) flips its normal part:

\[
\mathbf{r} = \mathbf{v} - 2\,(\mathbf{v} \cdot \hat{\mathbf{n}})\,\hat{\mathbf{n}}
\]

Unity: `Vector3.Reflect`. It assumes \(\hat{\mathbf{n}}\) is normalised and does not check.

### Distance comparisons

\(\mathbf{d} \cdot \mathbf{d} = |\mathbf{d}|^2\). To ask "is it within range \(r\)", compare \(|\mathbf{d}|^2 \le r^2\) and skip the square root. Unity: `sqrMagnitude`.

## Cross product

\[
\mathbf{a} \times \mathbf{b} =
\begin{pmatrix}
a_y b_z - a_z b_y \\
a_z b_x - a_x b_z \\
a_x b_y - a_y b_x
\end{pmatrix}
\qquad
|\mathbf{a} \times \mathbf{b}| = |\mathbf{a}|\,|\mathbf{b}|\sin\theta
\]

The result is perpendicular to both inputs. Its length is the area of the parallelogram they span, so it is zero when they are parallel. Swapping the inputs flips it: \(\mathbf{b} \times \mathbf{a} = -(\mathbf{a} \times \mathbf{b})\).

The formula is the same in every engine. What changes is the picture. In a right-handed frame, the result follows the right-hand rule. Unity is left-handed (\(+x\) right, \(+y\) up, \(+z\) forward), so the same numbers follow the left-hand rule. In Unity:

```text
Cross(up, forward)    = right
Cross(right, up)      = forward
Cross(forward, right) = up
```

Code that ports a formula from a right-handed source, such as most textbooks, gets the right numbers and the mirrored picture. A triangle's winding, and which side its normal points, is where that bites.

### Triangle normal

\[
\mathbf{n} = (\mathbf{b} - \mathbf{a}) \times (\mathbf{c} - \mathbf{a})
\]

Normalise it for lighting. Its length, halved, is the triangle's area. Unity's front faces are clockwise as seen by the camera, which with the left-handed cross product makes this \(\mathbf{n}\) point towards the viewer.

### Signed angle about an axis

The angle from \(\mathbf{a}\) to \(\mathbf{b}\), with its sign taken from an axis \(\mathbf{n}\) such as world up:

\[
\theta = \operatorname{atan2}\!\bigl((\mathbf{a} \times \mathbf{b}) \cdot \hat{\mathbf{n}},\; \mathbf{a} \cdot \mathbf{b}\bigr)
\]

This is better than `acos` of a normalised dot product. `acos` loses precision near \(0\) and \(\pi\), returns `NaN` when rounding pushes its input past \(\pm 1\), and has no sign. `atan2` takes unnormalised inputs, since both arguments scale by the same \(|\mathbf{a}|\,|\mathbf{b}|\).

Unity: `Vector3.SignedAngle(from, to, axis)` returns degrees in \([-180, 180]\). `Vector3.Angle` is unsigned, in \([0, 180]\).

### 2D: the perp dot product

In 2D, the cross product's \(z\) component is all that is left:

\[
\mathbf{a} \times \mathbf{b} = a_x b_y - a_y b_x
\]

With \(+x\) right and \(+y\) up, it is positive when \(\mathbf{b}\) is counter-clockwise from \(\mathbf{a}\), negative when clockwise, and zero when they are parallel. That answers "is the target to my left or my right", "which way should I turn", and "which side of this line is the point". The signed 2D angle is `atan2(cross, dot)`, as above.

## Change of basis

A frame is an origin and three unit axes: right \(\mathbf{r}\), up \(\mathbf{u}\), and forward \(\mathbf{f}\), all perpendicular. A direction \(\mathbf{v}\) in world space has local coordinates

\[
v_{\text{local}} = (\mathbf{v} \cdot \mathbf{r},\; \mathbf{v} \cdot \mathbf{u},\; \mathbf{v} \cdot \mathbf{f})
\]

and back again, \(\mathbf{v} = x\,\mathbf{r} + y\,\mathbf{u} + z\,\mathbf{f}\). For a point, subtract the frame's origin first, and add it back after. The dot-product form only works because the axes are orthonormal. With scale or shear, use the inverse matrix.

Uses: "how far ahead and how far to the side is the target", input relative to a camera, and the local velocity an animator wants for strafe blends.

Unity: `transform.InverseTransformDirection` and `InverseTransformPoint` go to local space, and `TransformDirection` and `TransformPoint` come back. The `Point` versions include scale. `InverseTransformVector` and `TransformVector` include scale but not position.

### Building a frame from a forward vector

```text
f = normalise(forward)
r = normalise(cross(world_up, f))       // Unity's argument order
u = cross(f, r)                         // already unit length
```

This fails when `forward` is parallel to `world_up`, because the first cross product is zero. Looking straight up or down, pick a different reference, such as the previous frame's right vector. Unity's `Quaternion.LookRotation(forward, up)` builds the same frame and has the same blind spot.

## Language tips

=== "Unity C#"

    - `Vector3.normalized` returns `Vector3.zero` for a vector shorter than about \(10^{-5}\), instead of dividing by zero. Code that then takes a dot product gets `0`, which reads as "perpendicular". Check the length first when zero means something.
    - `Vector3.Angle` and `SignedAngle` return degrees. `Mathf.Atan2` and `Mathf.Acos` return radians.
    - `Vector2` converts to and from `Vector3` implicitly, dropping or zeroing `z`. A top-down game on the XZ plane needs `new Vector2(v.x, v.z)`, not the implicit conversion, which keeps `x` and `y`.
    - `Unity.Mathematics` (`float3`, `math.dot`, `math.cross`) has the same formulas and works in Burst. `math.normalize` of a zero vector returns `NaN`; `math.normalizesafe` returns zero.

=== "HLSL"

    - `dot`, `cross`, `normalize`, `reflect`, and `length` are built in. `normalize` of a zero vector is `NaN`, which spreads through every later step.
    - `reflect(i, n)` has the same formula as above and also expects a unit `n`.

!!! warning "Common pitfalls"

    A cone test with an unnormalised direction passes distant targets more easily. Normalise, or use the squared form for cones up to 90°.

    `acos` of a dot product of two unit vectors can see \(1.0000001\) after rounding and return `NaN`. Clamp to \([-1, 1]\), or use `atan2`.

    The cross product's argument order matters, and so does the engine's handedness. Swap the order and the normal points into the surface.

    Building a frame with `cross(world_up, forward)` fails when looking straight up or down. Handle the parallel case.

    The dot-product change of basis assumes unit, perpendicular axes. A scaled transform needs its inverse matrix.
