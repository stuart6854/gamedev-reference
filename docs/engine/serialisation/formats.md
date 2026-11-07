# Formats

Data an engine writes falls into two groups. **Authoring data** (scenes, prefabs, materials, settings) is edited by people, stored in version control, and merged. **Runtime data** (cooked assets, save games, network messages) is read by the game, as fast and compactly as possible. They want different formats.

| | Text | Binary |
| --- | --- | --- |
| Readable and diffable | Yes | No |
| Mergeable in version control | Yes, if written carefully | No |
| Size | Large | Small |
| Read speed | Parsing, string-to-number conversions | Close to a memory copy |
| Use for | Authoring data, config, debug dumps | Cooked assets, saves, network |

The [content pipeline](../content/import-cook.md) converts one into the other. The same [reflection](reflection.md) data drives both, so a type is described once.

## Text for authoring

A JSON-like format, or YAML as in Unity's scene files. What makes text work well in version control:

- **Stable order.** Write fields in declaration order and objects in a stable order (by id), never in hash-map order. Otherwise re-saving an unchanged file produces a diff.
- **One value per line** where it is cheap, so a change to one field is a one-line diff and two people changing different fields merge cleanly.
- **Exact floats.** Write floats so they read back exactly (C++17 `std::to_chars` gives the shortest exact form), or saving and loading slowly drifts every value.
- **Stable ids for objects**, not array positions. Inserting an object at the start of a list must not renumber every object after it (see [references](references.md)).
- **Omit defaults**, or write them all, but choose one: writing defaults makes files show every value; omitting them keeps files small and lets a default change reach existing data.

## Binary for runtime

```cpp
class BinaryWriter {
public:
    void write_u8(uint8_t v)   { bytes_.push_back(v); }
    void write_u32(uint32_t v) { for (int i = 0; i < 4; i++) write_u8(uint8_t(v >> (i * 8))); }   // little-endian
    void write_f32(float v)    { write_u32(std::bit_cast<uint32_t>(v)); }
    void write_string(std::string_view s)
    {
        write_varint(s.size());
        bytes_.insert(bytes_.end(), s.begin(), s.end());
    }
    void write_varint(uint64_t v)          // 7 bits per byte; high bit set means more follow
    {
        while (v >= 0x80) { write_u8(uint8_t(v) | 0x80); v >>= 7; }
        write_u8(uint8_t(v));
    }
private:
    std::vector<uint8_t> bytes_;
};
```

- **Fix the byte order** in the format (little-endian, as above), and write with shifts, not by copying structs. The file is then the same on every platform, whatever the CPU. See [byte order](../../data-structures/bits.md#byte-order).
- **Length-prefix** strings and arrays. Readers can then skip them, and allocate once.
- **Varints** store small numbers in one byte. Use them for counts and ids, which are usually small; use fixed sizes for values that are random-looking, like hashes and floats.
- **Do not write structs with `memcpy`** in formats that outlive one build: padding, alignment, and field layout change with the compiler and the platform. The exception is cooked data that is rebuilt for every build and platform; see [load-in-place](references.md#load-in-place).

### Reading safely

Save files are edited by players, downloaded, and corrupted by crashes mid-write. Network messages come from anyone. A reader must survive any bytes:

```cpp
class BinaryReader {
public:
    bool read_u32(uint32_t& v)
    {
        if (remaining() < 4) return fail();
        v = 0;
        for (int i = 0; i < 4; i++) v |= uint32_t(data_[pos_++]) << (i * 8);
        return true;
    }
    bool read_count(uint32_t& n, size_t min_bytes_each)
    {
        if (!read_varint32(n)) return false;
        if (uint64_t(n) * min_bytes_each > remaining()) return fail();   // no 4-billion-element allocations
        return true;
    }
    // ...
private:
    bool fail() { failed_ = true; return false; }
    std::span<const uint8_t> data_;
    size_t pos_ = 0;
    bool failed_ = false;
};
```

- Check every read against the remaining length.
- Check every count against what could possibly fit in the remaining bytes before allocating. A corrupt count is otherwise an out-of-memory crash.
- Once a read fails, stop: return an error for the whole file, and keep the game's previous state.
- Fuzz the reader (libFuzzer, AFL) with random and mutated files. Readers that have never been fuzzed always crash on something.

### Headers and chunks

```text
Header {
    magic           u32     "SAVE": identifies the file type
    version         u32     format version; see versioning
    flags           u32     compressed, ...
    payload_size    u32
    checksum        u32     CRC32 or xxHash of the payload
}
payload:
    chunk { tag: u32, size: u32, bytes }      // "PLYR", "WRLD", "QUST", ...
    chunk ...
```

- The **magic** number catches the wrong file passed in. The **checksum** catches truncation and corruption before the payload is parsed.
- **Chunks** with a tag and a size let a reader skip chunks it does not know, and let separate systems own their own chunks. The quest system reads `QUST` without knowing the format of `WRLD`.
- **Save atomically.** Write to a temporary file, flush it, then rename it over the old one, keeping one backup. A crash mid-save then leaves the old save intact. The [save system](../../unity/systems/saving/save-system.md) page does this in Unity.

## Compression

Compress the payload, not the header, so the version and checksum can be read without decompressing. LZ4 decompresses fastest; Zstandard compresses better at similar decompression speed. Both are open source. Compress after serialising, as a separate step, so the format and the compression can change independently.
