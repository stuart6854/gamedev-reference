# Memory and resources

In both APIs the application decides where every buffer and texture lives. The GPU's memory is divided into **types** with different properties, and choosing the wrong one makes a resource slow to read, slow to write, or impossible to map.

| Concept | D3D12 | Vulkan |
| --- | --- | --- |
| GPU-only memory | `D3D12_HEAP_TYPE_DEFAULT` | a `DEVICE_LOCAL` memory type |
| CPU writes, GPU reads | `D3D12_HEAP_TYPE_UPLOAD` | `HOST_VISIBLE \| HOST_COHERENT` |
| GPU writes, CPU reads | `D3D12_HEAP_TYPE_READBACK` | `HOST_VISIBLE \| HOST_CACHED` |
| CPU-writable video memory (resizable BAR) | `D3D12_HEAP_TYPE_GPU_UPLOAD` | `DEVICE_LOCAL \| HOST_VISIBLE` |
| One allocation per resource | committed resource | dedicated allocation |
| Many resources in one block | `ID3D12Heap` + placed resources | `VkDeviceMemory` + offsets |
| Allocator library | [D3D12MA](https://github.com/GPUOpen-LibrariesAndSDKs/D3D12MemoryAllocator) | [VMA](https://github.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator) |
| Memory budget | `IDXGIAdapter3::QueryVideoMemoryInfo` | `VK_EXT_memory_budget` |

## Use an allocator library

Allocating memory from the OS is slow, and the number of allocations is limited (`maxMemoryAllocationCount` is often 4096 in Vulkan). Real engines allocate large blocks and **sub-allocate** resources from them. Write your own only if you have a reason: the libraries handle alignment, memory type selection, defragmentation, and budgets, and are what most engines use.

=== "D3D12"

    ```cpp
    #include "D3D12MemAlloc.h"

    D3D12MA::ALLOCATOR_DESC allocatorDesc{};
    allocatorDesc.pDevice = device.Get();
    allocatorDesc.pAdapter = adapter.Get();
    D3D12MA::Allocator* allocator;
    HR_CHECK(D3D12MA::CreateAllocator(&allocatorDesc, &allocator));

    // A GPU-only buffer, created with an enhanced-barrier layout (buffers are always UNDEFINED).
    D3D12_RESOURCE_DESC1 desc{
        .Dimension = D3D12_RESOURCE_DIMENSION_BUFFER, .Width = 1 << 20, .Height = 1, .DepthOrArraySize = 1,
        .MipLevels = 1, .Format = DXGI_FORMAT_UNKNOWN, .SampleDesc = { 1, 0 },
        .Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR };
    D3D12MA::ALLOCATION_DESC allocDesc{};
    allocDesc.HeapType = D3D12_HEAP_TYPE_DEFAULT;
    D3D12MA::Allocation* allocation;
    ComPtr<ID3D12Resource> buffer;
    HR_CHECK(allocator->CreateResource3(&allocDesc, &desc, D3D12_BARRIER_LAYOUT_UNDEFINED,
                                        nullptr, 0, nullptr, &allocation, IID_PPV_ARGS(&buffer)));
    ```

=== "Vulkan"

    ```cpp
    #include <vk_mem_alloc.h>

    VmaAllocatorCreateInfo allocatorInfo{
        .flags = VMA_ALLOCATOR_CREATE_BUFFER_DEVICE_ADDRESS_BIT,
        .physicalDevice = physicalDevice, .device = device, .instance = instance,
        .vulkanApiVersion = VK_API_VERSION_1_3 };
    VmaAllocator allocator;
    VK_CHECK(vmaCreateAllocator(&allocatorInfo, &allocator));

    // A GPU-only vertex buffer: VMA picks a DEVICE_LOCAL type and sub-allocates from a large block.
    VkBufferCreateInfo vertexInfo{ .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = 1 << 20,
                                   .usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT };
    VmaAllocationCreateInfo gpuOnly{ .usage = VMA_MEMORY_USAGE_AUTO };
    VkBuffer vertexBuffer; VmaAllocation vertexAllocation;
    VK_CHECK(vmaCreateBuffer(allocator, &vertexInfo, &gpuOnly, &vertexBuffer, &vertexAllocation, nullptr));

    // A staging buffer the CPU writes once: host-visible and persistently mapped.
    VkBufferCreateInfo stagingInfo{ .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = 1 << 20,
                                    .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT };
    VmaAllocationCreateInfo upload{ .flags = VMA_ALLOCATION_CREATE_HOST_ACCESS_SEQUENTIAL_WRITE_BIT |
                                             VMA_ALLOCATION_CREATE_MAPPED_BIT,
                                    .usage = VMA_MEMORY_USAGE_AUTO };
    VkBuffer stagingBuffer; VmaAllocation stagingAllocation; VmaAllocationInfo stagingResult;
    VK_CHECK(vmaCreateBuffer(allocator, &stagingInfo, &upload, &stagingBuffer, &stagingAllocation, &stagingResult));
    std::memcpy(stagingResult.pMappedData, data, size);     // write sequentially; never read back from it
    ```

## Without a library

The underlying calls, for understanding what the libraries do and for the first triangle.

=== "D3D12"

    ```cpp
    ComPtr<ID3D12Resource> CreateBuffer(ID3D12Device10* device, uint64_t size, D3D12_HEAP_TYPE heapType)
    {
        D3D12_HEAP_PROPERTIES heap{ .Type = heapType };
        D3D12_RESOURCE_DESC1 desc{
            .Dimension = D3D12_RESOURCE_DIMENSION_BUFFER, .Width = size, .Height = 1, .DepthOrArraySize = 1,
            .MipLevels = 1, .Format = DXGI_FORMAT_UNKNOWN, .SampleDesc = { 1, 0 },
            .Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR };
        ComPtr<ID3D12Resource> buffer;
        // A committed resource: its own implicit heap. Fine for large or long-lived resources.
        HR_CHECK(device->CreateCommittedResource3(&heap, D3D12_HEAP_FLAG_NONE, &desc, D3D12_BARRIER_LAYOUT_UNDEFINED,
                                                  nullptr, nullptr, 0, nullptr, IID_PPV_ARGS(&buffer)));
        return buffer;
    }

    ComPtr<ID3D12Resource> CreateTexture(ID3D12Device10* device, uint32_t width, uint32_t height, DXGI_FORMAT format,
                                         D3D12_RESOURCE_FLAGS flags, D3D12_BARRIER_LAYOUT initialLayout)
    {
        D3D12_HEAP_PROPERTIES heap{ .Type = D3D12_HEAP_TYPE_DEFAULT };
        D3D12_RESOURCE_DESC1 desc{
            .Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D, .Width = width, .Height = height, .DepthOrArraySize = 1,
            .MipLevels = 1, .Format = format, .SampleDesc = { 1, 0 }, .Layout = D3D12_TEXTURE_LAYOUT_UNKNOWN,
            .Flags = flags };                          // e.g. D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET
        ComPtr<ID3D12Resource> texture;
        HR_CHECK(device->CreateCommittedResource3(&heap, D3D12_HEAP_FLAG_NONE, &desc, initialLayout,
                                                  nullptr, nullptr, 0, nullptr, IID_PPV_ARGS(&texture)));
        return texture;
    }
    ```

=== "Vulkan"

    ```cpp
    uint32_t FindMemoryType(uint32_t allowedTypes, VkMemoryPropertyFlags required)
    {
        for (uint32_t i = 0; i < memoryProperties.memoryTypeCount; i++)     // from vkGetPhysicalDeviceMemoryProperties
            if ((allowedTypes & (1u << i)) && (memoryProperties.memoryTypes[i].propertyFlags & required) == required)
                return i;
        throw std::runtime_error("no suitable memory type");
    }

    Buffer CreateBuffer(VkDeviceSize size, VkBufferUsageFlags usage, VkMemoryPropertyFlags properties)
    {
        Buffer b{};
        VkBufferCreateInfo info{ .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = size, .usage = usage,
                                 .sharingMode = VK_SHARING_MODE_EXCLUSIVE };
        VK_CHECK(vkCreateBuffer(device, &info, nullptr, &b.buffer));

        VkMemoryRequirements req;                   // size, alignment, and which memory types can hold it
        vkGetBufferMemoryRequirements(device, b.buffer, &req);
        VkMemoryAllocateInfo alloc{ .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, .allocationSize = req.size,
                                    .memoryTypeIndex = FindMemoryType(req.memoryTypeBits, properties) };
        VK_CHECK(vkAllocateMemory(device, &alloc, nullptr, &b.memory));   // one allocation per buffer: demo only
        VK_CHECK(vkBindBufferMemory(device, b.buffer, b.memory, 0));
        if (properties & VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT)
            VK_CHECK(vkMapMemory(device, b.memory, 0, VK_WHOLE_SIZE, 0, &b.mapped));   // map once, keep it mapped
        return b;
    }
    ```

    For buffers used with **buffer device address**, chain a `VkMemoryAllocateFlagsInfo` with `VK_MEMORY_ALLOCATE_DEVICE_ADDRESS_BIT` into the allocation. VMA does this when created with `VMA_ALLOCATOR_CREATE_BUFFER_DEVICE_ADDRESS_BIT`.

The Vulkan validation layer's best-practices mode warns about exactly this code: "allocating a VkDeviceMemory of size 4000. This is a very small allocation... sub-allocate from one large VkDeviceMemory." That is the reason for the library.

## Uploading data

GPU-only memory cannot be written by the CPU (except through resizable BAR, below). Write into an upload or staging buffer, then record a **copy** into the destination:

=== "D3D12"

    ```cpp
    // Textures in upload memory are laid out row by row, with each row padded to 256 bytes.
    D3D12_RESOURCE_DESC desc = texture->GetDesc();
    D3D12_PLACED_SUBRESOURCE_FOOTPRINT footprint;
    UINT rows; UINT64 rowSize, total;
    device->GetCopyableFootprints(&desc, 0, 1, 0, &footprint, &rows, &rowSize, &total);   // upload buffer needs `total` bytes

    uint8_t* mapped;
    D3D12_RANGE noRead{ 0, 0 };
    HR_CHECK(upload->Map(0, &noRead, reinterpret_cast<void**>(&mapped)));
    for (uint32_t y = 0; y < height; y++)
        std::memcpy(mapped + footprint.Offset + y * footprint.Footprint.RowPitch, pixels + y * rowBytes, rowBytes);
    upload->Unmap(0, nullptr);

    D3D12_TEXTURE_COPY_LOCATION dst{ .pResource = texture, .Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX, .SubresourceIndex = 0 };
    D3D12_TEXTURE_COPY_LOCATION src{ .pResource = upload, .Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT, .PlacedFootprint = footprint };
    list->CopyTextureRegion(&dst, 0, 0, 0, &src, nullptr);
    ```

=== "Vulkan"

    ```cpp
    // The texture must be in TRANSFER_DST_OPTIMAL for the copy: see synchronisation for ImageBarrier.
    ImageBarrier(cmd, texture.image,
                 VK_PIPELINE_STAGE_2_NONE, VK_ACCESS_2_NONE, VK_IMAGE_LAYOUT_UNDEFINED,
                 VK_PIPELINE_STAGE_2_COPY_BIT, VK_ACCESS_2_TRANSFER_WRITE_BIT, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
    VkBufferImageCopy copy{ .bufferOffset = 0, .bufferRowLength = 0,        // 0: rows are tightly packed
                            .imageSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }, .imageExtent = { width, height, 1 } };
    vkCmdCopyBufferToImage(cmd, staging.buffer, texture.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &copy);
    ImageBarrier(cmd, texture.image,
                 VK_PIPELINE_STAGE_2_COPY_BIT, VK_ACCESS_2_TRANSFER_WRITE_BIT, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                 VK_PIPELINE_STAGE_2_FRAGMENT_SHADER_BIT, VK_ACCESS_2_SHADER_SAMPLED_READ_BIT,
                 VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL);
    ```

- **Ring buffers for per-frame data.** Constants and dynamic vertices that change every frame go into one large, persistently mapped upload buffer, used as a ring with a region per [frame in flight](../../engine/rendering/frames-in-flight.md). No copy needed: the GPU reads upload memory directly, over PCIe. That is fine for small, read-once data and slow for anything read many times.
- **Static data** (meshes, textures) is copied once into GPU-only memory. Batch the copies, and use the [copy queue](async-compute.md#uploads) for streaming.
- **Resizable BAR** exposes all of video memory to the CPU (`D3D12_HEAP_TYPE_GPU_UPLOAD`, or a Vulkan type that is both `DEVICE_LOCAL` and `HOST_VISIBLE`). Writing straight into it skips the copy. Check support (`D3D12_FEATURE_D3D12_OPTIONS16::GPUUploadHeapSupported`, or look for the memory type) and fall back to staging when it is absent.
- **Never read from upload memory on the CPU.** It is write-combined: reads are uncached and extremely slow. Write sequentially, whole cache lines at a time, and keep the CPU's copy elsewhere.

## Alignment

| What | D3D12 | Vulkan |
| --- | --- | --- |
| Constant buffer offset and size | 256 bytes | `minUniformBufferOffsetAlignment` (often 64 or 256) |
| Storage buffer offset | 16 bytes for raw views | `minStorageBufferOffsetAlignment` |
| Texture row pitch in a copy | 256 bytes (`D3D12_TEXTURE_DATA_PITCH_ALIGNMENT`) | none (`bufferRowLength` 0 = tightly packed); `optimalBufferCopyRowPitchAlignment` for speed |
| Texture data offset in a copy | 512 bytes (`D3D12_TEXTURE_DATA_PLACEMENT_ALIGNMENT`) | `optimalBufferCopyOffsetAlignment` for speed |
| Placed resource or sub-allocation | 64 KiB (4 KiB for small textures, 4 MiB for MSAA) | `VkMemoryRequirements::alignment` |
| Buffer–image granularity | | `bufferImageGranularity`: linear and optimal resources sharing a page |

Query the Vulkan limits from `VkPhysicalDeviceLimits`, and round sub-allocations up with the [alignment helpers](../../maths/utilities.md#alignment).

## Residency and budgets

Video memory is shared with other applications and with the OS. Going over budget does not fail an allocation: the OS moves memory to system RAM, and frame times collapse.

- **Query the budget** every few frames (`QueryVideoMemoryInfo` on D3D12, `VK_EXT_memory_budget` on Vulkan) and stream lower texture mip levels when usage approaches it.
- D3D12 can **evict** and **make resident** heaps explicitly (`ID3D12Device::Evict`, `MakeResident`); the Vulkan driver manages residency itself, though the memory priority extension (`VK_EXT_memory_priority`) lets you say which allocations matter most.
- **Aliasing**: transient render targets used in different parts of the frame can share memory. A [render graph](../../engine/rendering/render-graph.md) works out the lifetimes; the APIs need placed resources in one heap (D3D12) or several images bound to the same memory (Vulkan), plus an aliasing barrier or a layout transition from `UNDEFINED` before the first use of each.

!!! warning "Common pitfalls"

    One `vkAllocateMemory` per resource runs out of allocations (`maxMemoryAllocationCount`) and is slow. Use VMA or sub-allocate.

    Reading back from upload or write-combined memory on the CPU is orders of magnitude slower than normal memory. Use readback memory (`HOST_CACHED`) for data you read.

    D3D12 texture uploads need rows padded to 256 bytes. Copy row by row using the footprint from `GetCopyableFootprints`, not one `memcpy`.

    Freeing or reusing a staging buffer before the GPU has executed the copy from it uploads garbage. Keep it until that frame's fence or timeline value has been reached.

    Over-committing video memory shows up as stutter, not as an error. Watch the budget.

## C# tips

- VMA and D3D12MA are C++ libraries. From C#, use the `Vortice.VulkanMemoryAllocator` package that goes with [Vortice.Vulkan](https://github.com/amerkoleci/Vortice.Vulkan), or call a small C wrapper of your own; Silk.NET does not ship VMA bindings.
- Map upload buffers once and write through a `Span<T>` over the mapped pointer (`new Span<Vertex>(mapped, count)`); `MemoryMarshal.AsBytes` and `CopyTo` compile to a `memcpy`.
