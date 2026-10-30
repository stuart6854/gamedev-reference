---
engine: Unity
version: 6+
uses:
  - name: Top-down survival
    text: Autosave on a timer, blocked while in combat or dead.
  - name: RPGs
    text: Several manual slots plus an autosave, each with a date and play time.
  - name: Open worlds
    text: One save that names the level to load, then puts the player back.
---

# Save system

A `SaveGame` class of plain fields, a `SaveStore` that writes it to disk without ever leaving a half-written file, and a `SaveManager` that asks the game to fill it, writes it, and puts it back after the level loads. Doors, containers, and anything else that lives in a scene are on [world state](world-state.md). Changing `SaveGame` after release is [versioning](versioning.md).

The manager loads levels through the [scene loader](../../architecture/scenes.md#scene-loader) and lives in the Core scene next to it.

## What JsonUtility can write

`JsonUtility` uses Unity's own serializer, so it writes what the inspector would show:

- Public fields, and private fields with `[SerializeField]`. Not properties, static fields, or `readonly` fields.
- `int`, `float`, `bool`, `string`, enums, `Vector3`, `Quaternion`, `Color`, and `[Serializable]` classes and structs.
- Arrays and `List<T>` of those. Not dictionaries, multidimensional arrays, or a list of lists. Use a list of `{key, value}` records instead of a dictionary, and wrap an inner list in a class.
- A field of a base type is written as the base type. Subclass fields are lost. Avoid polymorphism in save data; a type id string plus a JSON string per entry, as [world state](world-state.md#ids-and-records) does, is simpler to migrate than `[SerializeReference]`.
- A reference to a `ScriptableObject`, prefab, or `GameObject` is written as an instance id, which is only valid in the session that wrote it. Write ids you own instead.

`JsonUtility.FromJson` creates the object with its field initializers, then overwrites the fields the JSON has. A field the JSON lacks keeps its initializer. That is what makes adding fields free in [versioning](versioning.md#free-changes).

## Data

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// One save file. Plain fields only. Partial, so other pages add their own fields.
/// </summary>
[Serializable]
public partial class SaveGame
{
    public int version;
    public string savedAtUtc;
    public float playTimeSeconds;
    public string activeScene;
    public PlayerRecord player = new PlayerRecord();
}

[Serializable]
public class PlayerRecord
{
    // False in a new game, so the level's own spawn point is used.
    public bool present;
    public Vector3 position;
    public Quaternion rotation = Quaternion.identity;
    public float healthFraction = 1f;
    public List<ItemRecord> inventory = new List<ItemRecord>();
}
```

`ItemRecord` is the record from [inventory](../inventory/index.md#save-records). Health is saved as a fraction of max, so a max-health change in a patch does not leave the player over or under the bar.

## Writing files

`SaveStore` is file IO only. It does not touch the game.

A save is written to `slot.json.tmp` first. Only when that write has finished is it swapped into place, and the old file becomes `slot.json.bak`. A crash or power cut mid-write leaves the old save, not half of the new one. Reading tries the main file, then the backup.

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;

/// <summary>
/// Save files in persistentDataPath/saves. Writes go through a temp file and keep a backup.
/// </summary>
public static class SaveStore
{
    const string Extension = ".json";

    public static string Folder => Path.Combine(Application.persistentDataPath, "saves");

    /// <summary>Letters, digits, '-' and '_'. Keeps slot names safe as file names on every platform.</summary>
    public static bool IsValidSlot(string slot)
    {
        if (string.IsNullOrEmpty(slot) || slot.Length > 64)
            return false;
        foreach (char c in slot)
        {
            if (!char.IsLetterOrDigit(c) && c != '-' && c != '_')
                return false;
        }
        return true;
    }

    public static string PathFor(string slot) => Path.Combine(Folder, slot + Extension);

    public static void Write(string slot, string json) => WriteFile(PathFor(slot), json);

    /// <summary>The path is resolved here, on the main thread. Only the file IO runs on the thread pool.</summary>
    public static Task WriteAsync(string slot, string json)
    {
        string path = PathFor(slot);
        return Task.Run(() => WriteFile(path, json));
    }

    static void WriteFile(string path, string json)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path));
        string temp = path + ".tmp";
        File.WriteAllText(temp, json, new UTF8Encoding(false));

        if (File.Exists(path))
            File.Replace(temp, path, path + ".bak");
        else
            File.Move(temp, path);
    }

    /// <summary>The main file's text, then the backup's. The caller stops at the first that parses.</summary>
    public static IEnumerable<string> ReadCandidates(string slot)
    {
        string path = PathFor(slot);
        foreach (string candidate in new[] { path, path + ".bak" })
        {
            string text = null;
            try
            {
                if (File.Exists(candidate))
                    text = File.ReadAllText(candidate, Encoding.UTF8);
            }
            catch (IOException e)
            {
                Debug.LogWarning("Could not read " + candidate + ": " + e.Message);
            }

            if (!string.IsNullOrWhiteSpace(text))
                yield return text;
        }
    }

    public static bool Exists(string slot) => File.Exists(PathFor(slot)) || File.Exists(PathFor(slot) + ".bak");

    public static List<string> Slots()
    {
        var slots = new List<string>();
        if (!Directory.Exists(Folder))
            return slots;
        foreach (string file in Directory.GetFiles(Folder, "*" + Extension))
            slots.Add(Path.GetFileNameWithoutExtension(file));
        return slots;
    }

    public static void Delete(string slot)
    {
        string path = PathFor(slot);
        File.Delete(path);
        File.Delete(path + ".bak");
        File.Delete(path + ".tmp");
    }
}
```

- `Application.persistentDataPath` is a Unity API. Read it on the main thread, as `WriteAsync` does, and pass the path in.
- `File.Replace` swaps the files in one step on desktop file systems. If a platform throws `PlatformNotSupportedException` for it, fall back to deleting the old file and moving the temp file, which leaves a short window with only the `.bak`.
- WebGL has no threads. Call `Write` there, not `WriteAsync`. Consoles have their own save APIs and storage rules; follow the platform's documentation.
- A slot list that shows the date and play time has to read each file. For large saves, write a small `slot.meta.json` next to each one with only the header fields.

## Manager

Three static events split the work:

| Event | When | Who listens |
| --- | --- | --- |
| `Capturing` | During `SaveAsync`, on the main thread. | Anything that copies its state into the save. |
| `Preparing` | When a load starts, before the level loads. | Systems that act as scenes load, such as [world state](world-state.md). |
| `Restoring` | After the level has loaded and every `Start` in it has run. | Objects in the level, such as the player. |

```csharp
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.SceneManagement;

/// <summary>
/// Lives in the Core scene. Saves and loads slots, counts play time, and autosaves.
/// </summary>
public class SaveManager : MonoBehaviour
{
    public const int CurrentVersion = 1;

    [SerializeField] SceneLoader sceneLoader;
    [Tooltip("0 turns autosave off.")]
    [SerializeField] float autosaveMinutes = 5f;
    [SerializeField] string autosaveSlot = "autosave";

    public static event Action<SaveGame> Capturing;
    public static event Action<SaveGame> Preparing;
    public static event Action<SaveGame> Restoring;

    /// <summary>True from the start of a load until Restoring has run.</summary>
    public static bool IsRestoring { get; private set; }

    static readonly HashSet<object> s_blockers = new HashSet<object>();

    public event Action<string> Saved;
    public event Action<string> Loaded;
    public event Action<string, string> Failed; // slot, reason

    public float PlayTime => _playTime;
    public bool IsBusy => _saving || IsRestoring;

    float _playTime;
    float _nextAutosave;
    bool _saving;
    SaveGame _pending;
    string _pendingSlot;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        Capturing = null;
        Preparing = null;
        Restoring = null;
        IsRestoring = false;
        s_blockers.Clear();
    }

    /// <summary>Stops autosave and manual saves while any blocker is registered. Combat, death, a cut-scene.</summary>
    public static void BlockSaving(object who) => s_blockers.Add(who);
    public static void UnblockSaving(object who) => s_blockers.Remove(who);
    public static bool CanSave => s_blockers.Count == 0;

    void OnEnable() => sceneLoader.LevelLoaded += OnLevelLoaded;
    void OnDisable() => sceneLoader.LevelLoaded -= OnLevelLoaded;

    void Start() => _nextAutosave = autosaveMinutes * 60f;

    void Update()
    {
        // Unscaled, so slow motion still counts. Paused and loading time do not.
        if (sceneLoader.IsLoading || IsRestoring || Time.timeScale <= 0f)
            return;
        _playTime += Time.unscaledDeltaTime;

        if (autosaveMinutes > 0f && _playTime >= _nextAutosave && CanSave && !IsBusy)
        {
            _nextAutosave = _playTime + autosaveMinutes * 60f;
            _ = SaveAsync(autosaveSlot);
        }
    }

    public async Task<bool> SaveAsync(string slot)
    {
        if (IsBusy || sceneLoader.IsLoading || !CanSave)
        {
            Failed?.Invoke(slot, "Cannot save right now.");
            return false;
        }
        if (!SaveStore.IsValidSlot(slot))
        {
            Failed?.Invoke(slot, "Invalid slot name.");
            return false;
        }

        _saving = true;
        try
        {
            var save = new SaveGame
            {
                version = CurrentVersion,
                savedAtUtc = DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture),
                playTimeSeconds = _playTime,
                activeScene = sceneLoader.CurrentLevel.path
            };

            // On the main thread. One subscriber that throws fails the whole save, which beats a partial one.
            Capturing?.Invoke(save);
            string json = JsonUtility.ToJson(save);

            await SaveStore.WriteAsync(slot, json);
            Saved?.Invoke(slot);
            return true;
        }
        catch (Exception e)
        {
            Debug.LogException(e);
            Failed?.Invoke(slot, e.Message);
            return false;
        }
        finally
        {
            _saving = false;
        }
    }

    public bool Load(string slot)
    {
        if (IsBusy || sceneLoader.IsLoading)
            return false;
        if (!TryRead(slot, out SaveGame save, out string error))
        {
            Failed?.Invoke(slot, error);
            return false;
        }
        return Begin(save, slot);
    }

    /// <summary>An empty save. Clears world state, and the player stays at the level's spawn.</summary>
    public bool NewGame(string firstLevel)
    {
        if (IsBusy || sceneLoader.IsLoading)
            return false;
        _playTime = 0f;
        return Begin(new SaveGame { version = CurrentVersion, activeScene = firstLevel }, null);
    }

    bool Begin(SaveGame save, string slot)
    {
        IsRestoring = true;
        Preparing?.Invoke(save);

        _pending = save;
        _pendingSlot = slot;
        if (sceneLoader.LoadLevel(save.activeScene))
            return true;

        _pending = null;
        IsRestoring = false;
        Failed?.Invoke(slot, "Could not load scene '" + save.activeScene + "'.");
        return false;
    }

    /// <summary>Upgrades and parses the main file, then the backup if that fails.</summary>
    public static bool TryRead(string slot, out SaveGame save, out string error)
    {
        save = null;
        error = "No save in this slot.";
        if (!SaveStore.IsValidSlot(slot))
            return false;

        foreach (string json in SaveStore.ReadCandidates(slot))
        {
            if (SaveMigrations.TryLoad(json, CurrentVersion, out save, out error))
                return true;
        }
        return false;
    }

    void OnLevelLoaded(Scene level)
    {
        if (_pending != null)
            StartCoroutine(RestoreNextFrame());
    }

    IEnumerator RestoreNextFrame()
    {
        // Objects in a scene loaded this frame run Start next frame. Wait, so Start does not undo the restore.
        yield return null;

        SaveGame save = _pending;
        string slot = _pendingSlot;
        _pending = null;

        _playTime = save.playTimeSeconds;
        _nextAutosave = _playTime + autosaveMinutes * 60f;

        try
        {
            Restoring?.Invoke(save);
        }
        finally
        {
            IsRestoring = false;
        }

        if (slot != null)
            Loaded?.Invoke(slot);
    }
}
```

`SaveMigrations` is on [versioning](versioning.md#migrations). Until the first format change, a stub that only parses is enough:

```csharp
using System;
using UnityEngine;

public static class SaveMigrations
{
    public static bool TryLoad(string json, int current, out SaveGame save, out string error)
    {
        try
        {
            save = JsonUtility.FromJson<SaveGame>(json);
            error = save != null ? null : "The save is empty.";
            return save != null;
        }
        catch (Exception e)
        {
            save = null;
            error = "The save is damaged: " + e.Message;
            return false;
        }
    }
}
```

- `await` in a `MonoBehaviour` resumes on the main thread, so `Saved` runs there.
- The level is saved by path, which `SceneLoader.LoadLevel` accepts. Moving or renaming a scene file breaks old saves; map old paths in a [migration](versioning.md#content-ids).
- `IsRestoring` covers the frames between the old level unloading and the new one being restored. Scene objects that save themselves when they unload check it, as [world state](world-state.md#capture-when-a-scene-unloads) does.

## The player

The player copies its own record in and out. It subscribes like any other [event listener](../../architecture/lifecycle.md#subscribe-in-onenable-unsubscribe-in-ondisable).

```csharp
using UnityEngine;

/// <summary>
/// Saves the player's position, health, and bag. Blocks saving while dead.
/// </summary>
public class PlayerSave : MonoBehaviour
{
    [SerializeField] Health health;
    [SerializeField] ListInventory inventory;
    [SerializeField] ItemCatalogue catalogue;

    void OnEnable()
    {
        SaveManager.Capturing += Capture;
        SaveManager.Restoring += Restore;
        if (health != null)
            health.Died += OnDied;
    }

    void OnDisable()
    {
        SaveManager.Capturing -= Capture;
        SaveManager.Restoring -= Restore;
        if (health != null)
            health.Died -= OnDied;
        SaveManager.UnblockSaving(this);
    }

    void OnDied() => SaveManager.BlockSaving(this);

    void Capture(SaveGame save)
    {
        PlayerRecord record = save.player;
        record.present = true;
        record.position = transform.position;
        record.rotation = transform.rotation;
        record.healthFraction = health != null && health.Max > 0f ? health.Current / health.Max : 1f;

        record.inventory.Clear();
        if (inventory != null && catalogue != null)
        {
            foreach (ItemInstance item in inventory.Stacks)
                record.inventory.Add(catalogue.ToRecord(item));
        }
    }

    void Restore(SaveGame save)
    {
        PlayerRecord record = save.player;
        if (!record.present)
            return;

        Teleport(record.position, record.rotation);

        if (health != null)
        {
            health.Revive(Mathf.Clamp01(record.healthFraction));
            SaveManager.UnblockSaving(this);
        }

        if (inventory != null && catalogue != null)
        {
            // Empty the bag the level started with, then refill it from the save.
            for (int i = inventory.Stacks.Count - 1; i >= 0; i--)
                inventory.TryRemoveInstance(inventory.Stacks[i]);

            foreach (ItemRecord line in record.inventory)
            {
                ItemInstance item = catalogue.FromRecord(line);
                if (item != null && !inventory.TryAdd(new ItemStack(item), out _))
                    Debug.LogWarning("A saved stack did not fit: " + line.definitionId, this);
            }
        }
    }

    void Teleport(Vector3 position, Quaternion rotation)
    {
        // A CharacterController puts the transform back unless it is off for the move.
        var controller = GetComponent<CharacterController>();
        bool wasEnabled = controller != null && controller.enabled;
        if (wasEnabled)
            controller.enabled = false;

        transform.SetPositionAndRotation(position, rotation);

        if (wasEnabled)
            controller.enabled = true;
    }
}
```

`Health` is the component from [health](../health.md). A `Rigidbody` player sets `Rigidbody.position` and `rotation` instead, and an agent uses `NavMeshAgent.Warp`.

## Setup

1. Add `SaveManager` to the Core scene, next to the `SceneLoader`, and assign it.
2. Add `PlayerSave` to the player and assign its health, bag, and item catalogue.
3. Main menu: **Continue** calls `Load` on the newest slot, **New game** calls `NewGame` with the first level.
4. Pause menu: **Save** calls `SaveAsync` with the chosen slot. Show `Failed` reasons to the player.
5. Block saving from systems that should not be saved mid-way: `SaveManager.BlockSaving(this)` when combat starts, `UnblockSaving(this)` when it ends.

!!! warning "Common pitfalls"

    Calling a Unity API from inside `Task.Run`, including `Application.persistentDataPath` and `transform.position`, throws or returns garbage. Capture first, then write.

    A save written straight over the old file leaves a broken file if the game dies mid-write. Write to a temp file and swap it in.

    Restoring in the same frame the level loads lets `Start` methods run afterwards and undo it, such as a bag adding its starting items again. Restore a frame later.

    A `Dictionary`, property, or field of an interface type is silently left out of the JSON. Check a saved file by eye once.

    Saving settings in the save slot means loading an old save resets the player's volume and controls. Keep them apart.
