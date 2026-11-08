# C# performance

Writing C# that runs well in a game: fewer allocations, value types used where they help, collections and data laid out for the cache, and measuring before and after. Examples target .NET 8, with notes where Unity's runtimes (Mono and IL2CPP, C# 9) differ.

- [Allocations and the GC](allocations.md) — what allocates without looking like it, pooling, and garbage collector settings in .NET and Unity.
- [Structs, Span, and ref](structs-span.md) — when value types help, `in` and `ref`, defensive copies, `Span<T>` and `stackalloc`, and struct equality.
- [Pointers and native memory](memory.md) — `unsafe` code, pinning, native allocations and arenas, reinterpreting bytes with `MemoryMarshal`, struct layout, and calling native code.
- [Collections and data layout](collections.md) — choosing and sizing collections, arrays of structs against structs of arrays, and keeping virtual calls out of hot loops.
- [Measuring](measuring.md) — BenchmarkDotNet, allocation tests, reading the generated code, and profiling in Unity.

The rule that comes before all of them: measure first. Most code is not hot, and rewriting it for speed only makes it harder to read.
