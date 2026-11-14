# Standard library

The **standard library** is the code every program can use without writing it: maths, strings, collections, printing, files. Most of it should be written in the language itself, on top of a thin layer of [intrinsics](#intrinsics) and [runtime](runtime-abi.md) functions. Writing it is also the best test of the language: every awkward rule shows up there first.

## Layers

| Layer | Contains | Written in |
| --- | --- | --- |
| Built into the compiler | primitive types, operators, `as`, the slice and string types | the compiler |
| Intrinsics | `sqrt`, `abs`, `floor`, `min`/`max`, `count_ones`, `memcpy`, overflow-checked arithmetic | declarations in the library, implemented by the code generator |
| Core | `Option`, `Result`, slices and string functions, maths, `List`, `Map`, sorting, formatting | the language |
| Platform | printing, files, time, threads, environment | the language, over `extern` C functions or engine functions |
| Prelude | the names every file sees without importing | a list of re-exports |

Keep **core** free of the platform layer, so it also works where there is no operating system: inside a game engine, on a console, or in a sandboxed script.

## Writing it in the language

```text
// std/math.lang
pub fn clamp(x: f32, lo: f32, hi: f32) -> f32 {
    if x < lo { return lo; }
    if x > hi { return hi; }
    return x;
}

#[intrinsic("llvm.sqrt")]
pub fn sqrt(x: f32) -> f32;

pub struct Vec2 { x: f32, y: f32 }

pub fn length(v: Vec2) -> f32 {
    return sqrt(v.x * v.x + v.y * v.y);
}
```

How it reaches each program:

- **Compile it with every program.** The compiler includes the library's source files in every compilation. Simple, and LLVM can inline small functions like `clamp` into the caller. Costs compile time once the library is large.
- **Precompile it.** Compile the library once into an object file or static library, plus a file of its public **signatures** (a metadata file the binder loads instead of the source). Faster builds; small functions need cross-module inlining (LLVM bitcode and link-time optimisation) to stay fast.

Start with the first. Move to the second when the library's compile time is noticeable, and keep small, hot functions inline-able either way (bitcode for the library, or an `#[inline]` attribute that copies the body into each program).

## Intrinsics

An **intrinsic** is a library function the code generator implements directly, usually as one instruction. The library declares it with an attribute and no body; the binder treats it as an ordinary function; code generation emits the LLVM intrinsic instead of a call:

| Library function | LLVM intrinsic | Usually becomes |
| --- | --- | --- |
| `sqrt(x)` | `llvm.sqrt.f32` | one `sqrtss` |
| `abs(x)` for floats | `llvm.fabs.f32` | clearing the sign bit |
| `floor`, `ceil`, `trunc`, `round_even` | `llvm.floor`, `llvm.ceil`, `llvm.trunc`, `llvm.roundeven` | one instruction with SSE4.1 or ARM64 (`llvm.round`, halves away from zero, takes a few more on x86) |
| `min`, `max` for floats | `llvm.minnum`, `llvm.maxnum` | `minss`, `maxss` (with NaN handling) |
| `fma(a, b, c)` | `llvm.fma` | one fused multiply-add, where supported |
| `count_ones`, `leading_zeros`, `trailing_zeros` | `llvm.ctpop`, `llvm.ctlz`, `llvm.cttz` | `popcnt`, `lzcnt`, `tzcnt` |
| `checked_add` | `llvm.sadd.with.overflow` | `add` and a branch on the overflow flag |
| `copy(dst, src)` on slices | `llvm.memcpy` | `rep movs`, or a call to `memcpy` |

```text
emit_call(call):
    f = call.function
    if f has an intrinsic attribute:
        return call_intrinsic(f.intrinsic_name, overload types from the argument types, arguments)
    ...normal call
```

[Code generation](llvmsharp.md#conversions) has the `CallIntrinsic` helper. The [constant folder](lowering.md#constant-folding) should know the same intrinsics, so `sqrt(16.0)` in a constant becomes `4.0`.

## The prelude

The **prelude** is a list of library names imported into every file: common types (`Option`, `List`, `Vec2`), functions (`print`, `min`, `max`), and anything the compiler's own lowering refers to.

In the [binder](binding.md#scopes), it is one more scope between the global scope and each module's scope. A user definition with the same name shadows the prelude's, without an error, so adding a name to the prelude cannot break existing programs.

**Lang items** are library items the compiler itself needs: the panic function, `Option` for `?` or optional chaining, the iterator interface behind `for x in list`. Mark them in the library (`#[lang("panic")]`) and look them up by marker, not by name, so users can still define their own `Option`.

## Printing and formatting

- Do not expose C's `printf`. Its format string is untyped, and a wrong specifier is memory corruption. Write `print` in the language, formatting each value by its type, and send the bytes to the runtime (`lang_write(fd, ptr, len)` over C's `fwrite`, or the engine's log).
- Formatting numbers is surprisingly hard to do well (shortest round-trip float printing in particular). Call C's `snprintf` with a fixed, correct format for each primitive from inside the library, until you have a reason to replace it.
- String interpolation (`"hp: {hp}"`) is a [lexer](lexer.md) and lowering feature that becomes calls to the same formatting functions.

## A library for game code

For a game scripting language, the most important part of the library is the **engine API**:

- **Maths types** (`Vec2`, `Vec3`, `Quat`, `Mat4`) with the same memory layout as the engine's, so values pass to the engine without conversion. Use `f32` and the engine's field order; check the sizes with tests on both sides.
- **Engine functions** as `extern` declarations, generated from the engine's headers or from attributes on the engine's functions, never written by hand. A [source generator](../../csharp/roslyn/source-generators.md) or a small tool keeps them in sync.
- **Handles, not pointers**, for engine objects, as the [design page](../design.md#memory-model) explains: `Entity` is a 64-bit id, and every engine call checks it.

## Versioning

Once other people write code against the library, changing it breaks them:

- Mark public items explicitly (`pub`); everything else can change freely.
- **Deprecate** before removing: a `#[deprecated("use length_squared")]` attribute that the binder turns into a warning at each use.
- Test the library **in the language**, with `#[test]` functions the compiler can run (through the [JIT](llvmsharp.md#jit-with-orc)), so library tests do not depend on the C# test project.

## C# tips

- Ship the library's source inside the compiler as **embedded resources** (`<EmbeddedResource Include="std/**/*.lang" />`, read with `Assembly.GetManifestResourceStream`), so the compiler cannot run with a mismatched library.
- Bind the library **once** and reuse the result across compilations: symbols are immutable after binding, so a cached `BoundProgram` for the library can be shared safely between an editor's many recompilations.
- Map intrinsic names to code-generator functions with a `FrozenDictionary<string, Func<...>>`, and fail at compile time (not at code generation) when the library declares an intrinsic the code generator does not know.
