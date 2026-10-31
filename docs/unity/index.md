# Unity

Notes specific to Unity: lifecycle, input, queries, and the places where Unity’s defaults differ from the textbook formula. Shared maths and graphics stay in their own sections and are linked from here.

Written, by group. Each group's index lists its pages:

- [Architecture](architecture/index.md) — the MonoBehaviour lifecycle, bootstrapping and services, scenes and loading, events, shared variables, state machines, pooling, and the command pattern.
- [Input](input/index.md) — rebinding controls at runtime, with duplicates, composites, and saved overrides.
- [Mechanics](mechanics/index.md) — the four movement controllers, interaction, drag selection, and formation movement.
- [Cameras](cameras/index.md) — first-person, third-person orbit, and top-down strategy cameras.
- [Combat](combat/index.md) — hit flash, damage numbers, weapons, and attack combos.
- [Animation](animation/index.md) — locomotion blend trees and layers, driving the Animator from code, events, root motion, IK and aiming, ragdolls, procedural legs, and crowd performance.
- [AI](ai/index.md) — enemy behaviour, perception, noise sources, steering and crowds, utility AI, waves and spawning, horde simulation, and navigation scenarios.
- [Systems](systems/index.md) — health and stats, inventory and containers, building, loot tables, timed actions, needs and effects, and saving.
- [UI](ui/index.md) — choosing between uGUI and UI Toolkit, and views that only show state and report requests.
- [Rendering](rendering/index.md) — a day and night cycle, highlight and outline, post-processing, particles, roof and wall cutaways, and fog of war.
- [Tools](tools/index.md) — editor tooling (inspectors, drawers, menus, windows, handles, validation) and a profiler walkthrough.

Planned, with no page yet:

- An overview of the legacy Input Manager and the Input System, including projects that have both enabled.
- Physics queries: ray, sphere, and shape casts, layer masks, and triggers.
- Data and loading: `ScriptableObject`, addressables, and what belongs out of the scene.

Smaller topics are on the [roadmap](../roadmap.md).

The orbit camera is also the worked example for [exponential damping](../maths/interpolation.md#frame-rate-independent-damping).
