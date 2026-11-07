# Serialisation

Turning objects into bytes and back: for save games, scene and prefab files, cooked runtime data, network messages, and undo. The same data passes through several of these, so it pays to describe each type once and drive every format from that description.

- [Reflection](reflection.md) — describing a type's fields once, and using the description for every format, editor UI, and diffing.
- [Formats](formats.md) — text for authoring, binary for runtime, writing and reading binary safely, and file headers.
- [Versioning](versioning.md) — reading data written by older versions: version numbers and migrations, tagged fields, renames, and testing with old files.
- [References and load-in-place](references.md) — saving references as ids, resolving them on load, and binary blobs that are used straight from memory without parsing.

The [content pipeline](../content/index.md) pages cover how authored data becomes the runtime data these formats describe.
