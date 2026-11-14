---
package: LLVMSharp.Interop 22.1
---

# Debug info with LLVMSharp

Without debug info, a debugger shows compiled code as assembly and a crash as an address. With it, you can set a breakpoint on a line of the source language, step through it, see local variables, and read a backtrace in source terms. The data is **DWARF** on Linux and macOS (and **CodeView**, emitted from the same LLVM metadata, on Windows); you describe it to LLVM through a `DIBuilder`, and LLVM writes it into the object file.

This extends the [code generator](llvmsharp.md). The [LLVM page](../llvm.md#debug-info) shows the same objects in C++.

## What to describe

| Metadata | Made by | Gives the debugger |
| --- | --- | --- |
| Module flags | `AddModuleFlag` | the debug info and DWARF versions; tools that read the module back drop debug info without them |
| Compile unit and file | `CreateCompileUnit`, `CreateFile` | which source file the code came from |
| Types | `CreateBasicType`, `CreateStructType`, `CreatePointerType` | how to show a value |
| Subprogram per function | `CreateFunction`, then `function.Subprogram = ...` | the function name and its starting line |
| Variables | `CreateParameterVariable`, `CreateAutoVariable`, then a declare record | locals and parameters by name |
| Locations | `CreateDebugLocation`, set on the builder | the source line and column of each instruction |

## Setup, once per module

```csharp
module.AddModuleFlag("Debug Info Version", LLVMModuleFlagBehavior.LLVMModuleFlagBehaviorWarning, 3u);
module.AddModuleFlag("Dwarf Version", LLVMModuleFlagBehavior.LLVMModuleFlagBehaviorWarning, 5u);
// On Windows, add "CodeView" = 1 instead of "Dwarf Version", for Visual Studio and WinDbg.

LLVMDIBuilderRef di = module.CreateDIBuilder();
LLVMMetadataRef file = di.CreateFile("sum.lang", sourceDirectory);
LLVMMetadataRef unit = di.CreateCompileUnit(
    LLVMDWARFSourceLanguage.LLVMDWARFSourceLanguageC99, file, "langc 0.1", IsOptimized: 0, Flags: "",
    RuntimeVersion: 0, SplitName: "", LLVMDWARFEmissionKind.LLVMDWARFEmissionFull, DWOld: 0,
    SplitDebugInlining: 0, DebugInfoForProfiling: 0, SysRoot: "", SDK: "");
```

- One **file** per source file, and one **compile unit** per module. Pass the directory separately; debuggers join the two to find the source.
- The **language** tag tells the debugger how to print expressions. There is no tag for your language, and C99 is the safe choice: gdb and lldb then show structs, pointers, and integers in C syntax, which is close enough for a C-like language.

## Types

```csharp
const uint DW_ATE_signed = 0x05, DW_ATE_unsigned = 0x08, DW_ATE_float = 0x04, DW_ATE_boolean = 0x02;

LLVMMetadataRef DebugType(TypeSymbol type) => type switch
{
    _ when type == TypeSymbol.Bool => di.CreateBasicType("bool", 8, DW_ATE_boolean, LLVMDIFlags.LLVMDIFlagZero),
    { IsInteger: true } => di.CreateBasicType(type.ToString(), (ulong)type.SizeInBits,
                               type.IsSigned ? DW_ATE_signed : DW_ATE_unsigned, LLVMDIFlags.LLVMDIFlagZero),
    { IsFloat: true }   => di.CreateBasicType(type.ToString(), (ulong)type.SizeInBits, DW_ATE_float, LLVMDIFlags.LLVMDIFlagZero),
    StructType s        => DebugStruct(s.Symbol),
    _ => throw new UnreachableException($"No debug type for {type}"),
};
```

Cache the results in a dictionary, as for LLVM types. A struct is a `CreateStructType` whose elements are `CreateMemberType` entries, each with its size and **offset in bits**; read the offsets from the target's data layout (`LLVM.OffsetOfElement`) rather than computing them, so they match the code.

## Functions and variables

```csharp
LLVMMetadataRef subprogram = di.CreateFunction(unit, "sum_to", "sum_to", file, LineNo: 1,
    di.CreateSubroutineType(file, new[] { diI32, diI32 }, LLVMDIFlags.LLVMDIFlagZero),   // return type, then parameters
    IsLocalToUnit: 0, IsDefinition: 1, ScopeLine: 1, LLVMDIFlags.LLVMDIFlagPrototyped, IsOptimized: 0);
function.Subprogram = subprogram;
```

Every `alloca` from the code generator becomes a named variable with a **declare record**: "this variable lives in this stack slot".

```csharp
LLVMValueRef DeclareLocal(LLVMValueRef function, LLVMMetadataRef subprogram, Symbol symbol,
                          LLVMTypeRef type, LLVMMetadataRef debugType, uint line, uint argNo)
{
    LLVMValueRef slot = _builder.BuildAlloca(type, symbol.Name);
    LLVMMetadataRef variable = argNo > 0
        ? di.CreateParameterVariable(subprogram, symbol.Name, argNo, file, line, debugType, AlwaysPreserve: 1, LLVMDIFlags.LLVMDIFlagZero)
        : di.CreateAutoVariable(subprogram, symbol.Name, file, line, debugType, AlwaysPreserve: 1, LLVMDIFlags.LLVMDIFlagZero, AlignInBits: 0);
    di.InsertDeclareRecordAtEnd(slot, variable, di.CreateExpression(Array.Empty<ulong>()),
        _context.CreateDebugLocation(line, 1, subprogram, default), function.EntryBasicBlock);
    return slot;
}
```

- **Parameters are numbered from 1** (`argNo`), in order; `0` means a local.
- A local declared in a nested block can use a `CreateLexicalBlock(subprogram, file, line, column)` as its scope, so the debugger shows it only inside that block. Using the function as the scope for everything is a fine start.

## Locations

Before emitting the instructions for a statement or expression, set the builder's location from the bound node's syntax span:

```csharp
void SetLocation(BoundNode node, LLVMMetadataRef scope)
{
    (int line, int column) = node.Syntax.Text.Position(node.Syntax.Span.Start);    // 1-based
    _builder.CurrentDebugLocation2 = _context.CreateDebugLocation((uint)line, (uint)column, scope, default);
}
```

- **Every instruction in a function with a subprogram needs a location**, including calls. A call without one fails verification ("inlinable function call in a function with debug info must have a !dbg location").
- Set the location **per statement** for line stepping, and per expression if you want column-accurate stepping. The span conversion is the [line map](source-diagnostics.md#source-text-and-spans) from the first page.
- Instructions you add with no source of their own (the stores of parameters into their slots, the `unreachable` at the end of a function) take the function's opening line.

## Finishing

```csharp
di.DIBuilderFinalize();             // before verifying and before emitting: fills in what was deferred
if (!module.TryVerify(LLVMVerifierFailureAction.LLVMReturnStatusAction, out string error))
    throw new InvalidOperationException(error);
```

Emit at `LLVMCodeGenLevelNone` and without the optimisation passes for the best stepping. Then debug the linked program:

```bash
gdb -ex "break sum.lang:5" -ex run ./sum
```

```text
Breakpoint 1, sum_to (n=10) at sum.lang:5
5           total = total + i;
(gdb) info locals
total = 0
i = 1
(gdb) bt
#0  sum_to (n=10) at sum.lang:5
#1  0x000055555555517b in main () at sum.lang:12
```

## Optimised code

Debug info survives optimisation, with less accuracy: variables become "optimised out" once `mem2reg` turns their slots into registers (LLVM then tracks them with value records, approximately), and lines jump around as code moves. That is the same experience as debugging an optimised C++ build. Offer both: `-O0 -g` for debugging, `-O2 -g` for profiling, where the profiler only needs function names and lines.

Line tables are also what **profilers** and **crash reports** read. Even a release build should keep at least line-level debug info (`LLVMDWARFEmissionLineTablesOnly`), stored separately if size matters.

!!! warning "Common pitfalls"

    Without the "Debug Info Version" module flag, the debug info survives direct emission but is stripped, with only a warning, whenever LLVM reads the module back: `llc`, `opt`, bitcode files, and link-time optimisation. Always set it.

    A call instruction without a location, in a function that has a subprogram, fails verification. Set a location before emitting every statement, including generated ones.

    Forgetting `DIBuilderFinalize` leaves subprograms incomplete; debuggers then show no locals.

    The subroutine type's array starts with the **return type** (or a null metadata for `void`), followed by the parameters. Leaving out the return type shifts every parameter's type by one.
