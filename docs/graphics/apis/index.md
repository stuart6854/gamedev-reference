# D3D12 and Vulkan

Direct3D 12 and Vulkan are the two **explicit** graphics APIs on PC: the application allocates memory, records command lists, places barriers, and synchronises with the GPU itself, where older APIs did this in the driver. They were designed around the same ideas at the same time, and most concepts map one to one. These pages cover both side by side, for an engine with one [RHI](../../engine/rendering/rhi.md) over the two.

## Versions

The pages target the **modern** form of each API, which is simpler than the original:

| | D3D12 | Vulkan |
| --- | --- | --- |
| Baseline | Feature level 12_1 with the **Agility SDK** (ships the D3D12 runtime with your game) | **Vulkan 1.3** (core since 2022) |
| Barriers | **Enhanced barriers** (`ID3D12GraphicsCommandList7::Barrier`) | **Synchronization2** (`vkCmdPipelineBarrier2`) |
| Rendering without render pass objects | always | **dynamic rendering** (`vkCmdBeginRendering`) |
| GPU timeline | `ID3D12Fence` | **timeline semaphores** |
| Bindless | Shader Model 6.6 `ResourceDescriptorHeap[]` | descriptor indexing (core in 1.2) |
| Mesh shaders | Shader Model 6.5, mesh shader tier 1 | `VK_EXT_mesh_shader` |

Hardware from about 2018 onwards (NVIDIA Turing, AMD RDNA 2, Intel Arc) supports all of it. The older paths (resource-state barriers, `VkRenderPass` and framebuffers, binary semaphores for everything) still work, and appear in old samples; these pages mention them only where they cause confusion.

## Concepts side by side

| Concept | D3D12 | Vulkan |
| --- | --- | --- |
| Entry point | `IDXGIFactory6`, `D3D12CreateDevice` | `VkInstance`, `vkCreateDevice` |
| GPU | `IDXGIAdapter4` | `VkPhysicalDevice` |
| Device | `ID3D12Device10` | `VkDevice` |
| Queue | `ID3D12CommandQueue` (direct, compute, copy) | `VkQueue` from a queue family |
| Command memory | `ID3D12CommandAllocator` | `VkCommandPool` |
| Command list | `ID3D12GraphicsCommandList7` | `VkCommandBuffer` |
| GPU memory | `ID3D12Heap`, or committed resources | `VkDeviceMemory` |
| Buffer / texture | `ID3D12Resource` | `VkBuffer` / `VkImage` + `VkImageView` |
| Descriptor storage | `ID3D12DescriptorHeap` | `VkDescriptorPool` / `VkDescriptorSet` (or descriptor buffers) |
| Binding layout | `ID3D12RootSignature` | `VkPipelineLayout` + `VkDescriptorSetLayout` |
| Small constants | root constants | push constants |
| Pipeline | `ID3D12PipelineState` | `VkPipeline` |
| Pipeline cache | `ID3D12PipelineLibrary` | `VkPipelineCache` |
| CPU–GPU sync | `ID3D12Fence` + an event | timeline `VkSemaphore` |
| GPU–GPU sync | `ID3D12CommandQueue::Wait` on a fence | semaphore wait in `vkQueueSubmit2` |
| Barrier | `D3D12_TEXTURE_BARRIER`, `D3D12_BUFFER_BARRIER` | `VkImageMemoryBarrier2`, `VkBufferMemoryBarrier2` |
| Image layout | `D3D12_BARRIER_LAYOUT_*` | `VK_IMAGE_LAYOUT_*` |
| Swapchain | `IDXGISwapChain4` | `VkSwapchainKHR` + `VkSurfaceKHR` |
| Shader binary | DXIL | SPIR-V |
| Debug layer | D3D12 debug layer, GPU-based validation | Khronos validation layer |
| Capture tool | PIX, RenderDoc | RenderDoc, vendor tools |

## Differences that leak into an engine

- **Clip space**: Vulkan's Y axis points **down** in clip space, D3D12's points up. Flip it once, in the viewport, with a negative height (`y = height, height = -height`, core since Vulkan 1.1) rather than in every shader. Both use depth from 0 to 1. See [coordinate spaces](../coordinate-spaces.md).
- **Queues**: D3D12 has three fixed queue types. Vulkan has **queue families** with capabilities and counts that differ per GPU; the engine must discover them.
- **Image layouts**: both have them now, but Vulkan has always required correct ones; D3D12's enhanced barriers added explicit layouts in the same style.
- **Extensions**: D3D12 features are checked with `CheckFeatureSupport` and used directly. Vulkan features must be **enabled at device creation**, and many arrive as extensions first.
- **Shaders**: one HLSL source, compiled by DXC to DXIL for D3D12 and to SPIR-V for Vulkan, covers both. See [shader compilation](shaders.md).

## Pages

- [Devices, queues, and command lists](devices.md) — choosing a GPU, enabling features, queues, command memory, and recording and submitting work.
- [Memory and resources](memory.md) — memory types and heaps, allocators, buffers and textures, uploading data, and alignment.
- [Descriptors and binding](descriptors.md) — descriptor heaps and sets, root signatures and pipeline layouts, push and root constants, and bindless.
- [Pipelines](pipelines.md) — pipeline state, dynamic rendering, dynamic state, and pipeline caches.
- [Synchronisation and barriers](synchronisation.md) — fences and timeline semaphores, enhanced barriers and synchronization2, layouts, and common transitions.
- [Swapchains and presenting](swapchain.md) — creating a swapchain, present modes, acquiring and presenting, resizing, and frame pacing.
- [Shader compilation](shaders.md) — HLSL with DXC to DXIL and SPIR-V, binding annotations, reflection, and Slang.
- [Async compute and copy](async-compute.md) — extra queues, cross-queue synchronisation, queue ownership, and upload strategies.
- [Mesh shaders](mesh-shaders.md) — the amplification (task) and mesh stages, meshlets, and culling.
- [Debugging](debugging.md) — validation layers, object names, markers, captures, and investigating a lost device.

The engine-side design over these APIs is under [rendering](../../engine/rendering/index.md): the [RHI](../../engine/rendering/rhi.md), [frames in flight](../../engine/rendering/frames-in-flight.md), and the [render graph](../../engine/rendering/render-graph.md).

## C# tips

- **D3D12**: [Vortice.Windows](https://github.com/amerkoleci/Vortice.Windows) (`Vortice.Direct3D12`, `Vortice.DXGI`, `Vortice.Dxc`) wraps the COM interfaces as C# classes with `Dispose`, and is the most complete binding.
- **Vulkan**: [Silk.NET.Vulkan](https://github.com/dotnet/Silk.NET) and [Vortice.Vulkan](https://github.com/amerkoleci/Vortice.Vulkan) are thin, generated bindings: the code reads like the C API, with `unsafe` pointers to structs.
- Structs passed to either API must be **unmanaged** and laid out like their C versions. Build `pNext` chains from stack-allocated structs (`var features13 = new PhysicalDeviceVulkan13Features { ... }; features12.PNext = &features13;`) inside one `unsafe` method, so nothing moves while the call runs. [Pointers and native memory](../../csharp/performance/memory.md) covers the C# side.
- The validation layers and debug layer work the same from C#; their messages are the fastest way to find a wrong struct field in a binding.

## Reading

- [Vulkan Guide](https://docs.vulkan.org/guide/latest/index.html) (Khronos) and the [Vulkan specification](https://docs.vulkan.org/spec/latest/index.html).
- [Direct3D 12 programming guide](https://learn.microsoft.com/windows/win32/direct3d12/directx-12-programming-guide) and the [DirectX specs](https://microsoft.github.io/DirectX-Specs/) (enhanced barriers, Shader Model 6.6, mesh shaders).
- [GPUOpen](https://gpuopen.com/) and [NVIDIA developer](https://developer.nvidia.com/) articles on barriers, memory, and async compute for each vendor.
