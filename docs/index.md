# Game development reference

Personal notes for looking something up in the middle of a task. A formula is written out when it is easy to misremember, and a code sample keeps its assumptions next to the lines you would copy.

Engine-agnostic pages explain an idea once. Engine pages are complete, copyable implementations, so they run longer: setup steps, the scripts, and the ways each one fails. Topics that still need a page are on the [roadmap](roadmap.md).

## How a page is laid out

The top bar is the subject list. Choosing one opens that subject in the sidebar. Search covers every page, and the icon at the top switches between light and dark. Code blocks have a copy button. Where the same idea exists in two forms, tabs sit on one block so only one form is on screen — C# and HLSL, or the legacy Input Manager and the new Input System.

Admonitions mark a pitfall or an API quirk that is easy to miss if it is only a sentence in a paragraph. Display maths is LaTeX. Diagrams are Mermaid. An engine page names the versions it targets as pills under the title, from `engine`, `version`, and `package` in the frontmatter. A Unity page is plain C#, and adds an official-package variant when one shortens the setup.

## Conventions

- Points are column vectors. A transform applies on the left, so the product is read right to left. The graphics page spells this out, because the row-vector form is the same matrices transposed.
- Angles in Unity scripts are degrees. Angles inside a maths formula are radians unless the formula says otherwise.
- Spelling is British.

## Sections

Each section's index lists what is written there.

- [Maths](maths/index.md) — interpolation, easing, and frame-rate-independent damping so far.
- [Data structures](data-structures/index.md) — containers the standard libraries leave out, sparse sets, handle tables, and ring buffers so far.
- [Graphics](graphics/index.md) — the coordinate spaces from object space to the screen.
- [Physics](physics/index.md) — the fixed timestep and integrators.
- [Unity](unity/index.md) — the bulk of the site: cameras, controllers, systems, architecture, AI, combat, and rendering for Unity 6.

Gameplay and AI, engine architecture, and optimisation join this list when their first page is written.
