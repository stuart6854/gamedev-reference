---
engine: Unity
version: 6+
uses:
  - name: Top-down survival
    text: Hunger, thirst, and fatigue that drain with game time, bleeding that stacks per wound, and an infection that runs its course.
  - name: RPGs
    text: Buffs and debuffs with durations and stacking rules, on top of stat modifiers.
  - name: Life and colony sims
    text: Needs that drain faster with work and set a character's mood through thresholds.
---

# Needs and effects

Two systems that change a character over time. **Needs**, such as hunger, thirst, and fatigue, drain steadily and are refilled by eating, drinking, and sleeping. Crossing a threshold, such as "Hungry" at 50%, applies stat modifiers; reaching zero hurts. **Effects**, such as bleeding, a painkiller, or an infection, last for a duration, tick, stack by a rule, and wear off. Both write [stat modifiers](health.md#stats) and both damage through [health](health.md).

## Shared: a modifier recipe

A definition asset cannot hold a live `StatModifier`, because a modifier needs a source and belongs to one actor. It holds the recipe instead:

```csharp
using System;

[Serializable]
public struct ModifierSpec
{
    public StatDefinition stat;
    public float value;
    public ModifierOperation operation;
}
```

Both systems use the definition asset as the modifier's source. `Stat.RemoveFromSource(definition)` takes off exactly what that need or effect added.

## Needs

```csharp
using System;
using UnityEngine;

[CreateAssetMenu(fileName = "Need", menuName = "Game/Survival/Need")]
public class NeedDefinition : ScriptableObject
{
    [Serializable]
    public struct Threshold
    {
        public string label;
        [Tooltip("Applies while the need is below this fraction of max.")]
        [Range(0f, 1f)] public float below;
        public ModifierSpec[] modifiers;
    }

    public string id;
    [Min(1f)] public float max = 100f;
    [Min(0f)] public float start = 100f;
    [Tooltip("Lost per game hour, before activity multipliers.")]
    [Min(0f)] public float drainPerHour = 4f;
    [Tooltip("Highest first: Peckish 0.75, Hungry 0.5, Starving 0.2.")]
    public Threshold[] thresholds = Array.Empty<Threshold>();
    [Tooltip("Health lost per real second while at zero.")]
    [Min(0f)] public float damageAtZero = 0.5f;
    public DamageType damageType;
}
```

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Drains needs with game time, applies threshold modifiers, and hurts at zero.
/// </summary>
public class Needs : MonoBehaviour
{
    [SerializeField] NeedDefinition[] needs = Array.Empty<NeedDefinition>();
    [SerializeField] StatSheet stats;
    [SerializeField] Health health;
    [Tooltip("Optional. Game time comes from the clock; without one, Game Hours Per Second is used.")]
    [SerializeField] TimeOfDay clock;
    [SerializeField] float gameHoursPerSecond = 1f / 60f;

    class State
    {
        public NeedDefinition definition;
        public float value;
        public int threshold = -1;
        public readonly Dictionary<UnityEngine.Object, float> rates = new Dictionary<UnityEngine.Object, float>();
    }

    readonly List<State> _states = new List<State>();
    float _lastHours;

    public event Action<NeedDefinition, float> Changed;            // need, fraction
    public event Action<NeedDefinition, string> ThresholdChanged;  // need, label or empty

    void Awake()
    {
        foreach (NeedDefinition definition in needs)
        {
            if (definition != null)
                _states.Add(new State { definition = definition, value = Mathf.Min(definition.start, definition.max) });
        }
    }

    void OnEnable()
    {
        _lastHours = clock != null ? clock.Hours : 0f;
        foreach (State state in _states)
            UpdateThreshold(state, force: true);
    }

    void Update()
    {
        float hours;
        if (clock != null)
        {
            // Wraps at midnight. A paused clock drains nothing.
            hours = Mathf.Repeat(clock.Hours - _lastHours, 24f);
            _lastHours = clock.Hours;
        }
        else
        {
            hours = Time.deltaTime * gameHoursPerSecond;
        }

        foreach (State state in _states)
        {
            float multiplier = 1f;
            foreach (float rate in state.rates.Values)
                multiplier *= rate;

            if (hours > 0f)
                Set(state, state.value - state.definition.drainPerHour * multiplier * hours);

            if (state.value <= 0f && state.definition.damageAtZero > 0f && health != null)
            {
                health.ApplyDamage(new DamageInfo
                {
                    Amount = state.definition.damageAtZero * Time.deltaTime,
                    Type = state.definition.damageType,
                    Source = state.definition,
                    Point = transform.position
                });
            }
        }
    }

    public float Fraction(NeedDefinition need) => Find(need) is State s ? s.value / s.definition.max : 0f;

    /// <summary>Eating, drinking, sleeping. Negative amounts drain.</summary>
    public void Restore(NeedDefinition need, float amount)
    {
        if (Find(need) is State state)
            Set(state, state.value + amount);
    }

    /// <summary>Activity multipliers: running doubles thirst, sleeping drains fatigue backwards.</summary>
    public void SetRate(NeedDefinition need, UnityEngine.Object source, float multiplier)
    {
        if (Find(need) is State state)
            state.rates[source] = multiplier;
    }

    public void ClearRate(NeedDefinition need, UnityEngine.Object source)
    {
        if (Find(need) is State state)
            state.rates.Remove(source);
    }

    void Set(State state, float value)
    {
        float clamped = Mathf.Clamp(value, 0f, state.definition.max);
        if (Mathf.Approximately(clamped, state.value))
            return;
        state.value = clamped;
        Changed?.Invoke(state.definition, clamped / state.definition.max);
        UpdateThreshold(state, force: false);
    }

    void UpdateThreshold(State state, bool force)
    {
        float fraction = state.value / state.definition.max;
        int index = -1;
        NeedDefinition.Threshold[] thresholds = state.definition.thresholds;
        for (int i = 0; i < thresholds.Length; i++)
        {
            if (fraction < thresholds[i].below)
                index = i; // the lowest threshold crossed wins
        }
        if (index == state.threshold && !force)
            return;

        state.threshold = index;
        if (stats != null)
        {
            foreach (NeedDefinition.Threshold t in thresholds)
                foreach (ModifierSpec spec in t.modifiers)
                    if (spec.stat != null && stats.TryGet(spec.stat, out Stat stat))
                        stat.RemoveFromSource(state.definition);

            if (index >= 0)
                foreach (ModifierSpec spec in thresholds[index].modifiers)
                    if (spec.stat != null && stats.TryGet(spec.stat, out Stat stat))
                        stat.Add(new StatModifier(spec.value, spec.operation, state.definition));
        }

        ThresholdChanged?.Invoke(state.definition, index >= 0 ? thresholds[index].label : string.Empty);
    }

    State Find(NeedDefinition need)
    {
        foreach (State state in _states)
        {
            if (state.definition == need)
                return state;
        }
        return null;
    }

    // Saving: see below.
    [Serializable] class Saved { public List<string> ids = new List<string>(); public List<float> values = new List<float>(); }

    public string CaptureJson()
    {
        var saved = new Saved();
        foreach (State state in _states)
        {
            saved.ids.Add(state.definition.id);
            saved.values.Add(state.value);
        }
        return JsonUtility.ToJson(saved);
    }

    public void RestoreJson(string json)
    {
        if (string.IsNullOrEmpty(json))
            return;
        Saved saved = JsonUtility.FromJson<Saved>(json);
        for (int i = 0; i < saved.ids.Count && i < saved.values.Count; i++)
        {
            foreach (State state in _states)
            {
                if (state.definition.id == saved.ids[i])
                    Set(state, saved.values[i]);
            }
        }
    }
}
```

- Drain is in **game hours**. With the [day and night](../rendering/day-night.md) clock assigned, needs follow it, including when it is paused or sped up for sleeping.
- Thresholds are checked from highest to lowest; the lowest crossed one applies, so "Starving" replaces "Hungry" instead of adding to it. Put the strongest penalties on the lowest threshold.
- `SetRate` with a source lets several systems change a rate without undoing each other: the movement code sets running, the bed sets sleeping, and each clears its own.

| Need | Drain per hour | Thresholds | At zero |
| --- | --- | --- | --- |
| Hunger | 4 | Hungry 50%: −10% stamina regen. Starving 20%: −25% move speed. | Damage. |
| Thirst | 6 | Thirsty 50%, Parched 20%: slower actions. | Damage, faster. |
| Fatigue | 3, ×2 running, ×−8 sleeping | Tired 40%: slower actions. Exhausted 15%: aim sway. | Falls asleep: the brain or controller forces sleep. |

A food item restores hunger through its use action, a [timed action](timed-actions.md) that calls `Restore` on completion.

## Effects

```csharp
using System;
using UnityEngine;

public enum StackRule
{
    Refresh,     // one instance; applying again resets its time
    Extend,      // one instance; applying again adds its duration
    Intensity,   // one instance; applying again adds a stack, up to Max Stacks, and resets its time
    Independent  // every application is its own instance with its own timer: one per wound
}

[CreateAssetMenu(fileName = "Effect", menuName = "Game/Survival/Effect")]
public class EffectDefinition : ScriptableObject
{
    [Serializable]
    public struct NeedChange
    {
        public NeedDefinition need;
        public float amount;
    }

    public string id;
    public string[] tags = Array.Empty<string>();
    [Tooltip("Real seconds. 0 or less lasts until removed.")]
    public float duration = 10f;
    public StackRule stacking = StackRule.Refresh;
    [Min(1)] public int maxStacks = 5;

    [Header("Every tick, times stacks")]
    [Min(0.05f)] public float tickInterval = 1f;
    [Min(0f)] public float damagePerTick;
    public DamageType damageType;
    public NeedChange[] needChanges = Array.Empty<NeedChange>();

    [Header("While active, times stacks")]
    public ModifierSpec[] modifiers = Array.Empty<ModifierSpec>();

    [Tooltip("Applied when this runs out, not when it is removed. A wearing-off crash, or the end of an infection.")]
    public EffectDefinition onExpire;

    public bool HasTag(string tag) => Array.IndexOf(tags, tag) >= 0;
}
```

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Timed effects on one character: ticking damage and need changes, stacking modifiers, expiry.
/// </summary>
public class Effects : MonoBehaviour
{
    [SerializeField] StatSheet stats;
    [SerializeField] Health health;
    [SerializeField] Needs needs;
    [Tooltip("Every effect that can be saved and loaded.")]
    [SerializeField] EffectDefinition[] known = Array.Empty<EffectDefinition>();

    class Active
    {
        public EffectDefinition definition;
        public float remaining;
        public int stacks = 1;
        public float untilTick;
    }

    readonly List<Active> _active = new List<Active>();

    public event Action<EffectDefinition> Applied;
    public event Action<EffectDefinition> Ended;

    public void Apply(EffectDefinition definition, int stacks = 1)
    {
        if (definition == null || stacks <= 0)
            return;

        Active existing = definition.stacking == StackRule.Independent ? null : _active.Find(a => a.definition == definition);
        if (existing == null)
        {
            _active.Add(new Active
            {
                definition = definition,
                remaining = definition.duration,
                stacks = definition.stacking == StackRule.Intensity ? Mathf.Min(stacks, definition.maxStacks) : 1,
                untilTick = definition.tickInterval
            });
        }
        else
        {
            switch (definition.stacking)
            {
                case StackRule.Refresh:
                    existing.remaining = definition.duration;
                    break;
                case StackRule.Extend:
                    existing.remaining += definition.duration * stacks;
                    break;
                case StackRule.Intensity:
                    existing.stacks = Mathf.Min(definition.maxStacks, existing.stacks + stacks);
                    existing.remaining = definition.duration;
                    break;
            }
        }

        RefreshModifiers(definition);
        Applied?.Invoke(definition);
    }

    public bool Has(string tag) => _active.Exists(a => a.definition.HasTag(tag));

    public int Stacks(EffectDefinition definition)
    {
        int total = 0;
        foreach (Active a in _active)
        {
            if (a.definition == definition)
                total += a.stacks;
        }
        return total;
    }

    /// <summary>Cures: a bandage removes "Bleeding", an antibiotic "Infection". Does not fire On Expire.</summary>
    public int RemoveTag(string tag) => RemoveWhere(a => a.definition.HasTag(tag));

    public int Remove(EffectDefinition definition) => RemoveWhere(a => a.definition == definition);

    void Update()
    {
        float dt = Time.deltaTime;
        for (int i = _active.Count - 1; i >= 0; i--)
        {
            Active a = _active[i];
            EffectDefinition d = a.definition;

            a.untilTick -= dt;
            while (a.untilTick <= 0f)
            {
                a.untilTick += d.tickInterval;
                Tick(a);
            }

            if (d.duration > 0f)
            {
                a.remaining -= dt;
                if (a.remaining <= 0f)
                {
                    _active.RemoveAt(i);
                    RefreshModifiers(d);
                    Ended?.Invoke(d);
                    if (d.onExpire != null)
                        Apply(d.onExpire);
                }
            }
        }
    }

    void Tick(Active a)
    {
        EffectDefinition d = a.definition;
        if (d.damagePerTick > 0f && health != null)
        {
            health.ApplyDamage(new DamageInfo
            {
                Amount = d.damagePerTick * a.stacks,
                Type = d.damageType,
                Source = d,
                Point = transform.position
            });
        }

        if (needs != null)
        {
            foreach (EffectDefinition.NeedChange change in d.needChanges)
                needs.Restore(change.need, change.amount * a.stacks);
        }
    }

    /// <summary>Removes this effect's modifiers and adds them back scaled by its total stacks.</summary>
    void RefreshModifiers(EffectDefinition definition)
    {
        if (stats == null)
            return;
        int total = Stacks(definition);
        foreach (ModifierSpec spec in definition.modifiers)
        {
            if (spec.stat == null || !stats.TryGet(spec.stat, out Stat stat))
                continue;
            stat.RemoveFromSource(definition);
            if (total > 0)
                stat.Add(new StatModifier(spec.value * total, spec.operation, definition));
        }
    }

    int RemoveWhere(Predicate<Active> match)
    {
        var ended = new List<EffectDefinition>();
        for (int i = _active.Count - 1; i >= 0; i--)
        {
            if (!match(_active[i]))
                continue;
            ended.Add(_active[i].definition);
            _active.RemoveAt(i);
        }
        foreach (EffectDefinition d in ended)
        {
            RefreshModifiers(d);
            Ended?.Invoke(d);
        }
        return ended.Count;
    }

    [Serializable] class Saved { public List<string> ids = new List<string>(); public List<float> remaining = new List<float>(); public List<int> stacks = new List<int>(); }

    public string CaptureJson()
    {
        var saved = new Saved();
        foreach (Active a in _active)
        {
            saved.ids.Add(a.definition.id);
            saved.remaining.Add(a.remaining);
            saved.stacks.Add(a.stacks);
        }
        return JsonUtility.ToJson(saved);
    }

    public void RestoreJson(string json)
    {
        RemoveWhere(_ => true);
        if (string.IsNullOrEmpty(json))
            return;
        Saved saved = JsonUtility.FromJson<Saved>(json);
        for (int i = 0; i < saved.ids.Count; i++)
        {
            EffectDefinition definition = Array.Find(known, k => k != null && k.id == saved.ids[i]);
            if (definition == null)
                continue; // removed from the game since the save
            _active.Add(new Active
            {
                definition = definition,
                remaining = i < saved.remaining.Count ? saved.remaining[i] : definition.duration,
                stacks = i < saved.stacks.Count ? Mathf.Max(1, saved.stacks[i]) : 1,
                untilTick = definition.tickInterval
            });
            RefreshModifiers(definition);
        }
    }
}
```

- Modifiers are recomputed from the total stacks of that definition, so independent wounds and intensity stacks scale the same way. Flat and additive-percent modifiers scale linearly, which is what stacks usually mean.
- `RemoveTag` is a cure; it does not fire `On Expire`. Running out does. A painkiller that runs out can apply a short "Pain returns" effect; one that is cured does not.
- Damage from effects, like damage from needs, goes through `Health.Damaged`. List those damage types in the [timed action runner](timed-actions.md#runner)'s **Ignored Damage**, or a bleeding character cannot bandage.
- Ticks catch up after a long frame, with the `while` loop, so a hitch does not skip damage.

| Effect | Stacking | Duration | Per tick | Modifiers | On expire |
| --- | --- | --- | --- | --- | --- |
| Bleeding, tag `Bleeding` | Independent: one per wound | Until bandaged | 0.5 damage | −5% move speed per wound | |
| Painkiller | Refresh | 5 minutes | | Cancels pain: +10% aim stability | Pain returns, short |
| Well fed | Refresh | 30 minutes | +0.2 fatigue | +10% stamina regen | |
| Adrenaline | Intensity, max 3 | 20 seconds | | +5% move speed per stack | Exhausted, short |
| Infection, tag `Infection` | Refresh | 3 game days, in seconds | | −20% max stamina | Turned: lethal damage |

A zombie bite applies Bleeding and, on a roll, Infection. An antibiotic, through a timed action, calls `RemoveTag("Infection")` if the game allows a cure at all.

## Saving

Needs and effects belong to the player record, not to a scene object. Add two strings to `PlayerRecord` on the [save system](saving/save-system.md#data) page and fill them in `PlayerSave`:

```csharp
// In PlayerRecord:
public string needs;
public string effects;

// In PlayerSave.Capture:
record.needs = needs != null ? needs.CaptureJson() : null;
record.effects = effects != null ? effects.CaptureJson() : null;

// In PlayerSave.Restore:
needs?.RestoreJson(record.needs);
effects?.RestoreJson(record.effects);
```

For NPCs with needs, implement [`ISaveState`](saving/world-state.md#ids-and-records) on a small component that forwards to the same two methods.

!!! warning "Common pitfalls"

    Thresholds that each add their modifiers without removing the last stack "Hungry" and "Starving" together. Remove by source, then add the current one.

    Draining by real time makes needs ignore the game clock. Sleeping eight game hours in thirty real seconds should cost eight hours of hunger.

    Damage over time cancelling every timed action, because it arrives as damage. Ignore its damage types in the runner.

    An effect stored as a reference to its asset in the save file. Save the id and look it up in **Known** on load.

    A cure that fires `On Expire` turns "cured the infection" into "turned into a zombie". Removal and expiry are different.
