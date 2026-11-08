---
uses:
  - name: Base building
    text: Grid cells from world positions that stay correct either side of zero.
  - name: Open worlds
    text: Memory budgets shown in the right units, and stable string ids for streamed assets.
  - name: Multiplayer
    text: String hashes that are the same on every machine and every run.
---

# Maths utilities

Small functions that every engine writes and most standard libraries leave out, or ship in a form that is awkward to use. Each section gives C++ (C++20, `constexpr` wherever the language allows) and C# versions.

- **Integers:** rounded-up division, floor division and modulo for negative numbers, integer powers.
- **Powers of two, alignment, and pointer arithmetic.**
- **Memory sizes:** binary versus decimal units, and printing them.
- **Floats:** approximate equality, angles, `saturate`, `fract`.
- **Lerp and slerp.**
- **Hashing:** combining hashes, and string hashes for ids.

## Integers

- **Division rounds towards zero**, so `-3 / 2` is −1, and `-3 % 2` is −1. For grid cells, chunk indices, and wrapped indices you want **floor** division and a modulo that is never negative.
- **Rounded-up division** gives how many groups, pages, or blocks are needed: `(a + b - 1) / b` for `a >= 0`, `b > 0`.
- **Integer powers** by repeated squaring are exact, where `std::pow` goes through `double`.
- **Midpoint** of two large integers: `(a + b) / 2` overflows; `a + (b - a) / 2` does not when `a <= b`.

=== "C++"

    ```cpp
    #include <concepts>

    template <std::integral T>
    constexpr T div_ceil(T a, T b) { return (a + b - 1) / b; }          // a >= 0, b > 0

    template <std::signed_integral T>
    constexpr T floor_div(T a, T b)
    {
        T q = a / b;
        return (a % b != 0 && ((a < 0) != (b < 0))) ? q - 1 : q;
    }

    template <std::signed_integral T>
    constexpr T floor_mod(T a, T b)                                       // result has the sign of b
    {
        T r = a % b;
        return (r != 0 && ((r < 0) != (b < 0))) ? r + b : r;
    }

    template <std::signed_integral T>
    constexpr T sign(T x) { return (T(0) < x) - (x < T(0)); }

    template <std::integral T>
    constexpr T ipow(T base, unsigned exp)
    {
        T result = 1;
        while (exp != 0) {
            if (exp & 1) result *= base;
            exp >>= 1;
            if (exp != 0) base *= base;      // skip the last square: it could overflow
        }
        return result;
    }

    static_assert(floor_div(-3, 16) == -1 && floor_mod(-3, 16) == 13);
    static_assert(div_ceil(10, 4) == 3 && ipow(3, 4) == 81);
    ```

    - `std::min`, `std::max`, `std::clamp`, and `std::midpoint` (C++20) are already `constexpr`. `std::abs` is `constexpr` from C++23.
    - `std::abs(INT_MIN)` and `-INT_MIN` are undefined behaviour. Keep values away from the limits, or work in a wider type.
    - For a power-of-two divisor, `>>` and `& (n - 1)` give floor division and modulo directly; see [bit tricks](../data-structures/bits.md#tricks).

=== "C#"

    ```csharp
    public static int DivCeil(int a, int b) => (a + b - 1) / b;           // a >= 0, b > 0

    public static int FloorDiv(int a, int b)
    {
        int q = a / b;
        return (a % b != 0 && ((a < 0) != (b < 0))) ? q - 1 : q;
    }

    public static int FloorMod(int a, int b)                               // result has the sign of b
    {
        int r = a % b;
        return (r != 0 && ((r < 0) != (b < 0))) ? r + b : r;
    }

    public static long IPow(long b, int exp)
    {
        long result = 1;
        while (exp != 0)
        {
            if ((exp & 1) != 0) result *= b;
            exp >>= 1;
            if (exp != 0) b *= b;
        }
        return result;
    }
    ```

    - `Math.Sign`, `Math.Clamp`, `Math.DivRem`, `Math.Min`, and `Math.Max` cover the rest. On .NET 7 and later, `T : IBinaryInteger<T>` makes these generic.
    - `Math.Abs(int.MinValue)` throws `OverflowException`.
    - Unity: `Mathf.FloorToInt` and `math.floor` work on floats. For integers, use the functions above.

## Powers of two

| Operation | C++20 `<bit>` | C# (.NET 6+) | Unity.Mathematics |
| --- | --- | --- | --- |
| `x` is a power of two | `std::has_single_bit(x)` | `BitOperations.IsPow2(x)` | `math.ispow2(x)` |
| smallest power of two ≥ `x` | `std::bit_ceil(x)` | `BitOperations.RoundUpToPowerOf2(x)` | `math.ceilpow2(x)` |
| largest power of two ≤ `x` | `std::bit_floor(x)` | `1u << BitOperations.Log2(x)` | `1 << math.floorlog2(x)` |
| floor of log2 (`x > 0`) | `std::bit_width(x) - 1` | `BitOperations.Log2(x)` | `math.floorlog2(x)` |
| ceiling of log2 (`x > 0`) | `std::bit_width(x - 1)` | `x == 1 ? 0 : BitOperations.Log2(x - 1) + 1` | `math.ceillog2(x)` |
| 2<sup>n</sup> | `std::uint64_t(1) << n` | `1UL << n` | |

- All of the C++ functions are `constexpr` and take unsigned types only.
- Ceiling log2 is the number of mip levels below a size, or the bits needed to store `x` distinct values.
- The [bit manipulation](../data-structures/bits.md#counting-and-finding-bits) page has the versions without intrinsics, for older compilers and Unity's Mono runtime.

## Alignment

An address or size is **aligned** to `a` when it is a multiple of `a`. Allocators, GPU buffers (constant buffers at 256 bytes, for example), and file formats all need values rounded up to an alignment. With `a` a power of two this is a mask:

```text
align_up(x, a)   = (x + a - 1) & ~(a - 1)
align_down(x, a) = x & ~(a - 1)
is_aligned(x, a) = (x & (a - 1)) == 0
padding(x, a)    = (-x) & (a - 1)        // bytes to add to reach the next multiple
```

For an alignment that is not a power of two, use `div_ceil(x, a) * a`.

=== "C++"

    ```cpp
    #include <cstddef>
    #include <cstdint>

    template <std::unsigned_integral T>
    constexpr T align_up(T x, T a) { return (x + a - 1) & ~(a - 1); }     // a: power of two

    template <std::unsigned_integral T>
    constexpr T align_down(T x, T a) { return x & ~(a - 1); }

    template <std::unsigned_integral T>
    constexpr bool is_aligned(T x, T a) { return (x & (a - 1)) == 0; }

    template <std::unsigned_integral T>
    constexpr T padding(T x, T a) { return (T(0) - x) & (a - 1); }

    static_assert(align_up<std::size_t>(13, 8) == 16 && padding<std::size_t>(13, 8) == 3);

    // Pointers: work out the padding from the address, then step the pointer itself.
    inline std::byte* align_up(std::byte* p, std::size_t a)
    {
        return p + padding(static_cast<std::size_t>(reinterpret_cast<std::uintptr_t>(p)), a);
    }

    inline bool is_aligned(const void* p, std::size_t a)
    {
        return (reinterpret_cast<std::uintptr_t>(p) & (a - 1)) == 0;
    }
    ```

    - Pointer versions cannot be `constexpr`: `reinterpret_cast` is not allowed in constant expressions.
    - Adding the padding to the original pointer, rather than casting an aligned integer back to a pointer, keeps the compiler's knowledge of which allocation the pointer belongs to.
    - `alignof(T)` and `alignas(N)` give and set a type's alignment. `std::align` exists, but updates its arguments in place and is awkward to use; `std::assume_aligned` (C++20) is an optimisation hint only, and does not align anything.

=== "C#"

    ```csharp
    public static nuint AlignUp(nuint x, nuint a) => (x + a - 1) & ~(a - 1);     // a: power of two
    public static nuint AlignDown(nuint x, nuint a) => x & ~(a - 1);
    public static bool IsAligned(nuint x, nuint a) => (x & (a - 1)) == 0;
    public static nuint Padding(nuint x, nuint a) => (0 - x) & (a - 1);

    public static unsafe byte* AlignUp(byte* p, nuint a) => p + Padding((nuint)p, a);
    ```

    - Write `int` and `long` overloads as well; `nuint` is the type to use for addresses.
    - `NativeMemory.AlignedAlloc` (.NET 6) allocates aligned native memory. C# has no `alignof`: `Unsafe.SizeOf<T>()` gives the size only.
    - Unity: `CollectionHelper.Align(size, alignment)`, `UnsafeUtility.AlignOf<T>()`, and `UnsafeUtility.Malloc(size, alignment, allocator)`.

## Pointer arithmetic

- **Arithmetic on `T*` counts in elements**, not bytes: `p + 1` moves `sizeof(T)` bytes. For byte offsets, step a byte pointer.
- **Subtracting** two pointers into the same block gives the number of elements between them: `element - base` is an index.
- **Pointers from different allocations** cannot be compared with `<` portably. Compare addresses as integers when checking whether a pointer belongs to a block.
- **Reading a value at an arbitrary byte offset** may be misaligned. Copy it out with `memcpy` rather than casting the pointer.

=== "C++"

    ```cpp
    #include <cstring>

    inline void* ptr_add(void* p, std::ptrdiff_t bytes) { return static_cast<std::byte*>(p) + bytes; }

    inline std::ptrdiff_t ptr_diff(const void* a, const void* b)   // a and b in the same block
    {
        return static_cast<const std::byte*>(a) - static_cast<const std::byte*>(b);
    }

    inline bool ptr_in_range(const void* p, const void* begin, std::size_t size)
    {
        auto v = reinterpret_cast<std::uintptr_t>(p);
        auto b = reinterpret_cast<std::uintptr_t>(begin);
        return v - b < size;                  // one unsigned compare also rejects p < begin
    }

    template <class T>
    T load_unaligned(const void* p)           // compiles to a single load on x64 and ARM64
    {
        T value;
        std::memcpy(&value, p, sizeof(T));
        return value;
    }
    ```

    - `std::uintptr_t` and `std::ptrdiff_t` are the integer types for addresses and differences.
    - `offsetof(Type, member)` is only defined for standard-layout types.
    - Casting a `std::byte*` to `T*` and reading through it needs a `T` to really live there (placed with `new` or `std::construct_at`). Otherwise use `load_unaligned`.

=== "C#"

    ```csharp
    unsafe
    {
        byte* q = p + 16;                     // byte* steps in bytes
        long bytes = q - p;                   // difference in elements of the pointer type
        int value = Unsafe.ReadUnaligned<int>(q);
    }

    // Without unsafe pointers, on managed references:
    ref T next = ref Unsafe.Add(ref first, 1);                     // one element on
    ref T byByte = ref Unsafe.AddByteOffset(ref first, (nint)8);   // eight bytes on
    nint offset = Unsafe.ByteOffset(ref first, ref next);          // bytes between them
    ```

    - Prefer `Span<T>` slicing: it bounds-checks, and the JIT removes most of the checks in loops.
    - Pointers into managed arrays are only valid inside a `fixed` block, or while the array is pinned.
    - Unity: `NativeArray<T>.GetUnsafePtr()` and `UnsafeUtility.ReadArrayElement<T>(ptr, index)`.

## Memory sizes

Two sets of units are in common use, and they differ by 2.4 % at kilobytes and 7.4 % at gigabytes:

| Binary (IEC) | Bytes | Decimal (SI) | Bytes |
| --- | --- | --- | --- |
| KiB | 1,024 | KB | 1,000 |
| MiB | 1,048,576 | MB | 1,000,000 |
| GiB | 1,073,741,824 | GB | 1,000,000,000 |

- Memory budgets, page sizes, and GPU memory are normally binary. Disk and download sizes are normally decimal.
- Windows labels binary values "KB" and "MB"; macOS uses decimal. Write `KiB` and `MiB` in tools, so a reported number cannot be misread.
- Network speeds are in **bits** per second, in decimal: 1 Mbps is 125,000 bytes per second.

=== "C++"

    ```cpp
    #include <cstdio>
    #include <string>

    inline constexpr std::uint64_t KiB = 1024, MiB = KiB * 1024, GiB = MiB * 1024;
    inline constexpr std::uint64_t KB = 1000, MB = KB * 1000, GB = MB * 1000;

    constexpr double to_mib(std::uint64_t bytes) { return double(bytes) / double(MiB); }

    inline std::string format_bytes(std::uint64_t bytes)
    {
        static constexpr const char* units[] = { "B", "KiB", "MiB", "GiB", "TiB" };
        double value = double(bytes);
        int unit = 0;
        while (value >= 1024.0 && unit < 4) { value /= 1024.0; unit++; }
        char buf[32];
        std::snprintf(buf, sizeof buf, unit == 0 ? "%.0f %s" : "%.1f %s", value, units[unit]);
        return buf;                                                      // 1536 → "1.5 KiB"
    }

    static_assert(64 * MiB == 67'108'864);
    ```

=== "C#"

    ```csharp
    public const long KiB = 1024, MiB = KiB * 1024, GiB = MiB * 1024;
    public const long KB = 1000, MB = KB * 1000, GB = MB * 1000;

    public static string FormatBytes(long bytes)
    {
        string[] units = { "B", "KiB", "MiB", "GiB", "TiB" };
        double value = bytes;
        int unit = 0;
        while (value >= 1024 && unit < units.Length - 1) { value /= 1024; unit++; }
        return unit == 0 ? $"{value:0} {units[unit]}" : $"{value:0.0} {units[unit]}";
    }
    ```

    `const` works here because the values are built from literals, so they can be used in `case` labels and attribute arguments.

## Floats

- **Never compare floats with `==`** after arithmetic. Compare against a tolerance that combines an **absolute** part (for values near zero) and a **relative** part (for large values, where the gap between floats is wider).
- **Angles**: store radians, convert at the edges (inspector, UI, config files). Wrap angle differences to \([-\pi, \pi]\) before interpolating or comparing.
- **`saturate`** clamps to \([0, 1]\), and **`fract`** gives the fractional part, always in \([0, 1)\), also for negative numbers: `fract(-0.25)` is 0.75.

=== "C++"

    ```cpp
    #include <algorithm>
    #include <cmath>
    #include <numbers>

    inline constexpr float PI = std::numbers::pi_v<float>;
    inline constexpr float TAU = 2.0f * PI;

    constexpr float deg_to_rad(float deg) { return deg * (PI / 180.0f); }
    constexpr float rad_to_deg(float rad) { return rad * (180.0f / PI); }
    constexpr float saturate(float x) { return x < 0.0f ? 0.0f : (x > 1.0f ? 1.0f : x); }

    constexpr bool approx_equal(float a, float b, float abs_eps = 1e-6f, float rel_eps = 1e-5f)
    {
        float diff = a > b ? a - b : b - a;
        float largest = std::max(a < 0.0f ? -a : a, b < 0.0f ? -b : b);
        return diff <= abs_eps || diff <= rel_eps * largest;
    }

    inline float fract(float x) { return x - std::floor(x); }
    inline float wrap_angle(float a) { return std::remainder(a, TAU); }        // [-π, π]
    inline float delta_angle(float from, float to) { return wrap_angle(to - from); }

    static_assert(approx_equal(0.1f + 0.2f, 0.3f) && saturate(1.5f) == 1.0f);
    ```

    - `std::floor` and `std::remainder` become `constexpr` in C++23, but library support is uneven, so these are `inline` here.
    - `std::numbers` (C++20) has `pi`, `e`, `sqrt2`, `inv_pi`, and others, as `constexpr` values in each float type.
    - Tolerances depend on the scale of the values: 1e-6 is far below the spacing of floats near 10,000. Choose them per use, not one global epsilon.

=== "C#"

    ```csharp
    public const float Deg2Rad = MathF.PI / 180f, Rad2Deg = 180f / MathF.PI;

    public static float Saturate(float x) => Math.Clamp(x, 0f, 1f);
    public static float Fract(float x) => x - MathF.Floor(x);
    public static float WrapAngle(float a) => MathF.IEEERemainder(a, MathF.Tau);     // [-π, π]
    public static float DeltaAngle(float from, float to) => WrapAngle(to - from);

    public static bool ApproxEqual(float a, float b, float absEps = 1e-6f, float relEps = 1e-5f)
    {
        float diff = MathF.Abs(a - b);
        return diff <= absEps || diff <= relEps * MathF.Max(MathF.Abs(a), MathF.Abs(b));
    }
    ```

    Unity has most of these built in: `Mathf.Deg2Rad`, `Mathf.Approximately` (a fixed relative tolerance), `Mathf.DeltaAngle` and `Mathf.Repeat` (in degrees), and `math.radians`, `math.saturate`, and `math.frac` in Unity.Mathematics.

## Lerp and slerp

The short versions; [interpolation and easing](interpolation.md) and [quaternions](quaternions.md#slerp-and-nlerp) cover how to use them.

- `lerp(a, b, t)` blends from `a` to `b`; `inverse_lerp` finds `t` from a value; `remap` maps a value from one range to another.
- `a + (b - a) * t` can miss `b` slightly at `t = 1` because of rounding. `std::lerp` (C++20) is exact at both ends.
- **Angles** need the shortest way round: lerp by the wrapped difference.
- **Slerp** moves along the arc between two unit vectors at a constant angular speed. When they are nearly parallel it falls back to a normalised lerp, which avoids dividing by a tiny sine.

=== "C++"

    ```cpp
    constexpr float lerp(float a, float b, float t) { return a + (b - a) * t; }     // or std::lerp
    constexpr float inverse_lerp(float a, float b, float v) { return (v - a) / (b - a); }
    constexpr float remap(float v, float in0, float in1, float out0, float out1)
    {
        return lerp(out0, out1, inverse_lerp(in0, in1, v));
    }
    constexpr float smoothstep(float e0, float e1, float x)
    {
        float t = saturate((x - e0) / (e1 - e0));
        return t * t * (3.0f - 2.0f * t);
    }

    inline float lerp_angle(float a, float b, float t) { return a + delta_angle(a, b) * t; }

    // Any vec3 type with dot, normalize, +, -, and * by a scalar. a and b unit length.
    inline vec3 slerp(vec3 a, vec3 b, float t)
    {
        float d = std::clamp(dot(a, b), -1.0f, 1.0f);
        if (d > 0.9995f) return normalize(a + (b - a) * t);    // nearly parallel: nlerp
        vec3 towards_b = normalize(b - a * d);                 // perpendicular to a, in the plane of a and b
        float angle = std::acos(d) * t;
        return a * std::cos(angle) + towards_b * std::sin(angle);
    }

    static_assert(remap(5.0f, 0.0f, 10.0f, 100.0f, 200.0f) == 150.0f);
    ```

    - Opposite vectors (`d` close to −1) have no unique arc. Pick any perpendicular axis, or avoid the case.
    - `std::acos`, `std::sin`, and `std::cos` are not `constexpr` before C++26, so slerp cannot be either.

=== "C#"

    ```csharp
    public static float Lerp(float a, float b, float t) => a + (b - a) * t;
    public static float InverseLerp(float a, float b, float v) => (v - a) / (b - a);
    public static float Remap(float v, float in0, float in1, float out0, float out1) =>
        Lerp(out0, out1, InverseLerp(in0, in1, v));
    public static float LerpAngle(float a, float b, float t) => a + DeltaAngle(a, b) * t;

    public static Vector3 Slerp(Vector3 a, Vector3 b, float t)               // System.Numerics; unit vectors
    {
        float d = Math.Clamp(Vector3.Dot(a, b), -1f, 1f);
        if (d > 0.9995f) return Vector3.Normalize(Vector3.Lerp(a, b, t));
        Vector3 towardsB = Vector3.Normalize(b - a * d);
        float angle = MathF.Acos(d) * t;
        return a * MathF.Cos(angle) + towardsB * MathF.Sin(angle);
    }
    ```

    - `float.Lerp` exists from .NET 7, and `Quaternion.Slerp` in `System.Numerics`, but there is no vector slerp.
    - Unity: `Mathf.Lerp` and `Mathf.InverseLerp` clamp `t`; `Mathf.LerpUnclamped` does not. `Vector3.Slerp` and `Mathf.LerpAngle` (degrees) are built in.

## Hashing

- **Combining hashes** for a key made of several fields: mix each field's hash into a running seed. The combine must depend on order, or `(1, 2)` and `(2, 1)` collide.
- **String ids**: hash names like `"jump"` or `"textures/rock.png"` once, and compare 64-bit integers afterwards. FNV-1a is short, good enough for ids, and easy to make `constexpr`.
- **Check for collisions**: in debug builds, keep a table from hash to string, and assert when two different strings produce the same id.
- **Stable versus per-run hashes**: ids that are saved, sent over the network, or shared with tools must use a fixed algorithm, never the language's default string hash.

=== "C++"

    ```cpp
    #include <string_view>

    constexpr std::uint64_t fnv1a(std::string_view s)
    {
        std::uint64_t h = 14695981039346656037ull;
        for (char c : s) {
            h ^= static_cast<unsigned char>(c);
            h *= 1099511628211ull;
        }
        return h;
    }

    constexpr std::uint64_t mix64(std::uint64_t x)              // SplitMix64 finaliser
    {
        x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ull;
        x ^= x >> 27; x *= 0x94d049bb133111ebull;
        return x ^ (x >> 31);
    }

    constexpr std::uint64_t hash_combine(std::uint64_t seed, std::uint64_t value)
    {
        return seed ^ (mix64(value) + 0x9e3779b97f4a7c15ull + (seed << 6) + (seed >> 2));
    }

    // Compile-time ids, including in switch labels:
    switch (fnv1a(action_name)) {
        case fnv1a("jump"):  jump();  break;
        case fnv1a("crouch"): crouch(); break;
    }
    ```

    - A `consteval` wrapper (`consteval std::uint64_t id(std::string_view s) { return fnv1a(s); }`) makes sure the hash is never computed at run time by accident.
    - `std::hash` is not `constexpr`, its results differ between standard libraries, and for integers it is often the identity, so run `mix64` over it before using it in an open-addressing table.

=== "C#"

    ```csharp
    public static ulong Fnv1a(string s)
    {
        ulong h = 14695981039346656037;
        foreach (char c in s) { h ^= c; h *= 1099511628211; }
        return h;
    }

    // Per-run hash for dictionary keys:
    public override int GetHashCode() => HashCode.Combine(X, Y, Layer);
    ```

    - `string.GetHashCode()` and `HashCode` are **randomised per process** on .NET Core and .NET 5+. They are fine for dictionaries and must never be saved or sent.
    - `Fnv1a` above hashes UTF-16 characters, which matches the C++ version for ASCII strings only. For other text, hash `Encoding.UTF8.GetBytes(s)`.
    - C# has no `constexpr`. Compute ids once into `static readonly` fields, or generate them at build time with a [source generator](../csharp/roslyn/index.md).
    - Unity: `Animator.StringToHash` and `Shader.PropertyToID` are the same idea for their own names.

!!! warning "Common pitfalls"

    `%` on a negative number is negative in C++ and C#. Use `floor_mod` for wrapped indices and grid cells.

    `align_up` with an alignment that is not a power of two gives a wrong answer without any error. Assert `is_pow2(a)` in debug builds.

    Mixing KiB and KB in one tool makes budgets look 5 to 7 % off. Pick one, and label it.

    A single global float epsilon is wrong for most of the values it is used on. Choose a tolerance per comparison.

    Saving `GetHashCode()` or `std::hash` results makes saves that break on the next run, or on another platform.
