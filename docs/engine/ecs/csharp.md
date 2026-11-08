# ECS in C\#

The [entities](entities.md), [sparse-set storage](sparse-set-storage.md), and [archetype storage](archetype-storage.md) pages describe an ECS in pseudocode. This page is the same design in C#: entity ids, component type ids, component masks, sparse-set pools with a world and queries, archetype columns, and a command buffer. The code compiles with C# 9 language features (the version Unity uses) on .NET 8, and its tests pass. The few .NET-only APIs are noted.

## Entity ids

```csharp
public readonly struct Entity : IEquatable<Entity>
{
    public const int IndexBits = 24;
    public const uint IndexMask = (1u << IndexBits) - 1;
    public const uint GenerationMask = 0xFF;

    public readonly uint Value;
    public Entity(uint value) => Value = value;

    public static Entity Make(uint index, uint generation) =>
        new Entity((generation << IndexBits) | (index & IndexMask));

    public uint Index => Value & IndexMask;
    public uint Generation => Value >> IndexBits;
    public static Entity Null => default;
    public bool IsNull => Value == 0;

    public bool Equals(Entity other) => Value == other.Value;
    public override bool Equals(object? obj) => obj is Entity other && Equals(other);
    public override int GetHashCode() => (int)Value;
    public static bool operator ==(Entity a, Entity b) => a.Value == b.Value;
    public static bool operator !=(Entity a, Entity b) => a.Value != b.Value;
    public override string ToString() => $"Entity({Index}:{Generation})";
}

public sealed class EntityRegistry
{
    const uint NoIndex = Entity.IndexMask;
    Entity[] _slots = new Entity[64];
    int _count;
    uint _freeHead = NoIndex;

    public int Capacity => _count;

    public Entity Create()
    {
        if (_freeHead != NoIndex)
        {
            uint index = _freeHead;
            Entity slot = _slots[index];             // free slot: next free index + current generation
            _freeHead = slot.Index;
            Entity e = Entity.Make(index, slot.Generation);
            _slots[index] = e;
            return e;
        }
        if (_count == _slots.Length) Array.Resize(ref _slots, _count * 2);
        Entity created = Entity.Make((uint)_count, 1);   // generations start at 1: Entity.Null is never alive
        _slots[_count++] = created;
        return created;
    }

    public void Destroy(Entity e)
    {
        if (!IsAlive(e)) throw new InvalidOperationException($"{e} is not alive");
        uint generation = (e.Generation + 1) & Entity.GenerationMask;
        if (generation == 0) generation = 1;          // skip 0 on wrap
        _slots[e.Index] = Entity.Make(_freeHead, generation);
        _freeHead = e.Index;
    }

    public bool IsAlive(Entity e) => !e.IsNull && e.Index < _count && _slots[e.Index] == e;
}
```

- A `readonly struct` with one `uint` costs the same as a `uint`, but cannot be confused with an index or a count. `default(Entity)` is `Entity.Null`, which is never alive because generations start at 1.
- Implementing `IEquatable<Entity>` matters: without it, `Dictionary<Entity, …>` and `HashSet<Entity>` fall back to `ValueType.Equals`, which is much slower (see [struct equality](../../csharp/performance/structs-span.md#struct-equality)).
- The free list is threaded through `_slots`, as on the [entities](entities.md#the-free-list-in-the-id-array) page.

## Component type ids

```csharp
static class ComponentTypeCounter
{
    internal static int Next = -1;
}

public static class ComponentType<T> where T : struct
{
    // The runtime runs this initialiser once per T, the first time ComponentType<T> is used.
    public static readonly int Id = Interlocked.Increment(ref ComponentTypeCounter.Next);
}
```

- A static readonly field in a generic static class is initialised once per `T` by the runtime, thread-safely. `ComponentType<Position>.Id` is then a plain static field read, with no dictionary lookup.
- Ids depend on the order types are first used. Do not save them; save type names or stable ids for persistence.
- All assemblies in one process (or one load context) share the same `ComponentType<T>`, so ids work across assemblies, unlike C++ statics across DLLs. A type loaded twice in different [load contexts](../../csharp/assemblies/index.md#type-identity) is a different type with a different id.

## Component masks

One bit per component type, in a fixed-size struct so masks are values with no allocation:

```csharp
public struct ComponentMask : IEquatable<ComponentMask>
{
    public const int MaxComponents = 256;
    ulong _w0, _w1, _w2, _w3;

    public void Set(int id)
    {
        ulong bit = 1UL << (id & 63);
        switch (id >> 6) { case 0: _w0 |= bit; break; case 1: _w1 |= bit; break; case 2: _w2 |= bit; break; default: _w3 |= bit; break; }
    }

    public void Clear(int id)
    {
        ulong bit = ~(1UL << (id & 63));
        switch (id >> 6) { case 0: _w0 &= bit; break; case 1: _w1 &= bit; break; case 2: _w2 &= bit; break; default: _w3 &= bit; break; }
    }

    public readonly bool Has(int id)
    {
        ulong w = (id >> 6) switch { 0 => _w0, 1 => _w1, 2 => _w2, _ => _w3 };
        return (w & (1UL << (id & 63))) != 0;
    }

    public readonly bool ContainsAll(in ComponentMask r) =>
        (_w0 & r._w0) == r._w0 && (_w1 & r._w1) == r._w1 && (_w2 & r._w2) == r._w2 && (_w3 & r._w3) == r._w3;

    public readonly bool Intersects(in ComponentMask r) =>
        ((_w0 & r._w0) | (_w1 & r._w1) | (_w2 & r._w2) | (_w3 & r._w3)) != 0;

    public readonly bool Matches(in ComponentMask with, in ComponentMask without) =>
        ContainsAll(with) && !Intersects(without);

    // Visit every set bit: one iteration per component, not per bit.
    public readonly void ForEach<TVisitor>(ref TVisitor visitor) where TVisitor : struct, IMaskVisitor
    {
        Span<ulong> words = stackalloc ulong[4] { _w0, _w1, _w2, _w3 };
        for (int i = 0; i < 4; i++)
        {
            ulong w = words[i];
            while (w != 0)
            {
                visitor.Visit(i * 64 + BitOperations.TrailingZeroCount(w));
                w &= w - 1;
            }
        }
    }

    public static ComponentMask Of<T1>() where T1 : struct
    {
        var m = new ComponentMask(); m.Set(ComponentType<T1>.Id); return m;
    }

    public static ComponentMask Of<T1, T2>() where T1 : struct where T2 : struct
    {
        var m = Of<T1>(); m.Set(ComponentType<T2>.Id); return m;
    }

    public readonly bool Equals(ComponentMask o) => _w0 == o._w0 && _w1 == o._w1 && _w2 == o._w2 && _w3 == o._w3;
    public override readonly bool Equals(object? obj) => obj is ComponentMask o && Equals(o);
    public override readonly int GetHashCode() => HashCode.Combine(_w0, _w1, _w2, _w3);
}

public interface IMaskVisitor { void Visit(int componentId); }
```

- **Four `ulong` fields** give 256 component types. A struct cannot return a `ref` to its own field by index in C# 9, so `Set`, `Clear`, and `Has` switch on the word. `ContainsAll` and `Intersects` do all four words with no branches, which is what queries call most.
- On .NET 8 (not Unity), `[InlineArray(4)]` gives an indexable fixed buffer without `unsafe`. In Unity, a `fixed ulong Words[4]` buffer in an `unsafe` struct does the same, if the assembly allows unsafe code.
- **`System.Collections.BitArray`** is a class (a heap object per mask) with no "contains all" operation, so it does not suit per-entity masks.
- **`ForEach`** visits only the set bits using `BitOperations.TrailingZeroCount`. The visitor is a struct constrained by an interface, so the call is direct and allocation-free (see [virtual calls and interfaces](../../csharp/performance/collections.md#virtual-calls-and-interfaces)). `BitOperations` is not in Unity; use `math.tzcnt` from Unity.Mathematics there.
- `Of<T1, T2>()` builds masks for queries. Build them once, when a system starts, not per frame.

## Sparse-set pools

```csharp
public abstract class Pool
{
    // sparse[index] holds position + 1, so a fresh (zeroed) array means "absent" with no fill.
    protected int[] Sparse = new int[64];
    protected Entity[] Dense = new Entity[16];
    public int Count { get; protected set; }

    public ReadOnlySpan<Entity> Entities => new ReadOnlySpan<Entity>(Dense, 0, Count);

    public bool Contains(Entity e) => PositionOf(e) >= 0;
    public abstract void Remove(Entity e);
    public abstract void AddBytes(Entity e, ReadOnlySpan<byte> bytes);   // for command buffers

    protected int PositionOf(Entity e)
    {
        uint i = e.Index;
        if (i >= (uint)Sparse.Length) return -1;
        int p = Sparse[i] - 1;
        return p >= 0 && Dense[p] == e ? p : -1;
    }
}

public sealed class Pool<T> : Pool where T : struct
{
    T[] _values = new T[16];

    public Span<T> Values => new Span<T>(_values, 0, Count);

    public ref T Add(Entity e, in T value)
    {
        if (Contains(e)) throw new InvalidOperationException($"{e} already has {typeof(T).Name}");
        uint i = e.Index;
        if (i >= (uint)Sparse.Length) Array.Resize(ref Sparse, Math.Max((int)i + 1, Sparse.Length * 2));
        if (Count == Dense.Length)
        {
            Array.Resize(ref Dense, Count * 2);
            Array.Resize(ref _values, Count * 2);
        }
        Sparse[i] = Count + 1;
        Dense[Count] = e;
        _values[Count] = value;
        return ref _values[Count++];
    }

    public override void Remove(Entity e)
    {
        int p = PositionOf(e);
        if (p < 0) return;
        int last = Count - 1;
        if (p != last)                                  // swap the last element into the hole
        {
            Dense[p] = Dense[last];
            _values[p] = _values[last];
            Sparse[Dense[p].Index] = p + 1;
        }
        _values[last] = default;                        // drop references held by the removed value
        Sparse[e.Index] = 0;
        Count--;
    }

    public ref T Get(Entity e)
    {
        int p = PositionOf(e);
        if (p < 0) throw new KeyNotFoundException($"{e} has no {typeof(T).Name}");
        return ref _values[p];
    }

    public bool TryGet(Entity e, out T value)
    {
        int p = PositionOf(e);
        value = p >= 0 ? _values[p] : default;
        return p >= 0;
    }

    public override void AddBytes(Entity e, ReadOnlySpan<byte> bytes)
    {
        if (RuntimeHelpers.IsReferenceOrContainsReferences<T>())
            throw new InvalidOperationException($"{typeof(T).Name} holds references; it cannot come from bytes");
        Add(e, Unsafe.ReadUnaligned<T>(ref MemoryMarshal.GetReference(bytes)));
    }
}
```

- The abstract `Pool` base lets the world remove from any pool without knowing `T`. `Pool<T>` holds the typed values.
- `Sparse` stores **position + 1**, so a newly allocated array (all zeros) already means "absent", and growing it needs no fill.
- `Get` returns `ref T`, so systems change components in place: `world.Get<Position>(e).X += 1` modifies the stored value, where a copy would not.
- `Remove` clears the vacated slot with `default`, so a component holding a reference (a `string`, an array) does not keep it alive after removal.
- `AddBytes` reads a component from raw bytes for the command buffer, and refuses types that contain references, which cannot be rebuilt from bytes. `RuntimeHelpers.IsReferenceOrContainsReferences<T>()` is not in Unity; Unity's `UnsafeUtility.IsUnmanaged<T>()` is the equivalent.

## The world

```csharp
public sealed class World
{
    readonly EntityRegistry _entities = new EntityRegistry();
    Pool?[] _pools = new Pool?[32];                     // indexed by ComponentType<T>.Id
    ComponentMask[] _masks = new ComponentMask[64];     // indexed by entity index

    public Entity Create()
    {
        Entity e = _entities.Create();
        if (e.Index >= _masks.Length) Array.Resize(ref _masks, _masks.Length * 2);
        _masks[e.Index] = default;
        return e;
    }

    public bool IsAlive(Entity e) => _entities.IsAlive(e);

    public void Destroy(Entity e)
    {
        if (!IsAlive(e)) return;
        var remover = new RemoveFromPools { Pools = _pools, Entity = e };
        _masks[e.Index].ForEach(ref remover);
        _masks[e.Index] = default;
        _entities.Destroy(e);
    }

    struct RemoveFromPools : IMaskVisitor
    {
        public Pool?[] Pools;
        public Entity Entity;
        public void Visit(int id) => Pools[id]!.Remove(Entity);
    }

    public ref T Add<T>(Entity e, in T value) where T : struct
    {
        if (!IsAlive(e)) throw new InvalidOperationException($"{e} is not alive");
        _masks[e.Index].Set(ComponentType<T>.Id);
        return ref GetPool<T>().Add(e, value);
    }

    public void Remove<T>(Entity e) where T : struct
    {
        if (!IsAlive(e)) return;
        _masks[e.Index].Clear(ComponentType<T>.Id);
        GetPool<T>().Remove(e);
    }

    public bool Has<T>(Entity e) where T : struct =>
        IsAlive(e) && _masks[e.Index].Has(ComponentType<T>.Id);

    public bool HasAll(Entity e, in ComponentMask required) =>
        IsAlive(e) && _masks[e.Index].ContainsAll(required);

    public ref T Get<T>(Entity e) where T : struct => ref GetPool<T>().Get(e);

    public Pool<T> GetPool<T>() where T : struct
    {
        int id = ComponentType<T>.Id;
        if (id >= _pools.Length) Array.Resize(ref _pools, Math.Max(id + 1, _pools.Length * 2));
        return (Pool<T>)(_pools[id] ??= new Pool<T>());
    }

    public Pool? GetPool(int id) => id < _pools.Length ? _pools[id] : null;

    internal void AddBytes(Entity e, int id, ReadOnlySpan<byte> bytes)
    {
        _masks[e.Index].Set(id);
        _pools[id]!.AddBytes(e, bytes);
    }

    internal void RemoveById(Entity e, int id)
    {
        _masks[e.Index].Clear(id);
        _pools[id]?.Remove(e);
    }
}
```

- `Destroy` walks the entity's mask with a struct visitor, removing it from exactly the pools it is in.
- `GetPool<T>` creates pools on first use with `??=`. If systems run on several threads, create every pool at start-up instead, because two threads creating pools at once race on `_pools`.

## Queries

Two ways to run a function over every entity with `T1` and `T2`:

```csharp
public delegate void RefAction<T1, T2>(Entity e, ref T1 a, ref T2 b);

public interface IForEach<T1, T2>
{
    void Execute(Entity e, ref T1 a, ref T2 b);
}

public static class Queries
{
    // Simple: a delegate. Allocates if the lambda captures anything.
    public static void ForEach<T1, T2>(this World world, RefAction<T1, T2> action)
        where T1 : struct where T2 : struct
    {
        Pool<T1> p1 = world.GetPool<T1>();
        Pool<T2> p2 = world.GetPool<T2>();
        ReadOnlySpan<Entity> lead = p1.Count <= p2.Count ? p1.Entities : p2.Entities;   // smallest first
        for (int i = 0; i < lead.Length; i++)
        {
            Entity e = lead[i];
            if (!p1.Contains(e) || !p2.Contains(e)) continue;
            action(e, ref p1.Get(e), ref p2.Get(e));
        }
    }

    // Fast: a struct job. The JIT compiles a copy per job type and can inline Execute.
    public static void Run<T1, T2, TJob>(this World world, ref TJob job)
        where T1 : struct where T2 : struct
        where TJob : struct, IForEach<T1, T2>
    {
        Pool<T1> p1 = world.GetPool<T1>();
        Pool<T2> p2 = world.GetPool<T2>();
        ReadOnlySpan<Entity> lead = p1.Count <= p2.Count ? p1.Entities : p2.Entities;
        for (int i = 0; i < lead.Length; i++)
        {
            Entity e = lead[i];
            if (!p1.Contains(e) || !p2.Contains(e)) continue;
            job.Execute(e, ref p1.Get(e), ref p2.Get(e));
        }
    }
}
```

```csharp
// Delegate: simple. A static lambda (or one capturing nothing) is cached and does not allocate.
world.ForEach((Entity e, ref Position p, ref Velocity v) => { p.X += v.X; p.Y += v.Y; });

// Struct job: no delegate call; the JIT specialises Run for MoveJob and can inline Execute.
struct MoveJob : IForEach<Position, Velocity>
{
    public float Dt;
    public void Execute(Entity e, ref Position p, ref Velocity v) { p.X += v.X * Dt; p.Y += v.Y * Dt; }
}

var job = new MoveJob { Dt = dt };
world.Run<Position, Velocity, MoveJob>(ref job);
```

- The built-in `Action<T1, T2>` cannot take `ref` parameters, so declare a `RefAction` delegate. Without `ref`, each component is copied into the lambda and changes are lost.
- A lambda that captures a local (`dt`) allocates a closure on every call. Pass such values in a struct job's fields instead.
- C# has no variadic generics, so each arity (one, two, three… components) needs its own overload. Write them once by hand up to four or five, or [generate them](../../csharp/roslyn/source-generators.md).
- As in C++, **do not change pools during a query**: the `Entities` span is over the pool's internal array, which `Remove` reorders and `Add` can reallocate. Use the command buffer.

## Archetype columns

C# columns stay typed (`T[]`), behind a non-generic base class so an archetype can hold any mix:

```csharp
public abstract class Column
{
    public int Count { get; protected set; }
    public abstract void RemoveRow(int row);                 // swap-remove
    public abstract void MoveRowTo(int row, Column dst);     // append this row to dst (same T)
}

public sealed class Column<T> : Column where T : struct
{
    T[] _items = new T[16];

    public Span<T> Span => new Span<T>(_items, 0, Count);

    public void Add(in T value)
    {
        if (Count == _items.Length) Array.Resize(ref _items, Count * 2);
        _items[Count++] = value;
    }

    public override void RemoveRow(int row)
    {
        int last = Count - 1;
        _items[row] = _items[last];
        _items[last] = default;
        Count--;
    }

    public override void MoveRowTo(int row, Column dst) => ((Column<T>)dst).Add(_items[row]);
}

public sealed class Archetype
{
    public ComponentMask Mask;
    public readonly int[] Types;                    // component ids, same order as Columns
    public readonly Column[] Columns;
    public readonly List<Entity> Entities = new List<Entity>();

    public Archetype(ComponentMask mask, int[] types, Column[] columns)
    {
        Mask = mask; Types = types; Columns = columns;
    }

    public int ColumnIndex(int id) => Array.IndexOf(Types, id);
    public Column<T> Column<T>() where T : struct => (Column<T>)Columns[ColumnIndex(ComponentType<T>.Id)];
}

public static class ArchetypeQueries
{
    public static void ForEach<T1, T2>(List<Archetype> matching, RefAction<T1, T2> action)
        where T1 : struct where T2 : struct
    {
        foreach (Archetype a in matching)
        {
            Span<T1> c1 = a.Column<T1>().Span;          // cast once per archetype, not per row
            Span<T2> c2 = a.Column<T2>().Span;
            for (int row = 0; row < c1.Length; row++)
                action(a.Entities[row], ref c1[row], ref c2[row]);
        }
    }
}
```

- `MoveRowTo` copies a row into another archetype's column of the same type, and `RemoveRow` swap-removes it: moving an entity between archetypes is one of each per column, as on the [archetype page](archetype-storage.md#adding-and-removing-a-component).
- The virtual calls per column per move are acceptable for structural changes, which should be rare. The iteration is what must be fast, and it uses `Span<T>` over each typed array, fetched once per archetype.
- For unmanaged components, storing each column as a `byte[]` (or native memory) and reading it with `MemoryMarshal.Cast<byte, T>` avoids the virtual calls and allows chunks shared by all columns, as Unity Entities does internally.

## Command buffer

```csharp
public sealed class CommandBuffer
{
    enum Op : byte { Destroy, Add, Remove }

    [StructLayout(LayoutKind.Sequential, Pack = 1)]
    struct Header
    {
        public Op Op;
        public int Component;
        public Entity Entity;
        public int Size;
    }

    byte[] _bytes = new byte[1024];
    int _length;
    readonly List<Action<World>> _managed = new List<Action<World>>();   // components holding references

    public void Destroy(Entity e) => Write(new Header { Op = Op.Destroy, Entity = e });

    public void Remove<T>(Entity e) where T : struct =>
        Write(new Header { Op = Op.Remove, Component = ComponentType<T>.Id, Entity = e });

    public void Add<T>(Entity e, in T value) where T : unmanaged
    {
        int size = Unsafe.SizeOf<T>();
        Write(new Header { Op = Op.Add, Component = ComponentType<T>.Id, Entity = e, Size = size });
        Unsafe.WriteUnaligned(ref Reserve(size), value);
    }

    public void AddManaged<T>(Entity e, T value) where T : struct =>
        _managed.Add(w => { if (w.IsAlive(e)) w.Add(e, value); });         // allocates: use sparingly

    public void Playback(World world)
    {
        int pos = 0;
        int headerSize = Unsafe.SizeOf<Header>();
        while (pos < _length)
        {
            Header h = Unsafe.ReadUnaligned<Header>(ref _bytes[pos]);
            pos += headerSize;
            var payload = new ReadOnlySpan<byte>(_bytes, pos, h.Size);
            pos += h.Size;

            if (!world.IsAlive(h.Entity)) continue;                         // destroyed earlier: skip
            switch (h.Op)
            {
                case Op.Destroy: world.Destroy(h.Entity); break;
                case Op.Add: world.AddBytes(h.Entity, h.Component, payload); break;
                case Op.Remove: world.RemoveById(h.Entity, h.Component); break;
            }
        }
        _length = 0;                                                        // keeps capacity

        foreach (var action in _managed) action(world);
        _managed.Clear();
    }

    void Write(in Header h) => Unsafe.WriteUnaligned(ref Reserve(Unsafe.SizeOf<Header>()), h);

    ref byte Reserve(int size)
    {
        if (_length + size > _bytes.Length) Array.Resize(ref _bytes, Math.Max(_bytes.Length * 2, _length + size));
        ref byte start = ref _bytes[_length];
        _length += size;
        return ref start;
    }
}
```

- **Unmanaged** components (no references) are written into one growing `byte[]` with `Unsafe.WriteUnaligned`, after a packed header. Recording allocates nothing once the buffer has grown to its working size.
- Components that hold references (`string`, arrays, class references) cannot be stored as bytes. `AddManaged` keeps a closure per command instead, which allocates; keep such components rare, or give them their own typed lists.
- Playback skips commands whose entity is no longer alive, then clears the buffer without freeing it.
- In Unity Entities, `EntityCommandBuffer` is this structure, with the same rules: record during iteration, play back at a sync point.
