---
engine: Unity
version: 6+
---

# Health, damage, and stats

A health pool, a short damage pipeline, and a stat sheet with modifiers. UI and VFX subscribe to the events. They do not read the pool by polling.

Unity has no general combat package, so this page is the plain implementation. Modifiers are on this page. What is not is a clock: a buff that adds a modifier with itself as the source and calls `RemoveFromSource` when it expires. That is [timed buffs and debuffs](../../roadmap.md#game-systems) on the roadmap.

The body that carries this health is often the [character movement](../mechanics/character-movement.md) object. A gun that spends this pool is [Weapons](../combat/weapons.md). It fills a `DamageInfo` and calls `Hurtbox.Receive`. An enemy that swings at this body uses that same call from [enemy behaviour](../ai/enemy.md). A screen that should hear `Died` without polling is [Event systems](../architecture/events.md). A HUD that should read the numbers without a `Health` field can mirror them into a [shared variable](../architecture/variables.md). [Equipment](inventory/equipment.md) adds and removes modifiers on this sheet when gear changes, and a full bag slows movement through the same modifiers on [weight](inventory/weight.md).

## Setup

1. Create one asset per damage type: **Assets → Create → Game → Damage Type**. Create one asset per stat: **Assets → Create → Game → Stat Definition**. Name the health stat `Max Health`.
2. On the character, add `StatSheet`. Bind `Max Health` and set its base value, for example `100`.
3. Add `Health` to the same object. Assign the sheet and the `Max Health` definition. Leave **Start At Max** on.
4. Add a child called `Hurtbox` with a trigger collider slightly inside the body. Add `Hurtbox` and leave **Health** empty so it finds the parent. Put a multiplier entry on a second child if one part of the body should take more damage.
5. For a spikes hazard, use a trigger collider and a kinematic `Rigidbody`. Add `Hitbox`, set the amount and the damage type, and enable **Repeat While Overlapping** with **Repeat Interval** `0.5`. A `CharacterController` does not wake a static trigger. The rigidbody on the hazard is what makes `OnTriggerEnter` run.
6. In the physics layer matrix, let the hazard layer overlap the hurtbox layer, and stop the hazard overlapping itself.
7. Add `HealthBar` to a UI `Image` set to **Image Type: Filled**, **Horizontal**, origin **Left**. Assign the image and the health. The project needs `com.unity.ugui`, which a Unity 6 game template already has.
8. Death, a [hit flash](../combat/hit-flash.md), or a sound can use the inspector events on `Health`. Anything that needs the hit point or the damage type subscribes to the C# event instead.

## What each step is doing

`Hitbox` sees a collider, walks up to a `Hurtbox`, and ignores anything parented under its owner (the root, unless **Owner** is set). It builds a `DamageInfo`: amount, type, source, the closest point on the hurtbox, and a normal pointing from the hitbox toward that point. A one-shot hitbox records the hurtbox until the overlap ends, so a second collider on the same frame cannot strike twice. A contact hazard records a time and waits out **Repeat Interval**.

`Hurtbox` multiplies the amount by the first matching type. No entry means `1`. It then calls `Health.ApplyDamage`.

`Health` drops the hit if the body is dead, invulnerable, or the amount is not positive. It subtracts from the pool, starts invulnerability frames, and fires `Damaged`. Reaching zero latches death and fires `Died` once. `Heal` cannot revive. Call `Revive` for that.

The max pool is the `Max Health` stat when a sheet and a definition are assigned, otherwise the serialized **Max Health**. The stat result is never below `1`, so a bar does not divide by zero.

### Modifier order

A `Stat` caches its result and rebuilds it only when the base or the modifier list changes. The rebuild is always the same three steps, which is the order that makes flat and summed bonuses commute:

\[
(base + \sum flat) \times (1 + \sum percentAdd) \times \prod (1 + percentMultiply)
\]

`PercentAdd` values are fractions and are summed before they scale the stat. `+0.5` and `+0.1` together are `+60%`, not two separate multiplies. `PercentMultiply` values are also fractions, and each one multiplies on its own: two `+0.25` modifiers are `×1.25 ×1.25`, not `+50%`.

Worked example. Base `100`, flat `+20`, percent-add `+0.50` and `+0.10`, percent-multiply `+0.25`:

\[
(100 + 20) \times (1 + 0.50 + 0.10) \times 1.25 = 240
\]

Doing the multiply before the summed percent, or treating both percent kinds as the same list, gives a different number. The class does not offer a fourth operation.

Removing a modifier is by reference, or by source. Pass the buff component as the source. A later buff page owns the clock. This page only stores and withdraws the numbers.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Max Health | `100` | Pool size when no stat is assigned. |
| Start At Max | On | Begin full. Off uses **Current**, for a body that should start hurt. |
| Invulnerability Duration | `0.4` | Seconds after a landed hit during which further damage is ignored. `0` disables it. |
| Stats / Max Health Stat | Empty | When both are set, the stat replaces **Max Health**. |
| Repeat While Overlapping | Off | On for a hazard that keeps hurting while the body stands in it. |
| Repeat Interval | `0.5` | Seconds between those repeats. |

## Scripts

Each block is its own file. `Health` is the `IDamageable`. The bar and the hazard do not subclass it.

### Damage type

```csharp
using UnityEngine;

/// <summary>
/// One kind of damage. Resistances match this asset by reference.
/// </summary>
[CreateAssetMenu(fileName = "DamageType", menuName = "Game/Damage Type")]
public class DamageType : ScriptableObject
{
    [SerializeField] string displayName;

    public string DisplayName => string.IsNullOrEmpty(displayName) ? name : displayName;
}
```

### Damage info

```csharp
using System;
using UnityEngine;

/// <summary>
/// One hit, after a hurtbox has applied its multiplier.
/// </summary>
[Serializable]
public struct DamageInfo
{
    public float Amount;
    public DamageType Type;
    public UnityEngine.Object Source;
    public Vector3 Point;
    public Vector3 Normal;
}

public interface IDamageable
{
    void ApplyDamage(DamageInfo damage);
}
```

### Stats

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

public enum ModifierOperation
{
    Flat,
    PercentAdd,
    PercentMultiply
}

/// <summary>
/// A bonus stored on a stat. Value is a fraction for both percent operations:
/// 0.25 means +25%, not ×0.25 and not +25.
/// </summary>
public sealed class StatModifier
{
    public StatModifier(float value, ModifierOperation operation, UnityEngine.Object source)
    {
        Value = value;
        Operation = operation;
        Source = source;
    }

    public float Value { get; }
    public ModifierOperation Operation { get; }
    public UnityEngine.Object Source { get; }
}

/// <summary>
/// Base value plus modifiers. The cached result is rebuilt only when something changes.
/// </summary>
public sealed class Stat
{
    readonly List<StatModifier> _modifiers = new List<StatModifier>();
    float _baseValue;
    float _cached;
    bool _dirty;

    public Stat(float baseValue)
    {
        _baseValue = baseValue;
        _cached = baseValue;
    }

    public event Action Changed;

    public float BaseValue
    {
        get => _baseValue;
        set
        {
            if (Mathf.Approximately(_baseValue, value))
                return;
            _baseValue = value;
            MarkDirty();
        }
    }

    public float Value
    {
        get
        {
            if (!_dirty)
                return _cached;

            float flat = 0f;
            float percentAdd = 0f;
            float percentProduct = 1f;
            for (int i = 0; i < _modifiers.Count; i++)
            {
                StatModifier modifier = _modifiers[i];
                switch (modifier.Operation)
                {
                    case ModifierOperation.Flat:
                        flat += modifier.Value;
                        break;
                    case ModifierOperation.PercentAdd:
                        percentAdd += modifier.Value;
                        break;
                    case ModifierOperation.PercentMultiply:
                        percentProduct *= 1f + modifier.Value;
                        break;
                }
            }

            _cached = (_baseValue + flat) * (1f + percentAdd) * percentProduct;
            _dirty = false;
            return _cached;
        }
    }

    public void Add(StatModifier modifier)
    {
        if (modifier == null)
            return;
        _modifiers.Add(modifier);
        MarkDirty();
    }

    public bool Remove(StatModifier modifier)
    {
        if (modifier == null || !_modifiers.Remove(modifier))
            return false;
        MarkDirty();
        return true;
    }

    /// <summary>
    /// Drops every modifier that was added with this source. The source is the
    /// component that owns the buff, so the buff can withdraw itself.
    /// </summary>
    public int RemoveFromSource(UnityEngine.Object source)
    {
        if (source == null)
            return 0;

        int removed = _modifiers.RemoveAll(modifier => modifier.Source == source);
        if (removed > 0)
            MarkDirty();
        return removed;
    }

    void MarkDirty()
    {
        float previous = _cached;
        _dirty = true;
        float next = Value;
        if (!Mathf.Approximately(previous, next))
            Changed?.Invoke();
    }
}
```

### Stat definition and sheet

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

[CreateAssetMenu(fileName = "Stat", menuName = "Game/Stat Definition")]
public class StatDefinition : ScriptableObject
{
    [SerializeField] string displayName;

    public string DisplayName => string.IsNullOrEmpty(displayName) ? name : displayName;
}

/// <summary>
/// Runtime stats for one actor. The definition assets are the keys.
/// </summary>
[DisallowMultipleComponent]
public class StatSheet : MonoBehaviour
{
    [Serializable]
    public struct Binding
    {
        public StatDefinition definition;
        public float baseValue;
    }

    [SerializeField] Binding[] bindings = Array.Empty<Binding>();

    readonly Dictionary<StatDefinition, Stat> _stats = new Dictionary<StatDefinition, Stat>();
    bool _built;

    void Awake()
    {
        Build();
    }

    public bool TryGet(StatDefinition definition, out Stat stat)
    {
        // Build on first use too. Another component's OnEnable can run before this Awake.
        Build();
        if (definition == null)
        {
            stat = null;
            return false;
        }

        return _stats.TryGetValue(definition, out stat);
    }

    void Build()
    {
        if (_built)
            return;
        _built = true;
        if (bindings == null)
            return;

        for (int i = 0; i < bindings.Length; i++)
        {
            StatDefinition definition = bindings[i].definition;
            if (definition == null || _stats.ContainsKey(definition))
                continue;
            _stats.Add(definition, new Stat(bindings[i].baseValue));
        }
    }
}
```

### Health

```csharp
using System;
using UnityEngine;
using UnityEngine.Events;

/// <summary>
/// Current and max health, healing, death, and invulnerability frames.
/// </summary>
[DisallowMultipleComponent]
public class Health : MonoBehaviour, IDamageable
{
    [SerializeField] float maxHealth = 100f;
    [SerializeField] bool startAtMax = true;
    [SerializeField] float current = 100f;

    [Tooltip("Seconds after a landed hit during which further damage is ignored.")]
    [SerializeField] float invulnerabilityDuration = 0.4f;

    [Header("Optional max from a stat")]
    [SerializeField] StatSheet stats;
    [SerializeField] StatDefinition maxHealthStat;

    [Header("Inspector hooks")]
    [SerializeField] UnityEvent onDied;
    [SerializeField] UnityEvent<float> onDamaged;
    [SerializeField] UnityEvent<float> onHealed;

    Stat _maxStat;
    float _invulnerableUntil;
    bool _dead;
    bool _ready;

    public event Action<float, float> HealthChanged;
    public event Action<DamageInfo, float> Damaged;
    public event Action<float> Healed;
    public event Action Died;

    public bool IsDead => _dead;
    public bool IsInvulnerable => Time.time < _invulnerableUntil;
    public float Current => _current;
    float _current;

    public float Max
    {
        get
        {
            float value = maxHealth;
            if (_maxStat != null)
                value = _maxStat.Value;
            return Mathf.Max(1f, value);
        }
    }

    void OnEnable()
    {
        Subscribe();
        if (!_ready)
        {
            _ready = true;
            _dead = false;
            _current = startAtMax ? Max : Mathf.Clamp(current, 0f, Max);
            _dead = _current <= 0f;
        }

        Publish();
    }

    void OnDisable()
    {
        Unsubscribe();
    }

    public void ApplyDamage(DamageInfo damage)
    {
        if (_dead || IsInvulnerable || damage.Amount <= 0f)
            return;

        float applied = Mathf.Min(damage.Amount, _current);
        SetCurrent(_current - applied);
        Damaged?.Invoke(damage, applied);
        onDamaged?.Invoke(applied);

        if (invulnerabilityDuration > 0f)
            _invulnerableUntil = Time.time + invulnerabilityDuration;

        if (_current > 0f)
            return;

        _dead = true;
        Died?.Invoke();
        onDied?.Invoke();
    }

    public void Heal(float amount)
    {
        if (_dead || amount <= 0f)
            return;

        float applied = Mathf.Min(amount, Max - _current);
        if (applied <= 0f)
            return;

        SetCurrent(_current + applied);
        Healed?.Invoke(applied);
        onHealed?.Invoke(applied);
    }

    public void Revive(float fractionOfMax = 1f)
    {
        _invulnerableUntil = 0f;
        SetCurrent(Max * Mathf.Clamp01(fractionOfMax));
        _dead = _current <= 0f;
    }

    public void GrantInvulnerability(float seconds)
    {
        if (seconds <= 0f)
            return;
        float until = Time.time + seconds;
        if (until > _invulnerableUntil)
            _invulnerableUntil = until;
    }

    void Subscribe()
    {
        Unsubscribe();
        if (stats != null && maxHealthStat != null && stats.TryGet(maxHealthStat, out _maxStat))
            _maxStat.Changed += OnMaxStatChanged;
    }

    void Unsubscribe()
    {
        if (_maxStat != null)
            _maxStat.Changed -= OnMaxStatChanged;
        _maxStat = null;
    }

    void OnMaxStatChanged()
    {
        if (_current > Max)
            SetCurrent(Max);
        else
            Publish();
    }

    void SetCurrent(float value)
    {
        _current = Mathf.Clamp(value, 0f, Max);
        Publish();
    }

    void Publish()
    {
        HealthChanged?.Invoke(_current, Max);
    }

    void OnValidate()
    {
        maxHealth = Mathf.Max(1f, maxHealth);
        invulnerabilityDuration = Mathf.Max(0f, invulnerabilityDuration);
        current = Mathf.Max(0f, current);
    }
}
```

### Hurtbox and hitbox

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

[Serializable]
public struct DamageMultiplier
{
    public DamageType type;

    [Tooltip("1 is normal. 0.5 resists. 2 is vulnerable. 0 ignores the hit.")]
    public float multiplier;
}

/// <summary>
/// A volume that can be hit. Multipliers live here so a head and a body can differ.
/// </summary>
[DisallowMultipleComponent]
[RequireComponent(typeof(Collider))]
public class Hurtbox : MonoBehaviour
{
    [SerializeField] Health health;
    [SerializeField] DamageMultiplier[] multipliers = Array.Empty<DamageMultiplier>();

    public void Receive(DamageInfo info)
    {
        Health target = Resolve();
        if (target == null)
            return;

        info.Amount *= MultiplierFor(info.Type);
        if (info.Amount <= 0f)
            return;

        target.ApplyDamage(info);
    }

    float MultiplierFor(DamageType type)
    {
        if (type == null || multipliers == null)
            return 1f;

        for (int i = 0; i < multipliers.Length; i++)
        {
            if (multipliers[i].type == type)
                return Mathf.Max(0f, multipliers[i].multiplier);
        }

        return 1f;
    }

    Health Resolve()
    {
        if (health == null)
            health = GetComponentInParent<Health>();
        return health;
    }
}

/// <summary>
/// A volume that deals damage. A contact hazard is this component with repeat enabled.
/// </summary>
[DisallowMultipleComponent]
[RequireComponent(typeof(Collider))]
public class Hitbox : MonoBehaviour
{
    [SerializeField] float amount = 10f;
    [SerializeField] DamageType damageType;
    [SerializeField] UnityEngine.Object source;

    [Tooltip("Hurtboxes under this transform are ignored. Empty uses the root.")]
    [SerializeField] Transform owner;

    [SerializeField] bool repeatWhileOverlapping;
    [SerializeField] float repeatInterval = 0.5f;

    readonly Dictionary<int, float> _nextTime = new Dictionary<int, float>();

    Transform Owner => owner != null ? owner : transform.root;

    void OnTriggerEnter(Collider other)
    {
        TryDamage(other);
    }

    void OnTriggerStay(Collider other)
    {
        if (repeatWhileOverlapping)
            TryDamage(other);
    }

    void OnTriggerExit(Collider other)
    {
        Hurtbox hurtbox = FindHurtbox(other);
        if (hurtbox != null)
            _nextTime.Remove(hurtbox.GetInstanceID());
    }

    void TryDamage(Collider other)
    {
        Hurtbox hurtbox = FindHurtbox(other);
        if (hurtbox == null || hurtbox.transform.IsChildOf(Owner))
            return;

        int id = hurtbox.GetInstanceID();
        if (_nextTime.TryGetValue(id, out float readyAt) && Time.time < readyAt)
            return;

        _nextTime[id] = repeatWhileOverlapping
            ? Time.time + repeatInterval
            : float.PositiveInfinity;

        Vector3 point = other.ClosestPoint(transform.position);
        Vector3 normal = point - transform.position;
        if (normal.sqrMagnitude < 0.0001f)
            normal = transform.forward;
        else
            normal.Normalize();

        hurtbox.Receive(new DamageInfo
        {
            Amount = amount,
            Type = damageType,
            Source = source != null ? source : this,
            Point = point,
            Normal = normal
        });
    }

    static Hurtbox FindHurtbox(Collider other)
    {
        if (other == null)
            return null;

        Hurtbox hurtbox = other.GetComponent<Hurtbox>();
        if (hurtbox == null)
            hurtbox = other.GetComponentInParent<Hurtbox>();
        return hurtbox;
    }

    void OnValidate()
    {
        amount = Mathf.Max(0f, amount);
        if (repeatWhileOverlapping)
            repeatInterval = Mathf.Max(0.05f, repeatInterval);
    }
}
```

### Health bar

```csharp
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Fills an Image from the health events. The Image type has to be Filled.
/// </summary>
[DisallowMultipleComponent]
public class HealthBar : MonoBehaviour
{
    [SerializeField] Health health;
    [SerializeField] Image fill;

    void OnEnable()
    {
        if (health == null)
            return;

        health.HealthChanged += Refresh;
        Refresh(health.Current, health.Max);
    }

    void OnDisable()
    {
        if (health != null)
            health.HealthChanged -= Refresh;
    }

    void Refresh(float current, float max)
    {
        if (fill == null)
            return;
        fill.fillAmount = max <= 0f ? 0f : Mathf.Clamp01(current / max);
    }
}
```

!!! warning "Common pitfalls"

    A static trigger and a `CharacterController` do not report `OnTriggerEnter`. Put a kinematic `Rigidbody` on the hazard. One of the colliders still has to be a trigger, and the layer matrix has to allow the overlap.

    `OnTriggerStay` without an interval applies damage every physics step. **Repeat While Overlapping** waits for **Repeat Interval**. A one-shot hitbox suppresses further hits from that hurtbox until the overlap ends, so two colliders on one hurtbox in the same enter still count as one hit only after the first has been recorded.

    The hitbox ignores hurtboxes parented under **Owner**. A melee weapon parented to the character will not hit that character. An unparented projectile must assign **Owner** to the shooter, or it can hit them. [Weapons](../combat/weapons.md) passes that owner into each shot.

    Invulnerability blocks `ApplyDamage` and does not block `Heal`. It starts after a hit that actually removed health. A fully resisted hit never starts it, because the hurtbox does not call `ApplyDamage` when the scaled amount is zero.

    `Died` is latched. A listener that calls `ApplyDamage` again will not get a second event. `Heal` on a dead body does nothing. `Revive` clears the latch. Do not `Destroy` the body in a `Died` listener before other listeners on that same call have run; they are invoked synchronously, in subscription order.

    Percent-add and percent-multiply are different steps. Both are fractions. `0.25` is `+25%`. Summing the multiplies, or multiplying the summed percent, will not match the formula above.

    Changing a modifier's numbers in place does nothing to the cache. `StatModifier` has no setters. Remove it and add a new one, or remove by source. A null source cannot be withdrawn as a group.

    The max stat is read when `Health` enables. Unity only promises that a script's `Awake` runs before its own `OnEnable`, not before another component's, so `StatSheet` builds its dictionary on the first `TryGet` as well as in `Awake`. A sheet assigned later is not picked up until `Health` is disabled and enabled again.

    The bar's `Image` has to be **Filled**. A Simple image ignores `fillAmount`. `HealthBar` listens to the C# event, which carries current and max. The inspector `UnityEvent`s are the no-code hooks and do not carry the `DamageInfo`.
