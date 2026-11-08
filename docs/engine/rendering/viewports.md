# Viewports and windows

A game usually draws to one window. An editor draws to several: a main window with a scene view and a game view, a second window on another monitor with the material editor's preview, and floating panels dragged out of the main window. Each needs its own swapchain or render target, sized and resized independently.

## Swapchains per window

Each OS window has its own swapchain, created from the window's surface (Vulkan) or handle (DXGI). The device, queues, pipelines, and resources are shared.

```text
Window { os_handle, swapchain, width, height, needs_resize }

render_frame():
    wait for this frame slot's fence                       // see frames in flight
    for window in windows:
        if window.minimised: continue
        if window.needs_resize: recreate_swapchain(window)
        window.image = acquire_next_image(window.swapchain)
    build one render graph containing every window's views and UI
    submit
    present every acquired image                          // Vulkan: one present call can take several swapchains
```

- Build **one render graph** for all windows, so passes shared between them (shadow maps for the scene, shared post-processing resources) run once.
- **Vsync** with several windows: each vsync'd present can wait for a vertical blank. Present the main window with vsync and the others without, or present all in one call (`vkQueuePresentKHR` takes an array of swapchains; on D3D12 present secondary windows with a sync interval of 0), so the frame waits for at most one blank.
- Skip minimised and fully hidden windows entirely: no acquire, no rendering, no present.

## Viewports as render targets

Inside a window, a scene view or game view is a **viewport**: a rectangle of the editor UI that shows a rendered image. Render each one to its own texture, and draw that texture in the UI:

```text
Viewport { camera, size, color_target, depth_target }

editor frame:
    for viewport in visible viewports:
        size = size of its UI panel (in pixels, after DPI scaling)
        if size changed: resize its targets
        render the scene from viewport.camera into viewport.color_target
    render the editor UI, drawing each viewport's color_target as an image
```

```cpp
// With Dear ImGui: the panel's free space decides the viewport's size.
ImGui::Begin("Scene");
ImVec2 size = ImGui::GetContentRegionAvail();
scene_view.request_size((uint32_t)size.x, (uint32_t)size.y);
ImGui::Image((ImTextureID)scene_view.color_target_id(), size);
bool hovered = ImGui::IsItemHovered();          // only send camera input when the mouse is over it
ImGui::End();
```

- The viewport's size is known only while building the UI, and the image is drawn in the same frame. Use the size from **last frame** to render, and request the new size for next frame; the one-frame lag during a resize is not noticeable.
- Map input through the viewport's rectangle: a click in the scene view becomes a ray from that viewport's camera, using coordinates relative to the image, not the window.
- **Hidden** viewports (a scene view in a tab that is not selected) are not rendered at all.
- Viewports can render at a lower **resolution scale** than their panel, and be upscaled when drawn, which keeps a large editor responsive.

[Dear ImGui's](../ui/dear-imgui.md) docking branch can also pull panels out into their own OS windows (multi-viewports). Each pulled-out panel becomes a platform window with its own swapchain, created and destroyed by the platform and renderer backends; the engine renders each like any other window.

## Resizing

Window resizes produce a stream of size changes while the user drags the edge.

- **Recreate the swapchain** when the OS says the size changed, or when acquire or present report it as out of date (`VK_ERROR_OUT_OF_DATE_KHR`, `VK_SUBOPTIMAL_KHR`). Wait for the GPU to finish with the old swapchain's images before destroying them.
- **Recreate size-dependent targets** (G-buffer, post-processing chain) through the render graph: transient targets get the new size automatically the next frame, which is one more reason to keep them transient.
- **Do not recreate per pixel of a drag.** Recreate at most once per frame, with the latest size; some engines wait until the size has been stable for a few frames, and stretch the old image meanwhile.
- A **minimised** window has a size of 0 × 0, which is not a valid swapchain size. Stop rendering to it until it is restored.
- **DPI changes** (a window dragged to a monitor with different scaling) change the pixel size without the logical size changing. Treat them like a resize, and rescale the UI; see [scaling and DPI](../ui/architecture.md#scaling-and-dpi).

## Split screen

Split screen is several viewports in one window: one view per player, each with its own camera, rendered into its own rectangle of the same target, or into separate targets composited at the end.

- Each player's view is a separate [view](renderer.md#views) with its own culling. Shared work (shadow maps of a directional light) can be done once if every view can see the same region, but usually each view needs its own cascades.
- Cost scales with the number of views, not their size: four quarter-size views cost far more than one full-size view, because culling, shadows, and per-draw CPU work are paid four times. Lower the per-view detail (LOD bias, shadow distance) as players are added.
