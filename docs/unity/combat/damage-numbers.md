---
engine: Unity
version: 6+
uses:
  - name: RPGs
    text: Floating numbers coloured by damage type.
  - name: Hordes and crowds
    text: Pooled popups that merge rapid hits on many enemies.
---

# Damage numbers

A number pops above a body when it takes damage, drifts up, and fades. It listens to `Health.Damaged` on the [health](../systems/health.md#health) page, the same event as the [hit flash](hit-flash.md), and shows the amount that health actually lost, after resistances and the clamp at zero.

Each popup is a pooled object from the [object pooling](../architecture/pooling.md) page. A burst of pellets or a damage-over-time hazard would otherwise create and destroy a text object per hit. Rapid hits on the same body merge into one number that keeps counting, so a shotgun reads as one total instead of a cloud of digits.

The text is a world-space `TextMeshPro` component. In Unity 6 TextMesh Pro is part of the uGUI package (`com.unity.ugui` 2.0, namespace `TMPro`), which a new project already has.

## Setup

1. Create an empty object, add `DamageNumber`, and add a child with **GameObject → 3D Object → Text - TextMeshPro**. Import **TMP Essential Resources** when Unity asks. Centre the alignment and set the font size to about `5`.
2. Assign the text on `DamageNumber`. Save the object as a prefab with its root **inactive**, as the pooling page requires.
3. Add the `PoolManager` from the pooling page to the scene if there is not one already. Put the prefab in **Prewarm** with a count of about `20`.
4. On the character that has `Health`, add `DamageNumberSpawner`. Assign the pool manager and the prefab. Add colours for damage types if fire and poison should read differently.

## What each step is doing

`Health.Damaged` passes the `DamageInfo` and the amount applied. The spawner rounds the amount to a whole number, with a minimum of `1`, so a sliver of damage still shows something.

If the last number this spawner made is still on screen, was spawned less than **Merge Window** seconds ago, and has the same damage type, the new amount is added to it. The popup restarts its pop and its lifetime, but not its position. Otherwise the spawner asks the pool for a new one.

The popup's position is **Offset** above the body's pivot, plus a random sideways nudge so stacked numbers do not overlap exactly. It rises at **Rise Speed**, slows under **Gravity**, and turns to face the camera every `LateUpdate`, so the text is never seen edge-on. Its scale pops from **Pop Scale** to `1` over the first `0.1` s, and it fades out over the last third of its life before releasing itself back to the pool.

Bigger hits draw bigger: the scale is multiplied by up to **Big Hit Scale** as the amount approaches **Big Hit**.

Merging relies on a serial number. A pooled popup can be released and reused by another body between two hits. The spawner remembers the serial it saw, and a reused popup has a new one, so a stale reference is never merged into.

## Parameters

### Spawner

| Field | Default | Effect |
| --- | --- | --- |
| Health | Empty | Source of `Damaged`. Empty searches this object and its parents. |
| Pool / Prefab | Empty | The `PoolManager` and the `DamageNumber` prefab asset. |
| Offset | `(0, 2, 0)` | Spawn point above the pivot. |
| Spread | `0.4` | Random sideways offset, in metres. |
| Merge Window | `0.15` | Seconds in which hits of one type add to the same number. `0` turns merging off. |
| Big Hit | `100` | Amount at which a number reaches **Big Hit Scale**. |
| Big Hit Scale | `1.6` | Largest size multiplier. |
| Default Colour | White | Colour for a type with no entry. |
| Type Colours | Empty | Colour per `DamageType` asset. |

### Popup

| Field | Default | Effect |
| --- | --- | --- |
| Lifetime | `0.8` | Seconds before it returns to the pool. |
| Rise Speed | `2.5` | Starting upward speed, metres per second. |
| Gravity | `4` | Slows the rise. |
| Pop Scale | `1.5` | Scale at spawn, easing to `1`. |

## Scripts

### Popup

`PooledBehaviour` is on the pooling page. Its `Awake` is private and caches the body, so this subclass does not declare an `Awake`.

```csharp
using System.Globalization;
using TMPro;
using UnityEngine;

/// <summary>
/// One floating number. Lives on a pooled prefab and releases itself.
/// </summary>
[DisallowMultipleComponent]
public class DamageNumber : PooledBehaviour
{
    const float PopTime = 0.1f;
    static int _nextSerial;

    [SerializeField] TMP_Text text;
    [SerializeField] float lifetime = 0.8f;
    [SerializeField] float riseSpeed = 2.5f;
    [SerializeField] float gravity = 4f;
    [SerializeField] float popScale = 1.5f;

    Transform _camera;
    float _age;
    float _rise;
    float _amount;
    float _size = 1f;
    Color _colour = Color.white;

    public int Serial { get; private set; }
    public DamageType Type { get; private set; }

    public override void OnSpawn()
    {
        Serial = ++_nextSerial;
        Camera main = Camera.main;
        _camera = main != null ? main.transform : null;
    }

    public override void OnDespawn()
    {
        Serial = 0;
        Type = null;
    }

    public void Show(float amount, DamageType type, Color colour, float size)
    {
        Type = type;
        _amount = amount;
        _colour = colour;
        _size = size;
        _age = 0f;
        _rise = riseSpeed;
        Refresh();
    }

    /// <summary>Adds a merged hit. Restarts the pop and the lifetime, keeps the position.</summary>
    public void Add(float amount, float size)
    {
        _amount += amount;
        _size = Mathf.Max(_size, size);
        _age = 0f;
        Refresh();
    }

    void Update()
    {
        float dt = Time.deltaTime;
        _age += dt;
        if (_age >= lifetime)
        {
            Release();
            return;
        }

        _rise = Mathf.Max(0f, _rise - gravity * dt);
        transform.position += Vector3.up * (_rise * dt);

        float pop = Mathf.Clamp01(_age / PopTime);
        transform.localScale = Vector3.one * (_size * Mathf.Lerp(popScale, 1f, pop));

        if (text != null)
        {
            float fadeStart = lifetime * (2f / 3f);
            text.alpha = _age < fadeStart ? 1f : 1f - (_age - fadeStart) / (lifetime - fadeStart);
        }
    }

    void LateUpdate()
    {
        // After the camera has moved this frame, face the same way it does.
        if (_camera != null)
            transform.rotation = _camera.rotation;
    }

    void Refresh()
    {
        if (text == null)
            return;
        text.text = Mathf.Max(1, Mathf.RoundToInt(_amount)).ToString(CultureInfo.InvariantCulture);
        text.color = _colour;
    }

    void OnValidate()
    {
        lifetime = Mathf.Max(0.05f, lifetime);
        gravity = Mathf.Max(0f, gravity);
        popScale = Mathf.Max(0.01f, popScale);
    }
}
```

### Spawner

```csharp
using System;
using UnityEngine;

/// <summary>
/// Spawns a pooled DamageNumber for every Health.Damaged, merging rapid hits.
/// </summary>
[DisallowMultipleComponent]
public class DamageNumberSpawner : MonoBehaviour
{
    [Serializable]
    public struct TypeColour
    {
        public DamageType type;
        public Color colour;
    }

    [SerializeField] Health health;
    [SerializeField] PoolManager pool;
    [SerializeField] GameObject prefab;
    [SerializeField] Vector3 offset = new Vector3(0f, 2f, 0f);
    [SerializeField] float spread = 0.4f;
    [SerializeField] float mergeWindow = 0.15f;
    [SerializeField] float bigHit = 100f;
    [SerializeField] float bigHitScale = 1.6f;
    [SerializeField] Color defaultColour = Color.white;
    [SerializeField] TypeColour[] typeColours = Array.Empty<TypeColour>();

    DamageNumber _last;
    int _lastSerial;
    float _lastTime = float.NegativeInfinity;

    void Awake()
    {
        if (health == null)
            health = GetComponentInParent<Health>();
    }

    void OnEnable()
    {
        if (health != null)
            health.Damaged += OnDamaged;
    }

    void OnDisable()
    {
        if (health != null)
            health.Damaged -= OnDamaged;
        _last = null;
    }

    void OnDamaged(DamageInfo damage, float applied)
    {
        if (applied <= 0f || pool == null || prefab == null)
            return;

        float size = 1f;
        if (bigHit > 0f)
            size = Mathf.Lerp(1f, bigHitScale, Mathf.Clamp01(applied / bigHit));

        // The serial check catches a popup that went back to the pool and now belongs to someone else.
        bool canMerge = mergeWindow > 0f
            && _last != null
            && _last.isActiveAndEnabled
            && _last.Serial == _lastSerial
            && _last.Type == damage.Type
            && Time.time - _lastTime <= mergeWindow;

        if (canMerge)
        {
            _last.Add(applied, size);
            _lastTime = Time.time;
            return;
        }

        Vector2 nudge = UnityEngine.Random.insideUnitCircle * spread;
        Vector3 position = transform.position + offset + new Vector3(nudge.x, 0f, nudge.y);
        DamageNumber number = pool.Spawn(prefab, position, Quaternion.identity) as DamageNumber;
        if (number == null)
            return;

        number.Show(applied, damage.Type, ColourFor(damage.Type), size);
        _last = number;
        _lastSerial = number.Serial;
        _lastTime = Time.time;
    }

    Color ColourFor(DamageType type)
    {
        if (type != null && typeColours != null)
        {
            for (int i = 0; i < typeColours.Length; i++)
            {
                if (typeColours[i].type == type)
                    return typeColours[i].colour;
            }
        }

        return defaultColour;
    }

    void OnValidate()
    {
        spread = Mathf.Max(0f, spread);
        mergeWindow = Mathf.Max(0f, mergeWindow);
        bigHitScale = Mathf.Max(1f, bigHitScale);
    }
}
```

!!! warning "Common pitfalls"

    The prefab root must be saved inactive, and `DamageNumber` must be on that root. `PoolManager.Spawn` returns the root's `PooledBehaviour`. If the script sits on the text child, the cast returns null and nothing shows.

    The default TextMesh Pro shader is depth tested, so a number behind a wall or inside a large body is hidden. Switch the font material to **TextMeshPro/Distance Field Overlay** to draw numbers on top of everything.

    The size is in world units. A number far from the camera is small, and one next to it is huge. For a fixed on-screen size, multiply the scale by the distance to the camera, or draw the numbers on a screen-space canvas instead.

    `ToString` allocates a short string per number. That is fine at tens of hits a second. If the Profiler shows it, cache the strings for small values or use `TMP_Text.SetText` with a number argument.

    Merging is per spawner, so per body. Two enemies hit by the same blast each get their own number, which is the point.

    `Time.timeScale` at `0` freezes the numbers in place, because they use scaled time. That is usually right for a pause menu. For a hit stop, it holds the number at its pop until time resumes.
