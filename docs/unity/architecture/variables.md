---
engine: Unity
version: 6+
---

# Shared variables

A `ScriptableObject` that holds one runtime value, or a list of live objects, so a HUD and a player can share a number without holding each other. The value you can read at any time is this page. A signal with no stored value is an [event channel](events.md#scriptableobject-channels).

[Health](../systems/health.md#health) still owns the pool: death, invulnerability, and max. [Weapon](../combat/weapons.md#weapon) still owns the magazine. The assets here mirror those numbers for UI that should not reference the player or the gun. Writing the mirror does not heal or reload. A placement cost that is one number spends a float the same way. That wallet is [building](../systems/building.md#data).

## Which store

| Store | Strength | Limit |
| --- | --- | --- |
| Singleton `MonoBehaviour` | Easy to find. One scene object. | Hidden dependency. A missing or duplicate instance fails at runtime. Scene load order matters. Awkward in a test. |
| Static field | Always there. No asset. | No inspector. Survives Play Mode when domain reload is off, unless you reset it. Every caller can write it. Hard to swap per level. |
| Dependency injection | The dependency is explicit and swappable per test or per scope. A composition root (your own, or a container) constructs it. | Heavier than a designer-tuned number. This page does not add a container. Assigning an asset in the inspector is the manual version of the same idea. |
| `ScriptableObject` variable | Designers assign the same asset on the writer and the reader. It survives a scene load. Play Mode can show the live value on the asset. | One asset is one value. Two players, or two enemies, share it if they share the asset. It is not saved, and it is not replicated. |

Use a variable for a fact many objects read: a mirrored health, a mirrored ammo count, a volume, a score. Use a runtime set for "who is alive right now". Use the [Health](../systems/health.md) component for one body's pool. Use a channel or a C# event, from the [event systems](events.md) page, when you need the moment and not the current value.

## Variable

`Initial Value` is the authored number. It is what the asset stores, and what a build ships. `Value` is the runtime number. It is `[NonSerialized]`, so a change during Play Mode is not written back to the asset when you exit. Entering Play Mode copies initial into runtime.

That copy cannot live in a field initialiser. It runs in two places:

- The asset's `OnEnable`, which runs when the asset is loaded. That covers a build, an asset first loaded during this Play Mode, and the editor with domain reload on.
- A `SubsystemRegistration` method that walks every variable already in memory. With **Enter Play Mode Options** and **Reload Domain** off, an asset that stayed loaded from the last Play Mode does not get `OnDisable` or `OnEnable` again, because those calls are part of the domain reload. This scan is what resets it. It runs before any scene `OnEnable`.

Both clear `Changed` too, so a listener that leaked from the last Play Mode is gone before this scene subscribes. Listeners subscribe in their own `OnEnable` and read `Value` once. The reset does not raise, because nobody is listening yet.

In a player build there is no exit from Play Mode. The shipped `Initial Value` is the value at build time. `OnEnable` runs when the asset is loaded, not on every scene change. A variable that stays loaded keeps its runtime value across scenes. That is what you want for a score, and it is why a health mirror must be pushed again by the player's `OnEnable`.

`Set` raises the C# event, then the optional [channel](events.md#scriptableobject-channels). The channel is a concrete asset whose payload is `T`, the same shape as `AmmoEventChannel` on the events page. `FloatEventChannel` below is that one-line subclass. Leave the slot empty and only the C# event runs. An equal value does not raise. A listener must not call `Set` on the same variable: the listeners already in this raise still see the value from this call, and the nested `Set` raises them again.

A subclass that declares `OnEnable` hides the reset. Call `base.OnEnable()`.

The block below is one listing, but Unity needs every `ScriptableObject` type you create assets from in its own file, named after the class: `FloatVariable.cs`, `IntVariable.cs`, `BoolVariable.cs`, and `FloatEventChannel.cs`. An asset whose class lives in a file of another name loses its script reference. `VariableAsset` and `Variable<T>` can share a file, because no asset is made from them directly.

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Non-generic root so one editor and one play-mode reset can see every variable.
/// </summary>
public abstract class VariableAsset : ScriptableObject
{
    public abstract void ResetRuntime();
    public abstract void ApplyInitial();
    public abstract string RuntimeText { get; }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetLoaded()
    {
        VariableAsset[] loaded = Resources.FindObjectsOfTypeAll<VariableAsset>();
        for (int i = 0; i < loaded.Length; i++)
        {
            if (loaded[i] != null)
                loaded[i].ResetRuntime();
        }
    }
}

/// <summary>
/// Authored initial value, runtime value that Play Mode must not save back.
/// </summary>
public abstract class Variable<T> : VariableAsset
{
    [SerializeField] T initialValue;
    [SerializeField] EventChannel<T> changedChannel;

    [NonSerialized] T runtimeValue;
    [NonSerialized] bool hasRuntime;
    [NonSerialized] Action<T> _changed;

    public event Action<T> Changed
    {
        add => _changed += value;
        remove => _changed -= value;
    }

    public T Initial => initialValue;

    public T Value
    {
        get => hasRuntime ? runtimeValue : initialValue;
        set => Set(value);
    }

    public void Set(T value)
    {
        if (hasRuntime && EqualityComparer<T>.Default.Equals(runtimeValue, value))
            return;

        runtimeValue = value;
        hasRuntime = true;

        Action<T> listeners = _changed;
        if (listeners != null)
            listeners.Invoke(value);
        if (changedChannel != null)
            changedChannel.Raise(value);
    }

    public override void ResetRuntime()
    {
        runtimeValue = initialValue;
        hasRuntime = true;
        _changed = null;
    }

    public override void ApplyInitial()
    {
        Set(initialValue);
    }

    public override string RuntimeText
    {
        get
        {
            T value = Value;
            return value is null ? "null" : value.ToString();
        }
    }

    protected void OnEnable()
    {
        ResetRuntime();
    }

    protected void OnValidate()
    {
        if (Application.isPlaying)
            return;
        runtimeValue = initialValue;
        hasRuntime = true;
    }
}

[CreateAssetMenu(fileName = "FloatVariable", menuName = "Game/Variables/Float")]
public class FloatVariable : Variable<float>
{
}

[CreateAssetMenu(fileName = "IntVariable", menuName = "Game/Variables/Int")]
public class IntVariable : Variable<int>
{
}

[CreateAssetMenu(fileName = "BoolVariable", menuName = "Game/Variables/Bool")]
public class BoolVariable : Variable<bool>
{
}

/// <summary>
/// Concrete channel so the float variable's slot has an asset to assign.
/// Same pattern as AmmoEventChannel on the events page. Do not add OnEnable here.
/// </summary>
[CreateAssetMenu(fileName = "FloatEvent", menuName = "Game/Events/Float Event")]
public class FloatEventChannel : EventChannel<float>
{
}
```

`Value.ToString()` on a float uses the current culture. It is the debug label, not the HUD.

The inspector locks **Initial Value** during Play Mode so a slider drag is not saved into the asset. Debug mode on the inspector ignores this editor and will still write the field. The runtime line repaints while playing, because a custom inspector does not refresh on its own.

```csharp
#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

[CustomEditor(typeof(VariableAsset), true)]
public class VariableAssetEditor : Editor
{
    void OnEnable()
    {
        EditorApplication.update += OnEditorUpdate;
    }

    void OnDisable()
    {
        EditorApplication.update -= OnEditorUpdate;
    }

    void OnEditorUpdate()
    {
        if (Application.isPlaying)
            Repaint();
    }

    public override void OnInspectorGUI()
    {
        serializedObject.Update();
        SerializedProperty initial = serializedObject.FindProperty("initialValue");
        SerializedProperty channel = serializedObject.FindProperty("changedChannel");
        using (new EditorGUI.DisabledScope(Application.isPlaying))
        {
            if (initial != null)
                EditorGUILayout.PropertyField(initial);
        }

        if (channel != null)
            EditorGUILayout.PropertyField(channel);
        serializedObject.ApplyModifiedProperties();

        var variable = (VariableAsset)target;
        EditorGUILayout.LabelField("Runtime", variable.RuntimeText);
        if (!Application.isPlaying)
            return;
        if (GUILayout.Button("Reset runtime to initial"))
            variable.ApplyInitial();
    }
}
#endif
```

Keep this editor in an Editor folder if the runtime assembly cannot see `UnityEditor`. The events page uses the same split.

## Reference

A `FloatReference` is either a constant, typed on the component, or a `FloatVariable` asset. The component that fires a shot, or a bar filling from a stand-in number, does not care which. Gameplay that changes the number should `Set` the variable. Setting the constant writes a serialised field on the scene object.

`Reference<float>` as a field type is unreliable in the inspector. Use the concrete subclass. The drawer is the small toggle in front of the value. A proper treatment of drawers, including height, prefab overrides, and lists, is still [Property drawers](../../roadmap.md#editor) on the roadmap. This one only switches the two stored fields.

```csharp
using System;
using UnityEngine;

[Serializable]
public class Reference<T>
{
    [SerializeField] bool useConstant = true;
    [SerializeField] T constantValue;
    [SerializeField] Variable<T> variable;

    public bool UseConstant => useConstant;
    public Variable<T> Variable => variable;

    public T Value
    {
        get
        {
            if (useConstant || variable == null)
                return constantValue;
            return variable.Value;
        }
        set
        {
            if (useConstant || variable == null)
                constantValue = value;
            else
                variable.Set(value);
        }
    }
}

[Serializable]
public class FloatReference : Reference<float>
{
}

[Serializable]
public class IntReference : Reference<int>
{
}

[Serializable]
public class BoolReference : Reference<bool>
{
}
```

```csharp
#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

[CustomPropertyDrawer(typeof(Reference<>), true)]
public class ReferenceDrawer : PropertyDrawer
{
    static readonly GUIContent[] Modes =
    {
        new GUIContent("Const", "Use the constant on this component."),
        new GUIContent("Var", "Use the shared variable asset.")
    };

    public override float GetPropertyHeight(SerializedProperty property, GUIContent label)
    {
        SerializedProperty value = ValueProperty(property);
        if (value == null)
            return EditorGUIUtility.singleLineHeight;
        return EditorGUI.GetPropertyHeight(value, label, true);
    }

    public override void OnGUI(Rect position, SerializedProperty property, GUIContent label)
    {
        EditorGUI.BeginProperty(position, label, property);
        SerializedProperty useConstant = property.FindPropertyRelative("useConstant");
        SerializedProperty constantValue = property.FindPropertyRelative("constantValue");
        SerializedProperty variable = property.FindPropertyRelative("variable");
        if (useConstant == null || constantValue == null || variable == null)
        {
            EditorGUI.LabelField(position, label.text, "Missing Reference fields.");
            EditorGUI.EndProperty();
            return;
        }

        float line = EditorGUIUtility.singleLineHeight;
        Rect row = new Rect(position.x, position.y, position.width, line);
        int indent = EditorGUI.indentLevel;
        EditorGUI.indentLevel = 0;

        Rect content = EditorGUI.PrefixLabel(row, GUIUtility.GetControlID(FocusType.Passive), label);
        const float popupWidth = 72f;
        Rect popup = new Rect(content.x, content.y, popupWidth, line);
        Rect field = new Rect(
            content.x + popupWidth + 4f,
            content.y,
            content.width - popupWidth - 4f,
            position.height);

        EditorGUI.BeginChangeCheck();
        int picked = EditorGUI.Popup(popup, useConstant.boolValue ? 0 : 1, Modes);
        if (EditorGUI.EndChangeCheck())
            useConstant.boolValue = picked == 0;

        EditorGUI.PropertyField(
            field,
            useConstant.boolValue ? constantValue : variable,
            GUIContent.none,
            true);

        EditorGUI.indentLevel = indent;
        EditorGUI.EndProperty();
    }

    static SerializedProperty ValueProperty(SerializedProperty property)
    {
        SerializedProperty useConstant = property.FindPropertyRelative("useConstant");
        if (useConstant == null)
            return null;
        string name = useConstant.boolValue ? "constantValue" : "variable";
        return property.FindPropertyRelative(name);
    }
}
#endif
```

Subscribe to `reference.Variable` only when `UseConstant` is off and the asset is assigned. A constant has no `Changed` event. Pair the subscribe with `OnDisable`, as on the [events](events.md#lifecycle) page.

## Runtime sets

A set is the variable pattern for a list: who is registered right now. The list is not serialised. It is cleared the same two ways as a variable, by the asset's `OnEnable` and by a `SubsystemRegistration` scan, before scene `OnEnable`, then each member adds itself. `OnDisable` removes. Death is not `OnDisable` unless you disable or destroy the body, so the enemy member also unregisters on [`Health.Died`](../systems/health.md#health), and adds itself back when `Revive` raises `HealthChanged` on a living body.

The player does not get this component. The set would otherwise count the player as an enemy. One set asset is one list. Two rooms that share it share the count.

```csharp
using System;
using System.Collections.Generic;
using System.Text;
using UnityEngine;

public abstract class RuntimeSetAsset : ScriptableObject
{
    public abstract int Count { get; }
    public abstract void ClearSet();
    public abstract string DebugList();

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetLoaded()
    {
        RuntimeSetAsset[] loaded = Resources.FindObjectsOfTypeAll<RuntimeSetAsset>();
        for (int i = 0; i < loaded.Length; i++)
        {
            if (loaded[i] != null)
                loaded[i].ClearSet();
        }
    }
}

public abstract class RuntimeSet<T> : RuntimeSetAsset where T : UnityEngine.Object
{
    readonly List<T> items = new List<T>();
    Action _changed;

    public event Action Changed
    {
        add => _changed += value;
        remove => _changed -= value;
    }

    public override int Count
    {
        get
        {
            Compact();
            return items.Count;
        }
    }

    public T At(int index)
    {
        Compact();
        return items[index];
    }

    public bool Add(T item)
    {
        if (item == null || items.Contains(item))
            return false;
        items.Add(item);
        _changed?.Invoke();
        return true;
    }

    public bool Remove(T item)
    {
        if (item == null)
            return false;
        if (!items.Remove(item))
            return false;
        _changed?.Invoke();
        return true;
    }

    public override void ClearSet()
    {
        items.Clear();
        _changed = null;
    }

    public override string DebugList()
    {
        Compact();
        if (items.Count == 0)
            return "(none)";

        int shown = Mathf.Min(items.Count, 12);
        var builder = new StringBuilder();
        for (int i = 0; i < shown; i++)
        {
            if (i > 0)
                builder.Append('\n');
            builder.Append(items[i].name);
        }

        if (items.Count > shown)
            builder.Append("\n...");
        return builder.ToString();
    }

    protected void OnEnable()
    {
        ClearSet();
    }

    void Compact()
    {
        for (int i = items.Count - 1; i >= 0; i--)
        {
            if (items[i] == null)
                items.RemoveAt(i);
        }
    }
}

[CreateAssetMenu(fileName = "HealthSet", menuName = "Game/Runtime Sets/Health Set")]
public class HealthRuntimeSet : RuntimeSet<Health>
{
}
```

```csharp
using UnityEngine;

/// <summary>
/// Registers this body's Health while it is alive. Do not put it on the player.
/// </summary>
[DisallowMultipleComponent]
public class HealthSetMember : MonoBehaviour
{
    [SerializeField] HealthRuntimeSet set;
    Health _health;

    void OnEnable()
    {
        _health = GetComponent<Health>();
        if (_health == null)
            return;

        _health.Died += OnDied;
        _health.HealthChanged += OnHealthChanged;
        if (set != null && !_health.IsDead)
            set.Add(_health);
    }

    void OnDisable()
    {
        if (_health == null)
            return;

        _health.Died -= OnDied;
        _health.HealthChanged -= OnHealthChanged;
        if (set != null)
            set.Remove(_health);
    }

    void OnDied()
    {
        if (set != null)
            set.Remove(_health);
    }

    void OnHealthChanged(float current, float max)
    {
        // Revive raises HealthChanged on a living body. Add ignores a body already in the set.
        if (set != null && !_health.IsDead)
            set.Add(_health);
    }
}
```

```csharp
using TMPro;
using UnityEngine;

/// <summary>
/// Count of a runtime set. This object stays active.
/// </summary>
[DisallowMultipleComponent]
public class RuntimeSetCountLabel : MonoBehaviour
{
    [SerializeField] HealthRuntimeSet set;
    [SerializeField] TMP_Text label;

    void OnEnable()
    {
        if (set == null)
            return;
        set.Changed += Refresh;
        Refresh();
    }

    void OnDisable()
    {
        if (set != null)
            set.Changed -= Refresh;
    }

    void Refresh()
    {
        if (label != null && set != null)
            label.SetText("{0}", set.Count);
    }
}
```

`List.Remove` does not use Unity's overloaded `==`. A destroyed object can sit in the list if `OnDisable` did not run. `Count` drops those holes. It does not raise `Changed` for them.

## Health and ammo

The [health bar](../systems/health.md#health-bar) listens to `Health` directly. Use that when the bar sits on the player. Use the mirror when the HUD is another object and should only know the asset.

`HealthChanged` passes current and max. Two float variables carry them. The bridge pushes on enable, so a bar that enables first still corrects itself when the push raises `Changed`. A bar that enables second reads `Value` and does not need that event. The **Image** type is **Filled**, the same rule as the health page.

```csharp
using UnityEngine;

/// <summary>
/// Copies Health into shared floats. Does not replace Health.
/// </summary>
[DisallowMultipleComponent]
public class HealthToVariables : MonoBehaviour
{
    [SerializeField] Health health;
    [SerializeField] FloatVariable current;
    [SerializeField] FloatVariable max;

    void OnEnable()
    {
        if (health == null)
            return;
        health.HealthChanged += Push;
        Push(health.Current, health.Max);
    }

    void OnDisable()
    {
        if (health != null)
            health.HealthChanged -= Push;
    }

    void Push(float currentValue, float maxValue)
    {
        if (current != null)
            current.Set(currentValue);
        if (max != null)
            max.Set(maxValue);
    }
}
```

```csharp
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Filled image from two float variables. No Health reference.
/// </summary>
[DisallowMultipleComponent]
public class VariableHealthBar : MonoBehaviour
{
    [SerializeField] FloatVariable current;
    [SerializeField] FloatVariable max;
    [SerializeField] Image fill;

    void OnEnable()
    {
        if (current != null)
            current.Changed += OnChanged;
        if (max != null)
            max.Changed += OnChanged;
        OnChanged(0f);
    }

    void OnDisable()
    {
        if (current != null)
            current.Changed -= OnChanged;
        if (max != null)
            max.Changed -= OnChanged;
    }

    void OnChanged(float _)
    {
        if (fill == null || current == null)
            return;
        float top = max != null ? max.Value : 0f;
        fill.fillAmount = top <= 0f ? 0f : Mathf.Clamp01(current.Value / top);
    }
}
```

Ammo is the same mirror. [`AmmoReadout`](../combat/weapons.md#readout-and-effects) is the direct listener, including the weapon swap. The label here only knows the two int assets. `WeaponAmmoChannel` on the events page is the moment. This is the stored count.

```csharp
using UnityEngine;

[DisallowMultipleComponent]
public class WeaponAmmoToVariables : MonoBehaviour
{
    [SerializeField] Weapon weapon;
    [SerializeField] IntVariable magazine;
    [SerializeField] IntVariable reserve;

    void OnEnable()
    {
        if (weapon == null)
            return;
        weapon.AmmoChanged += Push;
        Push(weapon.Magazine, weapon.Reserve);
    }

    void OnDisable()
    {
        if (weapon != null)
            weapon.AmmoChanged -= Push;
    }

    void Push(int magazineValue, int reserveValue)
    {
        if (magazine != null)
            magazine.Set(magazineValue);
        if (reserve != null)
            reserve.Set(reserveValue);
    }
}
```

```csharp
using TMPro;
using UnityEngine;

[DisallowMultipleComponent]
public class AmmoVariableLabel : MonoBehaviour
{
    [SerializeField] IntVariable magazine;
    [SerializeField] IntVariable reserve;
    [SerializeField] TMP_Text label;

    void OnEnable()
    {
        if (magazine != null)
            magazine.Changed += OnChanged;
        if (reserve != null)
            reserve.Changed += OnChanged;
        OnChanged(0);
    }

    void OnDisable()
    {
        if (magazine != null)
            magazine.Changed -= OnChanged;
        if (reserve != null)
            reserve.Changed -= OnChanged;
    }

    void OnChanged(int _)
    {
        if (label == null || magazine == null)
            return;
        int spare = reserve != null ? reserve.Value : 0;
        label.SetText("{0} / {1}", magazine.Value, spare);
    }
}
```

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Initial Value | `0` or false | Authored value. Copied into the runtime value when play starts. The game does not write it. |
| Changed Channel | Empty | Optional channel raised after a runtime change. Payload type matches the variable. |
| Use Constant | On | The reference reads Constant Value and ignores the asset. |
| Constant Value | `0` or false | Used while Use Constant is on. A runtime write dirties the scene object. |
| Variable | Empty | Asset used while Use Constant is off. Empty falls back to the constant. |

## Setup

1. Copy the channel base from the [events](events.md#scriptableobject-channels) page, then the variable file. Create `Game/Variables/Float` twice: player health, and player max. Set **Initial Value** to the player's full health so the bar is right before the bridge pushes.
2. On the player, add `HealthToVariables`. Assign `Health` and the two assets. On the HUD, add `VariableHealthBar`. The **Image** is **Filled**. Leave the HUD off the player if the point is that it has no `Health` field.
3. Create two `Game/Variables/Int` assets. Add `WeaponAmmoToVariables` on the weapon and `AmmoVariableLabel` on the HUD. The direct counter remains [`AmmoReadout`](../combat/weapons.md#readout-and-effects) when the label can hold the `Weapon`.
4. Create `Game/Runtime Sets/Health Set`. Add `HealthSetMember` to each enemy, not the player. Add `RuntimeSetCountLabel` on an object that stays active.
5. Enter Play Mode and select the health asset. **Runtime** follows damage. **Initial Value** stays locked. **Reset runtime to initial** writes the authored number and notifies listeners. It does not heal the `Health` component.
6. Optional: create `Game/Events/Float Event`, assign it as **Changed Channel**, and listen with a `Void` style listener that takes a float. Pair that listener the way the events page pairs `OnEnable` and `OnDisable`.

## Pitfalls

!!! warning "Common pitfalls"

    A serialised runtime field is how Play Mode edits leak into the asset and into the next build. Only `Initial Value` is serialised. Do not copy `Value` back onto it in `OnDisable`. The custom inspector locks it during play. Inspector debug mode does not, and it will save what you type.

    With **Reload Domain** off, an asset that stayed loaded does not get `OnEnable` again on entering Play Mode, and field initialisers do not re-run. A reset that lived only in either runs once per editor session. The `SubsystemRegistration` scan is what resets those assets. A subclass that declares `OnEnable` and does not call `base.OnEnable()` also skips the load-time reset. **Reload Scene** off as well means scene objects do not run `OnEnable` again. Clearing `Changed` or the set then drops live listeners and members, and nothing puts them back. The events page has the same rule for the bus.

    In a build, `OnEnable` runs when the asset loads, not when the scene changes and not on a timer. A reference from a scene loads it with that scene. `Resources.Load` loads it on the call. An Addressables load runs `OnEnable` when the handle completes, which may be halfway through a level, and a release can unload it. The next load resets runtime to **Initial Value**. Preloaded assets load at startup and then stay. An asset that never loads never resets and is never read.

    `Resources.FindObjectsOfTypeAll` in the editor sees every loaded variable, not only the open scene. It does not see an asset that nothing has loaded. Do not treat that scan as a list of the variables in the build.

    One asset is one value on that machine. Two local players writing one health variable overwrite each other. A host and a client do not share the asset's memory. This is not a network variable. Per-enemy health stays on `Health`. The set counts bodies that registered. It does not replicate.

    Select the asset while playing to see **Runtime**. The line repaints only while that inspector is open. Listeners are C# events, so the inspector does not list them. A bar that does not move is usually subscribed before the reset cleared the list, or subscribed with a closure that `OnDisable` cannot remove.

    Several classes share a listing on this page. Unity needs each `MonoBehaviour` and each `ScriptableObject` you create assets from in its own file, named after the class, or components and assets lose their script reference.

    `Set` from inside `Changed` raises again. HUD code should read `Value` and not write it. `HealthToVariables` is the writer. The bar is the reader.
