---
engine: Unity
version: 6+
uses:
  - name: RPGs
    text: Item and loot assets with min-max ranges and read-only computed values.
  - name: Strategy and tactics
    text: Unit data that warns when a field is missing, instead of failing at runtime.
---

# Inspectors and property drawers

Unity 6 builds inspectors with **UI Toolkit**. Custom inspectors and drawers can be written in UI Toolkit or in the older IMGUI, and both work. This page uses UI Toolkit, with IMGUI notes at the end.

Reach for the least code that does the job:

| Need | Use |
| --- | --- |
| Labels, ranges, spacing, tooltips | [Attributes](#attributes), no editor code |
| A custom type drawn the same everywhere | A [property drawer](#property-drawer-for-a-type) for the type |
| A marker on fields, drawn specially | A [`PropertyAttribute`](#property-drawer-for-an-attribute) and its drawer |
| Buttons, warnings, or a layout for one component | A [custom inspector](#custom-inspector) |

## Attributes

| Attribute | Does |
| --- | --- |
| `[Header("Movement")]` | A bold label above the field. |
| `[Tooltip("...")]` | Hover text. |
| `[Space(8)]` | A gap. |
| `[Range(0f, 1f)]` | A slider. |
| `[Min(0f)]` | Clamps below. |
| `[TextArea(2, 6)]` | A multi-line string box. |
| `[HideInInspector]` | Serialised but not shown. |
| `[SerializeField]` | Shows and saves a private field. |
| `[FormerlySerializedAs("old")]` | Keeps data after a rename. |
| `[ContextMenu("Bake")]` on a method | Adds it to the component's **⋮** menu. |
| `[ContextMenuItem("Reset", "ResetSpeed")]` on a field | A right-click item on that field. |

## Property drawer for a type

A min-max pair used all over a game: damage ranges, spawn delays, loot counts. The drawer shows it on one line, labelled `min` and `max`, wherever it appears.

```csharp
// Runtime folder.
using System;
using UnityEngine;

[Serializable]
public struct FloatRange
{
    public float min;
    public float max;

    public FloatRange(float min, float max)
    {
        this.min = min;
        this.max = max;
    }

    public float Random() => UnityEngine.Random.Range(min, max);
    public float Clamp(float value) => Mathf.Clamp(value, min, max);
}
```

```csharp
// Editor folder.
using UnityEditor;
using UnityEditor.UIElements;
using UnityEngine;
using UnityEngine.UIElements;

[CustomPropertyDrawer(typeof(FloatRange))]
public class FloatRangeDrawer : PropertyDrawer
{
    public override VisualElement CreatePropertyGUI(SerializedProperty property)
    {
        // A BaseField-style row: the label lines up with every other field in the inspector.
        var row = new VisualElement();
        row.AddToClassList(BaseField<float>.ussClassName);
        row.AddToClassList(BaseField<float>.alignedFieldUssClassName);

        var label = new Label(property.displayName);
        label.AddToClassList(BaseField<float>.labelUssClassName);
        row.Add(label);

        var fields = new VisualElement { style = { flexDirection = FlexDirection.Row, flexGrow = 1 } };
        fields.Add(Field(property.FindPropertyRelative("min"), "min"));
        fields.Add(Field(property.FindPropertyRelative("max"), "max"));
        row.Add(fields);

        var warning = new HelpBox("Min is greater than max.", HelpBoxMessageType.Warning);
        var root = new VisualElement();
        root.Add(row);
        root.Add(warning);

        void Check(SerializedProperty _)
        {
            bool bad = property.FindPropertyRelative("min").floatValue > property.FindPropertyRelative("max").floatValue;
            warning.style.display = bad ? DisplayStyle.Flex : DisplayStyle.None;
        }
        root.TrackPropertyValue(property, Check);
        Check(property);
        return root;
    }

    static VisualElement Field(SerializedProperty property, string name)
    {
        var field = new FloatField(name) { style = { flexGrow = 1, flexBasis = 0 } };
        field.labelElement.style.minWidth = 26; // short inner labels
        field.BindProperty(property);
        return field;
    }
}
```

- `BindProperty` ties the field to the property: undo, prefab override bold, and multi-object editing come with it.
- `TrackPropertyValue` calls back whenever the property, or one of its children, changes, including through undo.
- The drawer is found by type. Every `FloatRange` field in every component and asset uses it, including inside lists.

## Property drawer for an attribute

A marker attribute changes how one field is drawn. `[ReadOnly]` shows a value, such as a computed id, without letting anyone edit it:

```csharp
// Runtime folder: the attribute must exist in builds, because fields carry it.
using UnityEngine;

public class ReadOnlyAttribute : PropertyAttribute { }
```

```csharp
// Editor folder.
using UnityEditor;
using UnityEditor.UIElements;
using UnityEngine.UIElements;

[CustomPropertyDrawer(typeof(ReadOnlyAttribute))]
public class ReadOnlyDrawer : PropertyDrawer
{
    public override VisualElement CreatePropertyGUI(SerializedProperty property)
    {
        var field = new PropertyField(property);
        field.SetEnabled(false);
        return field;
    }
}
```

```csharp
[ReadOnly] [SerializeField] string id;
```

`PropertyField` draws the property the default way, including its own drawer if it has one. Wrapping it is how an attribute drawer adds behaviour without redrawing the field. `fieldInfo` and `attribute` on the drawer give the field's reflection info and the attribute instance, for attributes with arguments.

## Custom inspector

A custom inspector replaces one component's whole inspector. Start from the default one and add to it, rather than rebuilding every field.

```csharp
// Editor folder.
using UnityEditor;
using UnityEditor.UIElements;
using UnityEngine;
using UnityEngine.UIElements;

[CustomEditor(typeof(Portal))]
[CanEditMultipleObjects]
public class PortalEditor : Editor
{
    public override VisualElement CreateInspectorGUI()
    {
        var root = new VisualElement();
        InspectorElement.FillDefaultInspector(root, serializedObject, this);

        var noLinks = new HelpBox("No links assigned. Agents cannot pass this portal.", HelpBoxMessageType.Warning);
        root.Insert(0, noLinks);

        void Check(SerializedObject so)
        {
            bool none = so.FindProperty("passLink").objectReferenceValue == null
                && so.FindProperty("openLink").objectReferenceValue == null
                && so.FindProperty("breakLink").objectReferenceValue == null;
            noLinks.style.display = none ? DisplayStyle.Flex : DisplayStyle.None;
        }
        root.TrackSerializedObjectValue(serializedObject, Check);
        Check(serializedObject);

        // Play mode only: the portal applies its links at runtime.
        var buttons = new VisualElement { style = { flexDirection = FlexDirection.Row, marginTop = 6 } };
        foreach (PortalState state in System.Enum.GetValues(typeof(PortalState)))
        {
            var button = new Button(() =>
            {
                foreach (Object t in targets)
                    ((Portal)t).SetState(state);
            }) { text = state.ToString() };
            button.SetEnabled(Application.isPlaying);
            buttons.Add(button);
        }
        root.Add(buttons);

        return root;
    }
}
```

- `targets`, with `[CanEditMultipleObjects]`, is every selected portal. `target` is only the first.
- `FindProperty` uses the serialised field names, which for private `[SerializeField]` fields are the field names as written.
- The buttons call runtime methods, so they only make sense in Play mode. For edit-time changes, edit serialised properties instead, or record undo first.
- `Portal` is the component from [doors and windows](../../ai/navigation/doors-windows.md#portal).

## IMGUI

Older drawers and inspectors use `OnGUI(Rect, SerializedProperty, GUIContent)` with `GetPropertyHeight`, and `OnInspectorGUI` with `EditorGUILayout`. They still work in Unity 6: a UI Toolkit inspector hosts an IMGUI drawer inside an `IMGUIContainer`. Two things to know when mixing:

- A drawer with only IMGUI code works everywhere. A drawer with only `CreatePropertyGUI` shows "No GUI implemented" inside an IMGUI inspector. Write both if the type may appear in an old IMGUI inspector.
- IMGUI redraws every repaint and is quicker to write for a one-off. UI Toolkit builds once and updates through bindings, which scales better for big inspectors and lists.

!!! warning "Common pitfalls"

    A `PropertyAttribute` class inside an `Editor` folder does not exist in builds, and every field using it fails to compile there. Keep attributes in runtime code.

    Setting fields on `target` directly skips undo and prefab overrides. Use `serializedObject` and properties, or record undo first.

    `CreateInspectorGUI` returning null falls back to the IMGUI `OnInspectorGUI`. An empty element hides the inspector.

    A custom inspector without `[CanEditMultipleObjects]` shows "Multi-object editing not supported" when several are selected.

    Field names passed to `FindProperty` are strings. Renaming the field breaks the inspector silently. Use `nameof` where the field is accessible.
