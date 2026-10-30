---
engine: Unity
version: 6+
package: AI Navigation 2.x
uses:
  - name: Zombie hordes
    text: Thousands of zombies across the map, with full AI only for the few near the player.
  - name: Herds and wildlife
    text: Herds graze and migrate across a large map without a GameObject each.
  - name: City crowds and traffic
    text: Pedestrians and cars exist down every street, but only nearby ones are real.
  - name: RTS armies
    text: Off-screen battles resolve cheaply while on-screen ones get full detail.
---

# Horde simulation

Simulating far more agents than can each have a GameObject, a `NavMeshAgent`, animation, and a brain. The trick is **level of detail for behaviour**: agents near the player are fully real, agents a little further out are cheap dots that still move, and agents far away are records that update every few seconds. An agent is promoted when the player comes near and demoted when the player leaves, so the player only ever sees the expensive kind.

The same idea runs Project Zomboid's map-wide zombie population, wildlife in open worlds, and pedestrians in city games.

## Tiers

| Tier | Where | Exists as | Updates | Moves by |
| --- | --- | --- | --- | --- |
| **Active** | Within **Active Radius**, up to **Max Active** | A pooled prefab instance with its own brain, perception, animation | Every frame, by its own components | Its own `NavMeshAgent` or steering |
| **Simple** | Within **Simple Radius** | A record in an array | Every **Simple Interval**, about 4 times a second | Straight towards its goal, or wandering, with light separation |
| **Dormant** | Everywhere else | A record in an array | Every **Dormant Interval**, every couple of seconds | Straight towards its goal, or wandering |

Simple and dormant agents ignore walls. That is acceptable because nobody is watching them, and it is why promotion snaps them onto the NavMesh. For a map where walls matter at a distance, such as a city, move them along a coarse graph of roads or sectors instead of in straight lines.

### Promotion and demotion

Distance to the player decides the wanted tier. Two rules keep it stable:

- **Hysteresis.** An active agent stays active until it is **Hysteresis** metres beyond the active radius. Without it, an agent on the boundary is promoted and demoted every frame, creating and releasing its instance each time.
- **A budget.** At most **Max Active** agents are active. When more want to be, the nearest win. The rest stay simple until room appears, so a horde rushing the player becomes real front row first.

Promotion takes an instance from a pool, places it at the record's position snapped to the NavMesh, and passes on any goal. Demotion copies the instance's position back into the record and returns the instance to the pool. While an agent is active, its instance is the truth, and the record follows it.

### Time slicing

Simple and dormant records are not all stepped every frame. Each has a next-tick time, spread randomly when it is added, so about \(n \cdot \Delta t / \text{interval}\) records step per frame. Each step uses the real time since that record's last step, so speed does not depend on the interval.

10,000 dormant records at a 2-second interval is 5,000 steps a second, about 80 a frame at 60 fps.

## Goals and attraction

Records carry a goal. `Attract(position, radius)` sets the goal of every record within the radius, whatever its tier, using a spatial hash grid of all record positions. Active agents get the call too, through the `Attracted` event on their `HordeAgent`, for their brain to act on.

This is how noise moves a horde. Forward gameplay noises to it alongside the per-agent [perception](perception.md#hearing):

```csharp
// A gunshot: nearby perceivers hear it, and the wider population drifts towards it.
Noise.Emit(muzzle.position, 40f, gameObject);
horde.Attract(muzzle.position, 120f);
```

Large meta-events, such as a helicopter passing over, call `Attract` with a radius of hundreds of metres, and the far population slowly migrates. With no goal, a record wanders: its heading drifts by a random amount each step.

## Persistence

Records are plain data: a position, a heading, a goal. Saving the horde is saving the array, and a level that streams in chunks can keep the records of an unloaded chunk and step them at the dormant rate, or not at all. A killed agent is removed from the array, so it stays dead.

## Setup

1. Make the agent prefab: the full enemy, such as the one from [enemy behaviour](enemy.md), plus `HordeAgent` on the root. When it dies, call `HordeAgent.Kill()`; the record is removed and the corpse is left to the prefab.
2. Copy `SpatialHashGrid` from the [spatial hash grid](../../data-structures/spatial-hash.md#reference-implementation) page, then `HordeAgent` and `HordeSimulation` below.
3. Put `HordeSimulation` on a manager object. Assign the player and the prefab. Set the radii and **Max Active**.
4. Populate it with `Add(position)`, for example scattered over the map at load, or from a [spawner](spawning.md) that adds records instead of instantiating.
5. Select the manager in Play mode. Gizmos show dormant records in grey, simple in yellow, and active in red.

## Scripts

### Horde agent

```csharp
using System;
using UnityEngine;
using UnityEngine.AI;

/// <summary>
/// On the prefab of a horde member. Links the instance to its record while active.
/// </summary>
public class HordeAgent : MonoBehaviour
{
    public HordeSimulation Simulation { get; internal set; }
    public int Index { get; internal set; } = -1;

    /// <summary>Raised when the simulation attracts this agent. The brain decides what to do.</summary>
    public event Action<Vector3> Attracted;

    NavMeshAgent _navAgent;

    void Awake()
    {
        TryGetComponent(out _navAgent);
    }

    internal void Place(Vector3 position, Quaternion rotation)
    {
        // A NavMeshAgent must be warped; setting the transform alone is undone by the agent.
        if (_navAgent != null && _navAgent.isActiveAndEnabled)
            _navAgent.Warp(position);
        transform.SetPositionAndRotation(position, rotation);
    }

    internal void RaiseAttracted(Vector3 position)
    {
        Attracted?.Invoke(position);
    }

    /// <summary>Call on death. Removes the record; the instance stays for the death animation.</summary>
    public void Kill()
    {
        if (Simulation != null)
            Simulation.Kill(this);
    }
}
```

### Horde simulation

```csharp
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.Pool;

/// <summary>
/// Many agents as records, with tiers by distance: active instances near the player,
/// cheap stepped records further out, and rarely stepped records far away.
/// </summary>
public class HordeSimulation : MonoBehaviour
{
    public enum Tier : byte
    {
        Dormant,
        Simple,
        Active
    }

    struct Member
    {
        public Vector3 Position;
        public Vector3 Heading;
        public Vector3 Goal;
        public bool HasGoal;
        public Tier Tier;
        public float NextTick;
        public float LastTick;
        public HordeAgent View;
    }

    [SerializeField] Transform player;
    [SerializeField] HordeAgent prefab;

    [Header("Tiers")]
    [SerializeField] float activeRadius = 30f;
    [SerializeField] float simpleRadius = 90f;
    [SerializeField] float hysteresis = 6f;
    [SerializeField] int maxActive = 60;
    [SerializeField] float simpleInterval = 0.25f;
    [SerializeField] float dormantInterval = 2f;

    [Header("Movement")]
    [SerializeField] float speed = 1.4f;
    [SerializeField] float wanderTurn = 90f;
    [SerializeField] float arriveRadius = 4f;
    [SerializeField] float separationRadius = 1.2f;

    Member[] _members = new Member[256];
    float[] _x = new float[256];
    float[] _z = new float[256];
    float[] _distance = new float[256];
    int _count;
    int _activeCount;

    SpatialHashGrid _grid;
    ObjectPool<HordeAgent> _pool;
    readonly List<int> _near = new List<int>();
    readonly List<int> _wantActive = new List<int>();
    DistanceOrder _byDistance;

    public int Count => _count;
    public int ActiveCount => _activeCount;

    void Awake()
    {
        _grid = new SpatialHashGrid(Mathf.Max(separationRadius, 4f), 4096);
        _byDistance = new DistanceOrder(this);
        _pool = new ObjectPool<HordeAgent>(
            () => Instantiate(prefab, transform),
            agent => agent.gameObject.SetActive(true),
            agent => agent.gameObject.SetActive(false),
            agent => Destroy(agent.gameObject),
            collectionCheck: false,
            defaultCapacity: maxActive,
            maxSize: maxActive * 2);
    }

    /// <summary>Adds a dormant record. It is promoted if the player is near.</summary>
    public void Add(Vector3 position)
    {
        Grow(_count + 1);
        float angle = Random.value * 360f;
        _members[_count] = new Member
        {
            Position = position,
            Heading = Quaternion.Euler(0f, angle, 0f) * Vector3.forward,
            Tier = Tier.Dormant,
            LastTick = Time.time,
            NextTick = Time.time + Random.value * dormantInterval
        };
        _count++;
    }

    /// <summary>Gives every agent within radius a goal at position, in every tier.</summary>
    public void Attract(Vector3 position, float radius)
    {
        _near.Clear();
        _grid.Query(position.x, position.z, radius, _near);
        for (int n = 0; n < _near.Count; n++)
        {
            int i = _near[n];
            if (i >= _count)
                continue; // the grid is from before records were removed this frame
            _members[i].Goal = position;
            _members[i].HasGoal = true;
            if (_members[i].View != null)
                _members[i].View.RaiseAttracted(position);
        }
    }

    internal void Kill(HordeAgent agent)
    {
        int i = agent.Index;
        if (i < 0 || i >= _count || _members[i].View != agent)
            return;

        agent.Simulation = null;
        agent.Index = -1;
        _members[i].View = null; // the corpse stays with the caller, not the pool
        _activeCount--;
        RemoveAt(i);
    }

    void Update()
    {
        if (player == null)
            return;

        // While active, the instance is the truth.
        for (int i = 0; i < _count; i++)
        {
            if (_members[i].View != null)
                _members[i].Position = _members[i].View.transform.position;
        }

        for (int i = 0; i < _count; i++)
        {
            _x[i] = _members[i].Position.x;
            _z[i] = _members[i].Position.z;
        }
        _grid.Build(_x, _z, _count);

        UpdateTiers();

        float now = Time.time;
        for (int i = 0; i < _count; i++)
        {
            ref Member m = ref _members[i];
            if (m.Tier == Tier.Active || now < m.NextTick)
                continue;

            Step(i, now - m.LastTick);
            m.LastTick = now;
            m.NextTick = now + (m.Tier == Tier.Simple ? simpleInterval : dormantInterval);
        }
    }

    void UpdateTiers()
    {
        Vector3 p = player.position;
        _wantActive.Clear();

        for (int i = 0; i < _count; i++)
        {
            ref Member m = ref _members[i];
            float dx = m.Position.x - p.x;
            float dz = m.Position.z - p.z;
            float d = Mathf.Sqrt(dx * dx + dz * dz);
            _distance[i] = d;

            float activeLimit = m.Tier == Tier.Active ? activeRadius + hysteresis : activeRadius;
            float simpleLimit = m.Tier != Tier.Dormant ? simpleRadius + hysteresis : simpleRadius;

            if (d <= activeLimit)
            {
                if (m.Tier != Tier.Active)
                    _wantActive.Add(i);
            }
            else if (m.Tier == Tier.Active)
            {
                Demote(i, d <= simpleLimit ? Tier.Simple : Tier.Dormant);
            }
            else
            {
                m.Tier = d <= simpleLimit ? Tier.Simple : Tier.Dormant;
            }
        }

        // Nearest first, within the budget. The rest stay simple until there is room.
        _wantActive.Sort(_byDistance);
        for (int n = 0; n < _wantActive.Count; n++)
        {
            int i = _wantActive[n];
            if (_activeCount < maxActive)
                Promote(i);
            else
                _members[i].Tier = Tier.Simple;
        }
    }

    void Promote(int i)
    {
        ref Member m = ref _members[i];
        Vector3 position = m.Position;
        if (NavMesh.SamplePosition(position, out NavMeshHit hit, 4f, NavMesh.AllAreas))
            position = hit.position;

        HordeAgent view = _pool.Get();
        view.Simulation = this;
        view.Index = i;
        view.Place(position, Quaternion.LookRotation(m.Heading));

        m.View = view;
        m.Position = position;
        m.Tier = Tier.Active;
        _activeCount++;

        if (m.HasGoal)
            view.RaiseAttracted(m.Goal);
    }

    void Demote(int i, Tier tier)
    {
        ref Member m = ref _members[i];
        HordeAgent view = m.View;
        m.Position = view.transform.position;
        m.Heading = view.transform.forward;
        view.Simulation = null;
        view.Index = -1;
        _pool.Release(view);

        m.View = null;
        m.Tier = tier;
        m.LastTick = Time.time;
        m.NextTick = Time.time + Random.value * (tier == Tier.Simple ? simpleInterval : dormantInterval);
        _activeCount--;
    }

    void Step(int i, float dt)
    {
        ref Member m = ref _members[i];

        if (m.HasGoal)
        {
            Vector3 to = m.Goal - m.Position;
            to.y = 0f;
            if (to.magnitude <= arriveRadius)
                m.HasGoal = false;
            else
                m.Heading = to.normalized;
        }
        else
        {
            float turn = Random.Range(-wanderTurn, wanderTurn) * dt;
            m.Heading = Quaternion.Euler(0f, turn, 0f) * m.Heading;
        }

        Vector3 move = m.Heading * speed;

        // Light separation for simple agents, so a converging group does not collapse into one point.
        if (m.Tier == Tier.Simple)
        {
            _near.Clear();
            _grid.Query(m.Position.x, m.Position.z, separationRadius, _near);
            for (int n = 0; n < _near.Count && n < 6; n++)
            {
                int j = _near[n];
                if (j == i || j >= _count)
                    continue;
                Vector3 away = m.Position - _members[j].Position;
                away.y = 0f;
                float distance = away.magnitude;
                if (distance > 1e-3f)
                    move += away / distance * (1f - distance / separationRadius) * speed;
            }
        }

        m.Position += move * dt;
    }

    void RemoveAt(int i)
    {
        int last = _count - 1;
        _members[i] = _members[last];
        _members[last] = default;
        if (_members[i].View != null)
            _members[i].View.Index = i;
        _count--;
    }

    void Grow(int needed)
    {
        if (_members.Length >= needed)
            return;
        int size = Mathf.Max(needed, _members.Length * 2);
        System.Array.Resize(ref _members, size);
        System.Array.Resize(ref _x, size);
        System.Array.Resize(ref _z, size);
        System.Array.Resize(ref _distance, size);
    }

    sealed class DistanceOrder : IComparer<int>
    {
        readonly HordeSimulation _owner;
        public DistanceOrder(HordeSimulation owner) => _owner = owner;
        public int Compare(int a, int b) => _owner._distance[a].CompareTo(_owner._distance[b]);
    }

    void OnDrawGizmosSelected()
    {
        for (int i = 0; i < _count; i++)
        {
            Gizmos.color = _members[i].Tier switch
            {
                Tier.Active => Color.red,
                Tier.Simple => Color.yellow,
                _ => Color.gray
            };
            Gizmos.DrawCube(_members[i].Position + Vector3.up, Vector3.one * 0.4f);
        }
    }
}
```

The comparer is a class held in a field, so sorting the candidates every frame does not allocate a delegate.

!!! warning "Common pitfalls"

    Without hysteresis, an agent on the active boundary is promoted and demoted every frame, and its instance flickers in and out of the pool.

    A pooled instance keeps the state of its last use: health, animator state, brain state, perception memory. Reset all of it on promotion, as the [object pooling](../architecture/pooling.md) page describes.

    Simple and dormant agents walk through walls. If the player can see further than **Active Radius**, they see it happen. Raise the radius, or hide distant agents with fog, darkness, or [fog of war and vision](../rendering/vision.md).

    A dead active agent that does not call `Kill` is demoted when the player leaves, and its record walks off again. Call it from the death handler.

    Record indices change when another record is removed, because removal swaps the last record in. Hold the `HordeAgent`, not an index.
