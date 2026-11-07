# Structs, Span, and ref

Value types live inline: in a local variable, in an array, or inside another object. They avoid the heap, and an array of them is one contiguous block. They are also copied whenever they are assigned or passed, which is either free or the whole problem, depending on size.

## Class or struct

| | Class | Struct |
| --- | --- | --- |
| Stored | On the heap; variables hold a reference | Inline, wherever the variable or field is |
| Assignment | Copies the reference (8 bytes) | Copies every field |
| Array of them | An array of references to objects scattered in the heap | One contiguous block of data |
| Identity, inheritance, null | Yes | No |
| GC cost | Each object is tracked | None, unless boxed or inside a class |

Use a struct for small, short-lived values with no identity: vectors, colours, ids, handles, ranges, hit results, and the elements of big arrays such as particles. Use a class for objects with identity and a lifetime: entities, systems, assets.

Size matters because of copying. Up to about 16 bytes, passing by value is as cheap as passing a reference. Larger structs are still fine in arrays, but pass them by reference (below) instead of copying them into every call.

## Passing by reference

```csharp
// Copies 64 bytes into each call.
static float Determinant(Matrix4x4 m) { ... }

// Passes a reference; the method cannot modify m.
static float Determinant(in Matrix4x4 m) { ... }

// Passes a reference; the method can modify the caller's value.
static void Integrate(ref Particle p, float dt)
{
    p.Velocity += p.Acceleration * dt;
    p.Position += p.Velocity * dt;
}

for (int i = 0; i < particles.Length; i++)
    Integrate(ref particles[i], dt);
```

`ref` and `ref` locals also fix the most common struct bug: modifying a copy.

```csharp
particles[i].Position += v;               // array element: modifies the element in place

list[i].Position += v;                    // List<T>: error CS1612, the indexer returns a copy

ref Particle p = ref particles[i];        // a reference to the element
p.Position += v;
p.Age += dt;
```

An array element is a storage location, so `particles[i].Field = x` works. A `List<T>` indexer returns a copy, so the compiler refuses the same statement. With a list of structs, read the element, change it, and write it back, or keep the data in an array.

## Defensive copies

When a method is called on a struct that the compiler must not let change (an `in` parameter, a `readonly` field), and the method might modify the struct, the compiler calls it on a **hidden copy**. The code is correct, but each call copies the struct.

```csharp
struct Bounds
{
    public Vector3 Min, Max;
    public Vector3 Size() => Max - Min;          // not marked readonly
}

float Volume(in Bounds b)
{
    Vector3 s = b.Size();                         // copies b first, then calls Size on the copy
    return s.x * s.y * s.z;
}
```

Prevent it by declaring what does not modify the struct:

```csharp
readonly struct Bounds { ... }                    // every member is readonly

struct Bounds
{
    public Vector3 Min, Max;
    public readonly Vector3 Size() => Max - Min;  // just this member (C# 8)
}
```

Make small immutable structs `readonly struct`. Mark the non-modifying members of mutable structs `readonly`. Then `in` parameters and `readonly` fields never copy.

## Span and stackalloc

`Span<T>` is a view of contiguous memory: part of an array, memory on the stack, or native memory. It allocates nothing, and slicing it is free.

```csharp
// A temporary buffer on the stack, with no heap allocation.
Span<int> neighbours = stackalloc int[8];
int count = GetNeighbours(cell, neighbours);
foreach (int n in neighbours[..count]) Visit(n);

// One method for arrays, slices of arrays, and stack memory.
static float Sum(ReadOnlySpan<float> values)
{
    float sum = 0;
    foreach (float v in values) sum += v;
    return sum;
}

Sum(samples);                     // the whole array
Sum(samples.AsSpan(10, 20));      // part of it, no copy
```

- `stackalloc` memory is freed when the method returns. Keep it small (a few hundred bytes to a few kilobytes), and never inside a loop that runs many times in one call, because each iteration takes more stack.
- `ReadOnlySpan<char>` slices strings without allocating: `line.AsSpan().Trim()`, `int.Parse(span)`, and `span.SequenceEqual("pickup")`. Parsing a data file this way creates only the strings you keep.
- `Span<T>` is a `ref struct`: it cannot be a field of a class, be boxed, be captured by a lambda, or live across an `await` or `yield`. Use `Memory<T>` when a view has to be stored.
- `MemoryMarshal.Cast<byte, float>(bytes)` reinterprets memory without copying, for reading binary data.
- In .NET 5 and later, `CollectionsMarshal.AsSpan(list)` gives a span over a `List<T>`'s internal array, so struct elements can be changed in place. Do not add or remove items while using it.

**Unity** (C# 9, .NET Standard 2.1) has `Span<T>`, `stackalloc` into a span, `in`, `readonly struct`, and `readonly` members, but not `CollectionsMarshal` or features from C# 10 and later. For native memory it has `NativeArray<T>`, which converts to a span with `AsSpan()`.

## Struct equality

`ValueType.Equals` and `ValueType.GetHashCode`, which a struct gets by default, compare fields using reflection when the struct contains references, and box the value when called through `object`. A struct used as a `Dictionary` or `HashSet` key should implement `IEquatable<T>`:

```csharp
readonly struct CellKey : IEquatable<CellKey>
{
    public readonly int X, Y;
    public CellKey(int x, int y) { X = x; Y = y; }

    public bool Equals(CellKey other) => X == other.X && Y == other.Y;
    public override bool Equals(object? obj) => obj is CellKey other && Equals(other);
    public override int GetHashCode() => HashCode.Combine(X, Y);
}
```

`Dictionary<TKey, TValue>` uses `EqualityComparer<TKey>.Default`, which calls `IEquatable<T>.Equals` directly when the type implements it. A `record struct` (C# 10) generates all of this, but is not available in Unity.
