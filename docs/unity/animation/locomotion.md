---
engine: Unity
version: 6+
uses:
  - name: Top-down survival
    text: Legs that walk, strafe, and backpedal while the body faces the aim direction.
  - name: Shooters
    text: An upper-body layer that holds the weapon while the legs run.
  - name: RPGs
    text: One controller for every weapon type, with an override controller swapping the clips.
---

# Locomotion and layers

A character that faces one way and moves another, such as a top-down survivor aiming at the mouse while backing away. The legs need a clip for every direction relative to facing, blended smoothly. The upper body needs its own clips, for the weapon in its hands. This page sets up both, then swaps the whole clip set per weapon without a second controller.

## Parameters

Every page in this section uses the same parameter names:

| Parameter | Type | Meaning |
| --- | --- | --- |
| `MoveX` | Float | Velocity to the character's right, as a fraction of run speed. -1 to 1. |
| `MoveZ` | Float | Velocity along the character's forward, as a fraction of run speed. -1 to 1. |
| `Speed` | Float | Ground speed as a fraction of run speed. 0 to 1, more when sprinting. |

Local velocity, not world velocity, is what makes facing and moving independent. Moving north while facing east is `MoveX = -1`, a strafe left.

## Blend tree

A **2D Freeform Directional** blend tree on `MoveX` and `MoveZ`:

| Motion | Position |
| --- | --- |
| Idle | (0, 0) |
| Walk forward | (0, 0.5) |
| Run forward | (0, 1) |
| Run backward | (0, -1) |
| Strafe left, right | (-1, 0), (1, 0) |
| Diagonals, if you have them | (±0.7, ±0.7) |

- **Freeform Directional** is for motions in different directions, with an idle at the centre. **Simple Directional** allows only one motion per direction, so it cannot hold walk and run forward. **Freeform Cartesian** is for motions that are not directions, such as speed against turn rate.
- Eight directions plus idle look good. Four plus idle works, and the diagonals blend from the neighbours, with some foot sliding.
- Backward diagonals blended from back and side clips often cross the legs. Author them, or keep backpedal strafes slow.
- With root-motion clips, **Compute Positions → Velocity XZ** places each motion at the speed it actually moves, which removes most sliding. Then scale the parameters by real speed, not a fraction.

For a character that only turns to face where it walks, a **1D** blend tree on `Speed` is enough: idle, walk, run.

## Feeding the parameters

The parameters come from how the body actually moved this frame, so it works with any [controller](../mechanics/controllers/index.md): a `CharacterController`, a `Rigidbody`, or a `NavMeshAgent`.

```csharp
using UnityEngine;

/// <summary>
/// Sets MoveX, MoveZ, and Speed from how far the body moved this frame, relative to its facing.
/// </summary>
[DefaultExecutionOrder(100)] // after the movement scripts
public class LocomotionAnimator : MonoBehaviour
{
    static readonly int MoveX = Animator.StringToHash("MoveX");
    static readonly int MoveZ = Animator.StringToHash("MoveZ");
    static readonly int Speed = Animator.StringToHash("Speed");

    [SerializeField] Animator animator;
    [Tooltip("The speed of the run clip, in metres per second. Parameters are fractions of this.")]
    [SerializeField] float runSpeed = 4f;
    [Tooltip("Seconds for parameters to settle. Hides jitter from the physics step.")]
    [SerializeField] float dampTime = 0.1f;

    Vector3 _lastPosition;

    void OnEnable() => _lastPosition = transform.position;

    void Update()
    {
        float dt = Time.deltaTime;
        if (dt <= 0f)
            return;

        Vector3 velocity = (transform.position - _lastPosition) / dt;
        _lastPosition = transform.position;
        velocity.y = 0f;

        // A teleport or a respawn is not movement.
        if (velocity.magnitude > runSpeed * 4f)
            velocity = Vector3.zero;

        Vector3 local = transform.InverseTransformDirection(velocity) / runSpeed;
        animator.SetFloat(MoveX, local.x, dampTime, dt);
        animator.SetFloat(MoveZ, local.z, dampTime, dt);
        animator.SetFloat(Speed, velocity.magnitude / runSpeed, dampTime, dt);
    }
}
```

- `SetFloat` with a damp time eases toward the value. Pass the frame's delta time every frame, or the damping stalls.
- Put it on the object whose `forward` is the facing. For a top-down character that faces the cursor, that is the body the [top-down controller](../mechanics/top-down.md) rotates.
- Physics bodies move in `FixedUpdate`, so some frames see no movement and the next sees two steps. The damping hides that. With **Interpolate** on the `Rigidbody`, the transform moves every frame and the problem mostly goes away.
- The Animator evaluates after `Update` and before `LateUpdate`. Setting parameters in `Update` after the movement, which the execution order does, uses them the same frame.

### Faster than the clip

When the character moves faster than the run clip, the feet slide. Tick **Multiplier → Parameter** on the locomotion state and drive a `MoveSpeedScale` parameter with `Mathf.Max(1f, speed / runSpeed)`, so the clip plays faster instead.

## Layers and avatar masks

The **Base Layer** plays locomotion for the whole body. A second layer plays the upper body on top of it.

| Setting | Upper-body layer |
| --- | --- |
| **Weight** | 1. Set from code to fade the layer in and out. |
| **Mask** | An **Avatar Mask** with the legs and root off. For Generic rigs, a transform mask with the spine and arms ticked. |
| **Blending** | **Override**: replaces the masked bones. **Additive**: adds the clip's difference from its first frame, for breathing, flinches, and recoil on top of whatever plays. |
| **Sync** | Off. Sync copies another layer's states, for wounded or crouched versions of the same machine. |

```csharp
// In the character's animator component. Fades the aim layer, which holds the weapon up.
static readonly int AimLayer = 1;
float _aimWeight;

public void TickAim(bool aiming, float dt)
{
    _aimWeight = Mathf.MoveTowards(_aimWeight, aiming ? 1f : 0f, dt / 0.15f);
    animator.SetLayerWeight(AimLayer, _aimWeight);
}
```

- Each layer adds the cost of the clips it plays. Keep layers that are always needed, and fold rarely used ones into states of an existing layer.
- Look up layer indices with `animator.GetLayerIndex("UpperBody")` once, rather than hard-coding them in more than one place.
- An additive clip must be authored from the pose it is added to. An additive recoil made on an idle pose bends a crouched character wrong.

## Override controllers per weapon

One state machine, many clip sets. An **Animator Override Controller** references the base controller and replaces chosen clips. A pistol, a rifle, and a melee weapon each get one, and the states and transitions stay in one place.

```csharp
// In the weapon holder, on equip. Each weapon definition has an AnimatorOverrideController.
if (definition.animations != null)
    animator.runtimeAnimatorController = definition.animations;
```

- Assigning a controller restarts the state machine. Do it on equip, while the character is in a neutral state, not mid-attack.
- An override controller with no clip in a slot uses the base clip. Override only what differs.
- For many characters that share one controller and differ by a few clips, create the override at runtime with `new AnimatorOverrideController(baseController)` and fill it with `ApplyOverrides`.

## Setup

1. Import the clips with the right **Rig** for the model. Untick **Loop Time** only on one-shot clips.
2. Add the parameters above to the Animator Controller.
3. Add a **Locomotion** state with a 2D Freeform Directional blend tree, as in the table.
4. Add `LocomotionAnimator` to the character's root and assign the Animator, which is often on the model child.
5. For an upper body that holds weapons, add a layer with an upper-body **Avatar Mask**.

!!! warning "Common pitfalls"

    World velocity in the parameters means the character runs forward while walking backwards. Convert to local space.

    `SetFloat` with damping, called only on some frames, never settles. Call it every frame.

    A 2D Simple Directional tree with two motions in the same direction, such as walk and run forward, blends wrongly. Use Freeform Directional.

    An upper-body layer without a mask overrides the legs too, and the character slides in its aim pose.

    Swapping the controller mid-attack restarts the Animator and cuts the attack. Swap on equip.
