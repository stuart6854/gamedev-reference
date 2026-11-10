# C\#

Notes on the C# language and its tooling that are not tied to an engine. Unity-specific setup is covered on each page where it differs.

- [Performance](performance/index.md) — allocations and the GC, structs and `Span<T>`, pointers and native memory, unions and command buffers, collections and data layout, and measuring.
- [Roslyn analysers and source generators](roslyn/index.md) — compiler plug-ins that check code as it is written, and generate code while it compiles.
- [Assemblies and load contexts](assemblies/index.md) — how .NET loads assemblies, plugins in their own load contexts, hosting .NET in a C++ engine, and reloading scripts.
- [Async and await in games](async.md) — what `await` does to threads and timing, cancellation, a per-frame synchronisation context, frame and game-time waits, and Unity's `Awaitable`.
