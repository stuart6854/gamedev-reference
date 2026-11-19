# Synchronisation and barriers

The explicit APIs do nothing in the background to keep work in order. Two kinds of ordering are the application's job:

- **CPU and GPU**: the CPU must not reuse memory (command allocators, upload buffers, descriptors) the GPU is still reading, and must wait before reading results back. That is **fences** and **timeline semaphores**.
- **Inside the GPU**: a pass that reads a texture must not start until the pass that wrote it has finished, its writes must be visible to the reader's caches, and the texture must be in the right **layout**. That is **barriers**.

| Concept | D3D12 | Vulkan |
| --- | --- | --- |
| A GPU counter the CPU can wait on | `ID3D12Fence` | timeline `VkSemaphore` |
| GPU signals a value | `queue->Signal(fence, value)` | `signalSemaphoreInfos` in `vkQueueSubmit2` |
| CPU waits | `SetEventOnCompletion` + `WaitForSingleObject` | `vkWaitSemaphores` |
| GPU waits (another queue) | `queue->Wait(fence, value)` | `waitSemaphoreInfos` in `vkQueueSubmit2` |
| Barrier call | `ID3D12GraphicsCommandList7::Barrier` | `vkCmdPipelineBarrier2` |
| When: before and after | `SyncBefore` / `SyncAfter` | `srcStageMask` / `dstStageMask` |
| What memory access | `AccessBefore` / `AccessAfter` | `srcAccessMask` / `dstAccessMask` |
| Texture layout | `LayoutBefore` / `LayoutAfter` | `oldLayout` / `newLayout` |
| Swapchain image ready, rendering done | handled by DXGI | binary semaphores |

## Fences and timelines

A fence or timeline semaphore is a **64-bit counter on the GPU** that only goes up. The GPU sets it to a value when it reaches a point in a queue; the CPU (or another queue) waits until it reaches a value.

=== "D3D12"

    ```cpp
    HR_CHECK(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&fence)));
    HANDLE event = CreateEvent(nullptr, FALSE, FALSE, nullptr);

    uint64_t Signal(ID3D12CommandQueue* queue)
    {
        HR_CHECK(queue->Signal(fence.Get(), ++fenceValue));      // the GPU sets the fence when it gets here
        return fenceValue;
    }

    void WaitOnCpu(uint64_t value)
    {
        if (fence->GetCompletedValue() < value)
        {
            HR_CHECK(fence->SetEventOnCompletion(value, event));
            WaitForSingleObject(event, INFINITE);
        }
    }
    ```

=== "Vulkan"

    ```cpp
    VkSemaphoreTypeCreateInfo timelineType{ .sType = VK_STRUCTURE_TYPE_SEMAPHORE_TYPE_CREATE_INFO,
                                            .semaphoreType = VK_SEMAPHORE_TYPE_TIMELINE, .initialValue = 0 };
    VkSemaphoreCreateInfo semInfo{ .sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO, .pNext = &timelineType };
    VK_CHECK(vkCreateSemaphore(device, &semInfo, nullptr, &timeline));

    // Signalled by a submission:
    VkSemaphoreSubmitInfo signal{ .sType = VK_STRUCTURE_TYPE_SEMAPHORE_SUBMIT_INFO, .semaphore = timeline,
                                  .value = ++timelineValue, .stageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT };
    // ...in VkSubmitInfo2::pSignalSemaphoreInfos...

    void WaitOnCpu(uint64_t value)
    {
        VkSemaphoreWaitInfo waitInfo{ .sType = VK_STRUCTURE_TYPE_SEMAPHORE_WAIT_INFO, .semaphoreCount = 1,
                                      .pSemaphores = &timeline, .pValues = &value };
        VK_CHECK(vkWaitSemaphores(device, &waitInfo, UINT64_MAX));
    }
    ```

One counter per queue is enough. Each frame records the value it signalled; before reusing frame N's allocators, upload space, and freed descriptors, the CPU waits for that value. That is the whole of [frames in flight](../../engine/rendering/frames-in-flight.md):

```text
begin_frame():
    frame = frames[frame_index % FRAMES_IN_FLIGHT]
    wait_on_cpu(frame.fence_value)          // usually already reached: no wait
    reset frame.allocators, frame.upload_ring, release frame.deferred_deletes
end_frame():
    submit
    frame.fence_value = signal(queue)
    frame_index += 1
```

Use binary semaphores in Vulkan only where the API requires them: acquiring and presenting [swapchain](swapchain.md) images.

## Barriers

A barrier says three things about a resource:

1. **Execution**: the work in `SyncBefore` / `srcStageMask` must finish before the work in `SyncAfter` / `dstStageMask` starts.
2. **Memory**: writes of kind `AccessBefore` / `srcAccessMask` must be made visible to reads or writes of kind `AccessAfter` / `dstAccessMask`. GPUs have many caches; without this, a reader can see stale data even after the writer has finished.
3. **Layout** (textures only): how the texture's memory is arranged. Render targets, sampled textures, and copy destinations may use different compression or tiling, and the transition converts between them.

=== "D3D12"

    ```cpp
    void TextureBarrier(ID3D12GraphicsCommandList7* list, ID3D12Resource* texture,
                        D3D12_BARRIER_SYNC syncBefore, D3D12_BARRIER_ACCESS accessBefore, D3D12_BARRIER_LAYOUT layoutBefore,
                        D3D12_BARRIER_SYNC syncAfter,  D3D12_BARRIER_ACCESS accessAfter,  D3D12_BARRIER_LAYOUT layoutAfter)
    {
        D3D12_TEXTURE_BARRIER barrier{
            .SyncBefore = syncBefore, .SyncAfter = syncAfter,
            .AccessBefore = accessBefore, .AccessAfter = accessAfter,
            .LayoutBefore = layoutBefore, .LayoutAfter = layoutAfter,
            .pResource = texture,
            .Subresources = { .IndexOrFirstMipLevel = 0xffffffff },   // all mips and array slices
            .Flags = D3D12_TEXTURE_BARRIER_FLAG_NONE };
        D3D12_BARRIER_GROUP group{ .Type = D3D12_BARRIER_TYPE_TEXTURE, .NumBarriers = 1, .pTextureBarriers = &barrier };
        list->Barrier(1, &group);
    }

    // Buffers have no layout: only sync and access.
    void BufferBarrier(ID3D12GraphicsCommandList7* list, ID3D12Resource* buffer,
                       D3D12_BARRIER_SYNC syncBefore, D3D12_BARRIER_ACCESS accessBefore,
                       D3D12_BARRIER_SYNC syncAfter,  D3D12_BARRIER_ACCESS accessAfter)
    {
        D3D12_BUFFER_BARRIER barrier{ .SyncBefore = syncBefore, .SyncAfter = syncAfter,
                                      .AccessBefore = accessBefore, .AccessAfter = accessAfter,
                                      .pResource = buffer, .Offset = 0, .Size = UINT64_MAX };
        D3D12_BARRIER_GROUP group{ .Type = D3D12_BARRIER_TYPE_BUFFER, .NumBarriers = 1, .pBufferBarriers = &barrier };
        list->Barrier(1, &group);
    }
    ```

=== "Vulkan"

    ```cpp
    void ImageBarrier(VkCommandBuffer cmd, VkImage image,
                      VkPipelineStageFlags2 srcStage, VkAccessFlags2 srcAccess, VkImageLayout oldLayout,
                      VkPipelineStageFlags2 dstStage, VkAccessFlags2 dstAccess, VkImageLayout newLayout)
    {
        VkImageMemoryBarrier2 barrier{
            .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2,
            .srcStageMask = srcStage, .srcAccessMask = srcAccess,
            .dstStageMask = dstStage, .dstAccessMask = dstAccess,
            .oldLayout = oldLayout, .newLayout = newLayout,
            .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .image = image,
            .subresourceRange = { VK_IMAGE_ASPECT_COLOR_BIT, 0, VK_REMAINING_MIP_LEVELS, 0, VK_REMAINING_ARRAY_LAYERS } };
        VkDependencyInfo dep{ .sType = VK_STRUCTURE_TYPE_DEPENDENCY_INFO,
                              .imageMemoryBarrierCount = 1, .pImageMemoryBarriers = &barrier };
        vkCmdPipelineBarrier2(cmd, &dep);
    }

    // Buffers: a global memory barrier covers every buffer, and costs the same as a per-buffer one.
    void MemoryBarrier(VkCommandBuffer cmd, VkPipelineStageFlags2 srcStage, VkAccessFlags2 srcAccess,
                       VkPipelineStageFlags2 dstStage, VkAccessFlags2 dstAccess)
    {
        VkMemoryBarrier2 barrier{ .sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER_2,
                                  .srcStageMask = srcStage, .srcAccessMask = srcAccess,
                                  .dstStageMask = dstStage, .dstAccessMask = dstAccess };
        VkDependencyInfo dep{ .sType = VK_STRUCTURE_TYPE_DEPENDENCY_INFO, .memoryBarrierCount = 1, .pMemoryBarriers = &barrier };
        vkCmdPipelineBarrier2(cmd, &dep);
    }
    ```

### Common transitions

| Transition | D3D12 sync / access / layout | Vulkan stage / access / layout |
| --- | --- | --- |
| New texture → copy destination | `NONE` / `NO_ACCESS` / `UNDEFINED` (or `COMMON`) → `COPY` / `COPY_DEST` / `COPY_DEST` | `NONE` / `NONE` / `UNDEFINED` → `COPY` / `TRANSFER_WRITE` / `TRANSFER_DST_OPTIMAL` |
| Copied → sampled in pixel shaders | `COPY` / `COPY_DEST` / `COPY_DEST` → `PIXEL_SHADING` / `SHADER_RESOURCE` / `SHADER_RESOURCE` | `COPY` / `TRANSFER_WRITE` / `TRANSFER_DST_OPTIMAL` → `FRAGMENT_SHADER` / `SHADER_SAMPLED_READ` / `SHADER_READ_ONLY_OPTIMAL` |
| Render target → sampled | `RENDER_TARGET` / `RENDER_TARGET` / `RENDER_TARGET` → `PIXEL_SHADING` / `SHADER_RESOURCE` / `SHADER_RESOURCE` | `COLOR_ATTACHMENT_OUTPUT` / `COLOR_ATTACHMENT_WRITE` / `COLOR_ATTACHMENT_OPTIMAL` → `FRAGMENT_SHADER` / `SHADER_SAMPLED_READ` / `SHADER_READ_ONLY_OPTIMAL` |
| Depth written → sampled (shadow map) | `DEPTH_STENCIL` / `DEPTH_STENCIL_WRITE` / `DEPTH_STENCIL_WRITE` → `PIXEL_SHADING` / `SHADER_RESOURCE` / `SHADER_RESOURCE` | `LATE_FRAGMENT_TESTS` / `DEPTH_STENCIL_ATTACHMENT_WRITE` / `DEPTH_ATTACHMENT_OPTIMAL` → `FRAGMENT_SHADER` / `SHADER_SAMPLED_READ` / `SHADER_READ_ONLY_OPTIMAL` (aspect `DEPTH`) |
| Compute writes → compute reads (same buffer) | `COMPUTE_SHADING` / `UNORDERED_ACCESS` → `COMPUTE_SHADING` / `UNORDERED_ACCESS` | memory barrier `COMPUTE_SHADER` / `SHADER_STORAGE_WRITE` → `COMPUTE_SHADER` / `SHADER_STORAGE_READ` |
| Compute writes → indirect draw arguments | `COMPUTE_SHADING` / `UNORDERED_ACCESS` → `EXECUTE_INDIRECT` / `INDIRECT_ARGUMENT` | `COMPUTE_SHADER` / `SHADER_STORAGE_WRITE` → `DRAW_INDIRECT` / `INDIRECT_COMMAND_READ` |
| GPU writes → CPU reads | wait on the fence; readback heaps need no barrier | `COPY` (or the writing stage) / its write access → `HOST` / `HOST_READ`, then wait |
| Swapchain image → render target → present | `NONE` / `NO_ACCESS` / `PRESENT` → `RENDER_TARGET` ... → `RENDER_TARGET` → `NONE` / `NO_ACCESS` / `PRESENT` | see [swapchains](swapchain.md#each-frame) |

In code, the upload case from [memory](memory.md#uploading-data):

=== "D3D12"

    ```cpp
    TextureBarrier(list, texture,
                   D3D12_BARRIER_SYNC_NONE, D3D12_BARRIER_ACCESS_NO_ACCESS, D3D12_BARRIER_LAYOUT_COMMON,
                   D3D12_BARRIER_SYNC_COPY, D3D12_BARRIER_ACCESS_COPY_DEST, D3D12_BARRIER_LAYOUT_COPY_DEST);
    // ... CopyTextureRegion ...
    TextureBarrier(list, texture,
                   D3D12_BARRIER_SYNC_COPY, D3D12_BARRIER_ACCESS_COPY_DEST, D3D12_BARRIER_LAYOUT_COPY_DEST,
                   D3D12_BARRIER_SYNC_PIXEL_SHADING, D3D12_BARRIER_ACCESS_SHADER_RESOURCE, D3D12_BARRIER_LAYOUT_SHADER_RESOURCE);
    ```

=== "Vulkan"

    ```cpp
    ImageBarrier(cmd, texture.image,
                 VK_PIPELINE_STAGE_2_NONE, VK_ACCESS_2_NONE, VK_IMAGE_LAYOUT_UNDEFINED,
                 VK_PIPELINE_STAGE_2_COPY_BIT, VK_ACCESS_2_TRANSFER_WRITE_BIT, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
    // ... vkCmdCopyBufferToImage ...
    ImageBarrier(cmd, texture.image,
                 VK_PIPELINE_STAGE_2_COPY_BIT, VK_ACCESS_2_TRANSFER_WRITE_BIT, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                 VK_PIPELINE_STAGE_2_FRAGMENT_SHADER_BIT, VK_ACCESS_2_SHADER_SAMPLED_READ_BIT,
                 VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL);
    ```

### Rules of thumb

- **Name the exact stages.** `ALL_COMMANDS` / `SYNC_ALL` on both sides is always correct and often slow: it waits for everything before and blocks everything after. The validation layer's best-practices mode warns about `ALL_COMMANDS` in semaphore waits for this reason.
- **`UNDEFINED` as the old layout discards the contents**, which is what you want for a target about to be cleared or fully overwritten, and what you never want for a texture you are about to read.
- **Batch barriers.** Pass all the barriers between two passes in one `Barrier` / `vkCmdPipelineBarrier2` call, so the GPU waits once.
- **Read-to-read needs no barrier**, only a layout change if the reader needs a different layout. Write-to-read, read-to-write, and write-to-write all do.
- **Prefer layouts that cover several uses**: a texture sampled by both compute and pixel shaders can stay in one read layout; `VK_IMAGE_LAYOUT_GENERAL` and D3D12's `COMMON` layouts work everywhere but may lose compression.
- **Let the render graph do it.** Tracking each resource's last stage, access, and layout by hand across a whole frame does not scale. A [render graph](../../engine/rendering/render-graph.md) knows every pass's reads and writes, and emits the minimal barriers between them.

## Old and new barrier APIs

Old samples use the original forms, which these pages do not:

| | Original | Modern |
| --- | --- | --- |
| D3D12 | resource-state barriers (`D3D12_RESOURCE_BARRIER`, `D3D12_RESOURCE_STATE_*`): one state for both layout and access, implicit sync | enhanced barriers: separate sync, access, and layout; `Barrier()` on `ID3D12GraphicsCommandList7` |
| Vulkan | `vkCmdPipelineBarrier` with 32-bit stage and access flags; `vkQueueSubmit` with binary semaphores | synchronization2 (`vkCmdPipelineBarrier2`, `vkQueueSubmit2`), timeline semaphores |

The modern forms are clearer, map one to one between the two APIs, and are what an RHI should expose. Enhanced barriers need the [Agility SDK](devices.md#the-device) and a driver that reports `EnhancedBarriersSupported`.

## Checking

Barrier mistakes often work on one GPU and corrupt rendering on another, because vendors cache and compress differently. Check with tools, not by eye:

- **Vulkan synchronisation validation**: enable `VK_VALIDATION_FEATURE_ENABLE_SYNCHRONIZATION_VALIDATION_EXT` (in `VkValidationFeaturesEXT`, or with `vkconfig`). It reports read-after-write hazards and missing transitions, with the commands involved.
- **D3D12 GPU-based validation** (`ID3D12Debug3::SetEnableGPUBasedValidation(TRUE)`) checks resource layouts at the point each shader reads, which the CPU-side debug layer cannot.
- See [debugging](debugging.md) for both.

!!! warning "Common pitfalls"

    Waiting on the CPU for the previous frame every frame (instead of the frame from `FRAMES_IN_FLIGHT` ago) serialises the CPU and GPU, and halves the frame rate when both are busy.

    Transitioning from `UNDEFINED` loses the texture's contents. Use the real previous layout for anything you want to keep.

    Forgetting the memory part (`AccessBefore` / `srcAccessMask` set to none after a write) orders the work but leaves stale data in caches: the reader sees old values on some GPUs.

    A Vulkan depth image barrier needs `VK_IMAGE_ASPECT_DEPTH_BIT` (and `STENCIL` if it has stencil), not `COLOR`. The helper above is for colour images.

    Signalling a fence value that is not larger than the last one does nothing useful, and waiting on it returns immediately. Increment the value with every signal.
