# Mesh shaders

Mesh shaders replace the vertex input, vertex shader, and tessellation stages with two compute-like stages:

- The **amplification shader** (D3D12) or **task shader** (Vulkan) runs first, per group of work, and decides how many mesh shader groups to launch. It is where culling happens.
- The **mesh shader** runs as a thread group that outputs a small mesh directly: a list of vertices and a list of triangles indexing them.

Models are split offline into **meshlets**, small clusters of up to 64 vertices and about 124 triangles. Each mesh shader group draws one meshlet, and the amplification stage skips meshlets that are off-screen or facing away, before any of their vertices are processed. This is the GPU-driven geometry pipeline behind modern renderers with very high triangle counts.

| | D3D12 | Vulkan |
| --- | --- | --- |
| Requirement | Shader Model 6.5, `D3D12_MESH_SHADER_TIER_1` | `VK_EXT_mesh_shader`, features `meshShader` and `taskShader` |
| First stage | amplification shader (`as_6_5`) | task shader |
| Second stage | mesh shader (`ms_6_5`) | mesh shader |
| Pipeline | stream with `AS`, `MS`, `PS` subobjects | stages `TASK`, `MESH`, `FRAGMENT`; no vertex input or input assembly state |
| Draw | `DispatchMesh(x, y, z)` | `vkCmdDrawMeshTasksEXT(x, y, z)` |
| Indirect draw | `ExecuteIndirect` with a dispatch-mesh argument | `vkCmdDrawMeshTasksIndirectEXT` |

## Meshlets

```text
Meshlet { vertex_offset, triangle_offset, vertex_count, triangle_count }

meshlet_vertices[]    // indices into the mesh's vertex buffer, per meshlet
meshlet_triangles[]   // 3 small indices per triangle, into the meshlet's vertex list (one byte each)
bounds per meshlet    // a bounding sphere, and a normal cone for back-face culling
```

Build them at import time with [meshoptimizer](https://github.com/zeux/meshoptimizer) (`meshopt_buildMeshlets`, then `meshopt_computeMeshletBounds` for the culling data), and store them in the [cooked mesh](../../engine/content/import-cook.md). Sizes of 64 vertices and 124 triangles suit NVIDIA hardware well, and 64 and 64 to 128 work across vendors; keep both under the API's limit of 256.

## The shaders

```hlsl
struct Meshlet { uint vertexOffset; uint triangleOffset; uint vertexCount; uint triangleCount; };
struct Payload { uint meshletIndices[32]; };

StructuredBuffer<Meshlet> meshlets;
StructuredBuffer<uint>    meshletVertices;
StructuredBuffer<uint>    meshletTriangles;      // three 8-bit indices packed per uint
StructuredBuffer<Vertex>  vertices;

groupshared Payload payload;
groupshared uint    visibleCount;

// Amplification / task shader: one thread per meshlet, 32 meshlets per group.
[numthreads(32, 1, 1)]
void ASMain(uint gtid : SV_GroupThreadID, uint gid : SV_GroupID)
{
    if (gtid == 0) visibleCount = 0;
    GroupMemoryBarrierWithGroupSync();

    uint index = gid * 32 + gtid;
    if (index < pc.meshletCount && IsVisible(index))          // frustum, normal cone, and occlusion tests
    {
        uint slot;
        InterlockedAdd(visibleCount, 1, slot);                 // compact the visible meshlets
        payload.meshletIndices[slot] = index;
    }
    GroupMemoryBarrierWithGroupSync();

    DispatchMesh(visibleCount, 1, 1, payload);                 // called once, by every thread, with the same values
}

struct VertexOut { float4 position : SV_Position; float3 normal : NORMAL; };

// Mesh shader: one group per visible meshlet.
[outputtopology("triangle")]
[numthreads(64, 1, 1)]
void MSMain(uint gtid : SV_GroupThreadID, uint gid : SV_GroupID,
            in payload Payload payload,
            out vertices VertexOut verts[64],
            out indices uint3 tris[124])
{
    Meshlet m = meshlets[payload.meshletIndices[gid]];
    SetMeshOutputCounts(m.vertexCount, m.triangleCount);      // first, before writing any output

    if (gtid < m.vertexCount)
    {
        Vertex v = vertices[meshletVertices[m.vertexOffset + gtid]];
        verts[gtid].position = mul(pc.viewProjection, float4(v.position, 1));
        verts[gtid].normal = v.normal;
    }
    for (uint t = gtid; t < m.triangleCount; t += 64)          // more triangles than threads
    {
        uint packed = meshletTriangles[m.triangleOffset + t];
        tris[t] = uint3(packed & 0xFF, (packed >> 8) & 0xFF, (packed >> 16) & 0xFF);
    }
}
```

- **`SetMeshOutputCounts`** must be called once per group, with the same values in every thread, before any output is written. The counts must not exceed the array sizes in the signature.
- **The amplification shader compacts** the visible meshlets with a groupshared counter. A wave intrinsic (`WavePrefixCountBits`) is faster, but only correct when the group is a single wave, which depends on the GPU's wave size; the counter is correct everywhere.
- **The payload** is limited to 16 KB, and the output arrays to roughly 32 KB per mesh shader group. Small payloads and outputs leave room for more groups in flight.
- The same HLSL compiles to SPIR-V for `VK_EXT_mesh_shader` with a recent DXC (`-spirv -T ms_6_5`); old DXC versions only targeted NVIDIA's earlier extension.

### Culling a meshlet

```text
is_visible(meshlet):
    b = bounds[meshlet]
    if sphere (b.centre, b.radius) is outside the view frustum: return false     // see frustum tests
    if dot(normalize(b.cone_apex - camera_position), b.cone_axis) >= b.cone_cutoff:
        return false                                                              // every triangle faces away
    if sphere is hidden behind last frame's depth (a depth pyramid test): return false
    return true
```

The frustum test is the sphere test from [frustum and visibility](../../maths/frustum.md). The normal cone comes from `meshopt_computeMeshletBounds`, and rejects about half of a closed mesh's meshlets on average. Occlusion culling against a hierarchical depth buffer from the previous frame is what makes dense scenes cheap.

## The API side

=== "D3D12"

    ```cpp
    struct Stream
    {
        CD3DX12_PIPELINE_STATE_STREAM_ROOT_SIGNATURE        root;
        CD3DX12_PIPELINE_STATE_STREAM_AS                    as;
        CD3DX12_PIPELINE_STATE_STREAM_MS                    ms;
        CD3DX12_PIPELINE_STATE_STREAM_PS                    ps;
        CD3DX12_PIPELINE_STATE_STREAM_RENDER_TARGET_FORMATS formats;
    } stream;
    stream.root = rootSignature.Get();
    stream.as = asBytecode;
    stream.ms = msBytecode;
    stream.ps = psBytecode;
    D3D12_RT_FORMAT_ARRAY formats{ .RTFormats = { DXGI_FORMAT_R8G8B8A8_UNORM }, .NumRenderTargets = 1 };
    stream.formats = formats;
    D3D12_PIPELINE_STATE_STREAM_DESC desc{ sizeof(stream), &stream };
    HR_CHECK(device->CreatePipelineState(&desc, IID_PPV_ARGS(&meshPipeline)));

    // Recording: one amplification group per 32 meshlets.
    list->SetPipelineState(meshPipeline.Get());
    list->DispatchMesh((meshletCount + 31) / 32, 1, 1);
    ```

    Check `D3D12_FEATURE_DATA_D3D12_OPTIONS7::MeshShaderTier >= D3D12_MESH_SHADER_TIER_1` at start-up, and keep a vertex shader path for GPUs without it.

=== "Vulkan"

    ```cpp
    // Device creation: enable the extension and its features.
    VkPhysicalDeviceMeshShaderFeaturesEXT meshFeatures{ .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MESH_SHADER_FEATURES_EXT,
                                                        .taskShader = VK_TRUE, .meshShader = VK_TRUE };
    // ...chain it into VkDeviceCreateInfo::pNext, and add VK_EXT_MESH_SHADER_EXTENSION_NAME to the extensions...

    VkPipelineShaderStageCreateInfo stages[] = {
        { .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, .stage = VK_SHADER_STAGE_TASK_BIT_EXT,
          .module = as, .pName = "ASMain" },
        { .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, .stage = VK_SHADER_STAGE_MESH_BIT_EXT,
          .module = ms, .pName = "MSMain" },
        { .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, .stage = VK_SHADER_STAGE_FRAGMENT_BIT,
          .module = ps, .pName = "PSMain" },
    };
    VkGraphicsPipelineCreateInfo meshPipelineInfo = pipelineInfo;     // the graphics pipeline from the pipelines page
    meshPipelineInfo.stageCount = 3;
    meshPipelineInfo.pStages = stages;
    meshPipelineInfo.pVertexInputState = nullptr;                     // no vertex input or input assembly
    meshPipelineInfo.pInputAssemblyState = nullptr;
    VK_CHECK(vkCreateGraphicsPipelines(device, pipelineCache, 1, &meshPipelineInfo, nullptr, &meshPipeline));

    // Recording. The function comes from the extension, so load it once.
    auto drawMeshTasks = (PFN_vkCmdDrawMeshTasksEXT)vkGetDeviceProcAddr(device, "vkCmdDrawMeshTasksEXT");
    vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, meshPipeline);
    drawMeshTasks(cmd, (meshletCount + 31) / 32, 1, 1);
    ```

    Query `VkPhysicalDeviceMeshShaderPropertiesEXT` for the limits (`maxMeshOutputVertices`, `maxTaskPayloadSize`, the preferred group sizes) and size meshlets within them.

## When to use them

- **Dense geometry**: per-meshlet culling makes millions of triangles cheap when most are hidden. With few large meshes, the vertex shader path is as fast and simpler.
- **Mixed hardware**: GPUs from before 2018 (and some integrated GPUs) lack mesh shaders. Ship both paths, or a compute-based culling pass that writes a compacted index buffer and an indirect draw, which works everywhere and gives much of the benefit.
- **Fewer pipelines per material**: the vertex layout lives in the shader's buffer reads, not in pipeline state.

!!! warning "Common pitfalls"

    Calling `SetMeshOutputCounts` after writing outputs, more than once, or with different values per thread is undefined. Call it first, uniformly.

    Compacting visible meshlets with wave intrinsics assumes the thread group is one wave. On GPUs with smaller waves the indices collide; use a groupshared counter, or size the group to the queried wave size.

    `DispatchMesh` must be called exactly once by the whole amplification group, outside any divergent branch.

    Forgetting to enable `taskShader` as well as `meshShader` in Vulkan makes pipelines with a task stage invalid.

## C# tips

- Meshlet building belongs in the C# content pipeline: meshoptimizer has C bindings usable through P/Invoke, or call its command-line tool (`gltfpack`) during import.
- Store meshlets as structs with `[StructLayout(LayoutKind.Sequential)]` matching the HLSL `Meshlet` (four `uint`s), and write them straight into the cooked file with `MemoryMarshal.AsBytes`.
