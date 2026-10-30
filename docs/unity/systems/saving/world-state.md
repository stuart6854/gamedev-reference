---
engine: Unity
version: 6+
uses:
  - name: Top-down survival
    text: Looted containers stay empty, broken doors stay broken, and dropped items stay where they fell.
  - name: Open worlds
    text: Chunks that unload keep their state in memory, then in the save.
  - name: Base building
    text: Placed pieces are spawned objects, saved with their prefab key and position.
---

# World state

The [save system](save-system.md) saves the player. This page saves the scene: which doors are open, what is left in a crate, which pickups are gone, and what the player built or dropped. It also covers scenes that load and unload while playing, such as streamed chunks.

## Ids and records

The level file already holds every placed object. A save only needs what changed, keyed by an id that is the same every time the level loads.

| Object | In the scene file? | Saved as |
| --- | --- | --- |
| **Placed** — a door, a crate, a pickup put down in the editor | Yes | Its id and its components' state. If it was destroyed, its id in the `destroyed` list. |
| **Spawned** — a dropped item, a built wall, a corpse | No | Its id, its prefab key, its position, and its components' state. |

The `InstanceID` and the hierarchy path are not ids. The first changes every session, and the second changes when someone renames a parent. A `SaveId` component holds a GUID string, made once in the editor.

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

public partial class SaveGame
{
    public List<ObjectRecord> objects = new List<ObjectRecord>();
    // Placed objects that are gone for good. The scene file would bring them back otherwise.
    public List<string> destroyed = new List<string>();
}

[Serializable]
public class ObjectRecord
{
    public string id;
    public string scene;
    public string prefab; // empty for placed objects
    public bool active = true;
    public bool hasTransform;
    public Vector3 position;
    public Quaternion rotation = Quaternion.identity;
    public List<ComponentRecord> components = new List<ComponentRecord>();
}

/// <summary>One component's state, as its own JSON string. Each component owns its format.</summary>
[Serializable]
public class ComponentRecord
{
    public string key;
    public string json;
}

/// <summary>
/// A component that has state to save. The key tells two components on one object apart.
/// </summary>
public interface ISaveState
{
    string SaveKey { get; }
    string CaptureJson();
    void RestoreJson(string json);
}
```

Each component writing its own JSON string keeps `SaveGame` free of every game type. A door's record does not need a field in `SaveGame`, and a component removed from the game leaves a record nothing reads, which is harmless.

## Save id

```csharp
using System;
using UnityEngine;
#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.SceneManagement;
#endif

/// <summary>
/// A stable id for a scene object. Placed objects get one in the editor. Spawned objects get one from WorldSave.Spawn.
/// </summary>
[DisallowMultipleComponent]
public class SaveId : MonoBehaviour
{
    [SerializeField] string id;
    [Tooltip("Save position and rotation. Always on for spawned objects.")]
    [SerializeField] bool saveTransform;

    public string Id => id;
    public string PrefabKey { get; private set; }
    public bool IsSpawned => !string.IsNullOrEmpty(PrefabKey);
    public bool SavesTransform => saveTransform || IsSpawned;

    public void AssignRuntime(string newId, string prefabKey)
    {
        id = newId;
        PrefabKey = prefabKey;
    }

#if UNITY_EDITOR
    void OnValidate()
    {
        if (Application.isPlaying)
            return;
        // Prefab assets and Prefab Mode keep no id. Each instance placed in a scene gets its own.
        if (PrefabUtility.IsPartOfPrefabAsset(this) || PrefabStageUtility.GetPrefabStage(gameObject) != null)
            return;

        // OnValidate may not change other objects or call Find. Do it after the inspector update.
        EditorApplication.delayCall += AssignIfNeeded;
    }

    void AssignIfNeeded()
    {
        if (this == null || Application.isPlaying)
            return;
        if (!string.IsNullOrEmpty(id) && !IsDuplicate())
            return;

        Undo.RecordObject(this, "Assign Save Id");
        id = Guid.NewGuid().ToString("N");
        PrefabUtility.RecordPrefabInstancePropertyModifications(this);
        EditorUtility.SetDirty(this);
    }

    bool IsDuplicate()
    {
        // Ctrl+D copies the id. The copy sees the original and takes a new one.
        foreach (SaveId other in FindObjectsByType<SaveId>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            if (other != this && other.id == id)
                return true;
        }
        return false;
    }
#endif
}
```

- The duplicate check only sees scenes open at the time. An object copied from one scene to another while the first is closed keeps the same id. Give level designers a menu item that opens every level and lists duplicates, or key ids by scene as well.
- Once a build has shipped, never regenerate ids. A new id is a new object, and the old record is ignored.

## Prefab catalogue

Spawned objects are rebuilt from a key. The catalogue is the only place keys meet prefabs, like the [item catalogue](../inventory/index.md#save-records).

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

[CreateAssetMenu(fileName = "PrefabCatalogue", menuName = "Game/Prefab Catalogue")]
public class PrefabCatalogue : ScriptableObject
{
    [Serializable]
    public struct Entry
    {
        public string key;
        public SaveId prefab;
    }

    [SerializeField] Entry[] entries = Array.Empty<Entry>();

    Dictionary<string, SaveId> _byKey;

    void OnEnable() => _byKey = null;

    public bool TryGet(string key, out SaveId prefab)
    {
        if (_byKey == null)
        {
            _byKey = new Dictionary<string, SaveId>(StringComparer.Ordinal);
            foreach (Entry entry in entries)
            {
                if (!string.IsNullOrEmpty(entry.key) && entry.prefab != null && !_byKey.ContainsKey(entry.key))
                    _byKey.Add(entry.key, entry.prefab);
            }
        }

        prefab = null;
        return !string.IsNullOrEmpty(key) && _byKey.TryGetValue(key, out prefab);
    }
}
```

## World save

`WorldSave` keeps a record list per scene in memory. A scene's list is refreshed when the scene unloads and when the game saves, and applied when the scene loads. That is what keeps a chunk the player walked away from as they left it, before any file is written.

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

/// <summary>
/// Saves placed and spawned objects with a SaveId, per scene.
/// Call CaptureScene before unloading any scene.
/// </summary>
public static class WorldSave
{
    public static PrefabCatalogue Prefabs { get; set; }

    static readonly Dictionary<string, List<ObjectRecord>> s_byScene = new Dictionary<string, List<ObjectRecord>>();
    static readonly HashSet<string> s_destroyed = new HashSet<string>();
    static readonly HashSet<string> s_restored = new HashSet<string>();

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        Prefabs = null;
        s_byScene.Clear();
        s_destroyed.Clear();
        s_restored.Clear();
    }

    // After SubsystemRegistration, so SaveManager's reset has already cleared its events.
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
    static void Subscribe()
    {
        SaveManager.Capturing += Capture;
        SaveManager.Preparing += Prepare;
        SaveManager.Restoring += RestoreLoaded;

        // SceneManager's events survive Enter Play Mode without a domain reload. Remove before adding.
        SceneManager.sceneLoaded -= OnSceneLoaded;
        SceneManager.sceneLoaded += OnSceneLoaded;
        SceneManager.sceneUnloaded -= OnSceneUnloaded;
        SceneManager.sceneUnloaded += OnSceneUnloaded;
    }

    /// <summary>Instantiates a saved prefab with a new id. The scene defaults to the active scene.</summary>
    public static GameObject Spawn(string prefabKey, Vector3 position, Quaternion rotation, Scene scene = default)
    {
        SaveId instance = Instantiate(prefabKey, position, rotation, scene);
        if (instance == null)
            return null;
        instance.AssignRuntime(Guid.NewGuid().ToString("N"), prefabKey);
        return instance.gameObject;
    }

    /// <summary>Call before destroying a placed object that should stay gone, such as a picked-up item.</summary>
    public static void MarkDestroyed(SaveId target)
    {
        if (target != null && !target.IsSpawned && !string.IsNullOrEmpty(target.Id))
            s_destroyed.Add(target.Id);
    }

    /// <summary>Copies a scene's objects into memory. Call right before UnloadSceneAsync.</summary>
    public static void CaptureScene(Scene scene)
    {
        // During a load, the scene going away belongs to the game being replaced.
        if (SaveManager.IsRestoring || !scene.IsValid() || !scene.isLoaded)
            return;

        var records = new List<ObjectRecord>();
        foreach (SaveId target in InScene(scene))
        {
            if (!string.IsNullOrEmpty(target.Id))
                records.Add(Record(target));
        }
        s_byScene[scene.path] = records;
    }

    static void Capture(SaveGame save)
    {
        for (int i = 0; i < SceneManager.sceneCount; i++)
            CaptureScene(SceneManager.GetSceneAt(i));

        save.objects.Clear();
        foreach (List<ObjectRecord> records in s_byScene.Values)
            save.objects.AddRange(records);

        save.destroyed.Clear();
        save.destroyed.AddRange(s_destroyed);
    }

    static void Prepare(SaveGame save)
    {
        s_byScene.Clear();
        s_destroyed.Clear();
        s_restored.Clear();

        foreach (string id in save.destroyed)
            s_destroyed.Add(id);

        foreach (ObjectRecord record in save.objects)
        {
            if (record == null || string.IsNullOrEmpty(record.scene))
                continue;
            if (!s_byScene.TryGetValue(record.scene, out List<ObjectRecord> list))
                s_byScene[record.scene] = list = new List<ObjectRecord>();
            list.Add(record);
        }
    }

    static void OnSceneLoaded(Scene scene, LoadSceneMode mode) => RestoreScene(scene);
    static void OnSceneUnloaded(Scene scene) => s_restored.Remove(scene.path);

    /// <summary>Scenes loaded before the save was read, such as Core.</summary>
    static void RestoreLoaded(SaveGame save)
    {
        for (int i = 0; i < SceneManager.sceneCount; i++)
            RestoreScene(SceneManager.GetSceneAt(i));
    }

    static void RestoreScene(Scene scene)
    {
        if (!scene.IsValid() || !scene.isLoaded || !s_restored.Add(scene.path))
            return;

        var placed = new Dictionary<string, SaveId>(StringComparer.Ordinal);
        foreach (SaveId target in InScene(scene))
        {
            if (target.IsSpawned)
                Object.Destroy(target.gameObject); // left over from the game being replaced
            else if (!string.IsNullOrEmpty(target.Id))
                placed[target.Id] = target;
        }

        foreach (KeyValuePair<string, SaveId> pair in placed)
        {
            if (s_destroyed.Contains(pair.Key))
                Object.Destroy(pair.Value.gameObject);
        }

        if (!s_byScene.TryGetValue(scene.path, out List<ObjectRecord> records))
            return;

        foreach (ObjectRecord record in records)
        {
            SaveId target;
            if (!string.IsNullOrEmpty(record.prefab))
            {
                target = Instantiate(record.prefab, record.position, record.rotation, scene);
                if (target == null)
                    continue;
                target.AssignRuntime(record.id, record.prefab);
            }
            else if (!placed.TryGetValue(record.id, out target) || s_destroyed.Contains(record.id))
            {
                continue; // removed from the level since the save, or destroyed
            }

            Apply(target, record);
        }
    }

    static ObjectRecord Record(SaveId target)
    {
        var record = new ObjectRecord
        {
            id = target.Id,
            scene = target.gameObject.scene.path,
            prefab = target.PrefabKey ?? string.Empty,
            active = target.gameObject.activeSelf,
            hasTransform = target.SavesTransform,
            position = target.transform.position,
            rotation = target.transform.rotation
        };

        foreach (ISaveState state in target.GetComponents<ISaveState>())
            record.components.Add(new ComponentRecord { key = state.SaveKey, json = state.CaptureJson() });
        return record;
    }

    static void Apply(SaveId target, ObjectRecord record)
    {
        if (record.hasTransform)
        {
            if (target.TryGetComponent(out NavMeshAgent agent) && agent.enabled)
                agent.Warp(record.position); // setting the transform alone is undone by the agent
            else
                target.transform.position = record.position;
            target.transform.rotation = record.rotation;
        }

        foreach (ISaveState state in target.GetComponents<ISaveState>())
        {
            ComponentRecord match = record.components.Find(c => c.key == state.SaveKey);
            if (match != null)
                state.RestoreJson(match.json);
        }

        target.gameObject.SetActive(record.active);
    }

    static SaveId Instantiate(string prefabKey, Vector3 position, Quaternion rotation, Scene scene)
    {
        if (Prefabs == null || !Prefabs.TryGet(prefabKey, out SaveId prefab))
        {
            Debug.LogWarning("No prefab for save key '" + prefabKey + "'.");
            return null;
        }

        SaveId instance = Object.Instantiate(prefab, position, rotation);
        if (scene.IsValid() && scene.isLoaded && instance.gameObject.scene != scene)
            SceneManager.MoveGameObjectToScene(instance.gameObject, scene);
        return instance;
    }

    static IEnumerable<SaveId> InScene(Scene scene)
    {
        foreach (SaveId target in Object.FindObjectsByType<SaveId>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            if (target.gameObject.scene == scene)
                yield return target;
        }
    }
}
```

Set the catalogue from the Core scene:

```csharp
using UnityEngine;

public class WorldSaveSetup : MonoBehaviour
{
    [SerializeField] PrefabCatalogue prefabs;

    void Awake() => WorldSave.Prefabs = prefabs;
}
```

- `SaveId` sits on the root of the object. A spawned object moved under another object's hierarchy is still found, but its record is restored at the root of the scene.
- `FindObjectsByType` walks every object once per scene load and save. For tens of thousands of saved objects, keep a static registry that `SaveId` joins in `Awake` and leaves in `OnDestroy`. `Awake` does not run on objects that start inactive, so those still need a find.
- `sceneLoaded` runs after `Awake` and `OnEnable` and before `Start`. A component whose `Start` sets up state, such as starting loot, has to apply its restore after that. The container below does.

## Capture when a scene unloads

`sceneUnloaded` runs after the objects are gone, so capture has to happen first. In the [scene loader](../../architecture/scenes.md#scene-loader), add one line before the unload:

```csharp
// SceneLoader.Load, before UnloadSceneAsync(CurrentLevel):
WorldSave.CaptureScene(CurrentLevel);
```

Whatever streams chunks does the same before it unloads one. Without it, walking away from a chunk and back resets it to the scene file, while a save made before leaving still had the changes.

The records for chunks the player has left stay in memory until the next load, and go into every save. That grows with the explored map, not with what is loaded, which is usually fine. For a very large world, write each chunk's records to its own file when it unloads and read it back when it loads.

## Examples

### A door

A fragment inside a door component. The state is a small struct, written with `JsonUtility`.

```csharp
// In a Door : MonoBehaviour, ISaveState, with fields bool open and bool locked,
// and a SetOpen(bool open, bool instant) method that moves the door and updates its obstacle.
[Serializable]
struct DoorState
{
    public bool open;
    public bool locked;
}

public string SaveKey => "door";

public string CaptureJson() => JsonUtility.ToJson(new DoorState { open = open, locked = locked });

public void RestoreJson(string json)
{
    DoorState state = JsonUtility.FromJson<DoorState>(json);
    locked = state.locked;
    SetOpen(state.open, instant: true); // no animation or sound on load
}
```

Restore through the same method gameplay uses, so the NavMesh obstacle, the collider, and anything else the door drives follow. Skip effects and sounds on load.

### A container

A crate with a [list inventory](../inventory/list.md) and a "searched" flag. The bag adds its starting stacks in `Start`, so the restore waits until after that.

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Saves a container's contents and whether the player has searched it.
/// </summary>
[DefaultExecutionOrder(100)] // Start after ListInventory.Start has added the starting items
[RequireComponent(typeof(ListInventory))]
public class ContainerSave : MonoBehaviour, ISaveState
{
    [SerializeField] ItemCatalogue catalogue;

    [Serializable]
    class State
    {
        public bool searched;
        public List<ItemRecord> items = new List<ItemRecord>();
    }

    public bool Searched { get; set; }
    public string SaveKey => "container";

    State _pending;
    bool _started;

    ListInventory Bag => GetComponent<ListInventory>();

    void Start()
    {
        _started = true;
        if (_pending != null)
            Apply(_pending);
        _pending = null;
    }

    public string CaptureJson()
    {
        // Not started yet, as in a chunk saved the frame it loaded: the pending state is the truth.
        if (_pending != null)
            return JsonUtility.ToJson(_pending);

        var state = new State { searched = Searched };
        foreach (ItemInstance item in Bag.Stacks)
            state.items.Add(catalogue.ToRecord(item));
        return JsonUtility.ToJson(state);
    }

    public void RestoreJson(string json)
    {
        State state = JsonUtility.FromJson<State>(json);
        if (_started)
            Apply(state);
        else
            _pending = state; // inactive objects also wait here until they first enable
    }

    void Apply(State state)
    {
        Searched = state.searched;

        ListInventory bag = Bag;
        for (int i = bag.Stacks.Count - 1; i >= 0; i--)
            bag.TryRemoveInstance(bag.Stacks[i]);

        foreach (ItemRecord line in state.items)
        {
            ItemInstance item = catalogue.FromRecord(line);
            if (item != null)
                bag.TryAdd(new ItemStack(item), out _);
        }
    }
}
```

### Pickups and drops

```csharp
// Picking up a placed or spawned item:
WorldSave.MarkDestroyed(saveId); // no-op for spawned objects
Destroy(saveId.gameObject);

// Dropping one:
WorldSave.Spawn("pickup_bandage", dropPoint, Quaternion.identity);
```

A spawned object that is destroyed needs no mark. It is simply missing at the next capture.

## Setup

1. Add `SaveId` to every object with state: doors, containers, pickups, switches. The id appears when the component is added. Tick **Save Transform** on placed objects that move, such as a pushable crate.
2. Add `SaveId` to every prefab that can be spawned at runtime, and list it in a **Prefab Catalogue** with a key that never changes.
3. Add `WorldSaveSetup` to the Core scene with the catalogue.
4. Add `WorldSave.CaptureScene` before every `UnloadSceneAsync`.
5. Implement `ISaveState` on components with state. Give two such components on one object different keys.

!!! warning "Common pitfalls"

    Duplicating an object in the hierarchy duplicates its id. The editor code catches this for open scenes; check across scenes before release.

    Saving a reference to another object, such as "the door this switch opens", saves an instance id that is meaningless next session. Save the other object's `SaveId` string and look it up.

    A component that sets up in `Start` overwrites a restore applied in `sceneLoaded`. Hold the state until `Start`, as `ContainerSave` does.

    Unloading a chunk without `CaptureScene` resets it to the scene file the next time it loads.

    Setting `transform.position` on an object with an enabled `NavMeshAgent` is pulled back by the agent. Use `Warp`.

    Changing a prefab key or a scene path after release orphans every record that used it. Map the old value in a [migration](versioning.md#content-ids).
