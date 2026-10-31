---
engine: Unity
version: 6+
uses:
  - name: Hordes and crowds
    text: Finding which of thousands of agents' systems costs the most, with a marker per system.
  - name: Top-down survival
    text: Hunting the hitch when a new chunk streams in or a horde wakes up.
  - name: Open worlds
    text: Garbage collection spikes from allocations spread across hundreds of scripts.
---

# Profiler walkthrough

The Profiler records what every frame spent its time on. This page is the order to work in: profile the right thing, find the slow frames, tell whether the CPU or the GPU is the limit, find the code responsible, and measure the fix. Then custom markers for your own systems, and a stats readout in the game.

## Profile a build, not the editor

The editor adds its own work to every frame, and runs your code with extra checks. Numbers from Play mode are a rough guide; numbers from a build are the truth.

1. In **Build Profiles**, tick **Development Build** and **Autoconnect Profiler**. Leave **Deep Profiling Support** off.
2. Build and run on the target hardware: the slowest machine you support, not your workstation.
3. Open **Window → Analysis → Profiler**. With **Autoconnect**, it attaches when the build starts. Otherwise pick the player from the target dropdown at the top of the window.

Profiling Play mode is fine for comparing before and after a change, and for finding allocations. Ignore `EditorLoop` time there: it is the editor, not the game.

## Find the bad frames

The **CPU Usage** chart at the top shows every frame's time, coloured by category. Look for:

- **Spikes**: single frames far above the rest. Hitches. Often loading, garbage collection, or a burst of work, such as a horde waking.
- **A high floor**: every frame too slow. Steady per-frame cost.

Click a spike to select that frame. The lower half shows its detail.

## CPU or GPU

Select the **Timeline** view in the lower half. It shows the main thread, the render thread, and the job workers side by side, in time.

| On the main thread | Means |
| --- | --- |
| `PlayerLoop` taking most of the frame, with your scripts inside | CPU bound in game code. Read on. |
| `Gfx.WaitForPresentOnGfxThread` or `Gfx.WaitForGfxCommandsFromMainThread` | Waiting on the render thread or the GPU. Draw calls, shaders, resolution. Use the **Frame Debugger** and the GPU module, not script changes. |
| `WaitForTargetFPS` | Idle, waiting for vsync or **Target Frame Rate**. Not a cost. |
| `Semaphore.WaitForSignal` | Waiting on another thread, usually rendering. |
| `GC.Collect` | The garbage collector running. See [allocations](#allocations). |
| `Loading.*`, `Preload` | Asset loading on the main thread. Load asynchronously, or earlier. |
| `FixedUpdate.PhysicsFixedUpdate` several times in one frame | Physics catching up after a slow frame: the [fixed timestep](../../physics/fixed-timestep.md) spiral. |

## Find the code

Switch to the **Hierarchy** view for the selected frame and sort by **Total** or **Self** milliseconds.

- **Total** includes everything the entry called. Follow the biggest total down the tree to find the area.
- **Self** is time spent in the entry itself. The entry with the biggest self time is the code to change.
- Script `Update` methods appear under `Update.ScriptRunBehaviourUpdate` as **ClassName.Update()**. `FixedUpdate`, `LateUpdate`, and coroutines have their own entries.
- **Calls** shows how many times something ran. A cheap method called 5,000 times is often the fix: call it less, not faster.

Without markers, the Hierarchy stops at your `Update` methods. Inside them is one block. Either add [markers](#custom-markers), or turn on **Deep Profile**, which instruments every method call. Deep profiling makes everything several times slower and distorts the numbers. Use it briefly to find the area, then add markers.

## Allocations

The **GC Alloc** column in the Hierarchy shows bytes allocated on the managed heap per entry per frame. Every allocation brings the next garbage collection closer, and a collection is a spike.

Sort by **GC Alloc** and aim for zero in steady gameplay. Common sources:

| Source | Fix |
| --- | --- |
| String building: `+`, `string.Format`, `ToString()` every frame | Update text on change. With TextMeshPro, `SetText` with arguments. |
| `GetComponents`, `FindObjectsByType`, `Physics.RaycastAll`, `OverlapSphere` | The overloads that fill a list or array you keep: `GetComponents(list)`, `OverlapSphereNonAlloc`. |
| LINQ in `Update` | Plain loops. |
| Lambdas that capture locals, created every frame | Cache the delegate in a field. |
| `new List<T>()` per call | Keep one in a field and `Clear()` it. |
| Boxing: value types passed as `object`, or as interfaces | Generic methods; avoid `object` parameters in hot code. |
| `foreach` over a collection through an interface | Usually fine on `List<T>`; an interface-typed collection may allocate its enumerator. |

**Player Settings → Configuration → Use Incremental GC**, on by default, spreads collection over several frames. It softens spikes; it does not remove the cost of allocating.

For the whole heap, rather than per frame, use the **Memory Profiler** package: snapshots, compared before and after a level, show what is still alive.

## Custom markers

A `ProfilerMarker` names a block of your code in the Profiler, in builds as well as the editor. Markers cost almost nothing, and nothing in a non-development build.

```csharp
using Unity.Profiling;
using UnityEngine;

public class HordeSimulation : MonoBehaviour
{
    static readonly ProfilerMarker s_Tick = new ProfilerMarker("Horde.Tick");
    static readonly ProfilerMarker s_Promote = new ProfilerMarker("Horde.Promote");
    static readonly ProfilerMarker s_MoveSimple = new ProfilerMarker("Horde.MoveSimple");

    void Update()
    {
        using (s_Tick.Auto())
        {
            using (s_Promote.Auto())
                PromoteAndDemote();

            using (s_MoveSimple.Auto())
                MoveSimpleAgents();
        }
    }

    void PromoteAndDemote() { /* ... */ }
    void MoveSimpleAgents() { /* ... */ }
}
```

- `Auto()` begins the marker and ends it when the `using` block exits, even through a `return` or an exception.
- Mark each system, not each method. Ten well-named markers per frame beat Deep Profile.
- Markers appear in the Timeline and the Hierarchy under the method that ran them, and in the **Profile Analyzer** package for comparing captures.

## Stats in the game

`ProfilerRecorder` reads Profiler counters from code, including in release builds for some counters. An overlay shows frame time and memory to playtesters without a Profiler attached.

```csharp
using Unity.Profiling;
using UnityEngine;

/// <summary>
/// A corner readout of main-thread time and GC memory. For playtests.
/// </summary>
public class StatsOverlay : MonoBehaviour
{
    ProfilerRecorder _mainThread;
    ProfilerRecorder _gcReserved;
    ProfilerRecorder _gcAllocInFrame;
    string _text = string.Empty;
    float _nextRefresh;

    void OnEnable()
    {
        _mainThread = ProfilerRecorder.StartNew(ProfilerCategory.Internal, "Main Thread", 15);
        _gcReserved = ProfilerRecorder.StartNew(ProfilerCategory.Memory, "GC Reserved Memory");
        _gcAllocInFrame = ProfilerRecorder.StartNew(ProfilerCategory.Memory, "GC Allocated In Frame");
    }

    void OnDisable()
    {
        _mainThread.Dispose();
        _gcReserved.Dispose();
        _gcAllocInFrame.Dispose();
    }

    void Update()
    {
        if (Time.unscaledTime < _nextRefresh)
            return;
        _nextRefresh = Time.unscaledTime + 0.25f; // four times a second: the string allocates

        double ms = Average(_mainThread) * 1e-6; // nanoseconds to milliseconds
        _text = "Main thread " + ms.ToString("F1") + " ms\n"
              + "GC reserved " + (_gcReserved.LastValue / (1024 * 1024)) + " MB\n"
              + "GC alloc/frame " + _gcAllocInFrame.LastValue + " B";
    }

    void OnGUI() => GUI.Label(new Rect(10, 10, 300, 60), _text);

    static double Average(ProfilerRecorder recorder)
    {
        int count = recorder.Count;
        if (count == 0)
            return 0;
        double sum = 0;
        for (int i = 0; i < count; i++)
            sum += recorder.GetSample(i).Value;
        return sum / count;
    }
}
```

- The `15` keeps the last 15 samples for averaging; a single frame's time jumps about.
- `ProfilerRecorderHandle.GetAvailable` lists every counter the running build offers. Not every counter exists in release builds.
- `OnGUI` keeps the overlay self-contained. A real HUD would use the game's [UI](../ui/choosing.md).

## Measure the fix

1. Capture the same scene, at the same spot, before and after. Save captures with the Profiler's **Save** button.
2. Compare medians, not single frames. The **Profile Analyzer** package loads two captures and compares every marker's distribution.
3. Check the fix on the target hardware. An improvement in the editor on a fast machine may be noise on a console.

!!! warning "Common pitfalls"

    Optimising from editor numbers. The editor adds its own cost and its own allocations. Profile a development build.

    Deep Profile left on. It slows everything and changes what looks expensive. Use markers.

    Optimising scripts when the main thread is waiting on `Gfx.WaitForPresent`. The GPU is the limit; script changes will not help.

    Judging by one frame. Frame times vary; compare averages or medians over many frames.

    `WaitForTargetFPS` read as a cost. It is the game idling until the next vsync.
