# Physics

Notes on simulation as it is written in gameplay code: integrators, queries, and character movement. Not a rigid-body textbook.

Planned topics:

- Explicit Euler, semi-implicit Euler, and when a Verlet step is the one you actually want.
- Fixed timesteps, the accumulator, and what is allowed to read the interpolated render pose.
- Collision detection versus collision response, contact manifolds, and triggers.
- Character controllers: sliding along a plane, step offset, and ground snapping.
- Joints and constraints at the level of “what the solver is promising”.

Frame-rate-independent approaches that are just an exponential decay — camera lag, stickiness, a simple spring toward a goal — are under [interpolation and easing](../maths/interpolation.md#frame-rate-independent-damping). A physics page can send you there instead of re-deriving it.
