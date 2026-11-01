---
engine: Unity
version: 6+
package: URP 17.x
uses:
  - name: Shooters
    text: Impacts by surface from one shared system per effect, muzzle flashes, and shell casings that stay on the floor.
  - name: Top-down survival
    text: Rain that follows the camera, fire and smoke, blood that stays where it fell, and footstep dust.
  - name: Melee action
    text: Sword trails switched on for the swing's hit window.
  - name: RPGs
    text: Heal and buff auras that start and stop with the effect they show.
---

# Particles in Unity

Unity has two particle systems. The **Particle System** component, often called Shuriken, simulates on the CPU, collides with physics, and is driven from C#. **VFX Graph** simulates on the GPU, handles hundreds of thousands of particles, and is built in a node graph. This page chooses between them, covers the settings that matter, and builds the effects most games need: impacts, combat, weather, feedback, and trails. How particle systems work underneath is on the [graphics page](../../graphics/particles.md).

## Which system

| | Particle System | VFX Graph |
| --- | --- | --- |
| Simulates on | CPU | GPU, in compute shaders |
| Counts | Thousands | Up to millions |
| Physics collision | Yes: colliders, and collision events to scripts | No. Depth buffer, and simple shapes or signed distance fields |
| Scripting | Full: `Emit`, read and write particles, events per collision | Exposed properties and events. No reading particles back. |
| Platforms | All | Needs compute shader support. Check the VFX Graph docs for which outputs your pipeline and platform support. |
| Authoring | Modules in the inspector | A node graph |

Use the Particle System by default, and for anything gameplay touches. Use VFX Graph for volume: swarms, dense weather, magic storms, a horde's ash.

## Settings that matter

On the Particle System's **Main** module and the renderer:

| Setting | Use |
| --- | --- |
| **Simulation Space** | **World** for anything left behind by a moving emitter: smoke from a car, a trail of sparks. **Local** for effects that move with their object: an aura. |
| **Max Particles** | A hard cap. Set it to what the effect needs; the default 1000 hides runaway emission. |
| **Stop Action** | **Callback** sends `OnParticleSystemStopped`, which a pooled effect uses to return itself. **Destroy** and **Disable** do what they say; neither returns to a pool. |
| **Culling Mode** | What happens off screen. **Automatic** lets Unity pause predictable systems. **Pause And Catch-up** simulates the missed time on return, which can spike. **Always Simulate** for effects whose state matters off screen. |
| **Ring Buffer Mode** | Particles stay alive past their lifetime until **Max Particles** forces the oldest out. For blood pools, bullet holes, and shell casings on the floor. |
| **Prewarm** | A looping system starts as if it had run one full cycle. For fire and smoke already burning on level load. |
| **Scaling Mode** | **Hierarchy** scales with parents; **Local** ignores them; **Shape** scales only the emission shape. |
| Renderer **Sorting Fudge** and **Order in Layer** | Fix the draw order of blended systems against each other. |
| Renderer **Render Mode: Mesh** with **Enable Mesh GPU Instancing** | Mesh particles, such as debris, drawn instanced. Needs a shader that supports instanced particles. |

A system shows a warning icon in the inspector when its settings stop Unity from culling it procedurally, such as with some curves in **World** space. It then simulates off screen even on **Automatic**.

## One-shot effects

A muzzle flash or an explosion prefab, spawned and returned to the [pool](../architecture/pooling.md#registry-and-self-return) as a `PooledEffect` when it stops. The pool page has the component and the stop-action rules. Prewarm the pool with as many as can play at once.

## Emitting into one system

Hundreds of bullet impacts a second as pooled prefabs are hundreds of `GameObject`s a second. Instead, keep one **world-space** system per kind of effect, with **Emission** rate 0, and `Emit` particles into it where each hit lands. One system, one draw, no objects.

```csharp
using System;
using UnityEngine;

/// <summary>
/// Plays impacts by surface: one world-space system per surface, emitted into at each hit.
/// </summary>
public class ImpactEffects : MonoBehaviour
{
    [Serializable]
    public struct SurfaceEffect
    {
        public PhysicsMaterial material; // the collider's material decides the surface
        public ParticleSystem system;    // world space, no emission, no looping, Play On Awake on
        public int count;
    }

    [SerializeField] SurfaceEffect[] surfaces = Array.Empty<SurfaceEffect>();
    [SerializeField] ParticleSystem fallback;
    [SerializeField] int fallbackCount = 8;
    [SerializeField] float speed = 3f;

    public static ImpactEffects Instance { get; private set; }

    void OnEnable() => Instance = this;
    void OnDisable() { if (Instance == this) Instance = null; }

    public void Play(Vector3 point, Vector3 normal, Collider hit)
    {
        ParticleSystem system = fallback;
        int count = fallbackCount;
        PhysicsMaterial material = hit != null ? hit.sharedMaterial : null;
        foreach (SurfaceEffect s in surfaces)
        {
            if (s.material == material && s.system != null)
            {
                system = s.system;
                count = s.count;
                break;
            }
        }
        if (system == null)
            return;

        var p = new ParticleSystem.EmitParams { position = point, applyShapeToPosition = true };
        for (int i = 0; i < count; i++)
        {
            // Spray out of the surface, in a rough cone around the normal.
            Vector3 direction = (normal + UnityEngine.Random.insideUnitSphere * 0.6f).normalized;
            p.velocity = direction * speed * UnityEngine.Random.Range(0.5f, 1f);
            system.Emit(p, 1);
        }
    }
}
```

The [weapon](../combat/weapons.md)'s `Impact` event passes only the point and the normal. A short ray back into the surface finds the collider:

```csharp
void OnImpact(Vector3 point, Vector3 normal)
{
    Collider hit = Physics.Raycast(point + normal * 0.05f, -normal, out RaycastHit info, 0.1f) ? info.collider : null;
    ImpactEffects.Instance?.Play(point, normal, hit);
}
```

- `EmitParams` fields left unset use the system's own start values, so colour and lifetime still come from the inspector. Set only what differs per hit.
- **Apply Shape To Position** keeps the system's shape module as a small random offset around the point.
- The surfaces table can grow into sound, decals, and the [noise radius](../ai/noise.md) per surface, all keyed by the same material.

## Combat

**Muzzle flash.** A pooled prefab, or one system on the gun in **Local** space, with a single burst of a few large, short-lived additive particles, a flipbook flash, and the **Lights** module or a separate light enabled for a frame or two. Play it from the weapon's `Fired` event with `Play()`; it restarts each shot.

**Shell casings.** A mesh-particle system on the gun's ejection port, **World** space, **Collision** module against the world, **Ring Buffer Mode** on, and **Max Particles** of a few dozen. Casings bounce, settle, and the oldest disappear as new ones land. Real rigidbodies cost far more and are only worth it if casings must be kicked.

**Blood.** Two parts:

- A spray on hit: an `ImpactEffects` entry for flesh, emitting along the bullet direction rather than the normal.
- Pools that stay: a **World**, **Ring Buffer** system of flat, **Horizontal** particles, emitted on the ground under the hit with a ray down. For stains that wrap over uneven ground, use URP's **Decal Projector** instead, pooled the same way.

## Environment

### Weather that follows the camera

Rain over the whole map would be millions of particles. Rain over the screen is a few thousand. Move the emitter with the camera's focus, and simulate in **World** space, so falling drops do not slide sideways as the camera pans.

```csharp
using UnityEngine;

/// <summary>
/// Keeps a weather emitter above the camera's focus and sets its rate from intensity.
/// </summary>
public class WeatherEmitter : MonoBehaviour
{
    [SerializeField] ParticleSystem system;   // World space, Box shape wide enough to cover the view
    [SerializeField] Transform focus;         // the player, or the point the camera looks at
    [SerializeField] float height = 12f;
    [SerializeField] float maxRate = 4000f;

    [Range(0f, 1f)] public float Intensity = 1f;

    void LateUpdate()
    {
        if (focus == null)
            return;
        transform.position = focus.position + Vector3.up * height;

        ParticleSystem.EmissionModule emission = system.emission;
        emission.rateOverTime = maxRate * Intensity;
    }
}
```

- Module properties such as `system.emission` are structs that write through to the system. Get one, set fields on it; no need to assign it back.
- Use **Stretched Billboard** for rain and a slow, swaying **Noise** module for snow.
- Splashes: the **Collision** module with a **Sub Emitters** collision entry gives a splash where drops land, at a cost per collision. Cheaper: a second system of short splash particles emitted on the ground area at random, which reads the same from a top-down camera.
- Lower the [noise multiplier](../ai/noise.md#one-call) while it rains, from the same intensity.
- For a downpour of hundreds of thousands of drops, use VFX Graph with depth-buffer collision.

### Fire and smoke

A looping fire is three systems: additive flames with a flipbook, alpha-blended smoke above them, and a few additive embers with **Noise**. Use **Prewarm** so they are already burning, turn on **Depth Texture** in the URP asset and **Soft Particles** on the URP particle material, so smoke does not show hard lines where it meets walls, and add a flickering light. Smoke above flames: **Sorting Fudge** on the smoke so it draws after them.

### Dust and ambience

Dust motes in a sunbeam, ash after a fire, insects over water: low-rate, long-lived, **Local**-space systems in a box, with **Culling Mode** left on **Automatic**. They cost almost nothing off screen.

## Gameplay feedback

**Footstep dust.** From the [animation event relay](../animation/events.md#a-relay-on-the-model)'s `Footstep`, emit a few particles at the foot into one shared world-space dust system, the same way `ImpactEffects` does. Choose by the surface under the foot, like the [footstep noise](../ai/noise.md#footsteps).

**Pickup sparkle.** A looping **Local** system on the pickup prefab. Stop it with `Stop(true, ParticleSystemStopBehavior.StopEmitting)` when collected, so the existing sparkles fade out instead of vanishing.

**Auras for effects.** An aura per [effect](../systems/needs.md#effects), started and stopped by the effect's events:

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Plays a looping aura while an effect is active on this character.
/// </summary>
public class EffectAuras : MonoBehaviour
{
    [Serializable]
    public struct Aura
    {
        public EffectDefinition effect;
        public ParticleSystem system; // child of the character, Local space, looping
    }

    [SerializeField] Effects effects;
    [SerializeField] Aura[] auras = Array.Empty<Aura>();

    void OnEnable()
    {
        effects.Applied += OnApplied;
        effects.Ended += OnEnded;
    }

    void OnDisable()
    {
        effects.Applied -= OnApplied;
        effects.Ended -= OnEnded;
    }

    void OnApplied(EffectDefinition effect)
    {
        foreach (Aura a in auras)
        {
            if (a.effect == effect && !a.system.isEmitting)
                a.system.Play(true);
        }
    }

    void OnEnded(EffectDefinition effect)
    {
        // Ended fires once per instance; an independent effect may still have others running.
        if (effects.Stacks(effect) > 0)
            return;
        foreach (Aura a in auras)
        {
            if (a.effect == effect)
                a.system.Stop(true, ParticleSystemStopBehavior.StopEmitting);
        }
    }
}
```

**Death burst.** A pooled one-shot at the body, with a sub-emitter for lingering smoke. For a zombie horde, emit into one shared system instead, as impacts do.

## Trails

| Tool | Good for | Notes |
| --- | --- | --- |
| **Trail Renderer** | One trail behind a moving object: a projectile, a dash, a sword tip. | Builds a strip from the object's recent positions. `emitting` pauses it; `Clear()` wipes it. |
| **Line Renderer** | A line between known points: a laser, a rope, an aim line, a range circle. | You set the points with `SetPositions`. |
| **Trails** module on a Particle System | Trails behind many particles: sparks, fireworks, magic missiles. | One strip per particle, or ribbons connecting particles in order. |

[Bullet tracers](../combat/tracers.md) covers hitscan streaks and projectile trails in full. **Pooled projectiles** keep their trail from the last shot unless it is cleared. Call `trail.Clear()` when the projectile is taken from the pool, after it is moved to the muzzle, or the first frame draws a streak from where it last died.

**Sword swings.** A `TrailRenderer` on an empty at the blade tip, with **Emitting** off. Turn it on and off with the swing's hit window, from the same [animation events](../animation/events.md#a-relay-on-the-model) that open and close the hit box:

```csharp
relay.HitOpen += () => bladeTrail.emitting = true;
relay.HitClose += () => bladeTrail.emitting = false;
```

A trail from one point is a thin line. For a wide arc, use two points, base and tip, and build a mesh strip between their recent positions, or use a flipbook slash particle aligned to the swing.

## VFX Graph from code

A `VisualEffect` component plays a graph. Code talks to it through **exposed properties** and **events**:

```csharp
using UnityEngine;
using UnityEngine.VFX;

public class SwarmDriver : MonoBehaviour
{
    static readonly int TargetId = Shader.PropertyToID("Target");
    static readonly int IntensityId = Shader.PropertyToID("Intensity");

    [SerializeField] VisualEffect vfx;
    [SerializeField] Transform target;

    VFXEventAttribute _burstAttribute;

    void Start() => _burstAttribute = vfx.CreateVFXEventAttribute();

    void Update()
    {
        vfx.SetVector3(TargetId, target.position);
    }

    public void SetIntensity(float value) => vfx.SetFloat(IntensityId, value);

    public void BurstAt(Vector3 position)
    {
        _burstAttribute.SetVector3("position", position);
        vfx.SendEvent("Burst", _burstAttribute);
    }
}
```

- Property names must match the graph's **Blackboard** exactly, and the property must be **Exposed**. `HasFloat` and similar check first.
- Events start spawn contexts in the graph. `OnPlay` and `OnStop` exist by default; others are named in the graph.
- Reuse one `VFXEventAttribute`; creating one per event allocates.

## Performance

- **Overdraw** first. Large, overlapping, blended particles near the camera cost the most. Smaller particles, cropped textures, and the [Frame Debugger](../tools/profiler.md#cpu-or-gpu) show where.
- **Count** second. Lower **Max Particles** and emission at a distance.
- **CPU simulation** shows in the [Profiler](../tools/profiler.md) under the particle system update markers. Many small systems cost more than one shared one, which is why impacts share.
- **Culling**: keep systems procedural where possible, and use **Automatic** culling.
- **Collision** with the world is the expensive module. Use planes, or **Low** quality, or none.

!!! warning "Common pitfalls"

    **Local** simulation space on smoke from a moving object drags the whole plume along with it. Use **World**.

    A pooled effect with **Stop Action: Destroy** is destroyed while the pool still counts it as out. Use **Callback**.

    Emitting at a hit point into a **Local**-space system places particles relative to the system, not at the hit. Shared systems must be **World** space.

    A pooled projectile's trail streaks from its last position. `Clear()` it after placing it.

    `Clear()`, or `Stop` with **Stop Emitting And Clear**, removes every particle at once. `Stop` with its default, **Stop Emitting**, lets the live ones fade out.
