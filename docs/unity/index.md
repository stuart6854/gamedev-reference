# Unity

Notes specific to Unity: lifecycle, input, queries, and the places where Unity’s defaults differ from the textbook formula. Shared maths and graphics stay in their own sections and are linked from here.

Written, by group. Each group's index lists its pages:

- [Cameras](cameras/index.md) — third-person orbit, first-person, and top-down strategy cameras.
- [Mechanics](mechanics/index.md) — the four movement controllers and interaction.
- [Systems](systems/index.md) — health and stats, inventory, and building.
- [Architecture](architecture/index.md) — the MonoBehaviour lifecycle, bootstrapping and services, events, shared variables, state machines, and pooling.
- [AI](ai/index.md) — enemy behaviour on a `NavMeshAgent`.
- [Combat](combat/index.md) — weapons.
- [Rendering](rendering/index.md) — highlight and outline.

Planned, with no page yet:

- The legacy Input Manager and the Input System, including projects that have both enabled.
- Physics queries: ray, sphere, and shape casts, layer masks, and triggers.
- Data and loading: `ScriptableObject`, addressables, and what belongs out of the scene.

Smaller topics are on the [roadmap](../roadmap.md).

The orbit camera is also the worked example for [exponential damping](../maths/interpolation.md#frame-rate-independent-damping).
