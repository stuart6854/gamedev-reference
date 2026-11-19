# Devices, queues, and command lists

The first objects an engine creates, and the ones every frame uses: the GPU and a logical device for it, the queues that execute work, and the command lists that record it.

| Step | D3D12 | Vulkan |
| --- | --- | --- |
| Entry point | `CreateDXGIFactory2` | `vkCreateInstance` (with layers and instance extensions) |
| List GPUs | `IDXGIFactory6::EnumAdapterByGpuPreference` | `vkEnumeratePhysicalDevices` |
| Check features | `ID3D12Device::CheckFeatureSupport` | `vkGetPhysicalDeviceFeatures2` |
| Create device | `D3D12CreateDevice(adapter, featureLevel)` | `vkCreateDevice` with the features to **enable** |
| Get queues | `CreateCommandQueue(type)` | `vkGetDeviceQueue(family, index)` |
| Command memory | `CreateCommandAllocator(type)` | `vkCreateCommandPool(family)` |
| Command list | `CreateCommandList1` (created closed) | `vkAllocateCommandBuffers` |
| Submit | `ExecuteCommandLists` | `vkQueueSubmit2` |

## The device

=== "D3D12"

    ```cpp
    // The Agility SDK: export these from the .exe so the runtime loads the D3D12Core.dll you ship.
    extern "C" { __declspec(dllexport) extern const UINT D3D12SDKVersion = 616; }      // 1.616 -> 616: the SDK you ship
    extern "C" { __declspec(dllexport) extern const char* D3D12SDKPath = ".\\D3D12\\"; }

    ComPtr<ID3D12Debug3> debug;                         // development builds: before creating the device
    if (SUCCEEDED(D3D12GetDebugInterface(IID_PPV_ARGS(&debug))))
        debug->EnableDebugLayer();

    ComPtr<IDXGIFactory6> factory;
    HR_CHECK(CreateDXGIFactory2(DXGI_CREATE_FACTORY_DEBUG, IID_PPV_ARGS(&factory)));

    // Adapters in order of preference: discrete GPUs first on laptops with two.
    ComPtr<IDXGIAdapter4> adapter;
    for (UINT i = 0; factory->EnumAdapterByGpuPreference(i, DXGI_GPU_PREFERENCE_HIGH_PERFORMANCE,
                                                         IID_PPV_ARGS(&adapter)) != DXGI_ERROR_NOT_FOUND; i++)
    {
        DXGI_ADAPTER_DESC3 desc;
        adapter->GetDesc3(&desc);
        if (!(desc.Flags & DXGI_ADAPTER_FLAG3_SOFTWARE)) break;     // skip the software rasteriser
    }

    ComPtr<ID3D12Device10> device;
    HR_CHECK(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_12_1, IID_PPV_ARGS(&device)));

    // Require what the renderer uses, once, at start-up.
    D3D12_FEATURE_DATA_D3D12_OPTIONS12 options12{};
    device->CheckFeatureSupport(D3D12_FEATURE_D3D12_OPTIONS12, &options12, sizeof(options12));
    D3D12_FEATURE_DATA_SHADER_MODEL shaderModel{ D3D_SHADER_MODEL_6_6 };   // in: the highest you know about
    device->CheckFeatureSupport(D3D12_FEATURE_SHADER_MODEL, &shaderModel, sizeof(shaderModel));
    D3D12_FEATURE_DATA_D3D12_OPTIONS options{};
    device->CheckFeatureSupport(D3D12_FEATURE_D3D12_OPTIONS, &options, sizeof(options));

    bool ok = options12.EnhancedBarriersSupported
           && shaderModel.HighestShaderModel >= D3D_SHADER_MODEL_6_6
           && options.ResourceBindingTier >= D3D12_RESOURCE_BINDING_TIER_3;
    ```

=== "Vulkan"

    ```cpp
    const char* layers[] = { "VK_LAYER_KHRONOS_validation" };                  // development builds only
    const char* instanceExtensions[] = { VK_EXT_DEBUG_UTILS_EXTENSION_NAME };  // plus the surface extensions
    VkApplicationInfo app{ .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO, .pApplicationName = "game",
                           .pEngineName = "engine", .apiVersion = VK_API_VERSION_1_3 };
    VkInstanceCreateInfo instanceInfo{
        .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app,
        .enabledLayerCount = 1, .ppEnabledLayerNames = layers,
        .enabledExtensionCount = 1, .ppEnabledExtensionNames = instanceExtensions };
    VK_CHECK(vkCreateInstance(&instanceInfo, nullptr, &instance));

    // Pick a Vulkan 1.3 device, preferring a discrete GPU.
    uint32_t count = 0;
    vkEnumeratePhysicalDevices(instance, &count, nullptr);
    std::vector<VkPhysicalDevice> devices(count);
    vkEnumeratePhysicalDevices(instance, &count, devices.data());
    for (VkPhysicalDevice candidate : devices)
    {
        VkPhysicalDeviceProperties props;
        vkGetPhysicalDeviceProperties(candidate, &props);
        if (props.apiVersion < VK_API_VERSION_1_3) continue;
        if (physicalDevice == VK_NULL_HANDLE || props.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU)
            physicalDevice = candidate;
    }

    // Query what is supported: the same structs, chained through pNext.
    VkPhysicalDeviceVulkan13Features features13{ .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES };
    VkPhysicalDeviceVulkan12Features features12{ .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES, .pNext = &features13 };
    VkPhysicalDeviceFeatures2 supported{ .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, .pNext = &features12 };
    vkGetPhysicalDeviceFeatures2(physicalDevice, &supported);
    // ...check every feature you need here, and fail with a clear message if one is missing...

    // Then enable exactly those: fresh structs, with only the needed bits set.
    features13 = { .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES,
                   .synchronization2 = VK_TRUE, .dynamicRendering = VK_TRUE, .maintenance4 = VK_TRUE };
    features12 = { .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES, .pNext = &features13,
                   .descriptorIndexing = VK_TRUE, .descriptorBindingSampledImageUpdateAfterBind = VK_TRUE,
                   .descriptorBindingPartiallyBound = VK_TRUE, .runtimeDescriptorArray = VK_TRUE,
                   .timelineSemaphore = VK_TRUE, .bufferDeviceAddress = VK_TRUE };
    VkPhysicalDeviceFeatures2 enabled{ .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, .pNext = &features12 };

    float priority = 1.0f;
    VkDeviceQueueCreateInfo queueInfo{ .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
                                       .queueFamilyIndex = graphicsFamily, .queueCount = 1, .pQueuePriorities = &priority };
    const char* deviceExtensions[] = { VK_KHR_SWAPCHAIN_EXTENSION_NAME };
    VkDeviceCreateInfo deviceInfo{ .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, .pNext = &enabled,
                                   .queueCreateInfoCount = 1, .pQueueCreateInfos = &queueInfo,
                                   .enabledExtensionCount = 1, .ppEnabledExtensionNames = deviceExtensions };
    VK_CHECK(vkCreateDevice(physicalDevice, &deviceInfo, nullptr, &device));
    ```

- **Check features once, at start-up**, and refuse to run with a clear message ("this GPU does not support Vulkan 1.3 / Shader Model 6.6") rather than failing later in a draw call.
- **Vulkan features must be enabled** to be used, even when the device supports them. Using a feature you did not enable is a validation error, and on some drivers undefined behaviour. D3D12 has no such step.
- **Vulkan 1.3 bundles** many former extensions as core features (`dynamicRendering`, `synchronization2`, `maintenance4`); they still need their feature bits set. Turn on `maintenance4` too: SPIR-V compiled for Vulkan 1.3 can use `LocalSizeId`, which requires it.
- **The Agility SDK** lets the game ship a newer D3D12 runtime than the installed Windows has, which is what makes enhanced barriers and recent shader models available on Windows 10. Without the two exports, you get whatever the OS provides.
- **A Vulkan loader** (`vulkan-1.dll`, `libvulkan.so`) loads drivers and layers. Link it directly, or load functions at run time with a loader library such as [volk](https://github.com/zeux/volk), which also gives faster per-device function pointers.

## Queues

=== "D3D12"

    ```cpp
    // Three types: DIRECT (graphics + compute + copy), COMPUTE, and COPY. Create what you use.
    D3D12_COMMAND_QUEUE_DESC desc{ .Type = D3D12_COMMAND_LIST_TYPE_DIRECT };
    HR_CHECK(device->CreateCommandQueue(&desc, IID_PPV_ARGS(&directQueue)));
    desc.Type = D3D12_COMMAND_LIST_TYPE_COMPUTE;
    HR_CHECK(device->CreateCommandQueue(&desc, IID_PPV_ARGS(&computeQueue)));
    desc.Type = D3D12_COMMAND_LIST_TYPE_COPY;
    HR_CHECK(device->CreateCommandQueue(&desc, IID_PPV_ARGS(&copyQueue)));
    ```

=== "Vulkan"

    ```cpp
    // Queue families differ per GPU: find them by their flags.
    vkGetPhysicalDeviceQueueFamilyProperties(physicalDevice, &count, nullptr);
    std::vector<VkQueueFamilyProperties> families(count);
    vkGetPhysicalDeviceQueueFamilyProperties(physicalDevice, &count, families.data());

    for (uint32_t i = 0; i < count; i++)
    {
        VkQueueFlags f = families[i].queueFlags;
        if ((f & VK_QUEUE_GRAPHICS_BIT) && graphicsFamily == UINT32_MAX) graphicsFamily = i;    // also does compute and transfer
        if ((f & VK_QUEUE_COMPUTE_BIT) && !(f & VK_QUEUE_GRAPHICS_BIT)) computeFamily = i;      // a dedicated async compute family
        if ((f & VK_QUEUE_TRANSFER_BIT) && !(f & (VK_QUEUE_GRAPHICS_BIT | VK_QUEUE_COMPUTE_BIT))) transferFamily = i;   // DMA engine
    }
    // Ask for the queues in VkDeviceCreateInfo, then: vkGetDeviceQueue(device, family, 0, &queue);
    ```

- The **graphics** queue can do everything; start with only that, and add [async compute and copy](async-compute.md) queues once something measurably benefits.
- Not every GPU has a dedicated compute or transfer family. Fall back to the graphics family.
- A Vulkan `VkQueue` must not be used from two threads at once; D3D12 queues are thread-safe. Submit from one thread, or lock.
- Check the graphics family can **present** to your window (`vkGetPhysicalDeviceSurfaceSupportKHR`); it nearly always can.

## Command lists

Recording uses two objects: the **memory** commands are written into (allocator or pool), and the **list** that writes them. The memory can only be reset when the GPU has finished executing everything recorded into it, so keep one per [frame in flight](../../engine/rendering/frames-in-flight.md), **per recording thread**.

=== "D3D12"

    ```cpp
    // Once: one allocator per frame in flight per thread, and a list (created closed).
    HR_CHECK(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT, IID_PPV_ARGS(&allocator)));
    HR_CHECK(device->CreateCommandList1(0, D3D12_COMMAND_LIST_TYPE_DIRECT, D3D12_COMMAND_LIST_FLAG_NONE, IID_PPV_ARGS(&list)));

    // Each frame, once the fence says this frame's previous use has finished:
    HR_CHECK(allocator->Reset());
    HR_CHECK(list->Reset(allocator.Get(), nullptr));
    // ... record ...
    HR_CHECK(list->Close());

    ID3D12CommandList* lists[] = { list.Get() };
    directQueue->ExecuteCommandLists(1, lists);
    HR_CHECK(directQueue->Signal(fence.Get(), ++fenceValue));     // see synchronisation
    ```

=== "Vulkan"

    ```cpp
    // Once: one pool per frame in flight per thread, and a command buffer from it.
    VkCommandPoolCreateInfo poolInfo{ .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO, .queueFamilyIndex = graphicsFamily };
    VK_CHECK(vkCreateCommandPool(device, &poolInfo, nullptr, &pool));
    VkCommandBufferAllocateInfo cmdInfo{ .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, .commandPool = pool,
                                         .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1 };
    VK_CHECK(vkAllocateCommandBuffers(device, &cmdInfo, &cmd));

    // Each frame, once the timeline says this frame's previous use has finished:
    VK_CHECK(vkResetCommandPool(device, pool, 0));          // resets every buffer from the pool at once
    VkCommandBufferBeginInfo begin{ .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
                                    .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT };
    VK_CHECK(vkBeginCommandBuffer(cmd, &begin));
    // ... record ...
    VK_CHECK(vkEndCommandBuffer(cmd));

    VkSemaphoreSubmitInfo signal{ .sType = VK_STRUCTURE_TYPE_SEMAPHORE_SUBMIT_INFO, .semaphore = timeline,
                                  .value = ++timelineValue, .stageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT };
    VkCommandBufferSubmitInfo cb{ .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_SUBMIT_INFO, .commandBuffer = cmd };
    VkSubmitInfo2 submit{ .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO_2,
                          .commandBufferInfoCount = 1, .pCommandBufferInfos = &cb,
                          .signalSemaphoreInfoCount = 1, .pSignalSemaphoreInfos = &signal };
    VK_CHECK(vkQueueSubmit2(queue, 1, &submit, VK_NULL_HANDLE));
    ```

- **Reset the pool, not each buffer.** `vkResetCommandPool` (and one D3D12 allocator per list) is cheaper than resetting command buffers one at a time, which also needs the `RESET_COMMAND_BUFFER` pool flag.
- **Record in parallel**: each thread records its own list from its own allocator or pool, and one thread submits them all in order. This is the main CPU win of the explicit APIs. See the [job system](../../engine/jobs/index.md).
- **Submit few, large batches.** Each `ExecuteCommandLists` or `vkQueueSubmit2` has a fixed cost in the driver and the OS. A handful per frame is normal; one per draw is not.
- D3D12 **bundles** and Vulkan **secondary command buffers** let you record a sequence once and replay it. They help less than they seem to on modern drivers; recording in parallel is the better tool.

!!! warning "Common pitfalls"

    Resetting a command allocator or pool while the GPU is still executing what was recorded into it corrupts that work, often with no error. Wait on the frame's fence or timeline value first.

    Using a Vulkan feature without enabling it at device creation is a validation error that some drivers tolerate and others do not. Enable everything you use.

    A D3D12 list created with `CreateCommandList` (not `CreateCommandList1`) starts open, and must be closed before its first `Reset`.

    Picking the first adapter or physical device can choose the integrated GPU on a laptop. Ask for high performance (D3D12) or prefer `DISCRETE_GPU` (Vulkan), and let players override it.
