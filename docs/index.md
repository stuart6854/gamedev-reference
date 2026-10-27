# Game development reference

Personal notes for looking something up in the middle of a task. Pages are short on purpose. A formula is written out when it is easy to misremember, and a code sample keeps the assumptions next to the lines you would copy.

This repository is the foundation: theme, navigation, search, maths, diagrams, and deployment. Three pages are filled in so the tone and layout can be judged. The other sections are reserved, with a short index saying what will go there, and nothing else.

## How a page is laid out

The top bar is the subject list. Choosing one opens that subject in the sidebar. Search covers every page, and the icon at the top switches between light and dark. Code blocks have a copy button. Where the same idea exists in two forms, tabs sit on one block so only one form is on screen — C# and HLSL, or the legacy Input Manager and the new Input System.

Admonitions mark a pitfall or an API quirk that is easy to miss if it is only a sentence in a paragraph. Display maths is LaTeX. Diagrams are Mermaid.

## Conventions

- Points are column vectors. A transform applies on the left, so the product is read right to left. The graphics page spells this out, because the row-vector form is the same matrices transposed.
- Angles in Unity scripts are degrees. Angles inside a maths formula are radians unless the formula says otherwise.
- Spelling is British.

## Sample pages

- [Interpolation and easing](maths/interpolation.md) — lerp, remap, smoothstep, easing polynomials, and frame-rate-independent damping.
- [Coordinate spaces](graphics/coordinate-spaces.md) — object space through to the screen, with the matrices that get you there.
- [Third-person orbit camera](unity/orbit-camera.md) — a complete Unity camera, including collision pull-in and both input backends.

## Reserved sections

[Maths](maths/index.md), [graphics](graphics/index.md), and [Unity](unity/index.md) each start with the sample above. Still outlines only:

- [Physics](physics/index.md)
- [Gameplay and AI](gameplay/index.md)
- [Engine architecture](engine/index.md)
- [Optimisation](optimisation/index.md)
