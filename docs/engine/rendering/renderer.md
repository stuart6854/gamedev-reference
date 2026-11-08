# Renderer layer

The layer between the scene and the [render graph](render-graph.md). It decides what is drawn, by which pass, in which order, with which pipeline and data, and turns that into compact lists the render graph's passes execute.

## Extract, then render

The renderer never reads gameplay objects directly while drawing. At the end of the simulation frame, an **extract** step copies what rendering needs into render-side structures, the [frame packet](../patterns/frame.md#double-buffered-state):

```text
RenderObject {
    mesh            // handle
    material        // handle
    world_matrix
    prev_world      // for motion vectors
    bounds          // world-space sphere or box
    layer_mask      // which views and passes see it
    flags           // casts shadows, is static, ...
}

extract(scene) -> FramePacket:
    for each visible-capable entity with Transform and MeshRenderer:
        append RenderObject { ... }
    lights, cameras, decals, particles likewise
```

After extract, simulation can move on to the next frame while the renderer works from the copy. Static objects can be extracted once and updated only when they change.

## Views

A **view** is one thing to render the scene from: the main camera, each shadow cascade, each face of a reflection probe, a portal, a split-screen player.

```text
View {
    view_matrix, projection_matrix
    frustum
    pass_mask       // which passes this view needs: shadows only, or the full set
    render_target   // or a size, for the render graph to create
    lod_bias
}
```

The same scene gets rendered several times per frame from different views. Each step below runs per view, and views are independent, so they run as parallel [jobs](../jobs/index.md).

## Visibility

```text
for view in views:
    for object in packet.objects:
        if object.layer_mask & view.layer_mask == 0: continue
        if not view.frustum.intersects(object.bounds): continue       // see frustum tests
        visible[view].append(object)
```

- [Frustum culling](../../maths/frustum.md) removes everything outside the view; for many objects, do it with a [bounding volume hierarchy or grid](../../data-structures/spatial-hash.md) instead of testing every object.
- **Occlusion culling** removes what is hidden behind other objects: precomputed visibility for static levels, a software-rasterised depth buffer of large occluders, or GPU culling against last frame's depth pyramid (Hi-Z).
- **LOD selection** happens here too: choose each object's mesh level from its screen size.
- **Shadow views** cull with the light's frustum, and can skip objects whose shadows cannot fall inside the main view.

## Render queues and sort keys

Each pass gets a **queue** of draw items. Rather than sorting full structs, each item is a 64-bit **sort key** and an index:

```text
DrawItem { key: u64, object_index: u32 }

opaque key:      [ pass 4 | layer 4 | pipeline 16 | material 16 | depth 24 ]   // front to back within a material
transparent key: [ pass 4 | layer 4 | depth 32 inverted | pipeline 12 | ... ]  // back to front
```

- Sorting opaque draws by **pipeline, then material** minimises state changes, which are the main CPU cost per draw. Depth within a material (front to back) reduces overdraw.
- **Transparent** draws must be sorted back to front for correct blending, so depth goes in the highest bits, and state changes are accepted.
- Sorting 64-bit integers is fast (radix sort), and the key layout is a single place to tune draw order. The [packing fields](../../data-structures/bits.md#packing-fields) page covers building the key.

Then walk the sorted queue, only setting state when it changes:

```text
for item in sorted queue:
    if item.pipeline != current_pipeline: set pipeline
    if item.material != current_material: bind material
    write per-draw data (transform index, material index) to the upload ring
    draw
```

### Instancing and batching

Consecutive items with the same mesh and material become one **instanced** draw: write each instance's transform into a buffer, and draw once with an instance count. With [bindless](rhi.md#bindless) materials, items with the same pipeline and mesh but different materials can be batched too, because the material is just an index in the per-instance data.

The end point of this is **GPU-driven rendering**: culling and draw-list building run in compute shaders, and the CPU issues a handful of indirect draws (`DrawIndexedIndirect`, `ExecuteIndirect`) per pass.

## Materials

A material is a shader (or a shader template) plus parameters:

```text
MaterialTemplate { shader source, parameter layout, render states, which passes it supports }
Material         { template, parameter values, textures }
```

- Each material supports a set of **passes**: an opaque material has depth-only, shadow, and G-buffer versions; a transparent one a forward version. Adding an object to a view's queues means adding one item per pass its material supports.
- **Shader variants** come from features (skinned or not, alpha-tested or not, normal mapped or not). Each combination is a separate compiled shader. Keep the number of feature switches small: they multiply. Prefer dynamic branches on uniform values for features that cost little.
- Pack parameter values into a constant buffer layout (or a slot in a big material buffer for bindless) once, when the material is created or edited, not per draw.

## Pipeline caching

```text
pipeline_key = hash(shader variant, vertex layout, blend, depth, raster state, render target formats)

get_pipeline(key):
    if cache has key: return it
    request compilation on a background job; return the fallback pipeline for now
```

- Never block a frame on compiling a pipeline. Draw with a fallback (or skip the draw) until it is ready, and precompile the expected set at load time (see [pipelines](rhi.md#pipelines)).
- Keep render-target formats in the key: the same material drawn into an HDR target and an LDR target needs two pipelines.
