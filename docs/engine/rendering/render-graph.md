# Render graph

A frame is dozens of passes: shadows, depth prepass, G-buffer, lighting, transparency, post-processing, UI. Each reads some textures and writes others. A **render graph** (or frame graph) has each pass declare what it reads and writes, then works out the rest: the order, the barriers between passes, which textures can share memory, and which passes are not needed at all.

The design was popularised by Frostbite's "FrameGraph: Extensible Rendering Architecture in Frostbite" (Yuriy O'Donnell, GDC 2017).

## Declaring passes

Building the graph runs every frame, and has two phases per pass: **setup** declares resources, **execute** records commands.

```cpp
struct GBuffer { RGTexture albedo, normal, depth; };

GBuffer add_gbuffer_pass(RenderGraph& rg, const View& view)
{
    GBuffer out;
    rg.add_pass("GBuffer",
        [&](RGBuilder& b) {                                   // setup
            out.albedo = b.create_texture({ view.width, view.height, Format::RGBA8_SRGB }, "Albedo");
            out.normal = b.create_texture({ view.width, view.height, Format::RGB10A2 }, "Normal");
            out.depth  = b.create_texture({ view.width, view.height, Format::D32 }, "Depth");
            b.write_render_target(out.albedo, LoadOp::Clear);
            b.write_render_target(out.normal, LoadOp::Clear);
            b.write_depth(out.depth, LoadOp::Clear);
        },
        [&](CommandList& cmd, const RGResources& r) {         // execute
            draw_queue(cmd, view.opaque_queue);
        });
    return out;
}

RGTexture add_lighting_pass(RenderGraph& rg, const View& view, const GBuffer& gb, RGTexture shadows)
{
    RGTexture lit;
    rg.add_pass("Lighting",
        [&](RGBuilder& b) {
            b.read_texture(gb.albedo);
            b.read_texture(gb.normal);
            b.read_texture(gb.depth);
            b.read_texture(shadows);
            lit = b.create_texture({ view.width, view.height, Format::RGBA16F }, "SceneColor");
            b.write_render_target(lit, LoadOp::DontCare);
        },
        [&](CommandList& cmd, const RGResources& r) {
            bind(r.get(gb.albedo), r.get(gb.normal), r.get(gb.depth), r.get(shadows));
            draw_fullscreen(cmd, lighting_pipeline);
        });
    return lit;
}

// The frame
RGTexture shadows = add_shadow_pass(rg, view);
GBuffer gb        = add_gbuffer_pass(rg, view);
RGTexture lit     = add_lighting_pass(rg, view, gb, shadows);
RGTexture final   = add_post_passes(rg, view, lit);
rg.present(final, swapchain_image);
rg.compile();
rg.execute();
```

- `RGTexture` is a **virtual** resource: a handle into the graph, not a real texture. The graph creates the real ones during `compile`.
- Passes communicate only through these handles. The lighting pass does not know who wrote the G-buffer; it only names what it reads.
- **External** resources (the swapchain image, a persistent shadow atlas, last frame's history for TAA) are imported into the graph with `rg.import(texture, current_state)`, and the graph tracks their state like any other.

## Compiling

```text
compile():
    1. Cull: starting from the outputs (present, exported resources), walk backwards through
       the passes that produce what is read. Passes nothing reaches are removed.
    2. Order: passes run in declaration order (a valid order already); optionally reorder
       independent passes to overlap work.
    3. Lifetimes: for each transient resource, find its first and last use.
    4. Allocate: assign memory to transient resources, sharing memory between resources
       whose lifetimes do not overlap.
    5. Barriers: for each pass, compute the state each resource must be in, and the
       transitions from its previous state.
```

### Culling

A debug view that is turned off, a bloom pass when bloom is disabled, or a depth prepass whose output nobody reads: each is simply not executed, without `if` statements around the pass code. Features become "add the pass when enabled", and the graph removes anything left without a consumer.

### Barriers

Each declaration implies a state: `read_texture` means shader-readable, `write_render_target` means render target, `write_storage` means unordered access. The graph knows each resource's state after every pass, so it inserts exactly the transitions needed before each pass, and nothing else:

```text
for pass in passes:
    for (resource, required_state) in pass.accesses:
        if current_state[resource] != required_state or both are writes:
            add barrier(resource, current_state[resource] -> required_state) before pass
            current_state[resource] = required_state
```

Two passes that write the same storage buffer one after the other need a barrier even though the state does not change (a write-after-write hazard), which the "both are writes" check covers. Batch all of a pass's barriers into one API call: one call with eight barriers is much cheaper than eight calls.

### Memory aliasing

Transient textures live for part of a frame. The G-buffer is dead once lighting has read it; bloom's chain of downsampled textures only lives during post-processing. With lifetimes known, they can share memory:

```text
sort transient resources by first use
for r in resources:
    find a block in the heap whose previous occupant's last use < r.first_use
    and that is large enough; place r there (or allocate a new block)
```

The saving is large: full-resolution render targets at 4K are tens of megabytes each, and a frame might use twenty of them without ever needing more than a handful at once. When memory is reused by a different resource, the new resource's first use must discard (or clear) the old contents, and an aliasing barrier is needed on D3D12.

## Async compute

Passes can be marked for the compute queue, so that work such as light culling, SSAO, or particle simulation runs alongside graphics work that uses different units of the GPU (shadow map rendering is mostly rasteriser and depth bandwidth, leaving shader units idle).

The graph adds a cross-queue signal and wait wherever a pass on one queue reads what a pass on the other queue wrote. Overlap only helps when the two workloads use different parts of the GPU; measure it per platform.

## Debugging

The graph is data, so it can be shown: a list of passes in execution order, each with its inputs, outputs, and barriers, and a timeline of transient resource lifetimes and memory placement. Dump it on request, and draw it in an [ImGui](../ui/dear-imgui.md) window. Each pass's name also becomes a GPU marker, so RenderDoc and PIX captures show the same structure.
