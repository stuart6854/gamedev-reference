# Import and cook

Artists work in tools that save in their own formats: FBX and glTF from Blender and Maya, PSD and PNG from image editors, WAV from audio tools. The game should never read those formats. They are large, slow to parse, full of data the game does not need, and the libraries that read them do not belong in a shipped game. The pipeline converts them in two stages.

## The stages

| Stage | Input | Output | Runs |
| --- | --- | --- | --- |
| **Import** | Source file | Intermediate asset in the engine's own format, plus a metadata file | In the editor, when a source file is added or changes |
| **Cook** | Intermediate asset, platform | Runtime data for one platform | When building the game, or on demand in the editor |
| **Package** | Cooked data | Archive files | When building a release; see [packaging](packaging.md) |

**Import** turns a foreign format into the engine's own, keeping everything an editor might need: full-precision data, names, hierarchy, and settings. It runs once per source change. The result is what the editor shows and edits.

**Cook** turns that into exactly what the game needs on one platform, and nothing more: compressed textures in the GPU's format, vertex data in the layout the shaders read, compiled shaders, compressed audio. Editor-only data (names, thumbnails, source paths) is dropped.

Keeping the stages separate means a platform's cooking settings can change (a new texture compression) without re-importing, and the editor works on full-quality intermediate data while each platform gets its own cooked version.

## Per asset type

| Asset | Import | Cook |
| --- | --- | --- |
| Texture | Decode PSD or PNG to raw pixels; read settings (sRGB or linear, normal map, max size) from the metadata | Resize, generate mips, compress to BC1 to BC7 (desktop), ASTC (mobile), or the console's format |
| Mesh | Read FBX or glTF with a library (Assimp, cgltf, the FBX SDK); convert units and axes; split by material | Optimise vertex order for the GPU cache (meshoptimizer), quantise positions and normals, build LODs, interleave in the shader's layout |
| Skeleton and animation | Read bones and keys | Remove redundant keys, quantise, compress curves |
| Material | Parse the engine's text format; resolve texture references | Pack parameters into a constant-buffer layout; reference the compiled shader variant |
| Shader | Parse and find includes and variants | Compile each needed variant for each platform's graphics API; strip variants no material uses |
| Audio | Decode WAV | Resample if needed; encode as Vorbis, Opus, ADPCM, or the platform's codec |
| Level | Already in the engine's text format | Convert to binary, bake lighting and navigation, split into streaming cells |

## Tools as functions

Write each importer and cooker as a command-line tool, or a library function with no editor dependency:

```text
cook_texture(intermediate_bytes, settings, platform) -> cooked_bytes, dependencies, log
```

- The **editor** calls it when you save, to show the result.
- The **build server** calls it for every platform, without an editor running.
- **Tests** call it with small inputs and compare the output with [golden files](../testing/index.md#golden-files).

The function's output must depend only on its inputs. No timestamps in the output, no reading other files that were not declared as dependencies, no random numbers without a fixed seed, and no iterating over hash maps to decide order. That **determinism** is what makes [incremental builds and caching](incremental.md) possible: the same inputs always give the same bytes, so the result can be reused.

## Units, axes, and scale

Source tools disagree about which way is up (Y or Z), which way is forward, whether the coordinate system is left- or right-handed, and whether a unit is a centimetre or a metre. Convert everything to the engine's convention in the **importer**, once, so nothing after it has to know where an asset came from. Record the source tool's conventions in the import settings, with a sensible default per file type, and show the imported result next to a reference figure of known height in the editor, so a model that came in a hundred times too big is noticed at import, not in a level.

## Import settings

Settings that change the result (texture compression, mesh scale, whether to generate collision) are stored per asset in a **metadata file** next to the source:

```text
crate.png.meta:
    id: 4f1c9a2e-...
    importer: texture
    settings: { srgb: true, max_size: 1024, compression: high_quality }
    platform_overrides: { mobile: { max_size: 512 } }
```

Settings belong to the asset, not to the person importing it, so everyone gets the same result. They are versioned with the source file. Unity's `.meta` files work this way; see [editor workflow](editor-workflow.md).
