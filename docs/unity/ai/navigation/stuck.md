---
engine: Unity
version: 6+
package: AI Navigation 2.x
uses:
  - name: Hordes and crowds
    text: Zombies that queue at a doorway instead of jamming it, and recover when pushed off the mesh.
  - name: Companions and NPCs
    text: A follower that notices it is stuck and catches up out of sight.
  - name: Strategy and tactics
    text: Units that funnel through a gap one at a time.
---

# Stuck agents and chokepoints

`NavMeshAgent` reports a path, not progress. An agent can have a valid path and stand still forever: pushed against a wall by the crowd, pinned in a doorway by agents coming the other way, or knocked off the mesh by physics. This page notices that, works through a ladder of fixes, and keeps doorways from jamming in the first place.

## Why agents get stuck

| Cause | Sign | Fix |
| --- | --- | --- |
| Avoidance deadlock: two agents, or two groups, each giving way to the other | Both have paths, neither moves | Different **avoidance priorities**, a [chokepoint](#chokepoints) queue |
| Pushed off the mesh by physics or a knockback | `isOnNavMesh` false | Warp back to the last good position |
| The path's end is unreachable | `pathStatus` is `PathPartial` and the agent has arrived | Not stuck. Tell the brain the goal is unreachable. |
| A door locked after the path was planned | The [traverser](doors-windows.md#traverser) raises `Blocked` | Plan again, or pick another goal |
| A carved obstacle appeared on the path | Path goes stale, then re-plans | Usually fixes itself, a frame or two later |
| Destination off the mesh | The agent stops at the nearest point | Sample the destination with `NavMesh.SamplePosition` first |

## Detecting it

Measure progress over a window of time, not speed in one frame. Every agent stops for a moment now and then; a stuck one stops for seconds. Progress is the drop in remaining path distance, so a path that leads away round a wall still counts as progress.

```csharp
using System;
using UnityEngine;
using UnityEngine.AI;

/// <summary>
/// Notices an agent that has a path and is not getting closer, then tries repath, nudge, warp, and finally gives up.
/// </summary>
[RequireComponent(typeof(NavMeshAgent))]
public class StuckDetector : MonoBehaviour
{
    [SerializeField] float window = 1.5f;
    [Tooltip("Metres closer to the destination per window, below which the agent counts as stuck.")]
    [SerializeField] float minProgress = 0.4f;
    [SerializeField] float nudgeRadius = 2f;
    [SerializeField] float nudgeSeconds = 1f;
    [SerializeField] float warpSearchRadius = 3f;
    [Tooltip("Optional. Never warp while on screen.")]
    [SerializeField] Camera viewCamera;

    /// <summary>The attempt number, from 1. For debugging and barks.</summary>
    public event Action<int> Stuck;
    /// <summary>Every attempt failed. The agent's path has been cleared.</summary>
    public event Action GaveUp;
    /// <summary>The agent is at the end of a partial path.</summary>
    public event Action Unreachable;

    NavMeshAgent _agent;
    PortalTraverser _traverser;
    float _windowStart;
    float _startRemaining;
    Vector3 _lastValid;
    Vector3 _goal;
    float _nudgeUntil = -1f;
    int _attempts;

    void Awake()
    {
        _agent = GetComponent<NavMeshAgent>();
        _traverser = GetComponent<PortalTraverser>();
        _lastValid = transform.position;
    }

    void OnEnable() => ResetWindow();

    void Update()
    {
        if (!_agent.isOnNavMesh)
        {
            // Pushed off. Nothing else works until it is back.
            if (TryWarpNear(_lastValid))
                Resume();
            return;
        }

        if (NavMesh.SamplePosition(transform.position, out NavMeshHit here, 0.3f, _agent.areaMask))
            _lastValid = here.position;

        if (_nudgeUntil >= 0f && Time.time >= _nudgeUntil)
        {
            _nudgeUntil = -1f;
            _agent.SetDestination(_goal);
            ResetWindow();
            return;
        }

        bool busy = (_traverser != null && _traverser.IsTraversing) || _agent.isOnOffMeshLink;
        if (!_agent.hasPath || _agent.pathPending || _agent.isStopped || busy)
        {
            ResetWindow();
            return;
        }

        if (_agent.remainingDistance <= _agent.stoppingDistance)
        {
            if (_agent.pathStatus == NavMeshPathStatus.PathPartial)
                Unreachable?.Invoke();
            _attempts = 0;
            ResetWindow();
            return;
        }

        if (Time.time - _windowStart < window)
            return;

        float progress = _startRemaining - Remaining();
        if (progress < minProgress)
            Recover();
        else
            _attempts = 0;
        ResetWindow();
    }

    void Recover()
    {
        _attempts++;
        Stuck?.Invoke(_attempts);
        if (_nudgeUntil < 0f)
            _goal = _agent.destination;

        switch (_attempts)
        {
            case 1:
                // A fresh path often clears a stale corner or a link that changed.
                _agent.SetDestination(_goal);
                break;
            case 2:
                Vector3 offset = UnityEngine.Random.insideUnitSphere * nudgeRadius;
                offset.y = 0f;
                if (NavMesh.SamplePosition(transform.position + offset, out NavMeshHit nudge, nudgeRadius, _agent.areaMask))
                {
                    _agent.SetDestination(nudge.position);
                    _nudgeUntil = Time.time + nudgeSeconds;
                }
                break;
            case 3:
                if (!IsVisible() && TryWarpNear(_lastValid))
                    Resume();
                break;
            default:
                _attempts = 0;
                _agent.ResetPath();
                GaveUp?.Invoke();
                break;
        }
    }

    float Remaining()
    {
        // Infinity when the agent does not know the distance yet. Fall back to a straight line.
        float remaining = _agent.remainingDistance;
        return float.IsInfinity(remaining) ? Vector3.Distance(transform.position, _agent.destination) : remaining;
    }

    void ResetWindow()
    {
        _windowStart = Time.time;
        _startRemaining = _agent.isOnNavMesh && _agent.hasPath ? Remaining() : 0f;
    }

    bool TryWarpNear(Vector3 position)
    {
        if (!NavMesh.SamplePosition(position, out NavMeshHit hit, warpSearchRadius, _agent.areaMask))
            return false;
        return _agent.Warp(hit.position);
    }

    void Resume()
    {
        _nudgeUntil = -1f;
        if (_goal != Vector3.zero)
            _agent.SetDestination(_goal);
        ResetWindow();
    }

    bool IsVisible()
    {
        if (viewCamera == null)
            return false;
        Vector3 v = viewCamera.WorldToViewportPoint(transform.position);
        return v.z > 0f && v.x > -0.1f && v.x < 1.1f && v.y > -0.1f && v.y < 1.1f;
    }
}
```

- The window and the progress threshold set how patient it is. Shorter windows react faster and fire on every brief jostle. Start at 1.5 seconds and 0.4 metres for a 3.5 metre per second agent.
- A brain that stops the agent on purpose, to attack or to wait, sets `isStopped` or clears the path. The detector ignores both.
- `GaveUp` and `Unreachable` belong to the [state machine](../../architecture/state-machines.md). Pick a new goal, or switch to idle. Do not loop straight back to the same destination.
- Warping in view looks like a glitch. With **View Camera** set, the warp step is skipped on screen and the ladder moves on.

## Recovery

The ladder, cheapest first:

1. **Repath.** Most stalls are a stale path: a door changed, an obstacle moved, a corner the agent cut. A fresh `SetDestination` fixes them.
2. **Nudge.** Walk to a random nearby point for a second, then back to the goal. This breaks avoidance deadlocks, because the two agents stop facing each other.
3. **Warp.** Teleport to the last position that was on the mesh. Only off screen.
4. **Give up.** Clear the path and tell the brain.

Any progress resets the ladder.

## Chokepoints

A doorway one agent wide, with a crowd on both sides, deadlocks under local avoidance: each agent steers round the one in front, and none give way. A queue avoids that. Only so many agents may be in the doorway at once. The rest wait in line on their own side.

```csharp
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Lets a few agents through a narrow opening at a time. Others wait in line.
/// Put it on a trigger collider round the opening, with a kinematic Rigidbody.
/// </summary>
public class Chokepoint : MonoBehaviour
{
    [SerializeField, Min(1)] int capacity = 1;
    [SerializeField] float spacing = 0.9f;
    [SerializeField] float lineWidth = 0.4f;

    readonly List<object> _inside = new List<object>();
    readonly List<object> _queue = new List<object>();

    /// <summary>True: go through now. False: wait at WaitPoint and ask again.</summary>
    public bool Request(object who)
    {
        if (_inside.Contains(who))
            return true;

        bool first = _queue.Count == 0 || _queue[0] == who;
        if (_inside.Count < capacity && first)
        {
            _queue.Remove(who);
            _inside.Add(who);
            return true;
        }

        if (!_queue.Contains(who))
            _queue.Add(who);
        return false;
    }

    /// <summary>A place in line, on the side the agent is on.</summary>
    public Vector3 WaitPoint(object who, Vector3 from)
    {
        int place = Mathf.Max(0, _queue.IndexOf(who));
        float side = Vector3.Dot(from - transform.position, transform.forward) >= 0f ? 1f : -1f;
        float lateral = place % 2 == 0 ? lineWidth : -lineWidth; // zigzag, so the line is not single file
        return transform.position + transform.forward * side * spacing * (place + 1) + transform.right * lateral;
    }

    /// <summary>Through and out of the trigger.</summary>
    public void Exit(object who) => _inside.Remove(who);

    /// <summary>Changed goal, died, or disabled.</summary>
    public void Cancel(object who)
    {
        _inside.Remove(who);
        _queue.Remove(who);
    }
}
```

```csharp
using System.Collections;
using UnityEngine;
using UnityEngine.AI;

/// <summary>
/// Asks chokepoints for a turn when the agent walks into one.
/// </summary>
[RequireComponent(typeof(NavMeshAgent))]
public class ChokepointUser : MonoBehaviour
{
    [SerializeField] float pollInterval = 0.2f;

    NavMeshAgent _agent;
    Chokepoint _current;
    Coroutine _waiting;

    void Awake() => _agent = GetComponent<NavMeshAgent>();

    void OnDisable()
    {
        if (_current != null)
            _current.Cancel(this);
        _current = null;
        _waiting = null;
    }

    void OnTriggerEnter(Collider other)
    {
        if (_waiting != null || !other.TryGetComponent(out Chokepoint chokepoint))
            return;
        _current = chokepoint;
        if (!chokepoint.Request(this))
            _waiting = StartCoroutine(Wait(chokepoint, _agent.destination));
    }

    void OnTriggerExit(Collider other)
    {
        // A waiting agent may walk out to its place in line. It stays queued.
        if (_waiting == null && other.TryGetComponent(out Chokepoint chokepoint))
        {
            chokepoint.Exit(this);
            if (_current == chokepoint)
                _current = null;
        }
    }

    IEnumerator Wait(Chokepoint chokepoint, Vector3 goal)
    {
        var poll = new WaitForSeconds(pollInterval);
        while (!chokepoint.Request(this))
        {
            _agent.SetDestination(chokepoint.WaitPoint(this, transform.position));
            yield return poll;
        }
        _agent.SetDestination(goal);
        _waiting = null;
    }
}
```

- Trigger messages need a `Rigidbody` on one side. A kinematic one on the chokepoint is enough, and the agents can keep plain colliders.
- The brain must not send the agent elsewhere while it waits without calling `Cancel`, or the queue holds a place for an agent that left.
- Give the trigger the opening's width and about a metre each side. Larger and agents queue before they need to.

## Avoidance settings

Most jams are avoidance, and a few settings prevent many of them:

- **Avoidance Priority**, 0 to 99, default 50. A lower number is more important, and an agent ignores agents less important than itself. Equal priorities are what deadlock. Give each agent a slightly different one, such as `Random.Range(40, 60)`, and give important agents, such as a companion or a carrier, a lower number.
- **Radius.** Avoidance uses the agent's radius, not its collider. A radius much larger than the body jams doorways early. A smaller one lets bodies overlap.
- **Obstacle Avoidance Quality.** Lower quality is cheaper and less careful. For a large crowd, use **Low** and let the [crowd](../steering.md) or [horde](../horde.md) systems do the spacing.
- **Stopped agents are still obstacles.** An agent waiting in a doorway blocks it. Waiting spots belong to the side, as the chokepoint's line does.

!!! warning "Common pitfalls"

    Checking `velocity` for zero in one frame flags every agent that pauses to turn. Measure progress over a window.

    `remainingDistance` is `Infinity` while the agent does not know it, and is only valid once `pathPending` is false. Check both.

    Warping an agent in view looks broken. Do it off screen, or not at all.

    A queue that forgets agents that died or changed goal fills up and never opens. Cancel in `OnDisable` and when the goal changes.

    An agent pushed off the mesh by a `Rigidbody` or a knockback cannot path at all until it is warped back. Check `isOnNavMesh` first.
