# RHI design

The **render hardware interface** (RHI) is the engine's own thin layer over the graphics APIs. Everything above it (the [render graph](render-graph.md), the [renderer](renderer.md)) is written once against the RHI, and each backend (Vulkan, D3D12, Metal) implements it.

## How thin

| Approach | Looks like | Trade-off |
| --- | --- | --- |
| Thick (OpenGL / D3D11 style) | `set_texture(slot, tex)`, `draw()`; the RHI tracks state, barriers, and memory | Easy to use; hides costs; hard to make fast on explicit APIs |
| Thin (explicit) | Command lists, explicit barriers, pipelines, descriptor management | Maps directly to Vulkan, D3D12, and Metal; more work for the layer above |

Modern engines use a **thin** RHI and put the convenience in the render graph, which knows the whole frame and can place barriers and manage memory better than any per-call layer. This page describes a thin one.

## The objects

```text
Device              one per GPU; creates everything else
Queue               graphics, compute, copy; submits command lists
CommandList         records commands; one per thread per frame
Buffer, Texture     memory with a size and format; created with usage flags
View                how a shader sees a texture or buffer (format, mip range, array slice)
Sampler             filtering and addressing
Shader              compiled bytecode (SPIR-V, DXIL, Metal IR) for one stage
Pipeline            shaders + vertex layout + blend, depth, raster state + target formats
Fence               CPU/GPU synchronisation; see frames in flight
Swapchain           the images presented to a window; see viewports
```

```cpp
struct TextureDesc {
    uint32_t width, height, depth = 1, mips = 1, layers = 1;
    Format format;
    TextureUsage usage;          // ShaderRead | RenderTarget | DepthStencil | Storage | CopyDst
    const char* debug_name;
};

TextureHandle create_texture(const TextureDesc&);
void destroy_texture(TextureHandle);
```

- Return **handles**, not pointers (see the [handle table](../../data-structures/handle-table.md)). The backend keeps its own objects (`VkImage`, `ID3D12Resource*`) in a table; the layer above never sees them.
- Make **usage flags** explicit at creation. Every explicit API needs to know up front whether a texture will be a render target or sampled, to choose its memory layout and compression.
- Name everything. Debug names flow into RenderDoc, PIX, and validation messages, and save hours.

## Command lists

```cpp
CommandList& cmd = device.begin_command_list(QueueType::Graphics);
cmd.barrier(scene_color, ResourceState::RenderTarget);
cmd.begin_render_pass({ .color = { scene_color, LoadOp::Clear }, .depth = { depth, LoadOp::Clear } });
cmd.set_pipeline(opaque_pipeline);
cmd.set_vertex_buffer(0, mesh.vertices);
cmd.set_index_buffer(mesh.indices, IndexType::U16);
cmd.push_constants(&draw_data, sizeof(draw_data));
cmd.draw_indexed(mesh.index_count, 1, 0, 0, 0);
cmd.end_render_pass();
device.submit(QueueType::Graphics, { &cmd });
```

- **Record on many threads.** Command lists are recorded in parallel, each thread with its own command pool (Vulkan) or allocator (D3D12), and submitted together in a fixed order. Pools are per frame in flight, and reset only when the GPU has finished that frame.
- **Render passes** are explicit, with load and store operations. On mobile (tile-based) GPUs, `LoadOp::Clear` or `DontCare` and `StoreOp::DontCare` for depth save a great deal of bandwidth. Dynamic rendering (Vulkan 1.3) avoids creating render pass and framebuffer objects up front.
- **Barriers** are explicit: a texture written as a render target must be transitioned before it is sampled. Getting barriers right by hand across a whole frame is error-prone, which is why the [render graph](render-graph.md#barriers) inserts them.

## Pipelines

A pipeline bakes nearly all state into one object, so the driver compiles shaders for that exact combination once. Creating one can take milliseconds to hundreds of milliseconds.

```cpp
struct PipelineDesc {
    ShaderHandle vs, ps;
    VertexLayout vertex_layout;
    BlendState blend;  DepthState depth;  RasterState raster;
    Format color_formats[8]; Format depth_format;
    PrimitiveTopology topology;
};
```

- **Cache** pipelines by a hash of their description; see [pipeline caching](renderer.md#pipeline-caching).
- **Precompile** at load time, never during a draw. A pipeline created mid-frame is a visible hitch ("shader compilation stutter"). Record the pipelines each level used in play-testing and precompile that list.
- Save the driver's **pipeline cache** (`VkPipelineCache`, D3D12 pipeline libraries) to disk, so later runs compile faster.

## Binding resources

How shaders find their textures and buffers differs most between the APIs.

### Descriptor sets by frequency

The traditional model groups bindings by how often they change, so each group is bound once per that frequency:

```text
set 0: per frame      camera, time, lights, shadow maps
set 1: per pass       pass-specific inputs (G-buffer textures)
set 2: per material   material textures and parameters
set 3: per draw       usually push constants or a dynamic offset into one big buffer
```

Binding set 0 once per frame and set 2 once per material change keeps the per-draw work to almost nothing.

### Bindless

Modern hardware lets shaders index into one large table of all textures and buffers. The CPU binds that table once, and each draw passes indices:

```hlsl
Texture2D textures[] : register(t0, space1);          // every texture in the engine
SamplerState samplers[] : register(s0, space1);

struct Material { uint albedo, normal, sampler; float4 tint; };
StructuredBuffer<Material> materials : register(t0, space2);

float4 PSMain(PSIn input) : SV_Target
{
    Material m = materials[input.material_index];
    return textures[NonUniformResourceIndex(m.albedo)].Sample(samplers[m.sampler], input.uv) * m.tint;
}
```

- Every texture gets an index into the table when it is created; the index is its "descriptor". Materials store indices.
- Draws differ only in a few integers (material index, transform index), which makes [batching](renderer.md#render-queues-and-sort-keys) and GPU-driven rendering much easier.
- Use `NonUniformResourceIndex` (HLSL) or `nonuniformEXT` (GLSL) when the index can differ between pixels of the same draw.
- Requires Vulkan descriptor indexing (core in 1.2), D3D12 resource binding tier 3 (or SM 6.6 `ResourceDescriptorHeap`), or Metal argument buffers tier 2. Desktop GPUs from the last decade and current consoles have it; older mobile GPUs may not.

## Backends

- One backend per API, chosen at start-up. Keep the RHI interface free of API types.
- Use the **D3D12 and Vulkan models as the common denominator**: explicit barriers, pipelines, command lists. Metal maps onto them with small adjustments (its barriers are mostly automatic within a command encoder).
- Turn on the **validation layers** (Vulkan validation, the D3D12 debug layer, Metal API validation) in development builds, and treat their messages as bugs.
- Make GPU **markers** part of the RHI (`cmd.begin_marker("Shadows")`), so captures in RenderDoc, PIX, or Xcode show the frame's structure.
