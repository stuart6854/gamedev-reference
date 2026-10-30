---
engine: Unity
version: 6+
package: AI Navigation 2.x
uses:
  - name: Top-down survival
    text: Zombies that surround a car or a barricaded house instead of piling up on one corner.
  - name: Strategy and tactics
    text: Units that attack a building from every side, each from its own spot.
  - name: Melee action
    text: Enemies that spread round a large boss or a big player character.
---

# Large targets

Walking up to something much bigger than the agent: a vehicle, a building, a big monster. `SetDestination(target.position)` aims at the centre, which is usually inside the target, often in a hole carved out of the NavMesh, and the same for every attacker. Measure to the target's surface instead, and hand each attacker its own slot round it.

## What goes wrong with the centre

- **The centre is not on the mesh.** A target that carves, or sits on unwalkable ground, has no NavMesh under its middle. The agent goes to the nearest point the pathfinder finds, which can be on the far side, or round a wall.
- **Stopping distance is measured from the centre.** A stopping distance that suits a car's side stops short at its front, and never arrives at a long bus.
- **Everyone takes the same side.** Every path from one direction ends at the same nearest point. The crowd stacks there, and agents at the back push and never reach.

## Distance to the surface

`Collider.ClosestPoint` gives the point on a collider nearest a position. It works for box, sphere, and capsule colliders, and convex mesh colliders. For a non-convex mesh collider, use its `bounds` instead.

```csharp
using UnityEngine;

public static class Surface
{
    public static Vector3 ClosestPoint(Collider[] colliders, Vector3 from)
    {
        Vector3 best = from;
        float bestDistance = float.MaxValue;
        foreach (Collider c in colliders)
        {
            if (c == null || !c.enabled)
                continue;

            Vector3 p = c is MeshCollider mesh && !mesh.convex ? c.bounds.ClosestPoint(from) : c.ClosestPoint(from);
            float d = (p - from).sqrMagnitude;
            if (d < bestDistance)
            {
                bestDistance = d;
                best = p;
            }
        }
        return best;
    }

    /// <summary>Distance on the ground plane, so a tall target's top does not count.</summary>
    public static float FlatDistance(Collider[] colliders, Vector3 from)
    {
        Vector3 p = ClosestPoint(colliders, from) - from;
        p.y = 0f;
        return p.magnitude;
    }
}
```

`ClosestPoint` returns the input position when it is inside the collider. Then the distance is 0, which reads as in reach. That is usually right.

The attack check becomes `Surface.FlatDistance(colliders, agent.position) <= reach`, not a distance to `target.position`.

## Attack slots

A component on the large target. It holds a ring of points round the target's surface, a little way out, and gives each attacker the nearest free one. The points are worked out when asked for, so they follow a moving target.

```csharp
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;

/// <summary>
/// Spots round a large target, one attacker each.
/// </summary>
public class AttackSlots : MonoBehaviour
{
    [SerializeField] Collider[] colliders;
    [Tooltip("Optional. Hand-placed spots. When empty, slots are spread round the colliders.")]
    [SerializeField] Transform[] authored;
    [SerializeField, Min(1)] int slotCount = 8;
    [Tooltip("From the surface to the attacker's centre. At least the agent radius.")]
    [SerializeField] float standOff = 0.7f;
    [SerializeField] float sampleRadius = 1.5f;

    readonly Dictionary<object, int> _owner = new Dictionary<object, int>();
    readonly HashSet<int> _used = new HashSet<int>();

    public Collider[] Colliders => colliders;
    int Count => authored != null && authored.Length > 0 ? authored.Length : slotCount;

    /// <summary>Takes the free slot nearest to from. False when all are taken or none is on the mesh.</summary>
    public bool TryReserve(object who, Vector3 from, out Vector3 point)
    {
        Release(who);

        int best = -1;
        float bestDistance = float.MaxValue;
        point = default;
        for (int i = 0; i < Count; i++)
        {
            if (_used.Contains(i) || !TrySlotPoint(i, out Vector3 p))
                continue;
            float d = (p - from).sqrMagnitude;
            if (d < bestDistance)
            {
                bestDistance = d;
                best = i;
                point = p;
            }
        }

        if (best < 0)
            return false;
        _used.Add(best);
        _owner[who] = best;
        return true;
    }

    /// <summary>Where the reserved slot is now. Call again as the target moves.</summary>
    public bool TryGetPoint(object who, out Vector3 point)
    {
        point = default;
        return _owner.TryGetValue(who, out int slot) && TrySlotPoint(slot, out point);
    }

    public void Release(object who)
    {
        if (_owner.TryGetValue(who, out int slot))
        {
            _used.Remove(slot);
            _owner.Remove(who);
        }
    }

    /// <summary>The nearest point on the mesh beside the surface, for attackers without a slot.</summary>
    public bool TryApproachPoint(Vector3 from, out Vector3 point)
    {
        Vector3 surface = Surface.ClosestPoint(colliders, from);
        Vector3 away = from - surface;
        away.y = 0f;
        Vector3 direction = away.sqrMagnitude > 0.0001f ? away.normalized : -transform.forward;
        return Sample(surface + direction * standOff, out point);
    }

    bool TrySlotPoint(int index, out Vector3 point)
    {
        if (authored != null && authored.Length > 0)
            return Sample(authored[index].position, out point);

        Bounds bounds = WorldBounds();
        float angle = (index + 0.5f) / slotCount * 360f;
        Vector3 direction = Quaternion.Euler(0f, angle, 0f) * transform.forward;

        // From a point well outside, the closest point on the colliders is on the side facing that way.
        Vector3 far = bounds.center + direction * (bounds.extents.magnitude + 1f);
        Vector3 surface = Surface.ClosestPoint(colliders, far);
        Vector3 candidate = surface + direction * standOff;
        candidate.y = bounds.min.y;
        return Sample(candidate, out point);
    }

    bool Sample(Vector3 position, out Vector3 point)
    {
        bool found = NavMesh.SamplePosition(position, out NavMeshHit hit, sampleRadius, NavMesh.AllAreas);
        point = found ? hit.position : position;
        return found;
    }

    Bounds WorldBounds()
    {
        var bounds = new Bounds(transform.position, Vector3.zero);
        bool first = true;
        foreach (Collider c in colliders)
        {
            if (c == null)
                continue;
            if (first)
                bounds = c.bounds;
            else
                bounds.Encapsulate(c.bounds);
            first = false;
        }
        return bounds;
    }
}
```

In the attacker's chase state:

```csharp
// On entering the state:
if (!slots.TryReserve(this, transform.position, out Vector3 point))
    slots.TryApproachPoint(transform.position, out point); // all taken: wait at the nearest point
agent.SetDestination(point);

// Every 0.25 seconds or so, for a moving target:
if (slots.TryGetPoint(this, out Vector3 current) && (current - agent.destination).sqrMagnitude > 0.5f * 0.5f)
    agent.SetDestination(current);

// In reach:
bool inReach = Surface.FlatDistance(slots.Colliders, transform.position) <= reach;

// On leaving the state, on death, and in OnDisable:
slots.Release(this);
```

- Spread slots, not more attackers. With eight slots taken, the ninth zombie waits behind, which reads as a crowd. Ask again when one is released.
- Even angles give side centres and corners on a box. For a long target, such as a bus or a wall, place **Authored** slot transforms along it instead.
- A slot whose `SamplePosition` lands on a different floor or across a wall passes the check and fails the path. When the agent's path comes back partial, release it and take another.
- A target with a `NavMeshObstacle` that carves leaves a margin of the agent radius round the hole. Keep **Stand Off** and **Sample Radius** above that.

## Large agents

The other way round: an agent too big for the mesh. A `NavMeshSurface` bakes for one **Agent Type**, with its radius and height. A tank on a mesh baked for people cuts corners through walls and fits through doors. Add an agent type for it in **Window → AI → Navigation**, add a second `NavMeshSurface` for that type, and bake both. Doors that are too narrow for the big type leave a gap in its mesh, which is what you want.

!!! warning "Common pitfalls"

    `SetDestination` to a point inside a carved hole sends the agent to the nearest edge the pathfinder finds, which can be the far side. Sample a point beside the surface yourself.

    `Collider.ClosestPoint` does not support non-convex mesh colliders. Use their bounds, or add a simpler box collider for the AI.

    A stopping distance tuned on a small target makes agents stop short of, or walk into, a large one. Measure reach to the surface.

    Not releasing slots when an attacker dies leaves the ring full of ghosts. Release in `OnDisable` as well.
