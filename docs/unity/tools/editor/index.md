---
engine: Unity
version: 6+
---

# Editor tooling

Code that runs in the Unity Editor, not in the game: inspectors that explain themselves, menu commands for repetitive jobs, windows for project-wide views, and checks that stop broken content reaching a build.

| Page | Covers |
| --- | --- |
| [Inspectors and property drawers](inspectors.md) | Attributes first, then property drawers for your own types and attributes, then custom inspectors with buttons and warnings. |
| [Menus, windows, and handles](windows.md) | Menu items and shortcuts, component context menus, an editor window with a list, and handles for editing points in the Scene view. |
| [Validation](validation.md) | `OnValidate`, a `[Required]` attribute, a problems window that scans scenes and assets, and a build step that fails on errors. |

## Where editor code lives

Editor code uses `UnityEditor`, which does not exist in a build. Keep it out of the build in one of two ways:

- **An `Editor` folder.** Any folder named `Editor`, anywhere under `Assets`, compiles into an editor-only assembly.
- **An assembly definition** with only the **Editor** platform ticked, referencing the game's runtime assembly. Faster compiles once the project is large.

Runtime classes that editor code needs, such as a `PropertyAttribute`, stay in runtime folders. A runtime script that needs a bit of editor code, such as the save id's GUID generator on the [world state](../../systems/saving/world-state.md#save-id) page, wraps it in `#if UNITY_EDITOR`.

## Undo and dirty

Changes made by editor code must go through Unity's undo, or **Ctrl+Z** does nothing and the scene may not save them.

| Change | How |
| --- | --- |
| Fields through `SerializedObject` and `SerializedProperty` | Undo and dirty are handled. Call `ApplyModifiedProperties()`. |
| Fields set directly on the object | `Undo.RecordObject(target, "Name")` before the change. On a prefab instance, also `PrefabUtility.RecordPrefabInstancePropertyModifications(target)`. |
| New objects | `Undo.RegisterCreatedObjectUndo(go, "Name")` after creating. |
| Destroying | `Undo.DestroyObjectImmediate(go)`. |
| Assets changed outside serialized properties | `EditorUtility.SetDirty(asset)`, then `AssetDatabase.SaveAssets()` when needed. |

Prefer `SerializedProperty` in inspectors and drawers. It handles undo, multi-object editing, and prefab overrides for free.
