---
engine: Unity
version: 6+
package: AI Navigation 2.x
uses:
  - name: Top-down survival
    text: Zombies that break through a door when it is quicker than the long way round, and barricades that hold them.
  - name: Hordes and crowds
    text: A crowd that piles onto the one weak wall instead of circling the base.
  - name: Base building
    text: Player walls with health, which raiders break when there is no gate open.
---

# Breakable obstacles

Agents that break their way through: a door, a weak wall, or a barricade. There are two cases, and they need different tools.

| Case | The obstacle is | How the agent decides |
| --- | --- | --- |
| **In an opening** | A [portal](doors-windows.md) with a break link. Doors, windows, weak wall sections. | The pathfinder. The break link has a cost, so breaking wins when it is cheaper than walking round. |
| **In the open** | A carved `NavMeshObstacle` with health. A barricade across a street, a car wreck, a wall the player built. | After the path. No path goes through a carved obstacle, so a partial path is the sign to look for one to break. |

The [doors and windows](doors-windows.md) page has the `Portal` and the `PortalTraverser` that does the breaking. This page sets the costs, plans with or without breaking, and handles obstacles outside openings.

## Cost

The pathfinder compares distances. To compare breaking with walking, turn the break time into distance: the time to break, times the speed the agent walks. A door with 20 health against 10 damage per second takes 2 seconds, which at 3.5 metres per second is 7 metres. A path through it is about 7.5 metres longer than its straight line. If the way round is 40 metres, the agent breaks the door.

The link's cost is its length times its cost override, so the override is that distance divided by the link's length. `BreakCost` keeps it up to date as the door takes damage.

```csharp
using Unity.AI.Navigation;
using UnityEngine;

/// <summary>
/// Sets a portal's break link cost from its remaining health, as walking distance.
/// </summary>
[RequireComponent(typeof(Portal))]
public class BreakCost : MonoBehaviour
{
    [Tooltip("Damage per second of a typical breaker.")]
    [SerializeField] float referenceDamagePerSecond = 10f;
    [Tooltip("Walking speed of a typical breaker.")]
    [SerializeField] float referenceSpeed = 3.5f;

    Portal _portal;
    bool _dirty;

    void Awake() => _portal = GetComponent<Portal>();

    void OnEnable()
    {
        if (_portal.Health != null)
            _portal.Health.HealthChanged += OnHealthChanged;
        _dirty = true;
    }

    void OnDisable()
    {
        if (_portal.Health != null)
            _portal.Health.HealthChanged -= OnHealthChanged;
    }

    void OnHealthChanged(float current, float max) => _dirty = true;

    void LateUpdate()
    {
        NavMeshLink link = _portal.BreakLink;
        // Changing a link under an agent can drop it. Update when nobody is on it.
        if (!_dirty || link == null || link.occupied || _portal.Health == null)
            return;
        _dirty = false;

        // startPoint and endPoint are local, and the link ignores scale, so their distance is the world length.
        float length = Mathf.Max(0.1f, Vector3.Distance(link.startPoint, link.endPoint));
        float seconds = _portal.Health.Current / Mathf.Max(0.01f, referenceDamagePerSecond);
        link.costModifier = (length + seconds * referenceSpeed) / length;
    }
}
```

- The override is per link, so every agent sees the same cost. The profile still decides who may use it, through the **Breakable** area in its mask.
- The cost assumes one breaker. Ten zombies at one door break it ten times faster. For a horde, divide the seconds by the number of agents already on the link, or by an expected crowd size.
- If the link uses **Start Transform** and **End Transform**, measure the distance between those instead.
- A barricade the player repairs is a `Locked` portal whose health goes back up. The cost follows it.

## Plan with or without breaking

Some agents break anything cheaper. Some only break when there is no other way in, so a zombie walks round the house to the open back door rather than through the front. `BreakPlanner` plans with an area mask chosen for the moment, using `NavMesh.CalculatePath` and the agent's own area costs, then hands the path to the agent.

```csharp
using UnityEngine;
using UnityEngine.AI;

public enum BreakMode { Never, WhenCheaper, LastResort }

/// <summary>
/// Plans paths that use break links never, when cheaper, or only when nothing else reaches.
/// Falls back to a breakable obstacle near the end of a partial path.
/// </summary>
[RequireComponent(typeof(NavMeshAgent))]
public class BreakPlanner : MonoBehaviour
{
    [SerializeField] BreakMode mode = BreakMode.LastResort;
    [SerializeField] float sampleRadius = 2f;
    [SerializeField] float obstacleSearchRadius = 3f;
    [SerializeField] LayerMask obstacleLayers = ~0;

    /// <summary>Set when the plan is to break a carved obstacle at the end of a partial path.</summary>
    public Breakable Obstacle { get; private set; }

    NavMeshAgent _agent;
    NavMeshPath _path;
    int _baseMask;
    int _breakBit;
    readonly Collider[] _hits = new Collider[16];

    void Awake()
    {
        _agent = GetComponent<NavMeshAgent>();
        _path = new NavMeshPath();
        int area = NavMesh.GetAreaFromName("Breakable");
        _breakBit = area >= 0 ? 1 << area : 0;
    }

    // After the profile has set the mask in OnEnable.
    void Start() => _baseMask = _agent.areaMask;

    /// <summary>False when there is no way to the target at all, even by breaking.</summary>
    public bool MoveTo(Vector3 target)
    {
        Obstacle = null;
        if (!NavMesh.SamplePosition(target, out NavMeshHit hit, sampleRadius, _baseMask))
            return false;
        target = hit.position;

        bool mayBreak = (_baseMask & _breakBit) != 0 && mode != BreakMode.Never;
        int without = _baseMask & ~_breakBit;
        int with = _baseMask | _breakBit;

        int mask = mode == BreakMode.WhenCheaper && mayBreak ? with : without;
        bool complete = Plan(target, mask);

        if (!complete && mode == BreakMode.LastResort && mayBreak)
        {
            mask = with;
            complete = Plan(target, mask);
        }

        if (_path.status == NavMeshPathStatus.PathInvalid)
            return false;

        if (!complete && mayBreak)
            Obstacle = FindObstacle(target);

        // The agent re-plans with its own mask when its path goes stale, so give it the one used here.
        _agent.areaMask = mask;
        return _agent.SetPath(_path);
    }

    bool Plan(Vector3 target, int mask)
    {
        var filter = new NavMeshQueryFilter { agentTypeID = _agent.agentTypeID, areaMask = mask };
        for (int i = 0; i < 32; i++)
            filter.SetAreaCost(i, _agent.GetAreaCost(i));

        return NavMesh.CalculatePath(transform.position, target, filter, _path)
            && _path.status == NavMeshPathStatus.PathComplete;
    }

    Breakable FindObstacle(Vector3 target)
    {
        Vector3[] corners = _path.corners;
        if (corners.Length == 0)
            return null;
        Vector3 end = corners[corners.Length - 1];

        int count = Physics.OverlapSphereNonAlloc(end, obstacleSearchRadius, _hits, obstacleLayers, QueryTriggerInteraction.Ignore);
        Breakable best = null;
        float bestDistance = float.MaxValue;
        for (int i = 0; i < count; i++)
        {
            Breakable candidate = _hits[i].GetComponentInParent<Breakable>();
            if (candidate == null || candidate.IsBroken)
                continue;

            // Prefer the one between the path's end and the target.
            float distance = Vector3.Distance(_hits[i].ClosestPoint(target), target);
            if (distance < bestDistance)
            {
                bestDistance = distance;
                best = candidate;
            }
        }
        return best;
    }
}
```

- `CalculatePath` returns true for a partial path too. Check `status`. A partial path ends at the closest reachable point.
- With **Last Resort**, the first plan leaves break links out. Only when that does not reach is the second plan, with them, used.
- `areaMask` is set on the agent with the path. Leaving the full mask there lets the agent's own re-plan pick a break link the planner had ruled out.
- Plan again when something changes: a portal opens, an obstacle breaks, or the target moves far. Not every frame. `CalculatePath` runs on the main thread.

## Obstacles in the open

A carved obstacle with health. While it stands, the mesh under it is gone and no path crosses it. When it breaks, the obstacle switches off, and the hole closes on the next carving update.

```csharp
using System;
using UnityEngine;
using UnityEngine.AI;

/// <summary>
/// A barricade or wreck agents can break. Carves the NavMesh until its health runs out.
/// </summary>
[RequireComponent(typeof(Health))]
public class Breakable : MonoBehaviour
{
    [SerializeField] NavMeshObstacle obstacle;
    [SerializeField] GameObject intact;
    [SerializeField] GameObject rubble;

    public Health Health { get; private set; }
    public bool IsBroken { get; private set; }
    public event Action<Breakable> Broken;

    void Awake() => Health = GetComponent<Health>();
    void OnEnable() => Health.Died += OnDied;
    void OnDisable() => Health.Died -= OnDied;

    void OnDied()
    {
        IsBroken = true;
        if (obstacle != null)
            obstacle.enabled = false;
        if (intact != null)
            intact.SetActive(false);
        if (rubble != null)
            rubble.SetActive(true);
        Broken?.Invoke(this);
    }
}
```

In the brain, after `MoveTo`:

```csharp
// In a chase state's Tick: the agent is at the end of a partial path, next to the obstacle.
Breakable obstacle = planner.Obstacle;
if (obstacle != null && !obstacle.IsBroken && !agent.pathPending && agent.remainingDistance <= agent.stoppingDistance)
{
    // Hit obstacle.Health the same way the attack state hits the player.
    // On obstacle.Broken, call planner.MoveTo(target) again.
}
```

- Give the obstacle **Carve** on, with **Carve Only Stationary** on, so a pushed wreck does not re-carve every frame.
- Rubble that agents should walk over must not carve. Rubble that slows them can sit in an area with a higher cost, through a **NavMesh Modifier Volume** baked into the mesh.
- An obstacle you place at runtime, such as a player wall, carves immediately. Agents already on paths through that spot find out when their path goes stale. Plan again on the wall's placement event for agents nearby.

## Setup

1. Add the **Breakable** area, and tick it in the [profile](index.md#agent-profile) of agents that may break.
2. For openings: a `Portal` with a `Health` and a break link, then `BreakCost` on the same object.
3. For obstacles in the open: a `NavMeshObstacle` with **Carve**, a collider on a layer in the planner's **Obstacle Layers**, a `Health`, and `Breakable`.
4. Add `BreakPlanner` to agents that break. The brain calls `planner.MoveTo(target)` instead of `agent.SetDestination(target)`.

!!! warning "Common pitfalls"

    A break link with no cost override, or one left at the area cost, is as cheap as walking. Every zombie goes through every door.

    The pathfinder never sees a carved obstacle as a way through. Breaking one has to come from the partial path, not from the cost.

    `CalculatePath` with the default filter ignores the agent's own area costs. Copy them into the `NavMeshQueryFilter`.

    An agent whose mask still allows **Breakable** after a last-resort plan without it can re-plan straight through the door on its own. Set the mask with the path.

    A cost update while an agent is breaking the door can rebuild the link under it. `BreakCost` waits until the link is clear.
