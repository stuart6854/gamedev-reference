# Scene and transform hierarchy

Objects in a scene are arranged in a tree: a sword is a child of the hand bone, the hand of the character, the character of the moving platform it stands on. Each object stores its transform **relative to its parent**, and its world transform is its parent's world transform combined with its own. This page covers storing that tree, updating world transforms cheaply, and doing it in an ECS.

## Local and world

```text
Transform {
    local_position, local_rotation, local_scale     // relative to the parent
    world_matrix                                    // derived: parent.world_matrix * local_matrix
}

local_matrix(t) = translate(t.local_position) * rotate(t.local_rotation) * scale(t.local_scale)
world(t)        = t.parent ? world(t.parent) * local_matrix(t) : local_matrix(t)
```

Store the **local** values, which is what moves and what is edited, and derive the world matrix. Code that sets a world position converts it into the parent's space first:

```text
set_world_position(t, p):
    t.local_position = t.parent ? inverse(world(t.parent)) * p : p
```

Non-uniform scale on a parent with rotated children produces shear, which a position, rotation, and scale cannot represent. Either forbid non-uniform scale on objects with children, or keep world transforms as full matrices (as above) and only decompose them where needed.

## Dirty flags

Recomputing every world matrix every frame is simple and, for a few thousand objects, fast enough. For more, recompute only what changed:

```text
set_local_position(t, p):
    t.local_position = p
    mark_dirty(t)

mark_dirty(t):
    if t.dirty: return              // its subtree is already marked
    t.dirty = true
    for c in t.children: mark_dirty(c)

world_matrix(t):                    // lazily, when read
    if t.dirty:
        t.world_matrix = t.parent ? world_matrix(t.parent) * local_matrix(t) : local_matrix(t)
        t.dirty = false
    return t.world_matrix
```

Moving a character marks every attached child dirty, and each is recomputed once, when something reads it. The early return in `mark_dirty` makes repeated moves in one frame cheap.

Lazy recomputation on read is convenient but scatters work across the frame and across threads. The alternative is an explicit **update pass** once per frame, after gameplay and animation and before rendering and physics read the results.

## Storing the tree

A tree of objects with child pointers is easy to write and slow to walk: each node is somewhere different in memory. Store it as arrays instead.

### Parent indices in update order

```text
parent[]        // index of each node's parent, or -1
local[]         // local transforms
world[]         // world matrices

invariant: parent[i] < i for every node       // parents come before their children

update():
    for i in 0 .. count - 1:
        world[i] = parent[i] < 0 ? local[i] : world[parent[i]] * local[i]
```

With every parent stored before its children, one forward pass over the arrays updates the whole hierarchy: each parent's world matrix is ready by the time its children need it. This is how skeletons are stored, and it is the fastest layout for a hierarchy that rarely changes shape.

Reparenting breaks the ordering, so the arrays have to be re-sorted (a topological sort by depth) after structural changes. Do it once per frame, after all reparenting, not after each change.

### Depth buckets for parallel updates

To update in parallel, group nodes by depth:

```text
depth 0: roots          -> update all in parallel
depth 1: their children -> update all in parallel
depth 2: ...
```

Every node at depth d depends only on depth d − 1, so each level is a [parallel for](jobs/parallel-for.md). Most scenes are wide and shallow (thousands of roots, few deep chains), so the first levels carry most of the work.

## Hierarchies in an ECS

In an [ECS](ecs/index.md), the hierarchy is components:

```text
LocalTransform  { position, rotation, scale }
Parent          { entity }
Children        { entities[] }            // optional; kept in sync with Parent
WorldTransform  { matrix }                // written by the transform system
```

- Entities **without** a `Parent` are roots: their world transform is their local transform, and a system can update them all as one tight loop over packed components.
- Entities **with** a `Parent` are updated after their parent, by depth, as above.
- Keep `Parent` as the source of truth and rebuild `Children` from it, so the two can never disagree.
- Unity's Entities package uses this model: `LocalTransform`, `Parent`, `Child`, and `LocalToWorld` computed by the transform system.

Most entities in a game have no parent, so the hierarchy only costs anything for the entities that use it.

## Rules that keep it simple

- **One update point.** World transforms are valid after the transform pass and before the next change. Systems that read world transforms run after the pass; systems that write local transforms run before it. Anything that reads a world transform in between gets last frame's value.
- **Destroying a parent** destroys its children, or detaches them (keeping their world transform). Decide which per object, and apply it in the [deferred command](patterns/frame.md#deferred-commands) pass, not mid-iteration.
- **Reparenting keeps the world transform** by default (convert the local transform into the new parent's space), so an object picked up does not jump. Offer an option to keep the local transform instead, for snapping an item to a socket.
- **Physics bodies** usually should not be children of moving objects. The physics engine moves them in world space; a parent moving them too fights it. Attach with a joint, or move the body to follow the parent explicitly.
- **Static** objects (most of a level) never change after loading. Compute their world matrices once, and keep them out of the per-frame update.
