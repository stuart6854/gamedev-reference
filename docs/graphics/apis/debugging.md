# Debugging

The explicit APIs check almost nothing at run time. A wrong barrier, a stale descriptor, or a struct field left at zero is undefined behaviour: it may work, render garbage, or remove the device several frames later. The tools that make this manageable are the **validation layers**, **names and markers** on objects and passes, **frame captures**, and **crash diagnostics** for a lost device.

| Tool | D3D12 | Vulkan |
| --- | --- | --- |
| API validation | the debug layer (`ID3D12Debug::EnableDebugLayer`) | `VK_LAYER_KHRONOS_validation` |
| Validation on the GPU | GPU-based validation | GPU-assisted validation (`VK_VALIDATION_FEATURE_ENABLE_GPU_ASSISTED_EXT`) |
| Synchronisation checks | GPU-based validation (layouts at use) | synchronisation validation |
| Messages | `ID3D12InfoQueue` (break on severity, or a callback) | `VkDebugUtilsMessengerEXT` callback |
| Object names | `ID3D12Object::SetName` | `vkSetDebugUtilsObjectNameEXT` |
| Pass markers | PIX events (`PIXBeginEvent`) | `vkCmdBeginDebugUtilsLabelEXT` |
| Frame capture | PIX, RenderDoc | RenderDoc, Nsight Graphics, Radeon GPU Profiler |
| Lost device | DRED (auto-breadcrumbs, page faults) | `VK_EXT_device_fault`, vendor checkpoints |

## Validation

Turn validation on in every development build, and treat each message as a bug. It costs CPU time (and a lot for GPU-based validation), so make it a start-up option rather than always on.

=== "D3D12"

    ```cpp
    // Before creating the device.
    ComPtr<ID3D12Debug3> debug;
    if (SUCCEEDED(D3D12GetDebugInterface(IID_PPV_ARGS(&debug))))
    {
        debug->EnableDebugLayer();
        debug->SetEnableGPUBasedValidation(gpuBasedValidation);     // slow: run it regularly, not always
    }

    // After creating the device: stop in the debugger on errors.
    ComPtr<ID3D12InfoQueue> infoQueue;
    if (SUCCEEDED(device->QueryInterface(IID_PPV_ARGS(&infoQueue))))
    {
        infoQueue->SetBreakOnSeverity(D3D12_MESSAGE_SEVERITY_CORRUPTION, TRUE);
        infoQueue->SetBreakOnSeverity(D3D12_MESSAGE_SEVERITY_ERROR, TRUE);
    }
    ```

    The debug layer comes with the "Graphics Tools" optional Windows feature. `ID3D12InfoQueue1::RegisterMessageCallback` (Agility SDK) sends messages to your own log instead of the debugger output.

=== "Vulkan"

    ```cpp
    static VKAPI_ATTR VkBool32 VKAPI_CALL OnValidationMessage(
        VkDebugUtilsMessageSeverityFlagBitsEXT severity, VkDebugUtilsMessageTypeFlagsEXT,
        const VkDebugUtilsMessengerCallbackDataEXT* data, void*)
    {
        if (severity >= VK_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT)
            LogError("[vulkan] %s", data->pMessage);                  // break here in the debugger on errors
        return VK_FALSE;                                               // never abort the call that triggered it
    }

    VkDebugUtilsMessengerCreateInfoEXT messengerInfo{
        .sType = VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT,
        .messageSeverity = VK_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT | VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT,
        .messageType = VK_DEBUG_UTILS_MESSAGE_TYPE_GENERAL_BIT_EXT | VK_DEBUG_UTILS_MESSAGE_TYPE_VALIDATION_BIT_EXT |
                       VK_DEBUG_UTILS_MESSAGE_TYPE_PERFORMANCE_BIT_EXT,
        .pfnUserCallback = OnValidationMessage };

    // Extra checks, chained into VkInstanceCreateInfo (or set in vkconfig without code changes).
    VkValidationFeatureEnableEXT enables[] = { VK_VALIDATION_FEATURE_ENABLE_SYNCHRONIZATION_VALIDATION_EXT,
                                               VK_VALIDATION_FEATURE_ENABLE_BEST_PRACTICES_EXT };
    VkValidationFeaturesEXT validationFeatures{ .sType = VK_STRUCTURE_TYPE_VALIDATION_FEATURES_EXT, .pNext = &messengerInfo,
                                                .enabledValidationFeatureCount = 2, .pEnabledValidationFeatures = enables };
    instanceInfo.pNext = &validationFeatures;   // the messenger in the chain also reports problems inside vkCreateInstance

    VK_CHECK(vkCreateInstance(&instanceInfo, nullptr, &instance));
    auto createMessenger = (PFN_vkCreateDebugUtilsMessengerEXT)vkGetInstanceProcAddr(instance, "vkCreateDebugUtilsMessengerEXT");
    VK_CHECK(createMessenger(instance, &messengerInfo, nullptr, &messenger));
    ```

    The layer ships with the Vulkan SDK (and as `vulkan-validationlayers` on Linux). **vkconfig** turns on synchronisation validation, GPU-assisted validation, and best practices for any program, and filters messages.

What each one catches, from running the code on these pages:

- **Core validation**: wrong struct values, missing features (using `LocalSizeId` without enabling `maintenance4` was reported here), objects used after destruction, mismatched pipeline and attachment formats.
- **Synchronisation validation**: read-after-write and write-after-write hazards between commands, missing layout transitions.
- **Best practices**: performance problems, such as many small memory allocations ("sub-allocate from one large VkDeviceMemory") and `ALL_COMMANDS` stage masks in semaphore waits.
- **GPU-based or GPU-assisted validation**: errors only visible while shaders run: out-of-bounds descriptor indices in bindless arrays, descriptors that were never written, textures in the wrong layout at the point a shader samples them.

## Names and markers

Name every object, and mark every pass. Validation messages, captures, and crash reports then say "Shadow map (cascade 0)" and "Shadows > Cascade 0", not a hex handle.

=== "D3D12"

    ```cpp
    shadowMap->SetName(L"Shadow map (cascade 0)");
    directQueue->SetName(L"Direct queue");

    // Markers, with WinPixEventRuntime (pix3.h): PIX, RenderDoc, and the vendor tools all read them.
    PIXBeginEvent(list.Get(), PIX_COLOR(50, 50, 200), "Shadows");
    // ... the shadow passes ...
    PIXEndEvent(list.Get());
    ```

=== "Vulkan"

    ```cpp
    // Extension functions: load them once (VK_EXT_debug_utils must be enabled on the instance).
    auto setName    = (PFN_vkSetDebugUtilsObjectNameEXT)vkGetInstanceProcAddr(instance, "vkSetDebugUtilsObjectNameEXT");
    auto beginLabel = (PFN_vkCmdBeginDebugUtilsLabelEXT)vkGetInstanceProcAddr(instance, "vkCmdBeginDebugUtilsLabelEXT");
    auto endLabel   = (PFN_vkCmdEndDebugUtilsLabelEXT)vkGetInstanceProcAddr(instance, "vkCmdEndDebugUtilsLabelEXT");

    VkDebugUtilsObjectNameInfoEXT name{ .sType = VK_STRUCTURE_TYPE_DEBUG_UTILS_OBJECT_NAME_INFO_EXT,
                                        .objectType = VK_OBJECT_TYPE_IMAGE, .objectHandle = (uint64_t)shadowMap,
                                        .pObjectName = "Shadow map (cascade 0)" };
    setName(device, &name);

    VkDebugUtilsLabelEXT label{ .sType = VK_STRUCTURE_TYPE_DEBUG_UTILS_LABEL_EXT, .pLabelName = "Shadows",
                                .color = { 0.2f, 0.2f, 0.8f, 1.0f } };
    beginLabel(cmd, &label);
    // ... the shadow passes ...
    endLabel(cmd);
    ```

Put markers in the RHI (`cmd.begin_marker("Shadows")`, as on the [RHI page](../../engine/rendering/rhi.md#backends)), and have the [render graph](../../engine/rendering/render-graph.md) add one per pass automatically. The same scopes can drive [GPU timestamps](../../engine/profiling.md#gpu-timing).

## Frame captures

A capture records every API call of one frame and replays it, so you can inspect each draw: its inputs, outputs, pipeline state, and the contents of every buffer and texture.

- **[RenderDoc](https://renderdoc.org/)** works with both APIs. Its in-application API (`renderdoc_app.h`) lets the game trigger a capture from a key or a console command, around exactly the frame that goes wrong.
- **PIX** (D3D12) adds GPU timing and occupancy per pass, and shader debugging; it needs `-Zi` debug information in the shaders (see [shader compilation](shaders.md#compiling)).
- **Vendor tools**: Nsight Graphics (NVIDIA) and Radeon GPU Profiler (AMD) show what the hardware did: wave occupancy, cache hit rates, and how async compute overlapped.

A capture shows the state the GPU **was told to use**. When a capture looks right but the screen is wrong, suspect synchronisation: the capture tool serialises work, which hides races.

## A lost device

When the GPU faults or hangs, the OS resets it, and every later API call fails with `DXGI_ERROR_DEVICE_REMOVED` or `VK_ERROR_DEVICE_LOST`. The call that reports it is rarely the one that caused it. To find the cause, the API needs to record what the GPU was doing:

=== "D3D12"

    ```cpp
    // Before creating the device: Device Removed Extended Data.
    ComPtr<ID3D12DeviceRemovedExtendedDataSettings1> dredSettings;
    if (SUCCEEDED(D3D12GetDebugInterface(IID_PPV_ARGS(&dredSettings))))
    {
        dredSettings->SetAutoBreadcrumbsEnablement(D3D12_DRED_ENABLEMENT_FORCED_ON);
        dredSettings->SetPageFaultEnablement(D3D12_DRED_ENABLEMENT_FORCED_ON);
    }

    // When Present or a fence wait reports the device as removed:
    void ReportDeviceRemoved(ID3D12Device* device)
    {
        LogError("device removed: 0x%08x", (unsigned)device->GetDeviceRemovedReason());
        ComPtr<ID3D12DeviceRemovedExtendedData1> dred;
        if (FAILED(device->QueryInterface(IID_PPV_ARGS(&dred)))) return;

        D3D12_DRED_AUTO_BREADCRUMBS_OUTPUT1 breadcrumbs{};
        if (SUCCEEDED(dred->GetAutoBreadcrumbsOutput1(&breadcrumbs)))
            for (const D3D12_AUTO_BREADCRUMB_NODE1* node = breadcrumbs.pHeadAutoBreadcrumbNode; node; node = node->pNext)
            {
                uint32_t done = *node->pLastBreadcrumbValue;
                if (done < node->BreadcrumbCount)              // this command list did not finish
                    LogError("unfinished: %ls, operation %u of %u",
                             node->pCommandListDebugNameW ? node->pCommandListDebugNameW : L"?", done, node->BreadcrumbCount);
            }
        D3D12_DRED_PAGE_FAULT_OUTPUT1 pageFault{};
        if (SUCCEEDED(dred->GetPageFaultAllocationOutput1(&pageFault)))
            LogError("page fault at GPU address 0x%llx", (unsigned long long)pageFault.PageFaultVA);
    }
    ```

    The breadcrumbs name the command lists that did not finish, and the operation (draw, dispatch, copy) within each where the GPU stopped. Named command lists are what make this readable. DRED's page-fault data also lists recently freed allocations near the faulting address: a use after free shows up there.

=== "Vulkan"

    - **`VK_EXT_device_fault`**: after `VK_ERROR_DEVICE_LOST`, `vkGetDeviceFaultInfoEXT` returns a description and the faulting addresses, where the driver supports it.
    - **Manual breadcrumbs**: write an increasing marker value into a host-visible buffer between passes (`vkCmdFillBuffer`, or `vkCmdWriteBufferMarker2AMD` with `VK_AMD_buffer_marker`), and after a loss read the last value that arrived. This works on every driver, and the D3D12 equivalent is `WriteBufferImmediate`.
    - **Vendor tools**: NVIDIA Nsight Aftermath and AMD Radeon GPU Detective produce crash dumps with the faulting shader and draw, for both APIs.

Common causes of a lost device, in rough order: an out-of-bounds read through a stale or wrong descriptor index; a resource freed while the GPU still used it; an infinite loop in a shader; a wait on a fence value that is never signalled; and a [TDR](https://learn.microsoft.com/windows-hardware/drivers/display/timeout-detection-and-recovery) on Windows when a single submission takes more than about two seconds.

## A workflow

1. Run with **validation** and fix every message, including warnings.
2. Run with **synchronisation validation** (Vulkan) and **GPU-based validation** (D3D12) regularly, such as nightly on the test levels, because they are too slow for everyday use.
3. **Name and mark** everything, so 1 and 2 report readable messages.
4. For a visual bug, **capture** the frame and step through the draws.
5. For a crash, enable **DRED** or **device fault** reporting and breadcrumbs, and have the game write their output to its log, so reports from players' machines contain them.
6. Test on **all three vendors**. Synchronisation bugs in particular hide on one vendor's hardware and appear on another's.

!!! warning "Common pitfalls"

    Shipping with validation layers enabled costs CPU time and fails on players' machines that do not have them installed. Enable them from a command-line option or a developer setting.

    A clean validation run does not prove the barriers are right: core validation does not track hazards. Run synchronisation validation too.

    Device removal reported by `Present` is usually caused by work submitted earlier. Read DRED or the breadcrumbs, rather than debugging the call that returned the error.

    Captures serialise GPU work, so a race that corrupts the screen can disappear in the capture. If a capture looks correct, suspect synchronisation.

## C# tips

- Register the Vulkan messenger callback as a static method marked `[UnmanagedCallersOnly]` and pass `&OnValidationMessage` as a `delegate* unmanaged<...>`; a managed delegate would need to be kept alive, and is easy to let the GC collect.
- Wrap names and markers in `[Conditional("DEBUG")]` methods (or a development-build check), so they cost nothing in shipping builds.
