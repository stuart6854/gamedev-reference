# Maths

Notes on the mathematics that shows up directly in gameplay and rendering code. The aim is a formula you can check, plus the way it usually goes wrong in an engine, rather than a course.

Planned topics:

- Vectors, bases, and change of basis.
- Matrices and transforms. Quaternions are written: [Quaternions and rotations](quaternions.md).
- Interpolation, easing, and frame-rate-independent damping. The first of these is written: [Interpolation and easing](interpolation.md).
- Projections and the relationship between a field of view and a focal length. The pipeline itself lives under [coordinate spaces](../graphics/coordinate-spaces.md).
- Curves used for animation and cameras: smoothstep, Bézier, and Catmull–Rom.
- Random numbers, distributions, and noise.

Related notes will cross-link here when a gameplay or physics page depends on one of these results. The orbit camera already uses the damping step from the interpolation page.
