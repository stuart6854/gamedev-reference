---
engine: Unity
version: 6+
uses:
  - name: Open worlds
    text: Hundreds of hand-placed props checked for missing references before every build.
  - name: RPGs
    text: Item and loot assets checked for empty ids, duplicates, and broken tables.
  - name: Top-down survival
    text: Doors without links and containers without loot found before a playtest, not during one.
---

# Validation

Content breaks quietly: a field left empty, a script deleted, two items with the same id, a door with no links. Each one fails at runtime, often in a build, far from the mistake. Validation finds them in the editor. It runs at three levels: as a field is edited, on demand across the project, and when building.

## As you edit: OnValidate

`OnValidate` runs on a component or asset when it loads in the editor and whenever a value changes in the inspector. Use it for local fixes: clamping, filling in defaults, keeping two fields consistent.

```csharp
void OnValidate()
{
    stepTime = Mathf.Max(0.01f, stepTime);
    if (string.IsNullOrEmpty(id))
        id = name; // an asset's name as a starting id
}
```

- It runs on load, on undo, and on entering Play mode. It must be fast and must not depend on other objects being ready.
- It must not create, destroy, or move other objects, or call `AssetDatabase` methods that import. Defer that work with `EditorApplication.delayCall`, as the [save id](../../systems/saving/world-state.md#save-id) does.
- It runs in the editor only. It is not a runtime check.

## A Required attribute

Most broken references are fields someone forgot to assign. A marker attribute says which fields must be set, and the checks below enforce it.

```csharp
// Runtime folder.
using UnityEngine;

/// <summary>This object reference must be assigned.</summary>
public class RequiredAttribute : PropertyAttribute { }
```

```csharp
[Required] [SerializeField] Health health;
[Required] [SerializeField] ItemCatalogue catalogue;
```

A drawer can tint the field red when it is empty, the same way the [read-only drawer](inspectors.md#property-drawer-for-an-attribute) wraps a `PropertyField`.

## Your own checks

For checks that need knowledge of the component, it reports its own problems:

```csharp
// Runtime folder.
using System.Collections.Generic;

/// <summary>Reports content problems. Called by editor validation, never at runtime.</summary>
public interface IValidatable
{
    void Validate(List<string> problems);
}
```

```csharp
// In Portal, declared as Portal : MonoBehaviour, IValidatable:
public void Validate(List<string> problems)
{
    if (passLink == null && openLink == null && breakLink == null)
        problems.Add("No links. Agents cannot pass.");
    if (breakLink != null && health == null)
        problems.Add("Break link without Health. It can never break.");
}
```

## The validator

Editor code that walks scenes and assets, runs every check, and returns a list of problems tied to the object that has them.

```csharp
// Editor folder.
using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

public readonly struct Problem
{
    public readonly Object Context;
    public readonly string Message;
    public readonly bool IsError;

    public Problem(Object context, string message, bool isError = true)
    {
        Context = context;
        Message = message;
        IsError = isError;
    }
}

public static class ContentValidator
{
    public static List<Problem> ValidateScene(Scene scene)
    {
        var problems = new List<Problem>();
        var ids = new Dictionary<string, SaveId>();

        foreach (GameObject root in scene.GetRootGameObjects())
        {
            foreach (Transform t in root.GetComponentsInChildren<Transform>(true))
            {
                GameObject go = t.gameObject;

                int missing = GameObjectUtility.GetMonoBehavioursWithMissingScriptCount(go);
                if (missing > 0)
                    problems.Add(new Problem(go, missing + " missing script(s)."));

                foreach (MonoBehaviour behaviour in go.GetComponents<MonoBehaviour>())
                {
                    if (behaviour == null)
                        continue; // the missing scripts above
                    CheckObject(behaviour, problems);

                    if (behaviour is SaveId saveId && !string.IsNullOrEmpty(saveId.Id))
                    {
                        if (ids.TryGetValue(saveId.Id, out SaveId first))
                            problems.Add(new Problem(go, "Save id duplicates " + first.name + "."));
                        else
                            ids.Add(saveId.Id, saveId);
                    }
                }
            }
        }
        return problems;
    }

    public static List<Problem> ValidateAssets()
    {
        var problems = new List<Problem>();
        foreach (string guid in AssetDatabase.FindAssets("t:ScriptableObject", new[] { "Assets" }))
        {
            var asset = AssetDatabase.LoadAssetAtPath<ScriptableObject>(AssetDatabase.GUIDToAssetPath(guid));
            if (asset != null)
                CheckObject(asset, problems);
        }
        return problems;
    }

    static void CheckObject(Object target, List<Problem> problems)
    {
        // [Required] fields, found by reflection, including private serialised ones and base classes.
        for (Type type = target.GetType(); type != null && type != typeof(MonoBehaviour) && type != typeof(ScriptableObject); type = type.BaseType)
        {
            foreach (FieldInfo field in type.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly))
            {
                if (field.GetCustomAttribute<RequiredAttribute>() == null)
                    continue;
                if (field.GetValue(target) is Object value ? value == null : field.GetValue(target) == null)
                    problems.Add(new Problem(target, "'" + ObjectNames.NicifyVariableName(field.Name) + "' is not assigned."));
            }
        }

        if (target is IValidatable validatable)
        {
            var messages = new List<string>();
            validatable.Validate(messages);
            foreach (string message in messages)
                problems.Add(new Problem(target, message));
        }
    }
}
```

- `GetMonoBehavioursWithMissingScriptCount` finds components whose script was deleted or renamed. They show as "Missing (Mono Script)" and do nothing.
- A `UnityEngine.Object` that was destroyed, or never assigned, compares equal to null with Unity's `==`, so the check covers both.
- Loading every `ScriptableObject` in a large project takes time. Limit the folders passed to `FindAssets` if it gets slow.

## A problems window

```csharp
// Editor folder.
using System.Collections.Generic;
using UnityEditor;
using UnityEngine.SceneManagement;
using UnityEngine.UIElements;

public class ProblemsWindow : EditorWindow
{
    readonly List<Problem> _problems = new List<Problem>();
    ListView _list;
    Label _summary;

    [MenuItem("Tools/Game/Validate Content")]
    static void Open() => GetWindow<ProblemsWindow>("Problems").Run();

    void CreateGUI()
    {
        rootVisualElement.Add(new Button(Run) { text = "Run" });
        _summary = new Label();
        rootVisualElement.Add(_summary);

        _list = new ListView(_problems, 20, () => new Label(), (e, i) =>
        {
            Problem p = _problems[i];
            ((Label)e).text = (p.IsError ? "✖ " : "⚠ ") + (p.Context != null ? p.Context.name + ": " : "") + p.Message;
        }) { style = { flexGrow = 1 } };
        _list.selectionChanged += items =>
        {
            foreach (object item in items)
            {
                if (item is Problem p && p.Context != null)
                {
                    Selection.activeObject = p.Context;
                    EditorGUIUtility.PingObject(p.Context);
                }
            }
        };
        rootVisualElement.Add(_list);
    }

    void Run()
    {
        _problems.Clear();
        for (int i = 0; i < SceneManager.sceneCount; i++)
            _problems.AddRange(ContentValidator.ValidateScene(SceneManager.GetSceneAt(i)));
        _problems.AddRange(ContentValidator.ValidateAssets());

        if (_summary != null)
            _summary.text = _problems.Count == 0 ? "No problems." : _problems.Count + " problem(s).";
        _list?.RefreshItems();
    }
}
```

It checks the scenes that are open. To check every level, open each build scene additively with `EditorSceneManager.OpenScene(path, OpenSceneMode.Additive)`, validate it, and close it again with `EditorSceneManager.CloseScene`.

## On build

The last chance. Scenes are processed one by one during a player build, and a callback can fail the build when a scene has errors:

```csharp
// Editor folder.
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;
using UnityEngine.SceneManagement;

public class ValidateOnBuild : IProcessSceneWithReport
{
    public int callbackOrder => 0;

    public void OnProcessScene(Scene scene, BuildReport report)
    {
        if (report == null)
            return; // also called when entering Play mode; only fail real builds

        int errors = 0;
        foreach (Problem p in ContentValidator.ValidateScene(scene))
        {
            if (!p.IsError)
                continue;
            errors++;
            Debug.LogError(scene.name + ": " + p.Message, p.Context);
        }

        if (errors > 0)
            throw new BuildFailedException(errors + " content error(s) in " + scene.name + ". See the Console.");
    }
}
```

- `OnProcessScene` also runs for each scene entering Play mode, with a null report. Returning early there keeps playtesting quick; drop the check to validate on every Play as well.
- `BuildFailedException` stops the build with the message. Logged errors with a context object are clickable in the Console.
- Unity 6.3 adds context-based build callback interfaces, such as `IPreprocessBuildWithContext`, which replace the report-based ones over time. The shape is the same.
- Validate assets once per build in an `IPreprocessBuildWithReport`, rather than once per scene.

!!! warning "Common pitfalls"

    `OnValidate` that creates or destroys objects logs errors and can corrupt the scene. Defer with `delayCall`.

    Missing scripts are invisible in code: `GetComponents` returns null in their place. Use `GetMonoBehavioursWithMissingScriptCount`.

    A validator that only checks the open scene misses every other level. Run it over the build scenes before a release.

    Checks that throw stop the validator half way. Catch and report as a problem instead.

    Failing every Play-mode entry on a warning makes people turn validation off. Fail builds on errors; show warnings in the window.
