# Async and await in games

`async` and `await` let a method pause until something finishes (a file loads, a web request returns, a second passes) and carry on from the same line, without blocking the thread or splitting the code into callbacks. In a game, the important questions are **which thread** the code resumes on, **when in the frame** it resumes, and **what happens if the object that started it is gone** by then. This page covers .NET first, then Unity's `Awaitable`.

## Async is not a thread

```csharp
async Task LoadLevelAsync(string name)
{
    ShowLoadingScreen();                          // main thread
    byte[] data = await File.ReadAllBytesAsync(path);   // returns to the caller here; no thread waits
    BuildLevel(data);                             // resumes later, on the main thread (see below)
    HideLoadingScreen();
}
```

- `await` on an operation that is not finished **returns** from the method, and registers the rest of it as a **continuation** to run when the operation completes.
- Nothing runs on another thread unless something explicitly puts it there (`Task.Run`, or an API that does I/O on the thread pool). `await` alone never makes code parallel.
- Where the continuation runs is decided by the **synchronisation context** captured at the `await`. A game's main thread installs one that queues continuations back onto the main thread, so code after `await` can touch engine objects safely.

## Tasks, ValueTasks, and async void

| Return type | Use for |
| --- | --- |
| `Task`, `Task<T>` | Most async methods. Can be awaited more than once and stored |
| `ValueTask`, `ValueTask<T>` | Hot methods that usually complete synchronously (a cache hit), to avoid allocating a `Task`. Await exactly once, and never store it |
| `async void` | Only event handlers that must have a `void` signature. Exceptions cannot be caught by the caller, and nobody can wait for it to finish |

Each `async` method that actually suspends allocates its state machine and a `Task`. That is fine for loading and network calls, which happen rarely. It is not fine every frame for hundreds of objects; see [allocations](performance/allocations.md#hidden-allocations).

## Cancellation

An operation started by an object must stop when the object goes away, or when the player leaves the screen that asked for it. Pass a `CancellationToken` through every async method:

```csharp
async Task<Texture> LoadAvatarAsync(string url, CancellationToken ct)
{
    byte[] bytes = await http.GetByteArrayAsync(url, ct);
    ct.ThrowIfCancellationRequested();                    // the await may have completed just before cancel
    return DecodeTexture(bytes);
}

// The screen owns a source and cancels it when it closes.
readonly CancellationTokenSource _closing = new();

async void OnOpened()                 // an event handler: async void is acceptable here
{
    try
    {
        avatar.Texture = await LoadAvatarAsync(url, _closing.Token);
    }
    catch (OperationCanceledException) { }             // closed while loading: nothing to do
    catch (Exception e) { Log.Error(e); }              // anything else must be logged, or it vanishes
}

void OnClosed() => _closing.Cancel();
```

- Cancelling throws `OperationCanceledException` from the awaited call. Catch it where the operation was started, and treat it as normal.
- `CancellationTokenSource.CreateLinkedTokenSource(a, b)` cancels when either the screen closes **or** the whole game is shutting down.
- After every `await`, the world may have changed. Check that what the method is about to touch still exists, even without cancellation.

## Resuming on the main thread

A custom engine has to provide the synchronisation context itself. It queues continuations and runs them once per frame, at a known point:

```csharp
public sealed class FrameSynchronizationContext : SynchronizationContext
{
    readonly ConcurrentQueue<(SendOrPostCallback Callback, object? State)> _queue = new();
    readonly int _mainThreadId = Environment.CurrentManagedThreadId;

    public override void Post(SendOrPostCallback d, object? state) => _queue.Enqueue((d, state));

    public override void Send(SendOrPostCallback d, object? state)
    {
        if (Environment.CurrentManagedThreadId == _mainThreadId) d(state);
        else throw new InvalidOperationException("Send from a background thread would deadlock; use Post.");
    }

    // Called by the game loop once per frame, on the main thread.
    public void RunPending()
    {
        int count = _queue.Count;                     // only what was queued before this call
        for (int i = 0; i < count && _queue.TryDequeue(out var item); i++)
            item.Callback(item.State);
    }
}

// At start-up, on the main thread:
var context = new FrameSynchronizationContext();
SynchronizationContext.SetSynchronizationContext(context);

// In the frame loop:
context.RunPending();          // e.g. after input, before gameplay update
```

- Pick **where** in the frame continuations run, and keep it fixed: code after an `await` then always runs at the same point relative to the [frame phases](../engine/patterns/frame.md#phases), not in the middle of physics.
- Running only the items queued **before** the call stops a continuation that immediately awaits again from looping forever within one frame.
- `ConfigureAwait(false)` on an `await` skips the context, and the continuation runs on whatever thread completed the operation. Use it in library code that never touches engine objects; never in gameplay code.

### Awaiting frames and game time

Games need to wait in frames and in **game** time, which pauses and slows down. `Task.Delay` uses real time, keeps running when the game is paused, and resumes on a timer thread's schedule. Provide frame-based waits instead:

```csharp
public static class Frame
{
    static List<TaskCompletionSource> _next = new(), _swap = new();

    public static Task Next()
    {
        var tcs = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        _next.Add(tcs);
        return tcs.Task;
    }

    // Called once per frame by the game loop, before FrameSynchronizationContext.RunPending.
    public static void Tick()
    {
        (_next, _swap) = (_swap, _next);
        foreach (var tcs in _swap) tcs.SetResult();     // continuations are posted to the context, not run here
        _swap.Clear();
    }
}

public static async Task Seconds(float seconds, GameClock clock, CancellationToken ct)
{
    double end = clock.Time + seconds;
    while (clock.Time < end)
    {
        ct.ThrowIfCancellationRequested();
        await Frame.Next();
    }
}
```

`RunContinuationsAsynchronously` makes each waiting method resume through the synchronisation context, at its fixed point in the frame, rather than inside `Tick`. This allocates a `TaskCompletionSource` per wait, which is fine for a few hundred waits. For thousands per frame, implement `IValueTaskSource` with pooled sources, or use a library that does (UniTask in Unity).

## Work on other threads

```csharp
async Task GenerateChunkAsync(ChunkCoord coord, CancellationToken ct)
{
    // Heavy, pure computation on the thread pool. Only plain data goes in and out.
    MeshData data = await Task.Run(() => ChunkGenerator.Build(coord, seed), ct);

    // Back on the main thread (the captured context), safe to touch engine objects.
    if (ct.IsCancellationRequested) return;
    world.AddChunk(coord, CreateMesh(data));
}
```

- Code inside `Task.Run` must not touch engine objects (entities, meshes, scene graph); most engines only allow that on the main thread. Give it plain data, and return plain data.
- For many small parallel tasks inside a frame, use the engine's [job system](../engine/jobs/index.md), not `Task.Run`: the thread pool knows nothing about frame deadlines.

## Pitfalls

- **`.Result` and `.Wait()` on the main thread deadlock.** The task's continuation is queued for the main thread, which is blocked waiting for the task. Await instead, all the way up.
- **Fire-and-forget loses exceptions.** A `Task` nobody awaits swallows its exception (it is only reported, if at all, when the task is collected). Wrap fire-and-forget calls in a helper that awaits and logs.
- **The object is gone when the method resumes.** Every `await` is a point where the scene can change. Cancel with the owner's lifetime, and check before touching.
- **Ordering between awaits** is not guaranteed between different operations. Two loads started in order can finish in either order. If order matters, await them in sequence or use `Task.WhenAll` and process results in the original order.

## In Unity

Unity's main thread has a `SynchronizationContext` (`UnitySynchronizationContext`), so `await` on a `Task` resumes on the main thread, during the frame's update. Unity 6 adds **`Awaitable`**, an awaitable type designed for games:

| `Awaitable` method | Resumes |
| --- | --- |
| `Awaitable.NextFrameAsync(ct)` | On the next frame |
| `Awaitable.WaitForSecondsAsync(seconds, ct)` | After the given time |
| `Awaitable.FixedUpdateAsync(ct)` | At the next fixed update |
| `Awaitable.EndOfFrameAsync(ct)` | After all of Unity's subsystems have run this frame |
| `Awaitable.BackgroundThreadAsync()` | On a thread-pool thread |
| `Awaitable.MainThreadAsync()` | On the main thread |
| `Awaitable.FromAsyncOperation(op, ct)` | When an `AsyncOperation` (scene load, asset bundle) completes |

```csharp
public sealed class Turret : MonoBehaviour
{
    async void Start()
    {
        try
        {
            while (true)
            {
                FireAtNearest();
                await Awaitable.WaitForSecondsAsync(cooldown, destroyCancellationToken);
            }
        }
        catch (OperationCanceledException) { }          // the turret was destroyed
    }

    async Awaitable<Mesh> BuildMeshAsync(TerrainData data)
    {
        await Awaitable.BackgroundThreadAsync();
        MeshData built = Generate(data);                // plain data only: no Unity objects here
        await Awaitable.MainThreadAsync();
        return ToMesh(built);                           // back on the main thread for the Mesh API
    }
}
```

- **`destroyCancellationToken`** (on every `MonoBehaviour`) is cancelled when the object is destroyed. Pass it to every wait the object starts. `Application.exitCancellationToken` is cancelled when the application (or Play Mode) exits.
- **Plain `Task`s keep running after you leave Play Mode** in the editor, because the editor process keeps going. A loop with `Task.Delay` keeps touching destroyed objects until the domain reloads. Cancel with the tokens above.
- **`Awaitable` instances are pooled.** Await each one exactly once, and do not keep it after awaiting; awaiting it again is undefined.
- Unity objects (`GameObject`, `Transform`, `Mesh`) can only be used on the main thread. After `BackgroundThreadAsync`, switch back with `MainThreadAsync` before touching them.

### Awaitable or coroutine

| | Coroutine | `async Awaitable` |
| --- | --- | --- |
| Returns a value | No | Yes (`Awaitable<T>`) |
| Error handling | Exceptions stop the coroutine and are logged | `try`/`catch` around awaits |
| Stops with its object | When the object is destroyed or its GameObject is deactivated (not when only the component is disabled) | Only if you pass `destroyCancellationToken`, which covers destruction; deactivation does not stop it |
| Composes with .NET async APIs (HTTP, file I/O) | No | Yes |
| Switching threads | No | `BackgroundThreadAsync` / `MainThreadAsync` |

Coroutines remain simpler for short behaviour sequences on one object that should stop when it does. Use `Awaitable` for anything that returns a result, needs error handling, or mixes with other async code. **UniTask** (a third-party package) provides allocation-free async with more features, and is widely used in Unity projects that rely heavily on async.
