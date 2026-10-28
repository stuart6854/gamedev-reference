# Data structures

Containers that most standard libraries do not ship, and that game code keeps rebuilding: stores keyed by small integer ids, handles that detect a dead object, and fixed-capacity buffers that never allocate.

Each page gives the structure as pseudocode, the invariant that keeps it correct, and then tips for C++ and C# where the language changes the details.

Written:

- [Sparse set](sparse-set.md) — integer keys with constant-time add, remove, and lookup, and a packed array to iterate. The component store behind most ECS libraries.
- [Handle table](handle-table.md) — index and generation handles that detect a destroyed object, the free list behind them, generation wrap, and a packed variant.
- [Ring buffer](ring-buffer.md) — a fixed-capacity queue that rejects or overwrites when full, power-of-two masking, input history, moving averages, snapshots, and a lock-free queue between two threads.
- [Free list and slab pool](free-list.md) — fixed-size blocks linked through their own free bytes, lazy init, index links, slabs that keep pointers stable, size classes, and catching use after free.

Spatial hash grids and quadtrees are on the [roadmap](../roadmap.md#data-structures).
