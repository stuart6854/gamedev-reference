---
engine: Unity
version: 6+
package: AI Navigation 2.x
uses:
  - name: Hordes and crowds
    text: Waves bought from a budget that grows each round.
  - name: Shooters
    text: Arena and tower-defence rounds with a clear break between them.
---

# Enemy waves

Spawning enemies in rounds: a wave spawns, the player clears it, a short break, then a harder wave. Waves can be authored by hand, or bought from a points budget that grows each wave. Both sit on a shared spawner that picks spawn points out of the player's sight and tracks who is alive.

Spawning that does not come in rounds, such as a steady trickle, zones that wake near the player, or a director that paces intensity, is [continuous spawning](spawning.md). It uses the same spawner.

## Which method

| Method | How difficulty rises | Good for | Weak at |
| --- | --- | --- | --- |
| **Fixed waves** | You author every wave. | Tower defence, arenas with a set number of rounds, tutorials. | Endless modes. Every wave past the authored ones is a guess. |
| **Budget waves** | Each wave gets more points. Enemies cost points, and are bought at random until the budget is spent. | Endless modes, and mixing enemy types without authoring every combination. | Exact set pieces. The same wave number varies from run to run. |

## Setup

1. Enemies need `Health` on the root, as on the [enemy behaviour](enemy.md) page. With a `NavMeshAgent`, bake a NavMesh first: spawn positions are snapped onto it.
2. Place empty objects with `SpawnPoint` around the level. **Radius** spreads enemies around each point. Points register themselves while enabled, so a door that opens can enable more.
3. Put `EnemySpawner` on a manager object. Assign the player and the camera. **Min Distance** and **Off Screen Only** stop enemies appearing on top of, or in front of, the player.
4. Put `WaveSpawner` on the same object. Pick **Mode**:
    - **Fixed**: fill **Waves**. Each wave is a list of groups: a prefab, a count, and the seconds between spawns. Groups run one after another.
    - **Budget**: fill **Entries** with prefabs, costs, weights, and the first wave each may appear in. Set **Base Budget** and **Budget Per Wave**.
5. UI subscribes to `WaveStarted` and `WaveCleared`, and reads `EnemySpawner.Alive` for a counter.

## What each step is doing

### Choosing a spawn point

Every enabled `SpawnPoint` is a candidate. A point is skipped when it is closer to the player than **Min Distance**, further than **Max Distance**, or, with **Off Screen Only**, inside the camera's view. The view test is the viewport position: in front of the camera and inside \([0, 1]\) on both axes. It ignores walls, so a point behind a wall but in the view direction counts as visible. That errs on the safe side.

One candidate is picked at random. When there are none, `TrySpawn` returns false and the caller tries again a moment later.

The spawn position is a random point within the point's radius, snapped to the NavMesh with `NavMesh.SamplePosition`. Instantiating a `NavMeshAgent` off the NavMesh logs an error and leaves the agent unable to move.

### Alive count and the cap

The spawner subscribes to each enemy's `Died` and removes it from its alive list. An enemy destroyed without dying, such as one despawned by a trigger, is pruned the next time the list is read. **Max Alive** caps the total. A wave waits for room instead of exceeding it, which bounds the cost of a big wave on a slow machine.

### A wave's life

```text
for wave = 1, 2, 3, ...:
    build the list of spawns for this wave
    WaveStarted(wave)
    for each spawn: wait for room, spawn, wait its interval
    wait until every enemy is dead, or Max Wave Time runs out
    WaveCleared(wave)
    wait Time Between Waves
```

In fixed mode, waves past the last authored one repeat the last wave, with each count multiplied by \(1 + \text{Overflow Growth} \times k\) for the \(k\)-th repeat.

### Buying a budget wave

```text
budget = Base Budget + Budget Per Wave * (wave - 1)
while some entry is unlocked (Min Wave <= wave) and costs no more than what is left:
    pick one of those entries, weighted
    add it to the wave
    budget -= its cost
```

Cheap enemies fill the gaps a big one leaves, so the budget is spent almost exactly. Costs of at least 1 keep the loop finite. To make late waves feel different and not only longer, raise **Min Wave** on stronger enemies and give them a higher weight than the weak ones, so they take over the budget as they unlock.

Spawning is spread over the wave by **Spawn Interval**. A wave of 40 points at 0.4 s each takes 16 s to arrive, which is part of the pacing.

## Scripts

### Spawn point

```csharp
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;

/// <summary>
/// A place enemies may appear. Registers itself while enabled.
/// </summary>
public class SpawnPoint : MonoBehaviour
{
    static readonly List<SpawnPoint> _all = new List<SpawnPoint>();
    public static IReadOnlyList<SpawnPoint> All => _all;

    [Tooltip("Enemies appear at a random point within this radius.")]
    [Min(0f)] [SerializeField] float radius = 1.5f;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        _all.Clear();
    }

    void OnEnable()
    {
        _all.Add(this);
    }

    void OnDisable()
    {
        _all.Remove(this);
    }

    /// <summary>A random position within the radius, on the NavMesh when there is one nearby.</summary>
    public Vector3 RandomPosition()
    {
        Vector2 offset = Random.insideUnitCircle * radius;
        Vector3 position = transform.position + new Vector3(offset.x, 0f, offset.y);
        if (NavMesh.SamplePosition(position, out NavMeshHit hit, radius + 2f, NavMesh.AllAreas))
            return hit.position;
        return position;
    }

    void OnDrawGizmos()
    {
        Gizmos.color = new Color(1f, 0.3f, 0.2f, 0.8f);
        Gizmos.DrawWireSphere(transform.position, radius);
    }
}
```

### Enemy spawner

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Spawns enemies at spawn points the player cannot see, and tracks which are alive.
/// </summary>
public class EnemySpawner : MonoBehaviour
{
    [SerializeField] Transform player;
    [SerializeField] Camera viewCamera;

    [Tooltip("Points nearer the player than this are skipped.")]
    [SerializeField] float minDistance = 12f;
    [Tooltip("Points further from the player than this are skipped.")]
    [SerializeField] float maxDistance = 80f;
    [Tooltip("Skip points inside the camera's view.")]
    [SerializeField] bool offScreenOnly = true;
    [Min(1)] [SerializeField] int maxAlive = 60;

    public event Action<Health> Spawned;
    public event Action<Health> Killed;

    public Transform Player => player;
    public int MaxAlive => maxAlive;

    public int Alive
    {
        get
        {
            _alive.RemoveAll(IsGone);
            return _alive.Count;
        }
    }

    /// <summary>Live tracked enemies. Destroyed ones are pruned first.</summary>
    public IReadOnlyList<Health> AliveEnemies
    {
        get
        {
            _alive.RemoveAll(IsGone);
            return _alive;
        }
    }

    public bool HasRoom => Alive < maxAlive;

    static readonly Predicate<Health> IsGone = health => health == null;

    readonly List<Health> _alive = new List<Health>();
    readonly List<SpawnPoint> _candidates = new List<SpawnPoint>();
    readonly Dictionary<Health, Action> _deathHandlers = new Dictionary<Health, Action>();

    void Awake()
    {
        if (viewCamera == null)
            viewCamera = Camera.main;
    }

    /// <summary>Spawns at a random valid spawn point. False when there is no room or no point.</summary>
    public bool TrySpawn(GameObject prefab, out Health enemy)
    {
        enemy = null;
        if (prefab == null || !HasRoom || !TryPickPoint(out SpawnPoint point))
            return false;
        return TrySpawnAt(prefab, point.RandomPosition(), out enemy);
    }

    /// <summary>Spawns at a given position, counted against the cap.</summary>
    public bool TrySpawnAt(GameObject prefab, Vector3 position, out Health enemy)
    {
        enemy = null;
        if (prefab == null || !HasRoom)
            return false;

        Vector3 toPlayer = player != null ? player.position - position : Vector3.forward;
        toPlayer.y = 0f;
        Quaternion facing = toPlayer.sqrMagnitude > 1e-4f ? Quaternion.LookRotation(toPlayer) : Quaternion.identity;

        GameObject instance = Instantiate(prefab, position, facing);
        if (!instance.TryGetComponent(out enemy))
        {
            Debug.LogWarning(prefab.name + " has no Health on its root, so it is not counted.", prefab);
            return true;
        }

        Health tracked = enemy;
        Action handler = () => OnDied(tracked);
        _deathHandlers[tracked] = handler;
        tracked.Died += handler;
        _alive.Add(tracked);

        Spawned?.Invoke(tracked);
        return true;
    }

    /// <summary>True when the position is in front of the camera and inside its viewport.</summary>
    public bool IsVisible(Vector3 position)
    {
        if (viewCamera == null)
            return false;
        Vector3 viewport = viewCamera.WorldToViewportPoint(position);
        return viewport.z > 0f && viewport.x >= 0f && viewport.x <= 1f && viewport.y >= 0f && viewport.y <= 1f;
    }

    bool TryPickPoint(out SpawnPoint point)
    {
        _candidates.Clear();
        IReadOnlyList<SpawnPoint> all = SpawnPoint.All;
        float min = minDistance * minDistance;
        float max = maxDistance * maxDistance;

        for (int i = 0; i < all.Count; i++)
        {
            Vector3 position = all[i].transform.position;
            if (player != null)
            {
                float distance = (position - player.position).sqrMagnitude;
                if (distance < min || distance > max)
                    continue;
            }
            if (offScreenOnly && IsVisible(position))
                continue;
            _candidates.Add(all[i]);
        }

        point = _candidates.Count > 0 ? _candidates[UnityEngine.Random.Range(0, _candidates.Count)] : null;
        return point != null;
    }

    void OnDied(Health enemy)
    {
        if (_deathHandlers.TryGetValue(enemy, out Action handler))
        {
            enemy.Died -= handler;
            _deathHandlers.Remove(enemy);
        }
        _alive.Remove(enemy);
        Killed?.Invoke(enemy);
    }
}
```

### Wave spawner

```csharp
using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

[Serializable]
public class WaveGroup
{
    public GameObject prefab;
    [Min(1)] public int count = 5;
    [Tooltip("Seconds between spawns in this group.")]
    [Min(0f)] public float interval = 0.5f;
}

[Serializable]
public class Wave
{
    public WaveGroup[] groups = Array.Empty<WaveGroup>();
}

[Serializable]
public class BudgetEntry
{
    public GameObject prefab;
    [Min(1)] public int cost = 1;
    [Min(0f)] public float weight = 1f;
    [Tooltip("First wave this enemy can appear in, counting from 1.")]
    [Min(1)] public int minWave = 1;
}

/// <summary>
/// Runs waves on an EnemySpawner: authored waves, or waves bought from a growing budget.
/// </summary>
[RequireComponent(typeof(EnemySpawner))]
public class WaveSpawner : MonoBehaviour
{
    public enum WaveMode
    {
        Fixed,
        Budget
    }

    [SerializeField] WaveMode mode = WaveMode.Fixed;
    [SerializeField] float firstWaveDelay = 3f;
    [SerializeField] float timeBetweenWaves = 8f;
    [Tooltip("Seconds before the next wave starts anyway. 0 waits for a clear.")]
    [SerializeField] float maxWaveTime = 0f;

    [Header("Fixed")]
    [SerializeField] Wave[] waves = Array.Empty<Wave>();
    [Tooltip("Count multiplier added for each repeat of the last wave.")]
    [SerializeField] float overflowGrowth = 0.25f;

    [Header("Budget")]
    [SerializeField] BudgetEntry[] entries = Array.Empty<BudgetEntry>();
    [SerializeField] int baseBudget = 10;
    [SerializeField] int budgetPerWave = 5;
    [SerializeField] float spawnInterval = 0.4f;

    public event Action<int> WaveStarted;
    public event Action<int> WaveCleared;

    public int CurrentWave { get; private set; }

    struct SpawnStep
    {
        public GameObject Prefab;
        public float Delay;
    }

    readonly List<SpawnStep> _steps = new List<SpawnStep>();
    readonly List<BudgetEntry> _affordable = new List<BudgetEntry>();
    EnemySpawner _spawner;

    void Awake()
    {
        _spawner = GetComponent<EnemySpawner>();
    }

    void OnEnable()
    {
        CurrentWave = 0;
        StartCoroutine(Run());
    }

    IEnumerator Run()
    {
        yield return new WaitForSeconds(firstWaveDelay);

        while (true)
        {
            CurrentWave++;
            BuildWave(CurrentWave);
            WaveStarted?.Invoke(CurrentWave);
            float started = Time.time;

            for (int i = 0; i < _steps.Count; i++)
            {
                // Wait for room under the cap, and for a valid spawn point.
                while (!_spawner.TrySpawn(_steps[i].Prefab, out _))
                    yield return new WaitForSeconds(0.25f);

                if (_steps[i].Delay > 0f)
                    yield return new WaitForSeconds(_steps[i].Delay);
            }

            while (_spawner.Alive > 0 && (maxWaveTime <= 0f || Time.time - started < maxWaveTime))
                yield return null;

            WaveCleared?.Invoke(CurrentWave);
            yield return new WaitForSeconds(timeBetweenWaves);
        }
    }

    void BuildWave(int wave)
    {
        _steps.Clear();
        if (mode == WaveMode.Fixed)
            BuildFixed(wave);
        else
            BuildBudget(wave);
    }

    void BuildFixed(int wave)
    {
        if (waves.Length == 0)
            return;

        int index = Mathf.Min(wave, waves.Length) - 1;
        int repeats = Mathf.Max(0, wave - waves.Length);
        float multiplier = 1f + overflowGrowth * repeats;

        foreach (WaveGroup group in waves[index].groups)
        {
            if (group.prefab == null)
                continue;
            int count = Mathf.Max(1, Mathf.RoundToInt(group.count * multiplier));
            for (int i = 0; i < count; i++)
                _steps.Add(new SpawnStep { Prefab = group.prefab, Delay = group.interval });
        }
    }

    void BuildBudget(int wave)
    {
        int budget = baseBudget + budgetPerWave * (wave - 1);

        while (true)
        {
            _affordable.Clear();
            float total = 0f;
            foreach (BudgetEntry entry in entries)
            {
                if (entry.prefab == null || entry.minWave > wave || entry.weight <= 0f || Mathf.Max(1, entry.cost) > budget)
                    continue;
                _affordable.Add(entry);
                total += entry.weight;
            }
            if (_affordable.Count == 0)
                break;

            float roll = UnityEngine.Random.value * total;
            BudgetEntry chosen = _affordable[_affordable.Count - 1];
            foreach (BudgetEntry entry in _affordable)
            {
                if (roll < entry.weight)
                {
                    chosen = entry;
                    break;
                }
                roll -= entry.weight;
            }

            _steps.Add(new SpawnStep { Prefab = chosen.prefab, Delay = spawnInterval });
            budget -= Mathf.Max(1, chosen.cost);
        }
    }
}
```

!!! warning "Common pitfalls"

    With **Off Screen Only** on and every spawn point in view, a wave stalls: `TrySpawn` keeps failing. Place points behind the player's usual view, or turn the option off for an arena where the whole floor is on screen.

    An enemy that never dies, such as one stuck outside the map, stops the wave forever. Set **Max Wave Time**, or kill enemies that fall below the level.

    Disabling the wave spawner stops its coroutine, and enabling it starts again from wave 1. Pause waves with `Time.timeScale`, or a flag, not by disabling.

    `WaitForSeconds` uses scaled time. A slow-motion effect also slows the waves, which is usually right. Use `WaitForSecondsRealtime` where it is not.

    Spawning bursts of enemies with `Instantiate` can spike a frame. Pool the enemies with the [object pooling](../architecture/pooling.md) registry, and have the spawner take from the pool instead.
