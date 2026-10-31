---
engine: Unity
version: 6+
package: Input System 1.x
uses:
  - name: Top-down survival
    text: A controls menu where players move every action, including the WASD keys one at a time.
  - name: Shooters
    text: Separate keyboard and gamepad bindings, with duplicates swapped instead of doubled up.
  - name: Strategy and tactics
    text: Long lists of hotkeys that players expect to set themselves.
---

# Rebinding

Players change their own controls. The Input System does the hard part: it waits for the player to press something and writes it as an **override** on the binding, leaving the asset untouched. This page adds what a controls menu needs around that: a row per binding, cancel and excluded controls, composite keys such as WASD, separate keyboard and gamepad columns, swapping duplicates, and saving.

## Read actions, not devices

A rebind changes what an **action** responds to. Code that reads `Keyboard.current.wKey` directly never sees it. Read actions instead:

```csharp
using UnityEngine;
using UnityEngine.InputSystem;

public class MoveInput : MonoBehaviour
{
    // Project-wide actions (Project Settings → Input System Package), or an asset you enable yourself.
    InputAction _move;
    InputAction _attack;

    void Awake()
    {
        _move = InputSystem.actions.FindAction("Player/Move", throwIfNotFound: true);
        _attack = InputSystem.actions.FindAction("Player/Attack", throwIfNotFound: true);
    }

    void Update()
    {
        Vector2 move = _move.ReadValue<Vector2>();
        bool attack = _attack.WasPressedThisFrame();
        // ...hand to the controller, as the movement pages do with device reads.
    }
}
```

Project-wide actions are enabled when the game starts. An `InputActionAsset` assigned to a component must be enabled with `Enable()`. Either way, use one asset for the game, so the controls menu and the game read the same bindings.

## Bindings and indices

An action has a flat list of bindings. A composite, such as a WASD **2D Vector**, is one binding with `isComposite` set, followed by its parts, each with `isPartOfComposite` and a `name` such as `up` or `left`.

| Index | Binding | Groups |
| --- | --- | --- |
| 0 | `<Gamepad>/leftStick` | Gamepad |
| 1 | 2D Vector (composite) | |
| 2 | up: `<Keyboard>/w` | Keyboard&Mouse |
| 3 | down: `<Keyboard>/s` | Keyboard&Mouse |
| 4 | left: `<Keyboard>/a` | Keyboard&Mouse |
| 5 | right: `<Keyboard>/d` | Keyboard&Mouse |

The **groups** are the control schemes. A controls menu with a keyboard column and a gamepad column picks bindings by group: `action.GetBindingIndex(InputBinding.MaskByGroup("Gamepad"))`.

## The rebind row

One row in the controls menu: a label, a button showing the current binding, and a reset. Clicking the button waits for input.

```csharp
using System;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UI;

/// <summary>
/// One binding in a controls menu. Rebinds a single binding, or every part of a composite in turn.
/// </summary>
public class RebindRow : MonoBehaviour
{
    [SerializeField] InputActionReference action;
    [Tooltip("Control scheme to rebind, such as Keyboard&Mouse or Gamepad.")]
    [SerializeField] string group = "Keyboard&Mouse";
    [Tooltip("For a composite, the part to rebind, such as 'up'. Empty rebinds every part in turn.")]
    [SerializeField] string compositePart;

    [SerializeField] TMP_Text label;
    [SerializeField] TMP_Text bindingText;
    [SerializeField] Button rebindButton;
    [SerializeField] Button resetButton;
    [SerializeField] GameObject waitingOverlay;

    public static event Action BindingsChanged;

    InputActionRebindingExtensions.RebindingOperation _operation;

    void OnEnable()
    {
        rebindButton.onClick.AddListener(StartRebind);
        resetButton.onClick.AddListener(ResetBinding);
        BindingsChanged += Refresh;
        Refresh();
    }

    void OnDisable()
    {
        rebindButton.onClick.RemoveListener(StartRebind);
        resetButton.onClick.RemoveListener(ResetBinding);
        BindingsChanged -= Refresh;
        Finish(); // a menu closed mid-rebind must not leak the operation
    }

    InputAction Action => action.action;

    /// <summary>The binding indices this row covers: one, or the parts of a composite.</summary>
    int[] Targets()
    {
        int first = Action.GetBindingIndex(InputBinding.MaskByGroup(group));
        if (first < 0)
            return Array.Empty<int>();

        // A part of a composite carries the group; the composite itself does not.
        if (!Action.bindings[first].isPartOfComposite)
            return new[] { first };

        var parts = new System.Collections.Generic.List<int>();
        for (int i = first; i < Action.bindings.Count && Action.bindings[i].isPartOfComposite; i++)
        {
            if (string.IsNullOrEmpty(compositePart) || Action.bindings[i].name == compositePart)
                parts.Add(i);
        }
        return parts.ToArray();
    }

    void Refresh()
    {
        if (label != null)
            label.text = string.IsNullOrEmpty(compositePart) ? Action.name : Action.name + " " + compositePart;

        int[] targets = Targets();
        var text = new System.Text.StringBuilder();
        foreach (int i in targets)
        {
            if (text.Length > 0)
                text.Append(' ');
            text.Append(Action.GetBindingDisplayString(i, InputBinding.DisplayStringOptions.DontIncludeInteractions));
        }
        bindingText.text = text.Length > 0 ? text.ToString() : "-";
    }

    void StartRebind()
    {
        int[] targets = Targets();
        if (targets.Length > 0)
            Rebind(targets, 0);
    }

    void Rebind(int[] targets, int step)
    {
        Finish();
        int index = targets[step];
        string previous = Action.bindings[index].effectivePath;

        // An enabled action cannot be rebound.
        bool wasEnabled = Action.enabled;
        Action.Disable();

        if (waitingOverlay != null)
            waitingOverlay.SetActive(true);

        _operation = Action.PerformInteractiveRebinding(index)
            .WithControlsExcluding("<Mouse>/position")
            .WithControlsExcluding("<Mouse>/delta")
            .WithControlsExcluding("<Pointer>/position")
            .WithCancelingThrough("<Keyboard>/escape")
            .OnMatchWaitForAnother(0.1f) // so a stick nudge does not win over the button the player meant
            .OnCancel(_ =>
            {
                Finish();
                if (wasEnabled)
                    Action.Enable();
                Refresh();
            })
            .OnComplete(_ =>
            {
                SwapDuplicates(index, previous);
                Finish();
                if (wasEnabled)
                    Action.Enable();

                RebindStore.Save(Action.actionMap.asset);
                BindingsChanged?.Invoke();

                if (step + 1 < targets.Length)
                    Rebind(targets, step + 1); // next part of the composite
            });

        _operation.Start();
    }

    /// <summary>If another binding in the same group now uses the same control, give it the old one.</summary>
    void SwapDuplicates(int index, string previous)
    {
        InputBinding changed = Action.bindings[index];
        foreach (InputAction other in Action.actionMap.actions)
        {
            for (int i = 0; i < other.bindings.Count; i++)
            {
                if (other == Action && i == index)
                    continue;
                InputBinding binding = other.bindings[i];
                if (binding.isComposite || binding.effectivePath != changed.effectivePath)
                    continue;
                if (!InputBinding.MaskByGroup(group).Matches(binding))
                    continue;

                other.ApplyBindingOverride(i, previous);
            }
        }
    }

    void ResetBinding()
    {
        foreach (int i in Targets())
            Action.RemoveBindingOverride(i);
        RebindStore.Save(Action.actionMap.asset);
        BindingsChanged?.Invoke();
    }

    void Finish()
    {
        _operation?.Dispose(); // operations hold native memory
        _operation = null;
        if (waitingOverlay != null)
            waitingOverlay.SetActive(false);
    }
}
```

- `PerformInteractiveRebinding(index)` targets one binding, and its defaults already expect the action's control type: a button action will not accept a stick.
- **Excluded controls** stop the mouse moving from counting as the new binding. Add others your game should never bind, such as `<Keyboard>/anyKey`.
- **Cancel through Escape** means Escape cannot itself be bound. That is the usual trade, with Escape kept for the pause menu.
- **Composites** step through their parts: press a key for up, then down, then left, then right. Set **Composite Part** to rebind a single part from its own row.
- **Swapping** gives the clashing binding the player's old key, which is what most games do. Refusing the rebind and showing a message is the alternative.
- Rebinding the gamepad column is the same row with **Group** set to `Gamepad`. The player presses a button on the pad.

`InputActionReference` is the asset-safe way to point at an action from the inspector. The **Rebinding UI** sample in the Input System package, in the Package Manager under **Samples**, is a fuller version of this row, with icons for gamepad buttons.

## Saving

Overrides are settings, not a [save slot](../systems/saving/index.md#what-does-not-go-in-a-save). Keep them in `PlayerPrefs` or a settings file.

```csharp
using UnityEngine;
using UnityEngine.InputSystem;

public static class RebindStore
{
    const string Key = "input.rebinds";

    public static void Save(InputActionAsset asset)
    {
        PlayerPrefs.SetString(Key, asset.SaveBindingOverridesAsJson());
        PlayerPrefs.Save();
    }

    /// <summary>Call once at startup, before gameplay reads input.</summary>
    public static void Load(InputActionAsset asset)
    {
        string json = PlayerPrefs.GetString(Key, string.Empty);
        if (!string.IsNullOrEmpty(json))
            asset.LoadBindingOverridesFromJson(json);
    }

    public static void ResetAll(InputActionAsset asset)
    {
        asset.RemoveAllBindingOverrides();
        PlayerPrefs.DeleteKey(Key);
    }
}
```

Call `RebindStore.Load(InputSystem.actions)` from the [bootstrap](../architecture/services.md) at startup. The JSON stores overrides by binding id, so adding new actions in an update keeps the player's old overrides on the bindings that still exist.

## Showing bindings elsewhere

On-screen prompts, such as "Press **E** to search", should read the binding too, or they lie after a rebind:

```csharp
string key = interactAction.GetBindingDisplayString(
    interactAction.GetBindingIndex(InputBinding.MaskByGroup("Keyboard&Mouse")));
prompt.text = "Press " + key + " to search";
```

Keyboard bindings are by **physical key position**: `<Keyboard>/w` is the key where W sits on a US layout. On an AZERTY keyboard it is labelled Z, and `GetBindingDisplayString` returns Z, which is what the player sees. Display strings can change while the game runs, if the player switches layout. Refresh prompts when they open, not once at startup.

## Setup

1. Make the game's actions in one asset, ideally the project-wide actions, with a **Keyboard&Mouse** and a **Gamepad** control scheme, and every binding in one of them.
2. Switch gameplay input from device reads to actions, as in the first snippet.
3. Build a controls menu with a `RebindRow` per action and group. For WASD, either one row that steps through all four, or four rows each with a **Composite Part**.
4. Load overrides at startup with `RebindStore.Load`. Add a **Reset all** button that calls `ResetAll` and raises a refresh.

!!! warning "Common pitfalls"

    Gameplay code reading `Keyboard.current` ignores every rebind. Read actions.

    Rebinding an enabled action throws. Disable it for the operation and enable it after.

    A rebinding operation that is never disposed leaks native memory. Dispose it on complete, on cancel, and when the menu closes mid-rebind.

    Without excluded controls, moving the mouse to click the button binds the action to mouse movement.

    Bindings without a control scheme group are not found by group masks, so they never show in either column. Put every binding in a group.
