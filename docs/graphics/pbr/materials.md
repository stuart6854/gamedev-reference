# Materials

A PBR material describes the surface, not the lighting: what colour it is, whether it is metal, how rough, and its fine surface detail. Under a correct [BRDF](brdf.md), those few properties produce the right look under any light.

## Metal and roughness

| Property | Range | Meaning |
| --- | --- | --- |
| Base colour | sRGB colour | Diffuse colour for non-metals; specular reflectance colour (F0) for metals |
| Metallic | 0 or 1 (mostly) | 0 = dielectric (plastic, wood, stone, skin); 1 = metal |
| Roughness | 0 to 1 | Perceptual roughness: 0 is a mirror, 1 is fully rough. The BRDF uses `alpha = roughness²` |
| Normal | Tangent-space vector | Surface detail smaller than the geometry |
| Ambient occlusion | 0 to 1 | How much ambient light reaches crevices |
| Emissive | HDR colour | Light the surface gives off itself |

```hlsl
float3 F0            = lerp(0.04.xxx, base_color, metallic);     // dielectrics reflect ~4 %
float3 diffuse_color = base_color * (1.0 - metallic);            // metals have no diffuse
```

- **Dielectrics** reflect about 2 % to 5 % of light at normal incidence, uncoloured. Using a constant 0.04 is accurate enough for nearly everything; a separate "specular" or "reflectance" parameter adjusts it for gems and water if needed.
- **Metals** reflect 50 % to 100 %, tinted (gold reflects yellow), and have no diffuse at all. Their base colour is their reflectance.
- **Metallic** is physically either 0 or 1. Values in between are for transitions in a texture (the edge where paint chips off metal), not for "a bit metallic".
- Roughness is **perceptual** (squared before use), so that a linear slider feels evenly spaced to artists.

## Plausible values

PBR only looks right if materials are in physical ranges:

| Material | Base colour (sRGB) | Metallic |
| --- | --- | --- |
| Charcoal, darkest dielectrics | about 50 | 0 |
| Most dielectrics (stone, wood, plastic, skin) | 50 to 240 | 0 |
| Fresh snow, brightest dielectrics | about 240 | 0 |
| Iron | (196, 199, 199) | 1 |
| Gold | (255, 226, 155) | 1 |
| Aluminium, silver | (245, 246, 246), (252, 250, 245) | 1 |

- No dielectric base colour should be pure black or pure white: nothing real reflects 0 % or 100 % of light diffusely. Very dark albedo makes surfaces render as black holes; very bright albedo makes them glow under strong light.
- **No lighting in the albedo**: no baked shadows, highlights, or ambient occlusion. Lighting comes from the renderer; light painted into textures is doubled.
- A **validation view** in the editor that colours pixels outside these ranges (base colour too dark or too bright, metallic between 0.1 and 0.9 over large areas) catches most authoring mistakes. Unreal and Unity HDRP both have one.

## Textures and packing

| Texture | Format | Colour space | Channels |
| --- | --- | --- | --- |
| Base colour (+ opacity) | BC7 (or BC1) | **sRGB** | RGB (+ A) |
| Normal | BC5 | Linear | RG; Z reconstructed |
| "ORM" mask | BC7 or BC1 | Linear | R occlusion, G roughness, B metallic |
| Emissive | BC6H or BC7 | sRGB or HDR | RGB |

- Only colours are **sRGB**. Roughness, metallic, occlusion, and normals are data, stored **linear**. Sampling a roughness map through an sRGB view (or the reverse) silently changes every value. See the [colour pipeline](colour.md#linear-and-srgb).
- **Pack** the single-channel maps into one texture (occlusion, roughness, metallic in R, G, B is the glTF convention), so the shader makes one fetch instead of three.
- **Normal maps** store only X and Y in a two-channel format (BC5), with Z rebuilt: `z = sqrt(saturate(1 - dot(xy, xy)))`. Two channels at full precision beat three at lower precision.

## Normal maps

A tangent-space normal map stores, per texel, a normal relative to the surface: (0, 0, 1) is "the surface itself". The shader rotates it into world space with the vertex's tangent frame:

```hlsl
float3 sample_normal(Texture2D tex, SamplerState s, float2 uv, float3 N, float4 T)
{
    float2 xy = tex.Sample(s, uv).rg * 2.0 - 1.0;                 // 0..1 -> -1..1
    float3 tn = float3(xy, sqrt(saturate(1.0 - dot(xy, xy))));
    float3 B  = cross(N, T.xyz) * T.w;                             // w: handedness, for mirrored UVs
    return normalize(tn.x * T.xyz + tn.y * B + tn.z * N);
}
```

- The tangent's `w` holds the **handedness** (±1), so mirrored UVs (common on symmetric models) get the bitangent the right way round.
- Tangent frames must match the ones the normal map was baked with, or seams and lighting errors appear. Use **MikkTSpace** in the importer: it is what Blender, Substance, Unity, and Unreal use.
- Normal map conventions differ in the sign of green: **OpenGL** (Y+, used by Blender, Unity, glTF) and **DirectX** (Y−, used by Unreal). A map in the wrong convention looks lit from below. Pick one convention for the engine and convert on import.
- Mipmapping a normal map averages normals and shortens them, losing detail at a distance. Use the shortened length to increase roughness at lower mips (Toksvig's method, or the specular anti-aliasing on the [BRDF](brdf.md#rough-highlights-and-aliasing) page).

## Ambient occlusion

Baked occlusion in the texture darkens **ambient** lighting (the [image-based lighting](ibl.md)) in crevices. Do not apply it to direct lights, which already have shadows. Combine it with screen-space ambient occlusion by taking the minimum of the two, not the product, which darkens twice.

## Beyond the standard model

The metal/roughness model covers most surfaces. Common extensions, each an extra BRDF term or layer:

- **Clear coat**: a second, smooth specular layer on top (car paint, varnished wood, carbon fibre).
- **Sheen**: soft retro-reflection at grazing angles for cloth and velvet.
- **Subsurface scattering**: light travelling under the surface for skin, wax, and leaves.
- **Anisotropy**: stretched highlights for brushed metal and hair.

glTF 2.0's extensions (`KHR_materials_clearcoat`, `KHR_materials_sheen`, and others) and Filament's documentation describe each.
