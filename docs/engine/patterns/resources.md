# Resources and handles

Meshes, textures, sounds, and scripts are loaded from disk, shared by many users, and freed when nobody needs them. A resource system gives out **handles** instead of pointers, loads in the background, counts references, and can replace an asset while the game runs.

## Ids and handles

Two kinds of reference:

| | Asset id | Runtime handle |
| --- | --- | --- |
| What it is | A stable name for the asset: a GUID, or a hash of its path | An index and a generation into the resource table |
| Stored in | Scene files, prefabs, save data | Components and runtime structures |
| Lifetime | Forever | This run of the game |
| Lookup | Hash table | Array index |

Content refers to assets by id. When a scene loads, each id is resolved to a handle once, and the game uses handles from then on. A GUID survives renaming and moving the file. A path hash does not, but is readable in a debugger and needs no metadata file.

Handles are the [handle table](../../data-structures/handle-table.md)'s index and generation, typed by resource kind so a texture handle cannot be passed where a mesh is expected:

```text
Handle<T> { index: u24, generation: u8 }

ResourceTable<T> {
    slots[]          // { generation, state, refcount, id, data: T, dependencies[] }
    by_id            // asset id -> index
}
```

A stale handle (to a resource that was unloaded and whose slot was reused) fails its generation check, and returns the [fallback](#placeholders-and-failures) instead of the wrong asset.

## Load states

```text
State = Unloaded | Queued | Loading | Loaded | Failed

load(id) -> Handle:
    if id in by_id: slot = by_id[id]; slot.refcount += 1; return handle
    slot = allocate a slot
    slot.state = Queued; slot.refcount = 1; slot.id = id
    push id onto the load queue
    return handle                        // usable straight away
```

`load` never blocks. It returns a handle to a slot that is not loaded yet. Code that needs the data checks the state, or uses the fallback while it is not `Loaded`. A scene can be "loading" for many frames while every resource it uses already has a handle.

### Dependencies

A material needs its shader and textures; a prefab needs its meshes and materials. Record them on the slot:

```text
on loaded(slot):
    for dep_id in slot.data.dependency_ids:
        slot.dependencies.append(load(dep_id))
    slot.state = Loaded when every dependency is Loaded or Failed
```

A resource is only `Loaded` when its dependencies are, so code never sees a material whose textures are missing. Releasing a resource releases its dependencies.

## Reference counting

```text
acquire(h)  = slot(h).refcount += 1
release(h):
    slot(h).refcount -= 1
    if slot(h).refcount == 0: push h onto the release queue
```

- **Unload later, not immediately.** A level that releases its assets and the next level that loads the same ones should not free and reload them. Process the release queue at the end of the frame, and skip any resource whose count went back above zero.
- **GPU resources need more time.** The GPU may still be drawing with a texture for two or three frames after the last CPU reference goes. Tag released GPU resources with the current frame number and free them once the GPU has finished that frame (a fence).
- **Unreferenced is not unloaded.** Keep recently released resources in a cache, ordered by last use, and only free them when memory is needed. Going back to a menu, or respawning, then costs nothing.
- In C++, a handle wrapper that acquires on copy and releases on destruction keeps counts right. In C#, use explicit `Dispose`: finalisers run late, on another thread, in an unknown order.

## Asynchronous loading

Loading has stages with different costs and threads:

```text
1. read      I/O thread       read the bytes from disk or a package file
2. decode    worker threads   decompress, parse, build CPU data
3. upload    render thread    create GPU buffers and textures
4. finish    main thread      resolve dependencies, set state = Loaded
```

- Read with a few large sequential reads, not many small ones. Package files that store a level's assets together, in load order, load several times faster than loose files.
- Limit the work per frame: upload at most a few megabytes, and finish at most a few resources, so loading in the background does not cause hitches.
- Give requests a **priority**. What is on screen now beats what will be needed after the next door.
- A request that is no longer wanted (the player turned back) should be cancellable while it is still queued.

## Placeholders and failures

While a texture loads, draw a small built-in texture (grey, or a checkerboard so it is noticeable). While a mesh loads, draw nothing or a bounding box. When a load fails, keep the slot in `Failed`, log the id and the reason once, and keep returning a fallback ("missing texture" magenta). A missing asset should be obvious, but should never crash the game.

## Hot reload

During development, an edited asset should appear in the running game without restarting:

```text
on file changed(id):
    slot = by_id[id]
    new_data = load synchronously or on a worker
    if load failed: log; keep the old data            // a half-saved file must not break the game
    else:
        old = slot.data
        slot.data = new_data
        slot.version += 1
        release old data (GPU data after the GPU's fence)
        notify dependents
```

- Reload **into the same slot**, so every existing handle sees the new data without being touched.
- Keep a **version** number per slot. Data built from a resource, such as a cached draw call that holds a material's constant buffer, stores the version it was built from and rebuilds when it differs.
- Dependents reload too: a shader change invalidates the materials that use it.
- File watchers fire several times per save, and while the file is still being written. Wait until the file has been unchanged for about 100 ms before reloading.
