# Swapchains and presenting

A **swapchain** is the set of images shown in a window: the game renders into one while the display shows another. Presenting hands a finished image to the OS compositor or the display. This is the one area where D3D12 and Vulkan differ most: D3D12 delegates it to DXGI, which handles the synchronisation, while Vulkan exposes it with its own semaphores.

| Step | D3D12 (DXGI) | Vulkan |
| --- | --- | --- |
| Window connection | the `HWND`, given to the swapchain | `VkSurfaceKHR` (`vkCreateWin32SurfaceKHR`, or from SDL / GLFW) |
| Create | `IDXGIFactory2::CreateSwapChainForHwnd(queue, ...)` | `vkCreateSwapchainKHR` |
| Images | `GetBuffer(i)` | `vkGetSwapchainImagesKHR` |
| Which image to render | `GetCurrentBackBufferIndex()` | `vkAcquireNextImageKHR` (returns an index and signals a semaphore) |
| Show it | `Present(syncInterval, flags)` | `vkQueuePresentKHR` (waits on a semaphore) |
| Vsync / tearing | `syncInterval` 1 or 0, `DXGI_PRESENT_ALLOW_TEARING` | present mode: `FIFO`, `MAILBOX`, `IMMEDIATE` |
| Window resized | `ResizeBuffers` | recreate on `VK_ERROR_OUT_OF_DATE_KHR` or `VK_SUBOPTIMAL_KHR` |
| Latency control | frame latency waitable object | `VK_KHR_present_wait` |

## Creating the swapchain

=== "D3D12"

    ```cpp
    // Tearing (vsync off with variable refresh rate displays) must be supported and requested at creation.
    BOOL allowTearing = FALSE;
    ComPtr<IDXGIFactory5> factory5;
    if (SUCCEEDED(factory.As(&factory5)))
        factory5->CheckFeatureSupport(DXGI_FEATURE_PRESENT_ALLOW_TEARING, &allowTearing, sizeof(allowTearing));

    swapchainFlags = DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT |
                     (allowTearing ? DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING : 0);
    DXGI_SWAP_CHAIN_DESC1 desc{
        .Width = 0, .Height = 0,                              // 0: the window's client size
        .Format = DXGI_FORMAT_R8G8B8A8_UNORM,                 // flip model: no _SRGB formats here (see below)
        .SampleDesc = { 1, 0 },
        .BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT,
        .BufferCount = 3,
        .Scaling = DXGI_SCALING_STRETCH,
        .SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD,          // the flip model: required for D3D12
        .AlphaMode = DXGI_ALPHA_MODE_UNSPECIFIED,
        .Flags = swapchainFlags };

    ComPtr<IDXGISwapChain1> swapchain1;
    HR_CHECK(factory->CreateSwapChainForHwnd(directQueue.Get(),   // the queue, not the device
                                             hwnd, &desc, nullptr, nullptr, &swapchain1));
    HR_CHECK(swapchain1.As(&swapchain));                          // IDXGISwapChain4
    factory->MakeWindowAssociation(hwnd, DXGI_MWA_NO_ALT_ENTER);  // handle fullscreen yourself

    swapchain->SetMaximumFrameLatency(1);
    frameLatencyWaitable = swapchain->GetFrameLatencyWaitableObject();

    for (UINT i = 0; i < 3; i++)
    {
        HR_CHECK(swapchain->GetBuffer(i, IID_PPV_ARGS(&backBuffers[i])));
        D3D12_RENDER_TARGET_VIEW_DESC rtv{ .Format = DXGI_FORMAT_R8G8B8A8_UNORM_SRGB,   // sRGB conversion on write
                                           .ViewDimension = D3D12_RTV_DIMENSION_TEXTURE2D };
        device->CreateRenderTargetView(backBuffers[i].Get(), &rtv, RtvHandle(i));
    }
    ```

=== "Vulkan"

    ```cpp
    struct Swapchain
    {
        VkSwapchainKHR handle = VK_NULL_HANDLE;
        VkFormat format;
        VkExtent2D extent;
        std::vector<VkImage> images;
        std::vector<VkImageView> views;
        std::vector<VkSemaphore> renderFinished;     // one per image, not per frame: see below
    };

    Swapchain CreateSwapchain(uint32_t windowWidth, uint32_t windowHeight, bool vsync, VkSwapchainKHR old)
    {
        Swapchain sc;
        VkSurfaceCapabilitiesKHR caps;
        VK_CHECK(vkGetPhysicalDeviceSurfaceCapabilitiesKHR(physicalDevice, surface, &caps));

        uint32_t count = 0;
        vkGetPhysicalDeviceSurfaceFormatsKHR(physicalDevice, surface, &count, nullptr);
        std::vector<VkSurfaceFormatKHR> formats(count);
        vkGetPhysicalDeviceSurfaceFormatsKHR(physicalDevice, surface, &count, formats.data());
        VkSurfaceFormatKHR chosen = formats[0];
        for (VkSurfaceFormatKHR f : formats)
            if (f.format == VK_FORMAT_B8G8R8A8_SRGB && f.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR) chosen = f;

        vkGetPhysicalDeviceSurfacePresentModesKHR(physicalDevice, surface, &count, nullptr);
        std::vector<VkPresentModeKHR> modes(count);
        vkGetPhysicalDeviceSurfacePresentModesKHR(physicalDevice, surface, &count, modes.data());
        auto has = [&](VkPresentModeKHR m) { return std::find(modes.begin(), modes.end(), m) != modes.end(); };
        VkPresentModeKHR mode = VK_PRESENT_MODE_FIFO_KHR;                        // vsync: always supported
        if (!vsync && has(VK_PRESENT_MODE_IMMEDIATE_KHR)) mode = VK_PRESENT_MODE_IMMEDIATE_KHR;
        else if (!vsync && has(VK_PRESENT_MODE_MAILBOX_KHR)) mode = VK_PRESENT_MODE_MAILBOX_KHR;

        sc.extent = caps.currentExtent;
        if (sc.extent.width == UINT32_MAX)                                       // the window lets us choose
            sc.extent = { std::clamp(windowWidth,  caps.minImageExtent.width,  caps.maxImageExtent.width),
                          std::clamp(windowHeight, caps.minImageExtent.height, caps.maxImageExtent.height) };
        uint32_t imageCount = std::max(caps.minImageCount + 1, 3u);
        if (caps.maxImageCount > 0) imageCount = std::min(imageCount, caps.maxImageCount);   // 0: no limit

        VkSwapchainCreateInfoKHR info{
            .sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR, .surface = surface,
            .minImageCount = imageCount, .imageFormat = chosen.format, .imageColorSpace = chosen.colorSpace,
            .imageExtent = sc.extent, .imageArrayLayers = 1,
            .imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT,
            .imageSharingMode = VK_SHARING_MODE_EXCLUSIVE,
            .preTransform = caps.currentTransform, .compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR,
            .presentMode = mode, .clipped = VK_TRUE, .oldSwapchain = old };
        VK_CHECK(vkCreateSwapchainKHR(device, &info, nullptr, &sc.handle));
        sc.format = chosen.format;

        vkGetSwapchainImagesKHR(device, sc.handle, &count, nullptr);
        sc.images.resize(count);
        vkGetSwapchainImagesKHR(device, sc.handle, &count, sc.images.data());
        VkSemaphoreCreateInfo binary{ .sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO };
        for (VkImage image : sc.images)
        {
            VkImageViewCreateInfo view{ .sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, .image = image,
                                        .viewType = VK_IMAGE_VIEW_TYPE_2D, .format = sc.format,
                                        .subresourceRange = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 } };
            VK_CHECK(vkCreateImageView(device, &view, nullptr, &sc.views.emplace_back()));
            VK_CHECK(vkCreateSemaphore(device, &binary, nullptr, &sc.renderFinished.emplace_back()));
        }
        return sc;
    }
    ```

    The instance needs `VK_KHR_surface` and the platform's surface extension (`VK_KHR_win32_surface`, `VK_KHR_wayland_surface`, ...; SDL and GLFW report the list), and the device needs `VK_KHR_swapchain`.

### Present modes

| Want | D3D12 | Vulkan | Notes |
| --- | --- | --- | --- |
| Vsync | `Present(1, 0)` | `FIFO` | always available; adds up to a frame of latency |
| Uncapped, may tear | `Present(0, DXGI_PRESENT_ALLOW_TEARING)` | `IMMEDIATE` | lowest latency; works with variable refresh rate displays |
| Uncapped, no tearing | `Present(0, 0)` | `MAILBOX` | renders faster than the display and shows the newest frame; wastes power |

`DXGI_PRESENT_ALLOW_TEARING` needs the matching swapchain flag, sync interval 0, and a windowed or borderless window. Exclusive fullscreen is no longer necessary on Windows 10 and later: the flip model in a borderless window gets the same latency through independent flip.

### sRGB

Rendering into an sRGB format applies the linear-to-sRGB conversion on write, which the [colour pipeline](../pbr/colour.md) needs at the end.

- **D3D12**: flip-model swapchains cannot use `_SRGB` formats. Create the swapchain as `R8G8B8A8_UNORM` and the render target **view** as `R8G8B8A8_UNORM_SRGB`.
- **Vulkan**: choose an `_SRGB` surface format directly, as above. If only `UNORM` formats are offered, do the conversion in the final shader.
- **HDR** output uses a 10-bit or 16-bit format with an HDR colour space: `SetColorSpace1(DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020)` on D3D12, or a surface format with `VK_COLOR_SPACE_HDR10_ST2084_EXT` on Vulkan. Check support first (`CheckColorSpaceSupport`, the surface format list).

## Each frame

=== "D3D12"

    ```cpp
    // Wait until DXGI is ready for another frame: this is what keeps latency low.
    WaitForSingleObjectEx(frameLatencyWaitable, 1000, TRUE);
    UINT index = swapchain->GetCurrentBackBufferIndex();
    ID3D12Resource* backBuffer = backBuffers[index].Get();

    // Swapchain buffers are in the PRESENT layout when we get them.
    TextureBarrier(list, backBuffer,
                   D3D12_BARRIER_SYNC_NONE, D3D12_BARRIER_ACCESS_NO_ACCESS, D3D12_BARRIER_LAYOUT_PRESENT,
                   D3D12_BARRIER_SYNC_RENDER_TARGET, D3D12_BARRIER_ACCESS_RENDER_TARGET, D3D12_BARRIER_LAYOUT_RENDER_TARGET);
    // ... render into RtvHandle(index) ...
    TextureBarrier(list, backBuffer,
                   D3D12_BARRIER_SYNC_RENDER_TARGET, D3D12_BARRIER_ACCESS_RENDER_TARGET, D3D12_BARRIER_LAYOUT_RENDER_TARGET,
                   D3D12_BARRIER_SYNC_NONE, D3D12_BARRIER_ACCESS_NO_ACCESS, D3D12_BARRIER_LAYOUT_PRESENT);
    HR_CHECK(list->Close());
    directQueue->ExecuteCommandLists(1, CommandListCast(list.GetAddressOf()));

    UINT presentFlags = (!vsync && allowTearing) ? DXGI_PRESENT_ALLOW_TEARING : 0;
    HR_CHECK(swapchain->Present(vsync ? 1 : 0, presentFlags));    // DXGI orders it after the submitted work
    frame.fenceValue = Signal(directQueue.Get());
    ```

=== "Vulkan"

    ```cpp
    bool RenderFrame(Swapchain& sc, Frame& frame)
    {
        uint32_t imageIndex;
        VkResult acquire = vkAcquireNextImageKHR(device, sc.handle, UINT64_MAX, frame.imageAcquired,
                                                 VK_NULL_HANDLE, &imageIndex);
        if (acquire == VK_ERROR_OUT_OF_DATE_KHR) return false;              // recreate, then try again
        VkImage image = sc.images[imageIndex];

        // ... begin frame.cmd ...
        // The acquire semaphore is waited on at COLOR_ATTACHMENT_OUTPUT, so the transition starts at that stage.
        ImageBarrier(frame.cmd, image,
                     VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT, VK_ACCESS_2_NONE, VK_IMAGE_LAYOUT_UNDEFINED,
                     VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT, VK_ACCESS_2_COLOR_ATTACHMENT_WRITE_BIT,
                     VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL);
        // ... render into sc.views[imageIndex] ...
        ImageBarrier(frame.cmd, image,
                     VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT, VK_ACCESS_2_COLOR_ATTACHMENT_WRITE_BIT,
                     VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
                     VK_PIPELINE_STAGE_2_NONE, VK_ACCESS_2_NONE, VK_IMAGE_LAYOUT_PRESENT_SRC_KHR);
        // ... end frame.cmd ...

        VkSemaphoreSubmitInfo wait{ .sType = VK_STRUCTURE_TYPE_SEMAPHORE_SUBMIT_INFO, .semaphore = frame.imageAcquired,
                                    .stageMask = VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT };
        VkSemaphoreSubmitInfo signals[] = {
            { .sType = VK_STRUCTURE_TYPE_SEMAPHORE_SUBMIT_INFO, .semaphore = sc.renderFinished[imageIndex],
              .stageMask = VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT },
            { .sType = VK_STRUCTURE_TYPE_SEMAPHORE_SUBMIT_INFO, .semaphore = timeline, .value = ++timelineValue,
              .stageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT },
        };
        VkCommandBufferSubmitInfo cb{ .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_SUBMIT_INFO, .commandBuffer = frame.cmd };
        VkSubmitInfo2 submit{ .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO_2,
                              .waitSemaphoreInfoCount = 1, .pWaitSemaphoreInfos = &wait,
                              .commandBufferInfoCount = 1, .pCommandBufferInfos = &cb,
                              .signalSemaphoreInfoCount = 2, .pSignalSemaphoreInfos = signals };
        VK_CHECK(vkQueueSubmit2(queue, 1, &submit, VK_NULL_HANDLE));
        frame.timelineValue = timelineValue;                               // wait for this before reusing the frame

        VkPresentInfoKHR present{ .sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR,
                                  .waitSemaphoreCount = 1, .pWaitSemaphores = &sc.renderFinished[imageIndex],
                                  .swapchainCount = 1, .pSwapchains = &sc.handle, .pImageIndices = &imageIndex };
        VkResult result = vkQueuePresentKHR(queue, &present);
        return result != VK_ERROR_OUT_OF_DATE_KHR && result != VK_SUBOPTIMAL_KHR;   // false: recreate
    }
    ```

    - **`imageAcquired`: one per frame in flight.** It is waited on by this frame's submission, and that submission has finished by the time the frame comes round again.
    - **`renderFinished`: one per swapchain image.** Presentation waits on it, and nothing tells you when presentation has finished with it. The image index, however, cannot come back from `vkAcquireNextImageKHR` until its previous present is done, so a semaphore per image is safe to reuse. A semaphore per frame is the most common swapchain bug, and validation reports it. (`VK_EXT_swapchain_maintenance1` adds a present fence that solves this more directly.)

## Resizing

=== "D3D12"

    ```cpp
    void Resize(uint32_t width, uint32_t height)
    {
        if (width == 0 || height == 0) return;                // minimised
        WaitForGpuIdle();                                      // signal the queue and wait on the fence
        for (auto& buffer : backBuffers) buffer.Reset();       // every reference must be released first
        HR_CHECK(swapchain->ResizeBuffers(0, width, height, DXGI_FORMAT_UNKNOWN, swapchainFlags));   // same flags as creation
        // ... GetBuffer and CreateRenderTargetView again ...
    }
    ```

=== "Vulkan"

    ```cpp
    void RecreateSwapchain(Swapchain& sc, uint32_t width, uint32_t height, bool vsync)
    {
        if (width == 0 || height == 0) return;                 // minimised: try again later
        vkDeviceWaitIdle(device);                              // simplest correct choice
        Swapchain next = CreateSwapchain(width, height, vsync, sc.handle);   // the old one lets the driver reuse memory
        for (VkImageView v : sc.views) vkDestroyImageView(device, v, nullptr);
        for (VkSemaphore s : sc.renderFinished) vkDestroySemaphore(device, s, nullptr);
        vkDestroySwapchainKHR(device, sc.handle, nullptr);
        sc = std::move(next);
    }
    ```

Recreate screen-sized render targets (depth buffer, G-buffer, post-processing targets) at the same time, and pipelines too if the swapchain format changed.

## Frame pacing and latency

How far the CPU runs ahead of the display decides input latency. The [frames in flight](../../engine/rendering/frames-in-flight.md#presenting) page covers the reasoning; the API pieces are:

- **D3D12**: `SetMaximumFrameLatency(1)` plus waiting on the **frame latency waitable object** at the start of each frame. The wait returns when DXGI can accept another frame, so input is sampled as late as possible.
- **Vulkan**: `VK_KHR_present_id` and `VK_KHR_present_wait` let the CPU wait until a given present has reached the display, which plays the same role. Without them, the number of frames in flight and the swapchain image count bound the latency.
- Vendor low-latency SDKs (NVIDIA Reflex, AMD Anti-Lag) go further, and hook in at the same point.

!!! warning "Common pitfalls"

    Using one `renderFinished` semaphore per frame in flight, rather than per swapchain image, reuses a semaphore that a present may still be waiting on.

    `ResizeBuffers` fails while any reference to a back buffer is alive, including one held by a descriptor view's resource or a pending command list. Release them all and wait for the GPU first.

    Ignoring `VK_SUBOPTIMAL_KHR` keeps presenting a swapchain that no longer matches the window, which some platforms scale and others refuse.

    Creating a D3D12 swapchain with an `_SRGB` format fails with the flip model. Use an sRGB render target view instead.

    A swapchain created without `DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING` cannot present with `DXGI_PRESENT_ALLOW_TEARING`; the call fails.

## C# tips

- Window creation and the native handle come from the windowing library: `SDL_GetPointerProperty(..., SDL_PROP_WINDOW_WIN32_HWND_POINTER, ...)` with SDL3, or `Silk.NET.Windowing`, which can also create the Vulkan surface (`IVkSurface.Create`).
- Keep the swapchain images, views, and semaphores in arrays indexed by the image index, and resize them on recreation; do not assume the image count you asked for is the count you got.
