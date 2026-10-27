# Unity

Notes specific to Unity: lifecycle, input, queries, and the places where Unity’s defaults differ from the textbook formula. Shared maths and graphics stay in their own sections and are linked from here.

Planned topics:

- `MonoBehaviour` lifecycle, script order, and what is safe in `Update` versus `LateUpdate`.
- The legacy Input Manager and the Input System, including projects that have both enabled.
- Physics queries: ray, sphere, and shape casts, layer masks, and triggers.
- Cameras. Written: [Third-person orbit camera](orbit-camera.md), as a plain script and as Cinemachine 3.
- Character mechanics. Written: the [controllers](mechanics/controllers/index.md) (CharacterController, Rigidbody, top-down, 2D platformer) and [interaction](mechanics/interaction.md).
- Shared systems. Written: [Health, damage, and stats](systems/health.md). Anything not written yet is on the [roadmap](../roadmap.md).
- Architecture. Written: [Event systems](architecture/events.md). Shared variables, state machines, and object pooling will join this group.
- Combat. Written: [Weapons](combat/weapons.md). Attack combos will join this group.
- Rendering. Written: [Highlight and outline](rendering/highlight-outline.md).
- Data and loading: `ScriptableObject`, addressables, and what belongs out of the scene.

The orbit camera is also the worked example for [exponential damping](../maths/interpolation.md#frame-rate-independent-damping).
