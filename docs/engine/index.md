# Engine architecture

Notes on how a game is structured once it is larger than a single scene of components. Unity-specific versions of these ideas stay in the Unity section.

Planned topics:

- How an engine is held together: the frame, subsystems and messaging, resources and handles, and modules. Written: [Engine patterns](patterns/index.md), with pages on [the frame](patterns/frame.md), [subsystems and messaging](patterns/subsystems.md), [resources and handles](patterns/resources.md), and [modules and plugins](patterns/modules.md).
- What an entity is, and how components are stored. Written: [Entity component system](ecs/index.md), with pages on [entities](ecs/entities.md), [sparse-set storage](ecs/sparse-set-storage.md), and [archetype storage](ecs/archetype-storage.md).
- How a retained-mode UI is built. Written: [UI](ui/index.md), with pages on the [widget tree](ui/widget-tree.md), [layout](ui/layout.md), [flexbox](ui/flexbox.md), [input and focus](ui/input.md), [common elements](ui/elements.md), [tabs, splits, and docking](ui/docking.md), [design and architecture](ui/architecture.md), and [style sheets](ui/stylesheets.md).
- Jobs, batches, and the layout consequences of writing them.
- Serialisation, content pipelines, and the difference between authoring data and runtime data. Written: [Serialisation](serialisation/index.md), with pages on [reflection](serialisation/reflection.md), [formats](serialisation/formats.md), [versioning](serialisation/versioning.md), and [references and load-in-place](serialisation/references.md); and [Content pipeline](content/index.md), with pages on [import and cook](content/import-cook.md), [dependencies and incremental builds](content/incremental.md), [packaging](content/packaging.md), and the [editor workflow](content/editor-workflow.md).
- Testing game and engine code. Written: [Unit testing](testing/index.md), with pages on [C# testing](testing/csharp.md) and [C++ testing](testing/cpp.md).
