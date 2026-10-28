# Sparse set

A set of small non-negative integer keys, such as entity ids, with constant-time add, remove, and membership test, and a packed array of the members to iterate. Values can ride along in a second packed array, which makes it a map. Most ECS libraries store each component type this way.

## When to use it

| Need | Sparse set | Hash set | Bitset | Sorted array |
| --- | --- | --- | --- | --- |
| Add, remove, contains | \(O(1)\), no hashing | \(O(1)\) average | \(O(1)\) | \(O(\log n)\) lookup, \(O(n)\) insert |
| Iterate the members | \(O(n)\), packed | Walks the buckets | \(O(\text{max key})\) | \(O(n)\), packed |
| Clear | \(O(1)\) | \(O(\text{buckets})\) | \(O(\text{max key})\) | \(O(1)\) |
| Memory | Proportional to the largest key | Proportional to \(n\) | 1 bit per possible key | Proportional to \(n\) |
| Keeps order | No | No | Key order | Key order |

Use it when keys are dense-ish integers you control, and iteration is the hot path. Use a hash map when keys are sparse over a huge range, such as 64-bit ids or strings.

## Layout

Two arrays and a count:

- `dense[0..count)` holds the members, packed, in no particular order.
- `sparse[key]` holds the index of `key` in `dense`.
- `values[0..count)`, optional, is parallel to `dense`: `values[i]` belongs to `dense[i]`.

The invariant is that the two arrays point at each other for every member:

\[
\texttt{dense}[\texttt{sparse}[k]] = k \quad\text{for every member } k
\]

Adding 5, 2, and 9, then removing 5:

| Step | `dense` | `sparse` entries that matter |
| --- | --- | --- |
| Add 5, 2, 9 | `[5, 2, 9]` | `sparse[5] = 0`, `sparse[2] = 1`, `sparse[9] = 2` |
| Remove 5 | `[9, 2]` | `sparse[9] = 0`, `sparse[2] = 1` |

Removing moves the last member into the hole, so `dense` stays packed. That is why order is not kept.

## Operations

```text
TOMBSTONE = max unsigned value

contains(k):
    return k < sparse.size
       and sparse[k] != TOMBSTONE
       and sparse[k] < count            // only needed if sparse is not reset on remove
       and dense[sparse[k]] == k

add(k, value):
    if contains(k): return false
    if k >= sparse.size: grow sparse to k + 1, filling with TOMBSTONE
    sparse[k] = count
    dense[count] = k
    values[count] = value
    count += 1
    return true

remove(k):
    if not contains(k): return false
    i    = sparse[k]
    last = count - 1
    dense[i]  = dense[last]             // move the last member into the hole
    values[i] = values[last]
    sparse[dense[i]] = i
    sparse[k] = TOMBSTONE
    count -= 1
    return true

get(k):
    return values[sparse[k]]            // caller checked contains(k)

clear():
    for i in 0..count: sparse[dense[i]] = TOMBSTONE
    count = 0
```

The order of the three writes in `remove` matters when `k` is the last member. Then `i == last`, `dense[i]` is `k` itself, and the line `sparse[dense[i]] = i` writes `sparse[k]`. Setting `sparse[k] = TOMBSTONE` after it, not before, is what leaves `k` removed. In the other order, `sparse[k]` ends up as `count`, and only the `sparse[k] < count` check stops `contains(k)` from returning true.

`clear` above is \(O(n)\), because it resets the sparse entries. The `sparse[k] < count` check in `contains` is what allows an \(O(1)\) `clear` that only sets `count = 0`: a stale `sparse[k]` either points past `count`, or points at a slot that now holds a different key, and the final `dense[sparse[k]] == k` check rejects both. Keep that check and you can skip the tombstones entirely. Drop it and every entry must be reset.

## Iterating

Iterate `dense[0..count)`, with `values` alongside. That is a linear walk over packed memory, which is the point of the structure.

Removing the current member while walking forwards skips one: the last member moves into index `i`, and the loop moves on to `i + 1`. Walk backwards instead. The member that moves into `i` came from the end, which the loop has already visited.

```text
for i from count - 1 down to 0:
    k = dense[i]
    if should_remove(k, values[i]):
        remove(k)
```

Adding while iterating is safe in this direction too, as long as the arrays do not reallocate under a pointer or reference you hold. The new member lands at the end, which a backwards walk has already passed, so it is not visited this pass.

## Iterating two sets

To visit every key that has both a position and a velocity, walk the smaller set and test the larger:

```text
small, large = order positions and velocities by count
for i in 0..small.count:
    k = small.dense[i]
    if large.contains(k):
        visit(k, small.values[i], large.get(k))
```

The cost is the size of the smaller set. Access into the larger set jumps around. ECS libraries remove that by sorting one set's `dense` into the order of the other, so both walk forwards together. Sorting `dense` is any sort that swaps entries in `dense` and `values` together and then rewrites `sparse[dense[i]] = i` for every `i`.

## Keys with a generation

Entity ids often pack a slot index and a generation into one integer, so a stale id to a recycled slot can be told apart. Index `sparse` with the slot part only, store the full id in `dense`, and compare the full id in `contains`:

```text
contains(id):
    s = slot(id)
    return s < sparse.size and sparse[s] != TOMBSTONE and dense[sparse[s]] == id
```

A stale id then fails the last comparison, because `dense` holds the new generation. Where the generation comes from is the handle table, which is still on the [roadmap](../roadmap.md#data-structures).

## Memory for large keys

`sparse` is as long as the largest key ever added. A million possible entities is 4 MB of `sparse` per set, for a component that ten entities have.

Page it. Split `sparse` into fixed pages, for example 4096 entries, kept in an array of page pointers. A page is allocated on the first add that lands in it. A missing page means every key in it is absent:

```text
PAGE = 4096
page_of(k)   = k / PAGE
offset_of(k) = k % PAGE

sparse_lookup(k):
    p = page_of(k)
    if p >= pages.size or pages[p] is null: return TOMBSTONE
    return pages[p][offset_of(k)]
```

Use a power of two for `PAGE`, so the divide and modulo become a shift and a mask.

## Language tips

=== "C++"

    - Use `std::vector<std::uint32_t>` for `dense` and `sparse`, and `std::vector<T>` for `values`. `TOMBSTONE` is `std::numeric_limits<std::uint32_t>::max()`.
    - Move, do not copy, in `remove`: `values[i] = std::move(values.back()); values.pop_back();`. With `pop_back` the vector size is the count, and `count` disappears.
    - A `T&` or iterator from `get` is invalidated by any `add` that grows the vector, and by any `remove`, which moves another value into that slot. Hold keys across frames, never references.
    - The textbook version (Briggs and Torczon) leaves `sparse` uninitialised and relies on the two-way check. In C++, reading an uninitialised integer is undefined behaviour. Initialise `sparse` to `TOMBSTONE` when it grows.
    - `values` of a non-trivially movable type, such as one holding a `std::string`, still works, but each remove runs a move constructor. Keep component types plain.

=== "C#"

    - Use raw arrays, `int[]` and `T[]`, with a `count` field. Grow them with `Array.Resize`, doubling. A `List<T>` of structs returns a copy from its indexer, so `list[i].x = 1` does not compile and `var v = list[i]; v.x = 1;` changes nothing.
    - Return values by reference: `public ref T Get(int key) => ref _values[_sparse[key]];`. The caller can then write `ref var p = ref set.Get(id); p.x += 1;` in place. The `ref` is invalid after the next `Add` that resizes, or any `Remove`.
    - On `Remove` of a reference type or a struct holding references, clear the vacated last slot (`_values[last] = default`) so the garbage collector can free what it pointed at.
    - For Burst jobs in Unity, hold the three arrays as `NativeList<T>`. The algorithm is unchanged, and it is not safe to add or remove from two jobs at once.
    - Do not use `foreach` over the set with a removal inside. Expose `count` and indexed access to `dense` and walk it backwards, as above.

!!! warning "Common pitfalls"

    Order is not kept. Removing swaps the last member into the hole, so anything that depends on order, such as draw order, needs its own sort.

    Removing while walking forwards skips the member that was moved into the current index. Walk backwards.

    Writing `sparse[k] = TOMBSTONE` before `sparse[dense[i]] = i` in `remove` leaves a stale index for a removed key that was the last member. Without the `sparse[k] < count` check, that key still looks present.

    A reference or pointer into `values` does not survive an add or a remove. Store the key, and look the value up again.

    Keys must be bounded. A key of 4 billion makes `sparse` 16 GB unless it is paged.
