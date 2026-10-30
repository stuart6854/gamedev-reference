---
engine: Unity
version: 6+
uses:
  - name: Hordes and crowds
    text: Hundreds of agents head for one goal without stacking, and swarmers pursue where the player is going.
  - name: Strategy and tactics
    text: A selected group spreads out at the destination instead of fighting over one point.
  - name: Wildlife
    text: Birds, fish, and bats from separation, alignment, and cohesion.
  - name: Open worlds
    text: Pedestrians follow a flow field through streets and avoid each other.
---

# Steering and crowds

Local movement from simple forces: seek a point, arrive and slow down, flee, pursue a moving target, and keep apart from neighbours. Combined with a **flow field**, one path search serves a whole crowd heading to the same goal. This page builds a crowd that moves hundreds of agents with plain transforms, using the `SpatialHashGrid` from the [spatial hash grid](../../data-structures/spatial-hash.md#reference-implementation) page for neighbours.

A `NavMeshAgent` already does pathfinding and local avoidance for one agent, as on the [enemy behaviour](enemy.md) page. Each agent costs a path and an avoidance solve. Past a few hundred agents, or when the motion should look like a crowd rather than individuals, steering takes over.

## The model

Each agent has a position \(\mathbf{p}\), a velocity \(\mathbf{v}\), a maximum speed, and a maximum acceleration. Every behaviour returns a **steering** vector, which is a requested change of velocity. The agent sums them, clamps, and integrates:

```text
steering = sum of weight_i * behaviour_i
steering = clamp_length(steering, max_accel)
v = clamp_length(v + steering * dt, max_speed)
p = p + v * dt
```

Most behaviours compute a **desired velocity** and return `desired - v`. The agent then turns towards the desired velocity at a rate limited by its acceleration, which is what makes the motion look physical rather than snappy.

## Behaviours

| Behaviour | Desired velocity | Notes |
| --- | --- | --- |
| **Seek** | Towards the target at max speed. | Overshoots and orbits a fixed point. |
| **Flee** | Away from the threat at max speed. | Usually only within a panic radius. |
| **Arrive** | Towards the target, at max speed scaled by \(\min(1, d / r_{\text{slow}})\). | Slows to a stop inside the slowing radius. |
| **Pursue** | Seek the target's predicted position \(\mathbf{p}_t + \mathbf{v}_t\,\tau\). | \(\tau = \min(d / v_{\max}, \tau_{\max})\). Evade is flee from the same point. |
| **Wander** | Forward, with a heading that drifts by a small random amount each frame. | Looks aimless without jitter. |
| **Separation** | Away from each neighbour within \(r\), weighted by \(1 - d/r\). | The one behaviour every crowd needs. |
| **Alignment** | The average velocity of neighbours. | Flocks only. |
| **Cohesion** | Seek the centre of neighbours. | Flocks only. |

### Combining

A **weighted sum** is simple, and fine for most crowds: separation at 1.5, the goal at 1. Its weakness is cancellation: separation and seek pointing in opposite directions sum to nothing, and the agent stops in a jam.

A **priority** blend fills the acceleration budget in order: separation first, then the goal with whatever acceleration remains. Agents in a crush still try to spread out before they push forward.

## Flow fields

A crowd of 500 heading to one place does not need 500 paths. A flow field does one search, from the goal outwards, over a grid of the area:

1. **Cost field.** Mark each cell walkable or blocked, once, when the level loads.
2. **Integration field.** Breadth-first search from the goal cell. Each walkable cell stores its step count to the goal.
3. **Direction field.** Each cell points at its neighbour with the lowest count.

An agent looks up its cell and uses that direction as its desired velocity. Changing the goal recomputes the field, once, for every agent. For a field that moves with the player, recompute when the player changes cell, or on a short interval.

Diagonal moves are allowed only when both neighbouring straight cells are walkable, or agents cut wall corners. Breadth-first search treats a diagonal as one step, which makes paths a little zig-zag. Dijkstra with a cost of \(\sqrt{2}\) for diagonals fixes that at the price of a priority queue.

## Setup

1. Copy `SpatialHashGrid` from the [spatial hash grid](../../data-structures/spatial-hash.md#reference-implementation) page, then `Steering`, `FlowField`, and `Crowd` below.
2. Put `FlowField` on an empty object at the bottom-left corner of the walkable area. Set **Size** in cells and **Cell Size**. Set **Obstacle Mask** to the walls. The gizmo shows blocked cells in red and the directions as lines.
3. Put `Crowd` on any object. Assign the field and a **Target**. Agents register with `Crowd.Add(transform)`, for example from a spawner, or add children with **Adopt Children On Start**.
4. Call `FlowField.SetGoal(position)` when the goal moves. `Crowd` does this for you every **Goal Refresh** seconds while a target is assigned.
5. Agents are moved on the ground plane. Their height stays where it was spawned. For uneven ground, raycast down in a later pass.

## Scripts

### Steering behaviours

```csharp
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Steering behaviours on the XZ plane. Each returns a change of velocity: desired minus current.
/// </summary>
public static class Steering
{
    public static Vector3 Seek(Vector3 position, Vector3 velocity, Vector3 target, float maxSpeed)
    {
        return Flat(target - position).normalized * maxSpeed - velocity;
    }

    public static Vector3 Flee(Vector3 position, Vector3 velocity, Vector3 threat, float maxSpeed)
    {
        return Flat(position - threat).normalized * maxSpeed - velocity;
    }

    public static Vector3 Arrive(Vector3 position, Vector3 velocity, Vector3 target, float maxSpeed, float slowRadius)
    {
        Vector3 to = Flat(target - position);
        float distance = to.magnitude;
        if (distance < 1e-4f)
            return -velocity;
        float speed = maxSpeed * Mathf.Min(1f, distance / Mathf.Max(slowRadius, 1e-4f));
        return to / distance * speed - velocity;
    }

    public static Vector3 Pursue(Vector3 position, Vector3 velocity, Vector3 targetPosition, Vector3 targetVelocity,
        float maxSpeed, float maxPrediction)
    {
        float distance = Vector3.Distance(position, targetPosition);
        float lead = Mathf.Min(distance / Mathf.Max(maxSpeed, 0.01f), maxPrediction);
        return Seek(position, velocity, targetPosition + targetVelocity * lead, maxSpeed);
    }

    /// <summary>Drifts a stored heading by up to jitter degrees per second, and walks along it.</summary>
    public static Vector3 Wander(Vector3 velocity, ref float headingDegrees, float jitter, float maxSpeed, float dt)
    {
        headingDegrees += Random.Range(-jitter, jitter) * dt;
        Vector3 desired = Quaternion.Euler(0f, headingDegrees, 0f) * Vector3.forward * maxSpeed;
        return desired - velocity;
    }

    /// <summary>A push away from each neighbour within radius, stronger when closer. Not scaled by speed.</summary>
    public static Vector3 Separation(Vector3 position, IReadOnlyList<Vector3> neighbours, float radius)
    {
        Vector3 push = Vector3.zero;
        for (int i = 0; i < neighbours.Count; i++)
        {
            Vector3 away = Flat(position - neighbours[i]);
            float distance = away.magnitude;
            if (distance > 1e-4f && distance < radius)
                push += away / distance * (1f - distance / radius);
        }
        return push;
    }

    static Vector3 Flat(Vector3 v)
    {
        v.y = 0f;
        return v;
    }
}
```

### Flow field

```csharp
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// A grid on the XZ plane that points every walkable cell towards a goal. One search serves every agent.
/// </summary>
public class FlowField : MonoBehaviour
{
    [Tooltip("Cells along X and Z. The transform is the bottom-left corner.")]
    [SerializeField] Vector2Int size = new Vector2Int(64, 64);
    [Min(0.1f)] [SerializeField] float cellSize = 1f;
    [SerializeField] LayerMask obstacleMask;
    [SerializeField] float obstacleCheckHeight = 1.8f;

    const int Unreached = int.MaxValue;

    bool[] _blocked;
    int[] _steps;
    Vector3[] _direction;
    readonly Queue<int> _open = new Queue<int>();
    int _goalCell = -1;
    Vector3 _goal;

    public float CellSize => cellSize;

    void Awake()
    {
        int count = size.x * size.y;
        _blocked = new bool[count];
        _steps = new int[count];
        _direction = new Vector3[count];
        BakeObstacles();
    }

    /// <summary>Marks cells that overlap obstacles. Call again if walls move.</summary>
    public void BakeObstacles()
    {
        Vector3 halfExtents = new Vector3(cellSize * 0.45f, obstacleCheckHeight * 0.5f, cellSize * 0.45f);
        for (int z = 0; z < size.y; z++)
        {
            for (int x = 0; x < size.x; x++)
            {
                Vector3 centre = CellCentre(x, z) + Vector3.up * (obstacleCheckHeight * 0.5f);
                _blocked[Index(x, z)] = Physics.CheckBox(centre, halfExtents, Quaternion.identity, obstacleMask,
                    QueryTriggerInteraction.Ignore);
            }
        }
        _goalCell = -1;
    }

    /// <summary>Recomputes the field towards goal. Skipped if the goal is in the same cell as last time.</summary>
    public void SetGoal(Vector3 goal)
    {
        _goal = goal;
        if (!TryCell(goal, out int gx, out int gz))
            return;

        int goalCell = Index(gx, gz);
        if (goalCell == _goalCell)
            return;
        _goalCell = goalCell;

        // Integration field: breadth-first steps from the goal over 4 neighbours.
        for (int i = 0; i < _steps.Length; i++)
            _steps[i] = Unreached;
        _open.Clear();
        _steps[goalCell] = 0;
        _open.Enqueue(goalCell);

        while (_open.Count > 0)
        {
            int cell = _open.Dequeue();
            int cx = cell % size.x, cz = cell / size.x;
            Visit(cx + 1, cz, _steps[cell] + 1);
            Visit(cx - 1, cz, _steps[cell] + 1);
            Visit(cx, cz + 1, _steps[cell] + 1);
            Visit(cx, cz - 1, _steps[cell] + 1);
        }

        // Direction field: towards the lowest of the 8 neighbours, without cutting corners.
        for (int z = 0; z < size.y; z++)
        {
            for (int x = 0; x < size.x; x++)
            {
                int cell = Index(x, z);
                _direction[cell] = Vector3.zero;
                if (_blocked[cell] || _steps[cell] == Unreached || cell == goalCell)
                    continue;

                int best = _steps[cell];
                for (int dz = -1; dz <= 1; dz++)
                {
                    for (int dx = -1; dx <= 1; dx++)
                    {
                        if ((dx == 0 && dz == 0) || !Walkable(x + dx, z + dz))
                            continue;
                        if (dx != 0 && dz != 0 && (!Walkable(x + dx, z) || !Walkable(x, z + dz)))
                            continue;

                        int steps = _steps[Index(x + dx, z + dz)];
                        if (steps < best)
                        {
                            best = steps;
                            _direction[cell] = new Vector3(dx, 0f, dz).normalized;
                        }
                    }
                }
            }
        }
    }

    /// <summary>Unit direction towards the goal, or zero outside the field, in a wall, or unreachable.</summary>
    public Vector3 Direction(Vector3 position)
    {
        if (!TryCell(position, out int x, out int z))
            return Vector3.zero;

        int cell = Index(x, z);
        if (cell == _goalCell)
        {
            Vector3 to = _goal - position;
            to.y = 0f;
            return to.sqrMagnitude > 1e-4f ? to.normalized : Vector3.zero;
        }
        return _direction[cell];
    }

    void Visit(int x, int z, int steps)
    {
        if (!Walkable(x, z))
            return;
        int cell = Index(x, z);
        if (_steps[cell] != Unreached)
            return;
        _steps[cell] = steps;
        _open.Enqueue(cell);
    }

    bool Walkable(int x, int z)
    {
        return x >= 0 && z >= 0 && x < size.x && z < size.y && !_blocked[Index(x, z)];
    }

    bool TryCell(Vector3 position, out int x, out int z)
    {
        Vector3 local = position - transform.position;
        x = Mathf.FloorToInt(local.x / cellSize);
        z = Mathf.FloorToInt(local.z / cellSize);
        return x >= 0 && z >= 0 && x < size.x && z < size.y;
    }

    int Index(int x, int z) => z * size.x + x;

    Vector3 CellCentre(int x, int z) => transform.position + new Vector3((x + 0.5f) * cellSize, 0f, (z + 0.5f) * cellSize);

    void OnDrawGizmosSelected()
    {
        if (_blocked == null)
            return;

        for (int z = 0; z < size.y; z++)
        {
            for (int x = 0; x < size.x; x++)
            {
                int cell = Index(x, z);
                Vector3 centre = CellCentre(x, z);
                if (_blocked[cell])
                {
                    Gizmos.color = new Color(1f, 0.2f, 0.2f, 0.5f);
                    Gizmos.DrawCube(centre, new Vector3(cellSize, 0.05f, cellSize));
                }
                else if (_direction[cell] != Vector3.zero)
                {
                    Gizmos.color = Color.cyan;
                    Gizmos.DrawLine(centre, centre + _direction[cell] * cellSize * 0.45f);
                }
            }
        }
    }
}
```

### Crowd

```csharp
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Moves many agents with a flow field, arrival, and separation. Positions only: no physics.
/// </summary>
public class Crowd : MonoBehaviour
{
    [SerializeField] FlowField field;
    [SerializeField] Transform target;
    [SerializeField] float goalRefresh = 0.25f;
    [SerializeField] bool adoptChildrenOnStart = true;

    [Header("Motion")]
    [SerializeField] float maxSpeed = 3.5f;
    [SerializeField] float maxAcceleration = 12f;
    [SerializeField] float arriveRadius = 2f;
    [SerializeField] float turnSpeed = 540f;

    [Header("Separation")]
    [SerializeField] float separationRadius = 1f;
    [SerializeField] float separationWeight = 1.5f;
    [Tooltip("Neighbours considered per agent. Caps the cost inside a dense pile.")]
    [SerializeField] int maxNeighbours = 8;

    readonly List<Transform> _agents = new List<Transform>();
    readonly List<int> _near = new List<int>();
    readonly List<Vector3> _nearPositions = new List<Vector3>();
    Vector3[] _velocity = new Vector3[0];
    Vector3[] _position = new Vector3[0];
    float[] _x = new float[0];
    float[] _z = new float[0];
    SpatialHashGrid _grid;
    float _nextGoal;

    public int Count => _agents.Count;

    void Awake()
    {
        _grid = new SpatialHashGrid(separationRadius, 1024);
    }

    void Start()
    {
        if (!adoptChildrenOnStart)
            return;
        foreach (Transform child in transform)
            Add(child);
    }

    public void Add(Transform agent)
    {
        if (agent == null || _agents.Contains(agent))
            return;
        _agents.Add(agent);
        Grow(_agents.Count);
        _velocity[_agents.Count - 1] = Vector3.zero;
    }

    public void Remove(Transform agent)
    {
        int index = _agents.IndexOf(agent);
        if (index >= 0)
            RemoveAt(index);
    }

    void Update()
    {
        float dt = Time.deltaTime;
        if (dt <= 0f)
            return;

        if (field != null && target != null && Time.time >= _nextGoal)
        {
            field.SetGoal(target.position);
            _nextGoal = Time.time + goalRefresh;
        }

        // Drop destroyed agents, keeping velocities aligned with the list.
        for (int i = _agents.Count - 1; i >= 0; i--)
        {
            if (_agents[i] == null)
                RemoveAt(i);
        }

        int count = _agents.Count;
        for (int i = 0; i < count; i++)
        {
            _position[i] = _agents[i].position;
            _x[i] = _position[i].x;
            _z[i] = _position[i].z;
        }
        _grid.Build(_x, _z, count);

        // Every agent reads this frame's positions, then all move together.
        for (int i = 0; i < count; i++)
        {
            Vector3 position = _position[i];
            Vector3 velocity = _velocity[i];

            Vector3 steer = Goal(position, velocity);

            _near.Clear();
            _nearPositions.Clear();
            _grid.Query(position.x, position.z, separationRadius, _near);
            for (int n = 0; n < _near.Count && _nearPositions.Count < maxNeighbours; n++)
            {
                if (_near[n] != i)
                    _nearPositions.Add(_position[_near[n]]);
            }
            steer += Steering.Separation(position, _nearPositions, separationRadius) * separationWeight * maxSpeed;

            steer = Vector3.ClampMagnitude(steer, maxAcceleration);
            _velocity[i] = Vector3.ClampMagnitude(velocity + steer * dt, maxSpeed);
        }

        for (int i = 0; i < count; i++)
        {
            Transform agent = _agents[i];
            agent.position = _position[i] + _velocity[i] * dt;

            Vector3 heading = _velocity[i];
            if (heading.sqrMagnitude > 0.04f)
                agent.rotation = Quaternion.RotateTowards(agent.rotation, Quaternion.LookRotation(heading), turnSpeed * dt);
        }
    }

    Vector3 Goal(Vector3 position, Vector3 velocity)
    {
        if (target == null)
            return -velocity; // brake

        Vector3 toTarget = target.position - position;
        toTarget.y = 0f;
        if (field == null || toTarget.magnitude < arriveRadius)
            return Steering.Arrive(position, velocity, target.position, maxSpeed, arriveRadius);

        Vector3 direction = field.Direction(position);
        if (direction == Vector3.zero)
            return Steering.Arrive(position, velocity, target.position, maxSpeed, arriveRadius);
        return direction * maxSpeed - velocity;
    }

    void RemoveAt(int index)
    {
        int last = _agents.Count - 1;
        _agents[index] = _agents[last];
        _velocity[index] = _velocity[last];
        _agents.RemoveAt(last);
    }

    void Grow(int needed)
    {
        if (_velocity.Length >= needed)
            return;
        int size = Mathf.Max(needed, _velocity.Length * 2);
        System.Array.Resize(ref _velocity, size);
        System.Array.Resize(ref _position, size);
        System.Array.Resize(ref _x, size);
        System.Array.Resize(ref _z, size);
    }
}
```

The velocities are computed for every agent before any agent moves. Updating positions inside the first loop would let early agents react to where later agents will be, and the order in the list would show in the motion.

## Scaling further

- **Thousands of agents.** Move the two loops into Burst jobs, with positions in `NativeArray<float3>` and `IJobParallelForTransform` writing the transforms through a `TransformAccessArray`. The grid's counting sort is a natural job too.
- **Rendering.** Thousands of separate GameObjects with skinned meshes cost more to draw than to move. GPU instancing, or vertex-animation textures for the walk, carry the rest.
- **Far agents.** Agents far from the player can step less often, or as a group. That is [horde simulation](horde.md)'s level of detail, not this page.

!!! warning "Common pitfalls"

    Without separation, every agent arrives at the same point and they stack into one. Without a neighbour cap, a pile of a hundred agents makes every query in it slow.

    A weighted sum lets separation and the goal cancel in a doorway, and the crowd stops. Raise the goal weight near the door, or use a priority blend.

    A flow field cell size much larger than an agent lets agents cut corners into walls; much smaller costs a larger search. Use about one agent width.

    Agents outside the field's area get a zero direction and fall back to arrival straight at the target, through walls. Make the field cover the whole playable area.

    These agents have no colliders pushing them out of walls. Separation can shove one into a wall where the field gives no direction. Keep obstacle cells slightly larger than the walls, or resolve agents against walls after moving.
