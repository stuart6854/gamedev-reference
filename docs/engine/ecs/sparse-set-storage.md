# Sparse-set storage

One [sparse set](../../data-structures/sparse-set.md) per component type, called a pool, keyed by [entity](entities.md) index. Adding or removing a component touches only that type's pool. Iterating one type is a walk over a packed array. Iterating several types is where the design needs extra work. EnTT is the best-known library built this way.

## The world

```text
Pool<T> {
    sparse[]                            // entity index -> position in dense
    dense[]                             // entity ids, packed
    values[]                            // T, parallel to dense
}

World {
    entities, free_head                 // from the entities page
    pools[]                             // pools[type_id(T)] is the Pool<T>, or null
}
```

Each component type gets a small integer id the first time it is used, and the world keeps pools in an array indexed by it. That makes finding a pool an array index, not a hash lookup.

```text
next_type_id = 0

type_id(T):                             // the same T always gets the same id
    if T has no id yet:
        T.id = next_type_id
        next_type_id += 1
    return T.id
```

## Components

```text
add(e, value: T):
    pool = pool_for(T)                  // creates the pool on first use
    pool.add(index_of(e), e, value)     // sparse by index, dense holds the full id

get(e, T):
    return pool_for(T).get(index_of(e))

has(e, T):
    return pool_for(T).contains(e)      // compares the full id, so a stale e fails

remove(e, T):
    pool_for(T).remove(e)
```

These are the sparse set operations unchanged, with the [generation check](../../data-structures/sparse-set.md#keys-with-a-generation) in `contains`. Removing a component moves the pool's last component into the hole, and nothing else in the world changes.

## Views

A view visits every entity with all of a set of components. Walk the smallest pool and test the others:

```text
view(A, B, C):
    lead = the pool among A, B, C with the smallest count
    for i from lead.count - 1 down to 0:
        e = lead.dense[i]
        if A.contains(e) and B.contains(e) and C.contains(e):
            visit(e, A.get(e), B.get(e), C.get(e))
```

The cost is the size of the smallest pool, times one `contains` per other type. The lead pool is walked in order. Every other pool is read at random positions, which costs a cache miss per entity when the pools are large.

An exclusion, "with A but without B", is the same walk with `not B.contains(e)`.

Walking backwards lets a system remove the current entity's components, for the reason on the [sparse set](../../data-structures/sparse-set.md#iterating) page. Other changes during the walk, such as adding components or changing other entities, can move values that a reference from `get` still points at, and inside a group they reorder the range being walked. Record those in a [command buffer](entities.md#deferred-commands).

## Groups

A group makes a multi-type walk packed. For a group that owns A and B, both pools keep the entities that have both at the front, `[0, size)`, in the same order. Then position `i` in A and position `i` in B are the same entity, and the walk is two arrays side by side:

```text
for i in 0 .. group.size:
    visit(A.dense[i], A.values[i], B.values[i])
```

Keeping that true costs a swap on every change that affects membership:

```text
swap(pool, i, j):                       // swap two positions, fix sparse
    exchange pool.dense[i] and pool.dense[j]
    exchange pool.values[i] and pool.values[j]
    pool.sparse[index_of(pool.dense[i])] = i
    pool.sparse[index_of(pool.dense[j])] = j

after adding A or B to e:
    if A.contains(e) and B.contains(e):
        swap(A, A.position(e), group.size)
        swap(B, B.position(e), group.size)
        group.size += 1

before removing A or B from e:
    if e is in the group (A.position(e) < group.size):
        group.size -= 1
        swap(A, A.position(e), group.size)
        swap(B, B.position(e), group.size)
    then remove as usual
```

The removal must swap the entity out of the group before the pool's own swap-and-pop, or the pop moves a non-member into the group's range.

A pool's order can belong to only one group, because two groups would want different entities at the front. Choose the groups for the hottest systems, and leave the rest as views. EnTT calls these owning groups, and allows nested groups that own a subset of another group's types.

## When to use it

- Components that come and go often: status effects, one-frame tags such as "damaged this frame", input events.
- Many entities with unusual combinations of components, which an archetype world would split into many small tables.
- Code that needs stable cost for add and remove, regardless of how many other components the entity has.

It is slower than archetypes for systems that read several components of most entities every frame, unless those systems use groups.

## Language tips

=== "C++"

    - The pool array holds a base class, such as `struct PoolBase { virtual void remove(Entity) = 0; virtual ~PoolBase() = default; };`, with `Pool<T>` derived from it. Destroying an entity calls `remove` through the base on every pool.
    - A type id from a function-local static, `template <class T> std::size_t type_id() { static const std::size_t id = next_type_id++; return id; }`, differs between a DLL and the executable. Pass ids across that boundary explicitly, or hash a type name.
    - A `T&` from `get` is invalid after any add or remove in the same pool. Groups add more moves, since membership changes swap other entities' components.

=== "C#"

    - Use a static generic class for type ids: `static class TypeId<T> { public static readonly int Value = Interlocked.Increment(ref TypeIds.Next) - 1; }`. The runtime initialises it once per `T`.
    - Keep pools in an array of a non-generic base, `abstract class Pool`, with `sealed class Pool<T> : Pool where T : struct`. Cast to `Pool<T>` once per view, not per entity.
    - Return components with `ref T Get(Entity e)` so a system edits in place. A view method can hand out `Span<T>` of the packed values for a group.

!!! warning "Common pitfalls"

    A reference from `get` held across an add or remove in the same pool points at whatever was moved into that slot. Look the component up again, or defer the change with a command buffer.

    A view that leads with the largest pool instead of the smallest does the same work as no filter. Pick the lead by count each time the view starts, since counts change.

    Two groups that both own the same pool corrupt each other's order. Give each pool one owner.

    Removing a group member without swapping it out first leaves the group range holding an entity without both components.
