---
uses:
  - name: Multiplayer
    text: Several message types in one packet, read with one switch and validated before use.
  - name: Hordes and crowds
    text: Spawns and despawns recorded during jobs and applied in one place.
  - name: Base building
    text: Undo and redo for placing, moving, and removing pieces.
---

# Unions and command buffers

A **command list** holds several kinds of command in one sequence, in order: draw calls for the renderer, entity changes to apply after a system runs, editor actions to undo, messages to send. A list of objects behind an interface does this with an allocation and a virtual call per command. This page stores them as plain data instead, in two ways:

- A **tagged union**: one struct type the size of the largest command, with a tag that says which one it holds. Simple, and it fits in a `List<T>` or array.
- A **byte command buffer**: each command written as a small header plus exactly its own payload. Compact when commands differ a lot in size, or carry variable-length data.

Both are unmanaged data, so they also work in native memory, jobs, and Burst. [Pointers and native memory](memory.md#reinterpreting-data) covers the `MemoryMarshal` and layout APIs used here.

## Tagged unions

`[StructLayout(LayoutKind.Explicit)]` puts fields at byte offsets you choose. Giving several payloads the same offset makes them share memory:

```csharp
using System.Diagnostics;
using System.Runtime.InteropServices;

public enum RenderOp : byte { SetPipeline, SetViewport, Draw }

public struct SetPipelineData { public int Pipeline; }
public struct ViewportData { public float X, Y, Width, Height; }
public struct DrawData { public int Mesh, Material, FirstInstance, InstanceCount; }

[StructLayout(LayoutKind.Explicit)]
public struct RenderCommand                       // 4 + 16 = 20 bytes
{
    [FieldOffset(0)] public RenderOp Op;
    [FieldOffset(4)] SetPipelineData _pipeline;   // the payloads overlap
    [FieldOffset(4)] ViewportData _viewport;
    [FieldOffset(4)] DrawData _draw;

    public static RenderCommand SetPipeline(int pipeline) =>
        new() { Op = RenderOp.SetPipeline, _pipeline = new() { Pipeline = pipeline } };

    public static RenderCommand Draw(int mesh, int material, int first, int count) =>
        new() { Op = RenderOp.Draw, _draw = new() { Mesh = mesh, Material = material, FirstInstance = first, InstanceCount = count } };

    public readonly DrawData AsDraw
    {
        get { Debug.Assert(Op == RenderOp.Draw); return _draw; }
    }
    // ...one factory and one accessor per payload
}
```

Reading is one `switch` over the tag:

```csharp
foreach (ref readonly RenderCommand cmd in CollectionsMarshal.AsSpan(commands))
{
    switch (cmd.Op)
    {
        case RenderOp.SetPipeline: device.Bind(cmd.AsPipeline.Pipeline); break;
        case RenderOp.SetViewport: device.SetViewport(cmd.AsViewport); break;
        case RenderOp.Draw:        device.Draw(cmd.AsDraw); break;
    }
}
```

- **Keep the payload fields private**, and set them only through factories that also set the tag. Reading the wrong payload gives garbage, not an exception. The accessors' asserts catch it in debug builds.
- **No references**. A field holding an object reference cannot overlap any other field: the runtime refuses to load the type. Store handles or indices (a mesh id, an index into a side list of strings) instead.
- **Offsets respect alignment.** Put payloads at a multiple of their largest field's size (4 for `int` and `float`, 8 for `long`, `double`, and pointers), after the tag.
- **Every command costs the largest size.** One 64-byte matrix payload makes every 4-byte `SetPipeline` cost 68 bytes. When that matters, use a byte buffer instead.
- Because each command is the same size, a list of them can be **sorted**. Render commands are often sorted by a [sort key](../../engine/rendering/renderer.md#render-queues-and-sort-keys) stored next to the union.

Without `unsafe` code or explicit layout, a **"fat" struct** with every payload's fields side by side does the same job at a larger size, and is safe to read in any state. For two or three small payloads it is often the simpler choice.

## Byte command buffers

Each command is a fixed header followed by its payload, padded so the next header is aligned:

```text
| Type | Size | payload ........ | pad | Type | Size | payload .. | pad | ...
  2 B    2 B    Size − 4 bytes          ← Size covers header, payload, and padding
```

```csharp
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

public struct CommandHeader { public ushort Type; public ushort Size; }

public sealed class CommandBuffer
{
    const int HeaderSize = 4, Alignment = 8;
    byte[] _data = new byte[4096];
    int _length;

    public int Length => _length;

    public void Write<T>(ushort type, in T payload) where T : unmanaged
    {
        Span<byte> span = Reserve(type, Unsafe.SizeOf<T>());
        MemoryMarshal.Write(span, in payload);
    }

    // Header plus `payloadSize` bytes; returns the payload span to fill.
    public Span<byte> Reserve(ushort type, int payloadSize)
    {
        int size = (HeaderSize + payloadSize + Alignment - 1) & ~(Alignment - 1);
        if (size > ushort.MaxValue) throw new ArgumentException("Command too large");
        if (_length + size > _data.Length) Array.Resize(ref _data, Math.Max(_data.Length * 2, _length + size));

        Span<byte> span = _data.AsSpan(_length, size);
        span.Clear();                                              // padding is zero, never stale bytes
        MemoryMarshal.Write(span, new CommandHeader { Type = type, Size = (ushort)size });
        _length += size;
        return span.Slice(HeaderSize, payloadSize);
    }

    public Reader GetReader() => new(_data.AsSpan(0, _length));
    public void Clear() => _length = 0;

    public ref struct Reader
    {
        ReadOnlySpan<byte> _rest;
        public ushort Type { get; private set; }
        public ReadOnlySpan<byte> Payload { get; private set; }    // includes padding at the end

        public Reader(ReadOnlySpan<byte> data) { _rest = data; Type = 0; Payload = default; }

        public bool Next()
        {
            if (_rest.IsEmpty) return false;
            var header = MemoryMarshal.Read<CommandHeader>(_rest);
            Type = header.Type;
            Payload = _rest.Slice(HeaderSize, header.Size - HeaderSize);
            _rest = _rest[header.Size..];
            return true;
        }

        public T Read<T>() where T : unmanaged => MemoryMarshal.Read<T>(Payload);
    }
}
```

```csharp
var reader = buffer.GetReader();
while (reader.Next())
{
    switch ((RenderOp)reader.Type)
    {
        case RenderOp.Draw:        device.Draw(reader.Read<DrawData>()); break;
        case RenderOp.SetViewport: device.SetViewport(reader.Read<ViewportData>()); break;
        // ...
    }
}
```

- **Variable-length data** goes straight after the fixed part: reserve `sizeof(fixed part) + byte count`, write the fixed part (including the count), then copy the bytes after it. A string becomes a length and UTF-8 bytes; a list of vertices becomes a count and the raw structs.
- **Commands are only read forwards.** For random access or reading backwards, keep a separate list of each command's offset.
- **Clearing is free**: set the length to 0 and keep the array. A buffer per frame (or two, one being written while the other is read) allocates nothing once it has grown.
- `Reserve` returns a span into the array. Do not hold it across another `Write`: growing the array moves the data.

**Unity:** `NativeList<byte>` or `UnsafeList<byte>` instead of the `byte[]`, so jobs can write commands; use one buffer per thread (or `UnsafeStream`) and play them back in order afterwards. `UnsafeUtility.SizeOf<T>()` replaces `Unsafe.SizeOf<T>()`.

## Examples

### Render commands

Game code records what to draw; the renderer replays it, often on another thread, a frame later.

- Fixed-size commands (`Draw`, `SetPipeline`, `SetViewport`) suit a tagged union, with a sort key per command so the renderer can reorder by pipeline and material.
- Commands with constant data of different sizes (per-object matrices, push constants) suit a byte buffer, or a union holding an offset into a separate byte buffer of constants.
- **Double-buffer**: game code writes buffer `N` while the render thread reads buffer `N − 1`, and they swap at the frame boundary. See [extract, then render](../../engine/rendering/renderer.md#extract-then-render).

### Entity commands

Systems iterating over entities cannot create, destroy, or change components in the middle of the loop. They record the change, and it is applied once the loop is done, as on the [deferred commands](../../engine/ecs/entities.md#deferred-commands) page.

```csharp
public enum EntityOp : ushort { Create, Destroy, AddComponent, RemoveComponent }

public struct EntityTarget { public int Entity; }                       // Destroy
public struct ComponentChange { public int Entity; public int ComponentId; } // Remove, and Add's fixed part

// AddComponent: the fixed part, then the component's bytes.
public static void Add<T>(CommandBuffer buffer, int entity, in T component) where T : unmanaged
{
    int fixedSize = Unsafe.SizeOf<ComponentChange>();
    Span<byte> payload = buffer.Reserve((ushort)EntityOp.AddComponent, fixedSize + Unsafe.SizeOf<T>());
    MemoryMarshal.Write(payload, new ComponentChange { Entity = entity, ComponentId = ComponentType<T>.Id });
    MemoryMarshal.Write(payload[fixedSize..], in component);
}
```

- Playback reads `ComponentChange`, then hands the rest of the payload to the store for `ComponentId`, which copies the bytes into place without knowing `T`.
- `Create` cannot return a real entity yet. Return a **temporary id** (negative, counting down) and record it in the command; playback creates the entity and keeps a table from temporary to real ids, so later commands in the same buffer can refer to it.
- Several threads recording at once each get their own buffer. Play them back in a fixed order (by thread index or system order), so the result does not depend on scheduling.

### Undo and redo

An editor command has to be undoable, so its payload records the state **before and after**:

```csharp
public struct SetFloatProperty { public int Entity; public int PropertyId; public float Old, New; }
public struct MoveEntity { public int Entity; public Vector3 OldPosition, NewPosition; }
```

```text
apply(cmd, forward):
    switch cmd.type:
        SetFloatProperty: set(cmd.entity, cmd.property, forward ? cmd.new : cmd.old)
        MoveEntity:       set_position(cmd.entity, forward ? cmd.new_position : cmd.old_position)

undo: step back one command, apply(cmd, forward = false)
redo: apply(cmd at cursor, forward = true), step forward
new command after an undo: truncate everything after the cursor, then append
```

- Undo walks the buffer **backwards**, so keep a list of command offsets alongside it.
- Group commands from one user action (a multi-select move) under a **begin and end marker**, so undo removes them together.
- **Merge** repeated commands during a drag: if the new command is a `MoveEntity` for the same entity as the last one, update its `NewPosition` instead of appending.
- Refer to entities by stable ids, not references or array indices: undoing a delete recreates the entity, which must get the same id back.

### Network messages

The same header-plus-payload layout works for packets, with three differences:

- **Byte order and layout must be fixed.** Write each field with `BinaryPrimitives.WriteInt32LittleEndian` and the other `Write` methods, or use `[StructLayout(LayoutKind.Sequential, Pack = 1)]` and check `BitConverter.IsLittleEndian` at startup.
- **Input is untrusted.** Before reading a payload, check that the header fits, that `Size` is at least the header size and no more than the bytes left, that `Type` is known, and that the payload is at least as large as the struct about to be read. `MemoryMarshal.TryRead` returns `false` instead of throwing.
- **Version it.** Put a protocol version in the connection handshake, and add new message types rather than changing the layout of existing ones.

```csharp
public static bool TryNext(ref ReadOnlySpan<byte> rest, out CommandHeader header, out ReadOnlySpan<byte> payload)
{
    payload = default;
    if (!MemoryMarshal.TryRead(rest, out header)) return false;                  // not even a header
    if (header.Size < 4 || header.Size > rest.Length) return false;              // lies about its size
    payload = rest.Slice(4, header.Size - 4);
    rest = rest[header.Size..];
    return true;
}
```

Floats in network messages are often [quantised](../../data-structures/bits.md#floats-in-fewer-bits) to fewer bits, which a byte-aligned struct cannot do; pack those fields with a bit writer instead.

!!! warning "Common pitfalls"

    Reading a union through the wrong payload returns garbage without an error. Set the tag and payload together in a factory, and assert the tag when reading.

    Storing an object reference in an explicit-layout struct fails when the type loads. Store an id or an index instead.

    Holding the span returned by `Reserve` and then writing another command can leave it pointing at the old array after the buffer grows.

    Trusting `Size` from a network packet lets a bad packet read past the end of the buffer or loop forever on `Size = 0`. Validate every header.

    Sharing one command buffer between threads without a lock corrupts it. Give each thread its own buffer and merge them in a fixed order.
