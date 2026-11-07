# References and load-in-place

Objects point at each other: a door at the key that opens it, an enemy at its patrol route, a material at its textures. Pointers mean nothing in a file, so references are saved as ids and turned back into pointers or handles on load. For cooked data, the file can instead be laid out so that it is usable straight from memory, with no parsing at all.

## Kinds of reference

| Points to | Save as | Resolved on load by |
| --- | --- | --- |
| An asset (texture, prefab, sound) | The asset's id: a GUID or path hash | The [resource system](../patterns/resources.md#ids-and-handles), which returns a handle |
| An object in the same file (a door's key) | A file-local id | Looking it up among the objects just loaded |
| An object in another file or level | A stable global id, plus which level or file it is in | A registry of loaded objects; missing until that level is loaded |
| A runtime-only object (the current target) | Nothing; rebuild it after loading | Game code |

Never save array indices or memory addresses. Indices change when objects are added or removed, and addresses change every run.

## File-local ids

Give each object in a scene or save file an id that is unique in that file and never changes once assigned:

```text
Scene file:
    object 17: Door   { key: ref 42, locked: true }
    object 42: Key    { name: "Rusty key" }
    object 63: Enemy  { patrol: ref 71, target: null }
```

Assign ids from a counter stored in the file (the next free id), not from the object's position. Deleting object 17 must not renumber 42, or every reference to it, and every version-control diff, changes.

## Loading in two passes

A reference can point to an object that comes later in the file, or to one that points back. Load in two passes:

```text
load_scene(file):
    // Pass 1: create every object; remember references as ids.
    by_id = {}
    pending = []
    for record in file.objects:
        obj = create(record.type)
        read fields into obj, recording each reference field as (obj, field, target_id) in pending
        by_id[record.id] = obj

    // Pass 2: resolve.
    for (obj, field, target_id) in pending:
        target = by_id.get(target_id)
        if target: set field to target's handle
        else: log "object {obj.id}: missing reference {target_id}"; leave field null
```

- Cycles are no problem: every object exists before any reference is set.
- A **missing target** is data corruption or a deleted object. Log it with both ids and carry on with a null reference, so one broken link does not stop the level loading.
- Set references to **handles** (entity ids, [resource handles](../patterns/resources.md)), not raw pointers, so a later deletion is detected instead of crashing.

### Spawning a prefab or loading a save into an existing world

When the same file is loaded several times (ten copies of a prefab), its local ids repeat. Remap them: each load builds its own `by_id` table, so references inside each copy point within that copy.

A save game contains objects that already exist in the level (doors, chests) and objects created during play (dropped items). Give level objects **stable ids** baked into the level, and dynamic ones ids assigned at run time. Loading a save then matches level objects by their stable ids, applies their saved state, and creates the dynamic ones. The [world state](../../unity/systems/saving/world-state.md) page does this in Unity.

## Load-in-place

Parsing has a cost: reading each field, allocating each array, converting each value. For cooked data that is rebuilt for every platform, there is a faster option. Write the data in exactly the in-memory layout the game uses, load the file into one block of memory, and use it directly.

```text
file in memory:
    [header][ Mesh struct ][ vertex array ][ index array ][ name chars ]
               |               ^               ^              ^
               +-- offsets ----+---------------+--------------+
```

Pointers inside the block are stored as **offsets** from the start of the block, or from the pointer itself. Two ways to use them:

### Fix-ups

After loading, convert each offset to a real pointer by adding the block's address. The file stores a list of where the pointers are, so the loader does not need to understand the types:

```cpp
struct BlobHeader {
    uint32_t magic, version;
    uint32_t fixup_count;
    uint32_t fixup_offsets_offset;      // where the list of pointer locations starts
};

void apply_fixups(std::byte* blob)
{
    auto* header = reinterpret_cast<BlobHeader*>(blob);
    auto* fixups = reinterpret_cast<uint32_t*>(blob + header->fixup_offsets_offset);
    for (uint32_t i = 0; i < header->fixup_count; i++) {
        auto* slot = reinterpret_cast<uint64_t*>(blob + fixups[i]);      // a pointer-sized slot
        *slot = reinterpret_cast<uint64_t>(blob + *slot);                // offset -> address
    }
}
```

After fix-ups, the data is ordinary structs with ordinary pointers. Loading costs one read and one pass over the fix-up list.

### Relative pointers

Store each pointer as an offset from its own address, and add it when the pointer is followed:

```cpp
template <class T>
struct RelPtr {
    int32_t offset;                     // from &offset to the target; 0 means null
    T* get() const
    {
        return offset ? reinterpret_cast<T*>(reinterpret_cast<intptr_t>(this) + offset) : nullptr;
    }
};

template <class T>
struct RelArray {
    RelPtr<T> data;
    uint32_t count;
};

struct CookedMesh {
    RelArray<Vertex> vertices;
    RelArray<uint16_t> indices;
    RelPtr<char> name;
};
```

There is no fix-up pass at all, so the file can be **memory-mapped** and used without being read in first, and pages the game never touches are never loaded. The block can also be moved or copied without breaking anything. FlatBuffers works this way, with a portable layout and generated accessors.

### Requirements

Load-in-place reads structs straight from bytes, so the bytes must match the compiled layout exactly:

- **Cook per platform**: the same sizes, alignment, padding, and byte order as the platform that reads them.
- **Plain data only**: no virtual functions (the vtable pointer would be meaningless), no `std::vector` or `std::string` (they own heap memory), no constructors that must run.
- **Align** each array and struct in the file to its type's alignment, and align the block itself when loading it.
- **Check the layout version.** Put a hash of the reflected layouts of every type in the blob into its header, and reject a blob built for a different layout. Rebuilding is the only fix, and the [content pipeline](../content/incremental.md) does it automatically when the hash changes.
- **Trust the data.** A blob is used without validation, so it must come from your own pipeline, never from players or the network. Use a parsed format for anything that can be tampered with.
