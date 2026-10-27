# Gameplay and AI

Notes on behaviour you can feel in a character, and on the decision-making that drives it. Camera work that is really a gameplay choice lives here; the Unity implementation of one camera lives in the Unity section.

Planned topics:

- Steering and movement intent, separate from the integrator that carries the body.
- Behaviour trees, utility scoring, and when a state machine is the clearer model.
- Animation graphs as gameplay state, not as an art tool.
- Game feel: buffering, coyote time, acceleration curves, and hit-stop. Easing curves used for this are under [interpolation and easing](../maths/interpolation.md).
- Cameras as a gameplay tool. A concrete third-person rig is the [orbit camera](../unity/orbit-camera.md).
