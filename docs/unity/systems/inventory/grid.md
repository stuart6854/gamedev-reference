---
engine: Unity
version: 6+
---

# Grid inventory

A rectangle of cells. Each item occupies `GridSize` on the [definition](index.md), or the swapped size when it is rotated. A stack is still one rectangle. The count is not a shape. `TryAdd` merges fungible stacks, then places the remainder with first-fit: unrotated, then rotated when **Auto Rotate** is on and the sides differ. `TryMove` moves into free cells, or swaps when the destination overlaps exactly one other item and that item fits at the origin just vacated.

Copy the item types and `IInventory` from the [overview](index.md). The list page's [view](list.md#view) is the binding pattern. This page does not draw a drag handle. That UI is [drag and drop](../../../roadmap.md#interface).

## Setup

1. Add `GridInventory`. **Width** and **Height** are cells. A 10 by 6 bag is the sample.
2. Leave **Auto Rotate** on if a 1 by 3 item may lie on its side to fit. Squares ignore rotation.
3. Call `TryPlace` for a player drop at a cell. Call `TryMove` for a move or a swap. Call `TryRotate` to turn an item in place.
4. Seed **Starting** only with what first-fit can pack. Overflow is dropped.

## Placement

An item stores its origin and a rotation flag on the grid, not on the definition, so two copies can face different ways. Cells hold the instance reference. Clearing an item walks its footprint from the stored origin.

First-fit scans rows from the top, columns from the left. It does not backtrack. A later small item will not be pulled forward to fill a hole under a wide one.

A swap removes both items, places the moved item at the destination, and places the other at the old origin with its old rotation. The other item is not centred in the hole. If it does not fit there, both go back and the call returns false. Overlapping two different items fails the same way. The bag does not shuffle the rest of the grid to make room.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Width | `10` | Columns. At least 1. |
| Height | `6` | Rows. At least 1. |
| Auto Rotate | On | First-fit may swap width and height. |
| Starting | Empty | Packed by first-fit from `Start`. |

## Scripts

`CellPlacement` is the origin. `x` grows across, `y` grows down the grid. The class is one file.

### Grid

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Occupancy grid. One instance is one rectangle.
/// </summary>
[DisallowMultipleComponent]
public class GridInventory : MonoBehaviour, IInventory
{
    struct CellPlacement
    {
        public int X;
        public int Y;
        public bool Rotated;
    }

    [Serializable]
    public struct StartingStack
    {
        public ItemDefinition definition;
        public int count;
    }

    [SerializeField] int width = 10;
    [SerializeField] int height = 6;
    [SerializeField] bool autoRotate = true;
    [SerializeField] StartingStack[] starting = Array.Empty<StartingStack>();

    ItemInstance[,] _cells;
    readonly Dictionary<ItemInstance, CellPlacement> _placed = new Dictionary<ItemInstance, CellPlacement>();
    readonly List<ItemInstance> _order = new List<ItemInstance>();
    bool _seeded;

    public event Action Changed;

    public int Width => width;
    public int Height => height;

    void Awake()
    {
        Allocate();
    }

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
            if (!TryAdd(new ItemStack(definition, starting[i].count), out remainder))
                Debug.LogWarning("Starting stack did not fit: " + definition.DisplayName, this);
        }
    }

    public bool TryFindFirstFit(ItemDefinition definition, bool allowRotation, out int x, out int y, out bool rotated)
    {
        Allocate();
        if (FindAt(definition, false, out x, out y))
        {
            rotated = false;
            return true;
        }

        Footprint(definition, false, out int w, out int h);
        if (allowRotation && w != h && FindAt(definition, true, out x, out y))
        {
            rotated = true;
            return true;
        }

        x = 0;
        y = 0;
        rotated = false;
        return false;
    }

    public bool TryPlace(ItemInstance item, int x, int y, bool rotated)
    {
        Allocate();
        if (item == null || item.Definition == null)
            return false;
        if (_placed.ContainsKey(item))
            return TryMove(item, x, y, rotated);
        if (!Fits(item.Definition, x, y, rotated))
            return false;

        _order.Add(item);
        Stamp(item, x, y, rotated);
        Changed?.Invoke();
        return true;
    }

    public bool TryMove(ItemInstance item, int x, int y, bool rotated)
    {
        Allocate();
        if (item == null || !_placed.TryGetValue(item, out CellPlacement old))
            return false;
        if (old.X == x && old.Y == y && old.Rotated == rotated)
            return true;

        ClearCells(item);
        int blockers = CountBlockers(item.Definition, x, y, rotated, out ItemInstance only);
        if (blockers == 0)
        {
            if (Fits(item.Definition, x, y, rotated))
            {
                Stamp(item, x, y, rotated);
                Changed?.Invoke();
                return true;
            }

            Stamp(item, old.X, old.Y, old.Rotated);
            return false;
        }

        if (blockers != 1 || only == null || !_placed.TryGetValue(only, out CellPlacement otherPlace))
        {
            Stamp(item, old.X, old.Y, old.Rotated);
            return false;
        }

        ClearCells(only);
        Footprint(item.Definition, rotated, out int moverW, out int moverH);
        Footprint(only.Definition, otherPlace.Rotated, out int otherW, out int otherH);
        bool separate = !Overlaps(x, y, moverW, moverH, old.X, old.Y, otherW, otherH);
        bool moverFits = separate && Fits(item.Definition, x, y, rotated);
        bool otherFits = separate && Fits(only.Definition, old.X, old.Y, otherPlace.Rotated);
        if (moverFits && otherFits)
        {
            Stamp(item, x, y, rotated);
            Stamp(only, otherPlace.X, otherPlace.Y, otherPlace.Rotated);
            Changed?.Invoke();
            return true;
        }

        Stamp(only, otherPlace.X, otherPlace.Y, otherPlace.Rotated);
        Stamp(item, old.X, old.Y, old.Rotated);
        return false;
    }

    public bool TryRotate(ItemInstance item)
    {
        if (item == null || item.Definition == null)
            return false;
        if (!_placed.TryGetValue(item, out CellPlacement place))
            return false;

        Footprint(item.Definition, false, out int w, out int h);
        if (w == h)
            return true;
        return TryMove(item, place.X, place.Y, !place.Rotated);
    }

    public int Count(ItemDefinition definition)
    {
        if (definition == null)
            return 0;

        int total = 0;
        for (int i = 0; i < _order.Count; i++)
        {
            if (_order[i].Definition == definition)
                total += _order[i].Count;
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
        return instance != null && _placed.ContainsKey(instance);
    }

    public bool CanAccept(ItemStack stack)
    {
        Allocate();
        if (!ItemStack.TryRead(stack, out ItemDefinition definition, out int count, out ItemInstance instance))
            return false;
        if (instance != null && _placed.ContainsKey(instance))
            return true;

        int left = count;
        if (definition.MaxDurability <= 0f)
            left -= Mathf.Min(left, MergeRoom(definition));
        if (left <= 0)
            return true;

        bool[,] busy = new bool[width, height];
        for (int y = 0; y < height; y++)
        {
            for (int x = 0; x < width; x++)
                busy[x, y] = _cells[x, y] != null;
        }

        if (definition.MaxDurability > 0f)
        {
            int needed = instance != null ? 1 : count;
            for (int n = 0; n < needed; n++)
            {
                if (!ScratchFit(busy, definition, out int x, out int y, out bool rotated))
                    return false;
                ScratchFill(busy, definition, x, y, rotated);
            }

            return true;
        }

        if (instance != null)
            return left <= definition.MaxStack && ScratchFit(busy, definition, out _, out _, out _);

        while (left > 0)
        {
            if (!ScratchFit(busy, definition, out int x, out int y, out bool rotated))
                return false;
            ScratchFill(busy, definition, x, y, rotated);
            left -= definition.MaxStack;
        }

        return true;
    }

    public bool TryAdd(ItemStack stack, out ItemStack remainder)
    {
        Allocate();
        remainder = default;
        if (!ItemStack.TryRead(stack, out ItemDefinition definition, out int count, out ItemInstance instance))
        {
            remainder = stack;
            return false;
        }

        if (instance != null && _placed.ContainsKey(instance))
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
        for (int i = _order.Count - 1; i >= 0 && left > 0; i--)
        {
            ItemInstance item = _order[i];
            if (item.Definition != definition)
                continue;
            left -= item.Reduce(left);
            if (item.Count <= 0)
                Unplace(item);
        }

        removed = new ItemStack(definition, count);
        Changed?.Invoke();
        return true;
    }

    public bool TryRemoveInstance(ItemInstance instance)
    {
        if (!ContainsInstance(instance))
            return false;
        Unplace(instance);
        Changed?.Invoke();
        return true;
    }

    bool AddFungible(ItemDefinition definition, int count, ItemInstance instance, out ItemStack remainder)
    {
        remainder = default;
        int left = count;
        bool changed = false;

        for (int i = 0; i < _order.Count && left > 0; i++)
        {
            ItemInstance other = _order[i];
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

        while (left > 0)
        {
            if (instance != null)
            {
                if (instance.Count <= 0 || instance.Count > definition.MaxStack)
                    break;
                if (!TryFindFirstFit(definition, autoRotate, out int x, out int y, out bool rotated))
                    break;
                _order.Add(instance);
                Stamp(instance, x, y, rotated);
                left = 0;
                changed = true;
                break;
            }

            if (!TryFindFirstFit(definition, autoRotate, out int px, out int py, out bool protated))
                break;
            ItemInstance created = ItemInstance.Create(definition, left);
            if (created == null)
                break;
            _order.Add(created);
            Stamp(created, px, py, protated);
            left -= created.Count;
            changed = true;
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
            if (!TryFindFirstFit(definition, autoRotate, out int x, out int y, out bool rotated))
            {
                remainder = new ItemStack(instance);
                return false;
            }

            _order.Add(instance);
            Stamp(instance, x, y, rotated);
            Changed?.Invoke();
            return true;
        }

        int placed = 0;
        while (placed < count)
        {
            if (!TryFindFirstFit(definition, autoRotate, out int x, out int y, out bool rotated))
                break;
            ItemInstance created = ItemInstance.Create(definition, 1);
            if (created == null)
                break;
            _order.Add(created);
            Stamp(created, x, y, rotated);
            placed++;
        }

        if (placed > 0)
            Changed?.Invoke();
        if (placed == count)
            return true;

        remainder = new ItemStack(definition, count - placed);
        return false;
    }

    int MergeRoom(ItemDefinition definition)
    {
        if (definition == null || definition.MaxDurability > 0f)
            return 0;

        int room = 0;
        for (int i = 0; i < _order.Count; i++)
        {
            if (_order[i].CanMergeWith(definition))
                room += _order[i].Room;
        }

        return room;
    }

    void Unplace(ItemInstance item)
    {
        ClearCells(item);
        _order.Remove(item);
    }

    void Stamp(ItemInstance item, int x, int y, bool rotated)
    {
        Footprint(item.Definition, rotated, out int w, out int h);
        for (int yy = y; yy < y + h; yy++)
        {
            for (int xx = x; xx < x + w; xx++)
                _cells[xx, yy] = item;
        }

        _placed[item] = new CellPlacement { X = x, Y = y, Rotated = rotated };
    }

    void ClearCells(ItemInstance item)
    {
        if (!_placed.TryGetValue(item, out CellPlacement place))
            return;

        Footprint(item.Definition, place.Rotated, out int w, out int h);
        for (int yy = place.Y; yy < place.Y + h; yy++)
        {
            for (int xx = place.X; xx < place.X + w; xx++)
            {
                if (_cells[xx, yy] == item)
                    _cells[xx, yy] = null;
            }
        }

        _placed.Remove(item);
    }

    bool Fits(ItemDefinition definition, int x, int y, bool rotated)
    {
        Footprint(definition, rotated, out int w, out int h);
        if (x < 0 || y < 0 || x + w > width || y + h > height)
            return false;

        for (int yy = y; yy < y + h; yy++)
        {
            for (int xx = x; xx < x + w; xx++)
            {
                if (_cells[xx, yy] != null)
                    return false;
            }
        }

        return true;
    }

    bool FindAt(ItemDefinition definition, bool rotated, out int x, out int y)
    {
        Footprint(definition, rotated, out int w, out int h);
        for (int yy = 0; yy <= height - h; yy++)
        {
            for (int xx = 0; xx <= width - w; xx++)
            {
                if (FitsRect(xx, yy, w, h))
                {
                    x = xx;
                    y = yy;
                    return true;
                }
            }
        }

        x = 0;
        y = 0;
        return false;
    }

    bool FitsRect(int x, int y, int w, int h)
    {
        for (int yy = y; yy < y + h; yy++)
        {
            for (int xx = x; xx < x + w; xx++)
            {
                if (_cells[xx, yy] != null)
                    return false;
            }
        }

        return true;
    }

    int CountBlockers(ItemDefinition definition, int x, int y, bool rotated, out ItemInstance only)
    {
        only = null;
        Footprint(definition, rotated, out int w, out int h);
        if (x < 0 || y < 0 || x + w > width || y + h > height)
            return 2;

        for (int yy = y; yy < y + h; yy++)
        {
            for (int xx = x; xx < x + w; xx++)
            {
                ItemInstance occupant = _cells[xx, yy];
                if (occupant == null)
                    continue;
                if (only == null)
                {
                    only = occupant;
                    continue;
                }

                if (occupant != only)
                {
                    only = null;
                    return 2;
                }
            }
        }

        return only == null ? 0 : 1;
    }

    static bool Overlaps(int ax, int ay, int aw, int ah, int bx, int by, int bw, int bh)
    {
        return ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by;
    }

    bool ScratchFit(bool[,] busy, ItemDefinition definition, out int x, out int y, out bool rotated)
    {
        if (ScratchFind(busy, definition, false, out x, out y))
        {
            rotated = false;
            return true;
        }

        Footprint(definition, false, out int w, out int h);
        if (autoRotate && w != h && ScratchFind(busy, definition, true, out x, out y))
        {
            rotated = true;
            return true;
        }

        rotated = false;
        return false;
    }

    bool ScratchFind(bool[,] busy, ItemDefinition definition, bool rotated, out int x, out int y)
    {
        Footprint(definition, rotated, out int w, out int h);
        for (int yy = 0; yy <= height - h; yy++)
        {
            for (int xx = 0; xx <= width - w; xx++)
            {
                if (ScratchFree(busy, xx, yy, w, h))
                {
                    x = xx;
                    y = yy;
                    return true;
                }
            }
        }

        x = 0;
        y = 0;
        return false;
    }

    static bool ScratchFree(bool[,] busy, int x, int y, int w, int h)
    {
        for (int yy = y; yy < y + h; yy++)
        {
            for (int xx = x; xx < x + w; xx++)
            {
                if (busy[xx, yy])
                    return false;
            }
        }

        return true;
    }

    void ScratchFill(bool[,] busy, ItemDefinition definition, int x, int y, bool rotated)
    {
        Footprint(definition, rotated, out int w, out int h);
        for (int yy = y; yy < y + h; yy++)
        {
            for (int xx = x; xx < x + w; xx++)
                busy[xx, yy] = true;
        }
    }

    static void Footprint(ItemDefinition definition, bool rotated, out int w, out int h)
    {
        w = 1;
        h = 1;
        if (definition == null)
            return;

        Vector2Int size = definition.GridSize;
        w = size.x;
        h = size.y;
        if (rotated && w != h)
        {
            int swap = w;
            w = h;
            h = swap;
        }
    }

    void Allocate()
    {
        if (_cells != null)
            return;
        if (width < 1)
            width = 1;
        if (height < 1)
            height = 1;
        _cells = new ItemInstance[width, height];
    }

    void OnValidate()
    {
        if (width < 1)
            width = 1;
        if (height < 1)
            height = 1;
    }
}
```

!!! warning "Common pitfalls"

    First-fit does not repack. A bag can reject a 2 by 2 while the free cells, added up, would hold it. That is the algorithm, not a missing hole check.

    Rotation that would leave the grid is a failed move. The item stays where it was. A square returns true from `TryRotate` and does not toggle a hidden flag.

    The swapped item sits at the old origin. A 1 by 1 leaving a 2 by 3 hole does not jump to the centre of that hole. If the other item is larger than the hole, the swap is refused and both items stay. If the two final rectangles would overlap, the swap is refused as well. Sliding one item into empty cells is not a swap, and that move may cover cells the item just left.

    Do not store the same instance in a list and a grid. `TryAdd` of an instance that is already on this grid returns true and changes nothing.

    `CanAccept` reserves rectangles on a copy. It does not mutate counts. Trust it only if nothing else writes the grid between the check and the add.

    Width and height are read the first time the grid allocates. Changing them later does not resize a grid that already exists. Set the size before play.

    A script compile during Play Mode clears the cells. `Start` does not seed again. The same Enter Play Mode rule as the [list](list.md) applies.
