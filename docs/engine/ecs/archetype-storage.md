---
uses:
  - name: Hordes and crowds
    text: Systems that read position and velocity of every agent in tight loops.
  - name: Open worlds
    text: Large simulations where most entities keep the same components.
---

# Archetype storage

Entities with exactly the same set of component types share a table. The set is the archetype. Each table has one column per component type, and one row per entity, so every column lines up: row `r` of the position column and row `r` of the velocity column belong to the same entity. A system that reads several components walks several arrays side by side, with no lookups. Unity Entities, flecs, and Bevy's default storage work this way.

The cost moves to structural changes. Adding or removing a component changes the entity's archetype, so its whole row moves to another table.

## Layout

```text
Archetype {
    types                               // sorted set of component type ids
    entities[]                          // entity id per row
    columns[]                           // one packed array per type in `types`
    column_of[type] -> column index     // for get
    edges_add[type]    -> Archetype     // cached transitions, below
    edges_remove[type] -> Archetype
}

Record { archetype, row }

World {
    entities, free_head                 // from the entities page
    records[]                           // records[index_of(e)] for every live entity
    archetypes: map from types -> Archetype
}
```

A new entity with no components goes in the empty archetype, whose `types` is the empty set.

The record makes `get` two array reads and a column lookup:

```text
get(e, T):
    r = records[index_of(e)]
    c = r.archetype.column_of[T]        // missing means e has no T
    return r.archetype.columns[c][r.row]
```

## Removing a row

Every table is packed. Removing row `r` moves the last row into it, in every column, and fixes the moved entity's record:

```text
remove_row(arch, r):
    last = arch.entities.size - 1
    moved = arch.entities[last]
    for each column: column[r] = column[last]; pop column
    arch.entities[r] = moved; pop arch.entities
    if r != last:
        records[index_of(moved)].row = r
```

This is also how an entity is destroyed: remove its row, then free its id. One operation, however many components it had.

## Adding and removing a component

```text
add(e, value: T):
    r   = records[index_of(e)]
    src = r.archetype
    dst = src.edges_add[T]
    if dst is missing:
        dst = archetype_for(src.types + T)
        src.edges_add[T] = dst
        dst.edges_remove[T] = src

    row = dst.entities.size
    dst.entities.push(e)
    for each type U in src.types:
        dst.columns[dst.column_of[U]].push(move src.columns[src.column_of[U]][r.row])
    dst.columns[dst.column_of[T]].push(value)

    remove_row(src, r.row)              // the values were moved out above
    records[index_of(e)] = { dst, row }
```

`remove(e, T)` is the mirror: follow `edges_remove[T]`, move every column except `T`, destroy the `T` value, and remove the old row.

`archetype_for` hashes the sorted type set and looks it up, creating the archetype if it is new. The edges make the second and later moves along the same path skip that hash, which is most of them: entities tend to gain and lose components in the same patterns. Flecs calls this the archetype graph.

Order the operations as above. The values are moved into the new row before `remove_row`, because `remove_row` overwrites the old row with the source table's last row. `remove_row` fixes the record of the entity it moved; the entity's own record is written after it.

## Queries

A query asks for archetypes whose types include everything required and nothing excluded:

```text
matches(arch, with, without):
    return with is a subset of arch.types and without does not intersect arch.types

run(query):
    for arch in query.cached_matches:
        if arch.entities.size == 0: continue
        P = arch.columns[arch.column_of[Position]]
        V = arch.columns[arch.column_of[Velocity]]
        for row in 0 .. arch.entities.size:
            P[row] += V[row] * dt
```

Archetypes are created rarely and queried every frame, so each query keeps its list of matching archetypes. When a new archetype is created, test it against every query once and append it where it matches. Running a query then never looks at an archetype that cannot match.

Inside one archetype, the loop is the tightest form there is: arrays of plain data in order, which compilers vectorise and prefetchers love.

## Chunks

A table that is one array per column must reallocate and copy whole columns as it grows. Unity Entities instead splits every archetype into fixed-size chunks of 16 KiB. Each chunk holds as many rows as fit, with the columns laid out back to back inside it:

```text
Chunk (16 KiB) {
    count
    entities[capacity]
    Position[capacity]
    Velocity[capacity]
    ...
}

capacity = (16 KiB - header) / (size of Entity + sum of component sizes)
```

Chunks give three things a single table does not:

- Growth allocates a new chunk. Nothing already stored moves.
- A chunk is a natural unit of work for a job thread.
- Each chunk can carry a version number per column, bumped when a system writes that column. A system can then skip every chunk whose data has not changed since it last ran. Unity calls this change filtering.

Unity also caps a chunk at 128 entities, whatever their size, so per-entity bits fit in fixed masks.

The cost is fragmentation. Every archetype takes at least one chunk, so 1,000 archetypes with 3 entities each use 1,000 chunks, almost all empty.

## Keeping structural changes rare

| Problem | Fix |
| --- | --- |
| A tag such as `Stunned` is added and removed every few frames, moving the entity each time. | Keep the component on the entity and toggle a bit instead. Unity's `IEnableableComponent` does this: queries skip disabled components, and nothing moves. |
| A component changes often and is read rarely. | Store just that type in a sparse set beside the tables. Bevy and flecs allow per-component storage choice. |
| Changes happen inside a system that is iterating. | Record them in a [command buffer](entities.md#deferred-commands) and apply them at a sync point. Moving rows mid-iteration corrupts the walk. |
| Many unique combinations create many tiny archetypes. | Merge rarely used optional data into one component, or move it to a sparse-set store. |

## Language tips

=== "C++"

    - A column is type-erased bytes. Store a small type record per component type, `{size, alignment, move, destroy}`, with function pointers. For trivially copyable types, `move` is `std::memcpy` and `destroy` is nothing.
    - `archetype_for` needs a hash of the sorted type ids. A `std::vector<std::uint32_t>` key in an `std::unordered_map` with a custom hash is enough, since lookups happen only on first transitions.
    - Iterate with raw pointers to each column's start, fetched once per archetype, so the inner loop is plain array indexing.

=== "C#"

    - Managed columns can be `T[]` behind a non-generic `abstract class Column` with `MoveRowTo(Column dst, int row)` and `RemoveRow(int row)` overrides. Generic code lives in `Column<T>`; the archetype only sees the base.
    - For unmanaged components, raw byte buffers with `Unsafe` reads avoid the virtual call per column per move. That is what Unity Entities does internally.
    - In Unity, a query's `ToComponentDataArray` copies. Iterate with `IJobChunk` or `SystemAPI.Query` to read the chunk arrays in place.

!!! warning "Common pitfalls"

    Adding or removing a component inside a query loop moves rows in the table being walked. Rows get skipped or visited twice. Use a command buffer.

    A reference to a component is invalid after any structural change to that archetype, including one on another entity: `remove_row` moves the last row into the gap.

    Toggling a tag component every frame turns a cheap flag into a full row copy per change. Use an enableable component or a sparse-set store.

    An archetype per rare combination wastes a chunk each. Watch the archetype count in the profiler or the debugger.
