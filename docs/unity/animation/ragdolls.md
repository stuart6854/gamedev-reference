---
engine: Unity
version: 6+
uses:
  - name: Top-down survival
    text: Zombies that drop where they are shot, pushed the way the bullet went.
  - name: Melee action
    text: Knockdowns that ragdoll for a moment, then blend into a get-up.
  - name: Hordes and crowds
    text: Bone colliders that are hurtboxes while alive and a ragdoll when dead.
---

# Ragdolls

A ragdoll is the character's skeleton as physics bodies joined at the joints. While the character is alive, the bodies are kinematic and follow the animation, and their colliders double as per-limb [hurtboxes](../systems/health.md#hurtbox-and-hitbox). On death, the Animator stops and the bodies become dynamic, keeping the character's momentum plus the hit's push. A get-up blends from wherever the ragdoll fell back into an animation.

## Building one

Unity's **Ragdoll Wizard** adds a `Rigidbody`, a collider, and a `CharacterJoint` to each main bone of a skinned character. **Auto-Fill** assigns the bones from a Humanoid's Animator. The Unity 6 manual covers opening it, under **Physics → Ragdoll physics**.

Then, by hand:

- Put the bone colliders on a **Ragdoll** layer that does not collide with the character's own capsule, in **Project Settings → Physics → Layer Collision Matrix**. Otherwise the live bones push against the `CharacterController` from inside.
- Keep masses within a factor of about ten of each other. Large mass ratios jitter.
- Avoid joint angle limits under about 5 degrees. Use 0 to lock an axis instead.
- Raise **Default Solver Iterations** to 10 or more in the Physics settings if the ragdoll jitters.
- Tick **Enable Projection** on the joints if limbs stretch apart when pushed hard.

## Switching to physics

```csharp
using UnityEngine;

/// <summary>
/// Switches a character between animation and ragdoll physics. Pushes the hit bone on death.
/// </summary>
public class Ragdoll : MonoBehaviour
{
    [SerializeField] Animator animator;
    [SerializeField] Rigidbody hips;
    [Tooltip("Turned off while ragdolled: the controller, agent, brain, and movement scripts.")]
    [SerializeField] Behaviour[] disableWhileRagdoll;
    [Tooltip("The character's own colliders, such as the CharacterController.")]
    [SerializeField] Collider[] rootColliders;
    [SerializeField] Health health;
    [SerializeField] float hitImpulse = 4f;

    Rigidbody[] _bodies;
    Vector3 _lastPosition;
    Vector3 _velocity;
    DamageInfo _lastHit;

    public bool IsRagdoll { get; private set; }
    public Rigidbody Hips => hips;
    public Rigidbody[] Bodies => _bodies;

    void Awake()
    {
        _bodies = hips.GetComponentsInChildren<Rigidbody>();
        SetRagdoll(false);
    }

    void OnEnable()
    {
        _lastPosition = transform.position;
        if (health != null)
        {
            health.Damaged += OnDamaged;
            health.Died += OnDied;
        }
    }

    void OnDisable()
    {
        if (health != null)
        {
            health.Damaged -= OnDamaged;
            health.Died -= OnDied;
        }
    }

    void Update()
    {
        if (Time.deltaTime > 0f && !IsRagdoll)
            _velocity = (transform.position - _lastPosition) / Time.deltaTime;
        _lastPosition = transform.position;
    }

    void OnDamaged(DamageInfo info, float amount) => _lastHit = info;

    void OnDied()
    {
        SetRagdoll(true);
        Push(_lastHit.Point, -_lastHit.Normal * hitImpulse);
    }

    public void SetRagdoll(bool on)
    {
        IsRagdoll = on;
        animator.enabled = !on;

        foreach (Rigidbody body in _bodies)
        {
            body.isKinematic = !on;
            body.interpolation = on ? RigidbodyInterpolation.Interpolate : RigidbodyInterpolation.None;
            if (on)
                body.linearVelocity = _velocity; // keep running momentum
        }

        foreach (Behaviour b in disableWhileRagdoll)
        {
            if (b != null)
                b.enabled = !on;
        }
        foreach (Collider c in rootColliders)
        {
            if (c != null)
                c.enabled = !on;
        }
    }

    /// <summary>Pushes the bone nearest the point. Also usable for explosions and kicks on a live ragdoll.</summary>
    public void Push(Vector3 point, Vector3 impulse)
    {
        Rigidbody nearest = hips;
        float best = float.MaxValue;
        foreach (Rigidbody body in _bodies)
        {
            float d = (body.worldCenterOfMass - point).sqrMagnitude;
            if (d < best)
            {
                best = d;
                nearest = body;
            }
        }
        nearest.AddForceAtPosition(impulse, point, ForceMode.Impulse);
    }
}
```

- `Health`, `DamageInfo`, and the `Damaged` and `Died` events are from [health](../systems/health.md). `Normal` points back toward the attacker, so the push is its opposite.
- Velocity is measured from the root's movement, so a running zombie falls forward instead of dropping straight down.
- Kinematic bones follow the Animator and still collide and receive raycasts, which is what makes them hurtboxes. Put a `Hurtbox` on each bone collider, with a multiplier for the head.
- A camera that follows the root stops following the body, because the root stays where the character died. Follow `Hips` while ragdolled.

## Getting up

A knockdown that recovers, or a zombie that rises again. Standing up straight from the ragdoll pose pops. The usual fix:

1. Wait until the hips have nearly stopped.
2. Decide face up or face down from the hips' facing, and pick the matching get-up clip.
3. Move the root under the hips and turn it to the clip's facing, without moving the bones.
4. Record every bone's pose, switch the Animator back on at the first frame of the get-up, and blend from the recorded pose to the animated one over a fraction of a second.

```csharp
using System.Collections;
using UnityEngine;

/// <summary>
/// Blends a ragdoll back into a face-up or face-down get-up clip.
/// </summary>
[RequireComponent(typeof(Ragdoll))]
public class RagdollGetUp : MonoBehaviour
{
    [SerializeField] Transform head;
    [SerializeField] string faceUpState = "GetUpFaceUp";
    [SerializeField] string faceDownState = "GetUpFaceDown";
    [Tooltip("The hips' local axis that points out of the chest.")]
    [SerializeField] Vector3 hipsFrontAxis = Vector3.forward;
    [Tooltip("Tick if, at the clip's first frame, the head points away from the character's forward.")]
    [SerializeField] bool headBehindWhenFaceUp = true;
    [SerializeField] float settleSpeed = 0.2f;
    [SerializeField] float settleTime = 0.5f;
    [SerializeField] float blendTime = 0.4f;
    [SerializeField] LayerMask ground = ~0;

    Ragdoll _ragdoll;
    Animator _animator;
    Transform[] _bones;
    Vector3[] _positions;
    Quaternion[] _rotations;
    float _blend = -1f;

    public bool IsGettingUp { get; private set; }

    void Awake()
    {
        _ragdoll = GetComponent<Ragdoll>();
        _animator = GetComponentInChildren<Animator>();
        _bones = _ragdoll.Hips.GetComponentsInChildren<Transform>(); // parents before children
        _positions = new Vector3[_bones.Length];
        _rotations = new Quaternion[_bones.Length];
    }

    public void StartGetUp() => StartCoroutine(GetUp());

    IEnumerator GetUp()
    {
        IsGettingUp = true;

        float still = 0f;
        while (still < settleTime)
        {
            still = _ragdoll.Hips.linearVelocity.magnitude < settleSpeed ? still + Time.deltaTime : 0f;
            yield return null;
        }

        Transform hips = _ragdoll.Hips.transform;
        bool faceUp = Vector3.Dot(hips.TransformDirection(hipsFrontAxis), Vector3.up) > 0f;

        Record();

        // Root under the hips, facing along the body.
        Vector3 rootPosition = hips.position;
        if (Physics.Raycast(hips.position + Vector3.up, Vector3.down, out RaycastHit hit, 3f, ground, QueryTriggerInteraction.Ignore))
            rootPosition.y = hit.point.y;

        Vector3 along = Vector3.ProjectOnPlane(head.position - hips.position, Vector3.up).normalized;
        if (faceUp && headBehindWhenFaceUp)
            along = -along;
        transform.SetPositionAndRotation(rootPosition, Quaternion.LookRotation(along, Vector3.up));

        Restore(); // moving the root moved the bones; put them back where they lay

        _ragdoll.SetRagdoll(false);
        _animator.Play(faceUp ? faceUpState : faceDownState, 0, 0f);
        _blend = 0f;

        while (_blend >= 0f)
            yield return null;
        IsGettingUp = false;
    }

    void LateUpdate()
    {
        if (_blend < 0f)
            return;

        // After the Animator has written this frame's pose: blend from the recorded ragdoll pose to it.
        _blend += Time.deltaTime / blendTime;
        float t = Mathf.Clamp01(_blend);
        for (int i = 0; i < _bones.Length; i++)
        {
            if (i == 0)
                _bones[i].position = Vector3.Lerp(_positions[i], _bones[i].position, t);
            _bones[i].rotation = Quaternion.Slerp(_rotations[i], _bones[i].rotation, t);
        }

        if (_blend >= 1f)
            _blend = -1f;
    }

    void Record()
    {
        for (int i = 0; i < _bones.Length; i++)
        {
            _positions[i] = _bones[i].position;
            _rotations[i] = _bones[i].rotation;
        }
    }

    void Restore()
    {
        for (int i = 0; i < _bones.Length; i++)
            _bones[i].SetPositionAndRotation(_positions[i], _rotations[i]);
    }
}
```

- The get-up clip's first frame should be lying flat, close to how a ragdoll settles. The closer it is, the shorter the blend can be.
- Only the hips blend position. The other bones follow through rotation, as the skeleton does.
- The brain stays off until `IsGettingUp` is false. Movement and the agent come back on with the Animator, so the brain must not issue moves during the blend.
- `GetComponentsInChildren` lists parents before children. Setting world rotations in that order is what keeps children correct.

## Hit reactions without dying

Full ragdolls on every hit look like puppets. For live hits:

- An additive **flinch** layer with a clip per direction, played with [`PlayHit`](scripting.md#one-owner) and chosen from the hit direction relative to facing.
- A short knockdown: ragdoll, push, then get up.
- An active ragdoll, where joints are driven toward the animated pose so the character staggers physically, is a larger topic and is not covered here.

## Pooled characters

A pooled character comes back with its bones where the last death left them. Store every bone's local position and rotation in `Awake`, and restore them on reuse along with [`Rebind`](scripting.md#pooled-characters), before `SetRagdoll(false)`.

!!! warning "Common pitfalls"

    Bone colliders on the same layer as the character's capsule push it around while alive. Separate the layers.

    A ragdoll switched on with zero velocity drops straight down mid-run. Copy the character's velocity to the bones.

    Leaving the `CharacterController` or `NavMeshAgent` on fights the ragdoll for the root. Disable them while ragdolled.

    Standing straight up from the ragdoll pose pops. Move the root under the hips, then blend from the recorded pose.

    Interpolation on all bones while animated costs for nothing. Turn it on only while ragdolled, as `SetRagdoll` does.
