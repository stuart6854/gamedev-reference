# Graphics

Notes on how a mesh becomes pixels, and on the shading and colour decisions that sit on top of that. Engine-specific API details stay in the Unity section unless the behaviour is really about the graphics pipeline.

Planned topics:

- Coordinate spaces and the transformation pipeline. Written: [Coordinate spaces](coordinate-spaces.md).
- Building meshes in code: planes, cubes, spheres, cylinders, cones, capsules, tori, discs, and rings. Written: [Primitive generation](primitives.md).
- Shading models, normal maps, and the difference between a light direction in world space and in tangent space.
- Colour, gamma, and tone mapping.
- Shadow maps and why the depth format dominates their quality.
- Post-processing as a sequence of buffers, not a stack of effects.

The coordinate-spaces page is the one the later shading notes will assume.
