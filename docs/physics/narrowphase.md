# Narrowphase

For each pair from the [broadphase](broadphase.md), the narrowphase decides whether the two shapes actually touch, and if so produces a **contact manifold**: the contact normal, and one to four contact points with their penetration depths. The [solver](solver.md) uses the manifold to push the bodies apart.

## Dispatch by shape pair

```text
collide[sphere][sphere]   = sphere_sphere
collide[sphere][capsule]  = sphere_capsule
collide[capsule][capsule] = capsule_capsule
collide[box][box]         = box_box_sat
collide[convex][convex]   = gjk_epa
collide[*][mesh]          = shape_vs_triangles
```

A table indexed by both shape types picks the function. Closed-form functions for the common simple pairs are much faster than the general algorithms, so write those first, and fall back to GJK for everything else.

## Simple pairs

```text
sphere_sphere(a, b):
    d = b.centre - a.centre
    dist = length(d)
    if dist >= a.radius + b.radius: return no contact
    normal = dist > 0 ? d / dist : (0, 1, 0)
    point = a.centre + normal * a.radius
    return Manifold { normal, points: [{ point, depth = a.radius + b.radius - dist }] }
```

A **capsule** is a segment with a radius. Sphere against capsule is sphere against the closest point on the capsule's segment; capsule against capsule is sphere against sphere at the closest points between the two segments. That is why capsules are the usual shape for characters: every test against them reduces to closest points and spheres.

## Separating axis test

Two convex shapes do not overlap if and only if some axis exists on which their projections do not overlap (the [separating axis test](../maths/intersections.md#separating-axis-test)). For two boxes, the candidate axes are the 3 face normals of each box and the 9 cross products of their edge directions: 15 axes.

```text
box_box(a, b):
    best_depth = infinity
    for axis in 15 candidate axes (skip near-zero cross products):
        overlap = projection overlap of a and b on axis
        if overlap < 0: return no contact                    // a separating axis: done
        if overlap < best_depth: best_depth, best_axis = overlap, axis
    the minimum-overlap axis is the contact normal; build the manifold (below)
```

Prefer face axes over edge axes when the depths are nearly equal (multiply edge depths by a small factor, such as 1.05). Otherwise the chosen axis flickers between a face and an edge from step to step, and a resting box jitters.

## GJK

The **Gilbert–Johnson–Keerthi** algorithm works for any pair of convex shapes, given only a **support function**: the point of the shape farthest in a given direction.

```text
support(sphere, d)  = centre + normalize(d) * radius
support(box, d)     = centre + Σ over local axes i: sign(dot(d, axis_i)) * half_extent_i * axis_i
support(hull, d)    = the vertex with the largest dot(vertex, d)
support(capsule, d) = support of its segment in d + normalize(d) * radius
```

GJK works on the **Minkowski difference** `A − B`: the set of all `a − b`. The shapes overlap exactly when the origin is inside it. Its support function is `support(A, d) − support(B, −d)`, so it never has to be built.

```text
gjk_intersect(A, B):
    d = any direction, e.g. B.centre - A.centre
    simplex = [ support(A, d) - support(B, -d) ]
    d = -simplex[0]
    loop:
        p = support(A, d) - support(B, -d)
        if dot(p, d) < 0: return false             // could not get past the origin: no overlap
        simplex.add(p)
        if do_simplex(simplex, d): return true      // the simplex contains the origin
```

`do_simplex` finds the part of the simplex (a point, line, triangle, or tetrahedron) closest to the origin, drops the other points, and sets `d` towards the origin from it:

| Simplex | Keeps | New direction |
| --- | --- | --- |
| Line `AB` (A newest) | The segment, or just A | Perpendicular from the segment towards the origin, or `-A` |
| Triangle `ABC` | The triangle, an edge, or A | Triangle normal facing the origin, or an edge's perpendicular |
| Tetrahedron `ABCD` | A face, or all four | Towards the origin from the closest face; all four means the origin is inside |

```text
// The line case, as an example. a is the newest point.
line_case(simplex, d):
    a, b = simplex
    ab = b - a;  ao = -a
    if dot(ab, ao) > 0:
        d = cross(cross(ab, ao), ab)          // perpendicular to ab, towards the origin
    else:
        simplex = [a];  d = ao
    return false
```

GJK can also return the **distance** and closest points between non-overlapping shapes, which is how continuous collision and speculative contacts measure gaps. Casey Muratori's "Implementing GJK" video and Gino van den Bergen's book *Collision Detection in Interactive 3D Environments* are the standard explanations.

## EPA

GJK says the shapes overlap but not by how much. The **expanding polytope algorithm** starts from GJK's final tetrahedron (which contains the origin) and grows it towards the surface of the Minkowski difference:

```text
epa(A, B, tetrahedron):
    polytope = tetrahedron's faces
    loop:
        face = the face closest to the origin
        p = support in face.normal
        if dot(p, face.normal) - face.distance < tolerance:
            return normal = face.normal, depth = face.distance
        remove every face that p can see; patch the hole with faces from its edges to p
```

The closest face of the final polytope gives the contact normal and penetration depth. EPA is slower than GJK and numerically delicate. Many engines avoid needing it by giving shapes a small rounded **margin** (convex radius): the core shapes are tested with GJK for distance, which is robust, and only deep overlaps of the cores need EPA.

## Contact manifolds

A box resting on the ground needs several contact points; one point lets it rock and spin. For box-box and hull-hull contacts with a face normal, find the points by **clipping**:

```text
face_contact(reference_body, incident_body, normal):
    reference = the face of reference_body most aligned with normal
    incident  = the face of incident_body most aligned with -normal
    polygon = incident face's vertices
    for each side plane of the reference face:
        polygon = clip(polygon, side plane)                   // Sutherland–Hodgman
    keep the points of polygon below the reference face; depth = distance below it
    reduce to at most 4 points: deepest, then the ones that span the largest area
```

Four well-spread points are enough for a stable resting contact, and keeping the number bounded keeps the solver's cost bounded.

### Persistent manifolds

Recomputing a manifold from scratch each step makes contact points jump around. Instead, keep each pair's manifold across steps, and match new points to old ones (by the features that produced them, such as "edge 3 of A against face 1 of B", or by proximity). A matched point keeps its **accumulated impulse** from last step, which the solver uses for [warm starting](solver.md#warm-starting). Stacks of boxes are only stable with this.

## Triangle meshes

Level geometry is a triangle mesh, which is not convex. Collide against it triangle by triangle:

```text
shape_vs_mesh(shape, mesh):
    for triangle in mesh.bvh.query(shape.aabb):         // static BVH built once
        contacts += convex_vs_triangle(shape, triangle)
    merge and reduce contacts into one manifold
```

The classic problem is **internal edges**: a box sliding across two coplanar triangles hits the edge between them and bumps, because against that triangle alone the edge looks like a real edge. Fixes precompute, per triangle edge, whether it is convex or flat, and discard contact normals from flat edges (Bullet's "internal edge utility", Box2D's chain shapes with ghost vertices).
