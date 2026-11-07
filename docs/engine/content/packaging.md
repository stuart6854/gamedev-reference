# Packaging

A shipped game does not load thousands of loose files. Cooked data is packed into a few large **archives**, which load faster, compress better, and are easier to patch and verify.

## Why archives

- **Opening files is slow.** Each open costs a system call and file-system lookups, and on consoles and some PC storage, much more. One archive opened once avoids that.
- **Large sequential reads are fast.** Reading assets in the order they are loaded, from one file, keeps the drive streaming instead of seeking.
- **Platform requirements.** Consoles and mobile stores limit the number of files, or require specific package formats.
- **Integrity.** A table of hashes detects corrupt or modified data.

## The archive format

```text
Header      { magic, version, toc_offset, toc_size, flags }
Data        file data, each entry aligned (e.g. to 4 KB or 64 KB)
TOC         table of contents, sorted by asset id:
            { asset_id, offset, size, compressed_size, compression, hash }
```

- The **table of contents** is read once when the archive is mounted and kept in memory. Finding an asset is a binary search or a hash lookup by id, with no file-system involved.
- Key entries by the same **asset id** the [resource system](../patterns/resources.md#ids-and-handles) uses, not by path. Paths only need to exist in development builds, for debugging.
- **Align** entries to the storage block size, so each read starts on a block boundary and uncompressed data can be read directly into its destination, or memory-mapped for [load-in-place](../serialisation/references.md#load-in-place) data.

## Compression

Compress each entry, or for large entries, each 64 KB block separately:

- Per-block compression lets the loader read and decompress part of a large asset (one mip of a texture, one section of a level) without the rest.
- Choose per type. Already-compressed data (Vorbis audio, video) gains nothing from more compression. BC-compressed textures still shrink well with a general compressor such as Oodle Kraken, Zstandard, or LZ4. Some formats compress much better after a reversible reordering (Oodle Texture, or splitting a vertex buffer into streams per attribute).
- Decompression speed matters more than ratio for anything loaded during play. Modern consoles decompress in hardware (Kraken on PlayStation 5, BCPack and zlib on Xbox Series), so use the hardware's formats there.

## Ordering for loading

Put assets in the archive in the order the game loads them. Record it: run the game in a development build with a file-access log, play through the start and each level, and write out every asset id in the order it was requested. The packager writes entries in that order, and anything not in the log after them.

Group by when assets are needed, too:

- A **start-up** archive with everything the main menu needs, so the game starts while the rest is still installing or downloading.
- An archive per **level or region**, so installing or streaming in chunks is possible.
- **Shared** assets used everywhere in their own archive, once, instead of duplicated into every level's archive. Duplication trades disk space for fewer seeks; it is worth it for small assets on slow drives, and rarely otherwise.

## Patches

A patch should download only what changed, not the whole game again.

- **Layered archives.** Mount the base archives first, then patch archives on top. When two archives contain the same asset id, the one mounted last wins. A patch is then an archive containing only the changed assets.
- **Deterministic cooking** keeps patches small. If unchanged assets cook to the same bytes, the patch tool sees they did not change. Timestamps or random ordering in cooked data make every asset "changed".
- **Keep the layout stable.** Some platforms patch by comparing the old and new files block by block. Adding an asset at the start of a big archive shifts everything after it, and the whole archive appears changed. Append new entries, or leave space, and keep the order of existing ones.

## DLC and mods

Downloadable content is more archives, mounted after the base game when the player owns them. Give each DLC its own range or namespace of asset ids, so it can add assets without colliding with the base game, and reference base assets freely. Mods work the same way if the game mounts archives (or loose folders) from a mods directory on top of the base game; the layering rules above decide what a mod can replace.

## Security

Encrypting archives stops casual extraction, but the key ships with the game, so it only slows people down. If modified data must be rejected (in competitive multiplayer), sign the table of contents and check each entry's hash when it loads. The [save file](../serialisation/formats.md#reading-safely) rules apply to anything a player can supply.
