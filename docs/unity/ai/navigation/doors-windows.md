---
engine: Unity
version: 6+
package: AI Navigation 2.x
uses:
  - name: Top-down survival
    text: Survivors open doors and climb through windows, zombies only get in by breaking them.
  - name: Stealth
    text: Guards who open doors on patrol, and doors the player locks behind them.
  - name: Companions and NPCs
    text: Followers who take the window when the door is locked.
---

# Doors and windows

An opening with a state, open, closed, locked, or broken, that agents path through. A `Portal` component switches its [links](index.md#openings-are-links) to match its state, and a `PortalTraverser` on each agent opens, climbs, or breaks its way through when its path reaches one. Choosing to break, and what that should cost, is [breakable obstacles](breakable.md).

## How it fits together

| Piece | Job |
| --- | --- |
| Baked gap | A **NavMesh Modifier Volume** set to **Not Walkable** across the doorway or window, so the mesh on each side is separate. |
| `NavMeshLink`s | Up to three across the gap: **pass** (open or broken), **open** (closed, needs opening), **break** (closed or locked, needs breaking). |
| `Portal` | Holds the state. Switches the links with `activated`. Raises `Changed` for the door's visuals and sound. |
| [Agent profile](index.md#agent-profile) | Which link areas the agent may use and what they cost it. |
| `PortalTraverser` | Turns off automatic link traversal. When the agent reaches a link, does what the portal's state needs, then crosses. |

| State | Pass | Open | Break |
| --- | --- | --- | --- |
| Open | on | off | off |
| Closed | off | on | on |
| Locked | off | off | on |
| Broken | on | off | off |

The pathfinder only sees links that are on and in the agent's area mask. A survivor with **Door** in its mask and **Breakable** out paths through a closed door and round a locked one. A zombie with the opposite mask breaks closed and locked doors alike.

## Portal

```csharp
using System;
using Unity.AI.Navigation;
using UnityEngine;

public enum PortalState { Open, Closed, Locked, Broken }

/// <summary>
/// A door, window, or weak wall. Switches its NavMesh links to match its state.
/// </summary>
[DisallowMultipleComponent]
public class Portal : MonoBehaviour
{
    [SerializeField] PortalState state = PortalState.Closed;

    [Tooltip("On when Open or Broken. Walkable area for a doorway, Vault for a window.")]
    [SerializeField] NavMeshLink passLink;
    [Tooltip("On when Closed. Door area, or Vault for a window.")]
    [SerializeField] NavMeshLink openLink;
    [Tooltip("On when Closed or Locked. Breakable area. Leave empty if it cannot be broken.")]
    [SerializeField] NavMeshLink breakLink;

    [SerializeField] bool isWindow;
    [SerializeField] float openSeconds = 0.8f;
    [Tooltip("Optional. When it dies, the portal is Broken.")]
    [SerializeField] Health health;

    public PortalState State => state;
    public bool IsWindow => isWindow;
    public float OpenSeconds => openSeconds;
    public Health Health => health;
    public NavMeshLink BreakLink => breakLink;
    public bool IsPassable => state == PortalState.Open || state == PortalState.Broken;

    public event Action<Portal> Changed;

    bool _linksDirty;

    void OnEnable()
    {
        if (health != null)
            health.Died += OnBroken;
        ApplyLinks();
    }

    void OnDisable()
    {
        if (health != null)
            health.Died -= OnBroken;
    }

    public bool TryOpen()
    {
        if (state != PortalState.Closed)
            return false;
        SetState(PortalState.Open);
        return true;
    }

    public bool TryClose()
    {
        if (state != PortalState.Open)
            return false;
        SetState(PortalState.Closed);
        return true;
    }

    public void SetLocked(bool locked)
    {
        if (locked && state == PortalState.Closed)
            SetState(PortalState.Locked);
        else if (!locked && state == PortalState.Locked)
            SetState(PortalState.Closed);
    }

    public void SetState(PortalState next)
    {
        if (state == next)
            return;
        state = next;
        _linksDirty = true;
        Changed?.Invoke(this);
    }

    void OnBroken() => SetState(PortalState.Broken);

    void LateUpdate()
    {
        // Switching off the link an agent is standing on can drop it mid-crossing. Wait until it is clear.
        if (_linksDirty && !Occupied(passLink) && !Occupied(openLink) && !Occupied(breakLink))
            ApplyLinks();
    }

    void ApplyLinks()
    {
        _linksDirty = false;
        SetActive(passLink, IsPassable);
        SetActive(openLink, state == PortalState.Closed);
        SetActive(breakLink, state == PortalState.Closed || state == PortalState.Locked);
    }

    static bool Occupied(NavMeshLink link) => link != null && link.occupied;

    static void SetActive(NavMeshLink link, bool on)
    {
        if (link != null)
            link.activated = on;
    }
}
```

- `activated` false keeps the link but stops any path using it. Switching it does not move or rebuild anything, so it is cheap.
- The state changes at once. Only the links wait. An agent arriving in the meantime reads the state, not the links, so it still does the right thing.
- Visuals listen to `Changed`: swing the door, play the sound, turn off the closed door's collider when it is open or broken.

## Traverser

`autoTraverseOffMeshLink` off makes the agent stop at the start of every link until `CompleteOffMeshLink` is called. The traverser moves it across itself, after opening or breaking what is in the way. Crossing by moving the transform and then calling `CompleteOffMeshLink` is the pattern Unity's own link examples use.

```csharp
using System;
using System.Collections;
using Unity.AI.Navigation;
using UnityEngine;
using UnityEngine.AI;

/// <summary>
/// Crosses NavMesh links by hand: opens doors, climbs windows, and breaks what the profile allows.
/// </summary>
[RequireComponent(typeof(NavMeshAgent), typeof(NavProfileUser))]
public class PortalTraverser : MonoBehaviour
{
    [SerializeField] float vaultSeconds = 0.7f;
    [SerializeField] float vaultHeight = 0.6f;
    [SerializeField] float hitInterval = 0.5f;
    [SerializeField] DamageType breakDamageType;

    /// <summary>Opening, breaking, or crossing started. For animation.</summary>
    public event Action<Portal, string> Acting;
    /// <summary>The path led to an opening this agent cannot pass. The agent has stopped.</summary>
    public event Action<Portal> Blocked;

    public bool IsTraversing => _routine != null;

    NavMeshAgent _agent;
    NavProfile _profile;
    Coroutine _routine;

    void Awake()
    {
        _agent = GetComponent<NavMeshAgent>();
        _profile = GetComponent<NavProfileUser>().Profile;
        _agent.autoTraverseOffMeshLink = false;
    }

    void OnDisable() => _routine = null; // coroutines stop with the component

    void Update()
    {
        if (_routine == null && _agent.isOnOffMeshLink)
            _routine = StartCoroutine(Traverse(_agent.currentOffMeshLinkData));
    }

    IEnumerator Traverse(OffMeshLinkData data)
    {
        // Links made by a NavMeshLink component report it as their owner.
        var link = data.owner as NavMeshLink;
        Portal portal = link != null ? link.GetComponentInParent<Portal>() : null;

        if (portal != null && !portal.IsPassable)
        {
            if (portal.State == PortalState.Closed && _profile.CanOpenDoors)
            {
                Acting?.Invoke(portal, "open");
                yield return Face(data.endPos, portal.OpenSeconds);
                portal.TryOpen(); // fails harmlessly if someone else opened or locked it meanwhile
            }

            if (!portal.IsPassable && _profile.CanBreak && portal.Health != null)
            {
                Acting?.Invoke(portal, "break");
                yield return Break(portal, data.endPos);
            }

            if (!portal.IsPassable)
            {
                GiveUp(portal, data);
                yield break;
            }
        }

        bool vault = portal != null && portal.IsWindow;
        if (vault && !_profile.CanVault)
        {
            GiveUp(portal, data);
            yield break;
        }

        Acting?.Invoke(portal, vault ? "vault" : "cross");
        yield return Cross(data, vault);
        _agent.CompleteOffMeshLink();
        _routine = null;
    }

    IEnumerator Break(Portal portal, Vector3 lookAt)
    {
        var hit = new DamageInfo
        {
            Amount = _profile.BreakDamagePerSecond * hitInterval,
            Type = breakDamageType,
            Source = gameObject,
            Point = portal.transform.position,
            Normal = (transform.position - portal.transform.position).normalized
        };

        while (!portal.IsPassable && !portal.Health.IsDead)
        {
            yield return Face(lookAt, hitInterval);
            portal.Health.ApplyDamage(hit);
        }
    }

    IEnumerator Cross(OffMeshLinkData data, bool vault)
    {
        Vector3 start = transform.position;
        Vector3 end = data.endPos + Vector3.up * _agent.baseOffset;
        float duration = vault ? vaultSeconds : Mathf.Max(0.05f, Vector3.Distance(start, end) / _agent.speed);
        Face(end);

        for (float t = 0f; t < 1f; t += Time.deltaTime / duration)
        {
            Vector3 p = Vector3.Lerp(start, end, t);
            if (vault)
                p.y += vaultHeight * 4f * t * (1f - t); // a parabola peaking at half way
            transform.position = p;
            yield return null;
        }
        transform.position = end;
    }

    IEnumerator Face(Vector3 point, float seconds)
    {
        Face(point);
        yield return new WaitForSeconds(seconds);
    }

    void Face(Vector3 point)
    {
        Vector3 flat = point - transform.position;
        flat.y = 0f;
        if (flat.sqrMagnitude > 0.0001f)
            transform.rotation = Quaternion.LookRotation(flat);
    }

    void GiveUp(Portal portal, OffMeshLinkData data)
    {
        // Warp takes the agent off the link and clears its path. The brain decides what next.
        _agent.Warp(data.startPos);
        _routine = null;
        Blocked?.Invoke(portal);
    }

    /// <summary>For the brain: stop whatever the traverser is doing, such as a break the target walked away from.</summary>
    public void Abort()
    {
        if (_routine == null)
            return;
        StopCoroutine(_routine);
        _routine = null;
        if (_agent.isOnOffMeshLink)
            _agent.Warp(_agent.currentOffMeshLinkData.startPos);
    }
}
```

- `Health`, `DamageInfo`, and `DamageType` are from [health](../../systems/health.md). `IsDead` and `ApplyDamage` are on that `Health`.
- The state is checked again on arrival. The path was planned when the door was closed; by the time the agent gets there, someone may have opened, locked, or broken it.
- `Blocked` is for the [state machine](../../architecture/state-machines.md): pick another goal, or try the [stuck recovery](stuck.md#recovery). Do not just call `SetDestination` again in the same frame. The portal's links may not have caught up yet, and the same path comes back.
- The traverser handles every link, not only portals. A plain jump link is crossed in a straight line. Add an arc for links in the **Jump** area if you use them.
- While the agent is on a link, its `NavMeshAgent` does not move it. The brain should treat `IsTraversing` as busy and not issue new destinations until it ends.

## Setup

1. Model the door as its own object, not part of the wall mesh. Exclude it from the bake: put it on a layer the `NavMeshSurface`'s **Include Layers** leaves out, or give it a **NavMesh Modifier** with **Mode** set to **Remove Object**.
2. Add a **NavMesh Modifier Volume** across the doorway, set to **Not Walkable**, a little deeper than the wall. Bake. The mesh now stops on both sides.
3. Add a child object with a **NavMesh Link** for each link the opening needs. Set **Start Point** and **End Point** on the mesh either side, **Width** to the doorway width, **Bidirectional** on, and the **Area Type** from the table above.
4. Add `Portal` to the door, assign the links, and set the starting state. For a breakable door, add a `Health` and assign it.
5. For a window, tick **Is Window**, put the pass link in the **Vault** area, and put the open link in **Vault** too with **Cost Override** set higher than the pass link, so agents that cannot climb never path to it.
6. Add `PortalTraverser` to every agent with a `NavProfileUser`.

!!! warning "Common pitfalls"

    A door included in the bake fills the gap when closed and leaves it filled when open. Bake without it.

    A link whose ends do not touch the NavMesh is never used. In the Scene view, the link's ends show as circles. Move them onto the mesh, or turn up the agent type's **Step Height**.

    With **Auto Traverse Off Mesh Link** on, which is the default, the agent slides through closed doors on its own. The traverser turns it off in `Awake`.

    Switching a link off while an agent stands on it can leave the agent stuck on the link. `Portal` waits for `occupied` to clear.

    An agent that is not allowed an area never paths through it, so it walks to the long way round, or reports no path at all. That is the mask working. Check the profile before the portal.
