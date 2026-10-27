# Engine architecture

Notes on how a game is structured once it is larger than a single scene of components. Unity-specific versions of these ideas stay in the Unity section.

Planned topics:

- The frame: input, simulation, animation, render submission, and which of those may stall.
- What an entity is in this project, and which data is allowed to live on it.
- Jobs, batches, and the layout consequences of writing them.
- Serialisation, content pipelines, and the difference between authoring data and runtime data.
- Tools that edit the same data the game reads.

Nothing in this section is written yet. The navigation entry is the outline above.
