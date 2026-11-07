# Measuring

Performance work starts and ends with a measurement: one to find what is slow, and one to show the change helped. Guessing is wrong often enough that it is not worth the risk.

## Rules for any measurement

- **Release builds only.** Debug builds disable inlining and most optimisation; their timings say nothing about shipped code. In Unity, profile a player build, not the editor.
- **Realistic sizes.** A loop over 10 items and a loop over 100,000 have different bottlenecks. Measure with the counts the game actually has.
- **Warm up.** The first calls include JIT compilation, cold caches, and lazy initialisation. Ignore them, or measure separately if start-up time is what matters.
- **Many runs, and look at the spread.** Report the median, and watch the outliers: a game cares about its worst frames, not its average.
- **One change at a time.** Measure, change one thing, measure again.

## Stopwatch

```csharp
var sw = Stopwatch.StartNew();
for (int i = 0; i < 1000; i++) Work();
sw.Stop();
Console.WriteLine($"{sw.Elapsed.TotalMilliseconds / 1000:F4} ms per call");
```

Good enough for a quick check, or for timing a whole loading step. For comparing two implementations of something that takes microseconds, the JIT can remove work whose result is unused, and timer resolution and noise swamp the difference. Use a benchmark library.

## BenchmarkDotNet

[BenchmarkDotNet](https://benchmarkdotnet.org/) handles warm-up, repetition, statistics, and keeping the JIT from optimising the work away.

```csharp
using BenchmarkDotNet.Attributes;
using BenchmarkDotNet.Running;

[MemoryDiagnoser]
public class SumBenchmarks
{
    float[] _values = null!;

    [Params(1_000, 100_000)]
    public int N;

    [GlobalSetup]
    public void Setup()
    {
        var random = new Random(42);
        _values = new float[N];
        for (int i = 0; i < N; i++) _values[i] = (float)random.NextDouble();
    }

    [Benchmark(Baseline = true)]
    public float ForLoop()
    {
        float sum = 0;
        for (int i = 0; i < _values.Length; i++) sum += _values[i];
        return sum;
    }

    [Benchmark]
    public float Linq() => _values.Sum();
}

public static class Program
{
    public static void Main() => BenchmarkRunner.Run<SumBenchmarks>();
}
```

```bash
dotnet run -c Release
```

- **Return the result** from each benchmark method. BenchmarkDotNet consumes it, so the JIT cannot discard the work as unused.
- `[Params]` runs every benchmark at each size. `Baseline = true` adds a **Ratio** column relative to that method.
- `[MemoryDiagnoser]` adds an **Allocated** column: bytes allocated per call. Anything other than `-` (zero) in a method meant to run per frame needs explaining.
- Put the setup in `[GlobalSetup]`, so it is not timed. Use a fixed random seed, so runs are comparable.
- Columns to read: **Mean** (average time per call), **Error** and **StdDev** (how noisy it was), **Ratio**, and **Allocated**. A difference smaller than the error is not a difference.

BenchmarkDotNet runs on .NET, not inside Unity. Code that does not depend on Unity can be benchmarked in a separate .NET project, which tells you which approach is faster, though not the exact times under Mono or IL2CPP.

## Allocation tests

Lock in "this allocates nothing" as a unit test, so a later change cannot quietly break it:

```csharp
[Fact]
public void Update_does_not_allocate()
{
    var system = new ParticleSystem(capacity: 1000);
    system.Update(0.016f);                                   // warm up: first call may allocate lazily

    long before = GC.GetAllocatedBytesForCurrentThread();
    for (int i = 0; i < 100; i++) system.Update(0.016f);
    long allocated = GC.GetAllocatedBytesForCurrentThread() - before;

    Assert.Equal(0, allocated);
}
```

In Unity tests, `Is.Not.AllocatingGCMemory()` does the same. It comes from `UnityEngine.TestTools.Constraints`, whose `Is` replaces NUnit's (`using Is = UnityEngine.TestTools.Constraints.Is;`):

```csharp
Assert.That(() => system.Update(0.016f), Is.Not.AllocatingGCMemory());
```

## Reading the generated code

To see what the compiler and JIT made of a piece of code:

- [SharpLab](https://sharplab.io/) shows, for a snippet, the lowered C# (what `foreach`, lambdas, and `using` turn into), the IL, and the JIT's assembly. It is the quickest way to see a hidden closure, a boxing instruction (`box` in the IL), or whether a bounds check was removed.
- BenchmarkDotNet's `[DisassemblyDiagnoser]` prints the assembly of each benchmark, as it actually ran.
- In .NET, `DOTNET_JitDisasm=MethodName` prints a method's assembly when it is compiled (.NET 7 and later).
- Unity's **Burst Inspector** (Jobs → Burst → Open Inspector) shows the assembly Burst produced for each job, including whether loops were vectorised.

## Profilers

| Tool | For |
| --- | --- |
| Unity Profiler | Frame timing, the GC Alloc column, custom markers. See the [profiler walkthrough](../../unity/tools/profiler.md). |
| Unity Memory Profiler package | Snapshots of the managed and native heap: what is alive and what references it. |
| dotnet-counters | Live GC counts, allocation rate, and heap size of a running .NET process. |
| dotnet-trace, PerfView | Sampling CPU profiles and allocation tracking for .NET. |
| Visual Studio and Rider profilers | CPU and memory profiling from the IDE, for .NET and for Unity players. |
| Superluminal, VTune, Tracy | Native-level sampling, useful for IL2CPP builds and engines with C++ underneath. |

## Unity runtimes

The same C# behaves differently on each runtime, so measure on the one you ship:

- **Mono** (the editor, and players built with the Mono scripting backend) JIT-compiles with fewer optimisations than .NET's RyuJIT. Code that is fast on .NET may not be on Mono.
- **IL2CPP** converts IL to C++ and compiles it ahead of time. It is usually faster than Mono, but adds null and bounds checks, and generic code over reference types is shared.
- **Burst** compiles a subset of C# (structs, `NativeArray`, no managed objects) through LLVM, with SIMD. For heavy loops it is often many times faster than either of the above. It is the main reason to restructure hot code into jobs over native containers.
