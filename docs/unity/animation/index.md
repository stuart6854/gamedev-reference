---
engine: Unity
version: 6+
---

# Animation

Characters driven by the Animator, then the parts the Animator alone does not do: feet on uneven ground, aiming, ragdolls, legs that step on their own, and hundreds of animated agents at once.

| Page | Covers |
| --- | --- |
| [Locomotion and layers](locomotion.md) | Blend trees for movement in any direction relative to facing, upper-body layers with avatar masks, and override controllers per weapon. |
| [Driving the Animator from code](scripting.md) | Parameter hashes, damping, triggers and bools, reading state, one component that owns the Animator, update modes, and resetting pooled characters. |
| [Animation events and timing](events.md) | Events on clips and who receives them, events in blend trees and cross-fades, curves, and state behaviours. |
| [Root motion](root-motion.md) | When the clip should move the character, with a CharacterController, a Rigidbody, or a NavMeshAgent, and target matching. |
| [IK and aiming](ik.md) | Humanoid foot IK and look-at, then Animation Rigging for aiming a weapon and placing the off hand. |
| [Ragdolls](ragdolls.md) | Switching from animation to physics on death, impulses on the hit bone, and blending back into a get-up. |
| [Procedural legs](procedural-legs.md) | Feet that plant and step for spiders and mechs, with body height and tilt from the feet. |
| [Crowd performance](crowds.md) | Culling, update rates, skinning settings, and baked animation for crowds too big for Animators. |

## Humanoid or Generic

Set on the model's **Rig** tab when it is imported.

| Rig | Use it when | Cost |
| --- | --- | --- |
| **Humanoid** | Clips are shared between differently proportioned characters, or the built-in foot IK, look-at, and target matching are wanted. | Retargeting runs every frame. Clips are stored as muscle curves. |
| **Generic** | One skeleton per clip set, creatures, and anything not two-armed and two-legged. Crowds. | No retargeting. IK comes from Animation Rigging, not `OnAnimatorIK`. |

Mixed projects are normal: Humanoid for people, Generic for animals and monsters.

## Who decides

The Animator shows what the game decided. It does not decide. The gameplay [state machine](../architecture/state-machines.md#animator) owns "am I attacking", and the Animator plays the clip for it. Reading the Animator's current state back to answer gameplay questions makes the two disagree during every cross-fade. The pages below keep that split: gameplay code calls one component, which sets parameters.
