# AI

Agents that decide what to do, on top of a body from [Mechanics](../mechanics/index.md). The decision model is the [state machine](../architecture/state-machines.md) from Architecture.

Written:

- [Enemy behaviour](enemy.md) — patrol, chase, attack, search, and flee on a `NavMeshAgent`, with simple sight.
- [Perception](perception.md) — sight cones with several aim points, noise events muffled by walls, an awareness meter, and memory of the last known position.
- [Noise sources](noise.md) — one call for perceivers and the horde, a loudness table, footsteps by gait and surface, impacts, damage and breaking, alarms, and noise rings for the player.
- [Steering and crowds](steering.md) — seek, arrive, flee, pursue, wander, and separation, a flow field for one goal, and a crowd that moves hundreds of agents.
- [Utility AI](utility.md) — actions scored from considerations and response curves, compensation, momentum and commitment, and a needs example.
- [Enemy waves](waves.md) — off-screen spawn points, an alive cap, and authored or budget-bought waves.
- [Continuous spawning](spawning.md) — a timed trickle on curves, proximity zones, and a director that paces build-up, peak, and relax.
- [Horde simulation](horde.md) — thousands of agents as records, with active, simple, and dormant tiers, hysteresis, an active budget, time slicing, and attraction.
- [Navigation scenarios](navigation/index.md) — doors and windows as NavMesh links, breaking through when it is quicker or the only way, surrounding large targets, and recovering stuck agents and queueing at chokepoints.

Behaviour trees are on the [roadmap](../../roadmap.md#ai).
