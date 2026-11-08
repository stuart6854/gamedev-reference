# Broadphase

A physics step must find every pair of bodies that might be touching. Testing every body against every other is \(n(n-1)/2\) tests: half a million for a thousand bodies. The **broadphase** cheaply finds the pairs whose bounding boxes overlap, so the expensive exact tests (the [narrowphase](narrowphase.md)) only run on those.

## Bounding boxes

Each body gets an axis-aligned bounding box (AABB) in world space, recomputed when it moves. For moving bodies, store a **fat** AABB: the real one enlarged by a margin, and stretched in the direction of motion:

```text
fat_aabb(body):
    box = body.shape.world_aabb(body.transform)
    box = expand(box, MARGIN)                          // e.g. 0.1 m
    box = extend(box, body.linear_velocity * dt * 2)   // where it is about to be
    return box

update(body):
    if not body.fat_aabb.contains(body.tight_aabb):    // only when it has left its fat box
        body.fat_aabb = fat_aabb(body)
        broadphase.move(body)
```

Most bodies move a little each step and stay inside their fat box, so the broadphase structure does not change for them at all. A slightly larger box gives a few extra pairs to the narrowphase, which rejects them quickly.

## Grids

A uniform grid (or a [spatial hash](../data-structures/spatial-hash.md)) puts each body in the cells its AABB covers; pairs are bodies sharing a cell. It is fast and simple when bodies are similar in size and spread evenly. It struggles when sizes vary a lot (a building covering hundreds of cells next to thousands of pebbles), which is common in games.

## Sweep and prune

Project every AABB onto one axis, as an interval `[min, max]`. Two boxes can only overlap if their intervals overlap on every axis, so sort the interval endpoints along one axis and sweep:

```text
sweep_and_prune(boxes, axis):
    sort boxes by box.min[axis]
    active = []
    pairs = []
    for b in boxes:
        remove from active every a with a.max[axis] < b.min[axis]
        for a in active:
            if overlap(a, b) on the other axes: pairs.append((a, b))
        active.append(b)
    return pairs
```

- Bodies move a little between steps, so last step's sorted order is almost sorted. **Insertion sort** on an almost sorted list is close to linear, which is what makes sweep and prune fast in practice.
- Choose the axis along which bodies are most spread out (the axis with the largest variance of centres). On a flat world, never sort on the vertical axis: everything overlaps in height.
- It degrades when many bodies cluster on the sweep axis, such as a long row of objects across it.

## Dynamic AABB tree

The general-purpose choice, used by Box2D, Bullet, and Jolt in various forms: a binary tree of boxes (a bounding volume hierarchy), where each internal node's box contains its two children, and leaves are bodies' fat AABBs.

```text
Node { box, parent, child1, child2, body }      // leaves have body; internal nodes have children
```

### Inserting

Find the sibling that makes the tree's total box area grow least (the surface area heuristic), and pair the new leaf with it:

```text
insert(leaf):
    sibling = root
    while sibling is internal:
        cost_here = area(union(sibling.box, leaf.box))                      // make a new parent here
        inherited = area(union(sibling.box, leaf.box)) - area(sibling.box)   // growth pushed onto ancestors
        cost1 = cost_of_descending(sibling.child1, leaf) + inherited
        cost2 = cost_of_descending(sibling.child2, leaf) + inherited
        if cost_here < cost1 and cost_here < cost2: break
        sibling = cost1 < cost2 ? sibling.child1 : sibling.child2

    new_parent = Node { box = union(sibling.box, leaf.box), children = (sibling, leaf) }
    put new_parent where sibling was
    walk up from new_parent, refitting each ancestor's box (and rotating to rebalance)
```

Erin Catto's GDC 2019 talk "Dynamic Bounding Volume Hierarchies" covers the cost function and tree rotations in detail.

### Removing and moving

Removing a leaf replaces its parent with its sibling, then refits the ancestors. Moving a body that has left its fat box is a remove and an insert.

### Finding pairs

```text
find_pairs():
    for each body that moved this step:
        query(tree, body.fat_aabb, callback = add_pair(body, other))

query(tree, box):
    stack = [root]
    while stack not empty:
        node = stack.pop()
        if not overlap(node.box, box): continue
        if node is leaf: report node.body
        else: stack.push(node.child1, node.child2)
```

Only bodies that moved are queried. Pairs between two bodies that did not move are unchanged since last step, and are kept.

Keep **static** bodies (level geometry) in a separate tree that is built once and never changes, and query moving bodies against both trees. Static-static pairs are never needed.

## Pair management

The broadphase hands the narrowphase a set of pairs, and the game wants to know when contact **begins** and **ends**:

```text
pairs: hash set of (min(id_a, id_b), max(id_a, id_b))       // order-independent key

step():
    new_pairs = broadphase.find_pairs()
    for p in new_pairs not in pairs: create a contact for p
    for p in pairs not in new_pairs: destroy its contact; if it was touching, send ContactEnded
```

- **Filter** before creating contacts: collision layers and masks (see [layer and collision masks](../data-structures/bits.md#layer-and-collision-masks)), two bodies on the same ragdoll, bodies joined by a joint that disables collision, and two static bodies.
- A pair whose boxes overlap is not a contact yet. The narrowphase decides whether shapes actually touch, and only then does `ContactBegan` fire.
- **Triggers** (sensor volumes) go through the same broadphase but skip the solver: their pairs only produce enter and exit events.
