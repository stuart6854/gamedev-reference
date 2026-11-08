---
uses:
  - name: Open worlds
    text: Roads, rivers, and rails laid along splines, and vehicles that follow them at a steady speed.
  - name: Platformers
    text: Moving platforms and camera rails on authored paths.
  - name: Strategy and tactics
    text: Smooth unit paths through waypoints, and patrol routes.
---

# Bézier curves and splines

Smooth curves through or near a set of control points: camera rails, patrol routes, roads, rivers, the path of a projectile in a cutscene. This page covers Bézier curves, joining them into splines, Catmull–Rom splines that pass through every point, moving along a curve at constant speed, finding the closest point, and orienting objects along a curve.

## Bézier curves

A **cubic Bézier** curve has four control points. It starts at `P0`, ends at `P3`, and is pulled towards `P1` and `P2` without passing through them:

```text
cubic(P0, P1, P2, P3, t):           // t in 0..1
    u = 1 - t
    return u*u*u * P0 + 3*u*u*t * P1 + 3*u*t*t * P2 + t*t*t * P3

derivative(P0, P1, P2, P3, t):      // velocity: direction and speed of travel
    u = 1 - t
    return 3*u*u * (P1 - P0) + 6*u*t * (P2 - P1) + 3*t*t * (P3 - P2)

second_derivative(P0, P1, P2, P3, t):
    return 6*(1 - t) * (P2 - 2*P1 + P0) + 6*t * (P3 - 2*P2 + P1)
```

- The curve leaves `P0` heading towards `P1`, and arrives at `P3` coming from `P2`. The handles `P1` and `P2` are the tangents an editor shows.
- The whole curve lies inside the convex hull of its four points, which gives a cheap bounding box.
- A **quadratic** Bézier (three points, `u*u*P0 + 2*u*t*P1 + t*t*P2`) is enough for simple arcs such as a thrown object's preview, but cannot make an S-shape.

### De Casteljau and splitting

The same point can be found by repeated linear interpolation, which is numerically stable and also **splits** the curve in two:

```text
de_casteljau(P0, P1, P2, P3, t):
    a = lerp(P0, P1, t);  b = lerp(P1, P2, t);  c = lerp(P2, P3, t)
    d = lerp(a, b, t);    e = lerp(b, c, t)
    f = lerp(d, e, t)                     // the point on the curve
    left  = (P0, a, d, f)                 // the curve from 0 to t
    right = (f, e, c, P3)                 // the curve from t to 1
```

Splitting is how editors insert a point into a curve without changing its shape, and how curves are subdivided adaptively for drawing or collision.

## Splines: chaining curves

A **spline** is several curves joined end to end. Each joint is a **knot**, with a handle on each side (an incoming and an outgoing tangent). How the handles relate decides how smooth the joint is:

| Joint | Handles | Result |
| --- | --- | --- |
| Broken (C0) | Independent | A corner |
| Aligned (G1) | Same direction, different lengths | Smooth direction; speed can jump |
| Mirrored (C1) | Same direction and length | Smooth direction and speed |

For a camera or vehicle, use mirrored or aligned joints: a corner in the path is a visible jerk.

## Catmull–Rom splines

Bézier control points are awkward to place by hand when the curve must pass through specific points (patrol waypoints, a road through set positions). A **Catmull–Rom** spline passes through every point, computing the tangents from the neighbouring points.

For the segment between `P1` and `P2`, with neighbours `P0` and `P3`, convert to a cubic Bézier:

```text
// Uniform Catmull–Rom
B0 = P1
B1 = P1 + (P2 - P0) / 6
B2 = P2 - (P3 - P1) / 6
B3 = P2
```

Uniform Catmull–Rom overshoots and can form loops and cusps where points are unevenly spaced. The **centripetal** variant fixes this by spacing the parameter by the square root of the distance between points:

```text
centripetal_to_bezier(P0, P1, P2, P3, alpha = 0.5):
    t0 = 0
    t1 = t0 + length(P1 - P0) ^ alpha
    t2 = t1 + length(P2 - P1) ^ alpha
    t3 = t2 + length(P3 - P2) ^ alpha
    m1 = (t2 - t1) * ((P1 - P0) / (t1 - t0) - (P2 - P0) / (t2 - t0) + (P2 - P1) / (t2 - t1))
    m2 = (t2 - t1) * ((P2 - P1) / (t2 - t1) - (P3 - P1) / (t3 - t1) + (P3 - P2) / (t3 - t2))
    return (P1, P1 + m1 / 3, P2 - m2 / 3, P2)
```

`alpha = 0` gives uniform, `0.5` centripetal (no cusps or self-intersections within a segment), and `1` chordal. Use centripetal unless there is a reason not to. Points that coincide make a `t` difference zero; remove duplicate points first.

For the first and last segments, which lack a neighbour, invent one: repeat the end point, or reflect its neighbour (`P0 = 2*P1 - P2`). For a closed loop, wrap around.

## Constant speed: arc length

`t` does not move at constant speed along a curve: points bunch up where the control points are close together. An object moving with `t += speed * dt` speeds up and slows down. Move by **distance** instead, using a table of lengths:

```text
build_length_table(curve, samples = 64):
    table = [(t = 0, length = 0)]
    previous = curve(0)
    total = 0
    for i in 1 .. samples:
        t = i / samples
        p = curve(t)
        total += length(p - previous)
        table.append((t, total))
        previous = p
    return table

t_at_distance(table, d):                  // d in 0..total
    find i with table[i].length <= d < table[i+1].length       // binary search
    f = (d - table[i].length) / (table[i+1].length - table[i].length)
    return lerp(table[i].t, table[i+1].t, f)

each frame:
    distance += speed * dt
    position = curve(t_at_distance(table, distance))
```

Build the table once per curve (rebuild when it is edited). 64 samples per segment is plenty for gameplay; more for long, tightly curved segments. The last entry is the curve's length.

## Closest point on a curve

For snapping, distance from a path, or knowing how far along a route a player is:

```text
closest_t(curve, point):
    best_t = sample the curve at 32–64 values of t, keep the closest
    refine around best_t:
        repeat a few times:
            check t ± step; move to the closest; halve step
    return best_t
```

The coarse pass finds the right part of the curve (a curve can come close to the point in several places); the refinement makes it precise. Newton's method on `dot(curve(t) - point, derivative(t)) = 0` converges faster, but needs the coarse pass first and a guard against stepping outside 0 to 1.

## Orienting along a curve

An object following a curve needs a rotation, not just a position. The **tangent** (the normalised derivative) gives forward. Up needs a choice:

- **World up**: `right = cross(up, forward)`, then `up = cross(forward, right)`. Fine for roads and paths on the ground. Fails when the curve points straight up or down, where `cross` gives zero.
- **Rotation-minimising frames**: carry an up vector along the curve, rotating it as little as possible between samples. Use them for tubes, rails, roller coasters, and anything that can go vertical or loop. The **double reflection** method (Wang et al., 2008) does it with two reflections per step:

```text
// x[i]: sample positions; t[i]: unit tangents; r[i]: up vectors. r[0] is chosen.
for i in 0 .. n - 2:
    v1 = x[i+1] - x[i];   c1 = dot(v1, v1)
    rL = r[i] - (2 / c1) * dot(v1, r[i]) * v1
    tL = t[i] - (2 / c1) * dot(v1, t[i]) * v1
    v2 = t[i+1] - tL;     c2 = dot(v2, v2)
    r[i+1] = rL - (2 / c2) * dot(v2, rL) * v2
```

Store the frames in the same table as the arc lengths, and interpolate between samples. Add an authored **roll** angle per knot on top, for banked turns.

## In Unity

The **Splines** package (`com.unity.splines`, 2.x) provides splines in the editor and at run time:

- A **SplineContainer** component holds one or more `Spline`s made of `BezierKnot`s, each with a `TangentMode`: `AutoSmooth` (Catmull–Rom style, through the knots), `Linear`, `Mirrored`, `Continuous`, or `Broken`, matching the joints above.
- `container.EvaluatePosition(t)`, `EvaluateTangent(t)`, and `EvaluateUpVector(t)` return world-space values for `t` from 0 to 1 along the whole spline. `container.CalculateLength()` gives its length.
- `SplineUtility.GetNearestPoint(spline, point, out nearest, out t)` finds the closest point (in the spline's local space), and `SplineUtility.GetPointAtLinearDistance` moves a given distance from a starting `t`, for constant-speed movement.
- Components cover common uses without code: **SplineAnimate** moves an object along a spline, **SplineExtrude** builds a tube mesh, and **SplineInstantiate** places prefabs along it, for fences and lamp posts.
