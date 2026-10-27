# Optimisation

Notes on finding the expensive thing and fixing that thing. A page here should start from a measurement, then name the mechanism, then the change.

Planned topics:

- How to tell CPU from GPU, and main thread from a worker, before changing code.
- Cache behaviour and data layout, at the scale of a tight gameplay loop.
- Draw calls, batching, overdraw, and resolution.
- Managed allocations and the garbage collector in C#, especially per-frame collections that do not show up as a spike until a hitch.
- Level of detail, culling, and what each one does not save.

Nothing in this section is written yet. The navigation entry is the outline above.
