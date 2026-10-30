---
engine: Unity
version: 6+
uses:
  - name: Shooters
    text: Bullets, impacts, and muzzle flashes reused instead of instantiated.
  - name: Hordes and crowds
    text: Enemies and their effects recycled during waves.
---

# Object pooling

`Instantiate` and `Destroy` allocate, and they can spike a frame. A pool creates the objects first and reuses them. The gun on the [weapons](../combat/weapons.md#projectiles) page already does this for its own shots. This page is the shared version: one registry for every prefab, reset hooks, and effects that return themselves.

A damage number is the same timed return as a hit effect. The popup itself is [damage numbers](../combat/damage-numbers.md).

## Why

| Approach | Use it when | Limit |
| --- | --- | --- |
| `Instantiate` and `Destroy` | The object is rare. A chest, a level piece, a menu. | A burst of them shows up as `GC.Alloc` and a spike in the Profiler. |
| `ObjectPool<T>` | The same prefab is created and destroyed in play. Projectiles, impacts, one-shot audio. | Every field that the last user wrote has to be reset. A pool hides that bug. |
| `ListPool` and the other collection pools | A method needs a list, a set, or a dictionary and can give it back before it returns. | The collection is shared. Using it after `Release` hands your data to the next caller. |
| Nothing | The Profiler does not show creation in the hot frame. | Pooling first makes a reset protocol you did not need. |

Profile before you add a pool. The CPU Usage module and the GC Alloc column are enough. One `Instantiate` of a huge prefab can cost more than a hundred reused bullets, and a pool does not make that prefab cheap to wake up.

`UnityEngine.Pool` is in the engine. There is no package. Entities, `ISystem`, and the job allocators are a different model. They are not this page.

## Setup

1. Save the prefab with its root **inactive**. `Instantiate` of an active prefab runs `OnEnable` before your code can stop it. A `NavMeshAgent` on the prefab should also be saved **disabled**. The inactive root has not run `Awake` before its first return to the pool, so the base class cannot disable the agent for it, and an enabled agent warns that it is not on the NavMesh when the instance first activates. `PooledAgent` enables it once the spawn point is sampled.
2. Add `PooledBehaviour`, or a subclass such as `PooledEffect`, on that root. A particle system that should return itself sits on **the same object** as the script. A system on a child does not send `OnParticleSystemStopped` to the parent. Set **Stop Action** to **Callback**. The script sets it again on spawn, so a prefab left on **Destroy** does not delete a pooled instance.
3. Add `PoolManager` to an object at the origin, scale `1`, not parented to the player or the camera. A moving parent carries every inactive instance, and a scaled parent scales the mesh.
4. Drop prefabs into **Prewarm**. The count is how many to create at `Start`. It must be at most **Max Size**, or the extras are destroyed as they come back.
5. Call `Spawn` with the project prefab, the same asset each time. An instance dragged from the Hierarchy is a different key, and it gets a second pool.
6. `PooledImpact` replaces `ImpactEffect` on the [weapons](../combat/weapons.md#holder-and-events) page. Copy `Weapon` and `WeaponHolder` first. The gun's own projectile pool stays where it is.

## Object pool

`ObjectPool<T>` stores inactive instances in a stack. `createFunc` builds one. `actionOnGet` runs when something takes it. `actionOnRelease` runs when it comes back, including when it will not be kept. `actionOnDestroy` runs for that discard, and when `Clear` empties the stack.

`defaultCapacity` is the stack's starting room. It does not create instances. `maxSize` is how many inactive instances are kept. Past that, `Release` still runs `actionOnRelease`, then `actionOnDestroy` instead of pushing. `collectionCheck` throws if the same instance is released while it is already on the stack. The check walks that stack, so leave it on while the calls are still wrong, and turn it off only if `Release` shows up in a profile.

`Get(out T)` returns a `PooledObject<T>`. Disposing it, which a `using` block does, calls `Release`. That is what you want for a list. It is the wrong scope for a projectile: the shot would return to the pool at the end of the method that fired it. A shot calls `Get()`, then `Release` later.

`createFunc` closes over the pool it is filling. The constructor does not call `createFunc`, so the assignment finishes before the first `Get`. Prewarm is that first `Get`.

```csharp
using UnityEngine;
using UnityEngine.Pool;

/// <summary>
/// One ObjectPool for one prefab. The manager owns these.
/// </summary>
public static class PoolFactory
{
    public static ObjectPool<PooledBehaviour> Create(
        GameObject prefab,
        Transform container,
        bool collectionCheck,
        int capacity,
        int maxSize)
    {
        ObjectPool<PooledBehaviour> pool = null;
        pool = new ObjectPool<PooledBehaviour>(
            createFunc: () => CreateInstance(prefab, container, pool),
            actionOnGet: item => item.MarkOut(),
            actionOnRelease: item => item.EnterPool(),
            actionOnDestroy: DestroyInstance,
            collectionCheck: collectionCheck,
            defaultCapacity: capacity,
            maxSize: maxSize);
        return pool;
    }

    static PooledBehaviour CreateInstance(GameObject prefab, Transform container, IObjectPool<PooledBehaviour> pool)
    {
        GameObject instance = Object.Instantiate(prefab, container);
        instance.SetActive(false);
        PooledBehaviour behaviour = instance.GetComponent<PooledBehaviour>();
        if (behaviour == null)
            behaviour = instance.AddComponent<PooledBehaviour>();
        behaviour.Bind(pool);
        return behaviour;
    }

    static void DestroyInstance(PooledBehaviour item)
    {
        if (item != null)
            Object.Destroy(item.gameObject);
    }
}
```

`ListPool<T>`, `HashSetPool<T>`, and `DictionaryPool<TKey, TValue>` are static `ObjectPool`s of collections. `Release` clears the collection. `CollectionPool<TCollection, TItem>` is the shared implementation. `GenericPool<T>` is one static pool for a plain class. It does not reset your fields. Two systems that both `Release` a `Scratch` will take each other's instance. A prefab does not belong there.

```csharp
using System.Collections.Generic;
using UnityEngine.Pool;

/// <summary>
/// Temporary collections. The using block returns them.
/// </summary>
public static class PoolScratch
{
    public static int Sum(int extra)
    {
        int total = extra;
        using (ListPool<int>.Get(out List<int> numbers))
        {
            numbers.Add(extra);
            total = numbers[0];
        }

        using (HashSetPool<int>.Get(out HashSet<int> seen))
        {
            seen.Add(total);
        }

        return total;
    }
}
```

`DictionaryPool<int, int>.Get(out Dictionary<int, int> map)` is the same shape. Do not return `numbers` from the method. After the brace it has been cleared and may already have been handed out again.

## Behaviour

`OnSpawn` runs after the instance is active. `OnEnable` has already run. `OnDespawn` runs while it is still active, and then the object is deactivated, which runs `OnDisable`. Subscribe in one of those pairs, not both, or the second shot double-fires.

The base reset clears a dynamic rigidbody, every `TrailRenderer`, coroutines, and a `NavMeshAgent`. An override that also needs this calls nothing special for those. `OnDespawn` is for the subclass: particles, audio, and listeners.

`_inPool` starts true. A brand-new instance is not checked out, so an `OnDisable` during `Instantiate` cannot `Release` into a pool that does not hold it yet. `MarkOut` runs from `actionOnGet`. `Release` sets the flag before the pool calls `EnterPool`, so a callback that releases again is ignored. `OnDestroy` does not `Release`. Scene unload destroys inactive children in an undefined order. Returning one then pushes a dead object, or calls into a pool that is already clearing.

```csharp
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.Pool;

public interface IPoolable
{
    void OnSpawn();
    void OnDespawn();
}

/// <summary>
/// Root of a pooled prefab. Subclasses override OnSpawn and OnDespawn.
/// </summary>
public class PooledBehaviour : MonoBehaviour, IPoolable
{
    IObjectPool<PooledBehaviour> _pool;
    bool _inPool = true;
    Rigidbody _body;
    TrailRenderer[] _trails;
    NavMeshAgent _agent;
    IPoolable[] _hooks;

    protected NavMeshAgent Agent => _agent;

    public void Bind(IObjectPool<PooledBehaviour> pool)
    {
        _pool = pool;
    }

    public void MarkOut()
    {
        _inPool = false;
    }

    void Awake()
    {
        _body = GetComponent<Rigidbody>();
        _trails = GetComponentsInChildren<TrailRenderer>(true);
        _agent = GetComponent<NavMeshAgent>();
    }

    public virtual void OnSpawn()
    {
    }

    public virtual void OnDespawn()
    {
    }

    public void Activate()
    {
        gameObject.SetActive(true);
        IPoolable[] hooks = Hooks();
        for (int i = 0; i < hooks.Length; i++)
        {
            if (hooks[i] != null)
                hooks[i].OnSpawn();
        }
    }

    // Found once per instance. Searching on every spawn would allocate an array each time.
    IPoolable[] Hooks()
    {
        if (_hooks == null)
            _hooks = GetComponentsInChildren<IPoolable>(true);
        return _hooks;
    }

    public void Release()
    {
        if (_inPool)
            return;

        _inPool = true;
        if (_pool != null)
            _pool.Release(this);
    }

    public void EnterPool()
    {
        _inPool = true;
        ResetMotion();

        IPoolable[] hooks = Hooks();
        for (int i = 0; i < hooks.Length; i++)
        {
            if (hooks[i] != null)
                hooks[i].OnDespawn();
        }

        if (gameObject.activeSelf)
            gameObject.SetActive(false);
    }

    public void ResetMotion()
    {
        if (_body != null && !_body.isKinematic)
        {
            _body.linearVelocity = Vector3.zero;
            _body.angularVelocity = Vector3.zero;
        }

        if (_trails != null)
        {
            for (int i = 0; i < _trails.Length; i++)
            {
                if (_trails[i] != null)
                    _trails[i].Clear();
            }
        }

        if (_agent != null)
        {
            if (_agent.isOnNavMesh)
                _agent.ResetPath();
            _agent.enabled = false;
        }

        StopAllCoroutines();
    }
}
```

`linearVelocity` is the Unity 6 name. `velocity` is obsolete. `angularVelocity` was not renamed. Writing either speed on a kinematic body logs a warning, so the kinematic body is left alone.

The pose is set **before** `Activate`. `actionOnGet` only marks the instance out. Turning it on inside `actionOnGet` would record a trail point at the old position, and the next move would draw a line across the map. `TrailRenderer.Clear` on the way in is the other half. Clear after the teleport as well if a subclass moves the transform again in `OnSpawn`.

## Registry and self-return

The manager's key is the prefab asset. Each key has its own pool and a container child, so inactive shells are not scattered at the world origin and are not parented to the gun. The [weapon](../combat/weapons.md#projectiles) keeps a separate `ObjectPool<Projectile>` on the gun, with the same four callbacks, because those shots must survive the gun being disabled. Do not also parent them here.

`Spawn` takes an instance, sets the world pose, then activates. `Prewarm` takes and immediately releases, so `OnSpawn` does not run and particle systems do not play. `Release` on the instance is the self-return. Lifetime, a collision, a finished particle system, and a finished clip all call it. Do not disable the manager. Instances that are out are still its children, and a disabled parent deactivates them.

A particle callback needs **Stop Action: Callback**. `OnParticleSystemStopped` is only sent to scripts on that particle system's object. `Stop` during `EnterPool` can send it immediately. The flag set at the start of `Release` drops that second call. **Destroy** and **Disable** are the wrong stop actions: Destroy removes the instance while the pool still thinks it is out, and Disable is not `Release`.

`AudioSource.PlayOneShot` does not set `isPlaying`, and it does not replace `clip`. `Spawn` the prefab, then call `Play`. Time the return from `clip.length` after that. A looping source never finishes. `OnDespawn` calls `Stop`.

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Pool;

[Serializable]
public struct PoolPrewarm
{
    public GameObject prefab;
    public int count;
}

/// <summary>
/// One pool per prefab asset. Spawn with that asset, not with an instance.
/// </summary>
[DisallowMultipleComponent]
public class PoolManager : MonoBehaviour
{
    [SerializeField] PoolPrewarm[] prewarm = Array.Empty<PoolPrewarm>();
    [SerializeField] bool collectionCheck = true;
    [SerializeField] int defaultCapacity = 16;
    [SerializeField] int maxSize = 64;

    readonly Dictionary<GameObject, ObjectPool<PooledBehaviour>> _pools =
        new Dictionary<GameObject, ObjectPool<PooledBehaviour>>();

    void Start()
    {
        if (prewarm == null)
            return;

        for (int i = 0; i < prewarm.Length; i++)
            Prewarm(prewarm[i].prefab, prewarm[i].count);
    }

    void OnDestroy()
    {
        foreach (var pair in _pools)
        {
            if (pair.Value != null)
                pair.Value.Clear();
        }

        _pools.Clear();
    }

    public PooledBehaviour Spawn(GameObject prefab, Vector3 position, Quaternion rotation)
    {
        if (prefab == null)
            return null;

        PooledBehaviour item = GetOrCreate(prefab).Get();
        item.transform.SetPositionAndRotation(position, rotation);
        item.Activate();
        return item;
    }

    public void Prewarm(GameObject prefab, int count)
    {
        if (prefab == null || count <= 0)
            return;

        ObjectPool<PooledBehaviour> pool = GetOrCreate(prefab);
        using (ListPool<PooledBehaviour>.Get(out List<PooledBehaviour> held))
        {
            int keep = Mathf.Min(count, Mathf.Max(1, maxSize));
            for (int i = 0; i < keep; i++)
                held.Add(pool.Get());
            for (int i = 0; i < held.Count; i++)
                held[i].Release();
        }
    }

    ObjectPool<PooledBehaviour> GetOrCreate(GameObject prefab)
    {
        if (_pools.TryGetValue(prefab, out ObjectPool<PooledBehaviour> existing))
            return existing;

        var containerObject = new GameObject(prefab.name + " Pool");
        containerObject.transform.SetParent(transform, false);
        int capacity = Mathf.Max(1, defaultCapacity);
        int limit = Mathf.Max(capacity, maxSize);
        ObjectPool<PooledBehaviour> pool = PoolFactory.Create(
            prefab,
            containerObject.transform,
            collectionCheck,
            capacity,
            limit);
        _pools.Add(prefab, pool);
        return pool;
    }
}
```

```csharp
using UnityEngine;

/// <summary>
/// Hit effect or any particle prefab. Lifetime and the stop callback both return it.
/// </summary>
[DisallowMultipleComponent]
public class PooledEffect : PooledBehaviour
{
    [SerializeField] ParticleSystem particles;
    [SerializeField] float lifetime = 2f;

    float _diesAt = float.PositiveInfinity;

    public override void OnSpawn()
    {
        _diesAt = Time.time + lifetime;
        if (particles == null)
            particles = GetComponent<ParticleSystem>();
        if (particles == null)
            return;

        ParticleSystem.MainModule main = particles.main;
        main.stopAction = ParticleSystemStopAction.Callback;
        particles.Clear(true);
        particles.Play(true);
    }

    public override void OnDespawn()
    {
        _diesAt = float.PositiveInfinity;
        if (particles != null)
            particles.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
    }

    void Update()
    {
        if (Time.time >= _diesAt)
            Release();
    }

    void OnParticleSystemStopped()
    {
        Release();
    }
}
```

A subclass that declares `Awake` replaces the base `Awake`. Unity does not call both. `PooledAgent` does not declare one, so the base cache runs and `Agent` is set. `PooledEffect` looks the particle system up in `OnSpawn` for the same reason.

```csharp
using UnityEngine;

/// <summary>
/// Returns the pooled root when this collider hits something.
/// One body in the pair has to be a non-kinematic rigidbody.
/// </summary>
[DisallowMultipleComponent]
public class ReleaseOnCollision : MonoBehaviour
{
    PooledBehaviour _root;

    void Awake()
    {
        _root = GetComponentInParent<PooledBehaviour>();
    }

    void OnCollisionEnter(Collision collision)
    {
        if (_root != null)
            _root.Release();
    }
}
```

```csharp
using UnityEngine;

/// <summary>
/// One clip, then back to the pool. PlayOneShot does not flip isPlaying.
/// </summary>
[DisallowMultipleComponent]
public class PooledAudio : PooledBehaviour
{
    [SerializeField] AudioSource source;
    float _diesAt;
    bool _playing;

    public void Play(AudioClip clip, float volume)
    {
        if (clip == null)
            return;
        if (source == null)
            source = GetComponent<AudioSource>();
        if (source == null)
            return;

        source.loop = false;
        source.clip = clip;
        source.volume = volume;
        source.Play();
        _diesAt = Time.time + clip.length;
        _playing = true;
    }

    public override void OnDespawn()
    {
        _playing = false;
        if (source != null)
            source.Stop();
    }

    void Update()
    {
        if (_playing && Time.time >= _diesAt)
            Release();
    }
}
```

```csharp
using UnityEngine;
using UnityEngine.AI;

/// <summary>
/// Enable the agent only when the spawn point is on the mesh.
/// The base class disables it on the way back in.
/// </summary>
[DisallowMultipleComponent]
public class PooledAgent : PooledBehaviour
{
    public override void OnSpawn()
    {
        if (Agent == null)
            return;
        if (!NavMesh.SamplePosition(transform.position, out NavMeshHit hit, 2f, NavMesh.AllAreas))
            return;

        Agent.enabled = true;
        Agent.Warp(hit.position);
    }
}
```

## Hit effects

`ImpactEffect` on the weapons page `Instantiate`s a prefab and `Destroy`s it after two seconds. That is the path a busy gun should not take. `PooledImpact` subscribes the same way and calls `Spawn`. The prefab is a `PooledEffect`.

The projectile pool on the weapon is the worked shot. `BuildPool` there is `PoolFactory` without the registry: `OnGet` activates, `Launch` writes `linearVelocity`, and `Release` zeros it before the instance is disabled. Copy that class if the shot is the weapon's. Use the registry for the impact, the audio, and any second gun that should share those prefabs.

A damage number would `Spawn` at the hit point and `Release` from a lifetime, which is `PooledEffect` with a different prefab. Drawing the digits, and merging rapid hits, is [damage numbers](../combat/damage-numbers.md).

```csharp
using UnityEngine;

/// <summary>
/// Pooled replacement for ImpactEffect. The prefab is a PooledEffect.
/// </summary>
[DisallowMultipleComponent]
public class PooledImpact : MonoBehaviour
{
    [SerializeField] WeaponHolder holder;
    [SerializeField] PoolManager pools;
    [SerializeField] GameObject prefab;

    void OnEnable()
    {
        if (holder == null || holder.Weapons == null)
            return;

        Weapon[] list = holder.Weapons;
        for (int i = 0; i < list.Length; i++)
        {
            if (list[i] != null)
                list[i].Impact += Spawn;
        }
    }

    void OnDisable()
    {
        if (holder == null || holder.Weapons == null)
            return;

        Weapon[] list = holder.Weapons;
        for (int i = 0; i < list.Length; i++)
        {
            if (list[i] != null)
                list[i].Impact -= Spawn;
        }
    }

    void Spawn(Vector3 point, Vector3 normal)
    {
        if (pools == null || prefab == null)
            return;
        if (normal.sqrMagnitude < 0.0001f)
            normal = Vector3.up;

        pools.Spawn(prefab, point, Quaternion.LookRotation(normal));
    }
}
```

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Prewarm count | `0` | Instances created at `Start`, then released. Capped by max size. |
| Collection Check | On | Throws if an instance is released while it is already inactive in the pool. |
| Default Capacity | `16` | Stack room. Not a prewarm. |
| Max Size | `64` | Inactive instances kept. Further returns are destroyed. |
| Lifetime | `2` | Seconds before `PooledEffect` releases, even if the particles loop. |

## Pitfalls

!!! warning "Common pitfalls"

    `using (pool.Get(out shot))` returns the shot when the block ends. Lists want that. Projectiles do not.

    Two `Release` calls without the flag throw under `collectionCheck` only if the first one already pushed the instance. A callback during `EnterPool` happens before the push. The flag is what ignores that call. `OnDisable` must not `Release`. Deactivating is what `EnterPool` does, so the disable would release again.

    Forgetting the rigidbody leaves the last `linearVelocity` on the next shot. The weapons page zeros it for the same reason. A trail that is not cleared draws from the old point to the new one. Clear on the way in, and set the pose before `SetActive(true)`. Coroutines are stopped on disable and do not resume. Start them from `OnSpawn`, not from `Awake`.

    A listener added in `OnEnable` and again in `OnSpawn` runs twice. Unsubscribe in the matching method. The [event](events.md) page has the subscribe rules.

    `OnDestroy` is not a release. `Clear` destroys inactive instances and leaves active ones to the scene load. Releasing either pushes a destroyed object. Unity's `== null` is true for those, and `actionOnDestroy` has to check it before `Destroy`.

    `maxSize` destroys the extra instance after `actionOnRelease`. A prewarm larger than that cap does not stay resident. `defaultCapacity` does not create anything.

    A `NavMeshAgent` left enabled off the mesh logs an error on the next `SetDestination`. Reset the path only when `isOnNavMesh` is true, disable on the way in, and `Warp` after `SamplePosition` on the way out. The [enemy](../ai/enemy.md) page uses that sample. The agent type still has `velocity`. Unity 6 did not rename it. `linearVelocity` is the rigidbody.

    The `IPoolable` hooks are found once per instance and cached. Components added to an instance at runtime, after its first spawn, are not in that cache. Add them to the prefab instead.

    `GenericPool<T>` and the collection pools are process-wide. `ListPool` inside a job is the wrong allocator. Jobs and Entities are out of scope here.
