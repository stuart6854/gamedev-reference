# Architecture

How Unity objects talk, the assets and machines they share, and how instances are reused. This is the Unity side. Notes that are not tied to one engine stay under [Engine architecture](../../engine/index.md).

Written:

- [Event systems](events.md) — C# events, `UnityEvent`, a typed static bus, and ScriptableObject channels.
- [Shared variables](variables.md) — a `ScriptableObject` value, a constant-or-variable reference, and a runtime set.
- [State machines](state-machines.md) — enum, class states, predicate transitions, a nested machine, and a pause stack.
- [Object pooling](pooling.md) — `ObjectPool<T>`, a prefab registry, and effects that return themselves.
