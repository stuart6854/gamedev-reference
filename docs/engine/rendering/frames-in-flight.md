# Frames in flight

The CPU records frame N+1 while the GPU draws frame N. That overlap keeps both busy, but anything the GPU might still read (constant buffers, uploaded data, objects being destroyed) must not be changed or freed until the GPU has finished with it. Explicit APIs leave this entirely to the engine.

## The loop

```text
FRAMES_IN_FLIGHT = 2

per_frame[FRAMES_IN_FLIGHT] {
    fence_value             // the value the GPU signals when this frame is done
    command_pools[threads]
    upload_ring_start
    deletion_queue[]
}

frame_index = 0
fence = create_fence()      // a timeline semaphore (Vulkan) or ID3D12Fence: a counter the GPU increments

render_frame():
    f = per_frame[frame_index]
    wait until fence.completed_value >= f.fence_value     // the GPU finished this slot's last use
    reset f.command_pools
    free everything in f.deletion_queue
    acquire the next swapchain image

    record and submit command lists

    f.fence_value = ++fence_counter
    queue.signal(fence, f.fence_value)
    present
    frame_index = (frame_index + 1) mod FRAMES_IN_FLIGHT
```

- Each slot's resources (command pools, per-frame buffers) are reused every `FRAMES_IN_FLIGHT` frames, after the wait guarantees the GPU is done with them.
- **Two** frames in flight lets the CPU and GPU overlap; **three** absorbs uneven frames better, at the cost of another frame of input latency. Most games use two.
- The wait at the top is where the CPU stalls when the GPU is the bottleneck. Profile it: time spent there means the frame is GPU-bound.

## Per-frame data: the upload ring

Constant data that changes every frame (camera, per-object transforms, particle vertices) goes in one large CPU-visible buffer used as a **ring**:

```text
UploadRing { buffer, mapped_pointer, size, head }

allocate(bytes, alignment) -> (offset, pointer):
    offset = round_up(head, alignment)
    if offset + bytes > size: offset = 0                 // wrap
    check offset does not overtake the oldest frame still in flight
    head = offset + bytes
    return offset, mapped_pointer + offset

at the start of each frame:
    per_frame[frame_index].upload_ring_start = head      // everything before this belongs to older frames
```

Writing is a `memcpy` into mapped memory, and shaders read it at the returned offset (a dynamic offset or a buffer address). Nothing is allocated or freed per draw. The ring must be large enough for `FRAMES_IN_FLIGHT` frames of data; assert if the head catches the oldest in-flight frame's start, rather than silently overwriting data the GPU is reading.

Respect the alignment the API requires for constant buffers (256 bytes in D3D12, `minUniformBufferOffsetAlignment` in Vulkan).

## Uploading to GPU memory

Textures and static meshes live in GPU-local memory that the CPU cannot write directly. Upload them through a staging buffer and a copy:

```text
upload_texture(texture, pixels):
    staging = upload_ring.allocate(size)           // or a dedicated staging buffer for large data
    copy pixels into staging
    copy_queue: copy staging -> texture
    signal the copy fence; the texture is usable once the graphics queue has waited for it
```

- Large uploads (streaming textures) go on the **copy queue**, in parallel with rendering, and the graphics queue waits on the copy fence before using them.
- Budget uploads per frame (a few megabytes), as the [resources](../patterns/resources.md#asynchronous-loading) page describes.
- On integrated GPUs and consoles with unified memory, the copy can often be skipped by writing straight into memory the GPU reads.

## Deferred deletion

A texture released by the game may still be referenced by command lists the GPU has not executed yet. Do not destroy it now; queue it:

```text
destroy_texture(handle):
    per_frame[frame_index].deletion_queue.append(handle)
    // freed when this slot comes round again, after its fence wait
```

Everything the GPU may touch goes through this queue: buffers, textures, views, pipelines, descriptor slots in a bindless table. Destroying immediately works in testing (the GPU happens to have finished) and crashes rarely and unreproducibly in the field.

## Presenting

- **Acquire** the next swapchain image before rendering to it; on Vulkan this returns a semaphore the first pass that writes the image must wait on.
- **Present** waits on a semaphore signalled by the last pass. Vsync and the present mode decide when the image reaches the screen: FIFO (vsync), mailbox (latest frame wins, no tearing), or immediate (tearing allowed).
- **Frame pacing.** With vsync, the CPU should start each frame just late enough that the GPU finishes just before the next vertical blank. Starting earlier adds latency; later drops frames. Waiting on the swapchain's latency object (DXGI `GetFrameLatencyWaitableObject`, Vulkan `VK_KHR_present_wait`) at the start of the frame, instead of on the fence, is the usual way to keep latency low.
- Handle **out-of-date swapchains** (window resized or minimised): recreate the swapchain and its size-dependent targets; see [viewports and windows](viewports.md#resizing).
