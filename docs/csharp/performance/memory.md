---
uses:
  - name: Hordes and crowds
    text: Large blocks of simulation data in native memory, outside the garbage collector.
  - name: Multiplayer
    text: Packets read and written as structs over byte buffers, with a fixed byte order.
---

# Pointers and native memory

The parts of C# that work below the managed heap: raw pointers, pinning, memory the garbage collector does not own, reinterpreting bytes as other types, and calling native code. Use them in the few places where they pay off: large data blocks, binary formats, and engine or library boundaries.

[Structs, Span, and ref](structs-span.md) covers `Span<T>`, `stackalloc`, and `ref`, which are the safe tools to try first. Examples target .NET 8; Unity notes are at the end of each section.

## Unsafe code

Pointers need `unsafe` code, enabled per project:

```xml
<PropertyGroup>
  <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
</PropertyGroup>
```

```csharp
unsafe struct Particle { public float X, Y, Z; public int Flags; }

static unsafe void Clear(Particle* p, int count)
{
    for (int i = 0; i < count; i++)
    {
        p[i].Flags = 0;            // same as (p + i)->Flags
    }
}
```

- A pointer can only point at an **unmanaged** type: primitives, enums, pointers, and structs that contain only those, with no references. The `where T : unmanaged` constraint lets generic code take `T*`.
- Arithmetic on `T*` counts in elements of `T`; cast to `byte*` for byte offsets. `sizeof(T)` works on any unmanaged type inside `unsafe` code.
- There are no bounds checks. A wrong index silently overwrites whatever is next to it, which may be another object's fields or the GC's own data.
- Keep pointer code in small methods with a safe signature (taking spans or arrays), so the rest of the code never sees a pointer.

**Unity:** enable "Allow 'unsafe' code" in Player settings, or in the assembly definition.

## Pinning

The garbage collector moves objects when it compacts the heap. A pointer into a managed array or string is only valid while the object is **pinned**, so it cannot move.

| How | Lasts | Use for |
| --- | --- | --- |
| `fixed` statement | until the end of the block | short operations: a copy, a native call |
| `GCHandle.Alloc(obj, GCHandleType.Pinned)` | until `handle.Free()` | buffers native code holds across calls |
| `GC.AllocateArray<T>(n, pinned: true)` (.NET 5) | the array's lifetime | long-lived buffers that are always pinned |
| Native memory (next section) | until freed | memory the GC should never see |

```csharp
static unsafe float Sum(float[] values)
{
    fixed (float* p = values)          // p is null for a null or empty array
    {
        float sum = 0;
        for (int i = 0; i < values.Length; i++) sum += p[i];
        return sum;
    }                                  // unpinned here: p must not be used after this
}

// Spans pin the same way, including spans over stack or native memory.
fixed (byte* p = span) { ... }
```

- Pinned objects get in the way of heap compaction. Many long-lived pins in the normal heap cause fragmentation, so long-lived buffers belong in the **pinned object heap** (`pinned: true`) or in native memory.
- A `GCHandle` that is never freed is a leak and a permanent pin. Free it in `Dispose`.

**Unity:** `fixed` and `GCHandle` work the same way. `UnsafeUtility.PinGCArrayAndGetDataAddress(array, out ulong handle)` and `UnsafeUtility.ReleaseGCObject(handle)` are Unity's equivalent of a pinned handle.

## Native memory

Memory from the native allocator is never scanned, moved, or freed by the GC, so a large block costs it nothing. In exchange, you free it yourself.

```csharp
using System.Runtime.InteropServices;

unsafe
{
    var p = (Particle*)NativeMemory.Alloc((nuint)count, (nuint)sizeof(Particle));
    NativeMemory.Clear(p, (nuint)(count * sizeof(Particle)));    // Alloc does not zero; AllocZeroed does
    // ...
    NativeMemory.Free(p);

    void* aligned = NativeMemory.AlignedAlloc(byteCount: 4096, alignment: 64);
    NativeMemory.AlignedFree(aligned);                           // must match AlignedAlloc
}
```

`NativeMemory` is .NET 6 and later; `Marshal.AllocHGlobal` and `Marshal.FreeHGlobal` do the same on older runtimes.

### Owning it

Wrap each allocation in a type that frees it, and expose it as a span:

```csharp
public unsafe struct NativeBuffer<T> : IDisposable where T : unmanaged
{
    T* _ptr;
    public int Length { get; private set; }

    public NativeBuffer(int length)
    {
        _ptr = (T*)NativeMemory.AllocZeroed((nuint)length, (nuint)sizeof(T));
        Length = length;
    }

    public Span<T> AsSpan() => new Span<T>(_ptr, Length);
    public ref T this[int i] => ref AsSpan()[i];                 // bounds-checked through the span

    public void Dispose()
    {
        NativeMemory.Free(_ptr);
        _ptr = null;
        Length = 0;
    }
}

using var positions = new NativeBuffer<Vector3>(100_000);
positions[0] = Vector3.One;
```

- A **struct** owner has no finaliser, so a missed `Dispose` leaks. Track live allocations in debug builds (a counter, or a table of call stacks) and report them at shutdown.
- Copying the struct copies the pointer. Two copies disposing the same buffer is a double free. Pass it by `ref`, or make the owner a class.
- A **class** owner can have a finaliser as a safety net, or wrap the pointer in a `SafeHandle`. Call `GC.AddMemoryPressure(bytes)` for large blocks, so the GC knows the class holds more memory than it appears to.

### Arenas

Per-frame scratch data (sort keys, culling results, temporary lists) suits a **linear allocator**: one native block, a bump pointer, and a reset at the end of the frame, with no individual frees.

```csharp
public unsafe sealed class FrameArena : IDisposable
{
    readonly byte* _base;
    readonly nuint _capacity;
    nuint _used;

    public FrameArena(nuint capacity)
    {
        _base = (byte*)NativeMemory.AlignedAlloc(capacity, 64);
        _capacity = capacity;
    }

    public Span<T> Alloc<T>(int count) where T : unmanaged
    {
        nuint align = sizeof(T) >= 16 ? 16 : BitOperations.RoundUpToPowerOf2((nuint)sizeof(T));  // power of two, up to 16
        nuint start = (_used + align - 1) & ~(align - 1);
        nuint size = (nuint)count * (nuint)sizeof(T);
        if (start + size > _capacity) throw new OutOfMemoryException("Frame arena full");
        _used = start + size;
        return new Span<T>(_base + start, count);
    }

    public void Reset() => _used = 0;                             // everything from this frame is gone
    public void Dispose() => NativeMemory.AlignedFree(_base);
}
```

Spans from the arena must not outlive the `Reset`. Keeping them as `Span<T>` (which cannot be stored in a field of a class) makes that hard to get wrong.

**Unity:** use `NativeArray<T>` with an `Allocator`: `Temp` (freed at the end of the frame), `TempJob` (must be disposed within four frames), or `Persistent`. They are checked for leaks and for use after dispose in the editor, and work with jobs and Burst. `UnsafeUtility.Malloc(size, alignment, allocator)` and `UnsafeUtility.Free` are the raw versions. Unity has no `NativeMemory`.

## Reinterpreting data

Treating the same bytes as a different type, without copying: reading a file's header as a struct, writing vertices into a byte buffer, or getting a float's bits.

| Need | API |
| --- | --- |
| Span of one type as a span of another | `MemoryMarshal.Cast<TFrom, TTo>(span)` |
| Any unmanaged span as bytes | `MemoryMarshal.AsBytes(span)` |
| One struct from bytes, or into bytes | `MemoryMarshal.Read<T>(bytes)`, `MemoryMarshal.Write(bytes, in value)` |
| A span over one value, as bytes | `MemoryMarshal.AsBytes(new Span<T>(ref value))` |
| A value's bits as another type | `Unsafe.BitCast<TFrom, TTo>(value)` (.NET 8), `BitConverter.SingleToInt32Bits` |
| A reference as another type | `Unsafe.As<TFrom, TTo>(ref value)` |
| Integers in a fixed byte order | `BinaryPrimitives.ReadInt32LittleEndian(bytes)` and the `Write` equivalents |

```csharp
[StructLayout(LayoutKind.Sequential, Pack = 1)]
struct FileHeader { public uint Magic; public ushort Version; public uint EntryCount; }

ReadOnlySpan<byte> file = File.ReadAllBytes(path);
var header = MemoryMarshal.Read<FileHeader>(file);                          // copies 10 bytes
ReadOnlySpan<Entry> entries = MemoryMarshal.Cast<byte, Entry>(file[10..]); // no copy

Span<byte> packet = stackalloc byte[64];
BinaryPrimitives.WriteUInt16LittleEndian(packet, messageId);
MemoryMarshal.Write(packet[2..], in position);                             // a Vector3 struct
```

- `MemoryMarshal.Read` and `Write` handle unaligned data. `Cast` and pointer casts assume the result's alignment; x64 and ARM64 tolerate misaligned loads, but SIMD and some ARM instructions do not.
- Raw struct bytes use the machine's byte order and the struct's layout. For files and packets that must be read elsewhere, write each field with `BinaryPrimitives`, or check `BitConverter.IsLittleEndian` and keep the layout explicit.
- `Unsafe.As` performs no checks. Using it to treat an object as an unrelated class corrupts memory.

### Struct layout

| Attribute | Effect |
| --- | --- |
| `[StructLayout(LayoutKind.Sequential)]` | fields in declaration order; the default for structs |
| `Pack = 1` (or 2, 4) | no padding beyond that alignment, for file and network formats |
| `[StructLayout(LayoutKind.Explicit)]` with `[FieldOffset(n)]` | each field at a byte offset you choose; overlapping offsets make a union |
| `fixed float Data[16];` | an inline array of primitives in an `unsafe` struct |
| `[InlineArray(16)]` (C# 12, .NET 8) | an inline array of any type, usable as a span, without `unsafe` |

```csharp
[StructLayout(LayoutKind.Explicit)]
struct Value                                   // a tagged union: 8 bytes of payload
{
    [FieldOffset(0)] public ValueKind Kind;
    [FieldOffset(4)] public int Int;
    [FieldOffset(4)] public float Float;       // overlaps Int
}

[InlineArray(8)]
struct Neighbours { int _first; }              // 8 ints, inline

var n = new Neighbours();
n[3] = 42;
Span<int> all = n;
```

- `Unsafe.SizeOf<T>()` (and `sizeof(T)`) is the managed size. `Marshal.SizeOf<T>()` is the size **after marshalling** for native calls, which differs for `bool`, `char`, and anything non-blittable. Use the first for memory work.
- Overlapping a reference field with any other field is not allowed: the runtime refuses to load the type.

**Unity:** `MemoryMarshal` and `BinaryPrimitives` are available. `Unsafe.As` and `Unsafe.BitCast` are not (`System.Runtime.CompilerServices.Unsafe` is not part of Unity's API by default); use `UnsafeUtility.As<TFrom, TTo>(ref value)` and `math.asint` / `math.asfloat`. `[InlineArray]` needs C# 12, so use `fixed` buffers or Unity's `FixedList` types.

## Interop

Calling native code (a C library, or your own engine) from C#. The rules come down to keeping the boundary **blittable**: types with the same memory layout on both sides, so they pass as plain memory with no conversion.

- **Blittable:** `byte`, `short`, `int`, `long`, `float`, `double`, their unsigned versions, `nint`, pointers, and structs of only those.
- **Not blittable:** `bool` (4 bytes by default for native calls, 1 byte in C++), `char`, `string`, arrays, and classes. These are converted on every call, which costs time and can surprise you.

```csharp
public static unsafe partial class Native
{
    [LibraryImport("engine")]                                  // .NET 7: generated at compile time
    public static partial void SetPositions(Vector3* positions, int count);

    [LibraryImport("engine", StringMarshalling = StringMarshalling.Utf8)]
    public static partial int LoadLevel(string name);

    [LibraryImport("engine")]
    public static partial int LoadLevelUtf8(byte* name);             // null-terminated UTF-8

    [LibraryImport("engine")]
    [return: MarshalAs(UnmanagedType.U1)]                      // C++ bool is one byte
    public static partial bool IsLoaded(int levelId);
}

// Arrays and spans: pin and pass a pointer and a length.
fixed (Vector3* p = positions) Native.SetPositions(p, positions.Length);

// UTF-8 literals need no conversion, and end in a hidden null terminator:
fixed (byte* name = "level_01"u8) Native.LoadLevelUtf8(name);
```

- **`LibraryImport`** (.NET 7) generates the marshalling code at compile time, which works with trimming and native AOT. **`DllImport`** does it at run time. Prefer `LibraryImport`; with only blittable parameters, the two are the same.
- **Callbacks from native code**: mark a static method `[UnmanagedCallersOnly]` and pass `&Method` as a `delegate* unmanaged<...>` function pointer. It cannot be called from managed code, and an exception thrown out of it crashes the process, so catch everything inside. The [hosting](../assemblies/hosting.md#calling-across-the-boundary) page builds a full engine boundary from these.
- **Lifetime**: native code must not keep a pointer into managed memory after the call returns, unless that memory is pinned with a `GCHandle`, on the pinned heap, or native.
- **Library names**: `"engine"` finds `engine.dll`, `libengine.so`, and `libengine.dylib`. `NativeLibrary.SetDllImportResolver` overrides the search.

**Unity:** use `[DllImport]` (no `LibraryImport`), with `"__Internal"` as the library name for statically linked plugins on iOS and WebGL. Callbacks under IL2CPP must be static methods marked `[MonoPInvokeCallback(typeof(TDelegate))]`. Burst-compiled code calls function pointers through `BurstCompiler.CompileFunctionPointer`.

!!! warning "Common pitfalls"

    Using a pointer from `fixed` after the block ends works until the GC compacts the heap, then reads or writes the wrong object. Never store it.

    `NativeMemory.Alloc` does not zero memory. A struct read from it before being written holds garbage.

    Copying a struct that owns native memory and disposing both copies is a double free, which corrupts the native heap and often crashes much later.

    `bool` in a `DllImport` signature is 4 bytes by default. Against a C++ `bool`, it reads three bytes of whatever follows.

    Writing structs straight to a file ties the format to one byte order and one compiler layout. Use `Pack = 1` and `BinaryPrimitives`, and a version number.
