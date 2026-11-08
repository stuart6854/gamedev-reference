# Image-based lighting

Direct lights cover the sun and lamps. Everything else (the sky, light bouncing off walls, the environment seen in reflections) arrives from every direction. **Image-based lighting** (IBL) stores that light in a cubemap and lights surfaces from it. Without it, PBR materials look flat and metals look black.

## The problem

Lighting from an environment means integrating the [BRDF](brdf.md) against light from every direction of the hemisphere. That is far too expensive per pixel. The standard solution precomputes almost all of it:

- **Diffuse**: the integral only depends on the normal, so precompute it per direction: an **irradiance** map or spherical harmonics.
- **Specular**: the **split-sum approximation** (Karis, "Real Shading in Unreal Engine 4") splits it into a prefiltered environment map and a small lookup table.

## Diffuse irradiance

For a Lambert surface, the light arriving at a normal `n` is the environment integrated over the hemisphere around `n`, weighted by the cosine. It changes slowly with direction, so a very compact representation is enough: **second-order spherical harmonics**, 9 RGB coefficients for the whole environment.

```hlsl
// Evaluate L2 spherical harmonics irradiance (coefficients premultiplied by the cosine
// convolution and 1/π, as computed when projecting the environment).
float3 sh_irradiance(float3 n, float3 sh[9])
{
    return max(0.0,
          sh[0]
        + sh[1] * n.y + sh[2] * n.z + sh[3] * n.x
        + sh[4] * (n.x * n.y) + sh[5] * (n.y * n.z)
        + sh[6] * (3.0 * n.z * n.z - 1.0)
        + sh[7] * (n.x * n.z) + sh[8] * (n.x * n.x - n.y * n.y));
}
```

The coefficients are computed once per environment (or per light probe) by projecting the cubemap onto the SH basis. With the basis constants and the cosine convolution folded in at projection time, evaluating is the few multiply-adds above. Robin Green's "Spherical Harmonic Lighting: The Gritty Details" and Ramamoorthi and Hanrahan's "An Efficient Representation for Irradiance Environment Maps" give the constants. A small irradiance cubemap (32 × 32 per face) is the alternative, at the cost of a texture fetch.

## Specular: the split sum

The specular integral is approximated as the product of two separately precomputed parts:

```text
∫ L(l) f(l, v) cos θ dl  ≈  [ prefiltered environment(r, roughness) ]  ×  [ ∫ f(l, v) cos θ dl ]
```

### Prefiltered environment map

The first part is the environment blurred by the GGX lobe for a given roughness, sampled in the reflection direction. Store increasing roughness in the cubemap's **mip levels**:

```text
for mip in 0 .. mip_count - 1:
    roughness = mip / (mip_count - 1)
    for each texel direction n (assuming n = v = r):
        importance-sample the GGX lobe around n with that roughness
        weighted average of the environment over those samples -> texel
```

Mip 0 is the sharp environment for mirror-like surfaces; the last mip is a broad blur for fully rough ones. The assumption `n = v = r` loses the stretching of reflections at grazing angles, which is the main error of the approximation, and is accepted.

### The BRDF lookup table

The second part depends only on `NdotV` and roughness once `F0` is factored out, so it fits in a small 2D texture (for example 128 × 128, RG16F), computed once and shipped with the engine:

```text
for each (NdotV, roughness) texel:
    integrate the specular BRDF over the hemisphere with importance sampling, splitting Fresnel as
    F0 * A + B; store (A, B)
```

### Putting it together

```hlsl
TextureCube  prefiltered_env;      // GGX-filtered mips
Texture2D    brdf_lut;             // (A, B) per (NdotV, roughness)
SamplerState linear_clamp;

float3 ambient_lighting(float3 n, float3 v, Surface s, float3 sh[9], float ao)
{
    float NdotV = max(dot(n, v), 1e-4);
    float3 r = reflect(-v, n);
    float3 F0 = lerp(0.04.xxx, s.base_color, s.metallic);
    float3 diffuse_color = s.base_color * (1.0 - s.metallic);

    float  mip = s.roughness * (ENV_MIP_COUNT - 1);
    float3 prefiltered = prefiltered_env.SampleLevel(linear_clamp, r, mip).rgb;
    float2 ab = brdf_lut.SampleLevel(linear_clamp, float2(NdotV, s.roughness), 0).rg;

    float3 specular = prefiltered * (F0 * ab.x + ab.y);
    float3 diffuse  = diffuse_color * sh_irradiance(n, sh);

    return (diffuse + specular) * ao;          // see materials: occlusion applies to ambient only
}
```

The result is added to the sum of the direct lights.

- **Energy loss on rough surfaces**: a single-scattering BRDF loses energy at high roughness, so rough metals look darker than they should. Fdez-Agüera's multiple-scattering compensation uses the same lookup table to add it back (`1 + F0 × (1 / (A + B) − 1)` as a scale on specular), as Filament does.
- **Specular occlusion**: ambient occlusion alone does not stop reflections showing in crevices. Approximate specular occlusion from AO and roughness, or use screen-space reflections and probes to replace the environment where they have data.

## Reflection probes

One environment for the whole scene is wrong indoors: a room lit by a window should not reflect the sky. **Reflection probes** capture the environment from points in the level:

```text
Probe { position, influence volume (box or sphere), prefiltered cubemap, SH coefficients }

for each pixel:
    find the probes whose influence volumes contain it (from a clustered or tiled list)
    blend their contributions by distance to each volume's edge
```

- **Parallax correction**: a cubemap is captured from one point, so reflections are only right at that point. For box-shaped rooms, intersect the reflection ray with the probe's box and look up the cubemap in the direction from the probe's centre to the hit point. Reflections then line up with the walls.
- **Capture** probes offline (or when lighting changes), with the scene's own lighting, and store them prefiltered. Real-time probes re-render cubemaps at run time for changing time of day, spread over several frames.
- **Light probes** for diffuse are separate and much denser: SH coefficients on a grid or tetrahedral mesh through the level, interpolated per object or per pixel, so moving objects pick up bounced light from their surroundings.

## Where the environment comes from

- An **HDR sky**: an equirectangular `.hdr` or `.exr` image converted to a cubemap, or a procedural sky rendered into one (and re-rendered as the sun moves).
- **Units** must match the direct lights. A sky of value 1 next to a sun of 100,000 lux looks black. Keep everything in physical units, or at least in consistent relative ones; see [physical light units](colour.md#physical-light-units).
