---
engine: Unity
version: 6+
---

# List inventory

An ordered list of stacks. `TryAdd` merges into an existing fungible stack, then opens a new row while the stack count is under **Capacity**. Sorting is by category, then display name. Filtering returns a new list and does not change the bag.

The item types and `IInventory` are on the [overview](index.md). Copy those first. A mass cap in front of this list is [weight](weight.md). Worn gear moves through this list from [equipment](equipment.md). The view at the bottom is the binding. Drag and drop stays on the [roadmap](../../../roadmap.md#interface).

## Setup

1. On the actor, add `ListInventory`. Set **Capacity** to the number of stacks, not the number of arrows.
2. Optionally fill **Starting**. Each entry is a definition and a count. `Start` adds them once. Anything that does not fit is dropped, with a warning.
3. Add `InventoryListView` to a uGUI `Text`. Assign the list and the label. The project needs `com.unity.ugui`.
4. Call `SortByCategory` from a button. Call `Filter` when the UI wants one category. Do not sort from inside `Changed`.

## Rules

Capacity counts rows. A stack of 20 coins is one row. Durability items take one row each and do not merge. `TryRemove` walks from the end, so the last matching stack shrinks first, and a row at count 0 is deleted. Holes do not appear, because this is a list, not a slot array.

`CanFitAfterRemoval` is the check [equipment](equipment.md) uses before it commits. It pretends `leaving` is already out of the bag, then asks whether `first` and `second` would fit. It does not change the list.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Capacity | `20` | Maximum stacks. At least 1. |
| Starting | Empty | Applied once from `Start`. Overflow is not kept. |

## Scripts

Each block is its own file.

### List

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Ordered stacks. Capacity is the number of rows.
/// </summary>
[DisallowMultipleComponent]
public class ListInventory : MonoBehaviour, IInventory
{
    [Serializable]
    public struct StartingStack
    {
        public ItemDefinition definition;
        public int count;
    }

    [SerializeField] int capacity = 20;
    [SerializeField] StartingStack[] starting = Array.Empty<StartingStack>();

    readonly List<ItemInstance> _items = new List<ItemInstance>();
    bool _seeded;

    public event Action Changed;

    public int Capacity => capacity;
    public IReadOnlyList<ItemInstance> Stacks => _items;

    void Start()
    {
        if (_seeded || starting == null)
            return;
        _seeded = true;

        for (int i = 0; i < starting.Length; i++)
        {
            ItemDefinition definition = starting[i].definition;
            if (definition == null || starting[i].count <= 0)
                continue;

            ItemStack remainder;
            bool fitted = TryAdd(new ItemStack(definition, starting[i].count), out remainder);
            if (!fitted)
                Debug.LogWarning("Starting stack did not fit: " + definition.DisplayName, this);
        }
    }

    public int Count(ItemDefinition definition)
    {
        if (definition == null)
            return 0;

        int total = 0;
        for (int i = 0; i < _items.Count; i++)
        {
            if (_items[i].Definition == definition)
                total += _items[i].Count;
        }

        return total;
    }

    public bool Contains(ItemDefinition definition, int count = 1)
    {
        if (count <= 0)
            return true;
        return Count(definition) >= count;
    }

    public bool ContainsInstance(ItemInstance instance)
    {
        return instance != null && _items.Contains(instance);
    }

    public bool CanAccept(ItemStack stack)
    {
        if (!ItemStack.TryRead(stack, out ItemDefinition definition, out int count, out ItemInstance instance))
            return false;
        if (instance != null && _items.Contains(instance))
            return true;
        if (instance != null)
            return InstanceFits(instance);
        if (definition.MaxDurability > 0f)
            return capacity - _items.Count >= count;
        return RoomFor(definition) >= count;
    }

    public bool TryAdd(ItemStack stack, out ItemStack remainder)
    {
        remainder = default;
        if (!ItemStack.TryRead(stack, out ItemDefinition definition, out int count, out ItemInstance instance))
        {
            remainder = stack;
            return false;
        }

        if (instance != null && _items.Contains(instance))
            return true;
        if (definition.MaxDurability > 0f)
            return AddDurable(definition, count, instance, out remainder);
        return AddFungible(definition, count, instance, out remainder);
    }

    public bool TryRemove(ItemDefinition definition, int count, out ItemStack removed)
    {
        removed = default;
        if (definition == null || count <= 0 || definition.MaxDurability > 0f)
            return false;
        if (Count(definition) < count)
            return false;

        int left = count;
        for (int i = _items.Count - 1; i >= 0 && left > 0; i--)
        {
            ItemInstance item = _items[i];
            if (item.Definition != definition)
                continue;
            left -= item.Reduce(left);
            if (item.Count <= 0)
                _items.RemoveAt(i);
        }

        removed = new ItemStack(definition, count);
        Changed?.Invoke();
        return true;
    }

    public bool TryRemoveInstance(ItemInstance instance)
    {
        if (instance == null || !_items.Remove(instance))
            return false;
        Changed?.Invoke();
        return true;
    }

    public void SortByCategory()
    {
        _items.Sort(CompareCategory);
        Changed?.Invoke();
    }

    public List<ItemInstance> Filter(ItemCategory category)
    {
        var result = new List<ItemInstance>();
        for (int i = 0; i < _items.Count; i++)
        {
            ItemInstance item = _items[i];
            if (item.Definition != null && item.Definition.Category == category)
                result.Add(item);
        }

        return result;
    }

    public List<ItemInstance> FilterTag(string tag)
    {
        var result = new List<ItemInstance>();
        for (int i = 0; i < _items.Count; i++)
        {
            ItemInstance item = _items[i];
            if (item.Definition != null && item.Definition.HasTag(tag))
                result.Add(item);
        }

        return result;
    }

    /// <summary>
    /// True if first and second would fit after leaving was removed.
    /// Does not change the list. A null argument is ignored.
    /// </summary>
    public bool CanFitAfterRemoval(ItemInstance leaving, ItemInstance first, ItemInstance second)
    {
        int empty = capacity - _items.Count;
        if (leaving != null && _items.Contains(leaving))
            empty++;

        var reserved = new Dictionary<ItemInstance, int>();
        return FitsIncoming(first, leaving, ref empty, reserved)
            && FitsIncoming(second, leaving, ref empty, reserved);
    }

    bool AddFungible(ItemDefinition definition, int count, ItemInstance instance, out ItemStack remainder)
    {
        remainder = default;
        int left = count;
        bool changed = false;

        for (int i = 0; i < _items.Count && left > 0; i++)
        {
            ItemInstance other = _items[i];
            if (other == instance || !other.CanMergeWith(definition))
                continue;
            int taken = other.Absorb(left);
            if (taken <= 0)
                continue;
            if (instance != null)
                instance.Reduce(taken);
            left -= taken;
            changed = true;
        }

        if (left > 0 && instance != null)
        {
            if (_items.Count < capacity && instance.Count > 0 && instance.Count <= definition.MaxStack)
            {
                _items.Add(instance);
                left = 0;
                changed = true;
            }
        }
        else if (instance == null)
        {
            while (left > 0 && _items.Count < capacity)
            {
                ItemInstance created = ItemInstance.Create(definition, left);
                if (created == null)
                    break;
                _items.Add(created);
                left -= created.Count;
                changed = true;
            }
        }

        if (changed)
            Changed?.Invoke();
        if (left <= 0)
            return true;

        remainder = instance != null && instance.Count > 0
            ? new ItemStack(instance)
            : new ItemStack(definition, left);
        return false;
    }

    bool AddDurable(ItemDefinition definition, int count, ItemInstance instance, out ItemStack remainder)
    {
        remainder = default;
        if (instance != null)
        {
            if (_items.Count >= capacity)
            {
                remainder = new ItemStack(instance);
                return false;
            }

            _items.Add(instance);
            Changed?.Invoke();
            return true;
        }

        int placed = 0;
        while (placed < count && _items.Count < capacity)
        {
            ItemInstance created = ItemInstance.Create(definition, 1);
            if (created == null)
                break;
            _items.Add(created);
            placed++;
        }

        if (placed > 0)
            Changed?.Invoke();
        if (placed == count)
            return true;

        remainder = new ItemStack(definition, count - placed);
        return false;
    }

    bool InstanceFits(ItemInstance instance)
    {
        int left = instance.Count;
        if (instance.Definition.MaxDurability <= 0f)
            left -= Mathf.Min(left, MergeRoom(instance.Definition, instance));
        if (left <= 0)
            return true;
        return _items.Count < capacity && left <= instance.Definition.MaxStack;
    }

    int RoomFor(ItemDefinition definition)
    {
        int empty = capacity - _items.Count;
        return MergeRoom(definition, null) + empty * definition.MaxStack;
    }

    int MergeRoom(ItemDefinition definition, ItemInstance ignore)
    {
        if (definition == null || definition.MaxDurability > 0f)
            return 0;

        int room = 0;
        for (int i = 0; i < _items.Count; i++)
        {
            ItemInstance other = _items[i];
            if (other == ignore || !other.CanMergeWith(definition))
                continue;
            room += other.Room;
        }

        return room;
    }

    bool FitsIncoming(ItemInstance incoming, ItemInstance leaving, ref int empty, Dictionary<ItemInstance, int> reserved)
    {
        if (incoming == null || incoming == leaving)
            return true;
        if (incoming.Definition == null)
            return false;

        int left = incoming.Count;
        if (incoming.Definition.MaxDurability > 0f)
        {
            if (left > 1 || empty < 1)
                return false;
            empty--;
            return true;
        }

        for (int i = 0; i < _items.Count && left > 0; i++)
        {
            ItemInstance other = _items[i];
            if (other == leaving || other == incoming || !other.CanMergeWith(incoming))
                continue;

            int already = 0;
            reserved.TryGetValue(other, out already);
            int room = other.Room - already;
            if (room <= 0)
                continue;

            int taken = left < room ? left : room;
            reserved[other] = already + taken;
            left -= taken;
        }

        if (left <= 0)
            return true;

        int max = incoming.Definition.MaxStack;
        int stacks = (left + max - 1) / max;
        if (stacks > empty)
            return false;
        empty -= stacks;
        return true;
    }

    static int CompareCategory(ItemInstance a, ItemInstance b)
    {
        int aCat = a != null && a.Definition != null ? (int)a.Definition.Category : int.MaxValue;
        int bCat = b != null && b.Definition != null ? (int)b.Definition.Category : int.MaxValue;
        int category = aCat.CompareTo(bCat);
        if (category != 0)
            return category;

        string aName = a != null && a.Definition != null ? a.Definition.DisplayName : string.Empty;
        string bName = b != null && b.Definition != null ? b.Definition.DisplayName : string.Empty;
        return string.Compare(aName, bName, StringComparison.OrdinalIgnoreCase);
    }

    void OnValidate()
    {
        if (capacity < 1)
            capacity = 1;
    }
}
```

### View

`Text` is the uGUI text component. The label rebuilds when the bag changes. It does not poll.

```csharp
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// One line per stack. Subscribe and read. No drag and drop.
/// </summary>
[DisallowMultipleComponent]
public class InventoryListView : MonoBehaviour
{
    [SerializeField] ListInventory inventory;
    [SerializeField] Text label;

    void OnEnable()
    {
        if (inventory != null)
            inventory.Changed += Refresh;
        Refresh();
    }

    void OnDisable()
    {
        if (inventory != null)
            inventory.Changed -= Refresh;
    }

    void Refresh()
    {
        if (label == null)
            return;
        if (inventory == null)
        {
            label.text = string.Empty;
            return;
        }

        var builder = new StringBuilder();
        IReadOnlyList<ItemInstance> stacks = inventory.Stacks;
        for (int i = 0; i < stacks.Count; i++)
        {
            ItemInstance item = stacks[i];
            if (item == null || item.Definition == null)
                continue;
            if (builder.Length > 0)
                builder.Append('\n');
            builder.Append(item.Definition.DisplayName);
            builder.Append("  ");
            builder.Append(item.Count.ToString(CultureInfo.InvariantCulture));
        }

        label.text = builder.ToString();
    }
}
```

!!! warning "Common pitfalls"

    **Capacity** is rows. Raising **Max Stack** on the definition does not give the list more rows, and a full row refuses the overflow instead of spilling into a hidden stack.

    `SortByCategory` raises `Changed`. A view that sorts inside that handler sorts again, forever. Sort from the button.

    `Filter` and `FilterTag` return a new list. Removing from that list does not remove from the bag.

    `Start` seeds once per object lifetime. Disabling and enabling the component does not clear the bag and does not seed again. With **Reload Domain** and **Reload Scene** both off, `Start` does not run on the next enter-play either, so picked-up items remain. A script compile during Play Mode drops the non-serialised list and does not run `Start` again. The bag is empty until the next play.

    Starting stacks that do not fit are discarded. The warning is the only record.

    `CanFitAfterRemoval` ignores weight. The [weight](weight.md) page has the mass check. Use both when the bag is encumbered.
