---
engine: Unity
version: 6+
---

# Attack combos

A melee chain where each press continues the attack in progress: light, light, light, or light, light, heavy for a finisher. Each step has a hit window, when its volume deals damage, and a combo window, when the next press is allowed to cut it short. A press that arrives early is buffered and plays as soon as the window opens, so the chain feels responsive without frame-perfect timing.

Hits go through the same pipeline as [weapons](weapons.md): a `DamageInfo` into [`Hurtbox.Receive`](../systems/health.md#hurtbox-and-hitbox), or `IDamageable` when there is no hurtbox.

## A step's timeline

```text
time  0 ───── hitStart ═══ hitEnd ───── comboOpen ─────────── duration
      wind-up   hit volume live         a buffered press      recovery ends,
                once per target         starts the next step  combo ends
```

- **Hit window**, `hitStart` to `hitEnd`: the step's box is tested every frame, and each target is hit at most once per step.
- **Combo window**, `comboOpen` to `duration`: a press in this window, or a buffered one, starts the step it branches to.
- **Recovery**: with no press, the step runs to `duration` and the combo ends. The Animator returns to locomotion through its own exit transition.

A step branches on which button was pressed. `nextLight` and `nextHeavy` are step indices, or `-1` to end there. That makes the combo a small tree:

| Index | Step | Next light | Next heavy |
| --- | --- | --- | --- |
| 0 | Slash 1 | 1 | -1 |
| 1 | Slash 2 | 2 | 3 |
| 2 | Slash 3 | -1 | -1 |
| 3 | Overhead finisher | -1 | -1 |

`lightStart` is 0. `heavyStart` can be its own opener, or `-1` for no heavy opener.

## Setup

1. In the Animator Controller, add one state per step, named to match the step's **Animator State**, for example `Slash1`. Give each a transition back to locomotion with **Has Exit Time** at the clip's end. The script cross-fades into states by name, so no transitions into them are needed.
2. Create a **Combo** asset (`Game/Combo`). Add the steps and fill in the timings in seconds, using the clip's length as **Duration**. Set the branches.
3. Put `ComboRunner` on the character. Assign the combo and the Animator. **Hit Mask** should include the hurtbox layers. **Owner** is the character's root, so it never hits itself.
4. Put `ComboInput` on the same object. Left mouse or the gamepad's west button is light; right mouse or north is heavy.
5. Select the character in Play mode. The step's hit box is drawn as a gizmo while it is live, which is the quickest way to tune `Hit Center` and `Hit Half Extents`.
6. To lock movement during an attack, subscribe to `StepStarted` and `ComboEnded`, or read `IsAttacking` from the controller.

## Input buffer

A press is stored with its time. It stays valid for **Input Buffer** seconds, 0.25 by default. Each frame the runner checks it:

- **Not attacking:** a fresh press starts the opener for that button.
- **In the combo window:** a fresh press with a branch starts that branch.
- **Otherwise:** the press waits. If the window opens before it expires, it plays then. If not, it is dropped.

One stored press is enough for a two-button chain. A fighting-game motion that matches a sequence needs a history instead, which is the [ring buffer](../../data-structures/ring-buffer.md#input-history) page.

## Timing from data or from animation events

The script times windows in seconds from the step's data by default. That keeps tuning in one asset, and it does not depend on which clip is playing during a cross-fade.

For timings that must follow the animation exactly, tick **Use Animation Events** and add events to each clip that call `ComboHitOpen`, `ComboHitClose`, and `ComboChainOpen`. Animation events only reach components on the same GameObject as the Animator, so put `ComboRunner` there, or forward the calls. During a cross-fade, the outgoing clip's events still fire. A late `ComboHitClose` from the previous step is harmless; a late `ComboHitOpen` can open the new step's window early. Keep events away from the very end of a clip.

## Scripts

### Attack step

```csharp
using System;
using UnityEngine;

public enum AttackInput
{
    Light,
    Heavy
}

/// <summary>
/// One attack in a combo: its animation, windows in seconds, damage, hit box, and branches.
/// </summary>
[Serializable]
public class AttackStep
{
    public string name = "Attack";

    [Tooltip("Animator state to cross-fade into. One state per step.")]
    public string animatorState = "Slash1";
    [Min(0f)] public float crossFade = 0.05f;

    [Tooltip("Seconds until the step ends and the combo drops.")]
    [Min(0.05f)] public float duration = 0.6f;
    [Tooltip("Seconds. The hit box is live from Hit Start to Hit End.")]
    [Min(0f)] public float hitStart = 0.15f;
    [Min(0f)] public float hitEnd = 0.25f;
    [Tooltip("Seconds. From here, a press starts the next step.")]
    [Min(0f)] public float comboOpen = 0.3f;

    public float damage = 10f;
    public DamageType damageType;

    [Tooltip("Hit box centre and half size, in the runner's local space.")]
    public Vector3 hitCenter = new Vector3(0f, 1f, 1f);
    public Vector3 hitHalfExtents = new Vector3(0.6f, 0.6f, 0.6f);

    [Tooltip("Step index for a light press in the window. -1 ends the combo.")]
    public int nextLight = -1;
    [Tooltip("Step index for a heavy press in the window. -1 ends the combo.")]
    public int nextHeavy = -1;
}
```

### Combo definition

```csharp
using System;
using UnityEngine;

/// <summary>
/// A tree of attack steps. Shared by every character that uses it.
/// </summary>
[CreateAssetMenu(menuName = "Game/Combo")]
public class ComboDefinition : ScriptableObject
{
    public AttackStep[] steps = Array.Empty<AttackStep>();

    [Tooltip("Step a light press starts from. -1 for none.")]
    public int lightStart = 0;
    [Tooltip("Step a heavy press starts from. -1 for none.")]
    public int heavyStart = -1;

    [Tooltip("Seconds a press waits for a window before it is dropped.")]
    [Min(0f)] public float inputBuffer = 0.25f;

    public AttackStep Get(int index)
    {
        return steps != null && index >= 0 && index < steps.Length ? steps[index] : null;
    }

    public int StartFor(AttackInput input)
    {
        return input == AttackInput.Light ? lightStart : heavyStart;
    }
}
```

### Runner

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Plays a combo: buffers presses, advances steps in their windows, and sweeps the hit box.
/// </summary>
[DisallowMultipleComponent]
public class ComboRunner : MonoBehaviour
{
    [SerializeField] ComboDefinition combo;
    [SerializeField] Animator animator;
    [SerializeField] LayerMask hitMask = ~0;

    [Tooltip("Colliders under this are never hit. Empty uses the root.")]
    [SerializeField] Transform owner;

    [Tooltip("Windows come from animation events instead of the step's seconds.")]
    [SerializeField] bool useAnimationEvents;

    public event Action<AttackStep> StepStarted;
    public event Action ComboEnded;

    public bool IsAttacking => _step != null;
    public AttackStep CurrentStep => _step;

    readonly Collider[] _overlaps = new Collider[16];
    readonly HashSet<object> _hitThisStep = new HashSet<object>();

    AttackStep _step;
    float _clock;
    bool _eventHitOpen;
    bool _eventChainOpen;

    bool _hasBuffered;
    AttackInput _buffered;
    float _bufferedAt;

    void Awake()
    {
        if (owner == null)
            owner = transform.root;
        if (animator == null)
            animator = GetComponentInChildren<Animator>();
    }

    void OnDisable()
    {
        _hasBuffered = false;
        EndCombo();
    }

    /// <summary>Records a press. It plays now, or when the next window opens, or expires.</summary>
    public void Press(AttackInput input)
    {
        _buffered = input;
        _bufferedAt = Time.time;
        _hasBuffered = true;
    }

    /// <summary>Stops the combo, for example when the character is staggered.</summary>
    public void Cancel()
    {
        EndCombo();
    }

    void Update()
    {
        if (combo == null)
            return;

        if (_hasBuffered && Time.time - _bufferedAt > combo.inputBuffer)
            _hasBuffered = false;

        if (_step == null)
        {
            if (_hasBuffered)
                StartStep(combo.StartFor(_buffered));
            return;
        }

        float previous = _clock;
        _clock += Time.deltaTime;

        if (HitWindowLive(previous, _clock))
            Sweep();

        if (_hasBuffered && CanChain())
        {
            int next = _buffered == AttackInput.Light ? _step.nextLight : _step.nextHeavy;
            if (StartStep(next))
                return;
        }

        if (_clock >= _step.duration)
            EndCombo();
    }

    bool StartStep(int index)
    {
        AttackStep step = combo.Get(index);
        if (step == null)
            return false;

        _hasBuffered = false;
        _step = step;
        _clock = 0f;
        _eventHitOpen = false;
        _eventChainOpen = false;
        _hitThisStep.Clear();

        if (animator != null && !string.IsNullOrEmpty(step.animatorState))
            animator.CrossFadeInFixedTime(step.animatorState, step.crossFade);

        StepStarted?.Invoke(step);
        return true;
    }

    void EndCombo()
    {
        if (_step == null)
            return;

        _step = null;
        _clock = 0f;
        _eventHitOpen = false;
        _eventChainOpen = false;
        ComboEnded?.Invoke();
    }

    bool HitWindowLive(float previous, float now)
    {
        if (useAnimationEvents)
            return _eventHitOpen;

        // Any overlap between this frame's interval and the window, so a short window
        // inside one long frame is still tested once.
        return previous < _step.hitEnd && now >= _step.hitStart;
    }

    bool CanChain()
    {
        return useAnimationEvents ? _eventChainOpen : _clock >= _step.comboOpen;
    }

    void Sweep()
    {
        Vector3 center = transform.TransformPoint(_step.hitCenter);
        int count = Physics.OverlapBoxNonAlloc(
            center, _step.hitHalfExtents, _overlaps, transform.rotation, hitMask, QueryTriggerInteraction.Collide);

        for (int i = 0; i < count; i++)
        {
            Collider col = _overlaps[i];
            if (col.transform.IsChildOf(owner))
                continue;

            Hurtbox hurtbox = col.GetComponent<Hurtbox>();
            IDamageable damageable = hurtbox == null ? col.GetComponentInParent<IDamageable>() : null;
            if (hurtbox == null && damageable == null)
                continue;

            // One hit per target per step, even with a head and a body hurtbox.
            Health health = col.GetComponentInParent<Health>();
            object key = health != null ? health : damageable != null ? (object)damageable : hurtbox;
            if (!_hitThisStep.Add(key))
                continue;

            Vector3 point = ClosestPoint(col, center);
            Vector3 toAttacker = center - point;

            DamageInfo info = new DamageInfo
            {
                Amount = _step.damage,
                Type = _step.damageType,
                Source = this,
                Point = point,
                Normal = toAttacker.sqrMagnitude > 1e-8f ? toAttacker.normalized : -transform.forward
            };

            if (hurtbox != null)
                hurtbox.Receive(info);
            else
                damageable.ApplyDamage(info);
        }
    }

    static Vector3 ClosestPoint(Collider col, Vector3 position)
    {
        // Collider.ClosestPoint supports primitives and convex meshes only.
        if (col is MeshCollider mesh && !mesh.convex)
            return col.bounds.ClosestPoint(position);
        return col.ClosestPoint(position);
    }

    // Animation events. Add them to the step clips when Use Animation Events is on.
    public void ComboHitOpen() => _eventHitOpen = true;
    public void ComboHitClose() => _eventHitOpen = false;
    public void ComboChainOpen() => _eventChainOpen = true;

    void OnDrawGizmosSelected()
    {
        if (_step == null || !Application.isPlaying)
            return;

        Gizmos.color = HitWindowLive(_clock, _clock) ? Color.red : new Color(1f, 0.5f, 0f, 0.4f);
        Gizmos.matrix = Matrix4x4.TRS(transform.TransformPoint(_step.hitCenter), transform.rotation, Vector3.one);
        Gizmos.DrawWireCube(Vector3.zero, _step.hitHalfExtents * 2f);
    }
}
```

### Input

The input script runs before the runner, so a press is seen on the frame it happens.

=== "Input System"

    ```csharp
    using UnityEngine;
    using UnityEngine.InputSystem;

    /// <summary>
    /// Light on left mouse or the west face button. Heavy on right mouse or north.
    /// </summary>
    [DefaultExecutionOrder(-10)]
    [RequireComponent(typeof(ComboRunner))]
    public class ComboInput : MonoBehaviour
    {
        ComboRunner _runner;

        void Awake()
        {
            _runner = GetComponent<ComboRunner>();
        }

        void Update()
        {
            Mouse mouse = Mouse.current;
            Gamepad pad = Gamepad.current;

            if ((mouse != null && mouse.leftButton.wasPressedThisFrame) ||
                (pad != null && pad.buttonWest.wasPressedThisFrame))
                _runner.Press(AttackInput.Light);

            if ((mouse != null && mouse.rightButton.wasPressedThisFrame) ||
                (pad != null && pad.buttonNorth.wasPressedThisFrame))
                _runner.Press(AttackInput.Heavy);
        }
    }
    ```

=== "Legacy Input Manager"

    ```csharp
    using UnityEngine;

    /// <summary>
    /// Light on left mouse or joystick button 2. Heavy on right mouse or joystick button 3.
    /// </summary>
    [DefaultExecutionOrder(-10)]
    [RequireComponent(typeof(ComboRunner))]
    public class ComboInput : MonoBehaviour
    {
        ComboRunner _runner;

        void Awake()
        {
            _runner = GetComponent<ComboRunner>();
        }

        void Update()
        {
            if (Input.GetMouseButtonDown(0) || Input.GetKeyDown(KeyCode.JoystickButton2))
                _runner.Press(AttackInput.Light);

            if (Input.GetMouseButtonDown(1) || Input.GetKeyDown(KeyCode.JoystickButton3))
                _runner.Press(AttackInput.Heavy);
        }
    }
    ```

!!! warning "Common pitfalls"

    Two steps that use the same Animator state may not restart it, because cross-fading into the state already playing does not always rewind it. Give each step its own state, even when two share a clip.

    A combo window that opens before the hit window lets a fast player skip a step's damage. Keep `comboOpen` at or after `hitEnd`.

    Without the one-hit-per-step set, a target is hit every frame of the window. Without keying it on `Health`, a head and a body hurtbox are hit separately by one swing.

    `Time.timeScale` of 0 freezes the clock and the buffer together, so a paused game does not eat a press. A hit-stop that slows time also stretches the windows, which is usually what you want.

    The hit box is in the runner's space. If the runner is on a child that the Animator rotates, the box swings with the bone. Put it on the root unless that is the intent.
