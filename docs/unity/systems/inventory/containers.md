---
engine: Unity
version: 6+
uses:
  - name: Top-down survival
    text: Cupboards, car boots, and corpses that take time to search, roll their loot on first look, and stay empty once looted.
  - name: RPGs
    text: Chests that need a key, or a crowbar and some noise.
  - name: Open worlds
    text: Thousands of containers that cost nothing until someone opens one.
---

# Lootable containers

A cupboard, a car boot, a corpse. The player searches it, which takes time, and its contents are rolled from a [loot table](../loot.md) the first time anyone looks. After that the contents are real: what the player leaves stays there, and the [world state](../saving/world-state.md#a-container) save remembers it. A locked container needs a key, or forcing open, which is slower and makes [noise](../../ai/noise.md).

## How it fits together

| Piece | Job |
| --- | --- |
| [`ListInventory`](list.md) | Holds the contents. Leave its starting stacks empty: the loot table fills it. |
| `ContainerSave` | From [world state](../saving/world-state.md#a-container). Saves contents and the searched flag. |
| `LootContainer` | The interactable. Starts a search action, rolls loot on the first completed search, handles locks, and opens the UI. |
| [`ActionRunner`](../timed-actions.md#runner) | On the player. Runs the search as a timed action, cancelled by walking away. |
| [`SaveId`](../saving/world-state.md#save-id) | On the container, so it has a stable id. |

Rolling on first search, not at level load, means a town of a thousand cupboards costs nothing until the player starts opening them. It also means that reloading a save and searching again rolls again. If that is an exploit for your game, save the roller's state too, as [pity](../loot.md#pity) describes, or roll with a seed made from the container's id and the world seed.

## Container

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// A searchable container. Rolls its loot table into the bag on the first completed search.
/// </summary>
[RequireComponent(typeof(ListInventory), typeof(ContainerSave))]
public class LootContainer : MonoBehaviour, IInteractable
{
    [SerializeField] LootTable table;
    [SerializeField] string displayName = "Cupboard";
    [Tooltip("First search: finding what is inside.")]
    [SerializeField] float searchSeconds = 2.5f;
    [Tooltip("Already searched: just opening it.")]
    [SerializeField] float openSeconds = 0.4f;
    [SerializeField] float reach = 2f;

    [Header("Lock")]
    [SerializeField] bool locked;
    [Tooltip("Opens it at once. Empty: no key exists.")]
    [SerializeField] ItemDefinition key;
    [Tooltip("Forcing it open, such as with a crowbar. Empty: cannot be forced.")]
    [SerializeField] ItemDefinition forceTool;
    [SerializeField] float forceSeconds = 4f;
    [SerializeField] float forceNoiseRadius = 15f;

    public ListInventory Bag { get; private set; }
    public bool Searched => _save.Searched;
    public bool Locked => locked;
    public string DisplayName => displayName;

    /// <summary>Show the container UI next to the player's bag.</summary>
    public static event Action<LootContainer, Interactor> Opened;
    /// <summary>For an outline or a "searched" marker.</summary>
    public event Action<LootContainer> SearchedChanged;

    ContainerSave _save;
    readonly List<ItemStack> _rolled = new List<ItemStack>();

    void Awake()
    {
        Bag = GetComponent<ListInventory>();
        _save = GetComponent<ContainerSave>();
    }

    // IInteractable. Hold Duration is 0: the timed action is the wait, not the button.
    public string Prompt => locked ? "Locked " + displayName : (Searched ? "Open " : "Search ") + displayName;
    public float HoldDuration => 0f;
    public bool CanInteract(Interactor interactor) => isActiveAndEnabled;
    public void OnFocusEnter(Interactor interactor) { }
    public void OnFocusExit(Interactor interactor) { }
    public void OnHoldChanged(Interactor interactor, float progress) { }

    public void Interact(Interactor interactor)
    {
        if (!interactor.TryGetComponent(out ActionRunner runner))
            return;

        if (locked)
        {
            interactor.TryGetComponent(out ListInventory playerBag);
            if (key != null && playerBag != null && playerBag.Contains(key))
                locked = false; // the key opens it at once; carry on to the search
            else if (forceTool != null && playerBag != null && playerBag.Contains(forceTool))
            {
                runner.Do(new DelegateAction("Force " + displayName, forceSeconds, _ =>
                {
                    locked = false;
                    Noise.Emit(transform.position, forceNoiseRadius, interactor.gameObject);
                }, MovePolicy.Cancel, InReach));
                return;
            }
            else
                return; // a prompt elsewhere can say what is needed
        }

        float seconds = Searched ? openSeconds : searchSeconds;
        runner.Do(new DelegateAction((Searched ? "Open " : "Search ") + displayName, seconds,
            _ => Open(interactor), MovePolicy.Cancel, InReach));
    }

    bool InReach(ActionRunner actor) =>
        this != null && (actor.transform.position - transform.position).sqrMagnitude <= reach * reach;

    void Open(Interactor interactor)
    {
        if (!Searched)
        {
            _rolled.Clear();
            LootDropper.Roller.Roll(table, _rolled);
            foreach (ItemStack stack in _rolled)
                Bag.TryAdd(stack, out _); // what does not fit is lost: size containers above the table's maximum
            _save.Searched = true;
            SearchedChanged?.Invoke(this);
        }
        Opened?.Invoke(this, interactor);
    }
}
```

- `IInteractable` and `Interactor` are from [interaction](../../mechanics/interaction.md). `DelegateAction`, `MovePolicy`, and `ActionRunner` are from [timed actions](../timed-actions.md).
- **Searched** lives on `ContainerSave`, so the save restores it with the contents. An unsearched container saves as empty and unsearched, and rolls when first opened after the load.
- The lock state here is not saved. Save it with a second `ISaveState` on the container, or add it to `ContainerSave`'s state, if forced locks must stay forced.
- `Noise.Emit` is the [perception](../../ai/perception.md#hearing) noise. The [noise sources](../../ai/noise.md) page also attracts the horde.

## Searching

The search is a [timed action](../timed-actions.md): a progress bar, cancelled by moving and by being hit, and invalid once out of reach. Searching an already searched container is quicker, because the player only needs to open it.

Tuning:

| Container | Search | Open | Notes |
| --- | --- | --- | --- |
| Drawer, cupboard | 1.5–2.5 s | 0.3 s | The common case. |
| Car boot | 3 s | 0.5 s | Car alarm chance on force. |
| Corpse | 2 s | 0.5 s | Roll from the zombie's table. A [loot dropper](../loot.md#dropper) can fill a container on the corpse instead of the ground. |
| Safe | 1 s | 0.5 s | Locked, key or long force. |

A **Search** stat or skill shortens all of them through the runner's action speed.

## Moving items

The container UI shows two [list inventories](list.md) side by side. Moving an item between them is remove-then-add, putting it back if it does not fit:

```csharp
/// <summary>Moves one item instance between bags. False, and nothing moves, if it does not fit.</summary>
public static bool Transfer(ListInventory from, ListInventory to, ItemInstance item)
{
    if (!from.ContainsInstance(item) || !to.CanAccept(new ItemStack(item)))
        return false;
    if (!from.TryRemoveInstance(item))
        return false;
    if (to.TryAdd(new ItemStack(item), out ItemStack remainder))
        return true;

    // Partly fitted: return what did not.
    if (!remainder.IsEmpty)
        from.TryAdd(remainder, out _);
    return false;
}
```

Moving items should itself take a moment in a slow-paced survival game: a short timed action per transfer, or per "take all", which can be interrupted like any other.

## Respawning loot

Most survival games never refill a searched container. Some refill slowly, so a long game does not run dry. To refill, store the game day when searched, and on a later open, if enough days have passed and the bag is empty, set `Searched` back to false so the next open rolls again. Use the [game clock](../../rendering/day-night.md), not real time, and save the day with the container.

## Setup

1. Add a `ListInventory` with enough **Capacity** for the table's largest roll, and no starting stacks.
2. Add `ContainerSave` with the item catalogue, a `SaveId`, and `LootContainer` with a loot table.
3. Put a collider on a layer the player's `Interactor` queries.
4. Add an `ActionRunner` to the player, and a container screen that listens to `LootContainer.Opened`.

!!! warning "Common pitfalls"

    Starting stacks on the container's bag are added every time the level loads, on top of what the save restored or the player left. Use the loot table.

    Rolling loot at level load costs a roll per container in the level, most of which nobody opens. Roll on first search.

    A container whose search completes after the player has walked away. Give the action a reach check.

    Loot that does not fit the bag disappears. Size the bag above the table's maximum roll.

    Containers without a `SaveId` lose their contents and searched flag on every load.
