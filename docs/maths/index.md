# Maths

Notes on the mathematics that shows up directly in gameplay and rendering code. The aim is a formula you can check, plus the way it usually goes wrong in an engine, rather than a course.

Written:

- Vectors, bases, and change of basis.
- Matrices, transforms, and quaternions, including the difference between renormalising a lerp and using slerp.
- Interpolation, easing, and frame-rate-independent damping. The first of these is written: [Interpolation and easing](interpolation.md).
- Projections and the relationship between a field of view and a focal length. The pipeline itself lives under [coordinate spaces](../graphics/coordinate-spaces.md).
- Curves used for animation and cameras: smoothstep, Bézier, and Catmull–Rom.
- Random numbers and distributions. Written: [Random distributions and shuffles](random.md). Noise is still planned.
- [Vectors, dot and cross products](vectors.md) — facing and cone tests, projection, reflection, signed angles, the 2D perp dot, and change of basis.
- [Interpolation and easing](interpolation.md) — lerp, inverse lerp, remap, smoothstep, easing curves, and frame-rate-independent damping.

Planned:

- Matrices and transforms. The pipeline itself lives under [coordinate spaces](../graphics/coordinate-spaces.md).
- Projections and the relationship between a field of view and a focal length.
- Curves used for animation and cameras: Bézier and Catmull–Rom.

Smaller topics are on the [roadmap](../roadmap.md#maths).
