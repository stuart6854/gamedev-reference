# Local lights and atlases

Spot and point lights have limited range, and a scene can have dozens of them. Each shadow-casting light costs at least one depth pass, so the work is in choosing which lights get shadows, packing their maps together, and not re-rendering what has not changed.

## Spot lights

A spot light's shadow is a single **perspective** shadow map, with the cone's angle as the field of view and the light's range as the far plane. Sampling is the same as the [basic comparison](basics.md#the-comparison), with the perspective divide.

- The near plane matters for depth precision: set it as far out as possible (a few centimetres to tens of centimetres) rather than 0.001.
- Perspective depth is non-linear, so bias needs to vary with distance from the light. Normal offset scaled by the shadow texel's world size at that distance handles it better than a constant depth bias.

## Point lights

A point light shines in every direction, so its shadow covers a full sphere. Two layouts:

| Layout | How | Trade-off |
| --- | --- | --- |
| Cube map | Six 90° perspective views, one per face | Even resolution; six passes (or one pass with layered rendering) |
| Dual paraboloid | Two hemispheres, each a paraboloid projection | Two passes; distorts large triangles, which are drawn straight in a curved projection |

Cube maps are standard. For a point light, store and compare **linear distance** from the light rather than perspective depth: it is the same for all six faces, which makes filtering across face edges and biasing consistent.

```hlsl
TextureCube<float> point_shadow;                  // stores distance / range, written by the shadow pass

float point_shadow_factor(float3 world_pos, float3 light_pos, float range)
{
    float3 to_pixel = world_pos - light_pos;
    float dist = length(to_pixel) / range;
    return point_shadow.SampleCmpLevelZero(shadow_sampler, to_pixel, dist - bias);
}
```

Six faces cost six times a spot light. **Cull per face**: only draw casters into the faces whose frustum they touch, and skip faces that look away from everything visible to the camera.

## Shadow atlases

Rather than a separate texture per light, pack all local lights' shadow maps into one large **atlas** (for example 8192 × 8192), each light getting a rectangle (and a point light six):

```text
each frame:
    candidates = shadow-casting lights that affect visible pixels
    for light in candidates: importance = projected screen size of its range × light priority
    sort by importance
    assign tile sizes: largest tiles (1024²) to the most important, smaller (512², 256², 128²) down the list
    pack tiles into the atlas (a quadtree of power-of-two tiles makes this simple)
    lights that do not fit: no shadow this frame (or the smallest tile)
```

- One texture and one sampler for every local shadow, so the lighting shader handles all lights in one pass (with [clustered or tiled](../../engine/rendering/renderer.md) light lists) and indexes the atlas with each light's tile rectangle.
- **Resolution follows importance**: a light filling half the screen gets a large tile; one in the distance gets a small one.
- Clamp filter taps to the tile's rectangle, or leave a border of a few texels around each tile, so filtering does not sample a neighbouring light's map.
- Tile sizes should change rarely (with hysteresis on importance), or shadows visibly pop in resolution as the camera moves.

## Caching static shadows

Most local lights are static, and most of what they illuminate is static too. Re-rendering their shadow maps every frame is wasted work:

```text
per light:
    static_map: rendered once (and when static geometry in range changes or the light moves)
    each frame:
        if no dynamic casters are in range: use static_map directly
        else: copy static_map into the frame's tile, then render only dynamic casters on top
```

- Copying a depth texture is far cheaper than re-rendering everything in range.
- Track which dynamic objects intersect each light's range (from the broadphase or a light-object overlap test), so lights with nothing moving near them cost nothing.
- Cached maps take memory. Keep them for the most important or most expensive lights, and evict the least recently used.

## Budgets

Shadows are often the largest cost in a lit scene. Set budgets and enforce them:

- **Maximum shadowed lights per frame** (for example 8 spot-equivalents, counting a point light as six), chosen by importance as above. Lights beyond the budget render without shadows.
- **Fade shadows out with distance** from the camera, per light, so the switch to unshadowed is not visible.
- **Designer control**: a "casts shadows" flag per light, defaulting to off for small fill lights. Most lights in a well-lit scene do not need shadows.
- **Measure** the shadow passes as their own group in the [GPU profiler](../../engine/profiling.md#gpu-timing), and set a millisecond budget for them per platform.
