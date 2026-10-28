# Free list and slab pool

A fixed-size block allocator. Memory is carved into equal blocks, and the free blocks are chained into a list through their own unused bytes. Allocating pops the head of the list, freeing pushes onto it, and both are \(O(1)\) with no per-block header and no fragmentation. A pool that grows by adding chunks of blocks is a slab pool.

Use it for many objects of one size that come and go: particles, projectiles, scene graph nodes, network messages, and the slots of a [handle table](handle-table.md).

This is pooling at the memory level. Reusing whole Unity objects to skip `Instantiate` is [object pooling](../unity/architecture/pooling.md), which keeps live objects rather than raw memory.

## Intrusive free list

A free block holds nothing, so it can hold the link to the next free block. The list costs no memory of its own.

```text
BLOCK = max(size of T, size of a pointer), rounded up to alignment of T

memory[capacity * BLOCK]
free_head                               // first free block, or null

init():
    for i in 0 .. capacity - 1:
        block(i).next = block(i + 1)
    block(capacity - 1).next = null
    free_head = block(0)

allocate():
    if free_head == null: return null   // or grow, below
    b = free_head
    free_head = b.next
    return b                            // construct a T in it

free(b):
    // destroy the T in b first
    b.next = free_head
    free_head = b
```

The block must be at least a pointer wide, so a pool of 2-byte items still spends 8 bytes on each on a 64-bit machine. Below that size, use indices instead.

## Lazy init

`init` above touches every block when the pool is created. For a large pool, that is a long first frame and memory the OS has to back immediately. Hand out never-used blocks by bumping an index instead, and use the free list only for returned ones:

```text
next_unused = 0

allocate():
    if free_head != null:
        b = free_head
        free_head = b.next
        return b
    if next_unused < capacity:
        b = block(next_unused)
        next_unused += 1
        return b
    return null
```

Creation is now \(O(1)\), and memory is touched in order as it is first used.

## Indices instead of pointers

Store the next free block as an index into the array, with a sentinel such as `-1` for the end:

- An index is 4 bytes, or 2 for a pool of at most 65,535 blocks, so small blocks waste less.
- It survives the array being moved or reallocated, which a pointer does not.
- It can be saved to disk or sent, because it does not depend on an address.

This is the free list inside the handle table. In a language without raw memory, such as C#, it is the only form: an array of structs with a `next` field used while the slot is free.

## Slab pool

A fixed pool fails when it runs out. A slab pool allocates another chunk of blocks, a slab, and threads its blocks onto the same free list:

```text
SLAB_BLOCKS = 256
slabs = []                              // each slab is SLAB_BLOCKS blocks

allocate():
    if free_head == null:
        s = new slab
        slabs.push(s)
        chain every block of s onto free_head
    b = free_head
    free_head = b.next
    return b
```

Slabs never move once allocated, so a pointer to a block stays valid until that block is freed. That is the advantage over one growing array, which moves every block when it reallocates.

Giving a slab back to the OS is harder. Its free blocks are spread through the shared list. To release slabs, keep a live count per slab and a free list per slab, allocate from the fullest partly used slab, and release a slab when its count reaches zero. That is the slab allocator design in operating system kernels. Most games keep the slabs until the level unloads and free them all at once.

## Size classes

A pool per size, such as 16, 32, 64, 128, and 256 bytes, with each request rounded up to the next class, is a small general-purpose allocator. It wastes up to half of each block, in exchange for \(O(1)\) allocation and no fragmentation. Requests above the largest class go to the normal allocator.

## Debugging

A free list hides two bugs well. The block freed last is the next one handed out, so a use after free usually reads a perfectly valid new object.

- **Poison on free.** In debug builds, fill a freed block with a pattern such as `0xDD`, after the `next` link. A use after free then reads garbage that is easy to spot in a debugger.
- **Catch double free.** A block freed twice appears on the list twice, and two later allocations get the same memory. Keep one bit per block, set while allocated, and assert it is set in `free`.
- **Check ownership.** Assert that a freed pointer lies inside one of the pool's slabs, and sits on a block boundary.

## Threads

The pool is not thread-safe. Two threads popping at once can both take the same head. Give each thread its own pool, or a lock.

A lock-free free list with a compare-and-swap on `free_head` looks simple and is not. Between one thread reading `head` and `head.next`, another thread can pop `head`, pop more, and push `head` back, so the compare succeeds against a stale `next`. That is the ABA problem, and the fix is a counter swapped together with the pointer. Use a tested library for it.

## Language tips

=== "C++"

    - Back the pool with `alignas(T) std::byte storage[...]` or a `std::unique_ptr<std::byte[]>` per slab. Build objects with `std::construct_at` (or placement `new`) and destroy them with `std::destroy_at`.
    - Read and write the `next` link with `std::memcpy` into the block's bytes, or make the block a `union { T value; Block* next; }`. Casting the bytes to `Block*` and back is the usual code and is technically outside the object rules.
    - The standard library has a size-class pool already: `std::pmr::unsynchronized_pool_resource`, with `synchronized_pool_resource` for threads. Measure it before writing your own.
    - A pool does not run destructors when it is destroyed. Destroy every live object first, or make the pool own and track them.

=== "C#"

    - There is no raw memory in managed code, so use the index form: a `T[]` of items and an `int[]` of `next` links, or one struct array with both. The garbage collector then sees every item.
    - On free, set the slot to `default` when `T` contains references, so what it pointed at can be collected.
    - `ArrayPool<T>.Shared` is a built-in size-class pool for temporary arrays. Rent, use, and return in the same scope.
    - In Unity, `UnityEngine.Pool.ObjectPool<T>` pools objects, not memory. For unmanaged memory, `UnsafeUtility.Malloc` with `Allocator.Persistent` gives a block to carve, and the pseudocode above applies with pointers inside `unsafe` code.

!!! warning "Common pitfalls"

    A block smaller than a pointer cannot hold the link. Round the block size up, or switch to 16-bit or 32-bit indices.

    Writing the `next` link into a block before destroying the object in it corrupts the object's last fields, which its destructor may still read. Destroy first, then link.

    Freeing the same block twice puts it on the list twice. Two later allocations then share memory, and the crash shows up far from the bug.

    A pointer into a single growing array is invalid after it grows. Use slabs, or indices.

    LIFO reuse makes use-after-free look fine in testing. Poison freed blocks in debug builds.
