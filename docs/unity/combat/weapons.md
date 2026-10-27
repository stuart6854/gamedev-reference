---
engine: Unity
version: 6+
---

# Weapons

A firearm driven by a shared definition: damage, fire rate, magazine, spread, falloff, and whether the shot is a ray or a projectile. The holder switches weapons. UI, muzzle flash, and impact effects subscribe to events.

Hits use the [health, damage, and stats](../systems/health.md#damage-info) pipeline. A shot builds a `DamageInfo` and calls [`Hurtbox.Receive`](../systems/health.md#hurtbox-and-hitbox), which applies the damage-type multiplier and then `Health.ApplyDamage`. A collider with no hurtbox falls back to `IDamageable`. The amount on the way in is the amount before that multiplier, the same as `Hitbox`.

Attack combos are not this page. They will join this Combat group. Until that page exists they stay on the [roadmap](../../roadmap.md#combat).

The aim ray is the camera from the [orbit camera](../orbit-camera.md). Recoil eases back with the [exponential blend](../../maths/interpolation.md#frame-rate-independent-damping) \(1 - e^{-k\Delta t}\).

## Setup

1. Create a **Damage Type** (`Game/Damage Type`) as on the health page. Put a **Hurtbox** on each target that should take a multiplier. A body with only `Health` still works: the shot falls back to `IDamageable`.
2. Create a **Weapon** asset (`Game/Weapon`). Set the damage, fire mode, delivery, magazine, spread, falloff, and recoil. The asset is shared, so the rounds left in the gun are not stored on it.
3. Under the shooter, add one child per weapon with a `Weapon` component, a mesh, and an empty **Muzzle** at the barrel. Assign the asset. **Hit Mask** should include the world and the hurtboxes and exclude the shooter. Leave **Owner** empty while this object sits under the shooter. The root is used. Set **Owner** when the gun is not parented to the shooter.
4. Add an empty child of the camera and put `WeaponRecoil` on it. Assign that child as **View** and as **Recoil** on every weapon. The orbit script writes the camera. It must not write this child. Shots read the child, so the next round follows the kick.
5. Add `WeaponHolder` on the shooter and assign the weapons. Key 1 selects index 0. Copy the Input System listing. A new Unity 6 project uses that backend. The legacy listing is the same holder for a project still on the Input Manager. The two files declare the same class, so add one of them.
6. If this view is the orbit camera, turn **Switch On Scroll** off. That camera already zooms with the wheel. Number keys and the gamepad d-pad still switch. With the toggle on, one frame of wheel movement changes weapon by one.
7. For projectiles, set **Delivery** to Projectile and assign a prefab with `Projectile` on the root. Do not parent that prefab to the gun. No rigidbody, or a kinematic one, steps the transform and casts along the step. A dynamic rigidbody is moved by physics, and the same cast covers the gap between frames. Put the projectile on a layer that does not collide with the shooter, and include the layers it should damage in **Hit Mask**.
8. Put `AmmoReadout` on a canvas object that stays active, and assign the holder. Put `MuzzleFlash` on each weapon. Put `ImpactEffect` on an object that stays active and assign the holder, so a shot already in the air still spawns a hit after a swap.
9. Active Input Handling must be **Input System Package (New)** or **Both** for the first holder, and **Input Manager (Old)** or **Both** for the legacy holder. The samples read devices directly and do not need an actions asset.

## Fire rate

The gap between shots is

\[
\Delta t = \frac{60}{\mathrm{rpm}}
\]

in seconds. Each shot schedules the next one \(\Delta t\) later, using `Time.time`. The lateness is `Time.time - next`. While the trigger still wants shots and the lateness covers more than one interval, the gun fires once per interval in that frame. A high rate therefore does not drop rounds when a frame is longer than \(\Delta t\).

Time with the trigger up is not stored. The schedule is pulled forward to now, otherwise the next press would dump every interval missed while you were not firing. One frame also stops after 16 shots, and any further lateness from a stall is dropped, so a hitch cannot empty the magazine on the following frames. Sixteen is enough for 57,600 rounds per minute at 60 fps. Above that, or across a stall, the extra intervals are discarded.

Semi-auto fires at most one shot per press, then waits \(\Delta t\). It does not use the loop. A press during the wait is ignored. There is no input buffer on this page. That belongs with attack combos.

Full-auto runs the loop while the trigger is held. Burst loads **Burst Count** on the press, then spends that queue through the same interval. A press while a burst is already running, or while the schedule is still in the future, does not start another.

Charge stores hold time up to **Charge Time** and fires once on release. Damage scales from **Min Charge** to full. Releasing during the fire interval keeps the charge and fires on the first frame the schedule allows. Holding does not fire.

`Time.deltaTime` and `Time.time` both stop when `timeScale` is 0, so a pause holds the trigger, the charge, and the reload.

## Hitscan

A ray from the camera centre and a ray along the muzzle are not the same line. The muzzle sits below and to the side, so a muzzle ray misses the point under the crosshair at close range, and a camera ray can count a hit the gun cannot actually see.

The camera ray only chooses an aim point. Let the camera origin be \(C\) and its forward \(f\). If that ray hits something in range, the aim point \(A\) is the hit. Otherwise \(A = C + f \cdot \mathrm{range}\). The shot leaves the muzzle \(M\) along

\[
d = \frac{A - M}{\|A - M\|}
\]

before spread. The damage ray is this second ray, not the camera ray. If something sits between the muzzle and \(A\), that something is what gets hit. A crosshair past a wall does not shoot through the wall.

Spread is applied to \(d\). A uniform point in a disk of radius **Spread + bloom** degrees becomes a pitch and yaw. The disk is `Random.insideUnitCircle`, so shots cluster at the centre. A square of `Random.Range` on each axis puts extra shots in the corners. Bloom is added after the shot, so the first round uses only **Spread**. It then recovers at **Bloom Recovery** degrees per second, from the clock, not once per frame as a fixed step.

Falloff uses the distance along the damage ray, in metres. With start \(s_0\), end \(s_1\), and minimum fraction \(m\),

\[
\mathrm{falloff}(s) = \mathrm{lerp}\!\left(1,\ m,\ \mathrm{clamp}\!\left(\frac{s - s_0}{s_1 - s_0},\ 0,\ 1\right)\right)
\]

The ray ignores the shooter's colliders, uses **Hit Mask**, and hits triggers (`QueryTriggerInteraction.Collide`) so a trigger hurtbox still counts. `RaycastNonAlloc` does not sort and it drops hits that do not fit in the buffer of 16. Exclude the shooter on the mask. The owner test is only a backstop.

## Projectiles

`UnityEngine.Pool.ObjectPool<Projectile>` creates, reactivates, and disables shots. The pool lives on the weapon. Instances are not parented to it, so holstering the gun does not freeze a shot already in the air. Do not `Destroy` a pooled shot. `Release` returns it. The weapon disposes the pool in `OnDestroy`. A prefab registry, prewarm, and effects that return themselves are [object pooling](../architecture/pooling.md). This gun keeps its own pool so a disabled weapon does not own the shot.

The prefab decides the motion.

- **Kinematic.** No rigidbody, or a kinematic one. Each `Update` casts from the current position along `velocity * dt` and moves only when the segment is clear. The cast is the whole step, so a fast shot cannot tunnel past a thin wall.
- **Dynamic.** A non-kinematic `Rigidbody`. The shot sets `linearVelocity` (Unity 6's name; `velocity` is obsolete), turns gravity off, and sets `CollisionDetectionMode.ContinuousDynamic`. Continuous detection still misses some thin colliders at a high speed. `LateUpdate` casts from the previous position to the current one and that segment is what applies damage. Gravity is forced off so this sample flies straight. An arcing shot would leave gravity on and keep the same segment cast.

Lifetime and range both return the shot to the pool. Range is distance travelled, and falloff uses that distance, including the last segment. Impact calls back into the weapon that spawned the shot, which applies `DamageInfo` and raises the impact event. A dynamic body is set to `RigidbodyInterpolation.None` so a reused instance does not smear from its previous pose.

## Ammo and reloading

The component copies **Magazine Size** into its own counter in `Awake`, and **Starting Reserve** is the rounds outside the gun. You start with a full magazine plus the reserve. Two weapons that share an asset do not share a counter.

A reload with rounds still in the magazine uses **Tactical Reload Time**. An empty magazine uses **Empty Reload Time**. Both top the magazine up from the reserve. Rounds already in the gun stay there. This is not a magazine you throw away.

The end time is `Time.time` plus the duration, so switching weapons does not freeze the clock. On the next enable, a reload that has already finished is applied. A fire press cancels a tactical reload, the time already spent is discarded, and that press can still fire because a round remains. An empty reload has nothing to fire, so the press does not cancel it. Fire is refused for the whole reload unless it was cancelled.

## Recoil

`Kick` adds pitch and a random yaw sign to a local offset, clamped so a long spray cannot turn the camera over. Pitch is negative so the view kicks up. `LateUpdate` then moves the offset towards zero by \(1 - e^{-k\Delta t}\) with \(k\) = **Recoil Recovery**. The kick is applied after the ray for that shot, so the round goes where the crosshair was and the view rises afterwards.

The offset is the local rotation of the recoil child. The orbit script can keep writing the camera parent. If recoil writes the same transform the orbit script writes, one of them wins every frame and the kick either never shows or it replaces the orbit.

## Holder and events

The holder reads fire, reload, the wheel, and the number keys, then calls `Weapon.Tick`. Its execution order is `-100`, so that tick sees this frame's press even though the weapon also ticks from its own `Update`. A second call in the same frame is ignored.

C# events carry the payload. `Fired` is the muzzle. `Impact` is the point and normal. `AmmoChanged` is the magazine and the reserve. `ReloadStarted` is the duration. Inspector `UnityEvent`s are the no-code hooks. `AmmoChanged` is also a `UnityEvent<int, int>`. The readout and the impact spawner listen to the C# events, the same way the [health bar](../systems/health.md#health-bar) listens to `HealthChanged`. Subscription rules, a typed bus, and a ScriptableObject channel for the same signals are [Event systems](../architecture/events.md). A counter that should not hold this weapon can mirror the magazine into a [shared variable](../architecture/variables.md).

`MuzzleFlash` sits on the weapon, so a holstered gun does not flash or play its shot sound. `ImpactEffect` and `AmmoReadout` sit on objects that stay active. The impact listener subscribes to every weapon in the holder, including a gun you have just put away, because a projectile from that gun can still land. `ImpactEffect` still uses `Instantiate` and `Destroy`. A rare hit can stay that way. A busy gun should use [`PooledImpact`](../architecture/pooling.md#hit-effects).

## Parameters

Definition (`Game/Weapon`):

| Field | Default | Effect |
| --- | --- | --- |
| Damage Type | Empty | `DamageInfo.Type`. The hurtbox matches it by reference. |
| Damage | `20` | Hit amount before falloff, charge scale, and the hurtbox multiplier. |
| Rounds Per Minute | `600` | Interval \(60 / \mathrm{rpm}\) seconds. |
| Fire Mode | Auto | Semi, Auto, Burst, or Charge. |
| Burst Count | `3` | Shots one press queues in Burst. |
| Charge Time | `0.6` | Seconds of hold for full damage. `0` is always full. |
| Min Charge | `0.25` | Fraction of damage if a charge is released immediately. |
| Magazine Size | `30` | Rounds in a full magazine. |
| Tactical Reload Time | `1.2` | Reload while a round remains. A fire press cancels it. |
| Empty Reload Time | `1.8` | Reload from empty. A fire press does not cancel it. |
| Range | `80` | Hitscan length and projectile travel, in metres. |
| Spread | `0.6` | Cone half-angle in degrees before bloom. |
| Bloom Per Shot | `0.35` | Degrees added after each shot. |
| Bloom Max | `4` | Cap on stacked bloom, in degrees, on top of Spread. |
| Bloom Recovery | `8` | Degrees of bloom removed per second. |
| Falloff Start | `20` | Metres of full damage. |
| Falloff End | `60` | Metres at which damage has reached Min Falloff. |
| Min Falloff | `0.4` | Fraction of damage at and beyond Falloff End. |
| Delivery | Hitscan | Hitscan or Projectile. |
| Projectile Prefab | Empty | Prefab with a `Projectile`. Used when delivery is Projectile. |
| Projectile Speed | `60` | Metres per second. |
| Projectile Lifetime | `3` | Seconds before a shot returns to the pool. |
| Recoil Kick | `(1.1, 0.35)` | Pitch and yaw in degrees. Pitch is up. Yaw picks a side per shot. |
| Recoil Recovery | `8` | Exponential rate \(k\). Half-life about `87 ms`. |

On the weapon and the holder:

| Field | Default | Effect |
| --- | --- | --- |
| Definition | Empty | The shared asset. |
| Muzzle | Empty | Ray and projectile origin. Empty uses this transform. |
| View | Empty | Crosshair transform. Empty uses `Camera.main`. |
| Owner | Empty | Hits under this transform are ignored. Empty uses the root. |
| Hit Mask | Everything | Layers a shot can hit. Exclude the shooter. |
| Starting Reserve | `90` | Rounds outside the magazine. Not stored on the asset. |
| Recoil | Empty | Child the kick is applied to. |
| Weapons | Empty | Holder list. Key 1 is index 0. |
| Start Index | `0` | Weapon equipped on play. |
| Switch On Scroll | On | Wheel changes weapon. Turn off when the orbit camera owns the wheel. |
| Max Pitch | `15` | Clamp on the recoil offset, in degrees. |

## Scripts

Copy these into the project next to the health scripts. They use `DamageType`, `DamageInfo`, `IDamageable`, and `Hurtbox` from that page. The two holder listings are one class each. Copy one of them, not both.

### Weapon definition

```csharp
using UnityEngine;

public enum FireMode
{
    Semi,
    Auto,
    Burst,
    Charge
}

public enum Delivery
{
    Hitscan,
    Projectile
}

/// <summary>
/// Shared firearm numbers. Magazine and bloom live on the weapon, not here.
/// </summary>
[CreateAssetMenu(fileName = "Weapon", menuName = "Game/Weapon")]
public class WeaponDefinition : ScriptableObject
{
    [Header("Damage")]
    public DamageType damageType = null;
    public float damage = 20f;

    [Header("Fire")]
    [Tooltip("Shots per minute. The gap between shots is 60 / this.")]
    public float roundsPerMinute = 600f;
    public FireMode fireMode = FireMode.Auto;

    [Tooltip("Shots one press queues when Fire Mode is Burst.")]
    public int burstCount = 3;

    [Tooltip("Seconds of hold for full damage when Fire Mode is Charge. 0 is always full.")]
    public float chargeTime = 0.6f;

    [Range(0f, 1f)]
    [Tooltip("Fraction of Damage if a charge is released immediately.")]
    public float minCharge = 0.25f;

    [Header("Ammo")]
    public int magazineSize = 30;

    [Tooltip("Seconds to reload while a round remains. A fire press can cancel it.")]
    public float tacticalReloadTime = 1.2f;

    [Tooltip("Seconds to reload from empty. A fire press cannot cancel it.")]
    public float emptyReloadTime = 1.8f;

    [Header("Aim")]
    [Tooltip("Metres. Hitscan length, and how far a projectile travels.")]
    public float range = 80f;

    [Tooltip("Cone half-angle in degrees before bloom.")]
    public float spread = 0.6f;

    [Tooltip("Degrees added to the cone after each shot.")]
    public float bloomPerShot = 0.35f;

    [Tooltip("Most bloom that can stack, in degrees, on top of Spread.")]
    public float bloomMax = 4f;

    [Tooltip("Degrees of bloom recovered per second.")]
    public float bloomRecovery = 8f;

    [Tooltip("Metres at which damage is still full.")]
    public float falloffStart = 20f;

    [Tooltip("Metres at which damage has fallen to Min Falloff.")]
    public float falloffEnd = 60f;

    [Range(0f, 1f)]
    public float minFalloff = 0.4f;

    [Header("Delivery")]
    public Delivery delivery = Delivery.Hitscan;
    public GameObject projectilePrefab = null;
    public float projectileSpeed = 60f;
    public float projectileLifetime = 3f;

    [Header("Recoil")]
    [Tooltip("Degrees. X is pitch (up). Y is yaw and picks a side per shot.")]
    public Vector2 recoilKick = new Vector2(1.1f, 0.35f);

    [Tooltip("Exponential recovery rate. Half-life is ln(2) / this.")]
    public float recoilRecovery = 8f;

    public float Interval => 60f / Mathf.Max(1f, roundsPerMinute);

    public float Falloff(float distance)
    {
        if (falloffEnd <= falloffStart)
            return distance <= falloffStart ? 1f : minFalloff;

        float t = Mathf.InverseLerp(falloffStart, falloffEnd, distance);
        return Mathf.Lerp(1f, minFalloff, t);
    }

    void OnValidate()
    {
        damage = Mathf.Max(0f, damage);
        roundsPerMinute = Mathf.Max(1f, roundsPerMinute);
        burstCount = Mathf.Max(1, burstCount);
        chargeTime = Mathf.Max(0f, chargeTime);
        magazineSize = Mathf.Max(1, magazineSize);
        tacticalReloadTime = Mathf.Max(0f, tacticalReloadTime);
        emptyReloadTime = Mathf.Max(0f, emptyReloadTime);
        range = Mathf.Max(0.1f, range);
        spread = Mathf.Max(0f, spread);
        bloomPerShot = Mathf.Max(0f, bloomPerShot);
        bloomMax = Mathf.Max(0f, bloomMax);
        bloomRecovery = Mathf.Max(0f, bloomRecovery);
        falloffStart = Mathf.Max(0f, falloffStart);
        falloffEnd = Mathf.Max(falloffStart, falloffEnd);
        projectileSpeed = Mathf.Max(0f, projectileSpeed);
        projectileLifetime = Mathf.Max(0.05f, projectileLifetime);
        recoilRecovery = Mathf.Max(0f, recoilRecovery);
    }
}
```

`InverseLerp` clamps, so anything inside **Falloff Start** is full damage and anything past **Falloff End** is **Min Falloff**. Keep the end past the start. If they are equal, damage steps from full to the minimum at that distance.

### Weapon

```csharp
using System;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.Pool;

/// <summary>
/// One equipped firearm. The shared asset holds the tuning. This holds the rounds and the bloom.
/// </summary>
[DisallowMultipleComponent]
public class Weapon : MonoBehaviour
{
    public const int MaxShotsPerFrame = 16;

    [SerializeField] WeaponDefinition definition;
    [SerializeField] Transform muzzle;

    [Tooltip("Crosshair transform. Assign the recoil child so shots follow the kick.")]
    [SerializeField] Transform view;

    [Tooltip("Hits under this transform are ignored. Empty uses the root.")]
    [SerializeField] Transform owner;

    [SerializeField] LayerMask hitMask = ~0;
    [SerializeField] int startingReserve = 90;
    [SerializeField] WeaponRecoil recoil;

    [Header("Inspector hooks")]
    [SerializeField] UnityEvent onFired;
    [SerializeField] UnityEvent onImpact;
    [SerializeField] UnityEvent<int, int> onAmmoChanged;
    [SerializeField] UnityEvent<float> onReloadStarted;

    public event Action Fired;
    public event Action<Vector3, Vector3> Impact;
    public event Action<int, int> AmmoChanged;
    public event Action<float> ReloadStarted;
    public event Action ReloadFinished;
    public event Action ReloadCancelled;

    int _magazine;
    int _reserve;
    float _nextShotTime;
    float _bloom;
    float _bloomTime;
    float _charge;
    float _reloadEndsAt = -1f;
    int _burstLeft;
    int _tickedFrame = -1;
    bool _charging;
    bool _firePressed;
    bool _fireHeld;
    bool _reloadPressed;
    ObjectPool<Projectile> _pool;
    readonly RaycastHit[] _hits = new RaycastHit[16];

    public WeaponDefinition Definition => definition;
    public int Magazine => _magazine;
    public int Reserve => _reserve;
    public bool IsReloading => _reloadEndsAt >= 0f;

    Transform Owner => owner != null ? owner : transform.root;

    void Awake()
    {
        _nextShotTime = Time.time;
        _bloomTime = Time.time;
        if (definition == null)
            return;

        _magazine = definition.magazineSize;
        _reserve = Mathf.Max(0, startingReserve);
        if (definition.delivery == Delivery.Projectile && definition.projectilePrefab != null)
            _pool = BuildPool();
    }

    void OnEnable()
    {
        float now = Time.time;
        if (_nextShotTime < now)
            _nextShotTime = now;
        _bloomTime = now;
        if (IsReloading && definition != null && now >= _reloadEndsAt)
            FinishReload();
        else
            PublishAmmo();
    }

    void OnDestroy()
    {
        if (_pool != null)
            _pool.Dispose();
    }

    void Update()
    {
        Tick();
    }

    public void SetInput(bool firePressed, bool fireHeld, bool reloadPressed)
    {
        _firePressed = firePressed;
        _fireHeld = fireHeld;
        _reloadPressed = reloadPressed;
    }

    public void Tick()
    {
        if (!isActiveAndEnabled || definition == null)
            return;
        if (_tickedFrame == Time.frameCount)
            return;
        _tickedFrame = Time.frameCount;

        RecoverBloom();
        if (_reloadPressed && !(_firePressed && _magazine > 0))
            BeginReload();
        if (IsReloading && Time.time >= _reloadEndsAt)
            FinishReload();
        if (IsReloading)
        {
            if (_firePressed && _magazine > 0)
                CancelReload();
            else
                return;
        }

        switch (definition.fireMode)
        {
            case FireMode.Semi:
                TickSemi();
                break;
            case FireMode.Auto:
                TickAuto();
                break;
            case FireMode.Burst:
                TickBurst();
                break;
            case FireMode.Charge:
                TickCharge(Time.deltaTime);
                break;
        }
    }

    void TickSemi()
    {
        float now = Time.time;
        if (!_firePressed || now < _nextShotTime)
        {
            if (_nextShotTime < now)
                _nextShotTime = now;
            return;
        }

        if (FireOne(1f))
            _nextShotTime = now + definition.Interval;
    }

    void TickAuto()
    {
        float now = Time.time;
        if (!_fireHeld)
        {
            if (_nextShotTime < now)
                _nextShotTime = now;
            return;
        }

        int guard = MaxShotsPerFrame;
        while (now >= _nextShotTime && guard-- > 0)
        {
            if (!FireOne(1f))
            {
                _nextShotTime = now + definition.Interval;
                return;
            }

            _nextShotTime += definition.Interval;
        }

        if (guard < 0)
            _nextShotTime = now;
    }

    void TickBurst()
    {
        float now = Time.time;
        if (_firePressed && _burstLeft <= 0 && now >= _nextShotTime)
            _burstLeft = definition.burstCount;

        if (_burstLeft <= 0)
        {
            if (_nextShotTime < now)
                _nextShotTime = now;
            return;
        }

        int guard = MaxShotsPerFrame;
        while (now >= _nextShotTime && _burstLeft > 0 && guard-- > 0)
        {
            if (!FireOne(1f))
            {
                _burstLeft = 0;
                _nextShotTime = now + definition.Interval;
                return;
            }

            _burstLeft--;
            _nextShotTime += definition.Interval;
        }

        if (guard < 0)
            _nextShotTime = now;
    }

    void TickCharge(float dt)
    {
        float now = Time.time;
        if (_fireHeld)
        {
            _charging = true;
            if (definition.chargeTime > 0f)
                _charge = Mathf.Min(definition.chargeTime, _charge + dt);
            return;
        }

        if (!_charging)
        {
            if (_nextShotTime < now)
                _nextShotTime = now;
            return;
        }

        if (now < _nextShotTime)
            return;

        float scale = 1f;
        if (definition.chargeTime > 0f)
        {
            float held = Mathf.Clamp01(_charge / definition.chargeTime);
            scale = Mathf.Lerp(definition.minCharge, 1f, held);
        }

        _charging = false;
        _charge = 0f;
        if (FireOne(scale))
            _nextShotTime = now + definition.Interval;
    }

    bool FireOne(float damageScale)
    {
        if (_magazine <= 0)
        {
            BeginReload();
            return false;
        }

        _magazine--;
        PublishAmmo();

        if (definition.delivery == Delivery.Projectile)
            SpawnProjectile(damageScale);
        else
            Hitscan(damageScale);

        _bloom = Mathf.Min(definition.bloomMax, _bloom + definition.bloomPerShot);
        if (recoil != null)
            recoil.Kick(definition.recoilKick, definition.recoilRecovery);

        Fired?.Invoke();
        onFired?.Invoke();
        return true;
    }

    void Hitscan(float damageScale)
    {
        Vector3 origin = MuzzlePosition();
        Vector3 direction = ShotDirection();
        if (!TryRay(origin, direction, definition.range, out RaycastHit hit))
            return;

        Deliver(hit.collider, hit.point, hit.normal, hit.distance, definition.damage * damageScale);
    }

    void SpawnProjectile(float damageScale)
    {
        if (_pool == null)
        {
            Debug.LogWarning("Assign a projectile prefab on the weapon asset.", this);
            return;
        }

        Projectile shot = _pool.Get();
        shot.Launch(
            MuzzlePosition(),
            ShotDirection(),
            definition.projectileSpeed,
            definition.damage * damageScale,
            definition.range,
            definition.projectileLifetime,
            hitMask,
            Owner,
            this);
    }

    Vector3 ShotDirection()
    {
        Vector3 origin = MuzzlePosition();
        Vector3 aim = AimPoint();
        Vector3 toAim = aim - origin;
        Vector3 direction = toAim.sqrMagnitude > 0.0001f ? toAim.normalized : ViewForward();
        return ApplySpread(direction);
    }

    Vector3 AimPoint()
    {
        Transform eye = Eye();
        if (eye == null)
            return MuzzlePosition() + ViewForward() * definition.range;

        if (TryRay(eye.position, eye.forward, definition.range, out RaycastHit hit))
            return hit.point;
        return eye.position + eye.forward * definition.range;
    }

    Vector3 ApplySpread(Vector3 direction)
    {
        float degrees = definition.spread + _bloom;
        if (degrees <= 0.001f)
            return direction;

        Vector2 disk = UnityEngine.Random.insideUnitCircle * degrees;
        return Look(direction) * Quaternion.Euler(disk.y, disk.x, 0f) * Vector3.forward;
    }

    bool TryRay(Vector3 origin, Vector3 direction, float distance, out RaycastHit closest)
    {
        closest = default;
        if (distance <= 0f || direction.sqrMagnitude < 0.0001f)
            return false;

        int count = Physics.RaycastNonAlloc(
            origin,
            direction,
            _hits,
            distance,
            hitMask,
            QueryTriggerInteraction.Collide);

        float best = float.PositiveInfinity;
        bool found = false;
        for (int i = 0; i < count; i++)
        {
            Collider collider = _hits[i].collider;
            if (collider == null || IsOwner(collider.transform))
                continue;
            if (_hits[i].distance >= best)
                continue;

            best = _hits[i].distance;
            closest = _hits[i];
            found = true;
        }

        return found;
    }

    /// <summary>
    /// Applies falloff and the health pipeline. Projectiles report the distance they travelled.
    /// </summary>
    public void Deliver(Collider collider, Vector3 point, Vector3 normal, float distance, float baseDamage)
    {
        if (definition == null || collider == null || IsOwner(collider.transform))
            return;

        var info = new DamageInfo
        {
            Amount = baseDamage * definition.Falloff(distance),
            Type = definition.damageType,
            Source = this,
            Point = point,
            Normal = normal
        };

        Hurtbox hurtbox = collider.GetComponent<Hurtbox>();
        if (hurtbox == null)
            hurtbox = collider.GetComponentInParent<Hurtbox>();

        if (hurtbox != null)
        {
            hurtbox.Receive(info);
        }
        else
        {
            IDamageable damageable = collider.GetComponent<IDamageable>();
            if (damageable == null)
                damageable = collider.GetComponentInParent<IDamageable>();
            if (damageable != null)
                damageable.ApplyDamage(info);
        }

        Impact?.Invoke(point, normal);
        onImpact?.Invoke();
    }

    bool IsOwner(Transform hit)
    {
        return hit != null && hit.IsChildOf(Owner);
    }

    void BeginReload()
    {
        if (IsReloading || definition == null)
            return;
        if (_magazine >= definition.magazineSize || _reserve <= 0)
            return;

        float duration = _magazine > 0 ? definition.tacticalReloadTime : definition.emptyReloadTime;
        _reloadEndsAt = Time.time + duration;
        _burstLeft = 0;
        _charging = false;
        _charge = 0f;
        ReloadStarted?.Invoke(duration);
        onReloadStarted?.Invoke(duration);
    }

    void CancelReload()
    {
        if (!IsReloading)
            return;
        _reloadEndsAt = -1f;
        ReloadCancelled?.Invoke();
    }

    void FinishReload()
    {
        int need = definition.magazineSize - _magazine;
        int take = Mathf.Min(need, _reserve);
        _magazine += take;
        _reserve -= take;
        _reloadEndsAt = -1f;
        PublishAmmo();
        ReloadFinished?.Invoke();
    }

    void PublishAmmo()
    {
        AmmoChanged?.Invoke(_magazine, _reserve);
        onAmmoChanged?.Invoke(_magazine, _reserve);
    }

    void RecoverBloom()
    {
        float now = Time.time;
        float dt = Mathf.Max(0f, now - _bloomTime);
        _bloomTime = now;
        if (dt > 0f)
            _bloom = Mathf.Max(0f, _bloom - definition.bloomRecovery * dt);
    }

    ObjectPool<Projectile> BuildPool()
    {
        return new ObjectPool<Projectile>(
            CreateProjectile,
            OnGetProjectile,
            OnReleaseProjectile,
            OnDestroyProjectile,
            true,
            16,
            64);
    }

    Projectile CreateProjectile()
    {
        GameObject instance = Instantiate(definition.projectilePrefab);
        Projectile projectile = instance.GetComponent<Projectile>();
        if (projectile == null)
            projectile = instance.AddComponent<Projectile>();
        return projectile;
    }

    void OnGetProjectile(Projectile projectile)
    {
        projectile.SetPool(_pool);
        projectile.gameObject.SetActive(true);
    }

    static void OnReleaseProjectile(Projectile projectile)
    {
        projectile.gameObject.SetActive(false);
    }

    static void OnDestroyProjectile(Projectile projectile)
    {
        if (projectile != null)
            Destroy(projectile.gameObject);
    }

    Vector3 MuzzlePosition()
    {
        return muzzle != null ? muzzle.position : transform.position;
    }

    Transform Eye()
    {
        if (view != null)
            return view;
        Camera main = Camera.main;
        return main != null ? main.transform : null;
    }

    Vector3 ViewForward()
    {
        Transform eye = Eye();
        if (eye != null)
            return eye.forward;
        if (muzzle != null)
            return muzzle.forward;
        return transform.forward;
    }

    static Quaternion Look(Vector3 direction)
    {
        Vector3 up = Mathf.Abs(direction.y) > 0.99f ? Vector3.forward : Vector3.up;
        return Quaternion.LookRotation(direction, up);
    }

    void OnValidate()
    {
        startingReserve = Mathf.Max(0, startingReserve);
    }
}
```

The pool is built in `Awake`. Changing the asset to projectile after that does not create one. `OnGet` assigns the pool before `Launch`, so a shot can release itself. The inactive cap is 64. Further returns are destroyed by the pool. The list starts with room for 16. It does not pre-instantiate them.

### Projectile

```csharp
using UnityEngine;
using UnityEngine.Pool;

/// <summary>
/// A pooled shot. Kinematic motion casts along the step.
/// A dynamic rigidbody is moved by physics, and LateUpdate casts the gap.
/// </summary>
[DisallowMultipleComponent]
public class Projectile : MonoBehaviour
{
    IObjectPool<Projectile> _pool;
    Weapon _weapon;
    Transform _owner;
    LayerMask _mask;
    Vector3 _velocity;
    Vector3 _previous;
    float _damage;
    float _rangeLeft;
    float _life;
    float _travelled;
    bool _alive;
    bool _useBody;
    Rigidbody _body;
    readonly RaycastHit[] _hits = new RaycastHit[16];

    void Awake()
    {
        _body = GetComponent<Rigidbody>();
    }

    public void SetPool(IObjectPool<Projectile> pool)
    {
        _pool = pool;
    }

    public void Launch(
        Vector3 position,
        Vector3 direction,
        float speed,
        float damage,
        float range,
        float lifetime,
        LayerMask mask,
        Transform owner,
        Weapon weapon)
    {
        if (direction.sqrMagnitude < 0.0001f)
            direction = Vector3.forward;
        direction.Normalize();

        _weapon = weapon;
        _owner = owner;
        _mask = mask;
        _damage = damage;
        _rangeLeft = Mathf.Max(0f, range);
        _life = lifetime;
        _travelled = 0f;
        _alive = true;
        _velocity = direction * Mathf.Max(0f, speed);
        _previous = position;
        _useBody = _body != null && !_body.isKinematic;

        Quaternion rotation = Look(direction);
        if (_useBody)
        {
            _body.linearVelocity = Vector3.zero;
            _body.angularVelocity = Vector3.zero;
            _body.useGravity = false;
            _body.collisionDetectionMode = CollisionDetectionMode.ContinuousDynamic;
            _body.interpolation = RigidbodyInterpolation.None;
            _body.position = position;
            _body.rotation = rotation;
            _body.linearVelocity = _velocity;
        }
        else
        {
            transform.SetPositionAndRotation(position, rotation);
        }
    }

    void Update()
    {
        if (!_alive)
            return;

        _life -= Time.deltaTime;
        if (_life <= 0f)
        {
            Release();
            return;
        }

        if (_useBody || _rangeLeft <= 0f)
            return;

        float step = _velocity.magnitude * Time.deltaTime;
        if (step <= 0f)
            return;
        if (step > _rangeLeft)
            step = _rangeLeft;

        Vector3 direction = _velocity.normalized;
        if (TryRay(transform.position, direction, step, out RaycastHit hit))
        {
            Impact(hit.collider, hit.point, hit.normal, _travelled + hit.distance);
            return;
        }

        transform.position += direction * step;
        _travelled += step;
        _rangeLeft -= step;
        if (_rangeLeft <= 0f)
            Release();
    }

    void LateUpdate()
    {
        if (!_alive || !_useBody)
            return;

        Vector3 current = _body.position;
        Vector3 delta = current - _previous;
        float distance = delta.magnitude;
        if (distance > 0.0001f && _rangeLeft > 0f)
        {
            float cast = Mathf.Min(distance, _rangeLeft);
            Vector3 direction = delta / distance;
            if (TryRay(_previous, direction, cast, out RaycastHit hit))
            {
                Impact(hit.collider, hit.point, hit.normal, _travelled + hit.distance);
                return;
            }

            _travelled += cast;
            _rangeLeft -= cast;
        }

        _previous = current;
        if (_rangeLeft <= 0f)
            Release();
    }

    void Impact(Collider collider, Vector3 point, Vector3 normal, float distance)
    {
        if (!_alive)
            return;

        if (_weapon != null)
            _weapon.Deliver(collider, point, normal, distance, _damage);
        Release();
    }

    void Release()
    {
        if (!_alive)
            return;

        _alive = false;
        if (_body != null && !_body.isKinematic)
        {
            _body.linearVelocity = Vector3.zero;
            _body.angularVelocity = Vector3.zero;
        }

        if (_pool != null)
            _pool.Release(this);
        else
            gameObject.SetActive(false);
    }

    bool TryRay(Vector3 origin, Vector3 direction, float distance, out RaycastHit closest)
    {
        closest = default;
        if (distance <= 0f)
            return false;

        int count = Physics.RaycastNonAlloc(
            origin,
            direction,
            _hits,
            distance,
            _mask,
            QueryTriggerInteraction.Collide);

        float best = float.PositiveInfinity;
        bool found = false;
        for (int i = 0; i < count; i++)
        {
            Collider collider = _hits[i].collider;
            if (collider == null)
                continue;
            if (_owner != null && collider.transform.IsChildOf(_owner))
                continue;
            if (collider.transform.IsChildOf(transform))
                continue;
            if (_hits[i].distance >= best)
                continue;

            best = _hits[i].distance;
            closest = _hits[i];
            found = true;
        }

        return found;
    }

    static Quaternion Look(Vector3 direction)
    {
        Vector3 up = Mathf.Abs(direction.y) > 0.99f ? Vector3.forward : Vector3.up;
        return Quaternion.LookRotation(direction, up);
    }
}
```

### Recoil

```csharp
using UnityEngine;

/// <summary>
/// Local kick on this transform, eased back to identity.
/// Put it on a child of the camera. Do not put it on a transform the orbit script writes.
/// </summary>
[DisallowMultipleComponent]
public class WeaponRecoil : MonoBehaviour
{
    [SerializeField] float maxPitch = 15f;

    Vector2 _offset;
    float _recovery = 8f;

    public void Kick(Vector2 pitchYaw, float recovery)
    {
        _recovery = Mathf.Max(0f, recovery);
        float yaw = pitchYaw.y;
        if (UnityEngine.Random.value < 0.5f)
            yaw = -yaw;

        _offset.x = Mathf.Max(-maxPitch, _offset.x - Mathf.Abs(pitchYaw.x));
        _offset.y = Mathf.Clamp(_offset.y + yaw, -maxPitch, maxPitch);
    }

    void LateUpdate()
    {
        float blend = 1f - Mathf.Exp(-_recovery * Time.deltaTime);
        _offset = Vector2.Lerp(_offset, Vector2.zero, blend);
        transform.localRotation = Quaternion.Euler(_offset.x, _offset.y, 0f);
    }

    void OnDisable()
    {
        _offset = Vector2.zero;
        transform.localRotation = Quaternion.identity;
    }

    void OnValidate()
    {
        maxPitch = Mathf.Max(0f, maxPitch);
    }
}
```

### Holder

The keyboard is the number keys, R, and the left mouse button. A gamepad uses the right trigger, the north face button, and the d-pad left and right. The wheel switches only when **Switch On Scroll** is on. Device reads are already this frame's state and are not multiplied by `Time.deltaTime`. The fire interval is what consumes time. A hotbar that selects by the same index calls `Equip` from [Slots and hotbar](../systems/inventory/slots.md).

=== "Input System"

    ```csharp
    using System;
    using UnityEngine;
    using UnityEngine.InputSystem;

    /// <summary>
    /// Switches weapons and feeds fire and reload into the equipped one.
    /// </summary>
    /// <remarks>
    /// Input System, the default backend in a new Unity 6 project.
    /// Requires the Input System package, and Active Input Handling set to
    /// "Input System Package (New)" or "Both". Reads devices directly so
    /// the sample does not need an actions asset. Runs before the weapon
    /// so this frame's press fires this frame.
    /// </remarks>
    [DefaultExecutionOrder(-100)]
    [DisallowMultipleComponent]
    public class WeaponHolder : MonoBehaviour
    {
        static readonly Key[] NumberKeys =
        {
            Key.Digit1,
            Key.Digit2,
            Key.Digit3,
            Key.Digit4,
            Key.Digit5,
            Key.Digit6,
            Key.Digit7,
            Key.Digit8,
            Key.Digit9
        };

        [SerializeField] Weapon[] weapons = Array.Empty<Weapon>();
        [SerializeField] int startIndex;

        [Tooltip("Turn off when an orbit camera already uses the scroll wheel to zoom.")]
        [SerializeField] bool switchOnScroll = true;

        int _index = -1;

        public event Action<Weapon> WeaponChanged;

        public Weapon Current => _index >= 0 && weapons != null && _index < weapons.Length ? weapons[_index] : null;

        public Weapon[] Weapons => weapons;

        void Start()
        {
            if (weapons == null || weapons.Length == 0)
                return;

            int index = Mathf.Clamp(startIndex, 0, weapons.Length - 1);
            for (int i = 0; i < weapons.Length; i++)
            {
                if (i != index && weapons[i] != null)
                    weapons[i].gameObject.SetActive(false);
            }

            Equip(index);
        }

        void Update()
        {
            ReadInput(out bool firePressed, out bool fireHeld, out bool reload, out float scroll, out int number);

            if (number >= 0)
                Equip(number);
            else if (switchOnScroll && scroll > 0f)
                Equip(Wrap(_index + 1));
            else if (switchOnScroll && scroll < 0f)
                Equip(Wrap(_index - 1));

            Weapon current = Current;
            if (current != null)
            {
                current.SetInput(firePressed, fireHeld, reload);
                current.Tick();
            }
        }

        public void Equip(int index)
        {
            if (weapons == null || index < 0 || index >= weapons.Length)
                return;
            if (weapons[index] == null)
                return;
            if (_index == index && weapons[index].gameObject.activeSelf)
                return;

            if (_index >= 0 && _index < weapons.Length && weapons[_index] != null)
                weapons[_index].gameObject.SetActive(false);

            _index = index;
            weapons[_index].gameObject.SetActive(true);
            WeaponChanged?.Invoke(weapons[_index]);
        }

        int Wrap(int index)
        {
            int count = weapons == null ? 0 : weapons.Length;
            if (count <= 0)
                return 0;

            int wrapped = index % count;
            if (wrapped < 0)
                wrapped += count;
            return wrapped;
        }

        void ReadInput(out bool firePressed, out bool fireHeld, out bool reload, out float scroll, out int number)
        {
            firePressed = false;
            fireHeld = false;
            reload = false;
            scroll = 0f;
            number = -1;

            Keyboard keyboard = Keyboard.current;
            if (keyboard != null)
            {
                reload |= keyboard.rKey.wasPressedThisFrame;
                for (int i = 0; i < NumberKeys.Length; i++)
                {
                    if (keyboard[NumberKeys[i]].wasPressedThisFrame)
                        number = i;
                }
            }

            Mouse mouse = Mouse.current;
            if (mouse != null)
            {
                firePressed |= mouse.leftButton.wasPressedThisFrame;
                fireHeld |= mouse.leftButton.isPressed;
                float wheel = mouse.scroll.ReadValue().y;
                if (wheel > 0.01f)
                    scroll = 1f;
                else if (wheel < -0.01f)
                    scroll = -1f;
            }

            Gamepad gamepad = Gamepad.current;
            if (gamepad != null)
            {
                firePressed |= gamepad.rightTrigger.wasPressedThisFrame;
                fireHeld |= gamepad.rightTrigger.isPressed;
                reload |= gamepad.buttonNorth.wasPressedThisFrame;
                if (gamepad.dpad.right.wasPressedThisFrame)
                    scroll = 1f;
                else if (gamepad.dpad.left.wasPressedThisFrame)
                    scroll = -1f;
            }
        }

        void OnValidate()
        {
            if (startIndex < 0)
                startIndex = 0;
        }
    }
    ```

=== "Legacy Input Manager"

    `GetMouseButton` is the left button. `GetKeyDown(KeyCode.R)` reloads. `GetAxis("Mouse ScrollWheel")` is the default wheel axis, already this frame's notch, and it is not multiplied by `Time.deltaTime`. There is no gamepad on this listing. A right trigger and a d-pad need the Input System tab.

    ```csharp
    using System;
    using UnityEngine;

    /// <summary>
    /// Switches weapons and feeds fire and reload into the equipped one.
    /// </summary>
    /// <remarks>
    /// Legacy Input Manager. Active Input Handling must be
    /// "Input Manager (Old)" or "Both". Fire is the left mouse button,
    /// reload is R, and the wheel uses the default Mouse ScrollWheel axis.
    /// Runs before the weapon so this frame's press fires this frame.
    /// </remarks>
    [DefaultExecutionOrder(-100)]
    [DisallowMultipleComponent]
    public class WeaponHolder : MonoBehaviour
    {
        [SerializeField] Weapon[] weapons = Array.Empty<Weapon>();
        [SerializeField] int startIndex;

        [Tooltip("Turn off when an orbit camera already uses the scroll wheel to zoom.")]
        [SerializeField] bool switchOnScroll = true;

        int _index = -1;

        public event Action<Weapon> WeaponChanged;

        public Weapon Current => _index >= 0 && weapons != null && _index < weapons.Length ? weapons[_index] : null;

        public Weapon[] Weapons => weapons;

        void Start()
        {
            if (weapons == null || weapons.Length == 0)
                return;

            int index = Mathf.Clamp(startIndex, 0, weapons.Length - 1);
            for (int i = 0; i < weapons.Length; i++)
            {
                if (i != index && weapons[i] != null)
                    weapons[i].gameObject.SetActive(false);
            }

            Equip(index);
        }

        void Update()
        {
            ReadInput(out bool firePressed, out bool fireHeld, out bool reload, out float scroll, out int number);

            if (number >= 0)
                Equip(number);
            else if (switchOnScroll && scroll > 0f)
                Equip(Wrap(_index + 1));
            else if (switchOnScroll && scroll < 0f)
                Equip(Wrap(_index - 1));

            Weapon current = Current;
            if (current != null)
            {
                current.SetInput(firePressed, fireHeld, reload);
                current.Tick();
            }
        }

        public void Equip(int index)
        {
            if (weapons == null || index < 0 || index >= weapons.Length)
                return;
            if (weapons[index] == null)
                return;
            if (_index == index && weapons[index].gameObject.activeSelf)
                return;

            if (_index >= 0 && _index < weapons.Length && weapons[_index] != null)
                weapons[_index].gameObject.SetActive(false);

            _index = index;
            weapons[_index].gameObject.SetActive(true);
            WeaponChanged?.Invoke(weapons[_index]);
        }

        int Wrap(int index)
        {
            int count = weapons == null ? 0 : weapons.Length;
            if (count <= 0)
                return 0;

            int wrapped = index % count;
            if (wrapped < 0)
                wrapped += count;
            return wrapped;
        }

        void ReadInput(out bool firePressed, out bool fireHeld, out bool reload, out float scroll, out int number)
        {
            firePressed = Input.GetMouseButtonDown(0);
            fireHeld = Input.GetMouseButton(0);
            reload = Input.GetKeyDown(KeyCode.R);
            scroll = 0f;
            number = -1;

            float wheel = Input.GetAxis("Mouse ScrollWheel");
            if (wheel > 0.01f)
                scroll = 1f;
            else if (wheel < -0.01f)
                scroll = -1f;

            for (int i = 0; i < 9; i++)
            {
                if (Input.GetKeyDown(KeyCode.Alpha1 + i))
                    number = i;
            }
        }

        void OnValidate()
        {
            if (startIndex < 0)
                startIndex = 0;
        }
    }
    ```

### Readout and effects

`Text` is the uGUI text component. A muzzle particle should be a short burst with **Play On Awake** off. The impact prefab is instantiated and destroyed. It is not pooled. A busy gun can pool it the same way as `Projectile`.

```csharp
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Shows the equipped weapon's magazine and reserve.
/// </summary>
[DisallowMultipleComponent]
public class AmmoReadout : MonoBehaviour
{
    [SerializeField] WeaponHolder holder;
    [SerializeField] Text label;

    Weapon _weapon;

    void OnEnable()
    {
        if (holder == null)
            return;

        holder.WeaponChanged += Bind;
        Bind(holder.Current);
    }

    void OnDisable()
    {
        if (holder != null)
            holder.WeaponChanged -= Bind;
        Bind(null);
    }

    void Bind(Weapon weapon)
    {
        if (_weapon != null)
            _weapon.AmmoChanged -= Refresh;

        _weapon = weapon;
        if (_weapon == null)
            return;

        _weapon.AmmoChanged += Refresh;
        Refresh(_weapon.Magazine, _weapon.Reserve);
    }

    void Refresh(int magazine, int reserve)
    {
        if (label != null)
            label.text = magazine + " / " + reserve;
    }
}
```

```csharp
using UnityEngine;

/// <summary>
/// Muzzle particle and shot sound. Keep this on the weapon so a holstered gun stays quiet.
/// </summary>
[DisallowMultipleComponent]
public class MuzzleFlash : MonoBehaviour
{
    [SerializeField] Weapon weapon;
    [SerializeField] ParticleSystem flash;
    [SerializeField] AudioSource shot;

    void Awake()
    {
        if (weapon == null)
            weapon = GetComponent<Weapon>();
    }

    void OnEnable()
    {
        if (weapon != null)
            weapon.Fired += Play;
    }

    void OnDisable()
    {
        if (weapon != null)
            weapon.Fired -= Play;
    }

    void Play()
    {
        if (flash != null)
            flash.Play();
        if (shot != null)
            shot.Play();
    }
}
```

```csharp
using UnityEngine;

/// <summary>
/// Spawns a hit prefab for every weapon on the holder, including one just holstered.
/// Instantiate is enough for a rare hit. A busy gun should use PooledImpact
/// from the object pooling page.
/// </summary>
[DisallowMultipleComponent]
public class ImpactEffect : MonoBehaviour
{
    [SerializeField] WeaponHolder holder;
    [SerializeField] GameObject prefab;
    [SerializeField] float lifetime = 2f;

    void OnEnable()
    {
        if (holder == null || holder.Weapons == null)
            return;

        Weapon[] list = holder.Weapons;
        for (int i = 0; i < list.Length; i++)
        {
            if (list[i] != null)
                list[i].Impact += Spawn;
        }
    }

    void OnDisable()
    {
        if (holder == null || holder.Weapons == null)
            return;

        Weapon[] list = holder.Weapons;
        for (int i = 0; i < list.Length; i++)
        {
            if (list[i] != null)
                list[i].Impact -= Spawn;
        }
    }

    void Spawn(Vector3 point, Vector3 normal)
    {
        if (prefab == null)
            return;

        if (normal.sqrMagnitude < 0.0001f)
            normal = Vector3.up;

        GameObject instance = Instantiate(prefab, point, Quaternion.LookRotation(normal));
        Destroy(instance, lifetime);
    }

    void OnValidate()
    {
        lifetime = Mathf.Max(0.05f, lifetime);
    }
}
```

!!! warning "Common pitfalls"

    The magazine must not live on the `ScriptableObject`. The asset is shared. Two guns would spend the same counter, and an edit at runtime would dirty the asset. Copy the size into the component.

    Do not bank fire time while the trigger is up. Pull the next-shot time forward to `Time.time`, or one press after a pause fires a catch-up burst. The 16-shot cap has to drop the rest of a stall as well, or the frames after the hitch keep emptying the magazine. Semi-auto must not use that loop.

    A camera-centre ray is the crosshair, not the bullet. Damage has to start at the muzzle and travel towards the camera's aim point. Exclude the shooter from **Hit Mask**. A ray that starts inside a collider does not hit that collider, so a barrel buried in a wall fires through it. `RaycastNonAlloc` is unsorted and keeps only 16 hits. If those 16 are the shooter's own bones, the target is never tested.

    Trigger hurtboxes are hit only because the query uses `QueryTriggerInteraction.Collide`. A mask of every layer will also hit trigger volumes that are not hurtboxes. Put hurtboxes on their own layer.

    `Hurtbox.Receive` multiplies the amount. Passing an amount you already multiplied doubles the resistance. Skipping the hurtbox and calling `Health.ApplyDamage` drops the head and body multipliers. Use the hurtbox when there is one.

    Pooled shots are not children of the gun, and they are released rather than destroyed. `Release` from `OnDisable` recurses: the pool disables the object, and `OnDisable` releases it again. Zero a dynamic body's `linearVelocity` before deactivating it. `velocity` is the obsolete name in Unity 6. `ContinuousDynamic` is not a substitute for the segment cast. Trails, scene unload, and a shared registry are [object pooling](../architecture/pooling.md#pitfalls).

    A tactical reload can be cancelled because a round remains, and the time already spent is thrown away. An empty reload cannot. Holstering uses the clock, so the reload finishes while the gun is away. Bloom does the same on the next tick.

    Recoil on the camera transform fights the orbit script, which writes that transform every `LateUpdate`. Kick a child, and aim through that child. Leave **Switch On Scroll** off when that orbit camera also reads the wheel, or one notch zooms and swaps weapons together.

    `AmmoReadout` binds when the holder equips. It has to stay active across a swap. A muzzle listener on the weapon unsubscribes when the gun is disabled, which is what you want for the flash and not what you want for a projectile that is still in the air.
