# Writing a compiler

How to build a compiler for a small statically typed language with local type inference, from source text to native code through LLVM. [Programming language design](../design.md) covers the choices a language makes. These pages cover implementing them: the data structures, the order to build things in, and the tests that keep it working.

Each page gives code in C++ (C++20) and C# (.NET 10), then tips for each. The code generation pages use [LLVMSharp](https://github.com/dotnet/LLVMSharp) from C#; the [LLVM](../llvm.md) page explains the IR, passes, and targets it drives, with the C++ API alongside.

## The example language

All the pages use the same small language: functions, `let` (immutable) and `var` (mutable) locals whose types are inferred, `if` and `while`, structs, and calls into C.

```text
struct Vec2 { x: f32, y: f32 }

extern fn putchar(c: i32) -> i32;

fn length_sq(v: Vec2) -> f32 {
    return v.x * v.x + v.y * v.y;
}

fn sum_to(n: i32) -> i32 {
    var total = 0;              // i32, inferred from the literal
    var i = 1;
    while i <= n {
        total = total + i;
        i = i + 1;
    }
    return total;
}

fn main() -> i32 {
    let v = Vec2 { x: 3.0, y: 4.0 };
    if length_sq(v) == 25.0 { putchar(89); }    // 'Y'
    return sum_to(10);                           // 55
}
```

## The pipeline

```mermaid
flowchart LR
    A[Source text] --> B[Lexer]
    B --> C[Parser]
    C --> D[Syntax tree]
    D --> E[Binder: names and types]
    E --> F[Bound tree]
    F --> G[Lowering]
    G --> H[LLVM IR]
    H --> I[Object file or JIT]
```

| Stage | Input | Output | Page |
| --- | --- | --- | --- |
| Source | file bytes | text, line map, diagnostics | [Source text and diagnostics](source-diagnostics.md) |
| Lexer | text | tokens with spans | [Lexer](lexer.md) |
| Parser | tokens | syntax tree | [Parser](parser.md), [Syntax trees](syntax-trees.md) |
| Binder | syntax tree | symbols, scopes, bound tree with types | [Names, scopes, and symbols](binding.md), [Type checking and inference](types.md), [Numeric types and conversions](numeric-conversions.md) |
| Lowering | bound tree | simpler bound tree, control-flow graph | [Lowering and control flow](lowering.md) |
| Evaluator | lowered tree | results, for tests and constants | [Reference evaluator](evaluator.md) |
| Code generation | lowered tree | LLVM module, object file, or JIT'd function | [Code generation with LLVMSharp](llvmsharp.md), [Debug info](debug-info.md) |
| Runtime and library | | support code linked with every program | [Runtime and ABI](runtime-abi.md), [Standard library](standard-library.md) |
| Tests | every stage | | [Testing a compiler](testing.md) |
| Editor support | the front end | errors, hover, completion in editors | [Language server](language-server.md) |

Every stage **reports errors and carries on**. The parser makes a tree even from broken code, the binder gives a broken expression an error type, and code generation runs only when there are no errors. One compile gives every error in the file, not just the first.

## Project layout

```text
Lang.slnx
src/
  Lang.Compiler/            // a library: no console, no file system beyond what it is given
    Text/                   // SourceText, TextSpan, line map
    Diagnostics/
    Syntax/                 // Lexer, Parser, syntax nodes
    Binding/                // symbols, scopes, Binder, bound nodes, types
    Lowering/
    CodeGen/                // LLVMSharp
    Compilation.cs          // runs the stages, collects diagnostics
  Lang.Cli/                 // langc build main.lang -o main
tests/
  Lang.Compiler.Tests/      // unit and snapshot tests
  cases/                    // end-to-end .lang files with expected output
```

Keep the compiler a **library**. The command line, a test, an editor plug-in, and a game that compiles scripts at run time are all just callers of `Compilation`. The result is the lowered functions, which the caller passes to the [code generator](llvmsharp.md) or the [evaluator](evaluator.md).

=== "C++"

    ```cpp
    struct CompileResult
    {
        std::vector<Diagnostic> diagnostics;
        std::unordered_map<const FunctionSymbol*, LoweredFunction> lowered = {};   // empty when there are errors
        bool succeeded = false;
    };

    class Compilation
    {
    public:
        // One file here. With several, each file gets its own bag, and the binder reports into the bag of the file it is binding.
        CompileResult Compile(const SourceText& source)
        {
            DiagnosticBag diagnostics(source);
            std::vector<Token> tokens = Lexer(source, diagnostics).Lex();
            Parser parser(std::move(tokens), diagnostics);
            const FileSyntax* tree = parser.ParseFile();
            nodes_ = parser.TakeNodes();                    // the tree must outlive the binder's results
            binder_ = std::make_unique<Binder>(diagnostics);
            const Scope& global = binder_->BindProgram({ tree });   // names, types; never throws on user errors
            if (diagnostics.HasErrors()) return { diagnostics.Items() };

            CompileResult result;
            for (const ItemSyntax* item : tree->items)
            {
                auto* syntax = dynamic_cast<const FunctionSyntax*>(item);
                if (!syntax) continue;
                auto* function = static_cast<const FunctionSymbol*>(global.Lookup(syntax->name.text));
                LoweredFunction lowered = Lowerer::Lower(function);
                FlowChecks::Run(function, *ControlFlowGraph::Build(lowered.body), diagnostics);   // missing returns, unassigned locals
                result.lowered.emplace(function, std::move(lowered));
            }
            result.diagnostics = diagnostics.Items();       // warnings may still be there
            result.succeeded = !diagnostics.HasErrors();
            if (!result.succeeded) result.lowered.clear();
            return result;
        }

    private:
        std::vector<std::unique_ptr<SyntaxNode>> nodes_;
        std::unique_ptr<Binder> binder_;
    };
    ```

=== "C#"

    ```csharp
    public sealed record CompileResult(
        ImmutableArray<Diagnostic> Diagnostics,
        ImmutableDictionary<FunctionSymbol, ImmutableArray<BoundStatement>>? Lowered);   // null when there are errors

    public static class Compilation
    {
        // One file here. With several, each file gets its own bag, and the binder reports into the bag of the file it is binding.
        public static CompileResult Compile(SourceText source)
        {
            var diagnostics = new DiagnosticBag(source);
            List<Token> tokens = new Lexer(source, diagnostics).Lex();
            FileSyntax tree = new Parser(tokens, diagnostics).ParseFile();
            Scope global = new Binder(diagnostics).BindProgram([tree]);           // names, types; never throws on user errors
            if (diagnostics.HasErrors) return new CompileResult([.. diagnostics], null);

            var lowered = ImmutableDictionary.CreateBuilder<FunctionSymbol, ImmutableArray<BoundStatement>>();
            foreach (var item in tree.Items.OfType<FunctionSyntax>())
            {
                var function = (FunctionSymbol)global.Lookup(item.Name.Text!)!;
                ImmutableArray<BoundStatement> body = Lowerer.Lower(function);
                FlowChecks.Run(function, ControlFlowGraph.Build(body), diagnostics);   // missing returns, unassigned locals
                lowered[function] = body;
            }
            if (diagnostics.HasErrors) return new CompileResult([.. diagnostics], null);
            return new CompileResult([.. diagnostics], lowered.ToImmutable());   // warnings may still be there
        }
    }

    public static class Compilation
    {
        // One file here. With several, each file gets its own bag, and the binder reports into the bag of the file it is binding.
        public static CompileResult Compile(SourceText source)
        {
            var diagnostics = new DiagnosticBag(source);
            List<Token> tokens = new Lexer(source, diagnostics).Lex();
            FileSyntax tree = new Parser(tokens, diagnostics).ParseFile();
            Scope global = new Binder(diagnostics).BindProgram([tree]);           // names, types; never throws on user errors
            if (diagnostics.HasErrors) return new CompileResult([.. diagnostics], null);

            var lowered = ImmutableDictionary.CreateBuilder<FunctionSymbol, ImmutableArray<BoundStatement>>();
            foreach (var item in tree.Items.OfType<FunctionSyntax>())
            {
                var function = (FunctionSymbol)global.Lookup(item.Name.Text!)!;
                ImmutableArray<BoundStatement> body = Lowerer.Lower(function);
                FlowChecks.Run(function, ControlFlowGraph.Build(body), diagnostics);   // missing returns, unassigned locals
                lowered[function] = body;
            }
            if (diagnostics.HasErrors) return new CompileResult([.. diagnostics], null);
            return new CompileResult([.. diagnostics], lowered.ToImmutable());   // warnings may still be there
        }
    }
    ```

## Order of work

Get something running end to end early, then grow every stage together. A complete lexer for a language that cannot run teaches you less than a whole pipeline for integer arithmetic.

1. **Expressions.** Lex and parse `1 + 2 * 3`, print the tree, evaluate it with a tree-walking [evaluator](evaluator.md).
2. **Functions and locals.** `fn`, `let`, `var`, `return`, parameters; the binder and scopes; `i32` and `bool` only.
3. **Control flow.** `if`, `while`, comparisons, `&&` and `||`; lowering to jumps; checks for missing returns.
4. **LLVM.** Generate IR for everything so far, JIT `main`, and compare its result with the evaluator's.
5. **More types.** Floats, conversions, structs, pointers or references, `extern` functions.
6. **Native output.** Emit an object file and link it with the system linker.
7. **Later.** Modules and imports, generics, arrays and slices, [debug info](debug-info.md), a [standard library](standard-library.md), and a [language server](language-server.md).

The evaluator from step 1 stays useful: it is the reference that the compiled code is tested against.

## C++ tips

- **C++20** gives `std::format`, designated initialisers, `std::span`, and `contains` on maps; all the code here uses it.
- **Build tests with sanitizers** (`-fsanitize=address,undefined` with GCC or Clang, `/fsanitize=address` with MSVC). A compiler is a graph of pointers, and use-after-free bugs in it are otherwise silent.
- **One owner per stage**: the parser owns the syntax nodes and the binder the symbols and bound nodes, and everything else holds plain `const` pointers. Keep each owner alive for as long as anything reads its output, as `Compilation` does.
- **Strings:** tokens hold `std::string_view`s into the source text; symbols copy names into `std::string`.
- **Switch on a `kind` enum** to dispatch on node types, with `static_cast` to the concrete type. `dynamic_cast` is fine where there are only a few cases.

## C# tips

- **Language features that fit compilers:** `sealed class`es with primary constructors for nodes and symbols (not records: nodes compare by reference), `switch` expressions with type patterns for walking trees, and `ImmutableArray<T>` for children.
- **Turn on nullable reference types and warnings as errors** from the start. A compiler is a large graph of objects, and null references are the commonest crash.
- **Strings:** lex from `ReadOnlySpan<char>` or `ReadOnlyMemory<char>`, and create `string` objects only for identifiers and literals.
- **Lookups:** `FrozenDictionary` (keyword tables, built once) and `SearchValues<char>` (character classes) are fast for tables that never change.
- **Do not copy Roslyn's architecture on day one.** Its red-green trees, incremental parsing, and lazy binding exist for an IDE editing a million-line codebase. Start simple and add these when a language server needs them.

## Reading

- [Crafting Interpreters](https://craftinginterpreters.com/), Robert Nystrom. Lexing, parsing, resolving, and two interpreters, written with great clarity.
- [Minsk](https://github.com/terrajobst/minsk), Immo Landwerth. A compiler written in C# on video, in the style of Roslyn: syntax trees, binder, lowering, and diagnostics. The closest match to these pages.
- [Simple but powerful Pratt parsing](https://matklad.github.io/2020/04/13/simple-but-powerful-pratt-parsing.html) and [Resilient LL parsing](https://matklad.github.io/2023/05/21/resilient-ll-parsing-tutorial.html), Alex Kladov. Expression parsing and error recovery.
- [LLVM Kaleidoscope tutorial](https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/index.html). The C++ version of the backend work.
- *Engineering a Compiler*, Cooper and Torczon. The textbook for everything after the parser.
