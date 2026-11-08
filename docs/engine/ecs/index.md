# Entity component system

How an ECS works underneath, written as the data structures it is built from. Using a particular library is not covered.

## The three parts

- An **entity** is an id and nothing else. It has no fields, no methods, and no list of components.
- A **component** is plain data attached to an entity: a position, a velocity, a health value. One entity has at most one component of each type.
- A **system** is a function that runs over every entity with a given set of components, such as "every entity with a position and a velocity".

The **world** owns all three: it hands out entity ids and stores the components. Everything interesting is in how it stores them, because a system's speed is the speed of walking that storage.

## Storage models

Two designs cover nearly every ECS library:

| | [Sparse-set storage](sparse-set-storage.md) | [Archetype storage](archetype-storage.md) |
| --- | --- | --- |
| Layout | One packed array per component type. | One table per combination of component types, with a column per type. |
| Add or remove a component | \(O(1)\). Touches one array. | Moves the entity's whole row to another table. |
| Iterate one component type | Packed. | Packed, a table at a time. |
| Iterate several component types | Walk the smallest array, look up the others. Packed only with groups. | Packed. Every column in a matching table lines up. |
| Many entity "shapes" | No cost. | One table per shape. Rare shapes give many small tables. |
| Examples | EnTT | Unity Entities (DOTS), flecs, Bevy (by default) |

Use sparse sets when components are added and removed often, such as status effects and tags that come and go every few frames. Use archetypes when the set of components on an entity rarely changes and systems iterate several components together, which is the common case in a large simulation.

## Pages

- [Entities](entities.md) — ids with a generation, a free list threaded through the id array, destroying an entity, and deferred commands.
- [Sparse-set storage](sparse-set-storage.md) — a pool per component type, type ids, views, and groups that make multi-component iteration packed.
- [Archetype storage](archetype-storage.md) — tables, entity records, moving an entity between tables, the archetype graph, cached queries, and chunks.

They build on the [sparse set](../../data-structures/sparse-set.md) and [handle table](../../data-structures/handle-table.md) pages.
