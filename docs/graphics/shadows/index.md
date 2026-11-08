# Shadow mapping

How real-time renderers decide which surfaces a light can see. Each shadow-casting light renders the scene's depth from its own point of view into a **shadow map**; a surface is lit if it is no farther from the light than the depth stored in the map. Shaders are HLSL.

- [Basics and bias](basics.md) — rendering the shadow map, the comparison, depth formats, shadow acne and peter-panning, and the biases that fix them.
- [Filtering](filtering.md) — hardware comparison sampling, PCF kernels, rotated Poisson disks, and contact-hardening soft shadows (PCSS).
- [Cascades](cascades.md) — cascaded shadow maps for the sun: split distances, fitting, stabilisation, selection, blending, and cost.
- [Local lights and atlases](local-lights.md) — spot and point light shadows, packing many into an atlas, caching static shadows, and budgets.

The [render graph](../../engine/rendering/render-graph.md) runs shadow passes as ordinary passes, and the [renderer](../../engine/rendering/renderer.md#views) treats each shadow map as another view.
