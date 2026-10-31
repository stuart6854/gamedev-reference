---
engine: Unity
version: 6+
uses:
  - name: Top-down survival
    text: Searching, bandaging, crafting, and barricading as progress bars that walking slows or cancels.
  - name: Base building
    text: Construction that takes time, queued piece by piece, and stops when the builder is hit.
  - name: Life and colony sims
    text: A queue of chores a character works through, cancelled from the front or cleared.
---

# Timed actions

Actions that take time: search a container, bandage a wound, craft a tool, barricade a window. Each shows a progress bar, can be queued behind others, and has rules for what interrupts it. Searching stops if the player walks away. Bandaging while walking is allowed, but slower. Taking a hit cancels most things. An `ActionRunner` on the character runs one action at a time from a queue.

## Rules per action

| Setting | Options |
| --- | --- |
| **While moving** | **Cancel**: moving stops the action. **Slow**: progress runs at a fraction. **Allow**: no effect. |
| **On damage** | Cancel, or carry on. |
| **Valid** | A check every frame, such as "the container is still within reach". When it fails, the action is cancelled. |
| **Duration** | Seconds, divided by the actor's action speed, so skills and modifiers shorten it. |

## Action

```csharp
using UnityEngine;

public enum MovePolicy { Cancel, Slow, Allow }

/// <summary>
/// One timed action. Subclass it, or use DelegateAction for simple cases.
/// </summary>
public abstract class TimedAction
{
    public abstract string Name { get; }
    /// <summary>Seconds at action speed 1.</summary>
    public abstract float Duration { get; }

    public virtual MovePolicy WhileMoving => MovePolicy.Cancel;
    public virtual float MovingRate => 0.5f;   // progress rate with MovePolicy.Slow
    public virtual bool CancelOnDamage => true;
    /// <summary>Animator state to play while acting, or empty.</summary>
    public virtual string AnimationState => string.Empty;

    /// <summary>Checked before starting. False skips the action.</summary>
    public virtual bool CanStart(ActionRunner actor) => true;
    /// <summary>Checked every frame while running. False cancels it.</summary>
    public virtual bool IsValid(ActionRunner actor) => true;

    public virtual void OnStart(ActionRunner actor) { }
    public virtual void OnTick(ActionRunner actor, float progress) { }
    public abstract void OnComplete(ActionRunner actor);
    public virtual void OnCancel(ActionRunner actor) { }
}
```

## Runner

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Runs a character's timed actions one at a time, from a queue.
/// </summary>
public class ActionRunner : MonoBehaviour
{
    [SerializeField] Health health;
    [Tooltip("Optional. Divides every duration: 1.25 makes actions 25% quicker.")]
    [SerializeField] StatSheet stats;
    [SerializeField] StatDefinition actionSpeed;
    [Tooltip("Speed above which the character counts as moving, in metres per second.")]
    [SerializeField] float movingThreshold = 0.3f;
    [Tooltip("Damage of these types never cancels actions: hunger, bleeding, and other damage over time.")]
    [SerializeField] DamageType[] ignoredDamage = Array.Empty<DamageType>();

    readonly LinkedList<TimedAction> _queue = new LinkedList<TimedAction>();
    Vector3 _lastPosition;

    public TimedAction Current { get; private set; }
    /// <summary>0 to 1.</summary>
    public float Progress { get; private set; }
    public bool IsBusy => Current != null;
    public int Queued => _queue.Count;

    public event Action<TimedAction> Started;
    public event Action<TimedAction, float> Ticked;
    public event Action<TimedAction> Completed;
    public event Action<TimedAction> Cancelled;

    void OnEnable()
    {
        _lastPosition = transform.position;
        if (health != null)
            health.Damaged += OnDamaged;
    }

    void OnDisable()
    {
        if (health != null)
            health.Damaged -= OnDamaged;
        CancelAll();
    }

    /// <summary>Clears the queue, cancels the current action, and starts this one.</summary>
    public void Do(TimedAction action)
    {
        CancelAll();
        Enqueue(action);
    }

    /// <summary>Adds to the end of the queue, as Shift-click does.</summary>
    public void Enqueue(TimedAction action)
    {
        if (action == null)
            return;
        _queue.AddLast(action);
        if (Current == null)
            StartNext();
    }

    public void CancelCurrent()
    {
        if (Current == null)
            return;
        TimedAction action = Current;
        Current = null;
        Progress = 0f;
        action.OnCancel(this);
        Cancelled?.Invoke(action);
        StartNext();
    }

    public void CancelAll()
    {
        _queue.Clear();
        CancelCurrent();
    }

    void Update()
    {
        float dt = Time.deltaTime;
        float speed = dt > 0f ? (transform.position - _lastPosition).magnitude / dt : 0f;
        _lastPosition = transform.position;

        if (Current == null)
            return;

        if (!Current.IsValid(this))
        {
            CancelCurrent();
            return;
        }

        float rate = 1f;
        if (speed > movingThreshold)
        {
            switch (Current.WhileMoving)
            {
                case MovePolicy.Cancel:
                    CancelAll(); // walking away abandons the plan, not only the current step
                    return;
                case MovePolicy.Slow:
                    rate = Current.MovingRate;
                    break;
            }
        }

        float duration = Mathf.Max(0.01f, Current.Duration / ActionSpeed());
        Progress = Mathf.Min(1f, Progress + dt * rate / duration);
        Current.OnTick(this, Progress);
        Ticked?.Invoke(Current, Progress);

        if (Progress >= 1f)
        {
            TimedAction done = Current;
            Current = null;
            Progress = 0f;
            done.OnComplete(this);
            Completed?.Invoke(done);
            StartNext();
        }
    }

    void StartNext()
    {
        while (Current == null && _queue.Count > 0)
        {
            TimedAction next = _queue.First.Value;
            _queue.RemoveFirst();
            if (!next.CanStart(this))
                continue;

            Current = next;
            Progress = 0f;
            next.OnStart(this);
            Started?.Invoke(next);
        }
    }

    void OnDamaged(DamageInfo info, float amount)
    {
        if (Current == null || !Current.CancelOnDamage || Array.IndexOf(ignoredDamage, info.Type) >= 0)
            return;
        CancelAll();
    }

    float ActionSpeed()
    {
        if (stats != null && actionSpeed != null && stats.TryGet(actionSpeed, out Stat stat))
            return Mathf.Max(0.1f, stat.Value);
        return 1f;
    }
}
```

- Moving is measured from the position, so the runner works with any [controller](../mechanics/controllers/index.md), and with a `NavMeshAgent` walking the character to the next action.
- **Cancel** on move clears the queue. A player who walks off mid-search has changed their mind about the whole plan.
- `CanStart` is checked when the action reaches the front, not when it is queued. A queued "eat" with no food left is skipped.
- `Stat.Value` and `StatSheet.TryGet` are from [stats](health.md#stats). An `ActionSpeed` stat with a base of 1, raised by skills or a tool, shortens every action.
- Damage arrives through `Health.Damaged`, from [health](health.md). Damage over time, such as starving or [bleeding](needs.md#effects), arrives the same way. List its damage types in **Ignored Damage**, or a bleeding character can never finish bandaging.

## Actions

A simple action needs no class of its own:

```csharp
using System;

public sealed class DelegateAction : TimedAction
{
    readonly string _name;
    readonly float _duration;
    readonly MovePolicy _moving;
    readonly Action<ActionRunner> _complete;
    readonly Func<ActionRunner, bool> _valid;

    public DelegateAction(string name, float duration, Action<ActionRunner> complete,
        MovePolicy moving = MovePolicy.Cancel, Func<ActionRunner, bool> valid = null)
    {
        _name = name;
        _duration = duration;
        _complete = complete;
        _moving = moving;
        _valid = valid;
    }

    public override string Name => _name;
    public override float Duration => _duration;
    public override MovePolicy WhileMoving => _moving;
    public override bool IsValid(ActionRunner actor) => _valid == null || _valid(actor);
    public override void OnComplete(ActionRunner actor) => _complete?.Invoke(actor);
}
```

A bandage that stops bleeding, allowed while walking at half speed:

```csharp
using UnityEngine;

public sealed class BandageAction : TimedAction
{
    readonly ItemDefinition _bandage;

    public BandageAction(ItemDefinition bandage) => _bandage = bandage;

    public override string Name => "Bandage";
    public override float Duration => 3f;
    public override MovePolicy WhileMoving => MovePolicy.Slow;
    public override string AnimationState => "Bandage";

    public override bool CanStart(ActionRunner actor) =>
        actor.TryGetComponent(out ListInventory bag) && bag.Contains(_bandage);

    public override void OnComplete(ActionRunner actor)
    {
        // Spend the bandage only on completion, so a cancelled bandage costs nothing.
        if (!actor.TryGetComponent(out ListInventory bag) || !bag.TryRemove(_bandage, 1, out _))
            return;
        if (actor.TryGetComponent(out Effects effects))
            effects.RemoveTag("Bleeding");
    }
}
```

`Effects` and its tags are on [needs and effects](needs.md#effects). Searching a container is on [containers](inventory/containers.md#searching).

## Progress bar and animation

```csharp
// A world-space bar over the character, from the runner's events.
void OnEnable()
{
    runner.Started += a => { bar.gameObject.SetActive(true); label.text = a.Name; };
    runner.Ticked += (a, p) => bar.fillAmount = p;
    runner.Completed += _ => bar.gameObject.SetActive(false);
    runner.Cancelled += _ => bar.gameObject.SetActive(false);
}
```

Use named methods instead of lambdas if the bar ever unsubscribes, as the [lifecycle](../architecture/lifecycle.md#subscribe-in-onenable-unsubscribe-in-ondisable) pattern does. For animation, start `AnimationState` on the upper-body layer through the [character animator](../animation/scripting.md#one-owner) on `Started`, and return to locomotion on `Completed` and `Cancelled`. The upper body bandages while the legs keep walking.

## Queues and the command pattern

The runner is the order queue from the [command pattern](../architecture/commands.md#queues) page, for one character. Its actions are not undoable: a finished search cannot be un-searched. Keep timed actions and the undo history separate.

For an AI character, the brain enqueues actions instead of calling methods directly: walk to the crate, search it, walk to the bed, sleep. Utility AI scores which [action](../ai/utility.md) to queue next when the queue empties.

## Saving

An action in progress is not saved. On load, characters are idle. Either block saving while busy, with [`SaveManager.BlockSaving`](saving/save-system.md#manager) on `Started` and `UnblockSaving` on `Completed` and `Cancelled`, or accept that a half-finished bandage restarts.

!!! warning "Common pitfalls"

    Spending the item when the action starts loses it when the action is cancelled. Spend on completion.

    Checking `CanStart` only when queueing lets a queued action run after its item is gone. The runner checks again at the front.

    Moving measured from input, not position, misses a character pushed by a zombie. Measure the body.

    An action with no `IsValid` keeps searching a container the player has walked ten metres from. Check reach every frame.

    Lambdas subscribed to the runner's events cannot be removed. Use methods when the listener can be destroyed before the runner.
