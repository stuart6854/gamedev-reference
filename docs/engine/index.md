# Engine architecture

Notes on how a game is structured once it is larger than a single scene of components. Unity-specific versions of these ideas stay in the Unity section.

Planned topics:

- The frame: input, simulation, animation, render submission, and which of those may stall.
- What an entity is, and how components are stored. Written: [Entity component system](ecs/index.md), with pages on [entities](ecs/entities.md), [sparse-set storage](ecs/sparse-set-storage.md), and [archetype storage](ecs/archetype-storage.md).
- How a retained-mode UI is built. Written: [UI](ui/index.md), with pages on the [widget tree](ui/widget-tree.md), [layout](ui/layout.md), [flexbox](ui/flexbox.md), [input and focus](ui/input.md), [common elements](ui/elements.md), [tabs, splits, and docking](ui/docking.md), [design and architecture](ui/architecture.md), and [style sheets](ui/stylesheets.md).
- Jobs, batches, and the layout consequences of writing them.
- Serialisation, content pipelines, and the difference between authoring data and runtime data.
- Tools that edit the same data the game reads.
