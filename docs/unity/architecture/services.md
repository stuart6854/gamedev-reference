---
engine: Unity
version: 6+
uses:
  - name: Open worlds
    text: Audio, saving, and settings that exist in every scene.
  - name: RPGs
    text: Game-wide systems such as quests and inventories reachable from any scene.
---

# Bootstrapping and services

Audio, saving, settings, and analytics are systems that every scene uses and no scene owns. They need to exist before anything asks for them, survive scene loads, exist exactly once, and still work when you press Play in whatever scene is open in the editor. This page compares the usual ways to get there, then builds the one that meets all four: a systems prefab spawned before the first scene wakes, and a small service locator that hands out interfaces.

The ordering facts this relies on are on the [MonoBehaviour lifecycle](lifecycle.md) page.

## Which approach

| Approach | How it works | Where it breaks |
| --- | --- | --- |
| **Scene-placed singleton** | A `static Instance` set in `Awake`, on an object in the first scene. | Pressing Play in any other scene has no instance. Reading `Instance` in another object's `Awake` races it. |
| **Lazy singleton** | `Instance` finds or creates the object on first access. | Works anywhere, but accessed during shutdown it creates a new object as the scene unloads. Every caller depends on the concrete class. |
| **Systems scene** | A scene of systems loaded additively at startup. | `SceneManager.LoadScene` finishes in the next frame, so the first scene's `Awake` and `Start` run before the systems exist. |
| **ScriptableObject channels and variables** | Assets that scenes share by reference, from [event systems](events.md) and [shared variables](variables.md). | Great for data and events. Not a home for something with a lifetime, like an `AudioSource`. |
| **Bootstrapper and locator** (this page) | A static method spawns a systems prefab before the first scene's `Awake`. Systems register an interface. | Every consumer must handle a missing service, which is also what makes tests and partial scenes work. |

A Core scene for UI and the loader, loaded additively under each level, is [scenes and loading](scenes.md). It complements this prefab rather than replacing it.

A dependency injection framework such as VContainer or Zenject is the next step past a locator. It is a package choice, and it is not covered here.

## Setup

1. Create an empty object named `Systems`. Add each system as a child, for example `AudioService` with an `AudioSource`.
2. Save it as a prefab at `Assets/Resources/Systems.prefab`. `Resources.Load` only finds assets under a folder named `Resources`.
3. Copy `Services` and `Bootstrapper`. Nothing needs to be placed in any scene.
4. Press Play in any scene. The **Hierarchy** shows `Systems` under **DontDestroyOnLoad**.
5. In gameplay code, ask `Services` for the interface where you use it, not for the concrete class.

## What each step is doing

`[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]` runs a static method after the first scene's objects are loaded into memory, but before any of their `Awake` calls. It runs in a build and on every entry to Play mode in the editor, in whichever scene is open. The bootstrapper instantiates the systems prefab there. `Instantiate` runs the prefab's `Awake` and `OnEnable` before it returns, so every system has registered before the first scene object wakes.

`DontDestroyOnLoad` moves the instance into a special scene that a normal scene load does not unload. It only works on root objects, which the instance is.

The locator is a dictionary from interface type to instance. A system registers in `Awake` and unregisters in `OnDestroy`. Registering a second instance of the same interface fails and returns `false`, so a duplicate can destroy itself. A destroyed Unity object still sitting in the dictionary is treated as missing, because Unity's `== null` is true for it.

`[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]` clears the dictionary at the very start of Play mode. With **Enter Play Mode Options** set to skip domain reload, static fields keep their values between Play sessions, so without the reset the second session would start with dead entries from the first.

## Scripts

### Service locator

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Interface type to instance. Systems register in Awake and unregister in OnDestroy.
/// </summary>
public static class Services
{
    static readonly Dictionary<Type, object> _services = new Dictionary<Type, object>();

    // With domain reload disabled, statics survive between Play sessions. Clear before anything registers.
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        _services.Clear();
    }

    /// <summary>False if a live instance of T is already registered. The caller should then destroy itself.</summary>
    public static bool Register<T>(T service) where T : class
    {
        if (service == null)
            throw new ArgumentNullException(nameof(service));

        if (_services.TryGetValue(typeof(T), out object existing) && IsAlive(existing) && !ReferenceEquals(existing, service))
        {
            Debug.LogWarning("A " + typeof(T).Name + " is already registered. Keeping the first.");
            return false;
        }

        _services[typeof(T)] = service;
        return true;
    }

    /// <summary>Removes the entry only if it is this instance, so a rejected duplicate cannot remove the original.</summary>
    public static void Unregister<T>(T service) where T : class
    {
        if (_services.TryGetValue(typeof(T), out object existing) && ReferenceEquals(existing, service))
            _services.Remove(typeof(T));
    }

    public static bool TryGet<T>(out T service) where T : class
    {
        if (_services.TryGetValue(typeof(T), out object found) && IsAlive(found))
        {
            service = (T)found;
            return true;
        }

        service = null;
        return false;
    }

    public static T Get<T>() where T : class
    {
        if (TryGet(out T service))
            return service;
        throw new InvalidOperationException(
            "No " + typeof(T).Name + " is registered. Is it on the Systems prefab under Resources?");
    }

    static bool IsAlive(object service)
    {
        // A destroyed component is not C# null, but Unity's == says it is.
        return !(service is UnityEngine.Object unityObject) || unityObject != null;
    }
}
```

### Bootstrapper

```csharp
using UnityEngine;

/// <summary>
/// Spawns Resources/Systems before the first scene's Awake, in a build and in any scene in the editor.
/// </summary>
public static class Bootstrapper
{
    const string SystemsPrefab = "Systems";

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
    static void SpawnSystems()
    {
        GameObject prefab = Resources.Load<GameObject>(SystemsPrefab);
        if (prefab == null)
        {
            Debug.LogWarning("No Resources/" + SystemsPrefab + " prefab. Services will be missing.");
            return;
        }

        GameObject systems = Object.Instantiate(prefab);
        systems.name = prefab.name;
        Object.DontDestroyOnLoad(systems);
    }
}
```

### A service

Consumers see the interface. The class behind it can change, or a test can register a fake, without touching a single caller.

```csharp
using UnityEngine;

public interface IAudioService
{
    void PlayUi(AudioClip clip);
}

[DisallowMultipleComponent]
[RequireComponent(typeof(AudioSource))]
public class AudioService : MonoBehaviour, IAudioService
{
    AudioSource _source;

    void Awake()
    {
        _source = GetComponent<AudioSource>();
        if (!Services.Register<IAudioService>(this))
            Destroy(gameObject);
    }

    void OnDestroy()
    {
        Services.Unregister<IAudioService>(this);
    }

    public void PlayUi(AudioClip clip)
    {
        if (clip != null)
            _source.PlayOneShot(clip);
    }
}
```

### A consumer

Resolve at the point of use. The service is there before any scene object wakes when the bootstrapper ran, but a test scene or a partial setup may not have it, and a cached reference outlives a service that was replaced.

```csharp
using UnityEngine;

public class ClickSound : MonoBehaviour
{
    [SerializeField] AudioClip click;

    public void Play()
    {
        if (Services.TryGet(out IAudioService audio))
            audio.PlayUi(click);
    }
}
```

## Systems that need the first scene

The bootstrapper runs before the scene wakes, so a system cannot find scene objects in its own `Awake`. A system that needs the scene, such as a music player that reads the level's track, subscribes to `SceneManager.sceneLoaded`. Unity raises it after the scene's `OnEnable` calls and before its `Start` calls, on every scene load, including the first.

!!! warning "Common pitfalls"

    `Resources.Load` only sees assets inside a folder named `Resources`, and everything in such a folder ships in the build whether it is used or not. Keep that folder to the one prefab.

    A system placed in a scene as well as on the prefab registers twice. The second `Register` returns false and the duplicate destroys itself. Without that check, the scene copy silently replaces the persistent one, and then dies on the next scene load.

    `OnDestroy` runs on every system when Play mode ends, in no fixed order. A system that calls another service from its own `OnDestroy` may find it gone. Use `TryGet` there, never `Get`.

    Do not cache a service in a static field of a consumer. With domain reload off, the static survives into the next Play session pointing at a destroyed object.

    `Get` throws when a service is missing, which is right for a service the game cannot run without. For optional ones, such as analytics, use `TryGet` and carry on.

    A locator hides dependencies: nothing in a class's fields says it needs audio. Keep the calls at the edges, in the few components that make noise, rather than in core logic, and that stays readable.
