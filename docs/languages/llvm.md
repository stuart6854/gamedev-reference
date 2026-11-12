# LLVM

LLVM is a compiler infrastructure whose contract is an **intermediate representation** (IR): a typed, SSA-form language that frontends emit and that backends lower to machine code. You do not write a register allocator, an instruction selector, or an object-file writer for each target. You generate IR, run a pass pipeline, and ask a target for an object file or for a JIT'd function pointer.

Game engines meet it as a library, not as `clang`. Unity's Burst compiles a subset of C# through LLVM, which is why it shows up when [measuring](../csharp/performance/measuring.md#reading-the-generated-code). Shader toolchains and custom script compilers use the same IR. Hosting C# itself is not an LLVM problem; that is [hosting from C++](../csharp/assemblies/hosting.md). [Roslyn](../csharp/roslyn/index.md) is a C# frontend that emits IL, not LLVM IR.

The snippets on this page target **LLVM 18 or later**, where pointers are opaque (`ptr`, not `double*`) and the new pass manager is the optimisation pipeline. The C++ is the native API. The C# is [LLVMSharp](https://github.com/dotnet/LLVMSharp) 20 (`LLVMSharp.Interop`), which wraps the LLVM C API; the libLLVM you load must be the same major version as the bindings. [Code generation with LLVMSharp](compiler/llvmsharp.md) uses LLVMSharp 22 for a whole language, including a working ORC JIT. The [Language Reference](https://llvm.org/docs/LangRef.html) is the IR's specification. The [Kaleidoscope tutorial](https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/index.html) is the walk-through that these sections compress.

## IR and SSA

A **module** is a translation unit: functions, globals, and metadata for one library or one compiled script. A **function** has a type, a linkage, and a list of **basic blocks**. A basic block is a straight-line sequence of instructions that ends in a terminator: `ret`, `br`, `switch`, `unreachable`. Control never falls out of a block.

Values are in **SSA** (static single assignment) form: each `%name` is assigned once. A later "change" is a new value. When two control-flow paths must agree on a value, a **phi** instruction at the start of the join block picks the incoming value according to the predecessor the flow actually came from.

```text
define double @abs(double %a) {
entry:
  %cmp = fcmp oge double %a, 0.000000e+00
  br i1 %cmp, label %pos, label %neg

pos:
  br label %merge

neg:
  %negated = fneg double %a
  br label %merge

merge:
  %r = phi double [ %a, %pos ], [ %negated, %neg ]
  ret double %r
}
```

`%r` is `%a` if the predecessor was `pos`, and `%negated` if it was `neg`. A phi must list every predecessor of its block, and sits before any non-phi instruction in that block.

### Types

IR is strongly typed. The common types are integers (`i1`, `i8`, `i32`, `i64`), `float` and `double`, arrays, structs, vectors, function types, and pointers. Since LLVM 15, and exclusively since 17, pointers are **opaque**: there is a single `ptr` type (per address space), and the element type is an argument of `load`, `store`, and `getelementptr`, not a property of the pointer.

```text
%p = alloca double, align 8
store double %a, ptr %p
%v = load double, ptr %p
%elem = getelementptr inbounds %T, ptr %base, i32 0, i32 2
```

`PointerType::get(Context, AddressSpace)` (address space 0 for ordinary memory) is how you ask for `ptr` in C++. There is no `getPointerElementType()`.

Integer types are just a bit width: `i32` is not "a C `int`". The **data layout** string on the module is what gives widths, alignments, and endianness for a target; without it, LLVM assumes a default layout that may not match the ABI you link against.

### Structure of a program

```text
Module          one IR file; holds functions, globals, aliases, metadata
  Function      a callable, with a type and linkage (external, internal, ...)
    BasicBlock  a labelled list of instructions ending in a terminator
      Instruction  a typed SSA value, or a terminator, or a store / call with no result
```

Globals and functions are themselves values (addresses). A declaration (`declare double @sin(double)`) is a function with no body; a definition has at least one block. Linkage decides whether the name is visible to the linker and whether identical definitions may be merged.

## Passes and the new pass manager

A **pass** is a transformation or an analysis: promote allocas to SSA registers (`SROA` / `mem2reg`), fold instructions (`InstCombine`), delete dead code, unroll or vectorise a loop, inline a call. Passes are composed into a pipeline.

LLVM currently has two pass managers. The **new pass manager** is what you use for IR optimisation. Analyses are cached on **analysis managers** (module, call-graph SCC, function, loop) and invalidated when a transform says they are stale. `PassBuilder` knows the default pipelines and how to parse a pipeline string. The **legacy pass manager** still runs the backend: instruction selection, register allocation, and emission of object or assembly files. Do not mix the two in the same pipeline.

```text
LoopAnalysisManager     LAM;
FunctionAnalysisManager FAM;
CGSCCAnalysisManager    CGAM;
ModuleAnalysisManager   MAM;     // declare in this order: destruction is the reverse

PassBuilder PB(TM.get());        // LLVM 18: PassBuilder(TargetMachine * = nullptr, ...)
PB.registerModuleAnalyses(MAM);
PB.registerCGSCCAnalyses(CGAM);
PB.registerFunctionAnalyses(FAM);
PB.registerLoopAnalyses(LAM);
PB.crossRegisterProxies(LAM, FAM, CGAM, MAM);

ModulePassManager MPM = PB.buildPerModuleDefaultPipeline(OptimizationLevel::O2);
MPM.run(*Mod, MAM);
```

The analysis managers must be declared in that order so that proxies are destroyed after the managers they reference. Later LLVM releases added an `LLVMContext &` as the first argument of `PassBuilder`; if a default construct no longer compiles, check the header you have.

The C API, which LLVMSharp wraps, does the same work with a pipeline string:

```text
default<O2>                 the same pipeline as buildPerModuleDefaultPipeline(O2)
sroa,instcombine,simplifycfg
function(mem2reg)           a function pass, adapted to a module
```

### Optimisation levels

| Level | What you get | When to use it |
| --- | --- | --- |
| `O0` | Almost no IR optimisation. Fast to compile, close to what you emitted | Debugging; a JIT of huge scripts where compile time is the budget |
| `O1` | Simplification and some inlining | A middle ground when `O2` is a measurable compile cost |
| `O2` | The default: inlining, instcombine, GVN, loop work, some vectorisation | Almost everything you will ship or JIT for an editor |
| `O3` | More inlining and more aggressive loop transforms | A hot kernel you compile once. Larger code, longer compiles |
| `Os` / `Oz` | The `O2` family, biased toward size (`Oz` more so) | Memory-tight consoles, download size |

`mem2reg` / SROA is the pass you notice first: it turns `alloca` plus `load`/`store` of a local into SSA values, which every later pass wants. If you are building a pipeline by hand, put that near the front. If you emit SSA directly (the IRBuilder style below), you need it less.

## Targets, backends, and linking

A **target** is a machine LLVM can generate code for, named by a **triple**: `arch-vendor-os-environment`, such as `x86_64-pc-windows-msvc` or `aarch64-unknown-linux-gnu`. A **TargetMachine** is a configured target: the triple, a CPU name (`generic`, or `haswell`, or an Apple Silicon core), feature flags, relocation model, and code model. The module's triple and **data layout** must come from that TargetMachine, or ABI-sensitive lowering (pointer width, struct layout, calling convention) will be wrong.

The backend for each target lowers IR to machine instructions, allocates registers, and emits object code, assembly, or an in-memory buffer. That is also the path to a text `.ll` file (`Mod->print`) or a bitcode `.bc` file, which are IR, not machine code.

**Linking** happens at two layers:

- **IR linking.** `llvm-link` merges modules. Declarations in one module bind to definitions in another. This is how a script compiler can put engine builtins in a separate module and link them before codegen. Linkage (`internal`, `private`, `external`, `linkonce_odr`, `weak`) decides what happens when two modules define the same name.
- **LTO and the system linker.** Bitcode can be carried into the link step so that inlining and dead-stripping happen across what used to be object-file boundaries (full LTO, or **ThinLTO** for scale). The object files you emit otherwise go to the platform linker, often **lld**, the same as any other compiler's output.

A JIT usually skips the system linker: it resolves symbols itself, and you must give it addresses for any function the IR only declared (`sin`, an engine API, `malloc`).

## JIT versus AOT

| | AOT (ahead of time) | JIT (just in time) |
| --- | --- | --- |
| When code is generated | At cook / compile time, into an object file or a shared library | When the function is first called, or when it has been hot |
| What you ship | Machine code, like any other translation unit | IR or bytecode, plus LLVM (or a thinner JIT) in the process |
| Best for | Player builds, shaders you can compile in the content pipeline, tools that can wait | Editors, REPLs, a language whose program is not known at pack time |
| Cost | Compile time is a build or cook cost. No LLVM runtime required in the player if you ship objects | Compile time is on the user's clock. LLVM as a library is large. You must still handle the symbols the IR calls |

The two share the frontend and the optimisation pipeline. They diverge at emission: `TargetMachine::addPassesToEmitFile` versus ORC's **LLJIT**, which is the JIT you should start with. ORC (On-Request Compilation) is the current JIT infrastructure; MCJIT is older and still appears in examples.

## Generating IR for a tiny expression language

The language is arithmetic on `double`, with named parameters and a comparison that needs a phi: a function `expr(a, b)` that computes `a * 2 + b`, and a function `abs(a)` that computes `a >= 0 ? a : -a`. The frontend of [language design](design.md) would have produced a typed AST; what follows is the lowering.

Headers, once, for the C++ snippets on this page:

```cpp
#include "llvm/ExecutionEngine/Orc/LLJIT.h"
#include "llvm/IR/DIBuilder.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/LLVMContext.h"
#include "llvm/IR/LegacyPassManager.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/Verifier.h"
#include "llvm/MC/TargetRegistry.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Support/TargetSelect.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Target/TargetMachine.h"
#include "llvm/TargetParser/Host.h"
```

=== "C++"

    ```cpp
    using namespace llvm;

    LLVMContext Ctx;
    auto Mod = std::make_unique<Module>("expr", Ctx);
    IRBuilder<> Builder(Ctx);
    Type *F64 = Type::getDoubleTy(Ctx);

    auto make_fn = [&](const char *name, ArrayRef<Type *> args) {
        auto *FT = FunctionType::get(F64, args, false);
        auto *F  = Function::Create(FT, Function::ExternalLinkage, name, *Mod);
        auto *BB = BasicBlock::Create(Ctx, "entry", F);
        Builder.SetInsertPoint(BB);
        return F;
    };

    Function *Expr = make_fn("expr", {F64, F64});
    Argument *A = Expr->getArg(0); A->setName("a");
    Argument *B = Expr->getArg(1); B->setName("b");
    Value *T0 = Builder.CreateFMul(A, ConstantFP::get(F64, 2.0), "t0");
    Value *T1 = Builder.CreateFAdd(T0, B, "t1");
    Builder.CreateRet(T1);

    Function *Abs = make_fn("abs", {F64});
    Argument *X = Abs->getArg(0); X->setName("a");
    Value *Cmp = Builder.CreateFCmpOGE(X, ConstantFP::get(F64, 0.0), "cmp");
    BasicBlock *Pos   = BasicBlock::Create(Ctx, "pos",   Abs);
    BasicBlock *Neg   = BasicBlock::Create(Ctx, "neg",   Abs);
    BasicBlock *Merge = BasicBlock::Create(Ctx, "merge", Abs);
    Builder.CreateCondBr(Cmp, Pos, Neg);

    Builder.SetInsertPoint(Pos);
    Builder.CreateBr(Merge);

    Builder.SetInsertPoint(Neg);
    Value *Negated = Builder.CreateFNeg(X, "negated");
    Builder.CreateBr(Merge);

    Builder.SetInsertPoint(Merge);
    PHINode *R = Builder.CreatePHI(F64, 2, "r");
    R->addIncoming(X, Pos);
    R->addIncoming(Negated, Neg);
    Builder.CreateRet(R);
    ```

=== "C#"

    ```csharp
    using LLVMSharp.Interop;

    LLVMContextRef context = LLVMContextRef.Create();
    LLVMModuleRef  module  = context.CreateModuleWithName("expr");
    LLVMBuilderRef builder = context.CreateBuilder();
    LLVMTypeRef    f64     = context.DoubleType;

    LLVMTypeRef ExprTy = LLVMTypeRef.CreateFunction(f64, new[] { f64, f64 });
    LLVMValueRef expr  = module.AddFunction("expr", ExprTy);
    builder.PositionAtEnd(expr.AppendBasicBlock("entry"));
    LLVMValueRef a  = expr.GetParam(0);
    LLVMValueRef b  = expr.GetParam(1);
    a.Name = "a";
    b.Name = "b";
    LLVMValueRef t0 = builder.BuildFMul(a, LLVMValueRef.CreateConstReal(f64, 2.0), "t0");
    LLVMValueRef t1 = builder.BuildFAdd(t0, b, "t1");
    builder.BuildRet(t1);

    LLVMTypeRef  AbsTy = LLVMTypeRef.CreateFunction(f64, new[] { f64 });
    LLVMValueRef abs   = module.AddFunction("abs", AbsTy);
    LLVMBasicBlockRef entry = abs.AppendBasicBlock("entry");
    LLVMBasicBlockRef pos   = abs.AppendBasicBlock("pos");
    LLVMBasicBlockRef neg   = abs.AppendBasicBlock("neg");
    LLVMBasicBlockRef merge = abs.AppendBasicBlock("merge");
    builder.PositionAtEnd(entry);
    LLVMValueRef x   = abs.GetParam(0);
    x.Name = "a";
    LLVMValueRef cmp = builder.BuildFCmp(
        LLVMRealPredicate.LLVMRealOGE, x, LLVMValueRef.CreateConstReal(f64, 0.0), "cmp");
    builder.BuildCondBr(cmp, pos, neg);

    builder.PositionAtEnd(pos);
    builder.BuildBr(merge);

    builder.PositionAtEnd(neg);
    LLVMValueRef negated = builder.BuildFNeg(x, "negated");
    builder.BuildBr(merge);

    builder.PositionAtEnd(merge);
    LLVMValueRef r = builder.BuildPhi(f64, "r");
    r.AddIncoming(new[] { x, negated }, new[] { pos, neg }, 2);
    builder.BuildRet(r);
    ```

Loads and GEPs must take the element type explicitly. An alloca of a local, which you would emit for a mutable variable before SROA, looks like this:

=== "C++"

    ```cpp
    Value *Slot = Builder.CreateAlloca(F64, nullptr, "x");
    Builder.CreateStore(A, Slot);
    Value *Loaded = Builder.CreateLoad(F64, Slot, "x.load");   // type first, not inferred
    ```

=== "C#"

    ```csharp
    LLVMValueRef slot   = builder.BuildAlloca(f64, "x");
    builder.BuildStore(a, slot);
    LLVMValueRef loaded = builder.BuildLoad2(f64, slot, "x.load");
    ```

A call uses the function type for the same reason, because the callee value is a `ptr`:

=== "C++"

    ```cpp
    Value *Call = Builder.CreateCall(Sin->getFunctionType(), Sin, {Arg}, "s");
    ```

=== "C#"

    ```csharp
    LLVMValueRef call = builder.BuildCall2(sinType, sin, new[] { arg }, "s");
    ```

## Verifying and optimising

`verifyModule` walks the IR and checks the rules the rest of LLVM assumes: every block has a terminator, every phi lists every predecessor, types of operands match, there are no cycles in the use-def graph that SSA would forbid. Run it on every module you generate, before optimisation and before you hand the module to a JIT. A failure is almost always a bug in the frontend, not in LLVM.

=== "C++"

    ```cpp
    std::string error;
    raw_string_ostream os(error);
    if (verifyModule(*Mod, &os)) {          // true means the module is broken
        errs() << os.str();
        return 1;
    }

    // Pass a TargetMachine* to PassBuilder when you have one (see below).
    LoopAnalysisManager     LAM;
    FunctionAnalysisManager FAM;
    CGSCCAnalysisManager    CGAM;
    ModuleAnalysisManager   MAM;
    PassBuilder PB;
    PB.registerModuleAnalyses(MAM);
    PB.registerCGSCCAnalyses(CGAM);
    PB.registerFunctionAnalyses(FAM);
    PB.registerLoopAnalyses(LAM);
    PB.crossRegisterProxies(LAM, FAM, CGAM, MAM);
    PB.buildPerModuleDefaultPipeline(OptimizationLevel::O2).run(*Mod, MAM);
    ```

=== "C#"

    ```csharp
    if (!module.TryVerify(LLVMVerifierFailureAction.LLVMPrintMessageAction, out string message))
        throw new InvalidOperationException(message);

    LLVMPassBuilderOptionsRef options = LLVMPassBuilderOptionsRef.Create();
    try
    {
        // "default<O2>" is the C API name for buildPerModuleDefaultPipeline(O2).
        if (!module.TryRunPasses("default<O2>", tm, options, out string passError))
            throw new InvalidOperationException(passError);
    }
    finally
    {
        options.Dispose();
    }
    ```

Dump the IR with `Mod->print(errs(), nullptr)` or `module.PrintToString()` while you are writing the frontend. After `O2`, `expr` should collapse to a single fused multiply-add or to `a` scaled and added, and `abs` may become a target intrinsic or a bitwise clear of the sign bit, depending on the target and the pass pipeline.

## Emitting object files

Initialise the targets you intend to use (or all of them, in a tool), build a `TargetMachine` from the host triple or from a triple you were given, copy its data layout and triple onto the module, then run the legacy codegen pipeline into a file or a buffer.

=== "C++"

    ```cpp
    InitializeAllTargetInfos();
    InitializeAllTargets();
    InitializeAllTargetMCs();
    InitializeAllAsmParsers();
    InitializeAllAsmPrinters();

    std::string triple = sys::getDefaultTargetTriple();
    std::string err;
    const Target *target = TargetRegistry::lookupTarget(triple, err);
    if (!target) {
        errs() << err << "\n";
        return 1;
    }

    auto TM = std::unique_ptr<TargetMachine>(target->createTargetMachine(
        triple, "generic", "", TargetOptions{}, Reloc::PIC_));
    Mod->setTargetTriple(triple);
    Mod->setDataLayout(TM->createDataLayout());

    std::error_code ec;
    raw_fd_ostream out("expr.o", ec, sys::fs::OF_None);
    if (ec) {
        errs() << "could not open expr.o: " << ec.message() << "\n";
        return 1;
    }

    legacy::PassManager codegen;
    if (TM->addPassesToEmitFile(codegen, out, nullptr, CodeGenFileType::ObjectFile)) {
        errs() << "this target cannot emit an object file\n";
        return 1;
    }
    codegen.run(*Mod);
    out.flush();
    ```

=== "C#"

    ```csharp
    LLVM.InitializeNativeTarget();
    LLVM.InitializeNativeAsmPrinter();
    LLVM.InitializeNativeAsmParser();

    string triple = LLVMTargetRef.DefaultTriple;
    if (!LLVMTargetRef.TryGetTargetFromTriple(triple, out LLVMTargetRef target, out string err))
        throw new InvalidOperationException(err);

    LLVMTargetMachineRef tm = target.CreateTargetMachine(
        triple,
        "generic",
        "",
        LLVMCodeGenOptLevel.LLVMCodeGenLevelDefault,
        LLVMRelocMode.LLVMRelocPIC,
        LLVMCodeModel.LLVMCodeModelDefault);

    module.Target = triple;
    module.DataLayoutObject = tm.CreateTargetDataLayout();

    if (!tm.TryEmitToFile(module, "expr.o", LLVMCodeGenFileType.LLVMObjectFile, out string emitErr))
        throw new InvalidOperationException(emitErr);
    ```

`addPassesToEmitFile` returns **true** on failure, which is the opposite of `TryEmitToFile` in LLVMSharp (true means success). The `.o` is an ordinary object file: pass it to the linker with the rest of the engine, or load it as a plugin as in [modules and plugins](../engine/patterns/modules.md#dynamic-plugins). For a shader or a script you cook, this is the AOT half of the table above.

## JIT with ORC LLJIT

LLJIT is the small ORC wrapper that covers "compile this module and give me a function pointer." You still have to initialise the native target, and you must move the module and its context into a `ThreadSafeModule` — after `addIRModule`, you no longer own them.

=== "C++"

    ```cpp
    InitializeNativeTarget();
    InitializeNativeTargetAsmPrinter();
    InitializeNativeTargetAsmParser();

    auto jit = ExitOnErr(orc::LLJITBuilder().create());

    // The context and module must outlive construction of the ThreadSafeModule,
    // and must not be used afterwards: ownership moves in.
    auto ctx = std::make_unique<LLVMContext>();
    auto mod = build_expr_module(*ctx);          // the IRBuilder work from above
    ExitOnErr(jit->addIRModule(orc::ThreadSafeModule(std::move(mod), std::move(ctx))));

    orc::ExecutorAddr addr = ExitOnErr(jit->lookup("expr"));
    auto *expr = addr.toPtr<double (*)(double, double)>();
    double result = expr(3.0, 4.0);              // 3 * 2 + 4 = 10
    ```

=== "C#"

    ```csharp
    // LLVMSharp exposes the ORC C API in llvm-c/LLJIT.h (LLVM.OrcCreateLLJIT,
    // LLVM.OrcLLJITAddLLVMIRModule, LLVM.OrcLLJITLookup, and the ThreadSafeModule
    // constructors). Ownership is the same as in C++: once the module is added,
    // the JIT owns it and the context. For a first AOT path, TryEmitToFile is
    // simpler; use LLJIT when the program is not known at pack time.
    ```

If the IR calls functions you did not define (`sin`, an engine API), add a definition or, more usually, define a JIT'd symbol that points at the host function. LLJIT's main JIT dylib accepts absolute symbols for that. Forgetting this looks like a lookup failure or a crash the first time the compiled code calls out.

Compile time is real: a large module at `O2` in the middle of a play session will hitch. Compile on a worker, or compile at `O0` and re-optimise later, or AOT at cook time. The language-level decision of interpreter, VM, JIT, or AOT is on the [design page](design.md#the-compile-pipeline).

## Debug info

Without debug info, a debugger and a profiler see whatever names survived in the IR, with no source line. `DIBuilder` attaches DWARF (or the platform equivalent) metadata to the module: a compile unit, a file, subprograms, local variables, and a source location on each interesting instruction.

```cpp
DIBuilder dib(*Mod);
DIFile *file = dib.createFile("expr.lang", ".");
DICompileUnit *cu = dib.createCompileUnit(
    dwarf::DW_LANG_C, file, "expr-compiler", /*isOptimized=*/false, "", 0);

DIType *Dbl = dib.createBasicType("double", 64, dwarf::DW_ATE_float);
DISubroutineType *fnTy = dib.createSubroutineType(
    dib.getOrCreateTypeArray({Dbl, Dbl, Dbl}));    // return type, then argument types
DISubprogram *sp = dib.createFunction(
    file, "expr", "expr", file, /*LineNo=*/1, fnTy, /*ScopeLine=*/1,
    DINode::FlagPrototyped, DISubprogram::SPFlagDefinition);
Expr->setSubprogram(sp);

Builder.SetCurrentDebugLocation(DILocation::get(Ctx, /*Line=*/1, /*Col=*/1, sp));
// ... IRBuilder emits for the body of expr, each with a location ...
dib.finalize();    // required; skipping it produces incomplete, often unusable debug info
```

Set a location before you emit the instructions it describes, including after you move the builder to a new block. Locations are metadata; they do not change what the program does, and most optimisation passes try to preserve them, with shrinking accuracy at higher levels. The C API for the same objects is `llvm-c/DebugInfo.h` (`LLVMCreateDIBuilder`, `LLVMDIBuilderCreateCompileUnit`, `LLVMDIBuilderFinalize`), which LLVMSharp generates bindings for.

## Version churn

LLVM's C++ API moves every release, and a frontend written against 18 will not compile unchanged against every later one. The IR is more stable than the C++ headers; the C API is in between, which is why LLVMSharp can track it, and why it still has to ship a new package for a new libLLVM major.

Things that have already broken frontends, and will break them again:

- **Opaque pointers.** `load` / `GEP` / `CreateCall` without an explicit type, and `PointerType::get(ElementTy, AS)` as a way to recover the element, are gone. So is `getPointerElementType()`.
- **`PassManagerBuilder`** (the old `createFunctionPassManager` / `OptBuilder` path) was removed in LLVM 17. Use `PassBuilder` and, from C, `LLVMRunPasses` / `module.RunPasses`.
- **`PassBuilder`'s constructor** gained arguments across releases. LLVM 18 takes an optional `TargetMachine *`. Later releases have required an `LLVMContext &` first. Codegen still uses `legacy::PassManager`.
- **Header homes.** `TargetRegistry.h` moved under `llvm/MC/`. `sys::getDefaultTargetTriple()` moved to `llvm/TargetParser/Host.h`. `setTargetTriple` has accepted a string and, in later APIs, a `Triple` object.
- **LLVMSharp and libLLVM must match.** A v20 package against an 18 library, or the reverse, fails in ways that look like missing exports or garbage IR. The higher-level `LLVMSharp` wrappers (not `LLVMSharp.Interop`) have historically lagged; the Interop types used above are the ones that track the C API.
- **ORC replaces MCJIT.** New code should not start from `EngineBuilder` / `MCJIT`. LLJIT is the entry point; the lower ORC layers are there when you need lazy compilation or custom linking.

Pin a version, read its release notes when you move, and keep a module dump and `verifyModule` in the test of the frontend. The IR you emit is the part you can snapshot; the C++ that emits it is not.

!!! warning "Common pitfalls"

    Skipping `verifyModule` and then crashing inside a pass or the JIT hides the bug in the frontend. Verify first; the messages are about SSA and types, not about the pass that happened to trip.

    A phi that misses a predecessor, or that is not at the start of its block, is invalid IR. When you add an edge, update every phi in the destination.

    Leaving the module's data layout and triple unset, or setting them to something other than the `TargetMachine` you will emit or JIT with, produces wrong struct offsets and calling conventions.

    After `addIRModule`, the JIT owns the module and the context. Using the `IRBuilder` or dumping the module afterwards is a use-after-move.

    `CreateLoad` / `BuildLoad2` and `CreateGEP` / `BuildGEP2` without the source type will not compile against a current LLVM, or will crash if an old wrapper still guesses. The same is true of `BuildCall2`.

    `addPassesToEmitFile` returns true on **failure**. It is easy to invert and think you emitted an object file when the target refused.

    Forgetting `DIBuilder::finalize` emits a compile unit that debuggers cannot use. Forgetting to set a debug location on later blocks leaves those instructions with no line.

    Linking LLVM without the targets and their asm printers you initialise will fail at `lookupTarget` or at emit, often only on a colleague's machine whose triple you did not test.
