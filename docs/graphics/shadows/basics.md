# Basics and bias

A shadow map is a depth image rendered from the light. Each pixel of the main view is transformed into the light's view; if it is farther from the light than the depth stored at that point, something closer to the light blocks it, and it is in shadow.

## Rendering the shadow map

```text
shadow pass (one per shadow-casting light, or per cascade or face):
    view = the light's view (looking along the light's direction)
    projection = orthographic for directional lights, perspective for spot lights
    render casters with a depth-only pipeline into a depth texture (no colour target)
```

- Use a **depth-only** pipeline: vertex shader only, no pixel shader, unless alpha-tested geometry (leaves, fences) needs a pixel shader to `clip` transparent texels.
- Cull with the light's frustum, not the camera's. An object behind the camera can still cast a shadow into view.
- Store the result in a depth format the pass can sample later: `D32_FLOAT` for precision, or `D16_UNORM` to halve memory and bandwidth for small or local shadow maps.

## The comparison

```hlsl
float4x4 light_view_proj;              // world -> light clip space
Texture2D<float> shadow_map;
SamplerComparisonState shadow_sampler; // comparison sampler: LESS_EQUAL, linear filtering

float shadow_factor(float3 world_pos)
{
    float4 clip = mul(light_view_proj, float4(world_pos, 1.0));
    float3 ndc = clip.xyz / clip.w;
    float2 uv = ndc.xy * float2(0.5, -0.5) + 0.5;       // D3D: y flips between NDC and texture space
    if (any(uv < 0.0) || any(uv > 1.0)) return 1.0;     // outside the map: lit
    return shadow_map.SampleCmpLevelZero(shadow_sampler, uv, ndc.z);   // 1 = lit, 0 = shadowed
}
```

`SampleCmpLevelZero` compares the receiver's depth with the stored depth in hardware. With a linear filter, it compares against the four nearest texels and blends the four results, giving a 2 × 2 filtered edge for the price of one sample. See [filtering](filtering.md).

## Shadow acne

A surface that should be lit shows stripes or a moiré pattern of shadow: **shadow acne**. Each shadow map texel covers an area of the surface, and stores one depth for it. Across that area, the real surface is sometimes slightly in front of the stored depth and sometimes slightly behind, so it shadows itself.

The error grows with the angle between the surface and the light: a surface nearly parallel to the light's direction covers a long stretch of depth within one texel.

### Biases

| Bias | How | Fixes |
| --- | --- | --- |
| Constant depth bias | Subtract a small constant from the receiver's depth | Acne on surfaces facing the light |
| Slope-scaled depth bias | Add a bias proportional to the depth slope, when rendering the shadow map | Acne on surfaces at grazing angles |
| Normal offset | Move the sampling position along the surface normal, by about one shadow texel | Acne at all angles, with less light leaking than depth bias |

```cpp
// Slope-scaled bias is a rasteriser setting on the shadow pass's pipeline (D3D12 shown).
D3D12_RASTERIZER_DESC raster = {};
raster.DepthBias = 1000;                 // in units of the depth format's smallest step
raster.SlopeScaledDepthBias = 2.0f;
raster.DepthBiasClamp = 0.0f;
```

```hlsl
// Normal offset: sample from a point pushed out along the normal, scaled by the texel size.
float3 offset_pos = world_pos + normal * (normal_offset_scale * shadow_texel_world_size)
                              * saturate(1.0 - dot(normal, light_dir));
```

The usual combination is a small slope-scaled bias in the shadow pass plus normal offset when sampling. Expose the values per light, and tune them visually: there is no value that is right for every scene.

## Peter-panning

Too much bias pushes shadows away from their casters, so objects look like they float above the ground: **peter-panning**. Bias trades acne for detachment. Two tricks reduce the need for bias:

- **Render back faces** into the shadow map (cull front faces). The stored depth is then the far side of each closed object, so the lit front faces are well in front of it. This fails for open geometry (single planes, foliage cards), which needs normal culling.
- **Tight depth range**: fit the light's near and far planes tightly around the casters and receivers, so the depth precision is spent where it is used.

## Resolution and aliasing

Each shadow map texel covers some area in the world. Where that area is larger than a screen pixel, shadow edges are blocky (**perspective aliasing**), worst close to the camera, where the camera sees most detail. Where a texel covers a long stretch of a surface at a grazing angle, edges smear (**projective aliasing**).

- More resolution helps both, at a squared memory and fill cost: 4096 × 4096 at 32 bits is 64 MB.
- [Cascades](cascades.md) spend resolution where the camera needs it, for directional lights.
- [Filtering](filtering.md) hides blocky edges by softening them, which looks better than sharp aliased ones even when the light should cast hard shadows.

## Where shadows come from

- **Static** geometry (most of a level) only needs re-rendering into a shadow map when the light moves; see [caching](local-lights.md#caching-static-shadows).
- **Small, distant** objects contribute little and cost a lot. Cull casters whose projected size in the shadow map is below a few texels.
- **Contact shadows**: shadow maps miss the tiny shadows where objects touch the ground. A short screen-space ray march towards the light from each pixel, through the depth buffer, adds them cheaply.
