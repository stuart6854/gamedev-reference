---
engine: Unity
version: 6+
package: Animation Rigging 1.3
uses:
  - name: Top-down survival
    text: The upper body twists to aim at the cursor while the legs keep walking.
  - name: Shooters
    text: The off hand stays on the rifle's grip through every animation.
  - name: Companions and NPCs
    text: Heads that turn to look at the player, and feet that stand on stairs.
---

# IK and aiming

Inverse kinematics bends a chain of bones so its end reaches a point: a foot onto a step, a hand onto a grip, a head toward a face. Unity has two ways. Humanoid characters get built-in foot, hand, and look-at IK through `OnAnimatorIK`. Any rig, Humanoid or Generic, can use the **Animation Rigging** package, which adds constraints to the hierarchy and suits aiming and props.

| Need | Use |
| --- | --- |
| Feet on slopes and stairs, Humanoid | [Built-in foot IK](#humanoid-foot-ik) |
| Head and eyes toward a point, Humanoid | [Built-in look-at](#look-at) |
| Spine and arms aiming a weapon | [Animation Rigging Multi-Aim](#aiming-with-animation-rigging) |
| Off hand on a weapon grip | [Animation Rigging Two Bone IK](#off-hand-on-the-grip) |
| Generic rigs, creatures, many-jointed legs | Animation Rigging. See [procedural legs](procedural-legs.md). |

## Humanoid IK

Built-in IK runs in `OnAnimatorIK`, on a script on the Animator's GameObject. It is only called for layers with **IK Pass** ticked: in the Animator window's **Layers** list, select the layer's cog and tick **IK Pass**.

### Humanoid foot IK

Animation assumes flat ground. On a slope or a step, one foot floats and the other sinks. Foot IK casts down from each foot, moves the foot onto what it hits, and lowers the hips so the lower foot can reach.

```csharp
using UnityEngine;

/// <summary>
/// Puts a Humanoid's feet on the ground under them. Needs IK Pass on the base layer.
/// </summary>
[RequireComponent(typeof(Animator))]
public class FootIK : MonoBehaviour
{
    [SerializeField] LayerMask ground = ~0;
    [SerializeField] float castHeight = 0.5f;
    [SerializeField] float castDepth = 0.8f;
    [Tooltip("How fast the hips follow the lower foot, per second.")]
    [SerializeField] float hipSpeed = 8f;

    /// <summary>1 on the ground, 0 in the air. Set by the movement code.</summary>
    public float Weight { get; set; } = 1f;

    Animator _animator;
    float _hipOffset;

    void Awake() => _animator = GetComponent<Animator>();

    void OnAnimatorIK(int layerIndex)
    {
        if (layerIndex != 0)
            return;

        float rootY = transform.position.y;
        float lowest = 0f;
        Place(AvatarIKGoal.LeftFoot, rootY, ref lowest);
        Place(AvatarIKGoal.RightFoot, rootY, ref lowest);

        // Lower the hips by the lower foot's drop, smoothly, so the leg can reach.
        _hipOffset = Mathf.Lerp(_hipOffset, lowest * Weight, 1f - Mathf.Exp(-hipSpeed * Time.deltaTime));
        _animator.bodyPosition += Vector3.up * _hipOffset;
    }

    void Place(AvatarIKGoal goal, float rootY, ref float lowest)
    {
        Vector3 foot = _animator.GetIKPosition(goal);
        Vector3 from = new Vector3(foot.x, rootY + castHeight, foot.z);

        if (Weight <= 0f || !Physics.Raycast(from, Vector3.down, out RaycastHit hit, castHeight + castDepth, ground, QueryTriggerInteraction.Ignore))
        {
            _animator.SetIKPositionWeight(goal, 0f);
            _animator.SetIKRotationWeight(goal, 0f);
            return;
        }

        // Keep the animated lift above the root, so steps still lift; move it onto the ground height.
        float drop = hit.point.y - rootY;
        lowest = Mathf.Min(lowest, drop);

        _animator.SetIKPositionWeight(goal, Weight);
        _animator.SetIKPosition(goal, foot + Vector3.up * drop);

        _animator.SetIKRotationWeight(goal, Weight);
        Quaternion tilt = Quaternion.FromToRotation(Vector3.up, hit.normal);
        _animator.SetIKRotation(goal, tilt * _animator.GetIKRotation(goal));
    }
}
```

- The foot keeps its animated height above the character's root, so a walk still lifts each foot. Only the ground under it changes.
- Lowering the hips is what lets a foot reach a step down. Without it, the leg is too short and the foot hangs.
- The `CharacterController` or collider still decides where the root is. Foot IK changes only the pose.
- Weight 0 in the air, or the feet reach for the ground during a jump. A [curve](events.md#curves) per foot, read with `GetFloat`, can fade the weight in only while the foot is planted.

### Look-at

```csharp
// In the same OnAnimatorIK, for a Humanoid with IK Pass on.
_lookWeight = Mathf.MoveTowards(_lookWeight, HasLookTarget ? 1f : 0f, Time.deltaTime * 3f);
_animator.SetLookAtWeight(_lookWeight, 0.2f, 0.8f, 1f, 0.6f); // overall, body, head, eyes, clamp
_animator.SetLookAtPosition(LookTarget);
```

**Clamp** limits how far the head turns. At 0.5 and above, a target behind the character turns the head only part of the way, instead of snapping round. Fade the weight in and out; a look-at that switches on in one frame snaps the head.

## Aiming with Animation Rigging

Install **Animation Rigging** from the Package Manager. It works on any rig and runs after the Animator, as part of the animation evaluation.

The components:

| Component | Where | Does |
| --- | --- | --- |
| **Rig Builder** | The Animator's GameObject | Collects the rigs and runs them after the Animator. |
| **Rig** | A child object, such as `AimRig` | Groups constraints. Its **Weight** fades them all. |
| **Multi-Aim Constraint** | Children of the rig | Turns one bone to face a source object. One each for spine, chest, and head, with lower weights lower down the spine, spreads the twist. |
| **Two Bone IK Constraint** | Children of the rig | Bends a root, mid, and tip, such as upper arm, forearm, and hand, so the tip reaches a target. |

**Animation Rigging → Rig Setup**, with the Animator's GameObject selected, adds the Rig Builder and an empty rig.

```csharp
using UnityEngine;
using UnityEngine.Animations.Rigging;

/// <summary>
/// Moves the aim constraints' target to the aim point and fades the aim rig in and out.
/// </summary>
public class AimRig : MonoBehaviour
{
    [SerializeField] Rig rig;
    [Tooltip("The source object of the Multi-Aim constraints.")]
    [SerializeField] Transform aimTarget;
    [Tooltip("Height above the character's feet to aim at. Keeps the spine level for a top-down cursor on the floor.")]
    [SerializeField] float aimHeight = 1.3f;
    [SerializeField] float blendTime = 0.15f;

    public bool Aiming { get; set; }
    /// <summary>World point to aim at, such as the cursor on the ground.</summary>
    public Vector3 AimPoint { get; set; }

    void Update()
    {
        Vector3 point = AimPoint;
        point.y = transform.position.y + aimHeight;
        aimTarget.position = point;

        rig.weight = Mathf.MoveTowards(rig.weight, Aiming ? 1f : 0f, Time.deltaTime / blendTime);
    }
}
```

- Give the spine constraints **Limits** on their angles. A target behind the character otherwise twists the spine round.
- For a top-down game, the body already turns toward the cursor. The aim rig only corrects the last few degrees and the pitch, so keep its weights modest.
- The rig runs after the upper-body [layer](locomotion.md#layers-and-avatar-masks). The aim pose clip holds the gun up; the rig points it.

### Off hand on the grip

A rifle animation made for one gun puts the left hand in the wrong place on another. A **Two Bone IK** on the left arm, with its target on the weapon's grip, keeps the hand there whatever plays.

1. On each weapon model, add an empty child, `OffHandGrip`, where the hand should hold it.
2. Under the rig, add a **Two Bone IK Constraint** with **Root**, **Mid**, and **Tip** set to the left upper arm, forearm, and hand. Its context menu's **Auto Setup from Tip Transform** creates a target and a hint.
3. On equip, point the constraint's target at the weapon's grip, and rebuild the rig:

```csharp
// In the weapon holder, after the weapon model is parented to the right hand.
offHandIK.data.target = weapon.OffHandGrip;
rigBuilder.Build(); // constraints read their source objects when the rig is built
offHandIK.weight = weapon.OffHandGrip != null ? 1f : 0f;
```

Fade `offHandIK.weight` to 0 during a reload, when the off hand leaves the gun.

!!! warning "Common pitfalls"

    `OnAnimatorIK` is never called without **IK Pass** on a layer, or when the script is not on the Animator's GameObject.

    Foot IK without lowering the hips cannot reach a step down. The foot floats above it.

    Foot IK at full weight in the air pulls the feet toward the ground below. Fade it out when not grounded.

    Changing a constraint's target or source object at runtime does nothing until the Rig Builder is rebuilt.

    Aiming the spine straight at a top-down cursor on the floor bends the character forward. Aim at chest height.
