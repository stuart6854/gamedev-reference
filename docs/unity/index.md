# Unity

Notes specific to Unity: lifecycle, input, queries, and the places where Unity’s defaults differ from the textbook formula. Shared maths and graphics stay in their own sections and are linked from here.

Written, by group. Each group's index lists its pages:

- [Architecture](architecture/index.md) — the MonoBehaviour lifecycle, bootstrapping and services, scenes and loading, events, shared variables, state machines, and pooling.
- [Mechanics](mechanics/index.md) — the four movement controllers, interaction, drag selection, and formation movement.
- [Cameras](cameras/index.md) — first-person, third-person orbit, and top-down strategy cameras.
- [Combat](combat/index.md) — hit flash, damage numbers, weapons, and attack combos.
- [AI](ai/index.md) — enemy behaviour, perception, steering and crowds, utility AI, waves and spawning, and horde simulation.
- [Systems](systems/index.md) — health and stats, inventory, building, and loot tables.
- [UI](ui/index.md) — choosing between uGUI and UI Toolkit, and views that only show state and report requests.
- [Rendering](rendering/index.md) — a day and night cycle, highlight and outline, post-processing, roof and wall cutaways, and fog of war.

Planned, with no page yet:

- The legacy Input Manager and the Input System, including projects that have both enabled.
- Physics queries: ray, sphere, and shape casts, layer masks, and triggers.
- Data and loading: `ScriptableObject`, addressables, and what belongs out of the scene.

Smaller topics are on the [roadmap](../roadmap.md).

The orbit camera is also the worked example for [exponential damping](../maths/interpolation.md#frame-rate-independent-damping).
