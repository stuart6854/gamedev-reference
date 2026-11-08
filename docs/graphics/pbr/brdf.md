# BRDF

A **BRDF** (bidirectional reflectance distribution function) says how much of the light arriving from one direction leaves towards another. Real-time PBR uses a sum of two parts: **specular** reflection from the surface itself, and **diffuse** light that entered the surface, scattered, and came back out.

## Vectors

```text
n   surface normal
v   direction to the viewer (camera)
l   direction to the light
h   half vector: normalize(v + l)
```

All are unit vectors pointing **away** from the surface, in the same space (world space is simplest). The dot products `NdotL`, `NdotV`, `NdotH`, and `VdotH` appear everywhere below; clamp them to be non-negative.

## Specular: Cook–Torrance

A rough surface is modelled as tiny flat mirrors (**microfacets**) pointing in different directions. Light reflects towards the viewer only off facets whose normal is `h`. The specular BRDF multiplies three factors:

\[
f_\text{spec} = \frac{D(h)\, G(l, v)\, F(v, h)}{4\,(n \cdot l)(n \cdot v)}
\]

- **D**, the normal distribution: how many facets point along `h`. Rough surfaces spread them out (wide, dim highlights); smooth ones concentrate them (small, bright highlights).
- **G**, geometric shadowing: facets that are hidden from the light or the viewer by other facets.
- **F**, Fresnel: how much light reflects rather than refracts, which rises sharply at grazing angles.

### D: GGX

```hlsl
// alpha = roughness * roughness (perceptual roughness squared; see materials)
float D_GGX(float NdotH, float alpha)
{
    float a2 = alpha * alpha;
    float d = NdotH * NdotH * (a2 - 1.0) + 1.0;
    return a2 / (PI * d * d);
}
```

GGX (also called Trowbridge–Reitz) has a long tail, so highlights fade out softly like real materials, rather than ending abruptly. It is the standard choice.

### G: Smith, as a visibility term

Combine `G` with the `4 (n·l)(n·v)` denominator into one **visibility** term, which is cheaper and avoids dividing by near-zero values:

```hlsl
// Height-correlated Smith GGX, returning G / (4 NdotL NdotV).
float V_SmithGGXCorrelated(float NdotV, float NdotL, float alpha)
{
    float a2 = alpha * alpha;
    float ggxV = NdotL * sqrt(NdotV * NdotV * (1.0 - a2) + a2);
    float ggxL = NdotV * sqrt(NdotL * NdotL * (1.0 - a2) + a2);
    return 0.5 / max(ggxV + ggxL, 1e-5);
}
```

This is Filament's formulation. Unreal 4's Schlick approximation of Smith (`k = (roughness + 1)² / 8`) is a little cheaper and slightly less accurate; either is fine.

### F: Schlick

```hlsl
float3 F_Schlick(float VdotH, float3 F0)
{
    return F0 + (1.0 - F0) * pow(1.0 - VdotH, 5.0);
}
```

`F0` is the reflectance looking straight at the surface: about 4 % (`0.04`) for most non-metals, and the coloured base colour for metals (see [materials](materials.md#metal-and-roughness)). At grazing angles every surface becomes a mirror, which is why a floor reflects strongly at a low angle and a lake looks like a mirror near the horizon.

## Diffuse

```hlsl
float3 Fd_Lambert(float3 diffuse_color)
{
    return diffuse_color / PI;
}
```

Lambert diffuse is constant in every direction. Dividing by π makes it conserve energy: a white surface reflects exactly the light it receives, not more. Disney's Burley diffuse adds roughness-dependent retro-reflection at a small cost; the difference is subtle, and many engines keep Lambert.

## One light

```hlsl
float3 shade(float3 n, float3 v, float3 l, float3 light_radiance, Surface s)
{
    float3 h = normalize(v + l);
    float NdotL = saturate(dot(n, l));
    float NdotV = max(dot(n, v), 1e-4);          // never exactly 0: it is in a denominator
    float NdotH = saturate(dot(n, h));
    float VdotH = saturate(dot(v, h));

    float alpha = s.roughness * s.roughness;
    float3 F0 = lerp(0.04.xxx, s.base_color, s.metallic);
    float3 diffuse_color = s.base_color * (1.0 - s.metallic);

    float  D = D_GGX(NdotH, alpha);
    float  V = V_SmithGGXCorrelated(NdotV, NdotL, alpha);
    float3 F = F_Schlick(VdotH, F0);

    float3 specular = D * V * F;
    float3 diffuse  = (1.0 - F) * Fd_Lambert(diffuse_color);    // light reflected at the surface does not enter it

    return (diffuse + specular) * light_radiance * NdotL;
}
```

- `light_radiance` is the light's colour times its intensity, times its attenuation and shadow at this point.
- The `NdotL` factor is the cosine falloff: light hitting a surface at an angle spreads over a larger area.
- Multiplying the diffuse by `1 − F` keeps the total at or below the incoming light. Some engines omit it for simplicity and accept slight extra brightness at grazing angles.
- The sum over lights is just the sum of `shade` for each light, plus the [ambient lighting](ibl.md).

### Light attenuation

```hlsl
// Point and spot lights: inverse square, windowed to reach zero at the light's range.
float distance_attenuation(float dist, float range)
{
    float inv_sq = 1.0 / max(dist * dist, 0.0001);
    float window = saturate(1.0 - pow(dist / range, 4.0));
    return inv_sq * window * window;
}
```

Physically, light falls off with the square of distance and never reaches zero. The window (from Karis's course notes) forces it to zero at the light's range, so lights can be culled, with little visible change inside the range.

## Rough highlights and aliasing

A very smooth surface (roughness near 0) with a detailed normal map produces tiny, bright highlights that flicker as the camera moves: the highlight is smaller than a pixel. Clamp roughness to a minimum (around 0.045 to 0.08), and use **specular anti-aliasing**: increase roughness where the normal varies quickly across a pixel, using the screen-space derivatives of the normal (Tokuyoshi and Kaplanyan's method, used in Filament and Unity HDRP).
