---
engine: Unity
version: 6+
---

# Equipment

Sockets on the body, fed by a [list](list.md). Equip takes an `ItemInstance` out of that list and puts it on a slot. Unequip does the reverse, and fails closed: if the bag cannot take the item, it stays worn. Nothing is destroyed to make a slot change succeed.

A slot accepts the item when the definition's mask includes it. **Two Handed** equips only in main hand, and only when the off hand is empty or the bag can take whatever is there. An off-hand equip fails while a two-handed weapon is in the main hand. It does not take that weapon off for you.

Bonuses become [`StatModifier`](../health.md#stats) values while worn, with this component as the source, and are removed by those references on unequip. The prefab on the definition is a mesh parented to a bone. The gun that fires is still the [weapon holder](../../combat/weapons.md#holder). Do not parent that live weapon as well.

The hotbar that selects those guns is [slots and hotbar](slots.md). Weight, when you use it, has to wrap this same list. Drag and drop is [not this page](../../../roadmap.md#interface).

## Setup

1. Add `Equipment` to the actor. Assign the `ListInventory` as **Bag**.
2. If the bag has a [weight](weight.md) cap, assign that `WeightInventory` as **Weight Limit**. Its inner list must be **Bag**. Returns then pay the mass cost. Leave it empty when mass does not matter.
3. Add a socket entry per bone you have: slot, and the transform to parent the mesh to. A missing bone skips the mesh and still applies stats.
4. The actor needs a [`StatSheet`](../health.md#stats) that binds every stat a piece of gear can change. Assign it.
5. On each item, set **Slots**, **Two Handed**, **Bonuses**, and **Equipped Prefab**.
6. Add `EquipmentLabel` to a uGUI `Text` if the slot names should be on screen.
7. Starting gear is applied in order from `Start`. A two-handed weapon listed while the off hand is already filled will fail unless the bag can take the off-hand item.

## Rules

Replacing a slot returns the old item first. If that return does not fit, the equip does not start. A two-handed equip also returns the off-hand item, and both have to fit together. The check is `CanFitAfterRemoval` on the list, plus `WouldFit` when a weight limit is assigned.

An item that is already worn in another slot moves. It is not copied, and it is not sent through the bag. `Equipped` and `Unequipped` fire for that move. Enabling the component applies stats and the mesh again, and does not fire those events.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Bag | Empty | List the worn item returns to. Required to replace a filled slot. |
| Weight Limit | Empty | Optional mass check. Must wrap **Bag**. |
| Stats | Empty | Sheet that receives bonuses. Empty equips with no modifiers. |
| Sockets | Empty | Slot to bone. The first match wins. |
| Starting | Empty | Definition and slot, applied once from `Start`. |

## Scripts

Each block is its own file. The stat types are on the health page. The list and the weight types are on their pages.

### Equipment

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Worn items. Equip fails closed when the bag cannot take the return.
/// </summary>
[DisallowMultipleComponent]
public class Equipment : MonoBehaviour
{
    [Serializable]
    public struct SocketBinding
    {
        public EquipSlotId slot;
        public Transform bone;
    }

    [Serializable]
    public struct StartingGear
    {
        public EquipSlotId slot;
        public ItemDefinition definition;
    }

    struct AppliedBonus
    {
        public Stat Stat;
        public StatModifier Modifier;
    }

    [SerializeField] ListInventory bag;
    [SerializeField] WeightInventory weightLimit;
    [SerializeField] StatSheet sheet;
    [SerializeField] SocketBinding[] sockets = Array.Empty<SocketBinding>();
    [SerializeField] StartingGear[] starting = Array.Empty<StartingGear>();

    readonly ItemInstance[] _equipped = new ItemInstance[6];
    readonly List<AppliedBonus>[] _applied = new List<AppliedBonus>[6];
    readonly GameObject[] _visuals = new GameObject[6];
    readonly bool[] _effectsOn = new bool[6];
    bool _seeded;

    public event Action<EquipSlotId, ItemInstance> Equipped;
    public event Action<EquipSlotId, ItemInstance> Unequipped;

    void Awake()
    {
        for (int i = 0; i < _applied.Length; i++)
            _applied[i] = new List<AppliedBonus>();
    }

    void OnEnable()
    {
        for (int i = 0; i < _equipped.Length; i++)
        {
            if (_equipped[i] != null)
                ApplyEffects(i);
        }
    }

    void Start()
    {
        if (weightLimit != null && !weightLimit.Wraps(bag))
            Debug.LogWarning("Equipment weight limit should wrap the same list as the bag.", this);

        if (_seeded || starting == null)
            return;
        _seeded = true;

        for (int i = 0; i < starting.Length; i++)
        {
            if (starting[i].definition == null)
                continue;
            ItemInstance instance = ItemInstance.Create(starting[i].definition, 1);
            if (!TryEquip(instance, starting[i].slot))
                Debug.LogWarning("Starting gear did not equip: " + starting[i].definition.DisplayName, this);
        }
    }

    void OnDisable()
    {
        for (int i = 0; i < _equipped.Length; i++)
            ClearEffects(i);
    }

    public ItemInstance Get(EquipSlotId slot)
    {
        int index = (int)slot;
        if (!Valid(index))
            return null;
        return _equipped[index];
    }

    public static EquipSlotMask MaskOf(EquipSlotId slot)
    {
        switch (slot)
        {
            case EquipSlotId.Head:
                return EquipSlotMask.Head;
            case EquipSlotId.Chest:
                return EquipSlotMask.Chest;
            case EquipSlotId.Legs:
                return EquipSlotMask.Legs;
            case EquipSlotId.Feet:
                return EquipSlotMask.Feet;
            case EquipSlotId.MainHand:
                return EquipSlotMask.MainHand;
            case EquipSlotId.OffHand:
                return EquipSlotMask.OffHand;
            default:
                return EquipSlotMask.None;
        }
    }

    public bool Accepts(ItemDefinition definition, EquipSlotId slot)
    {
        if (definition == null)
            return false;
        if (definition.TwoHanded)
            return slot == EquipSlotId.MainHand;
        if ((definition.Slots & MaskOf(slot)) == 0)
            return false;
        if (slot != EquipSlotId.OffHand)
            return true;

        ItemInstance main = _equipped[(int)EquipSlotId.MainHand];
        return main == null || main.Definition == null || !main.Definition.TwoHanded;
    }

    public bool TryEquip(ItemInstance item, EquipSlotId slot)
    {
        if (item == null || item.Definition == null)
            return false;

        int index = (int)slot;
        if (!Valid(index))
            return false;
        if (_equipped[index] == item)
            return true;
        if (!Accepts(item.Definition, slot))
            return false;

        ItemInstance previous = _equipped[index];
        ItemInstance off = null;
        if (item.Definition.TwoHanded)
        {
            ItemInstance offHand = _equipped[(int)EquipSlotId.OffHand];
            if (offHand != null && offHand != item)
                off = offHand;
        }

        if (!CanReturn(item, previous, off))
            return false;
        if (bag != null && bag.ContainsInstance(item) && !bag.TryRemoveInstance(item))
            return false;

        int fromSlot = IndexOf(item);
        if (fromSlot >= 0)
        {
            ClearEffects(fromSlot);
            _equipped[fromSlot] = null;
        }

        if (previous != null)
        {
            ClearEffects(index);
            _equipped[index] = null;
        }

        if (off != null)
        {
            ClearEffects((int)EquipSlotId.OffHand);
            _equipped[(int)EquipSlotId.OffHand] = null;
        }

        _equipped[index] = item;
        ApplyEffects(index);

        if (!Store(previous) || !Store(off))
            Debug.LogError("Equipped an item but the bag rejected what it replaced.", this);

        if (fromSlot >= 0)
            Unequipped?.Invoke((EquipSlotId)fromSlot, item);
        if (previous != null)
            Unequipped?.Invoke(slot, previous);
        if (off != null)
            Unequipped?.Invoke(EquipSlotId.OffHand, off);
        Equipped?.Invoke(slot, item);
        return true;
    }

    public bool TryUnequip(EquipSlotId slot)
    {
        int index = (int)slot;
        if (!Valid(index))
            return false;

        ItemInstance item = _equipped[index];
        if (item == null)
            return false;
        if (!CanReturn(null, item, null))
            return false;

        ClearEffects(index);
        _equipped[index] = null;
        if (!Store(item))
        {
            _equipped[index] = item;
            ApplyEffects(index);
            Debug.LogWarning("Unequip could not return the item to the bag.", this);
            return false;
        }

        Unequipped?.Invoke(slot, item);
        return true;
    }

    bool CanReturn(ItemInstance leaving, ItemInstance first, ItemInstance second)
    {
        if (first == null && second == null)
            return true;
        if (bag == null || !bag.CanFitAfterRemoval(leaving, first, second))
            return false;
        if (weightLimit != null && !weightLimit.WouldFit(leaving, first, second))
            return false;
        return true;
    }

    bool Store(ItemInstance item)
    {
        if (item == null)
            return true;

        IInventory destination = weightLimit != null ? (IInventory)weightLimit : bag;
        if (destination == null)
            return false;

        ItemStack remainder;
        return destination.TryAdd(new ItemStack(item), out remainder) && remainder.IsEmpty;
    }

    int IndexOf(ItemInstance item)
    {
        for (int i = 0; i < _equipped.Length; i++)
        {
            if (_equipped[i] == item)
                return i;
        }

        return -1;
    }

    void ApplyEffects(int index)
    {
        if (!isActiveAndEnabled || _effectsOn[index])
            return;

        _effectsOn[index] = true;
        ItemInstance item = _equipped[index];
        if (item == null || item.Definition == null)
            return;

        if (_applied[index] == null)
            _applied[index] = new List<AppliedBonus>();

        ItemStatBonus[] bonuses = item.Definition.Bonuses;
        if (sheet != null && bonuses != null)
        {
            for (int i = 0; i < bonuses.Length; i++)
            {
                if (bonuses[i].stat == null || !sheet.TryGet(bonuses[i].stat, out Stat stat))
                    continue;

                var modifier = new StatModifier(bonuses[i].value, bonuses[i].operation, this);
                stat.Add(modifier);
                _applied[index].Add(new AppliedBonus { Stat = stat, Modifier = modifier });
            }
        }

        GameObject prefab = item.Definition.EquippedPrefab;
        Transform bone = BoneFor((EquipSlotId)index);
        if (prefab == null || bone == null)
            return;

        GameObject visual = Instantiate(prefab, bone, false);
        visual.transform.localPosition = Vector3.zero;
        visual.transform.localRotation = Quaternion.identity;
        _visuals[index] = visual;
    }

    void ClearEffects(int index)
    {
        List<AppliedBonus> applied = _applied[index];
        if (applied != null)
        {
            for (int i = 0; i < applied.Count; i++)
            {
                if (applied[i].Stat != null)
                    applied[i].Stat.Remove(applied[i].Modifier);
            }

            applied.Clear();
        }

        if (_visuals[index] != null)
        {
            Destroy(_visuals[index]);
            _visuals[index] = null;
        }

        _effectsOn[index] = false;
    }

    Transform BoneFor(EquipSlotId slot)
    {
        if (sockets == null)
            return null;

        for (int i = 0; i < sockets.Length; i++)
        {
            if (sockets[i].slot == slot)
                return sockets[i].bone;
        }

        return null;
    }

    static bool Valid(int index)
    {
        return index >= 0 && index < 6;
    }
}
```

### Label

```csharp
using System.Text;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// One line per socket. Rebuilds when gear changes.
/// </summary>
[DisallowMultipleComponent]
public class EquipmentLabel : MonoBehaviour
{
    [SerializeField] Equipment equipment;
    [SerializeField] Text label;

    void OnEnable()
    {
        if (equipment != null)
        {
            equipment.Equipped += OnChanged;
            equipment.Unequipped += OnChanged;
        }

        Refresh();
    }

    void OnDisable()
    {
        if (equipment != null)
        {
            equipment.Equipped -= OnChanged;
            equipment.Unequipped -= OnChanged;
        }
    }

    void OnChanged(EquipSlotId slot, ItemInstance item)
    {
        Refresh();
    }

    void Refresh()
    {
        if (label == null)
            return;
        if (equipment == null)
        {
            label.text = string.Empty;
            return;
        }

        var builder = new StringBuilder();
        for (int i = 0; i < 6; i++)
        {
            EquipSlotId slot = (EquipSlotId)i;
            ItemInstance item = equipment.Get(slot);
            if (builder.Length > 0)
                builder.Append('\n');
            builder.Append(slot);
            builder.Append("  ");
            if (item != null && item.Definition != null)
                builder.Append(item.Definition.DisplayName);
            else
                builder.Append("Empty");
        }

        label.text = builder.ToString();
    }
}
```

!!! warning "Common pitfalls"

    Unequip does not drop the item on the ground. If the bag is full, the item stays in the slot. Check the bool before you play a sheath animation.

    A two-handed weapon will not push an off-hand item out unless that item fits in the bag. Both returns are checked together. One free row is not enough for a sword and a shield.

    Equipping the off hand fails while main hand is two-handed. Unequip the weapon first.

    Modifiers have no setters. The slot stores the references it added and removes those. A second `TryEquip` of the same instance in the same slot returns immediately and does not stack the bonus.

    A stat missing from the sheet is skipped. The item still equips. The bonus does nothing until the sheet has that definition.

    The socket prefab is cosmetic. [`WeaponHolder`](../../combat/weapons.md#holder) is what fires. Parenting the holder's weapon object as the prefab as well leaves two meshes, and disabling the holder weapon hides the one you just attached if they are the same object.

    A missing bone skips the visual and still applies stats. `Instantiate` is parented in local space, then the local position and rotation are zeroed. The prefab's scale is left alone.

    `OnDisable` withdraws modifiers and destroys the visual. The item stays in the slot. `OnEnable` applies them again and does not raise `Equipped`. A listener that grants a quest on `Equipped` will not grant it twice because the component toggled.

    The weight limit has to wrap **Bag**. A second list will take the returned item away from the bag you think is the backpack.

    Do not `Destroy` the character inside `Equipped`. The other listeners on that call have not run yet.
