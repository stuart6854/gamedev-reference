# Physically based rendering

Shading that follows how light actually reflects off surfaces, so that materials look right under any lighting, and artists author properties of the surface ("rough painted metal"), not a look for one scene. Shaders are HLSL.

- [BRDF](brdf.md) — the Cook–Torrance specular model with GGX, Smith, and Schlick, Lambert diffuse, and putting them together for one light.
- [Materials](materials.md) — the metal/roughness workflow, texture channels and packing, normal maps, and the authoring rules that keep materials plausible.
- [Image-based lighting](ibl.md) — lighting from the environment: the split-sum approximation, prefiltered cubemaps, the BRDF lookup table, irradiance, and reflection probes.
- [Colour pipeline](colour.md) — linear and sRGB, HDR render targets, physical light units, exposure, and tone mapping.

The [shadow mapping](../shadows/index.md) pages cover which lights reach a surface; these pages cover what happens when they do. Brian Karis's "Real Shading in Unreal Engine 4" (SIGGRAPH 2013) and Google's [Filament documentation](https://google.github.io/filament/Filament.html) are the two standard references, and these pages follow them.
