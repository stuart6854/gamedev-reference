---
uses:
  - name: Hordes and crowds
    text: Creating and destroying thousands of agents without fragmentation.
  - name: Life and colony sims
    text: Many small simulated things with ids that survive saves.
  - name: Multiplayer
    text: Command buffers that apply changes at a known point in the frame.
---

# Entities

An entity is a [handle](../../data-structures/handle-table.md): an index plus a generation, packed into one integer. The world needs to create ids, recycle them, and answer "is this id still alive" in \(O(1)\). It stores no value per entity, so the handle table shrinks to one array of ids and a free list.

## The id

```text
INDEX_BITS = 20                         // 1,048,576 live entities
GEN_BITS   = 12                         // 4,096 generations per index

Entity = (generation << INDEX_BITS) | index
NULL   = 0                              // index 0, generation 0
```

These are EnTT's defaults for a 32-bit id. Unity Entities uses two 32-bit fields, `Index` and `Version`. Pick the split by what runs out first, as on the [handle table](../../data-structures/handle-table.md#packing-the-handle) page.

Generations start at 1, so a zeroed id is never alive. Then a default component field that holds an entity is a null reference, not entity 0.

## The free list in the id array

The world keeps one array, `entities`, with one slot per index ever used. A live slot holds the entity's own id. A free slot holds the index of the next free slot, in the index bits, and the generation the slot will have when reused, in the generation bits. The free list costs nothing beyond the array.

```text
entities[]                              // one id per index ever used
free_head = NONE                        // index of the first free slot

create():
    if free_head == NONE:
        i = entities.size
        e = make(i, generation = 1)
        entities.push(e)
        return e
    i = free_head
    free_head = index_of(entities[i])   // the next free slot
    e = make(i, generation_of(entities[i]))
    entities[i] = e
    return e

alive(e):
    i = index_of(e)
    return i < entities.size and entities[i] == e

destroy(e):
    if not alive(e): return
    remove every component of e         // below
    i = index_of(e)
    next_gen = generation_of(e) + 1     // on wrap, skip 0; see the handle table page
    entities[i] = make(free_head, next_gen)
    free_head = i
```

`alive` is one comparison. A stale id fails it because the slot holds a later generation. A free slot fails it because its index bits hold the next free index or `NONE`, never `i` itself. Make `NONE` a value no real index takes, such as all index bits set, and never hand that index out.

The wrap rules from the [handle table](../../data-structures/handle-table.md#generation-wrap) apply unchanged. A game that spawns and kills one bullet a frame on a LIFO free list reuses one index every frame.

## Destroying an entity

The world must remove every component the entity has, without knowing which ones it has. How depends on storage:

- **Sparse sets:** ask every component pool `remove(e)`. Each pool answers in \(O(1)\), so the cost is the number of component types, often a few hundred. A per-entity bitmask of component types lets you skip pools that cannot contain it.
- **Archetypes:** the entity's record says which table it is in. Remove its row from that table. One operation, whatever its components.

Then free the id, as above.

## Component masks

A sparse-set world can keep a bitset per entity, one bit per component type, set when a component is added. It answers "does this entity have A and B" with one AND of two masks, and it lists which pools to visit on destroy. It costs one bitset per entity and must be updated on every add and remove. An archetype world does not need it: the entity's table is the mask.

## Deferred commands

Creating or destroying an entity, or adding or removing a component, changes storage. In both models that moves components in memory, so it must not happen while a system is iterating the same storage. The standard fix is a command buffer:

```text
commands = []

during a system:
    commands.push(Destroy(e))
    commands.push(Add(e, Burning { seconds = 3 }))

at a sync point, between systems:
    for c in commands: apply c
    commands.clear()
```

A command that creates an entity cannot return the real id, because the id is only allocated when the buffer plays back. Return a placeholder, and map placeholders to real ids during playback. Unity's `EntityCommandBuffer` does this, and it is also how jobs on other threads record changes.

Playback order matters. Two commands for the same entity run in the order they were recorded, and commands for an entity that a previous command destroyed must be skipped, so check `alive(e)` as each one is applied.

## Language tips

=== "C++"

    - Make `Entity` a distinct type, such as `enum class Entity : std::uint32_t {}`. A plain `std::uint32_t` converts silently to and from every other integer.
    - Reserve the `entities` vector at the expected count. A reallocation copies only integers, but it is still a spike on the frame that crosses the limit.
    - For the command buffer, record into a per-thread byte buffer of `{type tag, entity, component bytes}` rather than a vector of `std::function`, which allocates per command.

=== "C#"

    - Make `Entity` a `readonly struct` with one `uint` field, implementing `IEquatable<Entity>`. `default(Entity)` is then the null entity.
    - Commands as a `List<object>` box every struct. Use one list per command kind, such as `List<Entity>` for destroys, or a byte buffer with `MemoryMarshal`-based writes for component data.
    - In Unity, `EntityManager.Exists(entity)` is `alive`, and a structural change made directly on the `EntityManager` inside a `foreach` over a query throws. That is the iteration rule above, enforced. Use an `EntityCommandBuffer`.

!!! warning "Common pitfalls"

    Holding an entity id is safe. Holding a pointer or reference to one of its components across a structural change is not: adding a component anywhere can move it.

    A component that stores another entity, such as a target, must check `alive` before using it. The target may have been destroyed, and its index reused.

    A zeroed id that can be alive makes every unassigned entity field point at a real entity. Start generations at 1, and skip 0 when a generation wraps.

    A destroyed entity's commands still in a buffer must be skipped at playback, not applied to whatever reused the index.
