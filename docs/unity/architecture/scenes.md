---
engine: Unity
version: 6+
---

# Scenes and loading

How to split a game into scenes, and how to move between them without a frozen frame: a persistent **Core** scene that is always loaded, levels loaded additively on top of it, a loading screen, and an editor hook so pressing Play in a level still starts from Core.

Code-only systems, such as audio and saving, do not need a scene. They are the systems prefab from [bootstrapping and services](services.md), which exists before any scene wakes. A Core scene is for what belongs in a scene: the UI canvases, the EventSystem, the loading screen, and the loader itself.

## Layouts

| Layout | How | Good for | Weak at |
| --- | --- | --- | --- |
| **One scene per level** | `LoadScene` replaces everything. Persistent things use `DontDestroyOnLoad`. | Small games, jams. | Every load is a hitch, and persistent objects are invisible in the editor until Play. |
| **Core plus additive levels** | Core stays loaded. Levels load and unload on top. | Most games. UI and loader are scene content, edited like any other. | Pressing Play in a level skips Core, unless the editor hook below is used. |
| **Streamed chunks** | Core plus a level, plus chunks loaded and unloaded by distance. | Open worlds. | Cross-chunk references, and lighting baked per chunk. |

This page builds the second. The third is the same loader, called per chunk.

## Rules of additive scenes

- **The active scene owns the lighting.** Skybox, fog, ambient light, and lightmap settings come from the active scene. After loading a level, make it active. The [day and night cycle](../rendering/day-night.md) writes `RenderSettings`, which are the active scene's.
- **The active scene receives new objects.** `Instantiate` puts objects in the active scene. With the level active, spawned enemies unload with the level. With Core active, they would survive it.
- **No serialised references across scenes.** A field in a level cannot point at an object in Core. Use a service from the [locator](services.md), an [event channel](events.md), or find the object in `Start` or on `sceneLoaded`.
- **Unloading does not free assets.** `UnloadSceneAsync` destroys the objects. Textures and meshes they used stay in memory until `Resources.UnloadUnusedAssets`. A `Single` load calls that for you; an additive unload does not.
- **Lightmaps load per scene.** Scenes baked together keep separate lightmaps, so a level can unload safely, but they share light probe data.

## A load, step by step

```text
LoadLevel(next):
    fade the loading screen in
    unload the current level, wait for it
    Resources.UnloadUnusedAssets, wait for it
    LoadSceneAsync(next, Additive); while loading, show progress / 0.9
    SetActiveScene(next)
    fade the loading screen out
```

Unloading before loading keeps peak memory at one level, not two. A loader that must hide the swap completely, such as a seamless door, loads first and unloads after, and pays for both levels in memory for a moment.

### Progress and activation

An async load reports progress from 0 to 0.9 while it reads data, then activates the scene, which runs every `Awake` and `OnEnable`, and finishes at 1. Divide by 0.9 for a bar that fills.

`allowSceneActivation = false` holds the load at 0.9, for example to wait for a "Press any key" prompt. While it is held, the async operation queue is stalled: an `UnloadSceneAsync` or another load started after it does not run. Do not leave it held while waiting on another operation.

`SceneManager.LoadScene`, the non-async one, completes on the next frame, and forces every pending async operation to complete with it, held activation included. Do not mix it with async loads.

## Playing from any scene in the editor

With a Core scene at build index 0, a build always starts there. In the editor, Play starts in whatever scene is open. Without Core, the level has no UI and no loader.

`EditorSceneManager.playModeStartScene` makes the editor load a given scene asset on Play, instead of the open scenes. The editor script below sets it to Core, and stores the path of the level that was open. Core's loader then loads that level instead of the first one. Pressing Play in any level gives exactly the start-up a build has.

Unity loads the start scene, and the level, from disk. Unsaved changes in the open level are not in Play mode. Save first.

## Setup

1. Create `Assets/Scenes/Core.unity`. Add the EventSystem, a UI canvas with the loading screen (a full-screen panel with a `CanvasGroup`), and an object with `SceneLoader`. No camera or lights: those belong to levels.
2. In **File → Build Profiles**, put Core first in the scene list, then every level. A scene that is not in the list cannot be loaded at runtime, in the editor included.
3. Set **First Level** on `SceneLoader` to the first level's name or path.
4. Copy `PlayFromCore` into an `Editor` folder. Set `CorePath` if Core is elsewhere. **Tools → Play From Core** turns it on and off.
5. Open a level and press Play. The Hierarchy shows Core and the level, with the level in bold as the active scene.
6. Other scripts call `SceneLoader.LoadLevel("Level02")`, and listen to `LevelLoaded`.

## Scripts

### Scene loader

```csharp
using System;
using System.Collections;
using UnityEngine;
using UnityEngine.SceneManagement;

/// <summary>
/// Lives in the Core scene. Loads one level at a time additively, behind a loading screen.
/// </summary>
public class SceneLoader : MonoBehaviour
{
    public const string EditorStartLevelKey = "PlayFromCore.StartLevel";

    [Tooltip("Name or path of the level to load when Core starts.")]
    [SerializeField] string firstLevel = "Level01";

    [SerializeField] CanvasGroup loadingScreen;
    [SerializeField] float fadeTime = 0.25f;

    public event Action<Scene> LevelLoaded;

    public bool IsLoading { get; private set; }
    public float Progress { get; private set; }
    public Scene CurrentLevel { get; private set; }

    Scene _justLoaded;

    IEnumerator Start()
    {
        string level = firstLevel;

#if UNITY_EDITOR
        // Set by PlayFromCore when Play was pressed in a level.
        string fromEditor = UnityEditor.SessionState.GetString(EditorStartLevelKey, string.Empty);
        if (!string.IsNullOrEmpty(fromEditor))
            level = fromEditor;
#endif

        if (loadingScreen != null)
            SetScreen(1f);
        yield return Load(level);
    }

    /// <summary>Unloads the current level and loads another. Ignored while a load is running.</summary>
    public bool LoadLevel(string scene)
    {
        if (IsLoading || string.IsNullOrEmpty(scene))
            return false;
        StartCoroutine(Load(scene));
        return true;
    }

    IEnumerator Load(string scene)
    {
        IsLoading = true;
        Progress = 0f;
        yield return Fade(1f);

        if (CurrentLevel.IsValid() && CurrentLevel.isLoaded)
        {
            AsyncOperation unload = SceneManager.UnloadSceneAsync(CurrentLevel);
            if (unload != null)
                yield return unload;
        }

        // An additive unload leaves the level's assets in memory.
        yield return Resources.UnloadUnusedAssets();

        _justLoaded = default;
        SceneManager.sceneLoaded += OnSceneLoaded;
        AsyncOperation load = SceneManager.LoadSceneAsync(scene, LoadSceneMode.Additive);
        if (load == null)
        {
            // Not in the Build Profiles scene list.
            SceneManager.sceneLoaded -= OnSceneLoaded;
            Debug.LogError("Could not load scene '" + scene + "'.");
            IsLoading = false;
            yield break;
        }

        while (!load.isDone)
        {
            Progress = Mathf.Clamp01(load.progress / 0.9f);
            yield return null;
        }
        SceneManager.sceneLoaded -= OnSceneLoaded;

        Progress = 1f;
        CurrentLevel = _justLoaded;
        if (CurrentLevel.IsValid())
            SceneManager.SetActiveScene(CurrentLevel); // lighting, and the target for Instantiate

        yield return Fade(0f);
        IsLoading = false;
        LevelLoaded?.Invoke(CurrentLevel);
    }

    void OnSceneLoaded(Scene scene, LoadSceneMode mode)
    {
        if (mode == LoadSceneMode.Additive)
            _justLoaded = scene;
    }

    IEnumerator Fade(float target)
    {
        if (loadingScreen == null)
            yield break;

        loadingScreen.blocksRaycasts = true;
        float start = loadingScreen.alpha;
        for (float t = 0f; t < fadeTime; t += Time.unscaledDeltaTime)
        {
            SetScreen(Mathf.Lerp(start, target, t / fadeTime));
            yield return null;
        }
        SetScreen(target);
    }

    void SetScreen(float alpha)
    {
        loadingScreen.alpha = alpha;
        loadingScreen.blocksRaycasts = alpha > 0f;
        loadingScreen.gameObject.SetActive(alpha > 0f);
    }
}
```

A progress bar on the loading screen reads `Progress`. The fade uses unscaled time, so it works while the game is paused.

### Play from Core

```csharp
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.SceneManagement;

/// <summary>
/// Editor only. Play starts from Core, which then loads the level that was open.
/// </summary>
[InitializeOnLoad]
public static class PlayFromCore
{
    const string CorePath = "Assets/Scenes/Core.unity";
    const string EnabledKey = "PlayFromCore.Enabled";
    const string MenuPath = "Tools/Play From Core";

    static PlayFromCore()
    {
        EditorApplication.playModeStateChanged += OnPlayModeChanged;
        // The asset database may not be ready during the static constructor.
        EditorApplication.delayCall += Apply;
    }

    static bool Enabled
    {
        get => EditorPrefs.GetBool(EnabledKey, true);
        set => EditorPrefs.SetBool(EnabledKey, value);
    }

    [MenuItem(MenuPath)]
    static void Toggle()
    {
        Enabled = !Enabled;
        Apply();
    }

    [MenuItem(MenuPath, true)]
    static bool ToggleValidate()
    {
        Menu.SetChecked(MenuPath, Enabled);
        return true;
    }

    static void Apply()
    {
        EditorSceneManager.playModeStartScene = Enabled ? AssetDatabase.LoadAssetAtPath<SceneAsset>(CorePath) : null;
    }

    static void OnPlayModeChanged(PlayModeStateChange change)
    {
        if (change != PlayModeStateChange.ExitingEditMode)
            return;

        Apply();

        // Remember the level that was open, unless it is Core itself.
        Scene active = SceneManager.GetActiveScene();
        string level = Enabled && active.path != CorePath ? active.path : string.Empty;
        SessionState.SetString(SceneLoader.EditorStartLevelKey, level);
    }
}
```

`SessionState` keeps the value for the editor session, across the domain reload that entering Play mode can cause. The runtime loader only reads it inside `#if UNITY_EDITOR`, so builds always start from **First Level**.

!!! warning "Common pitfalls"

    A level missing from the Build Profiles scene list does not load, in the editor included. The loader logs an error and leaves the loading screen up.

    Forgetting `SetActiveScene` leaves Core active: the level's skybox and fog do not apply, and spawned objects land in Core and survive the level's unload.

    `Resources.UnloadUnusedAssets` is not called by an additive unload. Without it, memory grows with every level visited.

    Holding `allowSceneActivation` false while starting another async operation deadlocks the loader: the second waits for the first, which is waiting for you.

    Loading a scene by name loads the first scene in the build list with that name. Two levels called `Boss` in different folders need full paths.

    With **Play From Core** on, unsaved changes in the open level are not in Play mode, because the level loads from disk.
