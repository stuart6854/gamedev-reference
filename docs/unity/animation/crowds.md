---
engine: Unity
version: 6+
uses:
  - name: Hordes and crowds
    text: Hundreds of animated zombies, with far ones updated less often and the farthest drawn from baked textures.
  - name: Strategy and tactics
    text: Large armies where most units are too small on screen to need full animation.
  - name: Open worlds
    text: Townsfolk and wildlife that stop animating when nobody can see them.
---

# Crowd performance

Every `Animator` evaluates its state machine, samples its clips, writes bone transforms, and every `SkinnedMeshRenderer` skins its mesh. That is fine for a dozen characters and too much for hundreds. This page goes from free settings, to updating far characters less often, to dropping the Animator entirely for the [horde](../ai/horde.md)'s far tiers.

## Free settings

| Setting | Where | Effect |
| --- | --- | --- |
| **Culling Mode: Cull Completely** | Animator | No animation at all while no renderer of the character is visible. Unity's own advice for most characters. |
| **Cull Update Transforms** | Animator | Keeps the state machine and root motion running off screen, but skips retargeting, IK, and writing bones. Use it for characters whose root motion must keep moving them while unseen. |
| **Update When Offscreen** off | Skinned Mesh Renderer | Skips skinning and lets culling see the character as invisible. On is only for characters whose bounds are wrong. |
| **Optimize Game Objects** | Model import, **Rig** tab | Removes the bone GameObjects from the hierarchy, which makes writing the pose much cheaper. Bones you still need, such as a hand for a weapon, go in **Extra Transforms to Expose**. |
| **Skin Weights** | Quality settings, or per renderer | Fewer bones per vertex. Two is often enough at a distance. |
| **Mesh Deformation: GPU (Batched)** | Player settings | Skins on the GPU with compute shaders, and batches characters together. Check it on your target platforms. |
| **Generic rig** | Model import | No retargeting each frame. Use Humanoid only where its features are needed. |
| **No scale curves** | Clips | Scale curves cost more than position and rotation. Constant curves are almost free. |

`animator.fireEvents = false` on far characters stops their footstep and sound events too.

## Updating less often

Characters a little way off still need to move, but not 60 times a second. Turn off the Animator's own update and step it by hand, every few frames, with the time that has passed:

```csharp
using UnityEngine;

/// <summary>
/// Full-rate animation near the camera, stepped every few frames further out, frozen beyond that.
/// </summary>
public class AnimatorLod : MonoBehaviour
{
    [SerializeField] Animator animator;
    [SerializeField] float fullDistance = 15f;
    [SerializeField] float reducedDistance = 40f;
    [SerializeField, Min(2)] int reducedEvery = 3;

    /// <summary>What distance is measured from. The player, for a top-down game.</summary>
    public static Transform Focus { get; set; }

    static int s_nextOffset;
    int _offset;
    float _pending;

    void Awake()
    {
        _offset = s_nextOffset++; // spread the stepped characters across frames
        animator.keepAnimatorStateOnDisable = true; // or disabling resets the state
    }

    void Update()
    {
        if (Focus == null)
            return;

        float distanceSq = (transform.position - Focus.position).sqrMagnitude;

        if (distanceSq < fullDistance * fullDistance)
        {
            if (!animator.enabled)
                animator.enabled = true; // full rate, through the normal update
            _pending = 0f;
            return;
        }

        if (animator.enabled)
            animator.enabled = false;

        _pending += Time.deltaTime;
        if (distanceSq < reducedDistance * reducedDistance && (Time.frameCount + _offset) % reducedEvery == 0)
        {
            animator.Update(_pending); // catch up the time since the last step
            _pending = 0f;
        }
        // Beyond reduced distance: frozen. Moving characters there should be on a cheaper tier.
    }
}
```

- `Animator.Update(deltaTime)` evaluates once by the time given. Unity notes it may not suit physics, so keep stepped characters to Normal update mode, without `Rigidbody` root motion.
- Stepped characters animate at a lower rate, which reads as choppy close up and invisible at a distance. Raise **Full Distance** until it is not noticeable.
- The offset spreads stepped characters across frames, so every third frame is not a spike.
- [Pooled](scripting.md#pooled-characters) characters keep their offset; that is fine.

## Baked animation

Beyond a few hundred characters, the Animator and the `SkinnedMeshRenderer` are the cost, however rarely they update. The way past that is to bake the animation into textures ahead of time and play it in the vertex shader, on an ordinary `MeshRenderer` drawn with GPU instancing.

| Approach | Texture holds | Strengths | Limits |
| --- | --- | --- | --- |
| **Vertex animation textures** | Every vertex's position, per frame: one row per frame, one column per vertex. | Cheapest to play. No bones at runtime. | Big textures for detailed meshes. No attachments, IK, or ragdoll. |
| **Bone animation textures** | Every bone's matrix, per frame. The shader skins with them. | Smaller textures. Bone positions can be read for attachments. | More shader work per vertex. |

How it fits together:

1. **Bake, in the editor.** For each clip, sample it at a fixed rate, for example 30 frames per second, with `AnimationClip.SampleAnimation`. Read the posed mesh with `SkinnedMeshRenderer.BakeMesh`, or the bone matrices, and write them into a float texture. Store each clip's start row and frame count.
2. **Play, in the shader.** Each vertex finds its column from its vertex index, or from a UV channel written at bake time, and its row from the clip's start plus time times frame rate. Two rows sampled and blended give smooth motion between frames. Normals need their own texture, or the lighting stays in the bind pose.
3. **Per instance**, set the clip, the start time, and the speed through instanced material properties, so every zombie plays its own clip at its own phase.
4. **Switching clips** is a jump, or a short blend of two sampled poses in the shader. There is no state machine.

Use it for the [horde](../ai/horde.md)'s simple tier: agents that only walk, shamble, or idle. Promote an agent to a full prefab with an Animator when it gets close enough to attack, ragdoll, or need IK. The swap happens at a distance, where the change is hard to see.

Writing the baker and the shader is a project of its own. Several open-source and Asset Store tools exist for it; the table above is what to compare them on.

## Measuring

Before changing anything, look in the **Profiler**'s CPU view for the animation markers under `PreLateUpdate` (the `Director` animation updates) and the skinning markers, and in the **Frame Debugger** for how many skinned draws there are. Culling fixes characters off screen; update rates fix characters on screen but small; baking fixes characters that are simply too many.

!!! warning "Common pitfalls"

    **Update When Offscreen** on stops culling: the character is always treated as visible.

    **Cull Completely** on a character whose root motion moves it freezes it in place off screen. Use **Cull Update Transforms**, or move it with code.

    Disabling the Animator for LOD without **Keep Animator State On Disable** resets it to the entry state each time.

    **Optimize Game Objects** removes the bones a weapon or an effect was parented to. Expose them first.

    Stepping every far character on the same frame makes a spike every few frames. Offset them.
