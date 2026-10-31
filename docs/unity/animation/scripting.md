---
engine: Unity
version: 6+
uses:
  - name: Top-down survival
    text: One component that every system calls, so the zombie and the survivor share their animation code.
  - name: Hordes and crowds
    text: Pooled characters reset to idle on reuse instead of finishing their last death animation.
  - name: Melee action
    text: Attacks started from code with a cross-fade, and triggers that never fire late.
---

# Driving the Animator from code

The Animator is controlled through its parameters and a few play calls. Done carelessly, every script on the character sets its own parameters by string, triggers fire seconds late, and pooled characters come back halfway through a death. This page puts one component between the game and the Animator, and covers the API it uses.

## Hashes, not strings

```csharp
static readonly int Speed = Animator.StringToHash("Speed");

animator.SetFloat(Speed, value);
```

Every string call hashes the name each time. A static hash per parameter is free after the first, and a typo fails in one place. State names hash the same way, with or without the layer prefix: `"Base Layer.Attack"` is the full path, `"Attack"` the short name.

Setting a parameter the controller does not have logs a warning every call. Check names once, in the editor or in `Awake`:

```csharp
static bool HasParameter(Animator animator, int hash)
{
    foreach (AnimatorControllerParameter p in animator.parameters)
    {
        if (p.nameHash == hash)
            return true;
    }
    return false;
}
```

## Which parameter type

| Type | Use for | Watch for |
| --- | --- | --- |
| **Float** | Continuous values: speed, direction, aim angle. | Damp it, as on [locomotion](locomotion.md#feeding-the-parameters). |
| **Bool** | States that last: `IsAiming`, `IsGrounded`, `IsCrouched`. | Set it every frame from the source of truth, or on change, not both. |
| **Trigger** | One-shots: `Hit`, `Reload`. | It stays set until a transition consumes it. A trigger set while no transition can take it fires later, when one can. |
| **Int** | A choice among several: weapon type, attack variant. | Transitions compare for equality. Use an enum on the code side. |

Stale triggers are the classic Animator bug: a `Reload` pressed during a sprint, where reload cannot start, plays when the sprint ends. Clear it when the action is cancelled, with `ResetTrigger`, or skip triggers for actions and play the state directly:

```csharp
// Starts the state now, with a 0.1 second cross-fade, from the beginning.
animator.CrossFadeInFixedTime(ReloadState, 0.1f, layer: 1, fixedTimeOffset: 0f);
```

`CrossFadeInFixedTime` takes seconds, `CrossFade` takes normalised time, and `Play` cuts without blending. Starting actions from code needs no transitions into the state, only out of it, which is how [attack combos](../combat/combos.md) do it.

## Reading state

```csharp
AnimatorStateInfo state = animator.GetCurrentAnimatorStateInfo(0);

bool attacking = state.IsTag("Attack");      // a tag set on several states
bool inReload = state.shortNameHash == ReloadState;
float loops = state.normalizedTime;           // 1.5 is half way through the second loop
bool blending = animator.IsInTransition(0);
```

- During a transition, the current state is still the old one. `GetNextAnimatorStateInfo` is the one being blended to.
- `normalizedTime` keeps counting past 1 on looping clips. Use `% 1` for the position in the loop.
- Use reads for presentation, such as "do not play a footstep while attacking". For gameplay, such as "is the attack finished", keep the timer in the gameplay code. During a cross-fade the Animator is in two states at once, and the answer flickers.

## One owner

Gameplay scripts should not know parameter names. One component on the character turns game state into Animator calls, and everything else calls it.

```csharp
using UnityEngine;

/// <summary>
/// The only script that talks to the character's Animator.
/// </summary>
public class CharacterAnimator : MonoBehaviour
{
    static readonly int IsAiming = Animator.StringToHash("IsAiming");
    static readonly int IsDead = Animator.StringToHash("IsDead");
    static readonly int Reload = Animator.StringToHash("Reload");
    static readonly int HitState = Animator.StringToHash("Hit");
    static readonly int AttackVariant = Animator.StringToHash("AttackVariant");

    [SerializeField] Animator animator;
    [SerializeField] string upperBodyLayer = "UpperBody";

    int _upperLayer;
    float _aimWeight;
    bool _aiming;

    public Animator Animator => animator;

    void Awake()
    {
        _upperLayer = animator.GetLayerIndex(upperBodyLayer);
        // Keep the state when the Animator component is switched off by a culling or LOD script.
        animator.keepAnimatorStateOnDisable = true;
    }

    void Update()
    {
        if (_upperLayer < 0)
            return;
        _aimWeight = Mathf.MoveTowards(_aimWeight, _aiming ? 1f : 0f, Time.deltaTime / 0.15f);
        animator.SetLayerWeight(_upperLayer, _aimWeight);
    }

    public void SetAiming(bool aiming)
    {
        _aiming = aiming;
        animator.SetBool(IsAiming, aiming);
    }

    public void PlayReload() => animator.CrossFadeInFixedTime(Reload, 0.1f, _upperLayer);

    public void PlayHit() => animator.CrossFadeInFixedTime(HitState, 0.05f, _upperLayer);

    public void PlayAttack(int variant)
    {
        animator.SetInteger(AttackVariant, variant);
        animator.CrossFadeInFixedTime("Attack", 0.08f, 0);
    }

    public void SetDead(bool dead) => animator.SetBool(IsDead, dead);

    /// <summary>For pooled characters: back to the default state, as if new.</summary>
    public void ResetPose()
    {
        animator.Rebind();
        animator.Update(0f);
        _aimWeight = 0f;
        _aiming = false;
    }
}
```

Health, weapons, and the brain call `SetAiming`, `PlayReload`, and `SetDead`, the way views call into a model on the [UI](../ui/choosing.md#keep-the-game-out-of-the-ui) page. Renaming a parameter touches one file. A zombie and a survivor share the component and differ only in their controllers.

## Update mode

| Mode | Use it when |
| --- | --- |
| **Normal** | Most characters. Runs with `Update` and follows `Time.timeScale`. |
| **Fixed** | Root motion drives a `Rigidbody`. Steps with `FixedUpdate`, so the motion and the physics agree. Called **Animate Physics** in older versions. |
| **Unscaled Time** | UI and menu characters that animate while the game is paused. |

`animator.speed` scales one Animator. Setting it to 0 for a few frames is a cheap per-character hit stop.

## Pooled characters

A pooled character that was disabled mid-death comes back mid-death, or, with **Keep Animator State On Disable** off, which is the default, back at the entry state but with parameters as they were. Reset explicitly when taking one from the [pool](../architecture/pooling.md):

- `Rebind()` rebuilds the Animator's bindings and returns every bone and parameter to its default.
- `Update(0f)` evaluates once, so the pose is right on the first rendered frame instead of one frame late.

`Rebind` is not free. Call it on reuse, not every frame.

!!! warning "Common pitfalls"

    A trigger set when no transition can take it fires later, at the wrong time. Reset it on cancel, or start actions with `CrossFadeInFixedTime`.

    Gameplay that waits for `normalizedTime >= 1` on the current state hangs when a transition takes the state away first. Time actions in gameplay code.

    Parameter names as strings scattered through scripts break silently when one is renamed. Hash them in one component.

    Disabling the Animator component, as LOD scripts do, resets its state unless **Keep Animator State On Disable** is on.

    A pooled character reused without `Rebind` keeps its last pose and parameters.
