# Async compute and copy

A GPU has more than one engine. Besides the graphics queue, most have **compute** queues that run alongside it, and **copy** (DMA) engines that move data over PCIe without using shader units. Submitting work to them lets it overlap with rendering.

| | D3D12 | Vulkan |
| --- | --- | --- |
| Compute queue | `D3D12_COMMAND_LIST_TYPE_COMPUTE` | a queue family with `COMPUTE` but not `GRAPHICS` |
| Copy queue | `D3D12_COMMAND_LIST_TYPE_COPY` | a family with `TRANSFER` only |
| One queue waits for another | `queue->Wait(fence, value)` | wait on the other queue's timeline in `vkQueueSubmit2` |
| Sharing a resource | layouts valid on both queues (`COMMON`, `GENERIC_READ`, or the plain layouts) | queue family ownership transfer, or `VK_SHARING_MODE_CONCURRENT` |

## When it helps

**Async compute** fills idle shader units. A shadow-map or depth pre-pass is limited by rasterisation and depth testing, leaving ALUs free; a compute job that needs ALUs but little bandwidth (light culling, SSAO, particle simulation, GPU culling for the next pass) can run in that gap.

It does not help, and can hurt, when both workloads need the same thing: two bandwidth-heavy passes slow each other down, and the total can be slower than running them in turn. **Measure** with a GPU profiler that shows queue overlap (PIX, Radeon GPU Profiler, Nsight Graphics). Gains of 5 to 15 % of a frame are typical when it fits.

**Copy queues** are for **streaming**: uploading textures and meshes while the game renders, without the uploads taking graphics queue time. They are slower than the graphics queue for small copies and copies within video memory; use the graphics queue for those.

## Synchronising queues

Each queue gets its own fence or timeline. A queue that needs another's results waits **on the GPU** for a value; the CPU does not get involved.

=== "D3D12"

    ```cpp
    // Compute: light culling for this frame.
    computeQueue->ExecuteCommandLists(1, CommandListCast(cullList.GetAddressOf()));
    HR_CHECK(computeQueue->Signal(computeFence.Get(), ++computeValue));

    // Graphics: the shadow pass does not need the culling results, so it is submitted first and overlaps.
    directQueue->ExecuteCommandLists(1, CommandListCast(shadowList.GetAddressOf()));
    // The lighting pass does: wait on the GPU for the compute value, then submit.
    HR_CHECK(directQueue->Wait(computeFence.Get(), computeValue));
    directQueue->ExecuteCommandLists(1, CommandListCast(lightingList.GetAddressOf()));
    ```

=== "Vulkan"

    ```cpp
    void SubmitWaiting(VkQueue queue, VkCommandBuffer cmd, VkSemaphore otherTimeline, uint64_t otherValue,
                       VkSemaphore myTimeline, uint64_t myValue)
    {
        VkSemaphoreSubmitInfo wait{ .sType = VK_STRUCTURE_TYPE_SEMAPHORE_SUBMIT_INFO, .semaphore = otherTimeline,
                                    .value = otherValue,
                                    .stageMask = VK_PIPELINE_STAGE_2_FRAGMENT_SHADER_BIT };   // only these stages wait
        VkSemaphoreSubmitInfo signal{ .sType = VK_STRUCTURE_TYPE_SEMAPHORE_SUBMIT_INFO, .semaphore = myTimeline,
                                      .value = myValue, .stageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT };
        VkCommandBufferSubmitInfo cb{ .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_SUBMIT_INFO, .commandBuffer = cmd };
        VkSubmitInfo2 submit{ .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO_2,
                              .waitSemaphoreInfoCount = 1, .pWaitSemaphoreInfos = &wait,
                              .commandBufferInfoCount = 1, .pCommandBufferInfos = &cb,
                              .signalSemaphoreInfoCount = 1, .pSignalSemaphoreInfos = &signal };
        VK_CHECK(vkQueueSubmit2(queue, 1, &submit, VK_NULL_HANDLE));
    }
    ```

    The wait's `stageMask` lets earlier stages of the waiting submission (vertex work, say) start before the value is reached. Vulkan's timeline semaphores also allow **wait before signal**: the waiting submission may be submitted before the one that signals, as long as the signal does eventually arrive.

- Split the frame into **submissions at the points where queues meet**, not per pass. Each cross-queue wait is a sync point that costs a little.
- The [render graph](../../engine/rendering/render-graph.md) is the place to decide which passes go on which queue, and where the waits go: it knows every pass's inputs and outputs.
- **Priorities**: D3D12 queues take a priority at creation (`D3D12_COMMAND_QUEUE_PRIORITY_HIGH`), Vulkan queues a priority between 0 and 1 in `VkDeviceQueueCreateInfo`. Drivers treat them as hints.

## Sharing resources between queues

A resource written on one queue and read on another needs the cross-queue wait above **and** a layout (or ownership) that both queues understand.

=== "D3D12"

    - The plain layouts (`SHADER_RESOURCE`, `UNORDERED_ACCESS`, `GENERIC_READ`, `COMMON`) are valid on both the direct and compute queues. The `DIRECT_QUEUE_*` and `COMPUTE_QUEUE_*` layouts can be more efficient, but only that queue type may use the resource while it is in one.
    - Copy queues work with textures in the `COMMON` layout. Create streamed textures in `COMMON`, copy into them on the copy queue without any barrier, and transition them `COMMON` → `SHADER_RESOURCE` on the direct queue after it has waited on the copy fence.
    - Buffers have no layout, so only the fences are needed.

=== "Vulkan"

    Resources created with `VK_SHARING_MODE_EXCLUSIVE` (the default, and the faster one) belong to one queue family at a time. Moving one is a pair of barriers with matching layouts and family indices:

    ```cpp
    // On the transfer queue, after the copy: release ownership.
    VkImageMemoryBarrier2 release{
        .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2,
        .srcStageMask = VK_PIPELINE_STAGE_2_COPY_BIT, .srcAccessMask = VK_ACCESS_2_TRANSFER_WRITE_BIT,
        .dstStageMask = VK_PIPELINE_STAGE_2_NONE,     .dstAccessMask = VK_ACCESS_2_NONE,       // ignored for a release
        .oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, .newLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,
        .srcQueueFamilyIndex = transferFamily, .dstQueueFamilyIndex = graphicsFamily,
        .image = image, .subresourceRange = all };
    VkDependencyInfo releaseDep{ .sType = VK_STRUCTURE_TYPE_DEPENDENCY_INFO, .imageMemoryBarrierCount = 1,
                                 .pImageMemoryBarriers = &release };
    vkCmdPipelineBarrier2(copyCmd, &releaseDep);

    // On the graphics queue, after waiting on the transfer timeline: acquire, with the same layouts and families.
    VkImageMemoryBarrier2 acquire{
        .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2,
        .srcStageMask = VK_PIPELINE_STAGE_2_NONE, .srcAccessMask = VK_ACCESS_2_NONE,         // ignored for an acquire
        .dstStageMask = VK_PIPELINE_STAGE_2_FRAGMENT_SHADER_BIT, .dstAccessMask = VK_ACCESS_2_SHADER_SAMPLED_READ_BIT,
        .oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, .newLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,
        .srcQueueFamilyIndex = transferFamily, .dstQueueFamilyIndex = graphicsFamily,
        .image = image, .subresourceRange = all };
    VkDependencyInfo acquireDep{ .sType = VK_STRUCTURE_TYPE_DEPENDENCY_INFO, .imageMemoryBarrierCount = 1,
                                 .pImageMemoryBarriers = &acquire };
    vkCmdPipelineBarrier2(graphicsCmd, &acquireDep);
    ```

    - Both halves must describe the **same** transition. The release does the layout change; the acquire makes the result visible to its stages.
    - When both queues are in the **same family** (two queues of one family), no transfer is needed: the semaphore wait is enough.
    - **`VK_SHARING_MODE_CONCURRENT`**, with the list of families, skips ownership transfers entirely. It can disable compression on some GPUs, so use it for buffers and rarely written images rather than render targets.

## Uploads

A streaming system, using the copy queue:

```text
stream_in(texture):
    staging = upload_ring.allocate(texture.size)          // persistently mapped upload memory
    write the mip data into staging
    record on the copy queue: copy staging → texture (texture in COMMON / TRANSFER_DST, release on Vulkan)
    submit; value = signal(copy timeline)
    pending.add(texture, value)

each frame, on the graphics queue:
    for each pending texture whose copy value has been reached (check on the CPU, no waiting):
        record the transition to shader read (acquire on Vulkan)
        mark the texture ready: materials may now use its bindless index
    if this frame uses any newly ready texture: wait on the copy timeline value before the first pass that does
```

- **Poll, do not block.** Check the copy timeline's current value on the CPU (`GetCompletedValue`, `vkGetSemaphoreCounterValue`) and promote textures that have arrived; the frame never waits for a slow upload. Show a lower mip level until then.
- **Free staging memory** only when the copy's value has been reached, as for any [deferred deletion](../../engine/rendering/frames-in-flight.md#deferred-deletion).
- **DirectStorage** (Windows) and similar APIs read compressed data from disk straight into GPU memory, decompressing on the GPU; they build on the same copy queue.

!!! warning "Common pitfalls"

    A wait on a fence or timeline value that no submission will ever signal hangs the GPU, and the device is eventually removed. Every wait needs a matching signal.

    In Vulkan, using an exclusive resource on a second queue family without an ownership transfer gives undefined contents. Release and acquire, or create it concurrent.

    Async compute that competes for the same bandwidth or caches as the graphics work makes the frame slower. Profile before and after.

    Tiny copies on the copy queue are slower than on the graphics queue, and each needs a cross-queue wait. Batch uploads, and use the graphics queue for small or per-frame data.

## C# tips

- One fence or timeline object per queue, wrapped in a small class with `Signal()`, `WaitOnCpu(value)`, and `IsComplete(value)`, keeps the cross-queue logic readable.
- A streaming system's upload requests map naturally onto `async` code: a request completes when its timeline value is reached, polled once per frame, as on the [async/await](../../csharp/async.md) page.
