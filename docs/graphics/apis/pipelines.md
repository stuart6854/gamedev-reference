# Pipelines

A **pipeline** bundles the shaders with nearly all the fixed-function state (blending, depth testing, rasterisation, the render target formats) into one object, compiled into GPU code ahead of time. Creating one is expensive (milliseconds), so engines create them while loading and cache them on disk; binding one is cheap.

| Concept | D3D12 | Vulkan |
| --- | --- | --- |
| Graphics pipeline | `ID3D12PipelineState` from a pipeline state stream | `VkPipeline` from `VkGraphicsPipelineCreateInfo` |
| Compute pipeline | `ID3D12PipelineState` with a CS | `vkCreateComputePipelines` |
| Binding layout it is built for | root signature | pipeline layout |
| Render target formats | `RTVFormats`, `DSVFormat` in the stream | `VkPipelineRenderingCreateInfo` |
| State set at record time | viewport, scissor, blend factor, stencil reference, topology class | `VkDynamicState` list (viewport and scissor at least) |
| Starting rendering | `OMSetRenderTargets` (optionally `BeginRenderPass`) | `vkCmdBeginRendering` |
| Cache | `ID3D12PipelineLibrary` (plus the driver's own cache) | `VkPipelineCache` |

## Creating a graphics pipeline

The vertex shader for the examples draws a full-screen triangle without a vertex buffer, and the pixel shader is the bindless one from [descriptors](descriptors.md#the-shader):

```hlsl
struct VSOut { float4 position : SV_Position; float2 uv : TEXCOORD0; };

VSOut VSMain(uint id : SV_VertexID)
{
    float2 uv = float2((id << 1) & 2, id & 2);       // (0,0), (2,0), (0,2): covers the screen
    VSOut o;
    o.position = float4(uv * float2(2, -2) + float2(-1, 1), 0, 1);
    o.uv = uv;
    return o;
}
```

=== "D3D12"

    ```cpp
    // A pipeline state stream: only the subobjects that differ from the defaults.
    struct Stream
    {
        CD3DX12_PIPELINE_STATE_STREAM_ROOT_SIGNATURE        root;
        CD3DX12_PIPELINE_STATE_STREAM_VS                    vs;
        CD3DX12_PIPELINE_STATE_STREAM_PS                    ps;
        CD3DX12_PIPELINE_STATE_STREAM_PRIMITIVE_TOPOLOGY    topology;
        CD3DX12_PIPELINE_STATE_STREAM_RASTERIZER            raster;
        CD3DX12_PIPELINE_STATE_STREAM_RENDER_TARGET_FORMATS formats;
    } stream;
    stream.root = rootSignature.Get();
    stream.vs = vsBytecode;                            // D3D12_SHADER_BYTECODE { pointer, size } of the DXIL
    stream.ps = psBytecode;
    stream.topology = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
    CD3DX12_RASTERIZER_DESC raster(D3D12_DEFAULT);
    raster.CullMode = D3D12_CULL_MODE_NONE;
    stream.raster = raster;
    D3D12_RT_FORMAT_ARRAY formats{ .RTFormats = { DXGI_FORMAT_R8G8B8A8_UNORM }, .NumRenderTargets = 1 };
    stream.formats = formats;

    D3D12_PIPELINE_STATE_STREAM_DESC desc{ sizeof(stream), &stream };
    HR_CHECK(device->CreatePipelineState(&desc, IID_PPV_ARGS(&pipeline)));
    ```

    The `CD3DX12_*` helpers come from `d3dx12.h` in the DirectX-Headers. Each subobject has a sensible default, so a stream lists only what changes. The older `D3D12_GRAPHICS_PIPELINE_STATE_DESC` still works for vertex and pixel shaders, but streams are needed for mesh shaders and newer state.

=== "Vulkan"

    ```cpp
    VkPipelineShaderStageCreateInfo stages[] = {
        { .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, .stage = VK_SHADER_STAGE_VERTEX_BIT,
          .module = vs, .pName = "VSMain" },
        { .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, .stage = VK_SHADER_STAGE_FRAGMENT_BIT,
          .module = ps, .pName = "PSMain" },
    };
    VkPipelineVertexInputStateCreateInfo vertexInput{ .sType = VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO };
    VkPipelineInputAssemblyStateCreateInfo inputAssembly{ .sType = VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
                                                          .topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST };
    VkPipelineViewportStateCreateInfo viewportState{ .sType = VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO,
                                                     .viewportCount = 1, .scissorCount = 1 };   // values are dynamic
    VkPipelineRasterizationStateCreateInfo raster{ .sType = VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
                                                   .polygonMode = VK_POLYGON_MODE_FILL, .cullMode = VK_CULL_MODE_NONE,
                                                   .frontFace = VK_FRONT_FACE_CLOCKWISE, .lineWidth = 1.0f };
    VkPipelineMultisampleStateCreateInfo multisample{ .sType = VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
                                                      .rasterizationSamples = VK_SAMPLE_COUNT_1_BIT };
    VkPipelineColorBlendAttachmentState blendAttachment{ .colorWriteMask = 0xF };     // RGBA, no blending
    VkPipelineColorBlendStateCreateInfo blend{ .sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
                                               .attachmentCount = 1, .pAttachments = &blendAttachment };
    VkDynamicState dynamicStates[] = { VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR };
    VkPipelineDynamicStateCreateInfo dynamic{ .sType = VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO,
                                              .dynamicStateCount = 2, .pDynamicStates = dynamicStates };

    // Dynamic rendering: the pipeline names its attachment formats instead of a VkRenderPass.
    VkFormat colourFormat = VK_FORMAT_R8G8B8A8_UNORM;
    VkPipelineRenderingCreateInfo renderingInfo{ .sType = VK_STRUCTURE_TYPE_PIPELINE_RENDERING_CREATE_INFO,
                                                 .colorAttachmentCount = 1, .pColorAttachmentFormats = &colourFormat };

    VkGraphicsPipelineCreateInfo pipelineInfo{
        .sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO, .pNext = &renderingInfo,
        .stageCount = 2, .pStages = stages,
        .pVertexInputState = &vertexInput, .pInputAssemblyState = &inputAssembly, .pViewportState = &viewportState,
        .pRasterizationState = &raster, .pMultisampleState = &multisample, .pColorBlendState = &blend,
        .pDynamicState = &dynamic, .layout = pipelineLayout };
    VK_CHECK(vkCreateGraphicsPipelines(device, pipelineCache, 1, &pipelineInfo, nullptr, &pipeline));
    ```

- **Everything in the pipeline must match the draw**: the root signature or layout, the render target formats, the sample count. A mismatch is a validation error; without validation it is undefined.
- **Vertex input**: with bindless data, many engines skip vertex input state entirely and read vertices from buffers in the shader ("vertex pulling"), so one pipeline serves every vertex layout.
- **Compute pipelines** need only the shader and the layout: `CD3DX12_PIPELINE_STATE_STREAM_CS` in a stream, or `vkCreateComputePipelines` with one stage.

## Dynamic rendering

=== "D3D12"

    ```cpp
    // Render target views live in a CPU-only RTV heap.
    D3D12_DESCRIPTOR_HEAP_DESC rtvHeapDesc{ .Type = D3D12_DESCRIPTOR_HEAP_TYPE_RTV, .NumDescriptors = 64 };
    HR_CHECK(device->CreateDescriptorHeap(&rtvHeapDesc, IID_PPV_ARGS(&rtvHeap)));
    D3D12_CPU_DESCRIPTOR_HANDLE rtv = rtvHeap->GetCPUDescriptorHandleForHeapStart();
    device->CreateRenderTargetView(target.Get(), nullptr, rtv);     // nullptr: whole resource, its own format

    // Recording: the target must be in the RENDER_TARGET layout (see synchronisation).
    float clear[4] = { 0, 0, 0, 1 };
    list->OMSetRenderTargets(1, &rtv, FALSE, nullptr);
    list->ClearRenderTargetView(rtv, clear, 0, nullptr);
    list->SetPipelineState(pipeline.Get());
    D3D12_VIEWPORT viewport{ 0, 0, float(width), float(height), 0, 1 };
    D3D12_RECT scissor{ 0, 0, LONG(width), LONG(height) };
    list->RSSetViewports(1, &viewport);
    list->RSSetScissorRects(1, &scissor);
    list->IASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    list->DrawInstanced(3, 1, 0, 0);
    ```

=== "Vulkan"

    ```cpp
    VkRenderingAttachmentInfo colourAttachment{
        .sType = VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO, .imageView = target.view,
        .imageLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
        .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR, .storeOp = VK_ATTACHMENT_STORE_OP_STORE,
        .clearValue = { .color = { { 0, 0, 0, 1 } } } };
    VkRenderingInfo rendering{ .sType = VK_STRUCTURE_TYPE_RENDERING_INFO, .renderArea = { { 0, 0 }, { width, height } },
                               .layerCount = 1, .colorAttachmentCount = 1, .pColorAttachments = &colourAttachment };

    vkCmdBeginRendering(cmd, &rendering);
    vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);
    VkViewport viewport{ 0, 0, float(width), float(height), 0, 1 };
    VkRect2D scissor{ { 0, 0 }, { width, height } };
    vkCmdSetViewport(cmd, 0, 1, &viewport);
    vkCmdSetScissor(cmd, 0, 1, &scissor);
    vkCmdDraw(cmd, 3, 1, 0, 0);
    vkCmdEndRendering(cmd);
    ```

- **Load and store operations** say what happens to an attachment's contents at the start and end of rendering. `CLEAR` or `DONT_CARE` instead of `LOAD`, and `DONT_CARE` instead of `STORE` for depth buffers nothing reads later, save bandwidth, and save a lot on tile-based mobile GPUs. D3D12 has the same choices through `BeginRenderPass` / `EndRenderPass`; on desktop GPUs `OMSetRenderTargets` and explicit clears are equivalent.
- **Flip Y for Vulkan.** Vulkan's clip space has Y pointing down. Set the viewport to `{ 0, float(height), float(width), -float(height), 0, 1 }` (a negative height, core since Vulkan 1.1) so the same shaders and projection matrices give the same image on both APIs. With the flip in place, use the same front-face winding on both.
- Vulkan's original `VkRenderPass` and `VkFramebuffer` objects are no longer needed on desktop. Dynamic rendering, plus `VK_KHR_dynamic_rendering_local_read` for reading attachments in the same pass, covers what they did.

## Dynamic state

Everything not marked dynamic is baked into the pipeline, so changing it means another pipeline. Viewport and scissor are always worth making dynamic. Beyond that:

- **D3D12** fixes most state in the pipeline. Viewports, scissors, blend factor, stencil reference, primitive topology (within its class), and depth bounds are set on the command list.
- **Vulkan** lets you mark more state dynamic: depth test and write, cull mode, front face, and topology (core in 1.3), and almost everything else through `VK_EXT_extended_dynamic_state3`. **Shader objects** (`VK_EXT_shader_object`) go further and drop pipelines altogether, setting each shader and all state at record time, like older APIs.
- More dynamic state means fewer pipelines and less hitching, at some cost to the shaders the driver can generate. A common middle: make depth, stencil, and cull state dynamic, keep blending and formats in the pipeline.

## Caching and hitching

Pipeline creation compiles shaders into GPU instructions, which takes milliseconds to hundreds of milliseconds. Doing it the first time a material is drawn causes a visible **hitch**.

- **Create pipelines while loading**, on worker threads (both APIs allow creation from any thread). Know the set of pipelines a level needs: record the combinations used during play-testing, and ship that list.
- **Keep a pipeline cache on disk** so the second run is fast:

=== "D3D12"

    ```cpp
    ComPtr<ID3D12PipelineLibrary1> library;
    HRESULT hr = device->CreatePipelineLibrary(blob.data(), blob.size(), IID_PPV_ARGS(&library));   // blob from disk
    if (hr == D3D12_ERROR_DRIVER_VERSION_MISMATCH || hr == D3D12_ERROR_ADAPTER_NOT_FOUND || hr == E_INVALIDARG)
        HR_CHECK(device->CreatePipelineLibrary(nullptr, 0, IID_PPV_ARGS(&library)));       // stale or other GPU: start empty

    // For each pipeline: load it if cached, otherwise create and store it.
    ComPtr<ID3D12PipelineState> pso;
    if (FAILED(library->LoadPipeline(L"lit_opaque", &desc, IID_PPV_ARGS(&pso))))
    {
        HR_CHECK(device->CreatePipelineState(&desc, IID_PPV_ARGS(&pso)));
        library->StorePipeline(L"lit_opaque", pso.Get());
    }

    // At shutdown: write the library back.
    std::vector<uint8_t> out(library->GetSerializedSize());
    HR_CHECK(library->Serialize(out.data(), out.size()));
    ```

    The pipeline library's memory must stay alive (and unchanged) for as long as the library exists. Drivers also keep their own shader cache, so a cached library mostly saves the remaining work on top of it.

=== "Vulkan"

    ```cpp
    // Only use saved data from the same GPU and driver: the header says which.
    bool CacheMatchesDevice(const std::vector<uint8_t>& data, const VkPhysicalDeviceProperties& props)
    {
        if (data.size() < sizeof(VkPipelineCacheHeaderVersionOne)) return false;
        VkPipelineCacheHeaderVersionOne header;
        std::memcpy(&header, data.data(), sizeof(header));
        return header.headerVersion == VK_PIPELINE_CACHE_HEADER_VERSION_ONE
            && header.vendorID == props.vendorID && header.deviceID == props.deviceID
            && std::memcmp(header.pipelineCacheUUID, props.pipelineCacheUUID, VK_UUID_SIZE) == 0;
    }

    bool useSaved = CacheMatchesDevice(saved, props);            // `saved` read from disk
    VkPipelineCacheCreateInfo cacheInfo{ .sType = VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO,
                                         .initialDataSize = useSaved ? saved.size() : 0,
                                         .pInitialData = useSaved ? saved.data() : nullptr };
    VK_CHECK(vkCreatePipelineCache(device, &cacheInfo, nullptr, &pipelineCache));
    // ... pass pipelineCache to every vkCreate*Pipelines call ...

    // At shutdown: write the cache back.
    size_t size = 0;
    VK_CHECK(vkGetPipelineCacheData(device, pipelineCache, &size, nullptr));
    std::vector<uint8_t> out(size);
    VK_CHECK(vkGetPipelineCacheData(device, pipelineCache, &size, out.data()));
    ```

    Drivers should reject foreign data themselves, but some have crashed on it; checking the header is cheap insurance. One `VkPipelineCache` can be shared by all threads.

!!! warning "Common pitfalls"

    Creating pipelines on first use, during gameplay, hitches for tens or hundreds of milliseconds. Create them while loading, and keep a cache.

    A pipeline's render target formats and sample count must match what it is drawn into. Changing the swapchain format, or adding MSAA, needs new pipelines.

    Forgetting to flip the viewport on Vulkan renders the image upside down, and reverses which faces are culled.

    In D3D12, the root signature in the pipeline and the one set on the command list must be the same object (or identical). Set the root signature before setting root parameters.

## C# tips

- The pipeline state stream is a C++ struct of tagged, aligned subobjects. Vortice.Direct3D12 has `PipelineStateStream` helpers; with raw bindings, build the stream in a `[StructLayout(LayoutKind.Sequential)]` struct of subobject structs, each starting with its type field and aligned to `nint`.
- Load shader bytecode with `File.ReadAllBytes` and pin it (`fixed`) only for the duration of the create call.
