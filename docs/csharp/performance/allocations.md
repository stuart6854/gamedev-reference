# Allocations and the GC

Every `new` of a class, array, string, or delegate allocates on the managed heap, and the garbage collector reclaims it later. Allocating is fast. Collecting is the cost, and it lands in whichever frame happens to trigger it. A game that allocates a few kilobytes every frame collects regularly, and each collection is a hitch.

The goal is not zero allocations everywhere. It is **no allocations per frame** in steady gameplay: allocate when loading, and reuse during play.

## Hidden allocations

Most per-frame garbage comes from code that does not say `new`:

| Code | What is allocated | Instead |
| --- | --- | --- |
| A struct passed as `object` or an interface | A box: a heap copy of the struct | Generic methods with a `where T : struct` constraint |
| `string.Format("{0}", 42)`, `Debug.Log($"hp {hp}")` | A box per value type argument, and the string | Cache text that rarely changes; build it with a reused `StringBuilder` |
| String concatenation, `ToString()`, `Substring` | A new string each time | Compare and slice with `ReadOnlySpan<char>`; cache UI text and update it only when the value changes |
| A lambda that captures a local or `this` | A closure object and a delegate | A `static` lambda (C# 9), or pass state as a parameter |
| A method group passed as a delegate (`list.ForEach(Process)`) | A delegate, every call (before C# 11) | Store the delegate in a field once |
| `params object[]` or `params T[]` methods | The array | Overloads with fixed parameter counts |
| `foreach` over an `IEnumerable<T>` or `IList<T>` variable | A boxed enumerator | `foreach` over the concrete `List<T>` or array, which uses a struct enumerator |
| LINQ (`Where`, `Select`, `ToList`, `Any` with a lambda) | Iterators, delegates, closures, result lists | A `for` loop in hot code; LINQ is fine at load time |
| `yield return` iterators, Unity coroutines | The iterator object | Reuse long-running coroutines; avoid starting one per event |
| `async` methods that complete asynchronously | The state machine and a `Task` | `ValueTask` for methods that usually complete synchronously |
| `enum.ToString()`, `Enum.HasFlag` on Mono | A string; a box | Generated names (see [generator examples](../roslyn/generator-examples.md#fast-enum-names)); `(flags & X) != 0` |
| Unity: `GetComponents<T>()`, `Physics.RaycastAll`, `mesh.vertices` | A new array per call | `GetComponents(list)`, `Physics.RaycastNonAlloc` with a reused buffer, `mesh.GetVertices(list)` |

### Closures

```csharp
// Allocates a closure (for threshold) and a delegate on every call.
int CountAbove(List<Enemy> enemies, float threshold) =>
    enemies.Count(e => e.Health > threshold);

// Allocates nothing.
int CountAbove(List<Enemy> enemies, float threshold)
{
    int n = 0;
    foreach (Enemy e in enemies)            // List<T>.Enumerator is a struct
        if (e.Health > threshold) n++;
    return n;
}
```

A lambda that uses nothing from outside is cached by the compiler and allocates once. Mark such lambdas `static` (C# 9) so the compiler refuses if one later captures something by accident:

```csharp
items.Sort(static (a, b) => a.Price.CompareTo(b.Price));
```

## Reuse instead of allocating

### Buffers

```csharp
readonly List<Collider> _hits = new(64);            // allocated once, reused every frame
readonly Collider[] _overlap = new Collider[32];

void Update()
{
    _hits.Clear();                                   // keeps its capacity
    int count = Physics.OverlapSphereNonAlloc(transform.position, 5f, _overlap);
    for (int i = 0; i < count; i++)
        if (IsEnemy(_overlap[i])) _hits.Add(_overlap[i]);
}
```

A `List<T>` that is cleared and refilled keeps its internal array, so after the first few frames it never allocates again.

### Pools

For temporary arrays whose size varies, rent from a shared pool:

```csharp
int[] buffer = ArrayPool<int>.Shared.Rent(count);   // may be longer than count
try
{
    Fill(buffer.AsSpan(0, count));
}
finally
{
    ArrayPool<int>.Shared.Return(buffer);
}
```

The array may be longer than requested, so use `count`, not `buffer.Length`. Do not keep the array after returning it.

Unity provides `UnityEngine.Pool`: `ListPool<T>.Get()` and `ListPool<T>.Release(list)`, `HashSetPool<T>`, and `ObjectPool<T>` for your own objects. Pooling game objects is covered in [object pooling](../../unity/architecture/pooling.md).

Pool only what is allocated often. A pool of rarely used objects just keeps memory alive for nothing.

## The garbage collector

### .NET

The .NET GC is **generational** and **compacting**. New objects go in generation 0, which is collected often and cheaply because most objects die young. Survivors move to generations 1 and 2, which are collected rarely. Objects of 85,000 bytes or more go straight to the large object heap, collected only with generation 2.

- Short-lived garbage is cheap; long-lived objects that die later (caches, objects kept for a few seconds) are expensive, because they reach generation 2 first.
- `GCSettings.LatencyMode = GCLatencyMode.SustainedLowLatency` avoids blocking full collections where it can, during gameplay.
- Workstation GC with concurrent collection (the default for desktop apps) suits a game client. Server GC uses more threads and memory, and suits dedicated servers.
- `GC.TryStartNoGCRegion(bytes)` guarantees no collection for a short section, if that much memory can be reserved up front. End it with `GC.EndNoGCRegion()`.

### Unity

Unity's Mono and IL2CPP runtimes use the **Boehm** collector. It is not generational and does not compact: every collection scans the whole heap, so its cost grows with the total amount of managed memory, not with the amount of garbage.

- **Incremental GC** (Project Settings → Player, on by default) spreads the scan over several frames, in time slices. It reduces spikes, but does not remove the cost, and it adds a small overhead to writes of references.
- `GarbageCollector.GCMode` (namespace `UnityEngine.Scripting`) can be set to `Disabled` or `Manual` for a short section, such as a boss fight, as long as nothing in it allocates much; heap use grows until it is re-enabled. In `Manual` mode, `GarbageCollector.CollectIncremental(nanoseconds)` runs a slice when you choose, for example during a loading screen.
- Because the heap does not compact, a heap that grew during loading stays large and fragmented. Allocate big long-lived structures early and keep them.

## Finding allocations

- **Unity:** the Profiler's **GC Alloc** column in the Hierarchy view, sorted descending, shows which methods allocate each frame. See the [profiler walkthrough](../../unity/tools/profiler.md#allocations).
- **.NET:** BenchmarkDotNet's memory diagnoser reports bytes allocated per call. `GC.GetAllocatedBytesForCurrentThread()` before and after a call turns "this allocates nothing" into a test. See [measuring](measuring.md).
- **Analysers** such as the Heap Allocation Viewer (Rider) and ClrHeapAllocationAnalyzer highlight boxing, closures, and hidden allocations in the editor as you type.
