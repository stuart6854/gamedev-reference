---
engine: Unity
version: 6+
---

# Loot tables

Weighted random drops as assets: an enemy rolls its table on death, and gets item stacks for the [inventory](inventory/index.md). Entries can be an item, another table, or nothing. Nested tables give rarity tiers. Guaranteed entries always drop, and a pity counter guarantees a rare entry after enough misses.

## How a roll works

```text
roll(table):
    emit every guaranteed entry
    repeat between Min Rolls and Max Rolls times:
        pick one entry, with probability weight / total weight
        emit it:
            Item    -> a stack of Min Count to Max Count
            Table   -> roll that table, recursively
            Nothing -> no drop
```

The chance of entry \(i\) on one pick is

\[
P(i) = \frac{w_i}{\sum_j w_j}
\]

so weights need not add up to anything. A **Nothing** entry is the chance of no drop: weights of 3 for a potion and 1 for nothing give a 75% drop.

With **Unique** on, an entry that has been picked is out of the draw for the rest of this roll of the table. Three rolls of a unique table give three different entries.

## Rarity tiers

Make one table per tier and a top table that picks the tier:

| Top table entry | Weight | Chance |
| --- | --- | --- |
| Table: Common | 70 | 70% |
| Table: Rare | 25 | 25% |
| Table: Legendary | 5 | 5% |
| Nothing | 0 | 0% |

Each tier table lists its items, usually at equal weight. The chance of one item is the tier's chance times its share of the tier: a legendary table of four swords gives each sword \(5\% \times \tfrac{1}{4} = 1.25\%\) per pick. Adding a fifth sword does not change the legendary rate, which is the point of tiers.

## Pity

Bad luck streaks are long. At a 5% chance, about one player in 13 goes 50 picks without a hit, because \(0.95^{50} \approx 0.077\). Pity caps the streak.

Set **Pity Entry** to the entry to protect, usually the Legendary tier. The roller counts picks of the table that were not that entry.

- **Hard Pity** \(N\): once \(N\) picks in a row have missed, the next pick is the pity entry.
- **Soft Pity Per Miss** \(s\): the pity entry's weight grows by \(s\) for every miss, so the chance climbs smoothly instead of jumping.

Either resets to zero when the pity entry is picked. The counter lives in the `LootRoller`, not the asset, so it belongs to whoever owns the roller, usually the player. Save it with `Misses` and `SetMisses`, or the streak resets on every load.

## Setup

1. Create item definitions as on the [inventory](inventory/index.md) page.
2. Create a **Loot Table** (`Game/Loot Table`) per tier, then a top table whose entries are those tables. Set **Min Rolls** and **Max Rolls** on the top table, and add any **Guaranteed** entries, such as gold.
3. Put `LootDropper` on an enemy with `Health`, and assign the table. On death it rolls once.
4. To put the loot straight in a bag, assign a component that implements `IInventory` as **Inventory**. Anything that does not fit is passed to `Dropped`. With no inventory, everything is passed to `Dropped`.
5. Subscribe to `Dropped` to spawn pickups or show a loot window. The list is reused: copy what you keep.

For reproducible drops, such as a seeded run or a test, create a `LootRoller` with a seed and assign it to `LootDropper.Roller` before anything dies.

## Scripts

### Loot table

```csharp
using System;
using UnityEngine;

public enum LootKind
{
    Item,
    Table,
    Nothing
}

[Serializable]
public class LootEntry
{
    public LootKind kind = LootKind.Item;
    [Min(0f)] public float weight = 1f;

    [Tooltip("Used when Kind is Item.")]
    public ItemDefinition item;
    [Min(1)] public int minCount = 1;
    [Min(1)] public int maxCount = 1;

    [Tooltip("Used when Kind is Table.")]
    public LootTable table;
}

/// <summary>
/// Weighted entries, guaranteed entries, and an optional pity rule. Rolled by a LootRoller.
/// </summary>
[CreateAssetMenu(menuName = "Game/Loot Table")]
public class LootTable : ScriptableObject
{
    [Tooltip("Always emitted, before the weighted picks.")]
    public LootEntry[] guaranteed = Array.Empty<LootEntry>();

    public LootEntry[] entries = Array.Empty<LootEntry>();

    [Min(0)] public int minRolls = 1;
    [Min(0)] public int maxRolls = 1;

    [Tooltip("An entry can be picked at most once per roll of this table.")]
    public bool unique;

    [Header("Pity")]
    [Tooltip("Index into Entries that pity protects. -1 for none.")]
    public int pityEntry = -1;

    [Tooltip("After this many misses in a row, the next pick is the pity entry. 0 for none.")]
    [Min(0)] public int hardPity;

    [Tooltip("Weight added to the pity entry for each miss in a row.")]
    [Min(0f)] public float softPityPerMiss;

    /// <summary>Chance of entry index on one pick, ignoring pity and Unique.</summary>
    public float Chance(int index)
    {
        float total = 0f;
        for (int i = 0; i < entries.Length; i++)
            total += Mathf.Max(0f, entries[i].weight);
        return total > 0f && index >= 0 && index < entries.Length
            ? Mathf.Max(0f, entries[index].weight) / total
            : 0f;
    }
}
```

### Roller

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Rolls loot tables with its own random generator, and keeps pity counters per table.
/// </summary>
public class LootRoller
{
    const int MaxDepth = 8;

    readonly System.Random _random;
    readonly Dictionary<LootTable, int> _misses = new Dictionary<LootTable, int>();

    public LootRoller() : this(Environment.TickCount) { }

    public LootRoller(int seed)
    {
        _random = new System.Random(seed);
    }

    public int Misses(LootTable table)
    {
        return table != null && _misses.TryGetValue(table, out int misses) ? misses : 0;
    }

    /// <summary>Restores a saved pity counter.</summary>
    public void SetMisses(LootTable table, int misses)
    {
        if (table != null)
            _misses[table] = Mathf.Max(0, misses);
    }

    /// <summary>Appends the drops to results. Does not clear it.</summary>
    public void Roll(LootTable table, List<ItemStack> results)
    {
        Roll(table, results, 0);
    }

    void Roll(LootTable table, List<ItemStack> results, int depth)
    {
        if (table == null)
            return;
        if (depth > MaxDepth)
        {
            Debug.LogWarning("Loot table nesting is deeper than " + MaxDepth + ". Is " + table.name + " inside itself?");
            return;
        }

        for (int i = 0; i < table.guaranteed.Length; i++)
            Emit(table.guaranteed[i], results, depth);

        int rolls = Range(table.minRolls, table.maxRolls);
        bool[] used = table.unique ? new bool[table.entries.Length] : null;

        for (int r = 0; r < rolls; r++)
        {
            int index = Pick(table, used);
            if (index < 0)
                break;

            if (used != null)
                used[index] = true;
            CountPity(table, index);
            Emit(table.entries[index], results, depth);
        }
    }

    int Pick(LootTable table, bool[] used)
    {
        LootEntry[] entries = table.entries;
        bool pity = table.pityEntry >= 0 && table.pityEntry < entries.Length &&
                    (used == null || !used[table.pityEntry]);
        int misses = pity ? Misses(table) : 0;

        if (pity && table.hardPity > 0 && misses >= table.hardPity)
            return table.pityEntry;

        float total = 0f;
        for (int i = 0; i < entries.Length; i++)
            total += Weight(table, i, used, pity, misses);
        if (total <= 0f)
            return -1;

        double roll = _random.NextDouble() * total;
        int last = -1;
        for (int i = 0; i < entries.Length; i++)
        {
            float weight = Weight(table, i, used, pity, misses);
            if (weight <= 0f)
                continue;
            if (roll < weight)
                return i;
            roll -= weight;
            last = i;
        }

        return last; // rounding left the roll just past the end
    }

    static float Weight(LootTable table, int index, bool[] used, bool pity, int misses)
    {
        if (used != null && used[index])
            return 0f;

        float weight = Mathf.Max(0f, table.entries[index].weight);
        if (pity && index == table.pityEntry)
            weight += table.softPityPerMiss * misses;
        return weight;
    }

    void CountPity(LootTable table, int picked)
    {
        if (table.pityEntry < 0)
            return;
        _misses[table] = picked == table.pityEntry ? 0 : Misses(table) + 1;
    }

    void Emit(LootEntry entry, List<ItemStack> results, int depth)
    {
        if (entry == null)
            return;

        switch (entry.kind)
        {
            case LootKind.Table:
                Roll(entry.table, results, depth + 1);
                break;

            case LootKind.Item:
                if (entry.item == null)
                    break;

                int count = Range(entry.minCount, entry.maxCount);
                if (entry.item.MaxDurability > 0f)
                {
                    // Durability items do not stack: one instance each.
                    for (int i = 0; i < count; i++)
                        results.Add(new ItemStack(ItemInstance.Create(entry.item, 1)));
                }
                else
                {
                    results.Add(new ItemStack(entry.item, count));
                }
                break;
        }
    }

    int Range(int min, int max)
    {
        if (max < min)
            max = min;
        return _random.Next(min, max + 1); // upper bound is exclusive
    }
}
```

### Dropper

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Rolls a loot table when this Health dies. Fills an inventory or raises Dropped.
/// </summary>
[RequireComponent(typeof(Health))]
public class LootDropper : MonoBehaviour
{
    [SerializeField] LootTable table;

    [Tooltip("Optional. A component that implements IInventory. What does not fit goes to Dropped.")]
    [SerializeField] MonoBehaviour inventory;

    /// <summary>Loot to spawn or show. The list is reused: copy what you keep.</summary>
    public event Action<List<ItemStack>> Dropped;

    static LootRoller _roller;

    /// <summary>Shared by every dropper, so pity counts across enemies. Replace it to seed or to load.</summary>
    public static LootRoller Roller
    {
        get => _roller ??= new LootRoller();
        set => _roller = value;
    }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        _roller = null;
    }

    readonly List<ItemStack> _loot = new List<ItemStack>();
    readonly List<ItemStack> _left = new List<ItemStack>();
    Health _health;

    void Awake()
    {
        _health = GetComponent<Health>();
    }

    void OnEnable()
    {
        _health.Died += OnDied;
    }

    void OnDisable()
    {
        _health.Died -= OnDied;
    }

    void OnDied()
    {
        _loot.Clear();
        _left.Clear();
        Roller.Roll(table, _loot);

        if (inventory is IInventory bag)
        {
            for (int i = 0; i < _loot.Count; i++)
            {
                if (!bag.TryAdd(_loot[i], out ItemStack remainder) && !remainder.IsEmpty)
                    _left.Add(remainder);
            }
        }
        else
        {
            _left.AddRange(_loot);
        }

        if (_left.Count > 0)
            Dropped?.Invoke(_left);
    }
}
```

## Big tables

The pick above walks every entry, which is \(O(n)\). For tables of a few dozen entries rolled on death, that is nothing. The options are on the [random distributions](../../maths/random.md#weighted-picks) page. For thousands of entries rolled thousands of times, precompute the prefix sums of the weights and binary search them, \(O(\log n)\), or build Walker's alias table once, \(O(1)\) per pick. Both need rebuilding when a weight changes, so neither works with soft pity on that table.

!!! warning "Common pitfalls"

    `System.Random.Next(min, max)` excludes `max`. Without the `+ 1`, a 1-to-3 range never gives 3.

    Two rollers made with the default constructor in the same millisecond get the same seed, `Environment.TickCount`, and produce the same rolls. Share one roller, as `LootDropper.Roller` does.

    A table that contains itself, directly or through another table, recurses until the depth limit. The roller stops at 8 levels and logs a warning.

    Pity counters kept on the `ScriptableObject` would be shared by every player and lost, or worse, saved into the asset in the editor. Keep them in the roller and save them with the player.

    Weights of 0 everywhere make the table pick nothing. A table that should sometimes drop nothing needs a **Nothing** entry with a weight, not all-zero weights.
