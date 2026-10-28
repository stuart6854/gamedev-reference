# Architecture

How Unity objects talk, the assets and machines they share, and how instances are reused. This is the Unity side.

Written:

- [MonoBehaviour lifecycle](lifecycle.md) — callback order, what each callback may assume, spawning, disabling, `Destroy`, and execution order.
- [Bootstrapping and services](services.md) — singletons compared, a systems prefab spawned before the first scene wakes, and a small service locator.
- [Event systems](events.md) — C# events, `UnityEvent`, a typed static bus, and ScriptableObject channels.
- [Shared variables](variables.md) — a `ScriptableObject` value, a constant-or-variable reference, and a runtime set.
- [State machines](state-machines.md) — enum, class states, predicate transitions, a nested machine, and a pause stack.
- [Object pooling](pooling.md) — `ObjectPool<T>`, a prefab registry, and effects that return themselves.
