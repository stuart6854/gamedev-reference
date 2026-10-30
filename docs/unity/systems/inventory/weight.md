---
engine: Unity
version: 6+
uses:
  - name: Top-down survival
    text: Carry weight that slows the player when overloaded.
  - name: RPGs
    text: Encumbrance on top of an ordinary bag.
---

# Weight inventory

A mass cap in front of a [list](list.md). `TryAdd` on this component accepts only as many as the remaining weight allows, then forwards that portion to the list. Calls on the list itself skip the cap. **Weight** on the [definition](index.md) is the mass of one item. A stack weighs that times the count. Zero weighs nothing and can still run out of list rows.

Encumbrance writes a `PercentMultiply` modifier onto a Move Speed stat. The modifier order is the one on the [stats](../health.md#modifier-order) page. `-0.15` is ×0.85, not minus 0.15 metres per second. [Character movement](../../mechanics/character-movement.md) does not read that stat. Multiply its walk or run speed by `MoveSpeedScale.Multiplier`, or the body will not slow down.

## Setup

1. Add `ListInventory` and `WeightInventory` to the actor. Assign the list on the weight component. Leave the list's **Starting** empty.
2. Set **Max Weight**. Put starting stacks on the weight component so they pass the cap.
3. Create a **Game → Stat Definition** named Move Speed. On the actor's [`StatSheet`](../health.md#stats), bind it and set the base to the unburdened speed.
4. Add `Encumbrance`. Assign the weight component, the sheet, and the Move Speed definition. Add tiers, for example fraction `0.5` with multiply `-0.15`, and `0.85` with `-0.35`.
5. Add `MoveSpeedScale` and read `Multiplier` where the controller builds horizontal speed.

## Capacity

`Affordable` is `floor(room / unit weight)`. A durability item is never sliced to make the mass fit. If the whole item is heavier than the room, the add is refused and the remainder is the same stack. A fungible stack can split. The inner list may still refuse part of that split when it is out of rows. That part comes back as remainder too.

`WouldFit` is the dry run [equipment](equipment.md) uses when gear returns to a weighted bag. It subtracts `leaving` if that instance is in the list, then adds the mass of the items coming back. It does not change the bag.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Max Weight | `40` | Cap. `0` refuses every item with a positive weight. |
| From Fraction | — | Tier starts when used/max reaches this. `0.5` is half full. |
| Speed Percent Multiply | — | `StatModifier` value. `0` is no change. `-0.15` is ×0.85. |

## Scripts

Each block is its own file. `ListInventory` is the list page.

### Weight

```csharp
using System;
using UnityEngine;

/// <summary>
/// Mass gate in front of a ListInventory. Add through this component.
/// </summary>
[DisallowMultipleComponent]
public class WeightInventory : MonoBehaviour, IInventory
{
    [Serializable]
    public struct StartingStack
    {
        public ItemDefinition definition;
        public int count;
    }

    [SerializeField] ListInventory inner;
    [SerializeField] float maxWeight = 40f;
    [SerializeField] StartingStack[] starting = Array.Empty<StartingStack>();

    bool _seeded;

    public event Action Changed;

    public float MaxWeight => Mathf.Max(0f, maxWeight);
    public ListInventory Inner => inner;

    public float Used
    {
        get
        {
            if (inner == null)
                return 0f;

            float total = 0f;
            var stacks = inner.Stacks;
            for (int i = 0; i < stacks.Count; i++)
            {
                ItemInstance item = stacks[i];
                if (item == null || item.Definition == null)
                    continue;
                total += item.Definition.Weight * item.Count;
            }

            return total;
        }
    }

    public bool Wraps(ListInventory list)
    {
        return inner != null && inner == list;
    }

    void OnEnable()
    {
        if (inner != null)
            inner.Changed += OnInnerChanged;
    }

    void OnDisable()
    {
        if (inner != null)
            inner.Changed -= OnInnerChanged;
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

    public bool WouldFit(ItemInstance leaving, ItemInstance first, ItemInstance second)
    {
        if (inner == null)
            return false;

        float used = Used;
        if (leaving != null && inner.ContainsInstance(leaving) && leaving.Definition != null)
            used -= leaving.Definition.Weight * leaving.Count;
        used += AddedMass(leaving, first);
        used += AddedMass(leaving, second);
        return used <= MaxWeight + 0.0001f;
    }

    public int Count(ItemDefinition definition)
    {
        return inner != null ? inner.Count(definition) : 0;
    }

    public bool Contains(ItemDefinition definition, int count = 1)
    {
        return inner != null && inner.Contains(definition, count);
    }

    public bool ContainsInstance(ItemInstance instance)
    {
        return inner != null && inner.ContainsInstance(instance);
    }

    public bool CanAccept(ItemStack stack)
    {
        if (inner == null)
            return false;
        if (!ItemStack.TryRead(stack, out ItemDefinition definition, out int count, out _))
            return false;
        if (Affordable(definition, count) < count)
            return false;
        return inner.CanAccept(stack);
    }

    public bool TryAdd(ItemStack stack, out ItemStack remainder)
    {
        remainder = stack;
        if (inner == null)
            return false;
        if (!ItemStack.TryRead(stack, out ItemDefinition definition, out int count, out ItemInstance instance))
            return false;

        int allowed = Affordable(definition, count);
        if (allowed <= 0)
            return false;
        if (definition.MaxDurability > 0f && allowed < count)
            return false;
        if (allowed >= count)
            return inner.TryAdd(stack, out remainder);

        if (instance != null)
            return AddSlice(instance, allowed, out remainder);

        ItemStack leftover;
        inner.TryAdd(new ItemStack(definition, allowed), out leftover);
        int unplaced = leftover.IsEmpty ? 0 : leftover.Count;
        int still = count - (allowed - unplaced);
        if (still > 0)
        {
            remainder = new ItemStack(definition, still);
            return false;
        }

        remainder = default;
        return true;
    }

    public bool TryRemove(ItemDefinition definition, int count, out ItemStack removed)
    {
        removed = default;
        if (inner == null)
            return false;
        return inner.TryRemove(definition, count, out removed);
    }

    public bool TryRemoveInstance(ItemInstance instance)
    {
        return inner != null && inner.TryRemoveInstance(instance);
    }

    bool AddSlice(ItemInstance instance, int allowed, out ItemStack remainder)
    {
        remainder = new ItemStack(instance);
        ItemInstance slice = instance.Split(allowed);
        if (slice == null)
            return false;

        if (!inner.CanAccept(new ItemStack(slice)))
        {
            instance.Absorb(slice.Count);
            return false;
        }

        ItemStack innerLeft;
        inner.TryAdd(new ItemStack(slice), out innerLeft);
        if (!innerLeft.IsEmpty)
        {
            int back = innerLeft.Instance != null ? innerLeft.Instance.Count : innerLeft.Count;
            instance.Absorb(back);
        }

        if (instance.Count > 0)
        {
            remainder = new ItemStack(instance);
            return false;
        }

        remainder = default;
        return true;
    }

    int Affordable(ItemDefinition definition, int count)
    {
        if (definition == null || count <= 0)
            return 0;

        float unit = definition.Weight;
        if (unit <= 0f)
            return count;

        float room = MaxWeight - Used;
        if (room <= 0f)
            return 0;

        int byWeight = Mathf.FloorToInt(room / unit + 0.0001f);
        if (byWeight < 0)
            return 0;
        return byWeight > count ? count : byWeight;
    }

    static float AddedMass(ItemInstance leaving, ItemInstance incoming)
    {
        if (incoming == null || incoming == leaving || incoming.Definition == null)
            return 0f;
        return incoming.Definition.Weight * incoming.Count;
    }

    void OnInnerChanged()
    {
        Changed?.Invoke();
    }

    void OnValidate()
    {
        if (maxWeight < 0f)
            maxWeight = 0f;
    }
}
```

### Encumbrance

The source of the modifier is this component. `OnDisable` removes it, so a disabled bag does not leave the penalty on the sheet. Tiers pick the greatest **From Fraction** that the current load has reached.

```csharp
using System;
using UnityEngine;

/// <summary>
/// Writes one PercentMultiply onto Move Speed for the current load.
/// </summary>
[DisallowMultipleComponent]
public class Encumbrance : MonoBehaviour
{
    [Serializable]
    public struct Tier
    {
        [Range(0f, 1f)] public float fromFraction;
        public float speedPercentMultiply;
    }

    [SerializeField] WeightInventory weight;
    [SerializeField] StatSheet sheet;
    [SerializeField] StatDefinition moveSpeed;
    [SerializeField] Tier[] tiers = Array.Empty<Tier>();

    float _applied = float.NaN;

    void OnEnable()
    {
        if (weight != null)
            weight.Changed += Refresh;
        Refresh();
    }

    void OnDisable()
    {
        if (weight != null)
            weight.Changed -= Refresh;
        Apply(0f);
    }

    void Refresh()
    {
        Apply(Pick());
    }

    float Pick()
    {
        if (weight == null || weight.MaxWeight <= 0f || tiers == null)
            return 0f;

        float fraction = weight.Used / weight.MaxWeight;
        float best = float.NegativeInfinity;
        float multiplier = 0f;
        bool found = false;
        for (int i = 0; i < tiers.Length; i++)
        {
            if (fraction + 0.0001f < tiers[i].fromFraction)
                continue;
            if (tiers[i].fromFraction < best)
                continue;
            best = tiers[i].fromFraction;
            multiplier = tiers[i].speedPercentMultiply;
            found = true;
        }

        return found ? multiplier : 0f;
    }

    void Apply(float multiplier)
    {
        if (Mathf.Approximately(_applied, multiplier))
            return;
        if (sheet == null || !sheet.TryGet(moveSpeed, out Stat stat))
            return;

        stat.RemoveFromSource(this);
        _applied = 0f;
        if (Mathf.Approximately(multiplier, 0f))
            return;

        stat.Add(new StatModifier(multiplier, ModifierOperation.PercentMultiply, this));
        _applied = multiplier;
    }
}
```

### Speed scale

This does not move the body. Where character movement computes `walkSpeed` or `runSpeed`, multiply by `Multiplier`. The ratio is `stat.Value / stat.BaseValue`, so a flat bonus on the same stat is included.

```csharp
using UnityEngine;

/// <summary>
/// Current Move Speed divided by its base. Multiply a controller's
/// walk or run speed by this. 1 is unburdened.
/// </summary>
[DisallowMultipleComponent]
public class MoveSpeedScale : MonoBehaviour
{
    [SerializeField] StatSheet sheet;
    [SerializeField] StatDefinition moveSpeed;

    public float Multiplier
    {
        get
        {
            if (sheet == null || !sheet.TryGet(moveSpeed, out Stat stat))
                return 1f;
            if (stat.BaseValue <= 0f)
                return 1f;
            return stat.Value / stat.BaseValue;
        }
    }
}
```

!!! warning "Common pitfalls"

    `ListInventory.TryAdd` does not know about weight. Loot that calls the list fills the bag past the cap, and encumbrance still slows the body because it reads what is actually there.

    Starting stacks on the list also skip the cap. Put them on `WeightInventory`.

    A durability item is one piece. It is not split so that half a sword fits. Zero weight always passes the mass check and can still fail because the list has no row.

    `0.15` and `-0.15` are not the same modifier. A positive percent-multiply speeds the body up. The sign has to be negative to encumber.

    `RemoveFromSource` drops every modifier whose source is this component. Do not use the encumbrance object as the source of a second bonus.

    `Apply` removes, then adds. A listener on `Stat.Changed` sees the unburdened value in between. Read the stat after `Refresh` returns.

    The controller will not slow down until something multiplies by `MoveSpeedScale`. The stat sitting on the sheet is not wired into [character movement](../../mechanics/character-movement.md) by itself.

    `StatSheet.Awake` builds the dictionary before any `OnEnable`. A sheet created later is invisible until encumbrance is disabled and enabled again. The same order is documented on the health page.

    There is no tier below the first **From Fraction**. Under that load the modifier is removed.
