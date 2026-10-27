---
engine: Unity
version: 6+
---

# State machines

A small set of named situations, and the rules for leaving one. Idle, move, jump, and fall are that kind of set. So is patrol, chase, and flee on the [enemy](../ai/enemy.md) page. An [attack combo](../../roadmap.md#combat) will be another user of this machine. It is not written yet.

The [character controller](../mechanics/character-movement.md) still moves the body. This page only classifies what that motion is doing. The same four names apply to [Rigidbody movement](../mechanics/rigidbody-movement.md) and the [2D platformer](../mechanics/platformer-2d.md). Those bodies publish `linearVelocity`. The capsule publishes `CharacterController.velocity`, which Unity 6 did not rename.

## Which shape

| Shape | Use it when | Limit |
| --- | --- | --- |
| Enum and `switch` | Two or three states, and the script will not grow. | Every new state is another arm in every switch. An any-state rule is copy-pasted into each arm. |
| `IState` and `StateMachine` | The names are reused, or you want Enter and Exit in one place. | You write the predicates. A predicate that writes state will fight the next check. |
| Nested machine | A phase has its own phases. Air contains jump and fall. | Leaving the outer state exits the inner one. It does not remember it. |
| Pushdown stack | Pause, stun, or a modal that must return to the same jump. | `Time.timeScale = 0` also stops the tick that would pop, unless that tick uses unscaled time. |
| Animator `StateMachineBehaviour` | The state is a blend, a clip, or root motion the Animator already cross-fades. | Two states run during a transition. It is a second machine, not a replacement for this one. |

## Setup

1. On the same object as `CharacterMovement`, add `PlayerPose` and `PlayerStateDriver`. Leave **Pose** empty and the driver finds the pose.
2. Do not add `PlayerStateEnum` as well. That script is the version the machine replaces.
3. Add `StateDebugLabel` to a uGUI `Text` if you want the name on screen. **Log Transitions** on the driver prints `Idle -> Move` in the Console.
4. Call `Pause` and `Resume` from a menu. The sample does not read a key, so it does not fight the controller's input.
5. The body still needs the controller from the movement page. This driver never calls `Move`.

## Pose

`CharacterMovement` keeps `_grounded` and `_verticalSpeed` private, and it should. The pose reads the capsule after that script has moved. Put the driver at execution order `100`, and leave the controller at the default `0`, so the pose sees this frame's `Move`.

`CharacterController.isGrounded` is only updated by `Move`, and it can disagree with the controller page's own probe for a frame. The stick-to-ground speed is downward while the body is still grounded, so do not treat a negative vertical speed on its own as a fall. The fall rule requires the capsule to be ungrounded as well.

A `Rigidbody` pose uses `linearVelocity`, not `velocity`. A `Rigidbody2D` pose uses `linearVelocity.y` and `Mathf.Abs(linearVelocity.x)`. Grounded on those bodies is the probe from their own page, not `isGrounded`.

```csharp
using UnityEngine;

/// <summary>
/// Numbers the locomotion states read. The controller still moves the body.
/// </summary>
[DisallowMultipleComponent]
[RequireComponent(typeof(CharacterController))]
public class PlayerPose : MonoBehaviour
{
    [SerializeField] float moveThreshold = 0.2f;

    CharacterController _controller;

    public float MoveThreshold => moveThreshold;

    public bool Grounded => _controller != null && _controller.isGrounded;

    public float VerticalSpeed => _controller != null ? _controller.velocity.y : 0f;

    public float HorizontalSpeed
    {
        get
        {
            if (_controller == null)
                return 0f;
            Vector3 velocity = _controller.velocity;
            velocity.y = 0f;
            return velocity.magnitude;
        }
    }

    void Awake()
    {
        _controller = GetComponent<CharacterController>();
    }
}
```

## Enum and switch

This is the whole design while the set is tiny. Nothing forces an `Enter` or an `Exit`. A fifth state means another arm, and the air rule is already copied. The machine below is the replacement. Do not keep both components.

```csharp
using UnityEngine;

/// <summary>
/// The switch this page replaces. Shown so the duplication is visible.
/// </summary>
[DisallowMultipleComponent]
public class PlayerStateEnum : MonoBehaviour
{
    enum Stance
    {
        Idle,
        Move,
        Jump,
        Fall
    }

    [SerializeField] PlayerPose pose;

    Stance _state = Stance.Idle;

    void Awake()
    {
        if (pose == null)
            pose = GetComponent<PlayerPose>();
    }

    void Update()
    {
        if (pose == null)
            return;

        Stance next = _state;
        switch (_state)
        {
            case Stance.Idle:
                next = AirOr(_state, Stance.Move, pose.HorizontalSpeed > pose.MoveThreshold);
                break;
            case Stance.Move:
                next = AirOr(_state, Stance.Idle, pose.HorizontalSpeed <= pose.MoveThreshold);
                break;
            case Stance.Jump:
                if (pose.Grounded)
                    next = pose.HorizontalSpeed > pose.MoveThreshold ? Stance.Move : Stance.Idle;
                else if (pose.VerticalSpeed <= 0.05f)
                    next = Stance.Fall;
                break;
            case Stance.Fall:
                if (pose.Grounded)
                    next = pose.HorizontalSpeed > pose.MoveThreshold ? Stance.Move : Stance.Idle;
                break;
        }

        _state = next;
    }

    Stance AirOr(Stance stay, Stance groundedAlternative, bool groundedAlternativeWhen)
    {
        if (!pose.Grounded && pose.VerticalSpeed > 0.05f)
            return Stance.Jump;
        if (!pose.Grounded)
            return Stance.Fall;
        return groundedAlternativeWhen ? groundedAlternative : stay;
    }
}
```

The air rule is already copied into two arms. That copy is the bug this page is about.

## State machine

Transitions live in one list. `From` null means any state. A higher `priority` is tested first. The same priority keeps registration order. The first predicate that returns true wins, and a transition whose target is already current is ignored, so an any-state rule does not re-enter.

`Tick` decides, then ticks the state that won. `FixedTick` does not decide again, or a transition would fire twice in one frame. `Enter` and `Exit` are guarded. A predicate that itself calls a transition is ignored and a warning is logged. Predicates only read.

A machine is an `IState`. That is the nest. `Exit` on the outer machine exits the inner state. `Suspend` does not. Pause needs suspend. Build the graph once in `Start`. A lambda created there is one allocation, not one per frame.

`StateMachineHost` is the component base the [enemy](../ai/enemy.md) reuses. The gizmo label is the leaf name, so a nest reads `Jump` rather than `Locomotion`.

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

public interface IState
{
    string Name { get; }
    void Enter();
    void Tick(float dt);
    void FixedTick(float dt);
    void Exit();
}

/// <summary>
/// Pause and stun call these. Exit plus Enter would restart the state underneath.
/// </summary>
public interface ISuspendable
{
    void Suspend();
    void Resume();
}

/// <summary>
/// A state that only needs a name. Locomotion ticks live in the controller.
/// </summary>
public class NamedState : IState
{
    public NamedState(string name)
    {
        Name = name;
    }

    public string Name { get; }

    public virtual void Enter() { }
    public virtual void Tick(float dt) { }
    public virtual void FixedTick(float dt) { }
    public virtual void Exit() { }
}

/// <summary>
/// Predicate transitions, including any-state. Also a state, so it can nest.
/// </summary>
public class StateMachine : IState, ISuspendable
{
    sealed class Transition
    {
        public IState From;
        public IState To;
        public Func<bool> When;
        public int Priority;
        public int Order;
    }

    readonly List<Transition> _transitions = new List<Transition>();
    IState _current;
    IState _initial;
    UnityEngine.Object _logOwner;
    int _order;
    bool _changing;
    bool _suspended;
    bool _log;

    public StateMachine(string name)
    {
        Name = name;
    }

    public string Name { get; }
    public IState Current => _current;
    public event Action<IState, IState> Changed;

    public string CurrentName
    {
        get
        {
            if (_current is StateMachine nested)
                return nested.CurrentName;
            return _current != null ? _current.Name : "(none)";
        }
    }

    public void SetLog(UnityEngine.Object owner, bool enabled)
    {
        _logOwner = owner;
        _log = enabled;
    }

    public void SetInitial(IState state)
    {
        _initial = state;
    }

    public void AddTransition(IState from, IState to, Func<bool> when, int priority = 0)
    {
        Add(from, to, when, priority);
    }

    public void AddAnyTransition(IState to, Func<bool> when, int priority = 0)
    {
        Add(null, to, when, priority);
    }

    public virtual void Enter()
    {
        if (_current != null || _initial == null)
            return;
        ChangeTo(_initial);
    }

    public virtual void Exit()
    {
        _changing = true;
        _current?.Exit();
        _current = null;
        _changing = false;
        _suspended = false;
    }

    public virtual void Tick(float dt)
    {
        if (_suspended || _current == null)
            return;

        Evaluate();
        if (_current != null)
            _current.Tick(dt);
    }

    public virtual void FixedTick(float dt)
    {
        if (_suspended || _current == null)
            return;
        _current.FixedTick(dt);
    }

    public virtual void Suspend()
    {
        _suspended = true;
    }

    public virtual void Resume()
    {
        _suspended = false;
    }

    void IState.Enter() => Enter();
    void IState.Tick(float dt) => Tick(dt);
    void IState.FixedTick(float dt) => FixedTick(dt);
    void IState.Exit() => Exit();

    void Add(IState from, IState to, Func<bool> when, int priority)
    {
        if (to == null || when == null)
            return;

        _transitions.Add(new Transition
        {
            From = from,
            To = to,
            When = when,
            Priority = priority,
            Order = _order
        });
        _order++;
        _transitions.Sort(Compare);
    }

    static int Compare(Transition a, Transition b)
    {
        int priority = b.Priority.CompareTo(a.Priority);
        if (priority != 0)
            return priority;
        return a.Order.CompareTo(b.Order);
    }

    void Evaluate()
    {
        if (_changing)
            return;

        for (int i = 0; i < _transitions.Count; i++)
        {
            Transition transition = _transitions[i];
            if (transition.From != null && transition.From != _current)
                continue;
            if (transition.To == _current)
                continue;
            if (!transition.When())
                continue;

            ChangeTo(transition.To);
            return;
        }
    }

    void ChangeTo(IState next)
    {
        if (next == null || next == _current)
            return;
        if (_changing)
        {
            Debug.LogWarning("Ignored a transition during Enter or Exit.", _logOwner);
            return;
        }

        IState previous = _current;
        _changing = true;
        if (_current != null)
            _current.Exit();
        _current = next;
        _current.Enter();
        _changing = false;

        if (_log)
        {
            string from = previous != null ? previous.Name : "(none)";
            Debug.Log(Name + ": " + from + " -> " + next.Name, _logOwner);
        }

        Changed?.Invoke(previous, next);
    }
}

/// <summary>
/// A behaviour that owns one machine. The debug label and the gizmo read it.
/// </summary>
public abstract class StateMachineHost : MonoBehaviour
{
    public abstract StateMachine Machine { get; }

    public virtual string Label => Machine != null ? Machine.CurrentName : "(none)";

#if UNITY_EDITOR
    void OnDrawGizmosSelected()
    {
        if (!Application.isPlaying)
            return;
        UnityEditor.Handles.Label(transform.position + Vector3.up * 2f, Label);
    }
#endif
}
```

## Player

Air is a nested machine. Its `Enter` picks jump or fall from the vertical speed, so a walk off a ledge does not flash the jump state. Landing transitions outrank the any-state rule that enters air. Ground speed transitions sit at priority `0`, so they never steal an airborne frame.

These states do not move the capsule. A combo state, when that page exists, would be a sibling of locomotion and would tick its own window. It should not grow another switch inside `CharacterMovement`.

```csharp
using UnityEngine;

/// <summary>
/// Air picks jump or fall when the outer machine enters it.
/// </summary>
public class AirStates : StateMachine
{
    readonly PlayerPose _pose;
    readonly IState _jump;
    readonly IState _fall;

    public AirStates(PlayerPose pose, IState jump, IState fall)
        : base("Air")
    {
        _pose = pose;
        _jump = jump;
        _fall = fall;
        AddTransition(jump, fall, () => pose != null && pose.VerticalSpeed <= 0.05f);
    }

    public override void Enter()
    {
        if (Current != null)
            return;

        bool rising = _pose != null && _pose.VerticalSpeed > 0.05f;
        SetInitial(rising ? _jump : _fall);
        base.Enter();
    }
}

/// <summary>
/// Idle, move, jump, and fall on top of an existing controller.
/// </summary>
[DisallowMultipleComponent]
[DefaultExecutionOrder(100)]
public class PlayerStateDriver : StateMachineHost
{
    [SerializeField] PlayerPose pose;
    [SerializeField] bool logTransitions;

    StateMachine _locomotion;
    PushdownMachine _stack;
    NamedState _paused;

    public override StateMachine Machine => _locomotion;

    public override string Label
    {
        get
        {
            if (_stack != null && _stack.Depth > 1)
                return "Paused";
            return base.Label;
        }
    }

    void Awake()
    {
        if (pose == null)
            pose = GetComponent<PlayerPose>();
    }

    void Start()
    {
        if (pose == null)
        {
            Debug.LogWarning("Player state driver has no pose.", this);
            return;
        }

        var idle = new NamedState("Idle");
        var move = new NamedState("Move");
        var jump = new NamedState("Jump");
        var fall = new NamedState("Fall");
        var air = new AirStates(pose, jump, fall);

        _locomotion = new StateMachine("Locomotion");
        _locomotion.SetLog(this, logTransitions);
        air.SetLog(this, logTransitions);

        _locomotion.AddTransition(air, move, () => pose.Grounded && pose.HorizontalSpeed > pose.MoveThreshold, 20);
        _locomotion.AddTransition(air, idle, () => pose.Grounded, 15);
        _locomotion.AddAnyTransition(air, () => !pose.Grounded, 10);
        _locomotion.AddTransition(idle, move, () => pose.HorizontalSpeed > pose.MoveThreshold);
        _locomotion.AddTransition(move, idle, () => pose.HorizontalSpeed <= pose.MoveThreshold);

        bool grounded = pose.Grounded;
        _locomotion.SetInitial(grounded ? (IState)idle : air);

        _paused = new NamedState("Paused");
        _stack = new PushdownMachine();
        _stack.Push(_locomotion);
    }

    void Update()
    {
        if (_stack == null)
            return;
        _stack.Tick(Time.deltaTime);
    }

    void FixedUpdate()
    {
        if (_stack == null)
            return;
        _stack.FixedTick(Time.fixedDeltaTime);
    }

    public void Pause()
    {
        if (_stack == null || _stack.Depth != 1)
            return;
        _stack.Push(_paused);
    }

    public void Resume()
    {
        if (_stack == null || _stack.Depth < 2)
            return;
        _stack.Pop();
    }
}
```

## Stack

`Push` suspends the state underneath when it implements `ISuspendable`, and exits it otherwise. `Pop` is the reverse. The locomotion machine suspends, so a jump in progress is still the jump when the menu closes. A state that only implements `IState` is exited and entered again, and `Enter` runs a second time. That is the wrong tool for pause.

```csharp
using System.Collections.Generic;

/// <summary>
/// A stack of states. The top is the only one ticked.
/// </summary>
public class PushdownMachine
{
    readonly Stack<IState> _stack = new Stack<IState>();

    public int Depth => _stack.Count;

    public IState Current => _stack.Count > 0 ? _stack.Peek() : null;

    public void Push(IState state)
    {
        if (state == null)
            return;

        if (_stack.Count > 0)
            Suspend(_stack.Peek());

        _stack.Push(state);
        state.Enter();
    }

    public void Pop()
    {
        if (_stack.Count == 0)
            return;

        IState top = _stack.Pop();
        top.Exit();
        if (_stack.Count > 0)
            Resume(_stack.Peek());
    }

    public void Tick(float dt)
    {
        IState top = Current;
        if (top != null)
            top.Tick(dt);
    }

    public void FixedTick(float dt)
    {
        IState top = Current;
        if (top != null)
            top.FixedTick(dt);
    }

    static void Suspend(IState state)
    {
        if (state is ISuspendable suspendable)
            suspendable.Suspend();
        else
            state.Exit();
    }

    static void Resume(IState state)
    {
        if (state is ISuspendable suspendable)
            suspendable.Resume();
        else
            state.Enter();
    }
}
```

## Animator

Use a `StateMachineBehaviour` when the clip, the blend, or the root motion is the thing that matters. The gameplay machine should not also be the Animator. Drive parameters from the gameplay state if a clip must follow idle and jump. Do not read the Animator's current name back as the authority for "am I falling", or the two graphs will disagree during a cross-fade.

The behaviour below is the shape a combo window would use. The combo itself is still the [roadmap](../../roadmap.md#combat) entry. The flag lives on a `MonoBehaviour` because the behaviour asset is shared by every Animator that uses the controller. Mutable data on the `StateMachineBehaviour` is shared too.

```csharp
using UnityEngine;

/// <summary>
/// Per-character combo flag. The Animator behaviour only sets it.
/// </summary>
public class ComboWindow : MonoBehaviour
{
    public bool IsOpen { get; private set; }

    public void Begin()
    {
        IsOpen = true;
    }

    public void End()
    {
        IsOpen = false;
    }
}

/// <summary>
/// Put this on the attack state in the Animator, not on the gameplay machine.
/// </summary>
public class AttackWindowBehaviour : StateMachineBehaviour
{
    public override void OnStateEnter(Animator animator, AnimatorStateInfo stateInfo, int layerIndex)
    {
        ComboWindow window = animator.GetComponent<ComboWindow>();
        if (window != null)
            window.Begin();
    }

    public override void OnStateExit(Animator animator, AnimatorStateInfo stateInfo, int layerIndex)
    {
        ComboWindow window = animator.GetComponent<ComboWindow>();
        if (window != null)
            window.End();
    }
}
```

## Debugging

Select the driver in Play Mode. The gizmo is the leaf state, or `Paused` while the stack is deeper than the locomotion machine. **Log Transitions** prints one line per change, including the nested air machine. The label is the same string on a uGUI `Text`.

```csharp
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Shows the host's label. No polling beyond the binding.
/// </summary>
[DisallowMultipleComponent]
public class StateDebugLabel : MonoBehaviour
{
    [SerializeField] StateMachineHost host;
    [SerializeField] Text label;

    void LateUpdate()
    {
        if (label == null)
            return;
        label.text = host != null ? host.Label : string.Empty;
    }
}
```

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Move Threshold | `0.2` | Horizontal speed, in metres per second, that counts as moving. |
| Log Transitions | Off | Console line for every change. |
| Landing priority | `20` / `15` | Grounded leave-air rules, tested before the any-state air rule at `10`. |
| Air rule | `10` | Any state, when the capsule is not grounded. |
| Fall cutoff | `0.05` | Vertical speed at or below this, while airborne, is fall rather than jump. |

## Pitfalls

!!! warning "Common pitfalls"

    `CharacterController.isGrounded` flips when `Move` runs, and the controller page's own probe can disagree with it. If jump and fall flicker, publish that page's grounded flag into the pose. Do not run a second, different ground cast and hope they match.

    `CharacterController.velocity` is the right name on the capsule. `linearVelocity` is the Rigidbody name. Swapping them does not compile on the other type.

    The first `Update` can run before the controller has moved. The driver waits until `Start`, then reads the pose. A machine built in `Awake` and ticked in `Update` on order `0` will often begin in fall, because `isGrounded` is still false.

    A predicate that changes the machine is ignored. So is a second transition in the same `Enter`. One change per evaluation. The new state's own rules run on the next `Tick`, which is the same frame, after `Enter`.

    Any-state at a high priority silences the specific rules. Landing is deliberately higher than "go to air", or a grounded landing would re-enter air because of a one-frame `isGrounded` dip you have not actually fixed.

    Rebuilding the transition list in `Update` allocates and can change order. Build it once.

    `Pause` suspends. A hand-rolled `Exit` plus `Enter` for the menu replays the state's `Enter` and, for air, picks jump or fall again.

    `Time.timeScale = 0` freezes `Update`. The menu that calls `Resume` must run on unscaled time, or the stack never pops. This sample does not change `timeScale`.

    Nested `Exit` exits the inner state. It does not restore it later. The stack is what remembers an in-progress jump.

    During an Animator cross-fade, `OnStateEnter` of the next clip can run before `OnStateExit` of the previous one, and both `OnStateUpdate` calls run while the weights move. A window that opens in `Enter` and closes in `Exit` flickers. Disabling the object inside `OnStateEnter` skips `OnStateExit`, so the flag stays open.

    The `StateMachineBehaviour` instance is the asset on the controller. Do not store a per-character timer on it. Write a `MonoBehaviour` on the Animator, as `ComboWindow` does.

    These states must not call `CharacterController.Move`. The movement script already did. A second displacement in `Tick` stacks on top of it.
