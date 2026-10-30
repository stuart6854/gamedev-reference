---
engine: Unity
version: 6+
uses:
  - name: Hordes
    text: A gunshot pulls every zombie within its radius towards where it was fired.
  - name: Stealth
    text: Guards fill an awareness meter faster when the player is close, lit, or standing up.
  - name: Wildlife
    text: Animals hear footsteps and flee before the player is in sight.
  - name: Turrets and cameras
    text: A narrow cone and a long range, with no hearing.
  - name: Companions
    text: Allies notice threats the player has not seen, and call them out.
---

# Perception

What an agent knows about the world: what it can see, what it has heard, and how sure it is. Sight is a cone, a range, and rays against walls. Hearing is noise events with a radius, muffled by walls. Both feed an **awareness** meter per target, so an agent first turns to look, then investigates, then commits, instead of snapping from idle to attack the moment one ray connects. When a target is lost, the agent remembers where it last was.

Perception only reports. Deciding what to do with it is the brain's job: the [state machine](../architecture/state-machines.md) on [enemy behaviour](enemy.md), or a utility score.

## Sight

A target is seen when all of these hold, checked from the agent's eyes:

1. **Range.** Within **Sight Range**.
2. **Cone.** Within half the **Field Of View** of the eyes' forward direction. Inside **Close Range**, any direction counts, so an agent notices someone standing right behind it, at half rate.
3. **Line of sight.** A ray from the eyes reaches at least one of the target's **Aim Points** without hitting an occluder.

One ray to a target's pivot misses a target whose feet are behind a low wall, and sees one through a gap the size of the ray. Several aim points, such as head, chest, and feet, are much more robust, and the ray stops at the first one that is clear.

### Awareness

Seeing a target does not mean noticing it. Each tick a target is visible, awareness rises:

\[
a \leftarrow a + r_{\text{notice}} \cdot v \cdot \Bigl(1 - 0.8\,\frac{d}{d_{\max}}\Bigr) \cdot \Delta t
\]

with \(v\) the target's **Visibility**: 1 by default, lower when crouching or in shadow, higher when lit or firing. Close and visible targets fill the meter in a fraction of a second; distant ones in shadow take several seconds, or never get there.

| Awareness | Typical response |
| --- | --- |
| 0 | Unaware. |
| Rising | Turn the head towards it, show a "?" indicator. |
| 0.5 | Investigate the last known position. |
| 1 | Noticed: the `Noticed` event fires. Chase, attack, or raise the alarm. |

When the target is not visible, awareness decays at **Decay Rate** after a short grace period. A noticed target is forgotten, with `Forgotten`, only once awareness is back to zero and **Memory** seconds have passed since it was last seen or heard. Until then, `LastKnownPosition` is where to search.

## Hearing

A noise is an event, not a sound effect: a position, a radius, and a source.

```csharp
Noise.Emit(muzzle.position, 40f, gameObject);   // a gunshot heard 40 m away
Noise.Emit(feet.position, running ? 8f : 3f, gameObject);  // footsteps
```

Every perceiver within the radius hears it, with a strength that falls off linearly with distance:

\[
s = 1 - \frac{d}{r}
\]

If a wall is between the noise and the listener, \(s\) is multiplied by **Muffled By Walls**. The perceiver raises `Heard` with the position and strength. If the noise came from a perception target, it also adds to that target's awareness and moves its last known position to the noise. A noise from a target the agent cannot see makes it look in the right place.

Noises from things that are not targets, such as a thrown bottle or a car alarm, still raise `Heard`. That is the distraction mechanic: the brain investigates `LastNoise` without knowing who made it.

## Ticking

Sight is a few rays per agent per target. For many agents, checking every frame is wasteful and unnecessary: human reaction time is about a fifth of a second anyway. Each perceiver ticks every **Tick Interval** seconds, starting at a random offset so a hundred agents spawned together do not all tick on the same frame. Awareness uses the real time since the last tick, so it rises at the same rate whatever the interval.

Noises are delivered immediately, because they are rare and the brain usually wants to react on the same frame.

## Setup

1. Put `PerceptionTarget` on the player, and on anything else agents should notice. Add child transforms for **Aim Points**, such as head and chest; empty uses the root.
2. Put `Perceiver` on each agent. Assign **Eyes**, a child at head height facing forward. Set **Occluders** to the layers that block sight and sound, such as walls and terrain. Do not include the characters' own layers, or a target blocks its own rays.
3. Call `Noise.Emit` from the things that make noise: weapons, footsteps, doors, glass, vehicles.
4. In the brain, subscribe to `Noticed`, `Forgotten`, and `Heard`, or poll `TryGetTarget` and `LastNoise` from its state machine.
5. Crouching, darkness, or camouflage set `PerceptionTarget.Visibility` below 1.

## Scripts

### Perception target

```csharp
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Something perceivers can see. Registers itself while enabled.
/// </summary>
public class PerceptionTarget : MonoBehaviour
{
    static readonly List<PerceptionTarget> _all = new List<PerceptionTarget>();
    public static IReadOnlyList<PerceptionTarget> All => _all;

    [Tooltip("Points sight rays aim at, such as head, chest, and feet. Empty uses this transform.")]
    [SerializeField] Transform[] aimPoints = System.Array.Empty<Transform>();

    [Tooltip("1 is normal. Lower when crouching or in shadow, higher when lit or firing.")]
    [Min(0f)] [SerializeField] float visibility = 1f;

    public float Visibility
    {
        get => visibility;
        set => visibility = Mathf.Max(0f, value);
    }

    public int AimPointCount => aimPoints.Length > 0 ? aimPoints.Length : 1;

    public Vector3 AimPoint(int index)
    {
        return aimPoints.Length > 0 && aimPoints[index] != null ? aimPoints[index].position : transform.position;
    }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        _all.Clear();
    }

    void OnEnable()
    {
        _all.Add(this);
    }

    void OnDisable()
    {
        _all.Remove(this);
    }
}
```

### Noise

```csharp
using UnityEngine;

public struct NoiseEvent
{
    public Vector3 Position;
    public float Radius;
    public GameObject Source;
    public float Time;
}

/// <summary>
/// Gameplay noise. Every perceiver within the radius hears it now.
/// </summary>
public static class Noise
{
    public static void Emit(Vector3 position, float radius, GameObject source = null)
    {
        if (radius <= 0f)
            return;

        NoiseEvent noise = new NoiseEvent
        {
            Position = position,
            Radius = radius,
            Source = source,
            Time = UnityEngine.Time.time
        };

        float radiusSquared = radius * radius;
        var listeners = Perceiver.All;
        for (int i = listeners.Count - 1; i >= 0; i--)
        {
            Perceiver listener = listeners[i];
            float distanceSquared = (listener.transform.position - position).sqrMagnitude;
            if (distanceSquared <= radiusSquared)
                listener.Hear(noise, Mathf.Sqrt(distanceSquared));
        }
    }
}
```

The loop runs backwards so a listener that disables itself in its `Heard` handler does not skip the next one.

### Perceiver

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Sight and hearing for one agent, with an awareness meter and a last known position per target.
/// </summary>
public class Perceiver : MonoBehaviour
{
    static readonly List<Perceiver> _all = new List<Perceiver>();
    public static IReadOnlyList<Perceiver> All => _all;

    [Header("Sight")]
    [SerializeField] Transform eyes;
    [SerializeField] float sightRange = 15f;
    [Range(1f, 360f)] [SerializeField] float fieldOfView = 110f;
    [Tooltip("Within this range, targets are seen in any direction, at half rate.")]
    [SerializeField] float closeRange = 2f;
    [SerializeField] LayerMask occluders = ~0;
    [SerializeField] float tickInterval = 0.2f;

    [Header("Awareness")]
    [Tooltip("Awareness per second for a close, fully visible target. 1 is noticed.")]
    [SerializeField] float noticeRate = 2f;
    [SerializeField] float decayRate = 0.25f;
    [Tooltip("Seconds unseen before awareness starts to decay.")]
    [SerializeField] float decayDelay = 1f;
    [Tooltip("Seconds since last seen or heard before a noticed target is forgotten.")]
    [SerializeField] float memory = 10f;

    [Header("Hearing")]
    [SerializeField] bool canHear = true;
    [SerializeField] float hearingGain = 1f;
    [Range(0f, 1f)] [SerializeField] float muffledByWalls = 0.5f;

    public event Action<PerceptionTarget> Noticed;
    public event Action<PerceptionTarget> Forgotten;
    public event Action<NoiseEvent, float> Heard;

    public bool HasHeardNoise { get; private set; }
    public NoiseEvent LastNoise { get; private set; }

    public class Record
    {
        public float Awareness;
        public bool Visible;
        public bool Noticed;
        public Vector3 LastKnownPosition;
        public float LastSensedTime;
    }

    readonly Dictionary<PerceptionTarget, Record> _records = new Dictionary<PerceptionTarget, Record>();
    readonly List<PerceptionTarget> _toForget = new List<PerceptionTarget>();
    float _nextTick;
    float _lastTick;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        _all.Clear();
    }

    void Awake()
    {
        if (eyes == null)
            eyes = transform;
    }

    void OnEnable()
    {
        _all.Add(this);
        _lastTick = Time.time;
        _nextTick = Time.time + UnityEngine.Random.value * tickInterval; // stagger agents
    }

    void OnDisable()
    {
        _all.Remove(this);
    }

    void Update()
    {
        if (Time.time < _nextTick)
            return;

        float dt = Mathf.Min(Time.time - _lastTick, 1f);
        _lastTick = Time.time;
        _nextTick = Time.time + tickInterval;
        Sense(dt);
    }

    /// <summary>The noticed target with the highest awareness, preferring visible ones.</summary>
    public bool TryGetTarget(out PerceptionTarget target, out Record record)
    {
        target = null;
        record = null;
        float best = float.MinValue;
        foreach (KeyValuePair<PerceptionTarget, Record> pair in _records)
        {
            if (pair.Key == null || !pair.Value.Noticed)
                continue;
            float score = pair.Value.Awareness + (pair.Value.Visible ? 1f : 0f);
            if (score > best)
            {
                best = score;
                target = pair.Key;
                record = pair.Value;
            }
        }
        return target != null;
    }

    public float AwarenessOf(PerceptionTarget target)
    {
        return target != null && _records.TryGetValue(target, out Record record) ? record.Awareness : 0f;
    }

    void Sense(float dt)
    {
        IReadOnlyList<PerceptionTarget> targets = PerceptionTarget.All;
        for (int i = 0; i < targets.Count; i++)
        {
            PerceptionTarget target = targets[i];
            if (target.transform.IsChildOf(transform))
                continue;

            float sight = SightFactor(target, out Vector3 seenAt);
            Record record = Get(target, sight > 0f);
            if (record == null)
                continue;

            record.Visible = sight > 0f;
            if (record.Visible)
            {
                record.LastKnownPosition = seenAt;
                record.LastSensedTime = Time.time;
                Raise(target, record, noticeRate * sight * dt);
            }
        }

        // Decay and forget, including targets that were disabled or destroyed.
        _toForget.Clear();
        foreach (KeyValuePair<PerceptionTarget, Record> pair in _records)
        {
            Record record = pair.Value;
            bool gone = pair.Key == null || !pair.Key.isActiveAndEnabled;
            if (gone)
                record.Visible = false;

            float unsensed = Time.time - record.LastSensedTime;
            if (!record.Visible && unsensed > decayDelay)
                record.Awareness = Mathf.Max(0f, record.Awareness - decayRate * dt);

            if (gone || (record.Awareness <= 0f && unsensed > memory))
                _toForget.Add(pair.Key);
        }

        foreach (PerceptionTarget target in _toForget)
        {
            bool wasNoticed = _records[target].Noticed;
            _records.Remove(target);
            if (wasNoticed && target != null)
                Forgotten?.Invoke(target);
        }
    }

    float SightFactor(PerceptionTarget target, out Vector3 seenAt)
    {
        seenAt = target.transform.position;
        if (target.Visibility <= 0f)
            return 0f;

        Vector3 eye = eyes.position;
        for (int i = 0; i < target.AimPointCount; i++)
        {
            Vector3 point = target.AimPoint(i);
            Vector3 to = point - eye;
            float distance = to.magnitude;
            if (distance > sightRange)
                continue;

            bool inCone = Vector3.Angle(eyes.forward, to) <= fieldOfView * 0.5f;
            bool close = distance <= closeRange;
            if (!inCone && !close)
                continue;

            if (Physics.Linecast(eye, point, occluders, QueryTriggerInteraction.Ignore))
                continue;

            float factor = target.Visibility * (1f - 0.8f * distance / sightRange);
            return inCone ? factor : factor * 0.5f;
        }
        return 0f;
    }

    /// <summary>Called by Noise.Emit.</summary>
    public void Hear(NoiseEvent noise, float distance)
    {
        if (!canHear || !isActiveAndEnabled)
            return;

        float strength = 1f - distance / noise.Radius;
        if (strength <= 0f)
            return;
        if (Physics.Linecast(eyes.position, noise.Position, occluders, QueryTriggerInteraction.Ignore))
            strength *= muffledByWalls;
        if (strength <= 0f)
            return;

        HasHeardNoise = true;
        LastNoise = noise;

        if (noise.Source != null && noise.Source.TryGetComponent(out PerceptionTarget target) &&
            !target.transform.IsChildOf(transform))
        {
            Record record = Get(target, true);
            record.LastKnownPosition = noise.Position;
            record.LastSensedTime = Time.time;
            Raise(target, record, strength * hearingGain);
        }

        Heard?.Invoke(noise, strength);
    }

    Record Get(PerceptionTarget target, bool create)
    {
        if (_records.TryGetValue(target, out Record record))
            return record;
        if (!create)
            return null;

        record = new Record { LastSensedTime = Time.time };
        _records.Add(target, record);
        return record;
    }

    void Raise(PerceptionTarget target, Record record, float amount)
    {
        record.Awareness = Mathf.Clamp01(record.Awareness + amount);
        if (!record.Noticed && record.Awareness >= 1f)
        {
            record.Noticed = true;
            Noticed?.Invoke(target);
        }
    }

    void OnDrawGizmosSelected()
    {
        Transform from = eyes != null ? eyes : transform;
        Gizmos.color = new Color(1f, 0.9f, 0.2f, 0.6f);
        Vector3 left = Quaternion.AngleAxis(-fieldOfView * 0.5f, Vector3.up) * from.forward;
        Vector3 right = Quaternion.AngleAxis(fieldOfView * 0.5f, Vector3.up) * from.forward;
        Gizmos.DrawLine(from.position, from.position + left * sightRange);
        Gizmos.DrawLine(from.position, from.position + right * sightRange);
        Gizmos.DrawWireSphere(from.position, closeRange);
    }
}
```

A noticed target stays noticed while its awareness decays, so a brain keeps chasing the last known position. It is only dropped, with `Forgotten`, once awareness is zero and the memory time has passed.

## At scale

- **Many perceivers, one player.** The loop is perceivers × targets × aim points rays per tick. With 200 agents ticking at 5 Hz and two aim points, that is up to 2,000 rays a second, which is fine. The range check comes first, so distant agents cast nothing.
- **Hundreds of agents and noises.** `Noise.Emit` checks every perceiver. Filing perceivers in a spatial hash grid makes a noise check only the cells within its radius.
- **Thousands of agents.** Batch the sight rays with `RaycastCommand` in a job, and give distant agents a slower tick, or no sight at all until a noise wakes them.

!!! warning "Common pitfalls"

    **Occluders** that include the characters' layers block a target's own sight rays on its own collider, and nothing is ever seen. Use only walls and terrain.

    An eyes transform that does not turn with the head or the body makes the cone point the wrong way. Parent it to whatever the agent looks with.

    One aim point at the pivot, usually the feet, is hidden by every low obstacle. Use a chest and a head point.

    Ticking every perceiver on the same frame makes a spike every interval. The random start offset spreads them; keep it.

    Footstep noises with a large radius make every agent in a building hear the player walk. Scale the radius with speed, and keep walking quiet.
