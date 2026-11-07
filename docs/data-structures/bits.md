---
uses:
  - name: Multiplayer
    text: Packing state into as few bits as possible before it goes over the network.
  - name: Base building
    text: Tile data packed into one integer per cell, and bitsets of occupied cells.
  - name: Strategy and tactics
    text: Visited and visible sets for flood fills and line of sight over large grids.
---

# Bit manipulation

Working with the individual bits of an integer: flags and masks, several small values packed into one integer, fast tricks built on two's complement, and arrays of bits. The code is pseudocode on unsigned 32-bit integers unless it says otherwise. Notes cover where C# and C++ differ.

## Operators

| Operator | Name | Bit is 1 when |
| --- | --- | --- |
| `a & b` | and | both are 1 |
| `a \| b` | or | either is 1 |
| `a ^ b` | xor | exactly one is 1 |
| `~a` | not | it was 0 |
| `a << n` | shift left | it was `n` places to the right; zeros come in on the right |
| `a >> n` | shift right | it was `n` places to the left; see below for what comes in on the left |

Shifting left by `n` multiplies by \(2^n\). Shifting right divides by \(2^n\), rounding down.

### Shift pitfalls

- **Signed right shift copies the sign bit** (an arithmetic shift): `-8 >> 1` is `-4`, and `-1 >> 1` stays `-1`. Unsigned right shift fills with zeros. Do bit work on **unsigned** types so `>>` means one thing. C# 11 adds `>>>`, which always fills with zeros.
- **Shifting by the full width or more** is undefined behaviour in C and C++. In C#, the count is masked to the width, so `1 << 32` is `1`, not `0`. Neither gives the 0 that the maths suggests. Guard the case where `n` can equal the width, such as a mask of `n` low bits with `n == 32`.
- **The literal's type sets the width.** `1 << 31` overflows a signed 32-bit `int` (undefined in C++ before C++20), and `1 << 40` is wrong in both languages. Write `1u << 31` and `1ul << 40` (C#: `1u`, `1ul`; C++: `1u`, `1ull`).
- **Precedence.** `==` binds tighter than `&`, so `x & mask == 0` means `x & (mask == 0)`. C compiles it silently; C# refuses it. Always bracket: `(x & mask) == 0`.

## Single bits

```text
bit(n)          = 1 << n
set(x, n)       = x | bit(n)
clear(x, n)     = x & ~bit(n)
toggle(x, n)    = x ^ bit(n)
test(x, n)      = (x & bit(n)) != 0
assign(x, n, b) = (x & ~bit(n)) | (b << n)           // b is 0 or 1
```

## Flags

Flags give each yes/no property its own bit, so a whole set of them fits in one integer, copies in one instruction, and compares in one instruction:

```text
enum Status : u32 {
    None      = 0
    Burning   = 1 << 0
    Poisoned  = 1 << 1
    Stunned   = 1 << 2
    Invisible = 1 << 3
    Frozen    = 1 << 4
    CannotAct = Stunned | Frozen        // combinations can be named too
}

s = s | Burning | Poisoned              // add
s = s & ~Poisoned                       // remove
any  = (s & (Burning | Poisoned)) != 0                  // has at least one
all  = (s & (Burning | Poisoned)) == (Burning | Poisoned)   // has every one
none = (s & CannotAct) == 0
changed = old ^ new                     // which flags differ
added   = new & ~old
removed = old & ~new
```

- Give flags explicit values, and never renumber them once they are saved to disk or sent over a network. Add new flags at new bits.
- Keep `0` as "none", and keep it out of `any` and `all` tests: `(s & None) != 0` is never true.
- `added` and `removed` are how a status-effect system knows which effects to start and stop when the whole set is replaced at once.

**In C#,** mark the enum `[Flags]` so `ToString` prints `Burning, Poisoned`. `HasFlag(x)` is the same as the `all` test. It boxes on older runtimes, Unity's Mono included, so write the `&` test in hot code. **In C++,** an `enum class` needs `|`, `&`, `^`, and `~` operators defined for it before any of this compiles.

## Masks

A mask selects some bits and ignores the rest.

```text
low_bits(n)      = n >= 32 ? 0xFFFFFFFF : (1 << n) - 1    // n ones on the right
range(lo, n)     = low_bits(n) << lo                     // n ones starting at bit lo
x & m            // keep only the bits in m
x & ~m           // clear the bits in m
(x & m) == m     // every bit of m is set in x
```

### Layer and collision masks

Physics engines use masks to decide what collides with what. Each object has a **category** (the bits saying what it is) and a **mask** (the bits saying what it collides with). Two objects collide only if each one's mask includes the other's category:

```text
collides(a, b) = (a.category & b.mask) != 0 and (b.category & a.mask) != 0
```

Box2D works this way. Unity's layers are the same idea with one category bit per object: a GameObject is on one of 32 layers, and a `LayerMask` is a 32-bit mask of layers.

```text
mask_for(layer)      = 1 << layer
includes(mask, go)   = (mask & (1 << go.layer)) != 0
everything           = ~0
everything_except(l) = ~(1 << l)
```

In Unity, `LayerMask.GetMask("Ground", "Water")` builds a mask from names, and `LayerMask.NameToLayer("Ground")` returns the **layer index**, not a mask. Passing an index where a mask is expected is the classic layer bug: layer 8 passed as a mask means layer 3 (8 is `1 << 3`).

## Packing fields

Several small values can share one integer, each in its own range of bits. A field is described by its **shift** (where its lowest bit is) and its **width** (how many bits it has):

```text
get(x, shift, width)    = (x >> shift) & low_bits(width)
put(x, shift, width, v) = (x & ~range(shift, width)) | ((v & low_bits(width)) << shift)
```

`put` clears the field before or-ing in the new value. Masking `v` stops a value that is too large from spilling into the next field.

### Examples

```text
Handle (32 bits)            index: 24 bits | generation: 8 bits
Tile (16 bits)              type: 8 | rotation: 2 | variant: 4 | walkable: 1 | burnt: 1
Colour (32 bits)            r: 8 | g: 8 | b: 8 | a: 8
Render sort key (64 bits)   layer: 4 | transparent: 1 | depth: 24 | material: 20 | mesh: 15
```

- The [handle table](handle-table.md) packs an index and a generation, so a handle is one integer that copies and compares cheaply.
- A grid of packed tiles is a quarter the size of a grid of tile structs, so more of the map fits in cache, and saves and network updates are smaller.
- **Sort keys** put the most important field in the highest bits, so sorting the integers sorts by layer first, then by depth within a layer, then by material. One integer comparison replaces a chain of `if`s. For transparent objects, store the depth inverted so they sort back to front.

### Signed fields

A field read with `get` is always non-negative. To store a signed value in `w` bits, store it as is (masking keeps its low `w` bits), and **sign-extend** it when reading: move the field's top bit to the integer's top bit, then shift back down with an arithmetic shift, which copies the sign bit down:

```text
get_signed(x, shift, width) =
    i32(get(x, shift, width) << (32 - width)) >> (32 - width)    // >> on a signed type
```

A 4-bit field holds −8 to 7: `0b1111` reads back as −1 and `0b1000` as −8.

### Floats in fewer bits

Store a float in a known range as an integer fraction of that range, then convert it back when reading:

```text
quantise(v, lo, hi, bits)   = round((clamp(v, lo, hi) - lo) / (hi - lo) * low_bits(bits))
dequantise(q, lo, hi, bits) = lo + q / low_bits(bits) * (hi - lo)
```

16 bits for a position within a 100 m area gives about 1.5 mm steps, which is enough for a networked character in place of a 32-bit float. Rounding, not truncating, keeps the error to half a step either way.

### Interleaving: Morton codes

Interleaving the bits of x and y (`y1 x1 y0 x0`) gives a **Morton code** (Z-order). Cells close together in 2D get close codes, so sorting objects by Morton code keeps neighbours near each other in memory, and a range of codes covers a square region. Quadtrees and spatial sorting use them.

```text
spread(x):                              // 16 bits -> every other bit of 32
    x = x & 0x0000FFFF
    x = (x | (x << 8)) & 0x00FF00FF
    x = (x | (x << 4)) & 0x0F0F0F0F
    x = (x | (x << 2)) & 0x33333333
    x = (x | (x << 1)) & 0x55555555
    return x

morton(x, y) = spread(x) | (spread(y) << 1)

compact(x):                             // the inverse of spread
    x = x & 0x55555555
    x = (x | (x >> 1)) & 0x33333333
    x = (x | (x >> 2)) & 0x0F0F0F0F
    x = (x | (x >> 4)) & 0x00FF00FF
    x = (x | (x >> 8)) & 0x0000FFFF
    return x

x = compact(code), y = compact(code >> 1)
```

Each step moves half of the remaining bits outward by a power of two, so 16 bits are spread in four steps, not sixteen.

### Byte order

Shifts and masks work on values, not on bytes in memory, so packing code with shifts gives the same result on every machine. Byte order (endianness) only matters when the same memory is read as a different type, such as reading four bytes from a file straight into an integer. Write files and network packets a byte at a time with shifts, and the question never comes up.

## Tricks

These rely on two's complement: `-x` is `~x + 1`, so `x - 1` flips the lowest set bit and every zero below it.

| Expression | Result | For `x = 0b0110_1000` |
| --- | --- | --- |
| `x & (x - 1)` | lowest set bit cleared | `0b0110_0000` |
| `x & -x` | only the lowest set bit | `0b0000_1000` |
| `x \| (x - 1)` | ones filled in below the lowest set bit | `0b0110_1111` |
| `x != 0 and (x & (x - 1)) == 0` | `x` is a power of two | false |
| `x & (n - 1)` | `x mod n`, when `n` is a power of two | |

- **Modulo by a power of two** is a mask, which is why [ring buffers](ring-buffer.md) and hash tables round their size up to a power of two. For negative `x` it gives the non-negative remainder (`-3 & 7` is 5), where `%` in C and C# gives −3, which is usually what a wrapped index needs.
- **Division by a power of two** with `>>` rounds down, towards minus infinity (`-3 >> 1` is −2), while `/` rounds towards zero (`-3 / 2` is −1). Use `>>` to turn world positions into grid cells: `-3 >> 4` puts −3 in cell −1, where `-3 / 16` wrongly puts it in cell 0, so cells either side of 0 would be the same.

### Counting and finding bits

| Operation | Meaning | C# (.NET Core 3+) | Unity.Mathematics | C++20 `<bit>` |
| --- | --- | --- | --- | --- |
| popcount | number of set bits | `BitOperations.PopCount` | `math.countbits` | `std::popcount` |
| count trailing zeros | index of the lowest set bit | `BitOperations.TrailingZeroCount` | `math.tzcnt` | `std::countr_zero` |
| count leading zeros | zeros above the highest set bit | `BitOperations.LeadingZeroCount` | `math.lzcnt` | `std::countl_zero` |
| floor of log2 | index of the highest set bit | `BitOperations.Log2` | `31 - math.lzcnt(x)` | `std::bit_width(x) - 1` |
| is power of two | | `BitOperations.IsPow2` (.NET 6) | `math.ispow2` | `std::has_single_bit` |
| round up to a power of two | | `BitOperations.RoundUpToPowerOf2` (.NET 6) | `math.ceilpow2` | `std::bit_ceil` |
| rotate | shift with wrap-around | `BitOperations.RotateLeft` | `math.rol` | `std::rotl` |

Each compiles to one or two instructions on current CPUs. Unity's Mono runtime does not have `BitOperations`; use Unity.Mathematics, which Burst turns into the same instructions. Before C++20, use the compiler built-ins (`__builtin_popcount`, `__builtin_ctz`, `__builtin_clz` on GCC and Clang; `__popcnt` and `_BitScanForward` on MSVC). The `ctz` and `clz` built-ins are undefined for 0, so check for zero first.

Without an intrinsic, rounding up to a power of two "smears" the highest set bit into every bit below it, then adds one:

```text
ceil_pow2(x):                           // x >= 1
    x = x - 1
    x = x | (x >> 1)
    x = x | (x >> 2)
    x = x | (x >> 4)
    x = x | (x >> 8)
    x = x | (x >> 16)
    return x + 1
```

### Visiting each set bit

```text
while x != 0:
    i = ctz(x)              // index of the lowest set bit
    visit(i)
    x = x & (x - 1)         // clear it
```

The loop runs once per set bit, not once per bit, so it is fast for sparse masks: which of 32 slots are occupied, which neighbours of a tile are walls, which flags changed.

## Bitsets

A bitset is an array of bits, stored in 64-bit words. It holds a set of small integers (entity indices, tile indices, slot numbers) in one bit each, a sixty-fourth of the size of an array of `u64`s and an eighth of an array of bools.

```text
Bitset { words: u64[] }               // ceil(n / 64) words

set(b, i)    = b.words[i >> 6] |= (1 << (i & 63))      // 1 as a 64-bit literal
clear(b, i)  = b.words[i >> 6] &= ~(1 << (i & 63))
test(b, i)   = (b.words[i >> 6] & (1 << (i & 63))) != 0
```

`i >> 6` is the word (`i / 64`) and `i & 63` is the bit within it (`i mod 64`).

### Whole-set operations

Set operations work 64 elements at a time:

```text
union(a, b)        = for each w: a.words[w] | b.words[w]
intersection(a, b) = for each w: a.words[w] & b.words[w]
difference(a, b)   = for each w: a.words[w] & ~b.words[w]
count(a)           = sum of popcount(a.words[w])
any(a)             = some a.words[w] != 0
```

"Tiles visible to any player" is the union of each player's visibility bitset, and "tiles newly revealed this turn" is the difference between this turn's and last turn's. For a map of 256 × 256 tiles, each is 1,024 words.

When iterating, the bits past `n` in the last word must stay zero, or `count` and the iteration below include elements that do not exist. Keep them clear in every operation that can set them, such as `not`.

### Iterating and finding

```text
for w in 0 .. len(words) - 1:
    bits = words[w]
    while bits != 0:
        i = w * 64 + ctz(bits)
        visit(i)
        bits = bits & (bits - 1)

first_clear(b):                        // e.g. the first free slot
    for w in 0 .. len(words) - 1:
        if words[w] != ~0:             // this word has a zero
            return w * 64 + ctz(~words[w])
    return none
```

Both skip 64 elements at a time when a word is empty or full. For very large sets, add a **summary** bitset with one bit per word ("this word is not empty"), and search that first. Two levels of 64-bit words cover 4,096 elements with one search in each.

### Component masks

An [entity component system](../engine/ecs/index.md) can give each component type a bit and each entity (or each [archetype](../engine/ecs/archetype-storage.md)) a mask of the components it has. A query is two masks:

```text
matches(entity_mask, required, excluded) =
    (entity_mask & required) == required and (entity_mask & excluded) == 0
```

With 64 or fewer component types, the mask is one `u64` and a match is a few instructions. Beyond that, use a small fixed-size bitset (for example 4 words for 256 types) and test each word.
