# Numeric types and conversions

The rules for mixing numeric types are small to state and easy to get subtly wrong: which conversions happen without being asked, what `u8 + u8` produces, what a float that does not fit in an `i32` becomes, and what overflow does. Each choice is visible to users, so decide them on purpose, write them down, and make the [type checker](types.md#conversions), the [code generator](llvmsharp.md#conversions), and the [reference evaluator](evaluator.md) agree.

## Widening and narrowing

A conversion is **widening** when every value of the source type exists in the target type, and **narrowing** when some do not.

| From | To | Kind | Exact? |
| --- | --- | --- | --- |
| `i8` → `i16` → `i32` → `i64` | larger signed | widening | yes |
| `u8` → `u16` → `u32` → `u64` | larger unsigned | widening | yes |
| `u8`, `u16`, `u32` | a larger **signed** type (`u32` → `i64`) | widening | yes |
| any signed | any unsigned (`i32` → `u64`) | narrowing | no: negative values do not exist |
| larger integer | smaller integer | narrowing | no |
| `f32` → `f64` | | widening | yes |
| `f64` → `f32` | | narrowing | rounds; large values become infinity |
| `i32` → `f64` | | widening | yes: every `i32` is exactly a `double` |
| `i32` → `f32`, `i64` → `f64` | | **looks** widening | no: above 2^24 (`f32`) or 2^53 (`f64`), integers round |
| float → integer | | narrowing | no: fractions, NaN, and out-of-range values |

The usual policy: **widening is implicit, everything else needs `as`.** Treat the "looks widening" row as narrowing, or `let f: f32 = 16777217;` silently stores 16777216.

## Promotion

**Promotion** is what the language does to operands before an operation.

| Policy | `a: u8 + b: u8` | Seen in |
| --- | --- | --- |
| Integer promotion | both become `int`; the result is `int` | C, C++, C# (`byte + byte` is `int`) |
| Same type in, same type out | `u8`; overflow wraps or traps at 8 bits | Rust, Zig, Swift, Go |
| Usual arithmetic conversions | mixed operands are converted to a common type first (`i32 + i64` is `i64`) | C, C++, C# |

C's rules have well-known traps: in C, `-1 < 1u` is **false**, because `-1` converts to a huge unsigned value. C#'s `byte + byte` producing `int` forces a cast for every small-integer assignment.

For a new language, the **same-type rule** is the easiest to explain and to implement:

- Binary arithmetic and comparisons need both operands to have the **same type**, after widening a literal to the other operand's type (see [literals](types.md#literals)).
- Mixed types (`i32 + i64`, `i32 < u32`) are errors with a suggested cast: "cannot add 'i32' and 'i64'; convert one side with 'as'".
- Allowing **implicit widening** of one operand (`i32 + i64` → `i64`) is a reasonable relaxation. Never implicitly mix signed and unsigned.

## Explicit conversions

What `as` does for each pair, and the LLVM instruction behind it:

| Conversion | Result | LLVM |
| --- | --- | --- |
| larger → smaller integer | keep the low bits: `300 as u8` is 44 | `trunc` |
| smaller → larger, from signed | copy the sign bit up: `-1 as i64` is −1 | `sext` |
| smaller → larger, from unsigned | fill with zeros: `255u8 as i32` is 255 | `zext` |
| same size, signed ↔ unsigned | the same bits: `-1 as u32` is 4294967295 | nothing |
| integer → float | nearest float | `sitofp`, `uitofp` |
| `f64` → `f32` | nearest float; out of range is ±infinity | `fptrunc` |
| float → integer | **choose**: see below | `fptosi` / `fptoui`, or the `.sat` intrinsics |

### Float to integer

LLVM's `fptosi` returns **poison** (an undefined value that can make later code behave arbitrarily) for NaN and for values outside the target type. A language must define the result:

| Policy | `1e20 as i32` | `NaN as i32` | Cost |
| --- | --- | --- | --- |
| Saturate | 2147483647 | 0 | one intrinsic (`llvm.fptosi.sat`), a few instructions |
| Trap | runtime error | runtime error | a range check and a branch |
| Undefined | anything | anything | none, and a source of heisenbugs |

Saturation is what Rust and .NET 9 and later do, and what the [code generator](llvmsharp.md#conversions) emits. Pair it with **checked** conversions in the standard library (`i32.try_from(x)` returning an optional value) for code that needs to know.

## Overflow

What `i32.MAX + 1` does is the same kind of decision:

| Policy | Result | LLVM |
| --- | --- | --- |
| Wrap | −2147483648 | `add` |
| Trap | runtime error at the operation | `llvm.sadd.with.overflow` + branch to a [panic](runtime-abi.md#panics) |
| Saturate | 2147483647 | `llvm.sadd.sat` |
| Undefined | anything | `add nsw` |

A common split: **trap in debug builds, wrap in release builds** (Rust's default), with explicit `wrapping_add`, `saturating_add`, and `checked_add` functions for code that means one of them. Never choose "undefined" for a language that game scripters write.

## Shifts and division

- **Shifts**: in LLVM, shifting by the type's bit width or more returns poison. Define it: mask the amount (`x << (n & 31)`, what x86 and C# do), or trap. Right shift of a signed value is `ashr` (copies the sign); of unsigned is `lshr`.
- **Division and remainder by zero** are undefined in LLVM, and so is `INT_MIN / -1`. Emit a check and a [panic](runtime-abi.md#panics) before `sdiv` and `srem`, unless the divisor is a non-zero constant.
- **Remainder sign**: `srem` follows the dividend (`-7 % 3` is −1), as in C and C#. If you want a non-negative modulo, provide a separate function rather than changing `%`.
- **Comparisons** pick the predicate from the type: `slt` for signed, `ult` for unsigned, `olt` for floats (false when either is NaN).

## Floating point

- **NaN** compares unequal to everything, including itself. `==` on floats is `fcmp oeq`; `!=` should be `fcmp une` (true when either is NaN), so that `x != x` detects NaN.
- **Fast-math flags** (`nnan`, `ninf`, `contract`, `reassoc`) let LLVM reorder and fuse float operations, which changes results slightly. Leave them off by default; offer them per function or per build for code that opts in.
- **Constant folding** must use the target type's precision. Folding an `f32` expression in `double` and rounding at the end gives a different answer than the compiled code.

## C# tips

- Use C#'s own conversions carefully when implementing these rules in the evaluator or the constant folder. `unchecked((byte)300)` truncates to 44 like `trunc`. `(int)1e20f` saturates to `int.MaxValue` on .NET 9 and later, matching `fptosi.sat`, but returned `int.MinValue` on .NET 8 and earlier.
- Conversions to **small** integer types do not saturate in C#: `(byte)300.7f` is 44 (the value goes through `int` and is then truncated), where `llvm.fptoui.sat.i8` gives 255. Clamp explicitly (`(byte)Math.Clamp(MathF.Truncate(f), 0, 255)`) when matching the language's rule.
- Compute folded `f32` arithmetic in `float`, not `double`: `(float)(a + b)` with `double` operands can round differently from `a + b` with `float` operands.
- `int.MaxValue + 1` in an `unchecked` context wraps; in a `checked` context it throws `OverflowException`. Compile the constant folder with the context that matches the language, or use the explicit `int.CreateTruncating` / `int.CreateSaturating` / `int.CreateChecked` generic-math methods, which say what they do.
