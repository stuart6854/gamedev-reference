# Frustum and visibility tests

Is a point on screen? Is this object inside the camera's view volume? Is it actually visible, or behind a wall? And when it is off screen, where should its indicator arrow sit on the edge? The transforms behind these are on the [coordinate spaces](../graphics/coordinate-spaces.md) page.

## A point on screen

Project the point to clip space, \(\mathbf{p}_{\text{clip}} = P\,V\,\mathbf{p}_{\text{world}}\). It is inside the view volume when

\[
-w \le x \le w, \qquad -w \le y \le w, \qquad z \text{ in the API's depth range, scaled by } w
\]

with \(w = w_{\text{clip}} > 0\). The \(w > 0\) check is the "in front of the camera" test. Without it, a point behind the camera divides by a negative \(w\) and lands in the middle of the screen, mirrored.

Unity does the divide and the remap for you. `camera.WorldToViewportPoint(p)` returns \(x, y \in [0, 1]\) across the view and \(z\) as the distance in front of the camera:

```csharp
Vector3 v = cam.WorldToViewportPoint(position);
bool onScreen = v.z > 0f && v.x >= 0f && v.x <= 1f && v.y >= 0f && v.y <= 1f;
```

`WorldToScreenPoint` is the same in pixels.

## Frustum planes

The view volume is bounded by six planes: left, right, bottom, top, near, far. Each is \(\mathbf{n} \cdot \mathbf{x} + d = 0\), with \(\mathbf{n}\) pointing inwards, so a point inside is on the positive side of all six.

They can be read straight out of the combined matrix \(M = P\,V\) (Gribb and Hartmann). With \(\mathbf{m}_i\) the \(i\)-th row of \(M\), and the OpenGL depth convention \(-w \le z \le w\) that Unity's `projectionMatrix` uses:

| Plane | Coefficients \((n_x, n_y, n_z, d)\) |
| --- | --- |
| Left | \(\mathbf{m}_4 + \mathbf{m}_1\) |
| Right | \(\mathbf{m}_4 - \mathbf{m}_1\) |
| Bottom | \(\mathbf{m}_4 + \mathbf{m}_2\) |
| Top | \(\mathbf{m}_4 - \mathbf{m}_2\) |
| Near | \(\mathbf{m}_4 + \mathbf{m}_3\) |
| Far | \(\mathbf{m}_4 - \mathbf{m}_3\) |

Each comes from one inequality above: \(x \ge -w\) is \(\mathbf{m}_1 \cdot \mathbf{p} \ge -\mathbf{m}_4 \cdot \mathbf{p}\), which rearranges to the left plane. Divide each plane by \(\lvert\mathbf{n}\rvert\) so that \(\mathbf{n} \cdot \mathbf{x} + d\) is a true distance. With a \([0, 1]\) depth range, the near plane is \(\mathbf{m}_3\) alone.

Unity: `GeometryUtility.CalculateFrustumPlanes(camera)` returns the six in the order left, right, bottom, top, near, far. Pass a `Plane[6]` you keep, to avoid allocating every frame.

## Bounds against the frustum

### Sphere

For each plane, the signed distance from the centre is \(s = \mathbf{n} \cdot \mathbf{c} + d\).

- \(s < -r\) for any plane: entirely outside. Stop.
- \(s \ge r\) for every plane: entirely inside.
- Otherwise: intersecting.

### Axis-aligned box

Test one point per plane: the box's corner furthest along the plane's normal, its positive vertex. If that corner is outside, the whole box is. With the box as a centre \(\mathbf{c}\) and half-extents \(\mathbf{e}\), the same test is

\[
r = e_x \lvert n_x\rvert + e_y \lvert n_y\rvert + e_z \lvert n_z\rvert,
\qquad
\text{outside if } \mathbf{n} \cdot \mathbf{c} + d < -r
\]

which is the box's projected radius on the normal, the same quantity the separating axis test uses.

Unity: `GeometryUtility.TestPlanesAABB(planes, bounds)`.

### False positives

Testing each plane separately is conservative. A large box just outside a corner of the frustum can be on the inner side of every plane, and be reported as visible when it is not. For culling, that only costs drawing something unnecessary. For gameplay, such as "is the enemy on screen", test the centre point too, or accept the rare false yes.

## Culling

Unity already culls renderers against every camera's frustum, and against occlusion data if **Occlusion Culling** is baked. Do not write frustum tests to save draw calls. They are for gameplay and for systems that are not renderers:

- Skip expensive updates, such as animation or AI ticks, for objects off screen.
- Spawn enemies only where the player cannot see.
- Trigger "first seen" events.

For many objects, Unity's `CullingGroup` does the test in native code: you give it bounding spheres and it raises an event when each one becomes visible or invisible, or changes distance band. It is cheaper than testing thousands of objects in C# every frame.

## In view is not visible

A point in the frustum may be behind a wall. To check the line of sight, cast from the camera to the point, and ignore the target's own colliders:

```csharp
Vector3 from = cam.transform.position;
Vector3 to = target.position;
bool seen = onScreen && !Physics.Linecast(from, to, occluderMask);
```

For a large target, cast to several points on it, such as its head and its centre. One ray to the pivot misses a character whose feet are behind a low wall.

`Renderer.isVisible` and `OnBecameVisible` are true if any camera renders the object, including the Scene view camera in the editor and the shadow pass. They are not a "the player can see this" test.

## Off-screen indicators

An arrow on the screen edge pointing at a target off screen:

```text
v = world_to_viewport(target)           // x, y in [0, 1]; z is depth
if v.z < 0:                             // behind the camera: the projection is mirrored
    v.x = 1 - v.x
    v.y = 1 - v.y
if v.z > 0 and v is inside the margin: draw nothing, or a marker at v

d = (v.xy - 0.5) * screen_size          // from the centre, in pixels
half = 0.5 * screen_size - margin
scale = max(|d.x| / half.x, |d.y| / half.y)
d = d / scale                           // pushed onto the inset rectangle
position = 0.5 * screen_size + d
angle = atan2(d.y, d.x)                 // arrow rotation
```

Work in pixels, not viewport units. A viewport is square in its units, and the angle from the centre would be wrong on a wide screen.

The mirroring step is needed because a point behind the camera projects to the opposite side of the screen. Without it, an enemy behind and to the left gets an arrow on the right.

!!! warning "Common pitfalls"

    A screen-space test without the \(z > 0\) or \(w > 0\) check counts points behind the camera as on screen.

    Planes extracted from \(P\,V\) without normalising give correct inside and outside answers, but wrong distances, so a sphere test with a radius rejects at the wrong place.

    `GeometryUtility.CalculateFrustumPlanes(camera)` allocates a new array each call. Use the overload that fills an array you pass.

    `Renderer.isVisible` is true while the Scene view shows the object. Testing it in the editor gives different results from a build.

    An off-screen arrow computed in viewport units points the wrong way on non-square screens. Convert to pixels first.
