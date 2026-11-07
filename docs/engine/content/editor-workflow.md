# Editor workflow

How the pipeline looks from inside the editor: every asset has a stable id, changes on disk are noticed and imported, problems are reported where people will see them, and moving or renaming files never breaks the references to them.

## Asset ids and metadata files

Every asset gets an id when it is first imported: a random GUID, stored in a **metadata file** next to the source file, along with its [import settings](import-cook.md#import-settings).

```text
Assets/Props/crate.png
Assets/Props/crate.png.meta      id: 4f1c9a2e-..., importer settings
```

Everything else refers to the asset by that id: materials, prefabs, scenes, and the cooked data. The path is only where the file happens to be.

- **Moving or renaming** a file in the editor moves its metadata file with it. The id is unchanged, so nothing that references it needs updating.
- Moving a file **outside the editor** (in a file browser, or with `git mv` without the metadata file) separates them. The editor then sees a deleted asset and a new one with a new id, and every reference to the old id breaks. Detect this: when a new file appears at the same time as an identical file disappears, offer to keep the old id.
- **Commit metadata files** with their assets. A missing metadata file means each person's editor generates a different id for the same asset, and references made on one machine break on every other. Unity's `.meta` files cause exactly these problems when they are not committed.

The editor keeps an index from id to path, built by scanning the metadata files at start-up and kept up to date as files change, so looking up an asset by id is instant.

## Noticing changes

```text
file watcher -> changed paths -> debounce -> re-import -> re-cook for the editor -> hot reload
```

- Watch the asset folders for changes (`ReadDirectoryChangesW` on Windows, inotify on Linux, FSEvents on macOS).
- **Debounce**: wait until a file has been unchanged for a short time (about 100 to 500 ms) before importing it. Tools write files in several steps, and an import of a half-written file fails or produces garbage.
- Re-import in the background, then cook for the editor through the [cache](incremental.md#the-derived-data-cache), then reload the resource in place, so every user of the asset updates. See [hot reload](../patterns/resources.md#hot-reload).
- Watchers miss events (when the editor is closed, or under load). At start-up, compare each source file's content hash with the hash recorded at its last import, and re-import whatever differs.

## Validation

Catch problems when the asset is imported, not when the game ships:

| Check | Example |
| --- | --- |
| Limits | Texture larger than 4096, mesh over a triangle budget, audio longer than allowed for its type |
| Naming and location | Files outside allowed folders, names with spaces, wrong prefixes |
| References | A material pointing to a missing texture; a prefab pointing to a deleted mesh |
| Content | Non-power-of-two textures where a platform requires them, meshes with no UVs, NaN in animation data |
| Settings | A normal map imported as sRGB, a UI sprite with mipmaps |

- Report each problem against the **asset**, with a message that says how to fix it, in a problems list the editor keeps visible. A warning in a scrolling log is never read.
- Distinguish **errors** (the asset cannot be used; the build fails) from **warnings** (allowed, but should be looked at).
- Run the same validation on the build server, so a problem that slipped through locally still fails the build. Unity's version of this is on the [validation](../../unity/tools/editor/validation.md) page.

## Finding references

Because references are ids, the editor can answer "what uses this asset?" by scanning (or indexing) the ids in every asset file. Show it:

- Before deleting an asset, list everything that references it, and offer to cancel.
- In each asset's inspector, list what it uses and what uses it.
- A **broken references** report lists every id that points to nothing, with the asset containing it.

## Source control

- Store large binary source files (PSD, FBX, WAV) with Git LFS or in Perforce, and lock them while they are being edited, because binary files cannot be merged.
- Do not commit **cooked data** or caches: they are derived, rebuilt from source, and shared through the [derived data cache](incremental.md#the-derived-data-cache) instead.
- Keep **text** formats for everything people edit together (scenes, prefabs, materials), so changes can be reviewed and merged. See [text for authoring](../serialisation/formats.md#text-for-authoring).
