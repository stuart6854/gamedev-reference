# Handle table

A table that hands out small handles instead of pointers, and can tell when a handle is stale. A handle is a slot index plus a generation. Removing an object bumps its slot's generation, so every old handle to that slot stops matching, even after the slot is reused. Also called a slot map, or generational index.

Entities, textures, sounds, UI widgets, and anything else that several systems refer to and one system destroys are the usual users.

## Why not a pointer or a plain index

| Reference | After the object is destroyed | After its memory or slot is reused |
| --- | --- | --- |
| Pointer | Dangles. Reading it is undefined behaviour in C++. | Silently points at the new object. |
| Plain index | Points at an empty slot, if you check. | Silently points at the new object. |
| Handle (index + generation) | Generation no longer matches. Lookup returns nothing. | Generation still does not match. Lookup returns nothing. |

The handle also survives the table's storage growing and moving, which a pointer does not, and it is small and copyable, so it can be saved or sent over a network as plain data.

## Layout

```text
Handle { index, generation }

Slot {
    generation
    alive
    value          // valid only while alive
    next_free      // valid only while not alive
}

slots[]            // grows, never shrinks
free_head = NONE   // first free slot, or NONE
```

Free slots form a linked list threaded through `next_free`, so finding one is \(O(1)\) and costs no extra memory.

Generations start at 1. A zero-initialised handle, `{0, 0}`, then never matches a slot, and can be the null handle. In C# that makes `default(Handle)` null for free.

## Operations

```text
insert(value):
    if free_head != NONE:
        i = free_head
        free_head = slots[i].next_free
    else:
        i = slots.size
        slots.push(Slot { generation = 1 })
    slots[i].value = value
    slots[i].alive = true
    return Handle { i, slots[i].generation }

valid(h):
    return h.index < slots.size
       and slots[h.index].alive
       and slots[h.index].generation == h.generation

get(h):
    if not valid(h): return null
    return reference to slots[h.index].value

remove(h):
    if not valid(h): return false
    s = slots[h.index]
    destroy s.value
    s.alive = false
    s.generation += 1                  // every handle to this slot is now stale
    s.next_free = free_head
    free_head = h.index
    return true
```

Bump the generation on remove, not on insert. Then a handle to a removed slot fails as soon as the slot is freed, before anything reuses it, and `valid` needs the `alive` check only to reject a forged handle with the current generation.

## Packing the handle

A 32-bit handle is enough for most tables. Pack it with shifts, not bitfields, so the layout is the same on every compiler:

```text
INDEX_BITS = 20                         // 1,048,576 slots
GEN_BITS   = 12                         // 4,096 generations per slot
INDEX_MASK = (1 << INDEX_BITS) - 1

pack(index, generation) = (generation << INDEX_BITS) | index
index_of(h)             = h & INDEX_MASK
generation_of(h)        = h >> INDEX_BITS
```

Split the bits by what runs out first. A table of 50,000 particles that churn every frame wants more generation bits. A table of a million static props wants more index bits. When neither fits, use 64 bits, 32 and 32.

## Generation wrap

A slot's generation has \(2^{g}\) values. After the slot has been reused \(2^{g}\) times, a handle from the first use matches again. With 12 bits, that is 4,096 reuses.

A free list that is LIFO, as above, makes this worse: the slot freed last is the one reused first, so a single churning object burns through one slot's generations as fast as it is spawned. Three fixes, cheapest first:

1. **Reuse the oldest free slot.** Keep a tail as well as a head, push freed slots on the tail, and pop from the head. Reuse then spreads across every free slot.
2. **Hold a minimum free count.** Do not reuse a slot until at least, say, 1,024 are free; allocate a new one instead. A slot then comes back only after a thousand others have been freed. This is what Bitsquid-style entity managers did.
3. **Retire a slot at the last generation.** When `generation` would wrap, do not push the slot on the free list. It is never reused. The table leaks one slot per \(2^{g}\) reuses of it, which is nothing.

Use 1 or 2 for speed of wrap, and 3 to make wrap impossible.

```text
remove(h):                              // with retirement
    ...
    if s.generation == MAX_GENERATION:
        return true                     // never freed, never reused
    s.generation += 1
    push h.index on the free list
```

## Dense variant

The table above iterates over every slot, live or free. When the hot path is "update every object", keep the values packed instead, with the slots pointing into them. This is the [sparse set](sparse-set.md) layout, with the slots as `sparse`:

```text
Slot { generation, dense_index_or_next_free, alive }

values[0..count)    // packed
owner[0..count)     // owner[d] is the slot index whose value is values[d]

insert(value):
    take slot i from the free list, or push a new one
    slots[i].dense_index = count
    values[count] = value
    owner[count]  = i
    count += 1
    return Handle { i, slots[i].generation }

get(h):
    if not valid(h): return null
    return reference to values[slots[h.index].dense_index]

remove(h):
    if not valid(h): return false
    d    = slots[h.index].dense_index
    last = count - 1
    values[d] = values[last]            // move the last value into the hole
    owner[d]  = owner[last]
    slots[owner[d]].dense_index = d
    count -= 1
    free slot h.index as before         // alive = false, generation += 1, push on free list
    return true
```

Iterate `values[0..count)`. Removing while iterating has the same rule as the sparse set: walk backwards.

The cost is one extra indirection on every `get`, and a value moves on every remove. A pointer to a value is invalid after any remove, not only the one that removed it.

## Typed handles

A bare integer handle to a texture can be passed to the mesh table, and nothing complains. Give each table its own handle type, with the same layout:

```text
Handle<Texture>, Handle<Mesh>    // same bits, different types
```

The compiler then rejects a texture handle where a mesh handle was expected. It costs nothing at runtime.

## Language tips

=== "C++"

    - Pack into a `std::uint32_t` with shifts, as above. Bitfield layout and order are implementation-defined, which matters as soon as a handle is saved or sent.
    - Make handles typed with a tag: `template <class T> struct Handle { std::uint32_t bits = 0; };`. Give it `operator==` and a `std::hash` specialisation over `bits`.
    - Store the value as `std::optional<T>` in the slot, so `destroy` is `value.reset()` and a free slot runs no destructor twice. For trivially destructible `T`, a plain `T` is enough.
    - `get` returns `T*`. That pointer is invalid after any `insert` that grows `slots`, and, for the dense variant, after any `remove`. Store the handle and call `get` again each time.
    - To keep pointers stable, allocate `slots` in fixed-size chunks that never move, rather than as one `std::vector`.

=== "C#"

    - Make the handle a `readonly struct Handle : IEquatable<Handle>`, with `Equals` and `GetHashCode` over the packed bits. Without `IEquatable<T>`, a `Dictionary<Handle, ...>` boxes on every lookup.
    - A typed handle is a generic struct, `readonly struct Handle<T>`, with the same single field. `T` is only a tag and is never stored.
    - With generations starting at 1, `default(Handle)` is the null handle, and fields and arrays of handles are null until assigned.
    - Return values with `ref`: `public ref T Get(Handle h)`. A `ref` cannot be null, so `Get` must throw on a stale handle. Pair it with `bool TryGet(Handle h, out T value)` for callers that expect one.
    - In Unity, `Unity.Entities.Entity` is this design: an `Index` and a `Version`, with `Entity.Null` as `{0, 0}`. Read it as a handle table that DOTS keeps for you.

!!! warning "Common pitfalls"

    Generation 0 used as a live generation makes a zeroed handle valid. Start generations at 1, and keep 0 for null.

    A LIFO free list with few generation bits wraps fast. One enemy spawned and killed every frame wraps a 12-bit slot in 68 seconds at 60 frames per second. Reuse the oldest slot, hold a minimum free count, or retire saturated slots.

    A pointer from `get` is not a handle. Holding it across a frame brings back the dangling pointer the table exists to remove.

    Destroying an object while another system walks the table invalidates indices that walk holds, in the dense variant. Queue removals and apply them at one point in the frame.

    The table is not thread-safe. Two threads inserting at once can take the same free slot.
