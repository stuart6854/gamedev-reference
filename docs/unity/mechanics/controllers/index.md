# Controllers

Four ways to move a body. Dash, wall run, ledge climb, and a grappling hook are not a fifth body. They stay on the [roadmap](../../../roadmap.md#movement) as extras on top of one of these. Box selection for several units is on that list as well.

## Which controller

| Page | Body | When it moves | Use it when |
| --- | --- | --- | --- |
| [Character movement](../character-movement.md) | `CharacterController` | `Update` | Slopes, steps, and jumps should be reliable, and the body does not need to push rigidbodies. |
| [Rigidbody movement](../rigidbody-movement.md) | `Rigidbody` | Input in `Update`, motion in `FixedUpdate` | The same first or third person moves, but the capsule should shove props and take collision impulses. |
| [Top-down movement](../top-down.md) | `Rigidbody`, or `Rigidbody2D` | Input in `Update`, motion in `FixedUpdate` | Move and aim are different directions. Twin-stick, mouse aim, or an isometric camera. No jump. |
| [2D platformer](../platformer-2d.md) | `Rigidbody2D` | Input in `Update`, motion in `FixedUpdate` | Side view, tile colliders, a variable jump, and optional walls. |

The kinematic capsule never uses `linearVelocity`. Unity 6 renamed the physics speed and drag: `Rigidbody.linearVelocity` and `linearDamping`, and the same two names on `Rigidbody2D`. `velocity` and `drag` are the obsolete names.
