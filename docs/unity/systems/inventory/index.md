---
engine: Unity
version: 6+
---

# Inventory

One item definition, one stack, and one interface, shared by the four bags below and by [equipment](equipment.md). A list, a grid, a row of slots, and a weight cap disagree about space. They should not disagree about what an item is.

The numbers a piece of gear adds live on the [stat sheet](../health.md#stats). A gun the hotbar selects still fires through the [weapon holder](../../combat/weapons.md#holder). A placed piece that spends materials uses `Contains` and `TryRemove`. That loop is [building](../building.md). Dragging icons between slots is not on this page. That UI is [drag and drop](../../../roadmap.md#interface). Writing the bag to disk is not on this page either. Store ids, then use the [save and load](../../../roadmap.md#game-flow) work when it exists. Rolling a drop into the bag is [loot tables](../loot.md).

## Which bag

| Style | Use it when | Limit |
| --- | --- | --- |
| [List](list.md) | The player sorts and filters a few dozen stacks. Crafting, a loot dump, a shop. | A greatsword and a coin take the same row. There is no shape. |
| [Grid](grid.md) | The shape is a decision. A backpack, a Tetris loot screen. | First-fit leaves holes. It is not an optimal packer. Rotation and swap have to refuse anything that does not fit, or items disappear. |
| [Slots and hotbar](slots.md) | The player picks a fixed index with a number key. A bar, a shop cell, a gear doll's neighbour. | Empty holes stay empty. `TryAdd` fills the lowest free index, which includes the hotbar. |
| [Weight](weight.md) | The fantasy is mass, not shape. Encumbrance slows the body through a [stat modifier](../health.md#modifier-order). | Weight does not place items. It refuses mass, in front of a list. A feather and an anvil are the same kind of problem only if a grid is also in front. |

Use a list unless the shape or the key binding is the point. Add weight in front of that list when mass matters. Use [equipment](equipment.md) for what is worn, and keep the worn pieces out of the bag until they are unequipped.

The bag is a component on the actor. It is not a `ScriptableObject`. An asset would be one shared bag for every object that referenced it, which is the limit already called out for [shared variables](../../architecture/variables.md). Two players need two components.

## Definition

`Id` is the save key. Leave it empty and the asset name is used, which means renaming the asset changes the key. Set the id once and leave it. `MaxStack` is at least 1. A definition with durability forces max stack 1, so two worn swords never merge. `GridSize` is the rectangle a [grid](grid.md) occupies. The other bags ignore it. `Slots` is which [equipment](equipment.md) socket may hold it. `TwoHanded` occupies main hand and forbids an off-hand item. `Bonuses` are the authored modifier numbers. The live `StatModifier` is created when the item is equipped, because a modifier needs a source and the definition must not hold one.

`StatDefinition` and `ModifierOperation` are the types on the [stats](../health.md#stats) page. Copy those files before this one.

```csharp
using System;
using UnityEngine;

public enum ItemCategory
{
    Misc,
    Consumable,
    Material,
    Weapon,
    Armour,
    Quest
}

public enum EquipSlotId
{
    Head = 0,
    Chest = 1,
    Legs = 2,
    Feet = 3,
    MainHand = 4,
    OffHand = 5
}

[Flags]
public enum EquipSlotMask
{
    None = 0,
    Head = 1 << 0,
    Chest = 1 << 1,
    Legs = 1 << 2,
    Feet = 1 << 3,
    MainHand = 1 << 4,
    OffHand = 1 << 5
}

/// <summary>
/// Authored bonus. The equipment page turns this into a StatModifier
/// when the item is worn. Value is a fraction for both percent operations.
/// </summary>
[Serializable]
public struct ItemStatBonus
{
    public StatDefinition stat;
    public ModifierOperation operation;
    public float value;
}

/// <summary>
/// The shared item. Runtime counts and durability do not live here.
/// </summary>
[CreateAssetMenu(fileName = "Item", menuName = "Game/Item Definition")]
public class ItemDefinition : ScriptableObject
{
    [SerializeField] string id;
    [SerializeField] string displayName;
    [SerializeField] Sprite icon;
    [TextArea] [SerializeField] string description;
    [SerializeField] int maxStack = 1;
    [SerializeField] float weight = 1f;
    [SerializeField] Vector2Int gridSize = Vector2Int.one;
    [SerializeField] ItemCategory category;
    [SerializeField] string[] tags = Array.Empty<string>();
    [SerializeField] EquipSlotMask slots = EquipSlotMask.None;
    [SerializeField] bool twoHanded;
    [SerializeField] float maxDurability;
    [SerializeField] ItemStatBonus[] bonuses = Array.Empty<ItemStatBonus>();
    [SerializeField] GameObject equippedPrefab;

    public string Id => string.IsNullOrWhiteSpace(id) ? name : id.Trim();
    public string DisplayName => string.IsNullOrEmpty(displayName) ? name : displayName;
    public Sprite Icon => icon;
    public string Description => description;
    public float Weight => Mathf.Max(0f, weight);
    public ItemCategory Category => category;
    public EquipSlotMask Slots => slots;
    public bool TwoHanded => twoHanded;
    public float MaxDurability => Mathf.Max(0f, maxDurability);
    public ItemStatBonus[] Bonuses => bonuses;
    public GameObject EquippedPrefab => equippedPrefab;

    public int MaxStack => MaxDurability > 0f ? 1 : Mathf.Max(1, maxStack);

    public Vector2Int GridSize
    {
        get
        {
            int x = Mathf.Max(1, gridSize.x);
            int y = Mathf.Max(1, gridSize.y);
            return new Vector2Int(x, y);
        }
    }

    public bool HasTag(string tag)
    {
        if (string.IsNullOrEmpty(tag) || tags == null)
            return false;

        for (int i = 0; i < tags.Length; i++)
        {
            if (string.Equals(tags[i], tag, StringComparison.OrdinalIgnoreCase))
                return true;
        }

        return false;
    }

    void OnValidate()
    {
        if (maxStack < 1)
            maxStack = 1;
        if (weight < 0f)
            weight = 0f;
        if (maxDurability < 0f)
            maxDurability = 0f;
        if (maxDurability > 0f)
            maxStack = 1;
        if (gridSize.x < 1)
            gridSize.x = 1;
        if (gridSize.y < 1)
            gridSize.y = 1;
        if (twoHanded)
            slots |= EquipSlotMask.MainHand;
        if (!string.IsNullOrWhiteSpace(id))
            id = id.Trim();
    }
}
```

## Stacks

`ItemInstance` is one stored stack. Fungible items leave `Id` empty and merge up to `MaxStack`. A durability item gets an id, a durability value, and a count of 1, and it never merges, including at full durability. `Split` only works on a fungible stack, and only for a count strictly between the ends. Moving the whole stack is `TryRemoveInstance`, not a split.

`ItemStack` is the value passed through the interface. With an instance, the definition and count come from that instance. Without one, the inventory creates fungible stacks. `TryRead` is the null check the bags share.

```csharp
using System;
using UnityEngine;

/// <summary>
/// One stack in a bag. Fungible stacks have an empty id.
/// Durability stacks have an id and a count of 1.
/// </summary>
[Serializable]
public sealed class ItemInstance
{
    [SerializeField] string id;
    [SerializeField] ItemDefinition definition;
    [SerializeField] int count = 1;
    [SerializeField] float durability;

    public string Id => id ?? string.Empty;
    public ItemDefinition Definition => definition;
    public int Count => count;
    public float Durability => durability;

    public int Room
    {
        get
        {
            if (definition == null)
                return 0;
            return Mathf.Max(0, definition.MaxStack - count);
        }
    }

    public static ItemInstance Create(ItemDefinition definition, int count)
    {
        if (definition == null || count <= 0)
            return null;

        var instance = new ItemInstance();
        instance.definition = definition;
        if (definition.MaxDurability > 0f)
        {
            instance.count = 1;
            instance.durability = definition.MaxDurability;
            instance.id = Guid.NewGuid().ToString("N");
            return instance;
        }

        int max = definition.MaxStack;
        instance.count = count > max ? max : count;
        instance.durability = 0f;
        instance.id = string.Empty;
        return instance;
    }

    public static ItemInstance Restore(ItemDefinition definition, int count, string instanceId, float durability)
    {
        if (definition == null)
            return null;

        var instance = new ItemInstance();
        instance.definition = definition;
        if (definition.MaxDurability > 0f)
        {
            instance.count = 1;
            instance.durability = Mathf.Clamp(durability, 0f, definition.MaxDurability);
            instance.id = string.IsNullOrEmpty(instanceId) ? Guid.NewGuid().ToString("N") : instanceId;
            return instance;
        }

        instance.count = Mathf.Clamp(count, 1, definition.MaxStack);
        instance.durability = 0f;
        instance.id = string.Empty;
        return instance;
    }

    public bool CanMergeWith(ItemDefinition other)
    {
        if (definition == null || other == null || definition != other)
            return false;
        return definition.MaxDurability <= 0f;
    }

    public bool CanMergeWith(ItemInstance other)
    {
        return other != null && CanMergeWith(other.definition);
    }

    public int Absorb(int amount)
    {
        if (amount <= 0 || definition == null || definition.MaxDurability > 0f)
            return 0;

        int taken = Mathf.Min(amount, Room);
        count += taken;
        return taken;
    }

    public int Reduce(int amount)
    {
        if (amount <= 0)
            return 0;

        int taken = Mathf.Min(amount, count);
        count -= taken;
        return taken;
    }

    public void SetDurability(float value)
    {
        if (definition == null || definition.MaxDurability <= 0f)
            return;
        durability = Mathf.Clamp(value, 0f, definition.MaxDurability);
    }

    public ItemInstance Split(int amount)
    {
        if (definition == null || definition.MaxDurability > 0f)
            return null;
        if (amount <= 0 || amount >= count)
            return null;

        count -= amount;
        return Create(definition, amount);
    }
}

/// <summary>
/// A transfer. When Instance is set, Definition and Count follow it.
/// </summary>
public struct ItemStack
{
    public ItemDefinition Definition;
    public int Count;
    public ItemInstance Instance;

    public ItemStack(ItemDefinition definition, int count)
    {
        Definition = definition;
        Count = count;
        Instance = null;
    }

    public ItemStack(ItemInstance instance)
    {
        Instance = instance;
        Definition = instance != null ? instance.Definition : null;
        Count = instance != null ? instance.Count : 0;
    }

    public bool IsEmpty => Definition == null || Count <= 0;

    public static bool TryRead(ItemStack stack, out ItemDefinition definition, out int count, out ItemInstance instance)
    {
        instance = stack.Instance;
        if (instance != null)
        {
            definition = instance.Definition;
            count = instance.Count;
        }
        else
        {
            definition = stack.Definition;
            count = stack.Count;
        }

        if (definition == null || count <= 0)
        {
            definition = null;
            count = 0;
            instance = null;
            return false;
        }

        return true;
    }
}
```

Merging a stack of 12 into a stack of 15, with max stack 20, moves 5 and leaves a remainder of 7. `TryAdd` returns false when anything is left over. The remainder is that leftover, not the part that fitted. A full merge of a fungible instance drops that instance's count to 0 and does not store it. Do not keep using it.

`TryRemove` deletes a fungible quantity. It is all or nothing: if the bag holds fewer than asked, it removes nothing. It refuses a durability definition. Take those out with `TryRemoveInstance`, which hands the same object back so the durability travels with it.

## Interface

`Changed` is a C# event. It runs immediately, the same shape as the instance events on the [event systems](../../architecture/events.md) page. It does not run for a rejected add. A listener may read the bag. It must not change that same bag from inside the call.

`CanAccept` is the dry run. It does not create stacks and it does not change counts. Equip uses it so a failed move cannot destroy the item.

`Contains` with a count of 0 or less is true. Asking for nothing should not fail a recipe check.

```csharp
using System;

public interface IInventory
{
    event Action Changed;

    int Count(ItemDefinition definition);
    bool Contains(ItemDefinition definition, int count = 1);
    bool CanAccept(ItemStack stack);
    bool TryAdd(ItemStack stack, out ItemStack remainder);
    bool TryRemove(ItemDefinition definition, int count, out ItemStack removed);
    bool ContainsInstance(ItemInstance instance);
    bool TryRemoveInstance(ItemInstance instance);
}
```

## Save records

The record stores the definition id, the count, and, for a durability item, the instance id and the durability. It does not store the `ScriptableObject`. `ItemCatalogue` is the lookup, built from the definitions you assign, keyed by `Id`. Two assets with the same id: the catalogue keeps the first and logs a warning. `FromRecord` returns null when the id is unknown. The caller skips that line. The item is gone until the id is put back. That is quieter than inventing a stand-in.

`OnEnable` drops the cache. Entering Play Mode, and a domain reload, build it again on the next lookup. The catalogue is an asset, so do not write runtime stock into it.

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

[Serializable]
public struct ItemRecord
{
    public string definitionId;
    public int count;
    public string instanceId;
    public float durability;
}

/// <summary>
/// Id to definition. Assign every item the game can load.
/// </summary>
[CreateAssetMenu(fileName = "ItemCatalogue", menuName = "Game/Item Catalogue")]
public class ItemCatalogue : ScriptableObject
{
    [SerializeField] ItemDefinition[] items = Array.Empty<ItemDefinition>();

    Dictionary<string, ItemDefinition> _byId;

    void OnEnable()
    {
        _byId = null;
    }

    public bool TryGet(string id, out ItemDefinition definition)
    {
        Ensure();
        if (string.IsNullOrEmpty(id))
        {
            definition = null;
            return false;
        }

        return _byId.TryGetValue(id, out definition);
    }

    public ItemRecord ToRecord(ItemInstance instance)
    {
        if (instance == null || instance.Definition == null)
            return default;

        return new ItemRecord
        {
            definitionId = instance.Definition.Id,
            count = instance.Count,
            instanceId = instance.Id,
            durability = instance.Durability
        };
    }

    public ItemInstance FromRecord(ItemRecord record)
    {
        if (!TryGet(record.definitionId, out ItemDefinition definition))
            return null;
        return ItemInstance.Restore(definition, record.count, record.instanceId, record.durability);
    }

    void Ensure()
    {
        if (_byId != null)
            return;

        _byId = new Dictionary<string, ItemDefinition>(StringComparer.Ordinal);
        if (items == null)
            return;

        for (int i = 0; i < items.Length; i++)
        {
            ItemDefinition definition = items[i];
            if (definition == null)
                continue;

            string key = definition.Id;
            if (string.IsNullOrEmpty(key))
                continue;
            if (_byId.ContainsKey(key))
            {
                Debug.LogWarning("Two item definitions share the id '" + key + "'. The catalogue keeps the first.", this);
                continue;
            }

            _byId.Add(key, definition);
        }
    }
}
```

A JSON file of `ItemRecord` values is the save. This page does not write the file.

## Setup

1. Create one asset per item: **Assets → Create → Game → Item Definition**. Set **Id** to a stable key. Set **Max Stack**, **Weight**, and **Grid Size**. Put equippable items on a slot mask.
2. Create one **Game → Item Catalogue** and assign every definition the game can spawn or load.
3. Add the bag component from the page you are using. Seed it with starting stacks, or call `TryAdd` from gameplay.
4. A label subscribes to `Changed` and reads the bag. The [list](list.md) page has the small view. Do not build drag and drop here.
5. Copy the stat types from [Health, damage, and stats](../health.md) before using bonuses or encumbrance.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Id | Empty | Save key. Empty uses the asset name. |
| Max Stack | `1` | Fungible cap. Durability forces `1`. |
| Weight | `1` | Mass of one item. `0` is free of the weight cap. |
| Grid Size | `1, 1` | Cells on the grid page. Other bags ignore it. |
| Slots | None | Equipment sockets that may hold it. |
| Two Handed | Off | Main hand only, and the off hand must be free. |
| Max Durability | `0` | `0` means the stack merges. Above `0` it is unique. |

!!! warning "Common pitfalls"

    The definition is an asset. A change in Play Mode is saved into it. Counts, durability, and who is carrying the item do not belong on the definition.

    `TryRemove` will not pull a durability item apart, and it will not remove anything when the bag is short. Check the bool. The out stack is empty on failure.

    `Changed` is synchronous. A listener that calls `TryAdd` on the same bag re-enters the notify. Read in the listener. Mutate after it returns.

    Duplicate ids collide in the catalogue. The first asset wins, and a saved line for the second id will not resolve if you only shipped the first.

    Renaming an asset whose **Id** was left empty changes the key. Old saves miss. Set the id.

    `SetDurability` does not raise `Changed`. The view keeps the old number until something else notifies.

    This is one local bag. It is not replicated, and a second player is a second component, not a second reference to the same object.
