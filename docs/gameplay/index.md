# Gameplay and AI

Notes on behaviour you can feel in a character, and on the decision-making that drives it. Camera work that is really a gameplay choice lives here; the Unity implementation of one camera lives in the Unity section.

Planned topics:

- Steering and movement intent, separate from the integrator that carries the body.
- Behaviour trees, utility scoring, and when a state machine is the clearer model. A Unity 6 machine, and an enemy that uses it, are [state machines](../unity/architecture/state-machines.md) and [enemy behaviour](../unity/ai/enemy.md).
- Animation graphs as gameplay state, not as an art tool.
- Game feel: buffering, coyote time, acceleration curves, and hit-stop. Easing curves used for this are under [interpolation and easing](../maths/interpolation.md). A Unity 6 implementation of coyote time and jump buffering is [character movement](../unity/mechanics/character-movement.md). The same timers are on [Rigidbody movement](../unity/mechanics/rigidbody-movement.md) and the [2D platformer](../unity/mechanics/platformer-2d.md).
- Cameras as a gameplay tool. A concrete third-person rig is the [orbit camera](../unity/cameras/third-person.md). Using an object in reach is [interaction](../unity/mechanics/interaction.md).
