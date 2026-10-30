# Rendering

Materials, renderer features, and full-screen passes. Character controllers stay under [Mechanics](../mechanics/index.md). Shared numbers stay under [Systems](../systems/index.md).

Written:

- [Day and night cycle](day-night.md) — a game clock with dusk and dawn events, one light as sun and moon, curves for colour and intensity, gradient ambient, fog, and a procedural sky.
- [Highlight and outline](highlight-outline.md) — inverted hull, a stencil outline through Render Objects, a screen-space edge, and a fresnel highlight. Focus calls it from [interaction](../mechanics/interaction.md).
- [Post-processing](post-processing.md) — URP volumes and how they blend, the common effects, and driving them from gameplay by weight or by editing a profile.
- [Roof and wall cutaways](cutaways.md) — interior volumes that hide roofs while keeping their shadows, a dithered cutout circle around the player, and ray-faded occluders.
- [Fog of war and vision](vision.md) — grid shadowcasting with a view cone, explored memory, a fog texture read by a full-screen pass, and hiding units outside vision.

What is not written yet is on the [roadmap](../../roadmap.md). A topic comes off that list when its page exists.
