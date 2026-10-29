# Maths

Notes on the mathematics that shows up directly in gameplay and rendering code. The aim is a formula you can check, plus the way it usually goes wrong in an engine, rather than a course.

Written:

- [Vectors, dot and cross products](vectors.md) — facing and cone tests, projection, reflection, signed angles, the 2D perp dot, and change of basis.
- [Interpolation and easing](interpolation.md) — lerp, inverse lerp, remap, smoothstep, easing curves, and frame-rate-independent damping.
- [Quaternions and rotations](quaternions.md) — composition order, inverse and relative rotation, slerp versus nlerp, turning towards a target, building rotations, Euler-angle traps, and swing–twist.
- [Random distributions and shuffles](random.md) — seeded generators, unbiased ranges, weighted picks, Fisher–Yates, shuffle bags, non-uniform distributions, and pseudo-random distribution.
- [Intersection tests](intersections.md) — ray against plane, sphere, box, and triangle, overlap tests, and the separating axis test.
- [Frustum and visibility tests](frustum.md) — points on screen, frustum planes, bounds tests, culling, line of sight, and off-screen indicators.

Planned:

- Matrices and transforms. The pipeline itself lives under [coordinate spaces](../graphics/coordinate-spaces.md).
- Projections and the relationship between a field of view and a focal length.
- Curves used for animation and cameras: Bézier and Catmull–Rom.
- Noise.

Other topics are on the [roadmap](../roadmap.md).
