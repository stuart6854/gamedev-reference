# Languages

Notes on designing a language and on compiling one, for game scripting, tools, and shaders. Hosting C# inside an engine stays under [assemblies and load contexts](../csharp/assemblies/index.md). Compiling C# itself is [Roslyn](../csharp/roslyn/index.md). This section is the language and the compiler infrastructure.

- [Programming language design](design.md) — syntax and grammar, lexing and parsing, name resolution, type systems, semantics, memory models, and the path from a tree to an interpreter, a VM, or native code.
- [LLVM](llvm.md) — the IR, SSA, passes, targets, and the practical work of generating IR, verifying it, optimising, emitting an object file, and running it in ORC's LLJIT.
- [Writing a compiler](compiler/index.md) — building a compiler in C# for a small statically typed language: source spans and diagnostics, the lexer, the parser and error recovery, syntax trees, names and scopes, type checking and inference, lowering and control-flow checks, code generation with LLVMSharp, and testing.
