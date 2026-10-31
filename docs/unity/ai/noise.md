---
engine: Unity
version: 6+
uses:
  - name: Top-down survival
    text: A gunshot that pulls the street's zombies, a car alarm that keeps pulling them, and footsteps that give the player away.
  - name: Stealth
    text: Walking, running, and crouching footsteps, louder on gravel and quieter on carpet, shown as a ring around the player.
  - name: Hordes and crowds
    text: Zombies bashing on a door making the noise that brings more zombies.
---

# Noise sources

What makes noise in the world, and how loud. The [perception](perception.md#hearing) page has the event itself: `Noise.Emit(position, radius, source)`, heard by every perceiver in range and muffled by walls. The [horde](horde.md#goals-and-attraction) page has `Attract`, which moves the far population. This page puts both behind one call, then adds the sources: footsteps, gunfire, impacts, damage, alarms, and a ring that shows the player how loud they were.

## One call

```csharp
using System;
using UnityEngine;

/// <summary>
/// Gameplay noise: nearby perceivers hear it, the wider horde drifts toward it, and the UI can show it.
/// </summary>
public static class GameNoise
{
    /// <summary>Set by the horde when it starts. Null in levels without one.</summary>
    public static HordeSimulation Horde { get; set; }

    /// <summary>Scales every noise: rain and wind lower it, an echoing tunnel raises it.</summary>
    public static float GlobalMultiplier { get; set; } = 1f;

    /// <summary>How much further the horde hears than an individual agent.</summary>
    public static float HordeRange { get; set; } = 3f;

    /// <summary>For noise rings and debug drawing.</summary>
    public static event Action<Vector3, float, GameObject> Made;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        Horde = null;
        GlobalMultiplier = 1f;
        HordeRange = 3f;
        Made = null;
    }

    public static void Make(Vector3 position, float radius, GameObject source = null)
    {
        radius *= GlobalMultiplier;
        if (radius <= 0f)
            return;

        Noise.Emit(position, radius, source);
        if (Horde != null)
            Horde.Attract(position, radius * HordeRange);
        Made?.Invoke(position, radius, source);
    }
}
```

The horde registers itself with two lines in `HordeSimulation`, merged into its `OnEnable` and `OnDisable` if it already has them:

```csharp
// In HordeSimulation:
void OnEnable() => GameNoise.Horde = this;
void OnDisable() { if (GameNoise.Horde == this) GameNoise.Horde = null; }
```

Call `GameNoise.Make` everywhere the samples on other pages call `Noise.Emit`.

## How loud

Radius is in metres: how far a perceiver hears it with no wall in the way. These are starting points, tuned for a top-down game where the screen shows about 30 metres.

| Source | Radius |
| --- | --- |
| Crouch walk | 1 |
| Walk | 4 |
| Run | 10 |
| Melee hit, door opening | 6 |
| Breaking a window | 20 |
| Bashing a door, per hit | 12 |
| Forcing a lock | 15 |
| Suppressed pistol | 12 |
| Pistol | 40 |
| Shotgun, rifle | 60–80 |
| Car alarm, per pulse | 50 |
| Generator, per pulse | 20 |
| Explosion | 120 |

Radius already falls off: [perception](perception.md#hearing) scales strength from 1 at the source to 0 at the edge, and walls muffle it. Do not make quiet sounds louder to cross walls; make them reach their radius and let the walls decide.

## Footsteps

From the [animation event relay](../animation/events.md#a-relay-on-the-model)'s `Footstep`, so a noise lands on each step the feet make, with a radius from how the character is moving and what it is standing on.

```csharp
using UnityEngine;

/// <summary>
/// A noise per footstep, scaled by gait and surface.
/// </summary>
public class FootstepNoise : MonoBehaviour
{
    [SerializeField] AnimationEventRelay relay;
    [SerializeField] float walkRadius = 4f;
    [SerializeField] float runRadius = 10f;
    [SerializeField] float crouchMultiplier = 0.25f;
    [SerializeField] float runSpeed = 4f;
    [SerializeField] LayerMask ground = ~0;

    /// <summary>Set by the movement code.</summary>
    public bool Crouching { get; set; }

    Vector3 _lastPosition;
    float _speed;

    void OnEnable()
    {
        _lastPosition = transform.position;
        relay.Footstep += OnFootstep;
    }

    void OnDisable() => relay.Footstep -= OnFootstep;

    void Update()
    {
        if (Time.deltaTime > 0f)
            _speed = (transform.position - _lastPosition).magnitude / Time.deltaTime;
        _lastPosition = transform.position;
    }

    void OnFootstep(string foot)
    {
        float radius = Mathf.Lerp(walkRadius, runRadius, Mathf.InverseLerp(runSpeed * 0.5f, runSpeed, _speed));
        if (Crouching)
            radius *= crouchMultiplier;
        radius *= SurfaceMultiplier();
        GameNoise.Make(transform.position, radius, gameObject);
    }

    float SurfaceMultiplier()
    {
        if (Physics.Raycast(transform.position + Vector3.up * 0.5f, Vector3.down, out RaycastHit hit, 1.5f, ground, QueryTriggerInteraction.Ignore)
            && hit.collider.TryGetComponent(out Surface surface))
            return surface.NoiseMultiplier;
        return 1f;
    }
}

/// <summary>On floors and ground: gravel and broken glass are loud, carpet and grass quiet.</summary>
public class Surface : MonoBehaviour
{
    [SerializeField] float noiseMultiplier = 1f;
    public float NoiseMultiplier => noiseMultiplier;
}
```

The same `Surface` component picks the footstep sound, so what the player hears matches what the zombies hear.

## Impacts

Thrown bottles, dropped items, a body falling through a table. Loud in proportion to how hard they hit.

```csharp
using UnityEngine;

/// <summary>
/// Makes a noise when this Rigidbody hits something hard enough.
/// </summary>
[RequireComponent(typeof(Rigidbody))]
public class ImpactNoise : MonoBehaviour
{
    [Tooltip("Impact speed below which nothing is heard, in metres per second.")]
    [SerializeField] float minSpeed = 2f;
    [Tooltip("Noise radius per metre per second above Min Speed.")]
    [SerializeField] float radiusPerSpeed = 3f;
    [SerializeField] float maxRadius = 25f;
    [SerializeField] float cooldown = 0.2f;
    [Tooltip("The thrower, set when thrown, so the noise counts as theirs. Empty: an anonymous distraction.")]
    public GameObject Owner;

    float _quietUntil;

    void OnCollisionEnter(Collision collision)
    {
        float speed = collision.relativeVelocity.magnitude;
        if (speed < minSpeed || Time.time < _quietUntil)
            return;
        _quietUntil = Time.time + cooldown;

        float radius = Mathf.Min(maxRadius, (speed - minSpeed) * radiusPerSpeed);
        GameNoise.Make(collision.GetContact(0).point, radius, Owner);
    }
}
```

A thrown bottle with no owner is the classic distraction: zombies investigate where it broke, not who threw it. With the thrower as owner, the noise also raises awareness of the thrower, as [perception](perception.md#hearing) describes.

## Damage and breaking

A door being bashed is noise; a window breaking is louder. Hooking noise to [health](../systems/health.md) means anything with health makes noise when hit and when destroyed, including the [portals](navigation/doors-windows.md#portal) zombies break.

```csharp
using UnityEngine;

/// <summary>
/// A noise on every hit and a louder one on breaking.
/// </summary>
[RequireComponent(typeof(Health))]
public class DamageNoise : MonoBehaviour
{
    [SerializeField] float hitRadius = 12f;
    [SerializeField] float breakRadius = 20f;

    Health _health;

    void Awake() => _health = GetComponent<Health>();

    void OnEnable()
    {
        _health.Damaged += OnDamaged;
        _health.Died += OnDied;
    }

    void OnDisable()
    {
        _health.Damaged -= OnDamaged;
        _health.Died -= OnDied;
    }

    void OnDamaged(DamageInfo info, float amount) => GameNoise.Make(transform.position, hitRadius);
    void OnDied() => GameNoise.Make(transform.position, breakRadius);
}
```

The source is left empty: the door made the noise. Zombies hear a door being bashed and come to it, which is how one zombie at a door becomes a dozen. That loop is often the most memorable thing in a zombie game. Tune **Hit Radius** to decide how fast it snowballs.

## Sustained sources

A car alarm, a generator, a radio. A noise that repeats until something stops it.

```csharp
using UnityEngine;

/// <summary>
/// Repeats a noise while running. Car alarms, generators, radios.
/// </summary>
public class SustainedNoise : MonoBehaviour
{
    [SerializeField] float radius = 50f;
    [SerializeField] float interval = 1f;
    [Tooltip("Seconds before it stops on its own. 0 runs until stopped.")]
    [SerializeField] float duration = 60f;
    [SerializeField] bool startOn;

    public bool IsRunning { get; private set; }
    float _until;
    float _next;

    void Start()
    {
        if (startOn)
            Begin();
    }

    public void Begin()
    {
        IsRunning = true;
        _until = duration > 0f ? Time.time + duration : float.PositiveInfinity;
        _next = Time.time;
    }

    public void Stop() => IsRunning = false;

    void Update()
    {
        if (!IsRunning)
            return;
        if (Time.time >= _until)
        {
            Stop();
            return;
        }
        if (Time.time >= _next)
        {
            _next = Time.time + interval;
            GameNoise.Make(transform.position, radius);
        }
    }
}
```

- A car alarm starts when a car takes a hit, from `Health.Damaged`, or when a lock is forced. Switching it off is a [timed action](../systems/timed-actions.md) at the car.
- A generator the player runs for power is the trade-off in one component: electricity against a steady pull on every zombie nearby.
- Every pulse is a full noise event. Keep intervals at a second or more; perceivers do not need more often.

## Showing the player

The player cannot plan around noise they cannot see. A ring on the ground, sized to the radius, for the player's own noises:

```csharp
using UnityEngine;

/// <summary>
/// Shows a fading ring for each noise the player makes.
/// </summary>
public class NoiseRings : MonoBehaviour
{
    [SerializeField] GameObject player;
    [Tooltip("A flat ring prefab, one unit in radius, with a component that fades and returns itself to a pool.")]
    [SerializeField] GameObject ringPrefab;
    [SerializeField] float minRadius = 2f;

    void OnEnable() => GameNoise.Made += OnNoise;
    void OnDisable() => GameNoise.Made -= OnNoise;

    void OnNoise(Vector3 position, float radius, GameObject source)
    {
        if (source != player || radius < minRadius)
            return;
        GameObject ring = Instantiate(ringPrefab, position + Vector3.up * 0.05f, Quaternion.identity);
        ring.transform.localScale = new Vector3(radius, 1f, radius);
    }
}
```

Use an [object pool](../architecture/pooling.md) for the rings; footsteps make several a second. Skipping noises under **Min Radius** hides crouch steps, which the player should not need to see.

## Setup

1. Add the `HordeSimulation` lines above, so noise reaches the horde.
2. Replace `Noise.Emit` calls with `GameNoise.Make`.
3. Add `FootstepNoise` to characters with footstep events, and `Surface` to loud and quiet floors.
4. Add `ImpactNoise` to throwables, `DamageNoise` to doors, windows, and barricades, and `SustainedNoise` to cars and generators.
5. Add `NoiseRings` to the HUD scene, pointing at the player.
6. Lower `GameNoise.GlobalMultiplier` while it rains, from the weather system.

!!! warning "Common pitfalls"

    A noise per frame, such as an alarm in `Update` without an interval, checks every perceiver every frame. Pulse it.

    Footsteps from a timer instead of animation events drift from the visible steps, and keep sounding when the character slides to a stop.

    Every noise attributed to the player makes zombies always know where the player is. Leave the source empty for world noises such as doors and alarms.

    A horde radius equal to the perception radius makes gunshots no more dangerous than footsteps at range. The horde should hear further.

    Ring prefabs instantiated per footstep. Pool them.
