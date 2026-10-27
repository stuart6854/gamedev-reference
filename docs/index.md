# Game development reference

Personal notes for looking something up in the middle of a task. Pages are short on purpose. A formula is written out when it is easy to misremember, and a code sample keeps the assumptions next to the lines you would copy.

This repository is the foundation: theme, navigation, search, maths, diagrams, and deployment. A handful of pages are filled in so the tone and layout can be judged. The other sections are reserved, with a short index saying what will go there. Topics that still need a page are on the [roadmap](roadmap.md).

## How a page is laid out

The top bar is the subject list. Choosing one opens that subject in the sidebar. Search covers every page, and the icon at the top switches between light and dark. Code blocks have a copy button. Where the same idea exists in two forms, tabs sit on one block so only one form is on screen — C# and HLSL, or the legacy Input Manager and the new Input System.

Admonitions mark a pitfall or an API quirk that is easy to miss if it is only a sentence in a paragraph. Display maths is LaTeX. Diagrams are Mermaid. An engine page names the versions it targets as pills under the title, from `engine`, `version`, and `package` in the frontmatter. A Unity page is plain C#, and adds an official-package variant when one shortens the setup.

## Conventions

- Points are column vectors. A transform applies on the left, so the product is read right to left. The graphics page spells this out, because the row-vector form is the same matrices transposed.
- Angles in Unity scripts are degrees. Angles inside a maths formula are radians unless the formula says otherwise.
- Spelling is British.

## Sample pages

- [Interpolation and easing](maths/interpolation.md) — lerp, remap, smoothstep, easing polynomials, and frame-rate-independent damping.
- [Coordinate spaces](graphics/coordinate-spaces.md) — object space through to the screen, with the matrices that get you there.
- [Third-person orbit camera](unity/orbit-camera.md) — a Unity 6 camera as a plain script and as Cinemachine 3, including collision pull-in.
- [Character movement](unity/mechanics/character-movement.md) — a Unity 6 CharacterController with walk, run, jump, coyote time, and slopes.
- [Rigidbody movement](unity/mechanics/rigidbody-movement.md) — the same moves on a dynamic Rigidbody, with acceleration and air control.
- [Top-down movement](unity/mechanics/top-down.md) — twin-stick aim on a plane, in 3D or with a Rigidbody2D.
- [2D platformer](unity/mechanics/platformer-2d.md) — a Rigidbody2D jump with coyote time, an apex, and optional walls.
- [Interaction](unity/mechanics/interaction.md) — focus, prompt, and hold-to-interact for a first-person cast or a third-person overlap.
- [Health, damage, and stats](unity/systems/health.md) — a Unity 6 health pool, hitbox pipeline, and stat modifiers.
- [Weapons](unity/combat/weapons.md) — a Unity 6 firearm: fire modes, hitscan and pooled projectiles, ammo, and recoil.
- [Event systems](unity/architecture/events.md) — C# events, UnityEvent, a typed bus, and ScriptableObject channels.
- [Shared variables](unity/architecture/variables.md) — ScriptableObject floats, a constant-or-variable reference, and a runtime set.
- [State machines](unity/architecture/state-machines.md) — idle, move, jump, and fall as predicate transitions, plus a pause stack.
- [Enemy behaviour](unity/ai/enemy.md) — a Unity 6 NavMeshAgent loop: patrol, chase, attack, search, and flee.
- [Highlight and outline](unity/rendering/highlight-outline.md) — a Unity 6 URP outline, from an inverted hull to a fresnel highlight.
- [Inventory](unity/systems/inventory/index.md) — a Unity 6 item model, list, grid, slots and hotbar, weight, and equipment.

## Reserved sections

[Maths](maths/index.md), [graphics](graphics/index.md), and [Unity](unity/index.md) each start with the sample above. Still outlines only:

- [Physics](physics/index.md)
- [Gameplay and AI](gameplay/index.md)
- [Engine architecture](engine/index.md)
- [Optimisation](optimisation/index.md)
