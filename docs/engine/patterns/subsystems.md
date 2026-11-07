# Subsystems and messaging

An engine is a set of subsystems (rendering, audio, physics, input, assets, scripting) that depend on each other. This page covers creating and destroying them in a safe order, giving each one the others it needs, and letting them notify each other without knowing who is listening.

## Lifetime and order

```text
Subsystem {
    name
    depends_on[]            // names of subsystems that must start first
    init(context)
    shutdown()
}

start(subsystems):
    order = topological_sort(subsystems, by depends_on)     // a cycle is a start-up error
    for s in order: s.init(context)
    started = order

stop():
    for s in reverse(started): s.shutdown()
```

Shut down in **reverse** order. The renderer started after the window, so it must stop before the window does; a subsystem must never outlive anything it uses.

If `init` fails part way through, shut down only the subsystems already started, in reverse, and report which one failed. Keep the `started` list for exactly this.

### Two-phase start-up

Some subsystems refer to each other: the audio system wants the asset system to load sounds, and the asset system wants the audio system to decode them. Split start-up:

1. **Create** every subsystem. Constructors only allocate; they do not call each other.
2. **Init** in dependency order. Each subsystem may now look the others up and register with them.
3. **Start** (optional): begin threads, open devices, load first assets.

Shutdown runs the same phases backwards: stop threads first, then shut down, then destroy. Most "crash on exit" bugs are a thread still running into a subsystem that was already destroyed.

### Avoid static singletons

In C++, global objects in different files are constructed in an unspecified order (the "static initialisation order fiasco") and destroyed in reverse of whatever that was. A static `Renderer` that uses a static `Log` can run before the log exists. Own subsystems from one `Engine` object with an explicit order, and give globals nothing to do at construction time.

## Getting a subsystem

### Passing context

Pass each system what it uses:

```text
EngineContext {
    assets, audio, input, physics, renderer, clock, log
}

PlayerSystem.init(ctx):
    self.input = ctx.input
    self.audio = ctx.audio
```

What a system depends on is visible in its code, a test can pass fakes, and there is no hidden global. The cost is that the context object grows, and every new dependency is an edit.

### Service locator

```text
Services {
    table: type -> instance
}
register(Audio, OpenALAudio())
get(Audio) -> instance or NullAudio
```

Any code can reach any service, which is convenient and hides dependencies. Use it for **cross-cutting** services that nearly everything uses and that are safe to replace: logging, profiling, debug drawing. Return a **null service** (one that does nothing) when nothing is registered, so a headless server or a test can run code that plays sounds without an audio device.

| | Passing context | Service locator |
| --- | --- | --- |
| Dependencies visible | Yes | No |
| Testing | Pass fakes | Register fakes globally, and remember to reset them |
| Adding a dependency | Edit the context and its callers | One `get` call |
| Good for | Gameplay systems and most of the engine | Logging, profiling, debug drawing |

## Messaging

Subsystems often need to react to each other without depending on each other: the audio system plays a sound when something explodes, the achievement system counts kills, the UI updates on damage. Events decouple the sender from the receivers.

### Immediate dispatch

```text
Event<T> { listeners[] }

subscribe(event, callback) -> Subscription
publish(event, value):
    for l in copy of event.listeners: l(value)
```

The handlers run inside `publish`, before it returns. It is simple, and the sender sees every effect straight away. The problems all come from that:

- **Re-entrancy.** A handler publishes another event, whose handler publishes the first one again. Deep or infinite recursion, with the original handler half finished.
- **Changing the listener list during dispatch.** A handler unsubscribes itself or another listener. Iterate over a copy, as above, or mark removed listeners and compact the list after dispatch.
- **Order.** Listeners run in subscription order, which nobody chose on purpose. If one listener's result matters to another, the design needs a phase, not an event.
- **Cost in the wrong place.** A physics callback that triggers UI updates, audio, and particles makes the physics step slow, and the profile blames physics.

### Queued events

```text
EventQueue<T> {
    writing[]              // this frame's events
    reading[]              // last frame's events
}

send(queue, value) = queue.writing.append(value)

swap(queue):              // once per frame, at a fixed point
    queue.reading = queue.writing
    queue.writing = []

AudioSystem.update():
    for e in explosions.reading: play_sound(e.position)
```

- The sender never runs anyone else's code. Each reader processes events in its own phase, at its own cost.
- Events sent during the frame are read **next** frame, after the swap. Readers can never miss one, whatever order systems run in, at the price of one frame's delay.
- Several systems can read the same queue. Nothing is consumed, so no reader steals events from another.
- Queues are easy to record and replay, which helps debugging and replays.

Use immediate dispatch for rare, local notifications where the sender needs the result straight away, such as asking whether an action is allowed. Use queues for gameplay events with several readers, such as damage, deaths, pick-ups, and noises.

### Subscription lifetime

A listener that is destroyed without unsubscribing leaves a callback pointing at freed memory. In C++ that crashes; in C# the event keeps the dead object alive (a leak) and keeps calling it.

```text
Subscription { event, id }

subscribe(event, callback):
    id = next_id++
    event.listeners.append({ id, callback })
    return Subscription { event, id }

on destroy of Subscription:            // RAII in C++, IDisposable in C#
    remove listener with id from event
```

Make the subscription an object the listener owns. When the listener is destroyed, its subscriptions are destroyed with it, and unsubscribing cannot be forgotten. With an [ECS](../ecs/index.md), prefer queued events that systems read over callbacks stored per entity: there is nothing to unsubscribe.
