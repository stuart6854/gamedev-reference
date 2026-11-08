# Cascades

A directional light (the sun) shadows everything in view, from the player's feet to the horizon. One shadow map covering all of that gives each texel metres of ground: blocky shadows near the camera, where detail is needed most. **Cascaded shadow maps** (CSM) split the view into ranges by distance, and give each range its own shadow map: small and sharp near the camera, large and coarse far away.

## Split distances

```text
splits(near, far, count, lambda):
    for i in 1 .. count:
        p = i / count
        log_split     = near * (far / near) ^ p
        uniform_split = near + (far - near) * p
        split[i] = lerp(uniform_split, log_split, lambda)        // lambda ≈ 0.5 to 0.9
```

- **Logarithmic** splits match how perspective shrinks detail with distance, but give the first cascade a tiny range. **Uniform** splits waste resolution far away. The **practical split scheme** (Zhang et al.) blends the two with `lambda`.
- Use the **shadow distance**, not the camera's far plane, as `far`. Shadows beyond 100 to 200 m are rarely worth their cost; fade them out at the end of the last cascade.
- Typical setups: 4 cascades at 2048² each on high settings; 2 to 3 at 1024² on low.

## Fitting each cascade

For each split range, compute the part of the camera frustum between the two split distances, and fit the light's orthographic projection around it:

```text
fit_cascade(slice_corners[8], light_dir):
    // Fit a sphere: its size does not change as the camera rotates, which keeps the cascade stable.
    centre = average of slice_corners
    radius = max distance from centre to a corner, rounded up
    texel_size = 2 * radius / shadow_map_resolution

    light_view = look_at(centre - light_dir * radius, centre, up)
    // Snap the centre to whole texels in light space, so shadows do not shimmer as the camera moves.
    centre_ls = mul(light_view, centre)
    centre_ls.xy = floor(centre_ls.xy / texel_size) * texel_size
    projection = orthographic(centre_ls.x - radius, centre_ls.x + radius,
                              centre_ls.y - radius, centre_ls.y + radius,
                              near = -caster_extent, far = radius * 2)
```

- **Shimmering**: if the cascade's size or position changes by a fraction of a texel as the camera moves, every shadow edge is rasterised differently each frame, and edges crawl. Fitting a **sphere** (fixed size under rotation) and **snapping** to texel increments (fixed alignment under translation) removes it. A tight box fit uses resolution better, but shimmers.
- **Casters outside the slice** still cast shadows into it (a tall building behind the camera). Pull the near plane back towards the light far enough to include them, or use **depth clamping** (pancaking) in the shadow pass so casters in front of the near plane are flattened onto it instead of clipped.
- Each cascade has its own [culling](../../engine/rendering/renderer.md#visibility) of casters against its own box. Objects fully inside a nearer cascade can be skipped in farther ones when only the receiver's nearest cascade is sampled.

## Selecting a cascade

```hlsl
uint select_cascade(float view_depth)
{
    uint c = 0;
    [unroll] for (uint i = 0; i < CASCADE_COUNT - 1; i++)
        c += view_depth > cascade_split[i] ? 1 : 0;
    return c;
}
```

Selecting by **view depth** is simple. Selecting the first cascade whose box contains the point (testing its light-space position against each cascade's bounds) uses the sharper cascades for more of the screen, because the boxes are bigger than their slices.

Store all cascades in one **texture array** (or an atlas), so one sampler and one descriptor cover them, and pass the matrices and splits in a constant buffer.

## Blending between cascades

At the boundary between two cascades, the resolution changes suddenly and the seam is visible. Blend across a band near the end of each cascade:

```hlsl
float shadow = sample_cascade(c, world_pos);
float band_start = cascade_split[c] * (1.0 - BLEND_FRACTION);        // e.g. the last 10 %
if (c + 1 < CASCADE_COUNT && view_depth > band_start)
{
    float t = (view_depth - band_start) / (cascade_split[c] - band_start);
    shadow = lerp(shadow, sample_cascade(c + 1, world_pos), t);
}
```

Blending costs a second set of samples in the band. A cheaper alternative is **dithering**: in the band, choose the next cascade for a random fraction of pixels, and let TAA smooth the result.

## Cost

Cascades are often the most expensive shadow pass: four depth renders of most of the visible scene. Ways to spend less:

- **Update far cascades less often**: the last cascade every second or fourth frame, staggered so a different cascade updates each frame. Distant shadows lagging slightly is rarely visible.
- **Cache static geometry**: render static casters into a cached map once (while the sun does not move), and only render dynamic casters each frame, compositing the two.
- **Lower resolution or fewer cascades** at lower quality settings, and a shorter shadow distance.
- **Cull small casters** per cascade: a cup that covers less than a texel in the far cascade need not be drawn there.

For very large worlds, **virtual shadow maps** (as in Unreal Engine 5) use one huge sparse shadow texture, and only render and cache the pages that visible pixels need. They replace cascades but need a significant amount of engine infrastructure.
