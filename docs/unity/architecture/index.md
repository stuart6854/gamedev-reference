# Architecture

How Unity objects talk, and, later, the assets and machines they share. This is the Unity side. Notes that are not tied to one engine stay under [Engine architecture](../../engine/index.md).

Written:

- [Event systems](events.md) — C# events, `UnityEvent`, a typed static bus, and ScriptableObject channels.
- [Shared variables](variables.md) — a `ScriptableObject` value, a constant-or-variable reference, and a runtime set.
- [State machines](state-machines.md) — enum, class states, predicate transitions, a nested machine, and a pause stack.

Object pooling is still on the [roadmap](../../roadmap.md#architecture).
