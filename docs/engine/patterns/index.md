# Engine patterns

Patterns that hold an engine together, above the level of any one system. Each page is pseudocode, with C++ where the language is the point.

- [The frame](frame.md) — the game loop, update phases, clocks, double-buffered state for a render thread, deferred commands, and per-frame allocators.
- [Subsystems and messaging](subsystems.md) — creating and shutting down subsystems in order, passing dependencies, and events dispatched immediately or queued.
- [Resources and handles](resources.md) — asset ids and runtime handles, load states, reference counting, asynchronous loading, caches, and hot reload.
- [Modules and plugins](modules.md) — module interfaces, dependency order, static and dynamic plugins, reloading code, and keeping the editor out of the game.

They build on the [handle table](../../data-structures/handle-table.md), [free list](../../data-structures/free-list.md), and [fixed timestep](../../physics/fixed-timestep.md) pages.
