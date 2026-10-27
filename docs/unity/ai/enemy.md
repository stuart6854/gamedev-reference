---
engine: Unity
version: 6+
package: AI Navigation 2.x
---

# Enemy behaviour

A patrol, chase, attack, search, and flee loop on a `NavMeshAgent`, driven by the [state machine](../architecture/state-machines.md). The attack uses the same [`DamageInfo`](../systems/health.md#damage-info) as a [weapon](../combat/weapons.md). It prefers `Hurtbox.Receive`, and falls back to `IDamageable`.

Sight here is a distance check, an angle check, and one ray. That is a stand-in. The real model is [line of sight and hearing](../../roadmap.md#ai), which is not written yet. A utility score, or a [behaviour tree](../../roadmap.md#ai_1), would replace the predicates on this machine when the set of reasons grows past a list you can read. [Steering](../../roadmap.md#ai) would replace `SetDestination` when the agent's own avoidance is not the local motion you want. None of those are this page.

`NavMeshAgent` is in `UnityEngine.AI`. Baking is the AI Navigation package: `NavMeshSurface` lives in `Unity.AI.Navigation`. The agent's speed property is still `velocity`. Unity 6 renamed `Rigidbody.velocity` to `linearVelocity` and did not rename the agent.

## Setup

1. Install **AI Navigation** 2.x from the Package Manager (Unity Registry). The project needs `com.unity.ai.navigation`.
2. On the walkable ground, add `NavMeshSurface`. Set the agent type to **Humanoid**, include the ground layer, and exclude the enemy. Bake. Do not put the surface on a parent with a negative scale.
3. On the enemy, add a **NavMesh Agent**, a capsule, `Health`, `EnemyMotor`, `PlaceholderSenses`, and `EnemyBrain`. Match the agent's radius and height to the capsule. The motor writes **Stopping Distance** itself (`1.4`).
4. Assign the player as **Target**. Assign a **Damage Type** from the health page. Put a `Hurtbox` on the player if a limb multiplier should run.
5. Drop a few empty transforms into **Waypoints**, in order. An empty list wanders.
6. Copy `StateMachine` from the state machine page before this brain. `EnemyBrain` is a `StateMachineHost`, so the [debug label](../architecture/state-machines.md#debugging) can point at it.

A `NavMeshLink` from the same package is the off-mesh connection. The old `OffMeshLink` component is obsolete. Leave **Auto Traverse Off Mesh Link** on unless you are animating the hop yourself.

## Senses

`CanSee` is true after `Tick` when the target is inside the distance, inside half the view angle, and the ray does not hit a different collider first. A miss (nothing hit) counts as seen. `LostFor` is how long it has been since a successful test, so one frame of a wall does not drop chase.

This component is the piece the perception page replaces. Do not grow hearing, teams, or a memory of several targets onto it.

```csharp
using UnityEngine;

/// <summary>
/// Distance, angle, and one ray. A stand-in for the perception page.
/// </summary>
[DisallowMultipleComponent]
public class PlaceholderSenses : MonoBehaviour
{
    [SerializeField] Transform eyes;
    [SerializeField] float viewDistance = 12f;
    [SerializeField] float viewAngle = 110f;
    [SerializeField] LayerMask blocks = ~0;

    Transform _target;
    float _lostFor;
    bool _seeing;

    public Transform Target => _target;
    public bool CanSee => _seeing;
    public Vector3 LastSeen { get; private set; }

    public float Distance
    {
        get
        {
            if (_target == null)
                return Mathf.Infinity;
            return Vector3.Distance(transform.position, _target.position);
        }
    }

    public void SetTarget(Transform target)
    {
        _target = target;
        _lostFor = Mathf.Infinity;
        _seeing = false;
    }

    public bool LostFor(float seconds)
    {
        return _lostFor >= seconds;
    }

    public void Tick(float dt)
    {
        bool seen = Test();
        if (seen)
        {
            _lostFor = 0f;
            LastSeen = _target.position;
            _seeing = true;
        }
        else
        {
            _lostFor += dt;
            _seeing = false;
        }

        if (eyes != null && _target != null)
        {
            Color colour = _seeing ? Color.green : Color.red;
            Debug.DrawLine(eyes.position, _target.position, colour);
        }
    }

    bool Test()
    {
        if (_target == null)
            return false;

        Transform from = eyes != null ? eyes : transform;
        Vector3 to = _target.position - from.position;
        Vector3 flat = Vector3.ProjectOnPlane(to, Vector3.up);
        if (flat.magnitude > viewDistance || flat.sqrMagnitude < 0.0001f)
            return false;

        Vector3 forward = Vector3.ProjectOnPlane(from.forward, Vector3.up);
        if (Vector3.Angle(forward, flat) > viewAngle * 0.5f)
            return false;

        if (Physics.Raycast(from.position, to.normalized, out RaycastHit hit, to.magnitude, blocks, QueryTriggerInteraction.Ignore))
        {
            if (hit.transform != _target && !hit.transform.IsChildOf(_target))
                return false;
        }

        return true;
    }

    void OnValidate()
    {
        if (viewDistance < 0f)
            viewDistance = 0f;
        if (viewAngle < 0f)
            viewAngle = 0f;
        if (viewAngle > 360f)
            viewAngle = 360f;
    }
}
```

## Motor

`MoveTo` ignores a new point that is still within 0.5 m of the last request and already has a path. Chase calls it on a timer, not every frame. `Arrived` is false while `pathPending` is true, and false while `remainingDistance` is infinite, which is what you get before a path exists. It does not require `hasPath`. The path is cleared once the agent is counted as arrived, so requiring `hasPath` misses the arrival.

`Face` turns `updateRotation` off and slews with the same exponential blend as the controllers. `FacePath` turns it back on. Do not also write `transform.rotation` while `updateRotation` is still true. The two owners fight, and the agent twitches.

`FleeFrom` samples the navmesh. A raw point in the air is not a destination. `SetDestination` false means the point was not near the mesh. The previous path is left alone.

`TickLinks` does nothing while auto-traverse is on. If you turn it off, you have to move the transform and then call `CompleteOffMeshLink`. Forgetting the complete call leaves the agent on the link forever.

```csharp
using UnityEngine;
using UnityEngine.AI;

/// <summary>
/// NavMeshAgent movement for the enemy states. Does not use linearVelocity.
/// </summary>
[DisallowMultipleComponent]
[RequireComponent(typeof(NavMeshAgent))]
public class EnemyMotor : MonoBehaviour
{
    [SerializeField] float stoppingDistance = 1.4f;
    [SerializeField] float repathInterval = 0.25f;
    [SerializeField] float turnSharpness = 12f;
    [SerializeField] float fleeDistance = 8f;

    NavMeshAgent _agent;
    Vector3 _goal;
    float _repathIn;
    bool _hasGoal;

    public float RepathInterval => repathInterval;

    void Awake()
    {
        _agent = GetComponent<NavMeshAgent>();
        _agent.stoppingDistance = stoppingDistance;
        _agent.autoBraking = true;
    }

    void Start()
    {
        if (NavMesh.SamplePosition(transform.position, out NavMeshHit hit, 2f, NavMesh.AllAreas))
            _agent.Warp(hit.position);
        else
            Debug.LogWarning("Enemy is not near a NavMesh.", this);
    }

    public bool Arrived
    {
        get
        {
            if (_agent.pathPending)
                return false;
            if (float.IsInfinity(_agent.remainingDistance))
                return false;
            return _agent.remainingDistance <= _agent.stoppingDistance;
        }
    }

    public void MoveTo(Vector3 point)
    {
        if (_hasGoal && _agent.hasPath && (_goal - point).sqrMagnitude < 0.25f)
            return;

        _goal = point;
        _hasGoal = true;
        _agent.SetDestination(point);
    }

    public void Chase(Vector3 point, float dt)
    {
        _repathIn -= dt;
        if (_repathIn > 0f)
            return;
        _repathIn = repathInterval;
        MoveTo(point);
    }

    public bool Wander(float radius)
    {
        Vector3 offset = Random.insideUnitSphere * radius;
        offset.y = 0f;
        Vector3 candidate = transform.position + offset;
        if (!NavMesh.SamplePosition(candidate, out NavMeshHit hit, 2f, NavMesh.AllAreas))
            return false;
        MoveTo(hit.position);
        return true;
    }

    public bool FleeFrom(Transform threat)
    {
        Vector3 away = threat != null ? transform.position - threat.position : transform.forward;
        away.y = 0f;
        if (away.sqrMagnitude < 0.0001f)
            away = transform.forward;
        away.Normalize();

        Vector3 candidate = transform.position + away * fleeDistance;
        if (!NavMesh.SamplePosition(candidate, out NavMeshHit hit, 2f, NavMesh.AllAreas))
            return false;
        MoveTo(hit.position);
        return true;
    }

    public void Face(Vector3 worldPoint, float dt)
    {
        _agent.updateRotation = false;
        Vector3 flat = worldPoint - transform.position;
        flat.y = 0f;
        if (flat.sqrMagnitude < 0.0001f)
            return;

        Quaternion want = Quaternion.LookRotation(flat);
        float blend = 1f - Mathf.Exp(-turnSharpness * dt);
        transform.rotation = Quaternion.Slerp(transform.rotation, want, blend);
    }

    public void FacePath()
    {
        _agent.updateRotation = true;
    }

    public void Stop()
    {
        _agent.isStopped = true;
    }

    public void Resume()
    {
        _agent.isStopped = false;
    }

    public void TickLinks()
    {
        if (!_agent.isOnOffMeshLink || _agent.autoTraverseOffMeshLink)
            return;

        _agent.CompleteOffMeshLink();
    }
}
```

`TickLinks` completing a link it did not animate is only a safety net for the flag being off with no custom hop. Prefer leaving auto-traverse on.

## Brain

Flee is an any-state rule at priority `100`, and only while the target is inside the fear distance. A hurt enemy across the map does not run. Chase gives up after the senses have been wrong for `0.4` s, then search walks to `LastSeen`, waits, and patrols. Attack stops the agent so it does not orbit inside the stopping distance. The attack range is a little larger than that distance, or the agent brakes and never enters range.

Low health leaves attack through the any-state rule, which runs `Exit` and clears `isStopped`. The next state can path again.

```csharp
using UnityEngine;

/// <summary>
/// Patrol, chase, attack, search, and flee. Copy StateMachine first.
/// </summary>
[DisallowMultipleComponent]
[DefaultExecutionOrder(100)]
[RequireComponent(typeof(EnemyMotor))]
[RequireComponent(typeof(PlaceholderSenses))]
public class EnemyBrain : StateMachineHost
{
    [SerializeField] Transform target;
    [SerializeField] Health health;
    [SerializeField] DamageType damageType;
    [SerializeField] Transform[] waypoints = System.Array.Empty<Transform>();
    [SerializeField] float attackRange = 1.8f;
    [SerializeField] float attackDamage = 10f;
    [SerializeField] float attackCooldown = 1f;
    [SerializeField] float fearDistance = 14f;
    [SerializeField] float fleeFraction = 0.3f;
    [SerializeField] float wanderRadius = 8f;
    [SerializeField] bool logTransitions;

    EnemyMotor _motor;
    PlaceholderSenses _senses;
    StateMachine _machine;
    EnemyContext _context;

    public override StateMachine Machine => _machine;

    void Awake()
    {
        _motor = GetComponent<EnemyMotor>();
        _senses = GetComponent<PlaceholderSenses>();
        if (health == null)
            health = GetComponent<Health>();
        _senses.SetTarget(target);
    }

    void Start()
    {
        _context = new EnemyContext(this, _motor, _senses, health, waypoints);
        var patrol = new PatrolState(_context);
        var chase = new ChaseState(_context);
        var attack = new AttackState(_context);
        var search = new SearchState(_context);
        var flee = new FleeState(_context);

        _machine = new StateMachine("Enemy");
        _machine.SetLog(this, logTransitions);
        _machine.AddAnyTransition(flee, () => _context.LowHealth && _senses.Distance <= fearDistance, 100);
        _machine.AddTransition(flee, patrol, () => !_context.LowHealth || _senses.Distance > fearDistance, 50);
        _machine.AddTransition(chase, search, () => _senses.LostFor(0.4f), 40);
        _machine.AddTransition(attack, search, () => _senses.LostFor(0.4f), 40);
        _machine.AddTransition(chase, attack, () => _senses.Distance <= attackRange, 30);
        _machine.AddTransition(attack, chase, () => _senses.Distance > attackRange, 30);
        _machine.AddTransition(patrol, chase, () => _senses.CanSee, 20);
        _machine.AddTransition(search, chase, () => _senses.CanSee, 20);
        _machine.AddTransition(search, patrol, () => search.Finished, 10);
        _machine.SetInitial(patrol);
        _machine.Enter();
    }

    void Update()
    {
        if (_machine == null)
            return;
        if (health != null && health.IsDead)
        {
            _motor.Stop();
            return;
        }

        _senses.Tick(Time.deltaTime);
        _motor.TickLinks();
        _machine.Tick(Time.deltaTime);
    }

    public void Strike()
    {
        if (target == null || attackDamage <= 0f)
            return;

        Vector3 toTarget = target.position - transform.position;
        var info = new DamageInfo
        {
            Amount = attackDamage,
            Type = damageType,
            Source = this,
            Point = target.position,
            Normal = toTarget.sqrMagnitude > 0.0001f ? toTarget.normalized : transform.forward
        };

        Hurtbox hurtbox = target.GetComponentInChildren<Hurtbox>();
        if (hurtbox != null)
        {
            hurtbox.Receive(info);
            return;
        }

        IDamageable damageable = target.GetComponentInParent<IDamageable>();
        if (damageable != null)
            damageable.ApplyDamage(info);
    }

    sealed class EnemyContext
    {
        public readonly EnemyBrain Brain;
        public readonly EnemyMotor Motor;
        public readonly PlaceholderSenses Senses;
        public readonly Health Health;
        public readonly Transform[] Waypoints;

        public EnemyContext(EnemyBrain brain, EnemyMotor motor, PlaceholderSenses senses, Health health, Transform[] waypoints)
        {
            Brain = brain;
            Motor = motor;
            Senses = senses;
            Health = health;
            Waypoints = waypoints;
        }

        public Transform Target => Senses.Target;

        public bool LowHealth
        {
            get
            {
                if (Health == null || Health.Max <= 0f)
                    return false;
                return Health.Current / Health.Max <= Brain.fleeFraction;
            }
        }
    }

    sealed class PatrolState : NamedState
    {
        readonly EnemyContext _context;
        int _index;
        float _wait;
        bool _waiting;

        public PatrolState(EnemyContext context)
            : base("Patrol")
        {
            _context = context;
        }

        public override void Enter()
        {
            _context.Motor.Resume();
            _context.Motor.FacePath();
            _waiting = false;
            GoNext();
        }

        public override void Tick(float dt)
        {
            if (!_waiting)
            {
                if (!_context.Motor.Arrived)
                    return;
                _waiting = true;
                _wait = 0.6f;
                return;
            }

            _wait -= dt;
            if (_wait > 0f)
                return;
            _waiting = false;
            GoNext();
        }

        void GoNext()
        {
            Transform[] points = _context.Waypoints;
            if (points != null && points.Length > 0)
            {
                int guard = 0;
                while (guard < points.Length)
                {
                    Transform point = points[_index % points.Length];
                    _index++;
                    guard++;
                    if (point == null)
                        continue;
                    _context.Motor.MoveTo(point.position);
                    return;
                }
            }

            _context.Motor.Wander(_context.Brain.wanderRadius);
        }
    }

    sealed class ChaseState : NamedState
    {
        readonly EnemyContext _context;

        public ChaseState(EnemyContext context)
            : base("Chase")
        {
            _context = context;
        }

        public override void Enter()
        {
            _context.Motor.Resume();
        }

        public override void Tick(float dt)
        {
            Transform target = _context.Target;
            if (target == null)
                return;
            _context.Motor.Face(target.position, dt);
            _context.Motor.Chase(target.position, dt);
        }
    }

    sealed class AttackState : NamedState
    {
        readonly EnemyContext _context;
        float _cooldown;

        public AttackState(EnemyContext context)
            : base("Attack")
        {
            _context = context;
        }

        public override void Enter()
        {
            _context.Motor.Stop();
            _cooldown = 0f;
        }

        public override void Exit()
        {
            _context.Motor.Resume();
        }

        public override void Tick(float dt)
        {
            Transform target = _context.Target;
            if (target == null)
                return;

            _context.Motor.Face(target.position, dt);
            _cooldown -= dt;
            if (_cooldown > 0f)
                return;

            _cooldown = _context.Brain.attackCooldown;
            _context.Brain.Strike();
        }
    }

    sealed class SearchState : NamedState
    {
        readonly EnemyContext _context;
        float _wait;
        bool _waiting;

        public SearchState(EnemyContext context)
            : base("Search")
        {
            _context = context;
        }

        public bool Finished => _waiting && _wait <= 0f;

        public override void Enter()
        {
            _context.Motor.Resume();
            _context.Motor.FacePath();
            _waiting = false;
            _wait = 1.5f;
            _context.Motor.MoveTo(_context.Senses.LastSeen);
        }

        public override void Tick(float dt)
        {
            if (!_waiting)
            {
                if (_context.Motor.Arrived)
                    _waiting = true;
                return;
            }

            _wait -= dt;
        }
    }

    sealed class FleeState : NamedState
    {
        readonly EnemyContext _context;

        public FleeState(EnemyContext context)
            : base("Flee")
        {
            _context = context;
        }

        public override void Enter()
        {
            _context.Motor.Resume();
            _context.Motor.FacePath();
            _context.Motor.FleeFrom(_context.Target);
        }

        public override void Tick(float dt)
        {
            if (_context.Motor.Arrived)
                _context.Motor.FleeFrom(_context.Target);
        }
    }
}
```

Put **Eyes** on a child at head height. An empty eyes slot uses the agent transform, which is often the feet, and the cone then looks along the ground.

Runtime geometry calls `BuildNavMesh` once, not per frame. The inspector **Bake** button is the usual path. This component is only for a floor that appears later.

```csharp
using Unity.AI.Navigation;
using UnityEngine;

/// <summary>
/// Rebuilds one surface. Do not call this from Update.
/// </summary>
public class NavMeshRebuild : MonoBehaviour
{
    [SerializeField] NavMeshSurface surface;

    public void Rebuild()
    {
        if (surface != null)
            surface.BuildNavMesh();
    }
}
```

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| View Distance | `12` | Metres. Past this the placeholder cannot see. |
| View Angle | `110` | Full cone, in degrees. The test uses half of it. |
| Stopping Distance | `1.4` | Written onto the agent in `Awake`. |
| Attack Range | `1.8` | Metres. Slightly past the stopping distance so a braked agent can still strike. |
| Attack Cooldown | `1` | Seconds between `DamageInfo`s. |
| Flee Fraction | `0.3` | `Current / Max` at or below this, and inside the fear distance, flees. |
| Fear Distance | `14` | A hurt enemy farther away than this stays on patrol. |
| Repath Interval | `0.25` | Seconds between chase destinations. |
| Wander Radius | `8` | Metres, then `NavMesh.SamplePosition`. |

## Pitfalls

!!! warning "Common pitfalls"

    `SetDestination` every frame throws the path away before the agent can settle. Chase waits for the repath interval, and `MoveTo` ignores a point that has not moved by half a metre.

    `remainingDistance` is meaningless while `pathPending` is true, and it is infinite until a path exists. `Arrived` bails out on both. Requiring `hasPath` as well misses the frame the agent arrives and clears the path.

    Stopping distance `0` makes the agent orbit the player. Attack range has to be at least that distance, and attack sets `isStopped` so avoidance does not shove the body in and out of range. `Exit` clears `isStopped`. Leaving it set freezes the next patrol.

    `updateRotation` and a scripted `transform.rotation` must not both run. `Face` turns the agent flag off. `FacePath` turns it on. A state that faces the player has to turn the flag off again in `Tick`, not only in `Enter`, because the previous state turned it on.

    `NavMesh.SamplePosition` failing means the wander or flee point is not used. Do not pass the unsampled point to `SetDestination`. A spawn that is not within 2 m of the mesh logs a warning and will not move. Bake the surface, and do not scale its parent by a negative number.

    An off-mesh link with auto-traverse off waits until `CompleteOffMeshLink`. `TickLinks` completes it immediately, which skips a custom hop. Leave auto-traverse on unless you are moving the body yourself and then completing.

    The agent's `velocity` is not `linearVelocity`. That rename is the Rigidbody.

    `BuildNavMesh` stalls the frame. Bake in the editor, or call it when the level actually changes. A wall placed at runtime is [building](../systems/building.md#navigation-mesh). Prefer a `NavMeshObstacle` that carves. `UpdateNavMesh` is the other option, and it is not a per-frame call.

    The sight component is one ray and a cone. It will see through a gap the size of the ray, and it has no hearing. Replace the component when the [perception](../../roadmap.md#ai) page exists. Do not add those rules here.

    A behaviour tree or a utility score replaces this machine when the priority numbers become a puzzle. Steering replaces the motor, not the states. Those three stay on the [roadmap](../../roadmap.md#ai). Behaviour trees are the Ideas entry on that list.

    Copy `StateMachine` before `EnemyBrain`, or the brain does not compile. `Health` with no assignment never flees. A missing `Hurtbox` still applies damage through `IDamageable`, and skips limb multipliers. Do not call both.

    A dead `Health` stops the machine and the agent. Do not `Destroy` the body inside `Died` before other listeners run. The health page has the same warning.
