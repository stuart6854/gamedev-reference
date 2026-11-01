---
engine: Unity
version: 6+
uses:
  - name: Shooters
    text: Tracer rounds every few shots, visible streaks for hitscan guns, and trails on slow projectiles.
  - name: Top-down survival
    text: Seeing where the gunfire is going from above, including the zombies' side of the fight.
  - name: Strategy and tactics
    text: Lines of fire across the battlefield, from one shared particle system for every unit.
---

# Bullet tracers

A visible streak along a shot's path. A hitscan bullet hits on the frame it is fired, so there is nothing to see unless something is drawn; a real bullet at 900 metres per second crosses a 30 metre screen in two frames. A tracer is a visual: a short streak that travels from the muzzle to the end of the shot at a speed the eye can follow. It never decides what is hit.

This page adds a shot event to the [weapon](weapons.md), a component that decides which shots get a tracer, and three ways to draw them: pooled line streaks, one shared particle system, and trails on real projectiles.

| Approach | Draws | Cost | Use for |
| --- | --- | --- | --- |
| [Line streaks](#line-streaks) | A `LineRenderer` per tracer in flight, from a pool | One renderer each, updated in one loop | A few guns, tracers that need custom shapes or fading |
| [Shared particle system](#shared-particle-system) | A stretched particle per tracer in one world-space system | One system and one draw for every tracer | Many guns: squads, turrets, a whole battle |
| [Projectile trails](#projectile-trails) | A `TrailRenderer` behind a real projectile | One trail per projectile | Slow shots: rockets, arrows, plasma |

## The shot event

The weapon raises `Impact` only when something is hit. A tracer needs every shot, including misses, with where it started and where it ended. Add an event and raise it from `Hitscan`:

```csharp
// In Weapon, with the other events:
/// <summary>Every hitscan shot: start, end, and whether it hit something. For tracers.</summary>
public event Action<Vector3, Vector3, bool> Traced;

// In Weapon.Hitscan, replacing its body:
Vector3 origin = MuzzlePosition();
Vector3 direction = ShotDirection();
bool hit = TryRay(origin, direction, definition.range, out RaycastHit info);
Traced?.Invoke(origin, hit ? info.point : origin + direction * definition.range, hit);
if (hit)
    Deliver(info.collider, info.point, info.normal, info.distance, definition.damage * damageScale);
```

The tracer ends at the hit point, or at full range for a miss, so a shot into the sky still shows where it went.

## Which shots

```csharp
using UnityEngine;

/// <summary>What draws a tracer. Line streaks and the shared particle system both implement it.</summary>
public interface ITracerRenderer
{
    void Draw(Vector3 from, Vector3 to, float speed);
}

/// <summary>
/// Turns a weapon's shots into tracers: every Nth round, skipping the first metres of the path.
/// </summary>
public class TracerEmitter : MonoBehaviour
{
    [SerializeField] Weapon weapon;
    [Tooltip("A component that implements ITracerRenderer.")]
    [SerializeField] MonoBehaviour tracerRenderer;
    [Tooltip("1: every shot. 5: one in five, like a machine-gun belt.")]
    [SerializeField, Min(1)] int every = 1;
    [Tooltip("Metres per second. Real bullets are too fast to see; 200 to 400 reads well.")]
    [SerializeField] float speed = 300f;
    [Tooltip("Metres along the path before the tracer starts. Hides it at the muzzle and right in front of the camera.")]
    [SerializeField] float skipStart = 1.5f;
    [Tooltip("Paths shorter than this, after the skip, get no tracer.")]
    [SerializeField] float minLength = 2f;

    ITracerRenderer _renderer;
    int _shots;

    void Awake()
    {
        _renderer = tracerRenderer as ITracerRenderer;
        if (_renderer == null)
            Debug.LogWarning("Tracer Renderer must implement ITracerRenderer.", this);
    }

    void OnEnable()
    {
        if (weapon != null)
            weapon.Traced += OnTraced;
    }

    void OnDisable()
    {
        if (weapon != null)
            weapon.Traced -= OnTraced;
    }

    /// <summary>Restart the belt, for example on reload, so the first shot of a magazine is a tracer.</summary>
    public void ResetCount() => _shots = 0;

    void OnTraced(Vector3 start, Vector3 end, bool hit)
    {
        if (_renderer == null || _shots++ % every != 0)
            return;

        Vector3 path = end - start;
        float length = path.magnitude;
        if (length < skipStart + minLength)
            return;

        Vector3 direction = path / length;
        _renderer.Draw(start + direction * skipStart, end, speed);
    }
}
```

- **Every Nth.** Belt-fed guns load a tracer every few rounds. Every shot is fine for pistols in a top-down game, where every shot should read.
- **Last rounds.** Some games load tracers in the last few rounds of a magazine, as a warning to reload. Check `weapon.Magazine` in `OnTraced` instead of the counter.
- **Skip the start.** From a first-person camera, a tracer that starts at the muzzle runs straight away from the eye and shows as a bright dot or a smear across the bottom of the screen. Starting it a metre or two along the path hides that, and reads as the bullet appearing out of the muzzle flash.

## Line streaks

A pool of two-point `LineRenderer`s. Each tracer has a head that moves at the tracer speed and a tail a fixed length behind it, both clamped to the path, so the streak grows out of the start, travels, and shrinks into the end. One `Update` moves every tracer in flight.

```csharp
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Pool;

/// <summary>
/// Draws tracers as short line streaks that travel along each shot's path.
/// </summary>
public class TracerStreaks : MonoBehaviour, ITracerRenderer
{
    [Tooltip("Two positions, Use World Space on, an additive HDR material.")]
    [SerializeField] LineRenderer prefab;
    [SerializeField] float streakLength = 6f;
    [SerializeField] int maxInFlight = 128;

    class Flight
    {
        public LineRenderer line;
        public Vector3 from;
        public Vector3 direction;
        public float length;
        public float travelled;
        public float speed;
    }

    ObjectPool<LineRenderer> _pool;
    readonly List<Flight> _flights = new List<Flight>();
    readonly Stack<Flight> _spare = new Stack<Flight>();

    void Awake()
    {
        _pool = new ObjectPool<LineRenderer>(
            () => Instantiate(prefab, transform),
            line => line.gameObject.SetActive(true),
            line => line.gameObject.SetActive(false),
            line => Destroy(line.gameObject),
            collectionCheck: false, defaultCapacity: 16, maxSize: maxInFlight);
    }

    public void Draw(Vector3 from, Vector3 to, float speed)
    {
        if (_flights.Count >= maxInFlight)
            return; // a wall of tracers is no clearer than a full one

        Vector3 path = to - from;
        Flight f = _spare.Count > 0 ? _spare.Pop() : new Flight();
        f.line = _pool.Get();
        f.line.positionCount = 2;
        f.from = from;
        f.length = path.magnitude;
        f.direction = f.length > 0f ? path / f.length : Vector3.forward;
        f.travelled = 0f;
        f.speed = speed;
        _flights.Add(f);
        Place(f);
    }

    void Update()
    {
        float dt = Time.deltaTime;
        for (int i = _flights.Count - 1; i >= 0; i--)
        {
            Flight f = _flights[i];
            f.travelled += f.speed * dt;
            if (f.travelled - streakLength >= f.length)
            {
                _pool.Release(f.line);
                f.line = null;
                _spare.Push(f);
                _flights[i] = _flights[_flights.Count - 1];
                _flights.RemoveAt(_flights.Count - 1);
                continue;
            }
            Place(f);
        }
    }

    void Place(Flight f)
    {
        float head = Mathf.Min(f.travelled, f.length);
        float tail = Mathf.Clamp(f.travelled - streakLength, 0f, f.length);
        f.line.SetPosition(0, f.from + f.direction * tail);
        f.line.SetPosition(1, f.from + f.direction * head);
    }
}
```

- **The line.** Width about 0.03 to 0.06 metres in first person, more from a top-down camera. A **Width** curve that tapers to 0 at the tail end, and a gradient from transparent at the tail to bright at the head, reads as motion.
- **Material.** An additive or unlit particle shader with an HDR colour above 1, so [bloom](../rendering/post-processing.md#the-common-effects) picks it up. **Alignment: View** keeps the line facing the camera.
- **No allocation.** The pool, the flight records, and the swap-remove of finished flights keep firing free of garbage after warm-up.

## Shared particle system

For many guns, one world-space Particle System holds every tracer as a stretched particle. Each tracer is one `Emit` with a velocity along the path and a lifetime that ends it at the far end.

```csharp
using UnityEngine;

/// <summary>
/// Draws every tracer as one stretched particle in a shared world-space system.
/// </summary>
[RequireComponent(typeof(ParticleSystem))]
public class TracerParticles : MonoBehaviour, ITracerRenderer
{
    ParticleSystem _system;

    void Awake() => _system = GetComponent<ParticleSystem>();

    public void Draw(Vector3 from, Vector3 to, float speed)
    {
        Vector3 path = to - from;
        float distance = path.magnitude;
        if (distance <= 0f || speed <= 0f)
            return;

        var p = new ParticleSystem.EmitParams
        {
            position = from,
            velocity = path / distance * speed,
            startLifetime = distance / speed,
            applyShapeToPosition = false
        };
        _system.Emit(p, 1);
    }
}
```

The system's settings:

| Module | Setting |
| --- | --- |
| Main | **Simulation Space: World**, **Gravity Modifier** 0, **Start Speed** 0, **Max Particles** a few hundred, **Looping** off, **Play On Awake** on |
| Emission, Shape | Off: everything comes from `Emit` |
| Renderer | **Render Mode: Stretched Billboard**, **Speed Scale** 0, **Length Scale** to taste, so the streak length is constant whatever the speed |
| Material | Additive HDR, like the line streaks |

- Lifetime is set per particle, so a short shot and a long one each end at their own end point.
- A stretched billboard extends along the velocity from the particle's position. Watch a tracer hit a wall: if the streak pokes through the wall at the end, shorten `startLifetime` by about half the streak's length divided by the speed.
- `ImpactEffects` on the [particles](../rendering/particles.md#emitting-into-one-system) page uses the same pattern: one system, `Emit` per event.

## Projectile trails

Slow projectiles, such as rockets, arrows, and plasma, are visible on their own, and a `TrailRenderer` adds the streak behind them. Two problems with [pooled projectiles](weapons.md#projectiles):

- A reused projectile's trail still holds its last flight, and draws a streak from where it died to the muzzle. Clear it after moving it.
- On impact the projectile returns to the pool and disappears at once, taking the trail with it mid-air. The trail should stop growing and fade where it is.

A component on the projectile prefab borrows a trail from a shared pool while the projectile is out, and leaves it behind to fade when it returns:

```csharp
using UnityEngine;
using UnityEngine.Pool;

/// <summary>
/// Gives a pooled projectile a trail that is cleared on launch and left behind to fade on impact.
/// </summary>
public class ProjectileTrail : MonoBehaviour
{
    [SerializeField] TrailRenderer trailPrefab;

    static ObjectPool<TrailRenderer> s_pool;
    static TrailRenderer s_prefab;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        s_pool = null;
        s_prefab = null;
    }

    TrailRenderer _trail;
    bool _fresh;

    void OnEnable()
    {
        EnsurePool();
        _trail = s_pool.Get();
        _trail.emitting = false; // until the projectile is in place
        _fresh = true;
    }

    void LateUpdate()
    {
        if (_trail == null)
            return;
        _trail.transform.position = transform.position;
        if (_fresh)
        {
            // First frame after Launch moved the projectile: wipe the old flight, then start.
            _trail.Clear();
            _trail.emitting = true;
            _fresh = false;
        }
    }

    void OnDisable()
    {
        if (_trail == null)
            return;
        // Leave the trail where the projectile died, and give it back once it has faded.
        _trail.emitting = false;
        TrailReturn.After(_trail, _trail.time, s_pool);
        _trail = null;
    }

    void EnsurePool()
    {
        if (s_pool != null)
            return;
        s_prefab = trailPrefab;
        s_pool = new ObjectPool<TrailRenderer>(
            () => Instantiate(s_prefab),
            t => t.gameObject.SetActive(true),
            t => t.gameObject.SetActive(false),
            t => Destroy(t.gameObject),
            collectionCheck: false, defaultCapacity: 16, maxSize: 128);
    }
}

/// <summary>Returns a fading trail to its pool after a delay. Lives on the trail prefab.</summary>
public class TrailReturn : MonoBehaviour
{
    ObjectPool<TrailRenderer> _pool;
    TrailRenderer _trail;
    float _at;

    public static void After(TrailRenderer trail, float seconds, ObjectPool<TrailRenderer> pool)
    {
        if (!trail.TryGetComponent(out TrailReturn r))
            r = trail.gameObject.AddComponent<TrailReturn>();
        r._pool = pool;
        r._trail = trail;
        r._at = Time.time + seconds;
        r.enabled = true;
    }

    void Update()
    {
        if (Time.time < _at)
            return;
        enabled = false;
        _pool.Release(_trail);
    }
}
```

- The trail objects live at the scene root, not under the projectile, so the projectile's pool disabling it does not disable the trail.
- One shared pool for all projectiles of this trail type. Projectiles with different trails need a pool per prefab; key a dictionary by prefab, as the [pool manager](../architecture/pooling.md#registry-and-self-return) does.
- Put the `TrailReturn` component on the trail prefab, so `AddComponent` never runs during play.

## Hit timing

A tracer at 300 metres per second reaches a target 30 metres away in a tenth of a second. The hit has already landed: the damage, the impact effect, and the sound all played on the frame of the shot. For most games that is right, because the gun feels instant. Two alternatives:

- **Delay the impact effect** by distance divided by tracer speed, so sparks appear when the tracer arrives. Damage stays instant.
- **Use projectiles**, so damage, effect, and visual all arrive together. That changes how the gun plays, not just how it looks.

!!! warning "Common pitfalls"

    A tracer only on hits. Misses are most of the shots, and the ones the player most needs to see. Raise the shot event for every shot.

    Tracers at the bullet's real speed. They exist for a frame or two and read as flicker. Slow them down.

    A tracer starting at the muzzle in first person. It shoots straight away from the eye and shows as a dot. Skip the first metres.

    A pooled projectile's trail streaking back to where the last one died. Clear the trail after the projectile is placed.

    A trail parented to a pooled projectile vanishing on impact. Detach it and let it fade.
