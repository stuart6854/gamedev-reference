# Skinning

Skinning deforms the character's mesh to follow its skeleton. Each vertex is attached to a few bones with weights, and moves with them.

## Bind pose and skinning matrices

The mesh is modelled around the skeleton in its **bind pose** (usually a T-pose or A-pose). For each bone, store the **inverse bind matrix**: the transform from model space into that bone's space, in the bind pose.

```text
// Once per frame, per character, after the pose is final:
model[0] = local_matrix(pose, 0)
for bone in 1 .. bone_count - 1:
    model[bone] = model[parent[bone]] * local_matrix(pose, bone)

skin[bone] = model[bone] * inverse_bind[bone]
```

`skin[bone]` takes a vertex from its bind-pose position to where the bone's movement puts it. In the bind pose, every skin matrix is the identity.

## Linear blend skinning

```hlsl
struct SkinnedVertex {
    float3 position; float3 normal; float4 tangent; float2 uv;
    uint4  bones;      // up to 4 bone indices (often 8-bit each)
    float4 weights;    // sum to 1 (often 8-bit unorm each)
};

StructuredBuffer<float3x4> skin_matrices;      // this character's matrices

float3x4 m = skin_matrices[v.bones.x] * v.weights.x
           + skin_matrices[v.bones.y] * v.weights.y
           + skin_matrices[v.bones.z] * v.weights.z
           + skin_matrices[v.bones.w] * v.weights.w;

float3 position = mul(m, float4(v.position, 1.0));
float3 normal   = normalize(mul((float3x3)m, v.normal));
```

- **Four influences** per vertex is the usual limit. The importer keeps the four largest weights and renormalises them to sum to 1. Weights that do not sum to 1 make vertices drift away from the bones.
- Store skin matrices as **3×4** (the last row is always 0, 0, 0, 1), saving a quarter of the upload and bandwidth.
- Normals use the same blended matrix. That is only exactly right without non-uniform scale; skeletons with stretchy bones need the inverse transpose, or tolerate the small error.

### The candy-wrapper problem

Linear blending of matrices does not preserve volume. A forearm twisting 180° between two bones collapses to a point in the middle, like a twisted sweet wrapper, and elbows and shoulders lose volume when bent sharply.

- **Twist bones**: add helper bones along the forearm and upper arm that take part of the twist each, driven by the animation or by a constraint. Each joint then only blends a small angle. This is the most common fix.
- **Dual quaternion skinning** blends rigid transforms as dual quaternions, which keeps volume under twisting. It costs a little more, can bulge at bent joints instead, and does not support scale. Some engines use it per mesh, or blend between the two methods per vertex.

## Where to skin

| Approach | How | Use when |
| --- | --- | --- |
| Vertex shader | Skin in each pass's vertex shader | Simple; few passes per character |
| Compute pre-skinning | A compute shader writes skinned vertices to a buffer once per frame; every pass reads it like a static mesh | Many passes (depth, shadows for several lights, G-buffer, motion vectors), or ray tracing, which needs the skinned geometry in its acceleration structure |
| CPU | Skin on the CPU and upload | Only for collision or gameplay queries against the deformed mesh |

With several shadow-casting lights, vertex-shader skinning repeats the same work in every shadow pass. Compute pre-skinning does it once.

**Motion vectors** (for TAA and motion blur) need each vertex's position last frame too: keep last frame's skin matrices (or last frame's pre-skinned buffer) and skin with both.

## The pipeline as jobs

Every animated character runs the same steps, independent of the others:

```text
for character in visible and nearby characters:          // one job per character, or per batch
    evaluate the graph: sample, blend                      // see blending and graphs
    extract root motion
    apply IK
    local to model space
    skin matrices -> the character's slot in a big per-frame buffer
```

- The output goes into one large **upload buffer** for all characters (see [frames in flight](../rendering/frames-in-flight.md#per-frame-data-the-upload-ring)), and each character's draw gets the offset of its matrices.
- Gameplay that needs bone positions (a sword attached to a hand, a muzzle position) reads the model-space pose after this step. Run the animation update before gameplay systems that read bones, and after the ones that set the animation's parameters, as phases of the [frame](../patterns/frame.md#phases).

## Level of detail

Animation cost scales with the number of characters, and distant characters do not need full quality:

- **Update rate**: animate distant characters every second or fourth frame, staggered across characters so the cost is even, and hold or extrapolate the pose between updates.
- **Skeleton LOD**: skip finger, face, and twist bones on distant characters (their skin matrices keep the parent's motion).
- **Mesh LOD**: fewer vertices and fewer influences per vertex (two, or one) at a distance.
- **Off-screen**: characters out of view only need what gameplay reads (the root, perhaps a few bones), or nothing at all.
- **Baked animation** for crowds: store a few animations' skin matrices (or vertex positions) in a texture, and let the vertex shader sample it by instance and time. Thousands of characters cost almost no CPU. The [crowd performance](../../unity/animation/crowds.md) page covers this in Unity.
