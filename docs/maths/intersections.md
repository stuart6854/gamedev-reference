---
uses:
  - name: Shooters
    text: Hitscan against boxes and spheres without colliders, and bullet impacts on triangles.
  - name: Strategy and tactics
    text: Clicking the ground plane under the cursor, and picking units by their bounds.
  - name: Base building
    text: Overlap tests for whether a placed piece fits.
---

# Intersection tests

Does this ray hit that shape, and where? Do these two shapes overlap? Physics engines answer these for colliders. The formulas are still needed for picking without colliders, custom spatial structures, jobs and shaders, and anything that runs where the physics scene does not.

Conventions: a ray is \(\mathbf{p}(t) = \mathbf{o} + t\,\mathbf{d}\) for \(t \ge 0\). With \(\mathbf{d}\) normalised, \(t\) is the distance along the ray. Every test below returns the nearest \(t\), or no hit.

## Ray against plane

A plane with unit normal \(\hat{\mathbf{n}}\) through a point \(\mathbf{p}_0\):

\[
t = \frac{\hat{\mathbf{n}} \cdot (\mathbf{p}_0 - \mathbf{o})}{\hat{\mathbf{n}} \cdot \mathbf{d}}
\]

If \(\hat{\mathbf{n}} \cdot \mathbf{d}\) is near zero, the ray is parallel to the plane: no hit, or lying in it. A negative \(t\) means the plane is behind the ray. A one-sided test, such as only hitting the front of a floor, also requires \(\hat{\mathbf{n}} \cdot \mathbf{d} < 0\).

Unity: `new Plane(normal, point).Raycast(ray, out float enter)`. The [strategy camera](../unity/cameras/rts.md) uses it to find the ground point under the cursor.

## Ray against sphere

Centre \(\mathbf{c}\), radius \(r\), \(\mathbf{d}\) normalised. Let \(\mathbf{m} = \mathbf{o} - \mathbf{c}\):

```text
b = dot(m, d)
c = dot(m, m) - r * r
if c > 0 and b > 0: no hit          // outside, and pointing away
disc = b * b - c
if disc < 0: no hit                 // the line misses
t = -b - sqrt(disc)
if t < 0: t = 0                     // the ray starts inside
```

This is the quadratic \(t^2 + 2bt + c = 0\) with the early outs first, so most misses cost no square root.

## Ray against axis-aligned box

The slab method. The box is the overlap of three slabs, one per axis. Find where the ray enters and leaves each, and keep the latest entry and the earliest exit:

```text
inv = 1 / d                         // per component; 1/0 is +-infinity
t1 = (box.min - o) * inv            // per component
t2 = (box.max - o) * inv
t_enter = max(min(t1.x, t2.x), min(t1.y, t2.y), min(t1.z, t2.z))
t_exit  = min(max(t1.x, t2.x), max(t1.y, t2.y), max(t1.z, t2.z))
hit if t_exit >= max(t_enter, 0)
t = t_enter if t_enter >= 0 else 0  // 0 when the ray starts inside
```

A direction component of zero makes `inv` infinite, which the min and max handle, as long as the language follows IEEE floats. The one case that breaks is a ray lying exactly on a slab's boundary, where \(0 \times \infty\) is NaN. Nudge the origin, or treat NaN as a miss.

The reciprocal is computed once per ray, so testing one ray against many boxes is a few multiplies each. This is the test inside every bounding-volume hierarchy.

Unity: `Bounds.IntersectRay(ray, out float distance)`.

### Oriented box

Transform the ray into the box's local space with the inverse rotation and translation, and run the axis-aligned test there. With no scale, \(t\) is unchanged. Unity: `transform.InverseTransformPoint` and `InverseTransformDirection` on the ray, then the box's local bounds.

## Ray against triangle

Möller–Trumbore solves for \(t\) and the barycentric coordinates \(u, v\) together, without building the triangle's plane first:

```text
e1 = b - a
e2 = c - a
p = cross(d, e2)
det = dot(e1, p)
if abs(det) < epsilon: no hit       // parallel to the triangle
inv = 1 / det
s = o - a
u = dot(s, p) * inv
if u < 0 or u > 1: no hit
q = cross(s, e1)
v = dot(d, q) * inv
if v < 0 or u + v > 1: no hit
t = dot(e2, q) * inv
hit if t > epsilon
```

The hit point is \(\mathbf{a} + u\,\mathbf{e}_1 + v\,\mathbf{e}_2\). \(u\) and \(v\) interpolate anything stored per vertex: UVs, normals, colours.

The sign of `det` tells which face was hit. Keep only `det > epsilon` to cull back faces. Which sign is the front depends on the winding and the engine's handedness. In Unity, front faces wind clockwise as seen by the camera; see the [triangle normal](vectors.md#triangle-normal).

## Overlap tests

| Shapes | Overlap when | Notes |
| --- | --- | --- |
| Sphere, sphere | \(\lvert\mathbf{c}_1 - \mathbf{c}_2\rvert^2 \le (r_1 + r_2)^2\) | Compare squares. No square root. |
| Box, box (axis-aligned) | \(\text{min}_1 \le \text{max}_2\) and \(\text{min}_2 \le \text{max}_1\) on every axis | One failing axis is enough to reject. Unity: `Bounds.Intersects`. |
| Sphere, box (axis-aligned) | \(\lvert\text{clamp}(\mathbf{c}, \text{min}, \text{max}) - \mathbf{c}\rvert^2 \le r^2\) | The clamp is the closest point on the box. Unity: `Bounds.ClosestPoint`. |
| Point, box (oriented) | The local-space point is inside the local box | Transform the point, not the box. |
| Capsule, capsule | The closest distance between the two core segments \(\le r_1 + r_2\) | Needs the segment–segment closest-points routine. |

## Separating axis test

Two convex shapes do not overlap if and only if some axis exists on which their projections do not overlap. To prove an overlap, test every axis that could separate them; to reject, one separating axis is enough.

For each candidate axis \(\mathbf{L}\), project both shapes onto it and compare intervals. For boxes, with centre distance \(\mathbf{T}\), half-extents \(e_i\), and local axes \(\mathbf{u}_i\):

\[
r_A = \sum_i e^A_i\,\lvert\mathbf{u}^A_i \cdot \mathbf{L}\rvert
\qquad
r_B = \sum_i e^B_i\,\lvert\mathbf{u}^B_i \cdot \mathbf{L}\rvert
\qquad
\text{separated if } \lvert\mathbf{T} \cdot \mathbf{L}\rvert > r_A + r_B
\]

The candidate axes:

| Shapes | Axes to test |
| --- | --- |
| 2D convex polygons | The normal of every edge of both polygons. |
| Two oriented boxes in 3D | 3 face normals of A, 3 of B, and the 9 cross products of an edge of A with an edge of B: 15 in all. |
| Triangle and box in 3D | 3 box face normals, the triangle normal, and 9 edge cross products: 13. |

A cross product of two nearly parallel edges is nearly zero, and testing against it can report a false separation. Skip axes whose length is below a small epsilon; the face axes already cover that case.

The axis with the smallest overlap, when all of them overlap, is the minimum translation to push the shapes apart: that is how a simple collision response finds its contact normal.

## Precision

- Accept hits at \(t > \varepsilon\), not \(t > 0\), when the ray starts on a surface, such as a bounce or a shadow ray. Otherwise it hits the surface it left.
- Scale epsilons to the scene. \(10^{-6}\) is fine for objects a metre across; far from the origin, floats are coarser and the same epsilon is too small.
- A ray through the shared edge of two triangles can hit both, or, after rounding, neither. Games rarely care. Renderers that do use a watertight ray–triangle test.

!!! warning "Common pitfalls"

    The sphere test assumes \(\mathbf{d}\) is unit length. With an unnormalised direction, \(t\) is in units of \(\lvert\mathbf{d}\rvert\), and the formula above is wrong. Normalise first, or use the full quadratic with \(a = \mathbf{d} \cdot \mathbf{d}\).

    Forgetting the \(t \ge 0\) check returns hits behind the ray.

    A slab test without care for zero direction components divides by zero in languages that trap on it. Precompute `inv` once per ray and rely on IEEE infinities.

    Testing only face normals for two boxes in 3D misses edge-on-edge separations, and reports overlaps that are not there. Include the 9 cross products.
