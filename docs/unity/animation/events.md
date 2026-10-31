---
engine: Unity
version: 6+
uses:
  - name: Melee action
    text: The hit lands on the frame the blade connects, not on a timer that drifts from the clip.
  - name: Top-down survival
    text: Footstep sounds and noise for zombies, from the frames the feet touch down.
  - name: Shooters
    text: The magazine is refilled on the frame the new one clicks in.
---

# Animation events and timing

Gameplay that has to line up with a clip: the frame a sword connects, a foot touching down, a magazine clicking in. Animation events call a method from a frame of a clip. They are the right tool for presentation, and a careful one for gameplay, because cross-fades and blend trees fire events you did not expect. This page covers events, then curves and state behaviours, then when to time in code instead.

## Events

An event is a time on a clip, a method name, and one optional argument.

- **Clips made in Unity**: add events in the **Animation** window, on the event row above the curves.
- **Clips imported from a model**: the clip is read-only. Add events in the model's **Animation** tab, under **Events**, and select **Apply**.

The method is found by name on every component on the **same GameObject as the Animator**, like `SendMessage`. Components on parents or children do not receive it. If none has the method, Unity logs "AnimationEvent has no receiver".

The method takes nothing, or one `float`, `int`, `string`, object reference, or `AnimationEvent`. The `AnimationEvent` version carries all of them, plus which clip and state fired it.

## A relay on the model

The Animator usually sits on the model child, and gameplay on the root. A relay on the model turns events into C# events that root scripts subscribe to, so the method names live in one place.

```csharp
using System;
using UnityEngine;

/// <summary>
/// Receives animation events on the Animator's GameObject and re-raises them as C# events.
/// </summary>
public class AnimationEventRelay : MonoBehaviour
{
    [Tooltip("Events from clips blended below this weight are ignored.")]
    [SerializeField, Range(0f, 1f)] float minWeight = 0.5f;

    public event Action<string> Footstep;   // the argument names the foot
    public event Action HitOpen;
    public event Action HitClose;
    public event Action<string> Cue;        // anything else: "MagIn", "Throw", "Sound:Swing"

    // Names below are what the clips' events call.

    public void OnFootstep(AnimationEvent e)
    {
        if (Counts(e))
            Footstep?.Invoke(e.stringParameter);
    }

    public void OnHitOpen(AnimationEvent e)
    {
        if (Counts(e))
            HitOpen?.Invoke();
    }

    public void OnHitClose() => HitClose?.Invoke(); // always: a missed close leaves a hit box open

    public void OnCue(AnimationEvent e)
    {
        if (Counts(e))
            Cue?.Invoke(e.stringParameter);
    }

    bool Counts(AnimationEvent e) => e.animatorClipInfo.weight >= minWeight;
}
```

## Blend trees and cross-fades

Events fire from every clip that is playing, not only the one you see.

- **Blend trees.** In a locomotion blend between walk and run, both clips fire their footsteps, at slightly different times. Filter on `animatorClipInfo.weight`, as the relay does, so only the dominant clip counts.
- **Cross-fades.** The outgoing clip keeps playing during the transition and keeps firing. A hit event late in attack 1 can fire after attack 2 has started. Keep gameplay events away from the last fifth of a clip, or check the current state before acting.
- **Exits.** An event later in the clip than the point where its state is left never fires. A hit-close event after an early exit is skipped, and the hit box stays open. Close it in code on state change as well.
- **Loops.** A looping clip fires its events once per loop. A low frame rate does not skip them: events between the last and the current time all fire.

`animator.fireEvents = false` stops all events on one Animator, which is useful for far-away crowd members.

## Curves

An event is a moment. A **curve** is a value over the whole clip. In the model's **Animation** tab, under **Curves**, add a curve with a name, then add a **Float** parameter with the same name to the Animator Controller. The Animator drives that parameter from the curve every frame, blended like the clips are.

| Curve | Read it as |
| --- | --- |
| `WeaponTrail` 0 or 1 | Trail renderer on while above 0.5. |
| `LeftFootDown`, `RightFootDown` | Feet planted, for [foot IK](ik.md#humanoid-foot-ik) weight and footstep detection. |
| `MoveLock` | How much the player may steer during an attack. |
| `IKWeight` | Blend IK in and out as the clip needs. |

Curves blend through cross-fades and blend trees, which events cannot. The parameter is written by the Animator; setting it from code has no effect.

## State behaviours

A `StateMachineBehaviour` on a state gets `OnStateEnter`, `OnStateUpdate`, and `OnStateExit`. It suits work tied to the whole state, such as turning a weapon trail on for the attack state. The [state machines](../architecture/state-machines.md#animator) page has an example and the caveats: during a cross-fade the next state's `Enter` can come before the last state's `Exit`.

Each Animator gets its own instance of each behaviour, unless the class has `[SharedBetweenAnimators]`. Even so, keep per-character state on a component the behaviour finds with `animator.GetComponent`, so other scripts can read it.

## Events or code

| Timing source | Good for | Weak at |
| --- | --- | --- |
| **Animation events** | Sounds, effects, footsteps, and hit frames that must match the art. | Fire from blended clips and outgoing clips; skipped on early exits; method names are strings. |
| **Curves** | Values that rise and fall, and anything that must blend. | Need a matching Float parameter per curve. |
| **Times in data**, as [attack combos](../combat/combos.md#timing-from-data-or-from-animation-events) do | Gameplay windows that must be exact and testable without the Animator. | Drift from the art when an animator retimes the clip. |

A common split: gameplay windows from data, checked against the clip in the editor, and sounds and effects from events.

!!! warning "Common pitfalls"

    An event receiver on the root, when the Animator is on the model child, never gets called. Put the receiver, or a relay, next to the Animator.

    Footsteps fire twice in a locomotion blend tree, once from each clip. Filter on clip weight.

    An event in the last frames of a clip fires after the next state has started, or not at all on an early exit. Keep gameplay events away from the end.

    Events on an imported clip edited in the Animation window are lost. Add them in the model's import settings.

    A curve parameter set from a script is overwritten by the Animator every frame.
