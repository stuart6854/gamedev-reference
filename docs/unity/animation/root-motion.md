---
engine: Unity
version: 6+
uses:
  - name: Melee action
    text: Lunges and dodges that cover exactly the distance the animator authored.
  - name: Top-down survival
    text: In-place locomotion for control, with root motion only for vaults and finishers.
  - name: Companions and NPCs
    text: A NavMeshAgent that plans the path while the clips move the feet, with no sliding.
---

# Root motion

With root motion, the clip moves the character: the distance and turn baked into the animation are applied to the GameObject. Feet never slide, because the body moves exactly as far as the feet did. The cost is control. The character can only move as the clips allow, and speed, stopping, and turning feel heavier.

## When to use it

| Movement | Usually |
| --- | --- |
| Player locomotion in an action or top-down game | **In place.** The controller moves the body, and the [locomotion](locomotion.md) blend tree matches the legs to it. Responsive. |
| Attacks, dodges, lunges, finishers | **Root motion.** The step the animator authored is the step the character takes. |
| Vaults, climbs, ledge grabs | **Root motion** plus target matching, so the hand lands on the ledge. |
| NPC walking, cut-scenes, slow realistic characters | **Root motion** coupled to a `NavMeshAgent`. |

Mixing is normal: a controller moves the body most of the time and hands over to the clip for the moves that need it.

## Clip settings

On an imported clip's **Animation** tab, **Root Transform Rotation**, **Position (Y)**, and **Position (XZ)** each have **Bake Into Pose**. Baked parts stay on the skeleton and do not move the GameObject.

| Setting | Bake it when |
| --- | --- |
| **Rotation** | The clip should not turn the character: straight walks and runs, attacks forward. |
| **Position (Y)** | The clip should not change height. Almost always, except jumps and climbs. |
| **Position (XZ)** | The clip should not move the character: idles, and in-place clips. Stops slow drift from tiny deltas. |

The inspector shows a green light on settings the clip is a good candidate for. A clip with every part baked is an in-place clip, whatever **Apply Root Motion** says.

## Applying it yourself

**Apply Root Motion** on the Animator moves the transform directly. That ignores the `CharacterController`, collisions, and gravity. Instead, add `OnAnimatorMove` to a script on the Animator's GameObject. With that method present, Unity applies nothing itself, and the inspector shows **Handled by Script**. The script reads `animator.deltaPosition` and `deltaRotation` and moves the body the right way.

### CharacterController

```csharp
using UnityEngine;

/// <summary>
/// Applies root motion through a CharacterController while UseRootMotion is on.
/// Put it on the Animator's GameObject.
/// </summary>
[RequireComponent(typeof(Animator))]
public class RootMotionMover : MonoBehaviour
{
    [SerializeField] CharacterController body;
    [SerializeField] float gravity = -20f;

    /// <summary>On for attacks, dodges, and vaults. Off while the normal controller moves the body.</summary>
    public bool UseRootMotion { get; set; }

    Animator _animator;
    float _fallSpeed;

    void Awake() => _animator = GetComponent<Animator>();

    void OnAnimatorMove()
    {
        if (!UseRootMotion || body == null)
            return;

        float dt = Time.deltaTime;
        _fallSpeed = body.isGrounded ? -1f : _fallSpeed + gravity * dt;

        Vector3 move = _animator.deltaPosition;
        move.y = _fallSpeed * dt;
        body.Move(move);
        body.transform.rotation *= _animator.deltaRotation;
    }
}
```

- The `CharacterController` is usually on the root and the Animator on the model child. Moving the root moves both.
- While `UseRootMotion` is on, the normal movement script must stop moving the body, or the two add up. The gameplay state that starts the dodge sets both.
- `deltaPosition` is world space and already scaled by `animator.speed`.

### Rigidbody

Set the Animator's **Update Mode** to **Fixed**, so root motion is produced in step with physics, and turn the delta into a velocity:

```csharp
void OnAnimatorMove()
{
    if (!UseRootMotion)
        return;

    float dt = Time.deltaTime; // the fixed step, in Fixed update mode
    Vector3 velocity = _animator.deltaPosition / dt;
    velocity.y = body.linearVelocity.y; // keep gravity
    body.linearVelocity = velocity;
    body.MoveRotation(body.rotation * _animator.deltaRotation);
}
```

### NavMeshAgent

The agent plans and steers. The clip moves the feet. The agent is told not to move the transform, and its planned next position becomes the locomotion parameters.

```csharp
using UnityEngine;
using UnityEngine.AI;

/// <summary>
/// Drives locomotion from a NavMeshAgent's path and moves the body with root motion.
/// Put it on the GameObject with both the agent and the Animator.
/// </summary>
[RequireComponent(typeof(NavMeshAgent), typeof(Animator))]
public class AgentRootMotion : MonoBehaviour
{
    static readonly int MoveX = Animator.StringToHash("MoveX");
    static readonly int MoveZ = Animator.StringToHash("MoveZ");

    [Tooltip("Speed of the run clip, in metres per second.")]
    [SerializeField] float runSpeed = 4f;
    [SerializeField] float dampTime = 0.1f;

    NavMeshAgent _agent;
    Animator _animator;

    void Awake()
    {
        _agent = GetComponent<NavMeshAgent>();
        _animator = GetComponent<Animator>();
        _agent.updatePosition = false; // the clip moves the body
        _agent.updateRotation = true;  // the agent still turns it
    }

    void Update()
    {
        float dt = Time.deltaTime;
        if (dt <= 0f)
            return;

        Vector3 toAgent = _agent.nextPosition - transform.position;
        toAgent.y = 0f;

        // Ask for the speed that closes the gap this frame, capped at the agent's speed.
        Vector3 wanted = Vector3.ClampMagnitude(toAgent / dt, _agent.speed);
        if (_agent.remainingDistance <= _agent.stoppingDistance && !_agent.pathPending)
            wanted = Vector3.zero;

        Vector3 local = transform.InverseTransformDirection(wanted) / runSpeed;
        _animator.SetFloat(MoveX, local.x, dampTime, dt);
        _animator.SetFloat(MoveZ, local.z, dampTime, dt);

        // Do not let the agent run far ahead of the body.
        if (toAgent.magnitude > _agent.radius)
            _agent.nextPosition = transform.position + toAgent * 0.9f;
    }

    void OnAnimatorMove()
    {
        Vector3 position = _animator.rootPosition;
        position.y = _agent.nextPosition.y; // the mesh decides height
        transform.position = position;
    }
}
```

- `updatePosition = false` keeps the agent simulating, at `nextPosition`, without touching the transform.
- Pulling `nextPosition` back to the body stops the agent from leading by metres when the clips are slower than it.
- Using the agent's height keeps the body on stairs and slopes, which a flat clip does not climb.

## Target matching

For a vault or a ledge grab, the clip's hand has to land on the actual ledge, at whatever height and distance it is. `MatchTarget` bends the root motion during part of a clip so that a chosen body part reaches a point. Humanoid only.

```csharp
// After starting the vault state, while it plays:
AnimatorStateInfo state = animator.GetCurrentAnimatorStateInfo(0);
if (state.IsName("Vault") && !animator.isMatchingTarget && !animator.IsInTransition(0))
{
    animator.MatchTarget(
        ledgePoint, Quaternion.identity, AvatarTarget.LeftHand,
        new MatchTargetWeightMask(Vector3.one, 0f), // match position, not rotation
        0.15f, 0.35f);                              // normalised start and end time in the clip
}
```

The window is the part of the clip where the hand travels to the ledge. Find it by scrubbing the clip. Root motion must be on for the clip, through **Apply Root Motion** or an `OnAnimatorMove` that applies it.

!!! warning "Common pitfalls"

    **Apply Root Motion** on a character with a `CharacterController` moves it through walls. Apply the delta through `Move` in `OnAnimatorMove`.

    A script with an empty `OnAnimatorMove` stops all root motion, because Unity then leaves it to the script.

    A clip with **Bake Into Pose** off for XZ on an idle drifts the character slowly across the map.

    Root motion with a `Rigidbody` in **Normal** update mode stutters against physics. Use **Fixed**.

    A `NavMeshAgent` with `updatePosition` on and root motion on both move the body, and it doubles its speed.
