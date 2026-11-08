# Filtering

A single comparison per pixel gives hard, jagged shadow edges that crawl as the camera moves. **Percentage-closer filtering** (PCF) compares several nearby texels and averages the results, giving smooth edges. Note the order: compare first, then average. Averaging depths and comparing once does not work, because depth discontinuities at edges average to depths that belong to no surface.

## Hardware PCF

A comparison sampler with linear filtering does a 2 × 2 PCF in one instruction: it compares the four texels around the sample point and blends the four 0-or-1 results bilinearly.

```hlsl
SamplerComparisonState shadow_sampler;     // Filter = COMPARISON_MIN_MAG_LINEAR_MIP_POINT, ComparisonFunc = LESS_EQUAL
float lit = shadow_map.SampleCmpLevelZero(shadow_sampler, uv, depth);
```

That is the minimum. Larger kernels build on it.

## Larger kernels

```hlsl
// A 3 × 3 grid of hardware-filtered taps.
float pcf_grid(float2 uv, float depth, float2 texel)
{
    float sum = 0.0;
    [unroll] for (int y = -1; y <= 1; y++)
    [unroll] for (int x = -1; x <= 1; x++)
        sum += shadow_map.SampleCmpLevelZero(shadow_sampler, uv + float2(x, y) * texel, depth);
    return sum / 9.0;
}
```

- Each tap is itself a 2 × 2 bilinear comparison, so a 3 × 3 grid of taps covers a 4 × 4 texel area with smooth weights.
- A plain grid of taps shows its structure as banded edges at larger sizes. Optimised kernels place taps between texels with carefully chosen weights, to get a wide, smooth filter from few taps; most engines ship a variant of this.
- Bias needs to grow with the kernel size: taps farther from the pixel's own position are compared against depths of a different part of the surface. Use the [normal offset](basics.md#biases) scaled by the kernel radius, or a receiver-plane depth bias computed from the depth's screen-space derivatives.

## Poisson disks

Sample at points scattered evenly in a disk instead of on a grid, and rotate the pattern per pixel:

```hlsl
static const float2 POISSON[16] = { /* 16 points in the unit disk, precomputed */ };

float pcf_poisson(float2 uv, float depth, float radius_uv, float2 screen_pos)
{
    float angle = interleaved_gradient_noise(screen_pos) * 6.2831853;  // per-pixel rotation
    float2x2 rot = float2x2(cos(angle), -sin(angle), sin(angle), cos(angle));
    float sum = 0.0;
    [unroll] for (int i = 0; i < 16; i++)
        sum += shadow_map.SampleCmpLevelZero(shadow_sampler, uv + mul(rot, POISSON[i]) * radius_uv, depth);
    return sum / 16.0;
}

float interleaved_gradient_noise(float2 p)      // Jorge Jimenez's noise: cheap and well distributed
{
    return frac(52.9829189 * frac(dot(p, float2(0.06711056, 0.00583715))));
}
```

The per-pixel rotation turns the banding of a fixed pattern into fine noise. Temporal anti-aliasing then averages that noise over frames into a smooth penumbra, which is why rotated Poisson sampling pairs so well with TAA.

## Soft shadows: PCSS

Real shadows are sharp where an object touches the ground, and blur with distance from the caster: a pole's shadow is crisp at its base and soft at its tip. **Percentage-closer soft shadows** (PCSS, Fernando, 2005) estimate the penumbra size per pixel and choose the PCF radius from it:

```text
pcss(uv, receiver_depth):
    // 1. Blocker search: average depth of the texels that occlude this point, in a search region.
    search_radius = light_size * (receiver_depth - near) / receiver_depth
    blocker_sum = 0, blocker_count = 0
    for each sample in a Poisson disk of search_radius:
        d = shadow_map.Sample(point sampler, uv + offset)        // raw depth, not a comparison
        if d < receiver_depth: blocker_sum += d; blocker_count += 1
    if blocker_count == 0: return 1                               // nothing in the way: fully lit
    blocker = blocker_sum / blocker_count

    // 2. Penumbra width from similar triangles.
    penumbra = light_size * (receiver_depth - blocker) / blocker

    // 3. PCF with a radius proportional to the penumbra.
    return pcf_poisson(uv, receiver_depth, penumbra * scale)
```

- The formula assumes a perspective projection with depths in view space. For a directional light (orthographic), the penumbra is simply proportional to `receiver − blocker` distance.
- PCSS costs two sets of samples per pixel, and the search must be large enough for the widest penumbra, so it is used for the main light only, or only on high settings.
- Very wide penumbras need many samples to avoid noise. Clamp the maximum radius.

## Pre-filterable shadow maps

PCF must filter at sample time, so wide filters cost many samples. **Variance shadow maps** (VSM) and their variants (exponential VSM, moment shadow maps) store depth statistics that can be blurred ahead of time and mipmapped like a normal texture. One filtered sample then gives a soft shadow of any width. Their weakness is **light bleeding**: light leaks through where several occluders overlap. They suit wide, soft shadows (distant cascades, large area lights) better than crisp ones.

## Choosing

| Need | Use |
| --- | --- |
| Cheap, small local lights | Hardware 2 × 2 PCF, or a small grid |
| Main light, with TAA | Rotated Poisson PCF, 8 to 16 taps |
| Main light, contact hardening | PCSS, on high settings |
| Very soft, wide shadows | EVSM or moment shadow maps |

Filter radius should be in **world units** (converted to texels per cascade or light), so a shadow's softness does not change when it moves from one cascade to the next.
