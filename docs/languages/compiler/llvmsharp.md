---
package: LLVMSharp.Interop 22.1
---

# Code generation with LLVMSharp

The last stage turns the [lowered](lowering.md) program into LLVM IR, and LLVM turns that into machine code. [LLVM](../llvm.md) explains the IR, SSA, passes, and targets; this page is the C# code that maps the example language's constructs onto them with [LLVMSharp](https://github.com/dotnet/LLVMSharp). Because the API is the point here, this page is C# rather than pseudocode.

## Setup

```xml
<PropertyGroup>
  <TargetFramework>net10.0</TargetFramework>
  <AllowUnsafeBlocks>true</AllowUnsafeBlocks>        <!-- the JIT and some C API calls take pointers -->
  <RuntimeIdentifier>linux-x64</RuntimeIdentifier>   <!-- or win-x64, osx-arm64: selects the native libLLVM -->
</PropertyGroup>
<ItemGroup>
  <PackageReference Include="LLVMSharp.Interop" Version="22.1.8" />
</ItemGroup>
```

- `LLVMSharp.Interop` 22.1 targets **.NET 10** only. It wraps the LLVM C API one-to-one, with friendlier methods on handle structs (`LLVMModuleRef`, `LLVMBuilderRef`, `LLVMValueRef`). Use it rather than the older object-model `LLVMSharp` package.
- The native library comes from the `libLLVM.runtime.<rid>` package, which is only restored when a **runtime identifier** is set. Without one, the build succeeds and the first call throws `DllNotFoundException`.
- On Linux, that `libLLVM.so` needs `libz3.so.4` installed (`apt install libz3-4`); a missing Z3 also shows up as `DllNotFoundException: libLLVM`.
- The bindings and libLLVM must be the **same major version**. Pin the package version.

## The code generator

```csharp
using LLVMSharp.Interop;

public sealed class CodeGenerator : IDisposable
{
    readonly LLVMContextRef _context = LLVMContextRef.Create();
    readonly LLVMModuleRef _module;
    readonly LLVMBuilderRef _builder;

    readonly Dictionary<FunctionSymbol, (LLVMValueRef Function, LLVMTypeRef Type)> _functions = new();
    readonly Dictionary<StructSymbol, LLVMTypeRef> _structs = new();
    readonly Dictionary<Symbol, LLVMValueRef> _locals = new();          // locals and parameters: their alloca
    readonly Dictionary<BoundLabel, LLVMBasicBlockRef> _blocks = new();

    public CodeGenerator(string moduleName)
    {
        _module = _context.CreateModuleWithName(moduleName);
        _builder = _context.CreateBuilder();
    }

    public LLVMModuleRef Generate(BoundProgram program)
    {
        foreach (StructSymbol s in program.Structs) DeclareStruct(s);    // names first: fields may refer to each other
        foreach (StructSymbol s in program.Structs) DefineStruct(s);
        foreach (FunctionSymbol f in program.Functions) DeclareFunction(f);   // so calls can come before definitions
        foreach (var (f, body) in program.Bodies) EmitBody(f, body);
        return _module;
    }

    public void Dispose()
    {
        _builder.Dispose();
        _module.Dispose();      // skip both if the module and context were given to the JIT
        _context.Dispose();
    }
}
```

The same order as the [binder](binding.md#binding-in-passes): declare everything, then fill in bodies.

## Types

| Language | LLVM | LLVMSharp |
| --- | --- | --- |
| `i8`, `i16`, `i32`, `i64` (and unsigned) | `i8` ... `i64` | `_context.Int32Type`; signedness lives in the instructions, not the type |
| `bool` | `i1` | `_context.Int1Type` (stored as `i8` in memory by C; see below) |
| `f32`, `f64` | `float`, `double` | `_context.FloatType`, `_context.DoubleType` |
| `void` | `void` | `_context.VoidType` |
| `*T` | `ptr` | `LLVMTypeRef.CreatePointer(_context.Int8Type, 0)`: pointers are untyped |
| `struct Vec2 { x: f32, y: f32 }` | `%Vec2 = type { float, float }` | `_context.CreateNamedStruct("Vec2")` then `StructSetBody` |

```csharp
LLVMTypeRef Lower(TypeSymbol type) => type switch
{
    _ when type == TypeSymbol.Bool => _context.Int1Type,
    { IsInteger: true }            => _context.GetIntType((uint)type.SizeInBits),   // i8 .. i64, u8 .. u64
    { IsFloat: true, SizeInBits: 32 } => _context.FloatType,
    { IsFloat: true, SizeInBits: 64 } => _context.DoubleType,
    _ when type == TypeSymbol.Void => _context.VoidType,
    PointerType                    => LLVMTypeRef.CreatePointer(_context.Int8Type, 0),
    StructType s                   => _structs[s.Symbol],
    _ => throw new UnreachableException($"No LLVM type for {type}"),
};

void DeclareStruct(StructSymbol s) => _structs[s] = _context.CreateNamedStruct(s.Name);

void DefineStruct(StructSymbol s) =>
    _structs[s].StructSetBody(s.Fields.Select(f => Lower(f.Type)).ToArray(), Packed: false);
```

Signed and unsigned integers are the same LLVM type. The difference is in the instruction you choose: `BuildSDiv` or `BuildUDiv`, `LLVMIntSLT` or `LLVMIntULT`, `BuildSExt` or `BuildZExt`.

## Functions and locals

```csharp
void DeclareFunction(FunctionSymbol f)
{
    LLVMTypeRef[] parameters = f.Parameters.Select(p => Lower(p.Type)).ToArray();
    LLVMTypeRef type = LLVMTypeRef.CreateFunction(Lower(f.ReturnType), parameters, IsVarArg: false);
    LLVMValueRef function = _module.AddFunction(f.Name, type);
    if (!f.IsExtern && !f.IsExported) function.Linkage = LLVMLinkage.LLVMInternalLinkage;
    _functions[f] = (function, type);
}

void EmitBody(FunctionSymbol f, BoundBlock body)
{
    var (function, _) = _functions[f];
    _locals.Clear();
    _blocks.Clear();

    _builder.PositionAtEnd(function.AppendBasicBlock("entry"));

    // Every parameter and local gets a stack slot in the entry block.
    for (int i = 0; i < f.Parameters.Length; i++)
    {
        ParameterSymbol p = f.Parameters[i];
        LLVMValueRef slot = _builder.BuildAlloca(Lower(p.Type), p.Name);
        _builder.BuildStore(function.GetParam((uint)i), slot);
        _locals[p] = slot;
    }
    foreach (LocalSymbol local in body.Locals)
        _locals[local] = _builder.BuildAlloca(Lower(local.Type), local.Name);

    foreach (BoundStatement statement in body.Statements)
        EmitStatement(function, statement);

    // Close the last block: a void function returns; otherwise it is the dead block after the final return.
    if (!CurrentBlockTerminated())
    {
        if (f.ReturnType == TypeSymbol.Void) _builder.BuildRetVoid();
        else _builder.BuildUnreachable();       // the missing-return check guarantees no path reaches it
    }
}
```

- **Every local is an `alloca`** in the entry block, read with `BuildLoad2` and written with `BuildStore`. This avoids building SSA and phi nodes yourself: the `mem2reg` / SROA pass (part of `default<O1>` and above) turns the slots into SSA registers. Keep allocas in the entry block; one inside a loop allocates stack on every iteration.
- **Internal linkage** for everything except `main`, exported functions, and externs lets LLVM inline and delete functions that are no longer called.
- Names (`"entry"`, `p.Name`) only make the IR readable. LLVM makes them unique, and they can be empty strings.

## Expressions

```csharp
LLVMValueRef EmitExpression(BoundExpression e) => e switch
{
    BoundLiteral { Value: long v } l   => LLVMValueRef.CreateConstInt(Lower(l.Type), unchecked((ulong)v), SignExtend: true),
    BoundLiteral { Value: double d } l => LLVMValueRef.CreateConstReal(Lower(l.Type), d),
    BoundLiteral { Value: bool b }     => LLVMValueRef.CreateConstInt(_context.Int1Type, b ? 1UL : 0UL),
    BoundVariable v      => _builder.BuildLoad2(Lower(v.Type), _locals[v.Symbol], v.Symbol.Name),
    BoundUnary u         => EmitUnary(u),
    BoundBinary b        => EmitBinary(b),
    BoundCall c          => EmitCall(c),
    BoundFieldAccess f   => _builder.BuildLoad2(Lower(f.Type), EmitAddress(f), f.Field.Name),
    BoundAssignment a    => EmitAssignment(a),
    BoundConversion c    => EmitConversion(c),
    _ => throw new UnreachableException($"Unexpected {e.GetType().Name}"),
};

LLVMValueRef EmitBinary(BoundBinary b)
{
    LLVMValueRef l = EmitExpression(b.Left), r = EmitExpression(b.Right);
    return b.Operator.Kind switch
    {
        BinaryOperatorKind.IntAdd      => _builder.BuildAdd(l, r, "add"),
        BinaryOperatorKind.IntSub      => _builder.BuildSub(l, r, "sub"),
        BinaryOperatorKind.IntMul      => _builder.BuildMul(l, r, "mul"),
        BinaryOperatorKind.IntDiv      => _builder.BuildSDiv(l, r, "div"),
        BinaryOperatorKind.IntLess     => _builder.BuildICmp(LLVMIntPredicate.LLVMIntSLT, l, r, "lt"),
        BinaryOperatorKind.IntEquals   => _builder.BuildICmp(LLVMIntPredicate.LLVMIntEQ, l, r, "eq"),
        BinaryOperatorKind.FloatAdd    => _builder.BuildFAdd(l, r, "fadd"),
        BinaryOperatorKind.FloatMul    => _builder.BuildFMul(l, r, "fmul"),
        BinaryOperatorKind.FloatEquals => _builder.BuildFCmp(LLVMRealPredicate.LLVMRealOEQ, l, r, "feq"),
        _ => throw new UnreachableException($"Unexpected operator {b.Operator.Kind}"),
    };
}
```

```csharp
LLVMValueRef EmitUnary(BoundUnary u)
{
    LLVMValueRef operand = EmitExpression(u.Operand);
    return u.Operator.Kind switch
    {
        UnaryOperatorKind.IntNegate   => _builder.BuildNeg(operand, "neg"),
        UnaryOperatorKind.FloatNegate => _builder.BuildFNeg(operand, "fneg"),
        UnaryOperatorKind.LogicalNot  => _builder.BuildNot(operand, "not"),    // flips an i1
        _ => throw new UnreachableException($"Unexpected operator {u.Operator.Kind}"),
    };
}
```

- **Integer overflow**: `BuildAdd` wraps (two's complement). `BuildNSWAdd` tells LLVM signed overflow cannot happen, which is undefined behaviour if it does. Use the plain forms unless the language says overflow is undefined; for "trap on overflow", call the `llvm.sadd.with.overflow` intrinsic and branch on its flag.
- **Division by zero** and `INT_MIN / -1` are undefined behaviour in LLVM's `sdiv`. If the language defines them, emit a check and a branch before the division.
- `&&` and `||` were already lowered to jumps, so there is no short-circuit case here.

### Conversions

Every implicit and explicit conversion is a `BoundConversion` by now, so this is the only place that picks a cast instruction. The rules themselves are on [numeric types and conversions](numeric-conversions.md). `TypeSymbol` here has `IsInteger`, `IsSigned`, `IsFloat`, and `SizeInBits` for primitive types.

```csharp
LLVMValueRef EmitConversion(BoundConversion c)
{
    LLVMValueRef value = EmitExpression(c.Operand);
    TypeSymbol from = c.Operand.Type, to = c.Type;
    LLVMTypeRef target = Lower(to);

    if (from.IsInteger && to.IsInteger)
    {
        if (to.SizeInBits < from.SizeInBits) return _builder.BuildTrunc(value, target, "trunc");
        if (to.SizeInBits > from.SizeInBits)
            return from.IsSigned ? _builder.BuildSExt(value, target, "sext") : _builder.BuildZExt(value, target, "zext");
        return value;                                       // i32 <-> u32: the same bits
    }
    if (from.IsInteger && to.IsFloat)
        return from.IsSigned ? _builder.BuildSIToFP(value, target, "sitofp") : _builder.BuildUIToFP(value, target, "uitofp");
    if (from.IsFloat && to.IsFloat)
        return to.SizeInBits > from.SizeInBits ? _builder.BuildFPExt(value, target, "fpext") : _builder.BuildFPTrunc(value, target, "fptrunc");
    if (from.IsFloat && to.IsInteger)
    {
        // fptosi/fptoui give poison when the value does not fit (NaN, 1e20 as i32). The .sat
        // intrinsics clamp to the type's range and turn NaN into 0, so every input has an answer.
        string name = to.IsSigned ? "llvm.fptosi.sat" : "llvm.fptoui.sat";
        LLVMTypeRef source = Lower(from);
        return CallIntrinsic(name, new[] { target, source }, LLVMTypeRef.CreateFunction(target, new[] { source }), value);
    }
    throw new UnreachableException($"No conversion from {from} to {to}");
}

LLVMValueRef CallIntrinsic(string name, LLVMTypeRef[] overloadTypes, LLVMTypeRef functionType, params LLVMValueRef[] args)
{
    uint id = LookupIntrinsicId(name);
    LLVMValueRef function = _module.GetIntrinsicDeclaration(id, overloadTypes);   // e.g. llvm.fptosi.sat.i32.f32
    return _builder.BuildCall2(functionType, function, args, "");
}

static unsafe uint LookupIntrinsicId(string name)
{
    using var marshalled = new MarshaledString(name);
    uint id = LLVM.LookupIntrinsicID(marshalled, (nuint)name.Length);
    return id != 0 ? id : throw new ArgumentException($"Unknown intrinsic {name}");
}
```

`CallIntrinsic` also covers maths built-ins: `llvm.sqrt`, `llvm.fabs`, `llvm.floor`, `llvm.fma`, and `llvm.memcpy` become single instructions where the target has them. See [the standard library](standard-library.md#intrinsics).

### Addresses: fields and assignment

A field access or an assignment target needs an **address**, not a value:

```csharp
LLVMValueRef EmitAddress(BoundExpression e) => e switch
{
    BoundVariable v => _locals[v.Symbol],
    BoundFieldAccess f => _builder.BuildStructGEP2(
        _structs[((StructType)f.Receiver.Type).Symbol], EmitAddress(f.Receiver), (uint)f.Field.Index, f.Field.Name),
    _ => throw new UnreachableException("Not an assignable expression"),
};

LLVMValueRef EmitAssignment(BoundAssignment a)
{
    LLVMValueRef value = EmitExpression(a.Value);
    _builder.BuildStore(value, EmitAddress(a.Target));
    return value;
}
```

A struct value that is not stored anywhere (the result of a call, say) has no address. Store it in a temporary `alloca` first, or use `BuildExtractValue` to read one field from the value.

### Calls

```csharp
LLVMValueRef EmitCall(BoundCall c)
{
    var (function, type) = _functions[c.Function];
    LLVMValueRef[] args = c.Arguments.Select(EmitExpression).ToArray();
    string name = c.Function.ReturnType == TypeSymbol.Void ? "" : "call";     // a void call cannot have a name
    return _builder.BuildCall2(type, function, args, name);
}
```

- `BuildCall2`, `BuildLoad2`, and `BuildGEP2` take the **type explicitly**, because pointers no longer carry one. Keep each function's `LLVMTypeRef` next to its value, as `_functions` does.
- Pass an **array** (`args`, or `new LLVMValueRef[] { x }`), not a collection expression `[x]`: `BuildCall2` has array and span overloads, and `[x]` with a string name is ambiguous.

## Control flow

Each label from lowering becomes a basic block; gotos become branches.

```csharp
void EmitStatement(LLVMValueRef function, BoundStatement s)
{
    switch (s)
    {
        case BoundLabelStatement l:
            LLVMBasicBlockRef block = BlockFor(function, l.Label);
            if (!CurrentBlockTerminated()) _builder.BuildBr(block);     // fall through into the label
            _builder.PositionAtEnd(block);
            break;
        case BoundGotoStatement g:
            _builder.BuildBr(BlockFor(function, g.Label));
            StartUnreachableBlock(function);
            break;
        case BoundConditionalGotoStatement g:
            LLVMBasicBlockRef target = BlockFor(function, g.Label);
            LLVMBasicBlockRef next = function.AppendBasicBlock("next");
            LLVMValueRef condition = EmitExpression(g.Condition);
            if (g.JumpIfTrue) _builder.BuildCondBr(condition, target, next);
            else _builder.BuildCondBr(condition, next, target);
            _builder.PositionAtEnd(next);
            break;
        case BoundReturnStatement r:
            if (r.Expression is null) _builder.BuildRetVoid();
            else _builder.BuildRet(EmitExpression(r.Expression));
            StartUnreachableBlock(function);
            break;
        case BoundExpressionStatement e:
            EmitExpression(e.Expression);
            break;
    }
}

LLVMBasicBlockRef BlockFor(LLVMValueRef function, BoundLabel label) =>
    _blocks.TryGetValue(label, out var b) ? b : _blocks[label] = function.AppendBasicBlock(label.Name);

bool CurrentBlockTerminated() => _builder.InsertBlock.Terminator.Handle != IntPtr.Zero;

// Code after a jump or return is unreachable, but the builder still needs somewhere to put it.
void StartUnreachableBlock(LLVMValueRef function) =>
    _builder.PositionAtEnd(function.AppendBasicBlock("dead"));
```

- **Every block must end in exactly one terminator** (`br`, `ret`, `unreachable`), and nothing may follow it. Putting dead code in a fresh block keeps that true; the optimiser deletes the empty or unreachable blocks.
- The `BuildUnreachable` at the end of `EmitBody` relies on the [missing-return check](lowering.md#flow-checks): no real path can reach the end of a non-`void` function.
- The order of `AppendBasicBlock` calls is the order blocks appear in the printed IR. It does not affect correctness.

## Calling C

Declare the function and call it like any other. `putchar` from the example language:

```csharp
LLVMTypeRef putcharType = LLVMTypeRef.CreateFunction(_context.Int32Type, new[] { _context.Int32Type });
LLVMValueRef putchar = _module.AddFunction("putchar", putcharType);      // a declaration: no blocks
```

- **Scalars and pointers** pass as you would expect. **Structs by value** do not: each platform's C ABI splits, packs, or passes them in memory by rules that LLVM leaves to the front end (clang implements them). Pass structs to C by pointer until you are ready to implement the ABI.
- C's `bool` is one byte in memory. Use `i8` for a `bool` field in a struct shared with C, and `i1` only for values in registers.
- **String literals**: `_builder.BuildGlobalStringPtr("hello\n", "str")` makes a null-terminated constant and returns a pointer to it, ready to pass to `puts` or `printf`. Declare `printf` with `IsVarArg: true`.

## Verify, optimise, emit

```csharp
LLVM.InitializeNativeTarget();
LLVM.InitializeNativeAsmPrinter();
LLVM.InitializeNativeAsmParser();

if (!module.TryVerify(LLVMVerifierFailureAction.LLVMReturnStatusAction, out string verifyError))
    throw new InvalidOperationException(verifyError);          // a bug in the code generator, not the user's code

string triple = LLVMTargetRef.DefaultTriple;
LLVMTargetRef target = LLVMTargetRef.GetTargetFromTriple(triple);
LLVMTargetMachineRef machine = target.CreateTargetMachine(
    triple, "generic", "",                                      // or the host CPU, for a JIT
    LLVMCodeGenOptLevel.LLVMCodeGenLevelDefault, LLVMRelocMode.LLVMRelocPIC, LLVMCodeModel.LLVMCodeModelDefault);

module.Target = triple;
module.DataLayout = Marshal.PtrToStringAnsi((nint)LLVM.CopyStringRepOfTargetData(machine.CreateTargetDataLayout()))!;

LLVMPassBuilderOptionsRef options = LLVMPassBuilderOptionsRef.Create();
if (!module.TryRunPasses("default<O2>", machine, options, out string passError))
    throw new InvalidOperationException(passError);
options.Dispose();

if (!machine.TryEmitToFile(module, "main.o", LLVMCodeGenFileType.LLVMObjectFile, out string emitError))
    throw new InvalidOperationException(emitError);
LLVM.DisposeTargetMachine(machine);                             // LLVMTargetMachineRef has no Dispose method
```

Then link with the platform's linker, which also brings in the C runtime that calls `main`:

```bash
cc main.o -o main
```

On Windows, `clang main.obj -o main.exe` or `lld-link` with the MSVC runtime libraries. Dump `module.PrintToString()` before and after the passes while writing the code generator; reading the IR is how most bugs are found. The [LLVM page](../llvm.md#verifying-and-optimising) has more on pipelines and optimisation levels.

## JIT with ORC

For a REPL, running tests in process, or scripts compiled while a game runs, LLJIT compiles the module in memory and returns a function pointer. The C API is used directly, through `LLVM.Orc*`:

```csharp
static unsafe class Jit
{
    static LLVMOrcOpaqueLLJIT* _jit;

    // Ownership of the context and module moves into the JIT: do not use or dispose them afterwards.
    public static nint AddModuleAndLookup(LLVMContextRef context, LLVMModuleRef module, string name)
    {
        if (_jit == null)
        {
            LLVMOrcOpaqueLLJIT* jit;
            Check(LLVM.OrcCreateLLJIT(&jit, null));             // null builder: target the host
            _jit = jit;

            // Resolve undefined symbols (putchar, malloc, engine exports) from this process.
            LLVMOrcOpaqueDefinitionGenerator* generator;
            Check(LLVM.OrcCreateDynamicLibrarySearchGeneratorForProcess(
                &generator, LLVM.OrcLLJITGetGlobalPrefix(_jit), null, null));
            LLVM.OrcJITDylibAddGenerator(LLVM.OrcLLJITGetMainJITDylib(_jit), generator);
        }

        LLVMOrcOpaqueThreadSafeContext* tsc = LLVM.OrcCreateNewThreadSafeContextFromLLVMContext(context);
        LLVMOrcOpaqueThreadSafeModule* tsm = LLVM.OrcCreateNewThreadSafeModule(module, tsc);
        LLVM.OrcDisposeThreadSafeContext(tsc);                   // the module keeps its own reference
        Check(LLVM.OrcLLJITAddLLVMIRModule(_jit, LLVM.OrcLLJITGetMainJITDylib(_jit), tsm));

        ulong address;
        using var marshalledName = new MarshaledString(name);
        Check(LLVM.OrcLLJITLookup(_jit, &address, marshalledName));
        return (nint)address;
    }

    static void Check(LLVMOpaqueError* error)
    {
        if (error == null) return;
        sbyte* message = LLVM.GetErrorMessage(error);            // consumes the error
        string text = new(message);
        LLVM.DisposeErrorMessage(message);
        throw new InvalidOperationException(text);
    }
}

nint address = Jit.AddModuleAndLookup(context, module, "main");
int result = ((delegate* unmanaged<int>)address)();             // 55 for the example program
```

- Run the optimisation passes **before** adding the module; the JIT compiles what it is given.
- Each module added must define **different symbols**. To replace a function (hot reload), add modules through a resource tracker (`OrcLLJITAddLLVMIRModuleWithRT`) and remove the tracker before adding the new version.
- Call into the JIT'd code only with types that match the LLVM signature exactly. A `delegate* unmanaged<int>` for an `i32 ()` function is right; a mismatch corrupts the stack without an error.
- To let scripts call **C# functions**, mark static methods `[UnmanagedCallersOnly]`, and define their addresses as absolute symbols in the JIT dylib (`LLVM.OrcAbsoluteSymbols` and `OrcJITDylibDefine`). [Pointers and native memory](../../csharp/performance/memory.md#interop) covers the C# side.

## Debug info and the runtime

- [Debug info with LLVMSharp](debug-info.md) adds source lines and variables, so the compiled program can be stepped through in gdb, lldb, or Visual Studio.
- [Runtime and ABI](runtime-abi.md) covers the entry point, panics and bounds checks, string and array layouts, and passing structs to C correctly.

!!! warning "Common pitfalls"

    A block without a terminator, or with an instruction after one, fails verification. Track whether the current block is terminated, and start a new block after every `br` and `ret`.

    `BuildCall2`, `BuildLoad2`, and `BuildGEP2` with the wrong type (the pointer's type instead of the pointee's, or a function's pointer type instead of its function type) build invalid IR or crash in a pass. Keep the function and struct types in your own tables.

    `alloca`s outside the entry block grow the stack on each loop iteration, and `mem2reg` will not promote them.

    Passing structs by value to C functions compiles and runs, and passes garbage on most platforms. Pass a pointer.

    A missing runtime identifier, a missing `libz3` on Linux, or a libLLVM from a different major version all surface as `DllNotFoundException` or crashes in the first LLVM call.

    After `OrcLLJITAddLLVMIRModule`, the JIT owns the module and context. Disposing them, or using the builder on them, crashes later.
