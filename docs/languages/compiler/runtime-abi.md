# Runtime and ABI

Compiled code needs a little support that is not generated per program: an entry point, memory allocation, a way to stop with an error, and the layouts of strings and arrays. That is the language's **runtime**. Where compiled code meets C (the operating system, the C runtime, a game engine) it must also follow the platform's **ABI**: the rules for how values are passed and laid out.

## The runtime library

Keep it small, and write it in C at first. It is ordinary code, compiled once, and linked with every program:

```c
// runtime.c
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

_Noreturn void lang_panic(const char* message, const char* file, int32_t line) {
    fprintf(stderr, "%s:%d: panic: %s\n", file, line, message);
    abort();
}

void* lang_alloc(int64_t size, int64_t align) { return aligned_alloc(align, (size + align - 1) / align * align); }
void  lang_free(void* p) { free(p); }
```

```bash
cc -c runtime.c -o runtime.o
cc main.o runtime.o -o main
```

- **Prefix every runtime symbol** (`lang_`), so it cannot collide with user functions or C libraries.
- The compiler **declares** these functions in each module, like `extern` functions, and calls them where the language needs them.
- Later, much of the runtime can move into the language's own [standard library](standard-library.md). The parts that talk to the operating system stay in C or become `extern` declarations.

## The entry point

The C runtime starts the process and calls `main(argc, argv)`. Generate that function yourself, as a wrapper around the user's `main`:

```text
define i32 @main(i32 %argc, ptr %argv):
    call @lang_init(argc, argv)          // runtime setup: allocator, command-line arguments, globals
    %code = call @user.main()            // the program's own main, renamed so it does not clash
    call @lang_shutdown()
    ret %code
```

- Renaming the user's `main` (mangling every user symbol with a module prefix, as below) leaves the real `main` free for the wrapper.
- On Windows, linking with the MSVC C runtime (`clang main.obj runtime.obj`, or `link.exe` with `/subsystem:console`) gives the same `main` entry point.
- **Globals** with constant initialisers become LLVM globals with an initialiser. Globals that need code to compute (`let TABLE = build_table();`) are initialised in `lang_init`, in dependency order, before the user's `main`.

## Panics

A **panic** stops the program with a message and a source location. Bounds checks, failed conversions, division by zero, and explicit `panic("...")` all use it.

```csharp
LLVMTypeRef panicType = LLVMTypeRef.CreateFunction(_context.VoidType, new[] { ptr, ptr, i32 });
LLVMValueRef panic = _module.AddFunction("lang_panic", panicType);
uint noreturn = LLVMContextRef.GetEnumAttributeKindForName("noreturn");
panic.AddAttributeAtIndex(LLVMAttributeIndex.LLVMAttributeFunctionIndex, _context.CreateEnumAttribute(noreturn, 0));

void EmitPanic(string message, string file, int line)
{
    LLVMValueRef text = _builder.BuildGlobalStringPtr(message, "panic.msg");
    LLVMValueRef path = _builder.BuildGlobalStringPtr(file, "panic.file");
    _builder.BuildCall2(panicType, panic, new[] { text, path, LLVMValueRef.CreateConstInt(i32, (ulong)line) }, "");
    _builder.BuildUnreachable();          // tells LLVM control never continues past the call
}
```

The `noreturn` attribute and the `unreachable` after the call let LLVM treat the panic path as cold and move it out of the way of the fast path.

**Panics inside a game.** `abort()` is right for a command-line program and wrong for a script running in an editor. When the runtime is embedded, `lang_panic` calls a host callback instead: it logs the message and stops the script. Stopping it needs a way out of the script's stack frames: for a language without destructors, `setjmp` at the point where the engine calls into the script and `longjmp` from the panic is simple and works. With destructors or `defer`, you need real unwinding (LLVM's `invoke` and landing pads), which is a larger project. Never let a panic return into the code that caused it.

## Bounds checks

A **slice** is a pointer and a length. Indexing checks the index first:

```csharp
LLVMTypeRef sliceType = _context.GetStructType(new[] { ptr, i64 }, Packed: false);     // { ptr data, i64 length }

LLVMValueRef EmitIndex(LLVMValueRef function, LLVMValueRef slice, LLVMValueRef index, LLVMTypeRef elementType, int line)
{
    LLVMValueRef data = _builder.BuildExtractValue(slice, 0, "data");
    LLVMValueRef length = _builder.BuildExtractValue(slice, 1, "len");
    LLVMValueRef inBounds = _builder.BuildICmp(LLVMIntPredicate.LLVMIntULT, index, length, "in.bounds");   // unsigned: also rejects negatives
    LLVMBasicBlockRef ok = function.AppendBasicBlock("index.ok");
    LLVMBasicBlockRef fail = function.AppendBasicBlock("index.fail");
    _builder.BuildCondBr(inBounds, ok, fail);

    _builder.PositionAtEnd(fail);
    EmitPanic("index out of bounds", "main.lang", line);

    _builder.PositionAtEnd(ok);
    LLVMValueRef address = _builder.BuildInBoundsGEP2(elementType, data, new[] { index }, "elem.ptr");
    return _builder.BuildLoad2(elementType, address, "elem");
}
```

- **One unsigned comparison** covers both ends: a negative index, viewed as unsigned, is larger than any length.
- The optimiser removes checks it can prove are unnecessary, such as `for i in 0..s.len`. The checks that remain are usually cheap, because the branch is always predicted correctly.
- Offer an unchecked form for code that has measured the cost (`s.get_unchecked(i)` inside an `unsafe` block, say). Keep checks on by default, in release builds too.

## Data layout

| Value | Layout | Notes |
| --- | --- | --- |
| Fixed array `[4]f32` | `[4 x float]` | stored inline, like a struct; passed by pointer |
| Slice `[]T` | `{ ptr, i64 }` | a view: pointer and element count |
| String `str` | `{ ptr, i64 }` of UTF-8 bytes | a slice of `u8`; **not** null-terminated |
| Dynamic array `List<T>` | `{ ptr, i64 length, i64 capacity }` | owns its buffer; in the standard library, once generics exist |
| `bool` in memory | `i8` | `i1` only in registers; see [calling C](llvmsharp.md#calling-c) |
| Enum without data | the smallest integer that fits | `i8` for up to 256 cases |
| Tagged union | `{ tag, payload bytes }` sized for the largest case | see [unions](../../csharp/performance/unions.md) for the same layout in C# |

- **String literals** are global constants (an `[N x i8]` array) plus a slice pointing at them. Do not emit a null terminator into the string's length.
- Passing a string to C needs a **conversion** that copies it and appends a zero byte (`str.to_cstring()`), because C reads until the null.
- **Struct layout** follows LLVM's data layout for the target: fields in order, each aligned to its natural alignment, with padding. If users can lay out structs for C or for files, add an attribute for packed or explicit layout.

## Memory

The [language design](../design.md#memory-model) page covers the choices: manual, arenas, reference counting, tracing GC, or ownership. Whatever you choose, all allocation goes through **runtime functions** (`lang_alloc`, `lang_free`), never straight to `malloc`. One place to change later means you can:

- swap in a faster allocator, or a per-frame arena for scripts;
- count allocations, and report leaks at shutdown in debug builds;
- give the game engine control of memory when the language is embedded.

A garbage collector needs more from the compiler (it must find every pointer on the stack, through `gc.statepoint` or shadow stacks), which is a large step. Reference counting needs only calls to `lang_retain` and `lang_release` at copies and at the end of scopes, generated by the compiler.

## The C ABI

Your own functions can pass values however you like: LLVM chooses registers, and `internal` functions can even use a faster calling convention. Functions called **from or by C** must follow the platform's C ABI exactly, and LLVM does not do that for you. The front end (clang, in C's case) decides how each argument is passed, and different platforms decide differently:

| C function | Linux x86-64 | Windows x64 | Linux ARM64 |
| --- | --- | --- | --- |
| `float len_sq(Vec2 v)`, `Vec2 { float x, y; }` | `@len_sq(<2 x float>)` | `@len_sq(i64)` | `@len_sq([2 x float])` |
| `float dot3(Vec3 a, Vec3 b)` | `@dot3(<2 x float>, float, <2 x float>, float)` | `@dot3(ptr, ptr)` | `@dot3([3 x float], [3 x float])` |
| `Vec2 make(float, float)` | returns `<2 x float>` | returns `i64` | returns `%Vec2` |
| `double first(Big b)`, a 32-byte struct | `ptr byval(%Big)` | `ptr` (a copy made by the caller) | `[4 x double]` |

Passing `%Vec2` by value, as the [code generator](llvmsharp.md#calling-c) would for an internal function, matches none of these. Options, in order of effort:

1. **Pass structs to C by pointer**, and return them through an out pointer. Scalars and pointers are passed the same way on every platform. This is enough for most engines and libraries.
2. **Ask clang** what the signature should be: write the C prototype, run `clang -O1 -S -emit-llvm --target=<triple> abi.c`, and generate exactly that signature for `extern` functions, converting at the call site. The table above was produced this way.
3. **Implement the ABI rules** for each target you support (x86-64 System V classification, Windows x64, AArch64 AAPCS), as clang, Rust, Zig, and Swift each do. This is real work; do it when a library you must call passes structs by value.

### Symbol names

- **Mangle** user functions with their module path (`game.physics.step` becomes `game$physics$step`, or a scheme like Rust's or C++'s), so two modules can both have a `step`, and nothing collides with C.
- **Do not mangle** `extern` declarations and functions marked for export: their names are the C names.
- Keep the mangling **reversible**, so stack traces and profilers can show the original names (or record the original name in the [debug info](debug-info.md)).

!!! warning "Common pitfalls"

    Passing a struct by value to a C function compiles, links, and passes garbage. Pass a pointer, or generate the exact signature clang would.

    `bool` fields shared with C must be `i8`. An `i1` in memory is stored as a byte anyway, but loads and stores of `i1` from C-written memory assume only the lowest bit is set.

    Strings passed to C without a terminating zero are read past their end.

    A panic that returns, or that is not marked `noreturn` and followed by `unreachable`, lets execution continue into code that assumed the check passed.

    Calling `malloc` directly from generated code makes it impossible to replace the allocator later. Route every allocation through the runtime.
