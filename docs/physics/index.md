# Physics

Notes on simulation as it is written in gameplay code: integrators, queries, and character movement. Not a rigid-body textbook.

Planned topics:

- Explicit Euler, semi-implicit Euler, and when a Verlet step is the one you actually want. Written: [Integrators](integrators.md).
- Fixed timesteps, the accumulator, and what is allowed to read the interpolated render pose. Written: [Fixed timestep and the accumulator](fixed-timestep.md).
- How a rigid-body engine finds and resolves contacts. Written: [Broadphase](broadphase.md) (fat AABBs, sweep and prune, dynamic AABB trees, pairs and triggers), [Narrowphase](narrowphase.md) (shape dispatch, SAT, GJK, EPA, manifolds, meshes), [Solver](solver.md) (sequential impulses, clamping, bias, restitution, friction, warm starting, joints), and [Islands, sleeping, and CCD](islands-ccd.md).
- Character controllers: sliding along a plane, step offset, and ground snapping.

Frame-rate-independent approaches that are just an exponential decay — camera lag, stickiness, a simple spring toward a goal — are under [interpolation and easing](../maths/interpolation.md#frame-rate-independent-damping). A physics page can send you there instead of re-deriving it.
