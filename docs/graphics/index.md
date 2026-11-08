# Graphics

Notes on how a mesh becomes pixels, and on the shading and colour decisions that sit on top of that. Engine-specific API details stay in the Unity section unless the behaviour is really about the graphics pipeline.

Planned topics:

- Coordinate spaces and the transformation pipeline. Written: [Coordinate spaces](coordinate-spaces.md).
- Building meshes in code: planes, cubes, spheres, cylinders, cones, capsules, tori, discs, and rings. Written: [Primitive generation](primitives.md).
- How particle systems work: pools, emission, simulation, billboards, blending and sorting, and CPU against GPU. Written: [Particle systems](particles.md).
- Drawing an editor-style ground grid in a shader: anti-aliased lines, major lines and axes, fading, and changing spacing with zoom. Written: [Ground grid](grid.md).
- Distance and height fog, fog in custom shaders, and scattering colour. Written: [Fog](fog.md).
- Shading models, normal maps, colour, gamma, and tone mapping. Written: [Physically based rendering](pbr/index.md), with pages on the [BRDF](pbr/brdf.md), [materials](pbr/materials.md), [image-based lighting](pbr/ibl.md), and the [colour pipeline](pbr/colour.md).
- Shadow maps, bias, filtering, cascades, and local light shadows. Written: [Shadow mapping](shadows/index.md), with pages on [basics and bias](shadows/basics.md), [filtering](shadows/filtering.md), [cascades](shadows/cascades.md), and [local lights and atlases](shadows/local-lights.md).
- Post-processing as a sequence of buffers, not a stack of effects.

The coordinate-spaces page is the one the later shading notes will assume.
