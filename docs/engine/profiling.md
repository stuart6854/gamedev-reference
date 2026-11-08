# Profiler instrumentation

A sampling profiler shows where time goes on average. A game needs to know why **one frame** took 25 ms when the rest took 12. That needs **instrumentation**: the engine records when named sections of code start and end, on every thread, every frame, and a viewer shows them on a timeline. This page covers building that into an engine, and using Tracy, the most common open-source profiler for it.

## Scoped zones

```cpp
void PhysicsWorld::step(float dt)
{
    PROFILE_SCOPE("Physics.Step");
    {
        PROFILE_SCOPE("Broadphase");
        update_broadphase();
    }
    {
        PROFILE_SCOPE("Solve");
        solve(dt);
    }
}
```

```cpp
struct ProfileScope {
    const ZoneInfo* info;                                  // static: name, file, line
    explicit ProfileScope(const ZoneInfo* i) : info(i) { profiler::begin(info, now_ticks()); }
    ~ProfileScope() { profiler::end(now_ticks()); }
};

#define PROFILE_SCOPE(name)                                                         \
    static const ZoneInfo CONCAT(zone_info_, __LINE__) { name, __FILE__, __LINE__ };  \
    ProfileScope CONCAT(zone_, __LINE__)(&CONCAT(zone_info_, __LINE__))
```

- The name, file, and line live in a **static** struct, created once. Each event records only a pointer to it and a timestamp, so recording is a few stores.
- **Nesting** comes for free from scopes: zones on one thread form a stack, and the viewer draws children inside their parents.
- Name zones by what they do (`Physics.Step`, `Render.Shadows`), not by function signatures, and put them at the level someone would look for: systems, passes, and expensive loops. A zone around a function called a million times per frame costs more than the function.

## Recording without locks

Each thread writes events into **its own** buffer, so recording never contends:

```text
ThreadBuffer { events[], write_index, thread_id, thread_name }

begin(info, t): buffer.events[write++] = { Begin, info, t }
end(t):         buffer.events[write++] = { End, t }

collector thread, every few milliseconds:
    for each thread buffer: take the events written since last time (atomic index read)
    send them to the viewer (over a socket) or keep them in memory for a capture
```

- Use a [ring buffer](../data-structures/ring-buffer.md) per thread, written by its thread and read by the collector. If the collector falls behind and the ring fills, drop events and count the drops, rather than blocking the game.
- **Name threads** (`Main`, `Render`, `Worker 3`, `Audio`) when they start, so the timeline is readable.
- Mark **frame boundaries** with an event at the start of each frame. The viewer uses them to split the timeline into frames and to show per-frame statistics.

## Timestamps

| Source | Resolution | Notes |
| --- | --- | --- |
| `QueryPerformanceCounter` (Windows), `clock_gettime(CLOCK_MONOTONIC)` (Linux, consoles) | Typically under 100 ns | Safe; calls into the OS, though cheaply |
| `rdtsc` (x86 time stamp counter) | One CPU cycle | Very cheap. Constant rate on all current CPUs, but must be converted to time by calibrating against a clock at start-up |
| `std::chrono::steady_clock` | Varies | Portable; wraps one of the above |

Profilers use the cheapest reliable counter (Tracy uses the time stamp counter where it can), and convert ticks to time in the viewer, not at record time.

## GPU timing

CPU zones show when commands were **recorded**. To know how long the GPU took for each pass, write GPU timestamps into the command stream:

```text
begin_gpu_zone(cmd, name):  write a timestamp query at the start of the pass
end_gpu_zone(cmd):          write a timestamp query at the end

a few frames later (when the GPU has finished, see frames in flight):
    read back the query results
    duration = (end - begin) / timestamp_frequency
```

- Read results back after the frame's fence has signalled, never by waiting for them; that would stall the CPU on the GPU.
- Put GPU zones around each [render graph](rendering/render-graph.md) pass, with the pass's name. The same names in CPU and GPU timelines make the two easy to line up.
- GPU and CPU clocks differ. Calibrate the offset between them periodically (both APIs can return a CPU and GPU timestamp pair) so GPU zones appear in the right place on the shared timeline.
- Tile-based mobile GPUs and asynchronous queues make per-pass timings less exact: work overlaps, and timestamps measure when the GPU reached a point, not how long each pass alone took.

## Memory tracking

Allocation counters per category answer "where did 300 MB go?":

```text
alloc(size, category):
    p = underlying_alloc(size)
    stats[category].current += size;  stats[category].peak = max(peak, current)
    if detailed tracking: record { p, size, category, callstack hash } in a table
    profiler::event(Alloc, p, size)
    return p
```

- **Categories** (`Textures`, `Meshes`, `Audio`, `Physics`, `UI`, `Scripts`) come from a tag pushed around code (a scoped `MemoryCategory` like a profile zone), or from which allocator was used.
- **Peaks** matter more than averages on consoles with fixed memory. Report each category's high-water mark per level.
- **Leaks**: at shutdown, anything still in the detailed table is a leak; print it with its call stack. Recording call stacks for every allocation is slow, so turn it on per category when hunting.

## Counters and plots

Not everything is a span of time. Plot values once per frame:

```cpp
PROFILE_PLOT("Draw calls", draw_count);
PROFILE_PLOT("Entities", world.entity_count());
PROFILE_PLOT("Streaming MB/s", streaming.bandwidth());
```

A spike in a frame's timeline next to a spike in "entities spawned" or "bytes uploaded" usually explains itself.

## Using Tracy

[Tracy](https://github.com/wolfpld/tracy) provides all of this: a client library you compile into the engine, and a viewer that connects over the network, live or to a saved capture.

```cpp
#include <tracy/Tracy.hpp>

void update()
{
    ZoneScoped;                              // named after the function
    {
        ZoneScopedN("AI.Think");             // explicit name
        ZoneText(agent.name.c_str(), agent.name.size());   // per-instance detail
        think();
    }
    TracyPlot("Agents", (int64_t)agents.size());
}

// Once per frame, at the end of the main loop:
FrameMark;

// Memory: call from your allocator.
TracyAlloc(ptr, size);
TracyFree(ptr);

// Locks: replace std::mutex to see contention.
TracyLockable(std::mutex, m_lock);

// GPU (D3D12 shown; TracyVkZone/TracyVkCollect for Vulkan)
TracyD3D12Zone(gpu_ctx, cmd_list, "Shadows");
TracyD3D12Collect(gpu_ctx);                  // once per frame, to read back timestamps
```

- Define `TRACY_ENABLE` in builds that should profile. Without it, every macro compiles to nothing.
- Tracy can also capture **context switches** and call-stack samples on supported platforms, which shows when a thread was waiting rather than working.
- Wrap Tracy behind your own `PROFILE_*` macros if you might want another backend (a console's native profiler, Superluminal's API, or your own in-game view).

## Catching spikes

The frame you need is the one that was slow, and it is usually gone before anyone starts a capture:

- **Rolling capture**: keep the last few seconds of events in memory at all times. When a frame exceeds its budget (or on a hotkey), save the buffer to a file. Testers can then send captures of spikes they hit, without a profiler connected.
- **Budgets per zone**: set expected maximum times for key zones (physics 3 ms, AI 2 ms), and log or capture when they are exceeded in test builds.
- **Show it in the game**: a frame-time graph in the [debug overlay](debug-tools.md#the-in-game-console-and-overlays) makes spikes visible to everyone, not just whoever has the profiler open.

## Overhead

A zone costs tens of nanoseconds with Tracy. That is negligible around a system update, and significant around something called hundreds of thousands of times per frame. Keep zones coarse by default, add fine ones temporarily while investigating, and compile all instrumentation out of shipping builds.
