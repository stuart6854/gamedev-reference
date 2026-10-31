---
engine: Unity
version: 6+
uses:
  - name: Open worlds
    text: Dropping hundreds of props onto the terrain with one shortcut.
  - name: Top-down survival
    text: A window that lists every door and container in the scene, with a click to select each.
  - name: Hordes and crowds
    text: Spawn points placed and moved by dragging handles in the Scene view.
---

# Menus, windows, and handles

Commands designers run often, a window that shows the whole scene at once, and handles for editing positions where they are, in the Scene view. All of it is editor code: put it in an `Editor` folder, as the [editor tooling](index.md#where-editor-code-lives) page says.

## Menu items

A static method with `[MenuItem]` appears in the main menu. A second method with the same path and `true` decides when it is enabled.

```csharp
using UnityEditor;
using UnityEngine;

public static class GroundTools
{
    // _End: the End key, no modifier. % is Ctrl (Cmd on macOS), # is Shift, & is Alt.
    [MenuItem("Tools/Game/Drop To Ground _End")]
    static void DropToGround()
    {
        Physics.SyncTransforms(); // edit-mode moves are not seen by queries until synced

        Transform[] selected = Selection.transforms;
        Undo.RecordObjects(selected, "Drop To Ground");
        foreach (Transform t in selected)
        {
            // Start a little above, and ignore the object's own colliders by casting from above them.
            Vector3 from = t.position + Vector3.up * 2f;
            RaycastHit[] hits = Physics.RaycastAll(from, Vector3.down, 100f, ~0, QueryTriggerInteraction.Ignore);
            float best = float.MaxValue;
            Vector3? ground = null;
            foreach (RaycastHit hit in hits)
            {
                if (hit.transform.IsChildOf(t) || hit.distance >= best)
                    continue;
                best = hit.distance;
                ground = hit.point;
            }
            if (ground.HasValue)
                t.position = ground.Value;
        }
    }

    [MenuItem("Tools/Game/Drop To Ground _End", true)]
    static bool CanDropToGround() => Selection.transforms.Length > 0;
}
```

- `Selection.transforms` is the selected scene objects' top-level transforms, without children of other selected objects.
- `Undo.RecordObjects` before changing them makes one undo step for the whole selection.
- Shortcuts in the path can clash with Unity's own. **Edit → Shortcuts** shows and rebinds them, including yours.

### Component menus

`CONTEXT/Type/Name` adds an item to a component's **⋮** menu, from editor code, without touching the component:

```csharp
[MenuItem("CONTEXT/Transform/Snap To Half Metre")]
static void Snap(MenuCommand command)
{
    var t = (Transform)command.context;
    Undo.RecordObject(t, "Snap To Half Metre");
    Vector3 p = t.localPosition;
    t.localPosition = new Vector3(Mathf.Round(p.x * 2f) / 2f, Mathf.Round(p.y * 2f) / 2f, Mathf.Round(p.z * 2f) / 2f);
}
```

`[ContextMenu("Name")]` on a method of the component itself does the same from runtime code, which suits one-off actions such as "Bake Slots".

## An editor window

A window listing every [portal](../../ai/navigation/doors-windows.md#portal) in the open scenes, with its state, and a click to select it. The same shape works for spawn points, containers, or anything else designers need to find.

```csharp
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
using UnityEngine.UIElements;

public class PortalListWindow : EditorWindow
{
    readonly List<Portal> _portals = new List<Portal>();
    ListView _list;

    [MenuItem("Tools/Game/Portal List")]
    static void Open() => GetWindow<PortalListWindow>("Portals");

    void CreateGUI()
    {
        var refresh = new Button(Refresh) { text = "Refresh" };
        rootVisualElement.Add(refresh);

        _list = new ListView(_portals, 20, () => new Label(), (element, i) =>
        {
            Portal p = _portals[i];
            ((Label)element).text = p != null ? p.name + "  (" + p.State + ")" : "(destroyed)";
        })
        {
            selectionType = SelectionType.Multiple,
            style = { flexGrow = 1 }
        };
        _list.selectionChanged += items =>
        {
            var objects = new List<Object>();
            foreach (object item in items)
            {
                if (item is Portal p && p != null)
                    objects.Add(p.gameObject);
            }
            Selection.objects = objects.ToArray();
            if (objects.Count == 1)
                EditorGUIUtility.PingObject(objects[0]);
        };
        rootVisualElement.Add(_list);

        Refresh();
    }

    void OnHierarchyChange() => Refresh();

    void Refresh()
    {
        _portals.Clear();
        _portals.AddRange(FindObjectsByType<Portal>(FindObjectsInactive.Include, FindObjectsSortMode.None));
        _portals.Sort((a, b) => string.CompareOrdinal(a.name, b.name));
        _list?.RefreshItems();
    }
}
```

- `CreateGUI` runs once when the window opens, and again after a domain reload. Build the UI there.
- `OnHierarchyChange` keeps the list current as objects are added, removed, or renamed.
- `ListView` only creates elements for the visible rows, so it handles thousands of entries.
- Keep window state in fields. Fields marked `[SerializeField]` survive a domain reload; others reset.

## Handles in the Scene view

Positions that belong in the world, such as spawn points round an area, are easier to place by dragging than by typing. `OnSceneGUI` in a custom editor draws handles while the object is selected.

```csharp
// Runtime folder.
using UnityEngine;

public class SpawnArea : MonoBehaviour
{
    [Tooltip("Spawn points, local to this object.")]
    public Vector3[] points = { new Vector3(-2f, 0f, 0f), new Vector3(2f, 0f, 0f) };

    void OnDrawGizmosSelected()
    {
        Gizmos.color = Color.yellow;
        foreach (Vector3 p in points)
            Gizmos.DrawWireSphere(transform.TransformPoint(p), 0.3f);
    }
}
```

```csharp
// Editor folder.
using UnityEditor;
using UnityEngine;

[CustomEditor(typeof(SpawnArea))]
public class SpawnAreaEditor : Editor
{
    void OnSceneGUI()
    {
        var area = (SpawnArea)target;
        Transform t = area.transform;

        for (int i = 0; i < area.points.Length; i++)
        {
            Vector3 world = t.TransformPoint(area.points[i]);

            EditorGUI.BeginChangeCheck();
            Vector3 moved = Handles.PositionHandle(world, Tools.pivotRotation == PivotRotation.Local ? t.rotation : Quaternion.identity);
            if (EditorGUI.EndChangeCheck())
            {
                Undo.RecordObject(area, "Move Spawn Point");
                area.points[i] = t.InverseTransformPoint(moved);
            }

            Handles.Label(world + Vector3.up * 0.5f, i.ToString());
        }
    }
}
```

- `BeginChangeCheck` and `EndChangeCheck` around the handle tell you it was dragged this event. Record undo only then, or every repaint makes an undo step.
- `Handles.FreeMoveHandle` and `Handles.RadiusHandle` suit points on a plane and radii. Snap with **Ctrl** held, as Unity's own move tool does.
- `OnDrawGizmos` draws always; `OnDrawGizmosSelected` only while selected. Gizmos are runtime code, in the component, and stripped from builds.

## Remembering settings

| Store | Lasts | Use for |
| --- | --- | --- |
| `[SerializeField]` field on the window | Domain reloads, while open | The window's own state |
| `SessionState` | Until the editor closes | Things like the [play-from-core](../../architecture/scenes.md#play-from-core) start scene |
| `EditorPrefs` | Across sessions, per machine | A tool's preferences |
| A `ScriptableObject` settings asset | In the project, shared through version control | Team-wide settings |

!!! warning "Common pitfalls"

    A menu method that changes objects without `Undo.Record...` cannot be undone, and the scene may not be marked as changed.

    Raycasts in edit mode miss objects that were just moved, until `Physics.SyncTransforms`.

    Building a window's UI in `OnEnable` instead of `CreateGUI` can run before `rootVisualElement` is ready.

    Recording undo on every repaint in `OnSceneGUI` fills the undo history. Record only when the change check says it moved.

    Editor scripts outside an `Editor` folder or an editor-only assembly break the build with missing `UnityEditor` types.
