# Unity

Notes specific to Unity: lifecycle, input, queries, and the places where Unity’s defaults differ from the textbook formula. Shared maths and graphics stay in their own sections and are linked from here.

Planned topics:

- `MonoBehaviour` lifecycle, script order, and what is safe in `Update` versus `LateUpdate`.
- The legacy Input Manager and the Input System, including projects that have both enabled.
- Physics queries: ray, sphere, and shape casts, layer masks, and triggers.
- Cameras and Cinemachine-shaped problems written as plain scripts. Written: [Third-person orbit camera](orbit-camera.md).
- Data and loading: `ScriptableObject`, addressables, and what belongs out of the scene.

The orbit camera is also the worked example for [exponential damping](../maths/interpolation.md#frame-rate-independent-damping).
