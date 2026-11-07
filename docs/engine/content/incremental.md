# Dependencies and incremental builds

A game has tens of thousands of assets, and cooking all of them takes hours. A change to one texture should rebuild that texture and the few things built from it, in seconds. That needs three things: knowing what each output was built from, a key that changes exactly when that does, and somewhere to keep previous results.

## Build keys

Every cooked output gets a **key**: a hash of everything that can affect it.

```text
key(asset, platform) = hash(
    content hash of the source or intermediate file,
    the asset's import and cook settings,
    platform and its settings,
    version of the cooking code for this asset type,
    keys of every dependency
)
```

- Hash the file's **contents**, not its modification time. Timestamps change when a branch is switched or a file is touched without changes, and differ between machines, so they cause needless rebuilds and cannot be shared.
- Include a **version number for each cooker**, increased whenever its code changes in a way that changes output. Otherwise a fixed texture compressor does not rebuild existing textures.
- Including the **dependencies' keys** makes changes propagate: when a texture's key changes, the key of every material using it changes too.

If the key is the same as the last build's, the old output is still correct and nothing runs.

## Discovering dependencies

Only the cooker knows what an asset depends on: the textures a material references, the files a shader `#include`s, the meshes a prefab uses. Each cooker reports them as it runs:

```text
cook(asset) -> output, dependencies[]
```

Store the reported dependencies with the output. The next build reads them to compute the key without running the cooker. Two kinds:

- **Build dependencies**: inputs whose contents change the output (shader includes, a texture baked into an atlas). Their keys go into this asset's key.
- **Runtime references**: assets loaded alongside this one but not baked into it (the textures a material points to at run time). They do not change this asset's cooked bytes, so they stay out of its key, but they are followed to decide **what to cook**: starting from the levels in the build, cook everything reachable.

Getting this distinction wrong either rebuilds too much (every material when one texture changes) or too little (an atlas that does not pick up a changed sprite).

A dependency that is not reported is a bug that shows up as **stale output**: the build used an old version of a file because nothing said it mattered. Catch it by running cookers in a sandbox that only allows reading declared inputs, or by recording every file a cooker opens and comparing that with what it reported.

## The derived data cache

Store cooked outputs by key:

```text
cache_get(key) -> bytes or missing
cache_put(key, bytes)

cook_or_fetch(asset, platform):
    k = key(asset, platform)
    if bytes = cache_get(k): return bytes
    bytes = cook(asset, platform)
    cache_put(k, bytes)
    return bytes
```

- A **local** cache on each machine makes switching branches and back cheap: the old outputs are still there.
- A **shared** cache on the network (or in cloud storage), filled by the build server and by everyone's machines, means an asset cooked once is never cooked again by anyone. A new team member's first build downloads instead of cooking for hours.
- Keys are content hashes, so entries never need invalidating: a changed input gives a new key. Old entries are removed by age or size.
- Only **deterministic** cookers can share a cache. If cooking the same input twice gives different bytes, a shared cache is still correct but cannot be checked, and differing outputs between machines cause bugs that only some people see.

Unreal's Derived Data Cache and Unity's Accelerator work this way.

## Building in parallel

The dependencies form a graph: textures before the materials that bake them, meshes and materials before the levels that bake lighting with them. Cook in dependency order, with everything whose inputs are ready running in parallel, using the same ideas as a [job graph](../jobs/dependencies.md), across processes or machines.

Cookers often use a lot of memory or call external compilers. Run them in separate worker processes, so a crash in one (a corrupt FBX that crashes the importer) fails that asset with a clear error instead of the whole build.

## In the editor

The editor uses the same system, with lower stakes: cook only what is being looked at, on demand, at editor quality (faster texture compression, no lightmap bake), and use the cache for everything else. The quality setting goes into the key, so editor-quality and shipping-quality outputs are cached separately.
