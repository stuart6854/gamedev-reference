# Content pipeline

How assets get from the tools artists use to the bytes the game loads. Source files (FBX, PSD, WAV) are imported into the engine's own editable formats, then **cooked** into compact, platform-specific runtime data, and packed into archives for shipping.

```mermaid
flowchart LR
    S["Source<br/>FBX, PSD, WAV"] -- import --> I["Intermediate<br/>editable, with metadata"]
    I -- "cook (per platform)" --> C["Cooked<br/>runtime format"]
    C -- package --> P["Archives<br/>compressed, ordered"]
    P --> G[Game]
```

- [Import and cook](import-cook.md) — what each stage does, per asset type, and why authoring data and runtime data are different formats.
- [Dependencies and incremental builds](incremental.md) — build keys, dependency tracking, a derived data cache, and why determinism matters.
- [Packaging](packaging.md) — archives, compression, ordering for loading, patches, and DLC.
- [Editor workflow](editor-workflow.md) — asset ids in metadata files, re-importing on change, validation, and keeping references intact when files move.

The [serialisation](../serialisation/index.md) pages cover the formats themselves, and [resources and handles](../patterns/resources.md) covers loading cooked data at run time.
