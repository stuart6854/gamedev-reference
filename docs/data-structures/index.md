# Data structures

Containers that most standard libraries do not ship, and that game code keeps rebuilding: stores keyed by small integer ids, handles that detect a dead object, and fixed-capacity buffers that never allocate.

Each page gives the structure as pseudocode, the invariant that keeps it correct, and then tips for C++ and C# where the language changes the details.

Written:

- [Sparse set](sparse-set.md) — integer keys with constant-time add, remove, and lookup, and a packed array to iterate. The component store behind most ECS libraries.

Handle tables, ring buffers, and free lists are on the [roadmap](../roadmap.md#data-structures).
