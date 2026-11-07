# Collections and data layout

A hot loop's speed depends mostly on how its data sits in memory. Reading memory the CPU has just read, or is about to read, is fast; jumping around the heap waits on main memory for every object. This page covers choosing collections, laying data out for the cache, and keeping hot loops free of calls the JIT cannot inline.

## Choosing a collection

| Need | Use | Notes |
| --- | --- | --- |
| Fixed size, fastest iteration | `T[]` | Bounds checks are often removed (see [loops](#loops)). |
| Growing list | `List<T>` | Set the capacity up front if you know it. |
| Remove from the middle, order does not matter | `List<T>` with swap-remove | `O(1)` instead of `RemoveAt`'s `O(n)`. |
| Look up by key | `Dictionary<TKey, TValue>` | Keys need good hashes; see [struct equality](structs-span.md#struct-equality). |
| Small integer keys | An array indexed by the key, or a [sparse set](../../data-structures/sparse-set.md) | No hashing at all. |
| Membership | `HashSet<T>`, or a [bitset](../../data-structures/bits.md#bitsets) for small integers | |
| First in, first out | `Queue<T>`, or a [ring buffer](../../data-structures/ring-buffer.md) with a fixed size | |
| Always take the smallest | `PriorityQueue<TElement, TPriority>` (.NET 6) | Not in Unity: use a binary heap. |
| Sorted iteration | Sort a `List<T>` when needed | `SortedDictionary` and `SortedList` are slow to insert and iterate. |

```csharp
// Swap-remove: move the last element into the hole.
static void RemoveAtSwapBack<T>(List<T> list, int index)
{
    int last = list.Count - 1;
    list[index] = list[last];
    list.RemoveAt(last);
}
```

- **Capacity.** A `List<T>` or `Dictionary` grows by allocating a bigger array and copying. Pass the expected size to the constructor, or call `EnsureCapacity`.
- **Clear, don't recreate.** `Clear()` keeps the allocated storage. A list that is cleared and refilled every frame stops allocating after the first frame.
- **Strings as keys** hash every character on every lookup. Turn names into integer ids or hashes once, at load time, and look up by those.
- **Iterating a `Dictionary`** is slower than iterating a list, and its order is not guaranteed. When something is both looked up and iterated every frame, keep a list for iteration and a dictionary from key to index.

## Arrays of structs, structs of arrays

```csharp
// Array of classes: an array of references, objects scattered across the heap.
class Particle { public Vector3 Position, Velocity; public float Age; public Color Color; }
Particle[] particles;

// Array of structs (AoS): one block; each element holds every field.
struct Particle { public Vector3 Position, Velocity; public float Age; public Color Color; }
Particle[] particles;

// Struct of arrays (SoA): one array per field.
class Particles
{
    public Vector3[] Position, Velocity;
    public float[] Age;
    public Color[] Color;
}
```

A loop that updates positions reads `Position` and `Velocity` and nothing else.

- With **classes**, each particle is a separate object, and each access may miss the cache. This is usually the slowest by a wide margin, and the GC has to track every particle.
- With **AoS**, the loop also pulls `Age` and `Color` into the cache with each element, using cache space for data it does not need.
- With **SoA**, every byte the loop reads is one it uses, and the arrays are in the right form for SIMD (`System.Numerics.Vector<T>`, Unity's Burst).

Start with an array of structs, which is simple and much faster than classes. Move to SoA for the hottest loops over large counts, as the [particle system](../../graphics/particles.md) page does.

### Hot and cold data

A struct mixes fields used every frame (position, velocity) with fields used rarely (display name, spawn time, debug info). Split the rare ones into a separate array, indexed the same way. The hot array gets smaller, and more elements fit in the cache.

## Loops

```csharp
// The JIT removes the bounds check: it can see i stays within the array.
for (int i = 0; i < values.Length; i++)
    sum += values[i];

// Here it cannot be sure, so every access is checked.
for (int i = 0; i < count; i++)
    sum += values[i];

// Copy fields to locals: a field may change between iterations, a local cannot.
float[] v = _values;
for (int i = 0; i < v.Length; i++)
    sum += v[i];
```

- Looping to `array.Length` lets the JIT drop the bounds check. Looping to another count, or over a field the loop body might change, keeps it. `foreach` over an array or span gets the same treatment.
- Call no methods that cannot be inlined in the innermost loop. Hoist work that does not change out of it.
- IL2CPP adds bounds checks and null checks to the generated C++. `[Il2CppSetOption(Option.ArrayBoundsChecks, false)]` (from Unity's `Il2CppSetOptionAttribute.cs`) removes them for one method or class, once the code is known to be correct.

## Virtual calls and interfaces

A call through an interface or a virtual method cannot usually be inlined, and costs an indirect jump. In a loop over thousands of elements that adds up, and it stops the JIT from optimising the loop body as a whole.

```csharp
// Called through an interface for every element.
interface IModifier { float Apply(float v); }
static void ApplyAll(float[] values, IModifier m)
{
    for (int i = 0; i < values.Length; i++) values[i] = m.Apply(values[i]);
}

// A generic constrained to a struct: the JIT compiles a separate copy for each struct
// type, where m.Apply is a direct call it can inline.
static void ApplyAll<T>(float[] values, T m) where T : struct, IModifier
{
    for (int i = 0; i < values.Length; i++) values[i] = m.Apply(values[i]);
}

readonly struct Scale : IModifier
{
    readonly float _k;
    public Scale(float k) => _k = k;
    public float Apply(float v) => v * _k;
}

ApplyAll(values, new Scale(2f));
```

- **Value-type generics are specialised**: .NET and IL2CPP generate code per struct type argument, so the interface call disappears. Reference-type arguments share one copy of the code, and keep the interface call.
- **`sealed` classes** let the JIT call virtual methods directly when it knows the exact type. Seal classes that are not meant to be inherited from.
- **Batch by type.** Instead of a list of mixed `IEffect` objects processed one at a time, keep a list per effect type and process each list in its own loop. Each loop is then monomorphic, and the data for each type is together. This is the idea behind an [ECS](../../engine/ecs/index.md).
- **Delegates** are like interface calls: an indirect call that is not inlined. A `Func<T>` called per element in a hot loop costs the same as an interface call.
