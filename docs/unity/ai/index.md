# AI

Agents that decide what to do, on top of a body from [Mechanics](../mechanics/index.md). The decision model is the [state machine](../architecture/state-machines.md) from Architecture.

Written:

- [Enemy behaviour](enemy.md) — patrol, chase, attack, search, and flee on a `NavMeshAgent`, with placeholder sight.
- [Enemy waves](waves.md) — off-screen spawn points, an alive cap, and authored or budget-bought waves.
- [Continuous spawning](spawning.md) — a timed trickle on curves, proximity zones, and a director that paces build-up, peak, and relax.
- [Horde simulation](horde.md) — thousands of agents as records, with active, simple, and dormant tiers, hysteresis, an active budget, time slicing, and attraction.

Perception, utility AI, and steering behaviours are still on the [roadmap](../../roadmap.md#ai).
