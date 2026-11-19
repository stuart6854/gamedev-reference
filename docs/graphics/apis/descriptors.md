# Descriptors and binding

A **descriptor** is a small record the GPU reads to find a resource: a texture's address, format, and mip range, or a buffer's address and size. Shaders do not see resources directly, only descriptors. Both APIs make the application allocate descriptors, write them, and tell the GPU where they are.

| Concept | D3D12 | Vulkan |
| --- | --- | --- |
| Descriptor storage | `ID3D12DescriptorHeap` (CBV/SRV/UAV, sampler, RTV, DSV) | `VkDescriptorPool` → `VkDescriptorSet` |
| Writing a descriptor | `CreateShaderResourceView(resource, desc, cpuHandle)` | `vkUpdateDescriptorSets` |
| What a shader can bind | `ID3D12RootSignature` | `VkPipelineLayout` (set layouts + push constant ranges) |
| Small inline constants | root constants (up to 64 DWORDs in total) | push constants (128 bytes guaranteed, 256 common) |
| A group of descriptors | descriptor table (a range of a heap) | descriptor set |
| Bindless | Shader Model 6.6 `ResourceDescriptorHeap[i]`, or unbounded tables | descriptor indexing: large arrays, partially bound, update after bind |
| Render target views | RTV / DSV heaps, CPU-only | none: image views passed to `vkCmdBeginRendering` |

## Bindless: one big table

The traditional model binds a few descriptors per draw (this material's three textures, this object's constant buffer). It means many small updates per frame, and a different layout per shader. The modern model is **bindless**:

1. Every texture and buffer gets a descriptor in **one large array**, once, when it is loaded. Its **index** in the array is a plain integer.
2. That array is bound **once per frame** (or once ever).
3. Draws pass indices in push or root constants, or in a buffer of per-object data, and shaders index the array.

This removes per-draw descriptor work, lets every shader share one layout, and is what GPU-driven rendering needs. Both APIs support it on all hardware the [modern baseline](index.md#versions) covers.

### The shader

One HLSL file for both APIs. The `[[vk::...]]` attributes are ignored when compiling for D3D12, and the `register(...)` assignments are ignored for Vulkan (where the attributes give the binding).

```hlsl
struct PushConstants
{
    uint   textureIndex;
    float4 tint;                                    // offset 16: HLSL packs a float4 on a 16-byte boundary
};
[[vk::push_constant]] ConstantBuffer<PushConstants> pc : register(b0);

[[vk::binding(0, 0)]] Texture2D    textures[]    : register(t0, space1);   // all textures, one array
[[vk::binding(1, 0)]] SamplerState linearSampler : register(s0);

float4 PSMain(VSOut i) : SV_Target
{
    // The index comes from push constants, so it is the same for every pixel of the draw.
    return textures[pc.textureIndex].Sample(linearSampler, i.uv) * pc.tint;
}
```

**`NonUniformResourceIndex`**: when the index can **differ between pixels or threads of one draw** (read from a per-pixel material ID, or a per-instance value in a buffer), wrap it: `textures[NonUniformResourceIndex(materialId)]`. Without it, GPUs that load one descriptor per wave use whichever index the first lane had, and objects show the wrong texture. With a push constant, as here, the index is uniform and the wrapper is not needed.

### The layout

=== "D3D12"

    ```cpp
    D3D12_DESCRIPTOR_RANGE1 textures{
        .RangeType = D3D12_DESCRIPTOR_RANGE_TYPE_SRV,
        .NumDescriptors = UINT_MAX,                                    // unbounded: Texture2D textures[]
        .BaseShaderRegister = 0, .RegisterSpace = 1,                   // t0, space1
        .Flags = D3D12_DESCRIPTOR_RANGE_FLAG_DESCRIPTORS_VOLATILE,      // slots may be empty or change while bound
        .OffsetInDescriptorsFromTableStart = 0 };
    D3D12_ROOT_PARAMETER1 params[2] = {
        { .ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS,
          .Constants = { .ShaderRegister = 0, .RegisterSpace = 0, .Num32BitValues = 8 },        // b0: 32 bytes of constants
          .ShaderVisibility = D3D12_SHADER_VISIBILITY_ALL },
        { .ParameterType = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE,
          .DescriptorTable = { .NumDescriptorRanges = 1, .pDescriptorRanges = &textures },
          .ShaderVisibility = D3D12_SHADER_VISIBILITY_ALL },
    };
    D3D12_STATIC_SAMPLER_DESC sampler{ .Filter = D3D12_FILTER_MIN_MAG_MIP_LINEAR,
                                       .AddressU = D3D12_TEXTURE_ADDRESS_MODE_WRAP, .AddressV = D3D12_TEXTURE_ADDRESS_MODE_WRAP,
                                       .AddressW = D3D12_TEXTURE_ADDRESS_MODE_WRAP, .MaxLOD = D3D12_FLOAT32_MAX,
                                       .ShaderRegister = 0, .ShaderVisibility = D3D12_SHADER_VISIBILITY_ALL };   // s0
    D3D12_VERSIONED_ROOT_SIGNATURE_DESC desc{ .Version = D3D_ROOT_SIGNATURE_VERSION_1_1 };
    desc.Desc_1_1 = { .NumParameters = 2, .pParameters = params, .NumStaticSamplers = 1, .pStaticSamplers = &sampler };

    ComPtr<ID3DBlob> blob, error;
    if (FAILED(D3D12SerializeVersionedRootSignature(&desc, &blob, &error)))
        std::fprintf(stderr, "%s\n", (const char*)error->GetBufferPointer());    // a readable reason
    HR_CHECK(device->CreateRootSignature(0, blob->GetBufferPointer(), blob->GetBufferSize(), IID_PPV_ARGS(&rootSignature)));
    ```

=== "Vulkan"

    ```cpp
    const uint32_t MaxTextures = 100'000;             // within maxDescriptorSetUpdateAfterBindSampledImages
    VkDescriptorSetLayoutBinding bindings[] = {
        { .binding = 0, .descriptorType = VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE, .descriptorCount = MaxTextures,
          .stageFlags = VK_SHADER_STAGE_ALL },
        { .binding = 1, .descriptorType = VK_DESCRIPTOR_TYPE_SAMPLER, .descriptorCount = 1,
          .stageFlags = VK_SHADER_STAGE_ALL },
    };
    VkDescriptorBindingFlags bindingFlags[] = {
        VK_DESCRIPTOR_BINDING_PARTIALLY_BOUND_BIT |        // unused slots may be empty
        VK_DESCRIPTOR_BINDING_UPDATE_AFTER_BIND_BIT,       // slots may be written while the set is bound
        0,
    };
    VkDescriptorSetLayoutBindingFlagsCreateInfo flagsInfo{
        .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_BINDING_FLAGS_CREATE_INFO,
        .bindingCount = 2, .pBindingFlags = bindingFlags };
    VkDescriptorSetLayoutCreateInfo setLayoutInfo{
        .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO, .pNext = &flagsInfo,
        .flags = VK_DESCRIPTOR_SET_LAYOUT_CREATE_UPDATE_AFTER_BIND_POOL_BIT,
        .bindingCount = 2, .pBindings = bindings };
    VK_CHECK(vkCreateDescriptorSetLayout(device, &setLayoutInfo, nullptr, &bindlessLayout));

    // The pool must allow update-after-bind too. One set for the whole renderer.
    VkDescriptorPoolSize poolSizes[] = { { VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE, MaxTextures }, { VK_DESCRIPTOR_TYPE_SAMPLER, 1 } };
    VkDescriptorPoolCreateInfo poolInfo{ .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
                                         .flags = VK_DESCRIPTOR_POOL_CREATE_UPDATE_AFTER_BIND_BIT,
                                         .maxSets = 1, .poolSizeCount = 2, .pPoolSizes = poolSizes };
    VK_CHECK(vkCreateDescriptorPool(device, &poolInfo, nullptr, &descriptorPool));
    VkDescriptorSetAllocateInfo setAlloc{ .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,
                                          .descriptorPool = descriptorPool, .descriptorSetCount = 1,
                                          .pSetLayouts = &bindlessLayout };
    VK_CHECK(vkAllocateDescriptorSets(device, &setAlloc, &bindlessSet));

    // The pipeline layout: the bindless set plus 32 bytes of push constants.
    VkPushConstantRange pushRange{ .stageFlags = VK_SHADER_STAGE_ALL, .offset = 0, .size = 32 };
    VkPipelineLayoutCreateInfo layoutInfo{ .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
                                           .setLayoutCount = 1, .pSetLayouts = &bindlessLayout,
                                           .pushConstantRangeCount = 1, .pPushConstantRanges = &pushRange };
    VK_CHECK(vkCreatePipelineLayout(device, &layoutInfo, nullptr, &pipelineLayout));
    ```

    The device needs the descriptor indexing features enabled: `descriptorIndexing`, `runtimeDescriptorArray`, `descriptorBindingPartiallyBound`, and `descriptorBindingSampledImageUpdateAfterBind` (see [devices](devices.md#the-device)).

### Registering a resource

=== "D3D12"

    ```cpp
    // One shader-visible CBV/SRV/UAV heap for the whole renderer (up to 1,000,000 descriptors on tier 3).
    D3D12_DESCRIPTOR_HEAP_DESC heapDesc{ .Type = D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV, .NumDescriptors = 100'000,
                                         .Flags = D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE };
    HR_CHECK(device->CreateDescriptorHeap(&heapDesc, IID_PPV_ARGS(&heap)));
    UINT increment = device->GetDescriptorHandleIncrementSize(D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);

    // Write a texture's descriptor into slot `index`.
    D3D12_SHADER_RESOURCE_VIEW_DESC srv{ .Format = DXGI_FORMAT_R8G8B8A8_UNORM, .ViewDimension = D3D12_SRV_DIMENSION_TEXTURE2D,
                                         .Shader4ComponentMapping = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING,
                                         .Texture2D = { .MipLevels = 1 } };
    D3D12_CPU_DESCRIPTOR_HANDLE slot{ heap->GetCPUDescriptorHandleForHeapStart().ptr + SIZE_T(index) * increment };
    device->CreateShaderResourceView(texture, &srv, slot);
    ```

=== "Vulkan"

    ```cpp
    VkDescriptorImageInfo imageInfo{ .imageView = texture.view, .imageLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL };
    VkWriteDescriptorSet write{ .sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstSet = bindlessSet,
                                .dstBinding = 0, .dstArrayElement = index,      // slot `index` of textures[]
                                .descriptorCount = 1, .descriptorType = VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE,
                                .pImageInfo = &imageInfo };
    vkUpdateDescriptorSets(device, 1, &write, 0, nullptr);
    ```

- Hand out indices from a **free list** (see [handle tables](../../data-structures/handle-table.md)), so unloading a texture frees its slot for the next one.
- **Do not reuse a slot immediately.** Frames still in flight may be using the old descriptor. Put freed indices on a queue and return them to the free list only after that frame's fence value has passed, as with any [deferred deletion](../../engine/rendering/frames-in-flight.md).
- Writing a descriptor that a submitted frame **might** read is a race. With update-after-bind (Vulkan) and `DESCRIPTORS_VOLATILE` (D3D12) it is allowed for slots the GPU does not actually read; never overwrite a slot that is in use.

### Recording

=== "D3D12"

    ```cpp
    ID3D12DescriptorHeap* heaps[] = { heap.Get() };          // plus the sampler heap, if you use one
    list->SetDescriptorHeaps(1, heaps);                      // before SetGraphicsRootSignature; once per list
    list->SetGraphicsRootSignature(rootSignature.Get());
    list->SetGraphicsRootDescriptorTable(1, heap->GetGPUDescriptorHandleForHeapStart());
    struct { uint32_t textureIndex; uint32_t pad[3]; float tint[4]; } constants{ index, {}, { 1, 1, 1, 1 } };
    list->SetGraphicsRoot32BitConstants(0, 8, &constants, 0);
    ```

=== "Vulkan"

    ```cpp
    vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, pipelineLayout, 0, 1, &bindlessSet, 0, nullptr);
    struct PushConstants { uint32_t textureIndex; uint32_t pad[3]; float tint[4]; };   // match the HLSL layout
    PushConstants pc{ .textureIndex = index, .tint = { 1, 1, 1, 1 } };
    vkCmdPushConstants(cmd, pipelineLayout, VK_SHADER_STAGE_ALL, 0, sizeof(pc), &pc);
    ```

## Variations

**Shader Model 6.6 direct heap indexing** (D3D12). With the root signature flags `D3D12_ROOT_SIGNATURE_FLAG_CBV_SRV_UAV_HEAP_DIRECTLY_INDEXED` and `..._SAMPLER_HEAP_DIRECTLY_INDEXED`, shaders read the heap without any table: `Texture2D tex = ResourceDescriptorHeap[pc.textureIndex];`. The root signature then holds only constants. It is the simplest D3D12 form, but D3D12-specific HLSL; the array form above compiles for both APIs.

**Different resource types.** Vulkan's array has one descriptor type per binding, so use one binding per type (`textures[]`, `storageBuffers[]`, `storageImages[]`), all in the one set. D3D12's single heap holds every type; use one table range per register type, or direct indexing.

**Buffers without descriptors.** For buffers, [buffer device address](memory.md#without-a-library) (Vulkan) and root or GPU virtual addresses (D3D12) let shaders read a buffer from a 64-bit address passed in constants, skipping descriptors altogether. DXC's `vk::RawBufferLoad` reads one on Vulkan.

**Descriptor buffers** (`VK_EXT_descriptor_buffer`): Vulkan descriptors written straight into ordinary buffer memory, much like D3D12's heaps. They cut CPU overhead further, at the cost of more manual work; descriptor indexing is enough for most engines.

**Render targets** are not part of bindless. D3D12 needs an RTV or DSV descriptor in a non-shader-visible heap for each render target; Vulkan passes image views directly when [beginning rendering](pipelines.md#dynamic-rendering).

## Limits

| | D3D12 | Vulkan |
| --- | --- | --- |
| Bindless array size | 1,000,000 CBV/SRV/UAV (tier 3); 2,048 samplers | `maxDescriptorSetUpdateAfterBind*` (500,000 or more on desktop GPUs) |
| Inline constants | 64 DWORDs for the whole root signature (a constant costs 1, a root descriptor 2, a table 1) | `maxPushConstantsSize`: 128 bytes guaranteed, 256 on most desktop GPUs |
| Bound heaps or sets | one CBV/SRV/UAV heap and one sampler heap at a time | `maxBoundDescriptorSets` (at least 4) |

Changing the bound shader-visible heap in D3D12 can flush GPU work on some hardware. Bind one heap of each type for the whole frame.

!!! warning "Common pitfalls"

    A non-uniform index without `NonUniformResourceIndex` works on some GPUs and gives wrong textures on others. Wrap every index that can differ within a draw.

    Reusing a freed descriptor slot while an in-flight frame still reads it shows the wrong texture for a frame, intermittently. Delay reuse by the number of frames in flight.

    Push constant structs must match the HLSL packing: a `float4` after a `uint` starts at offset 16, not 4. Mirror the padding in C++, or reorder fields largest first.

    Forgetting `SetDescriptorHeaps` before using a table or heap index is undefined behaviour in D3D12. Set the heaps once at the start of each command list.

    In Vulkan, a bindless binding without `PARTIALLY_BOUND` requires every element of the array to hold a valid descriptor, which validation reports for each empty slot.

## C# tips

- Define the push-constant struct with `[StructLayout(LayoutKind.Sequential)]` and the same explicit padding (`uint TextureIndex; uint Pad0, Pad1, Pad2; Vector4 Tint;`), and pass it with `&pc` from an `unsafe` block, or `MemoryMarshal.AsBytes` on a one-element span.
- The descriptor slot allocator is ordinary managed code: a `Stack<int>` of free indices plus a per-frame list of indices waiting to be freed.
