# Testing a compiler

A compiler has an unusually testable shape: every stage is a pure function from one data structure to the next, and the whole thing is a function from text to behaviour. Most of its tests are files: a program in, an expected result out.

## What to test

| Kind | Checks | Written as |
| --- | --- | --- |
| Unit, per stage | one token kind, one parse rule, one type rule, one diagnostic | small code-level tests: the input, and one assertion |
| Snapshot | the whole output of a stage: tokens, a printed tree, lowered code, IR | the input, and an approved output file |
| Diagnostic | which errors, with which codes, at which spans | source files with the expected errors marked inline |
| End to end | the compiled program's behaviour: exit code, output | `.lang` files with the expected output |
| Differential | two implementations agree: the tree-walking evaluator and the compiled code | the same programs, run both ways |
| Robustness | nothing crashes, hangs, or loses text on any input | round-trip checks and fuzzing |

The first few weeks need mostly unit and snapshot tests. Once the backend runs, end-to-end tests become most of the suite, because they keep checking what users see while the inside changes.

## Unit tests

Table-driven tests suit the lexer and the operator rules:

=== "C++"

    ```cpp
    std::vector<SyntaxKind> Kinds(std::string_view text)
    {
        SourceText source("test", std::string(text));
        DiagnosticBag diagnostics(source);
        std::vector<SyntaxKind> kinds;
        for (const Token& t : Lexer(source, diagnostics).Lex()) kinds.push_back(t.kind);
        return kinds;
    }

    struct LexerCase { std::string_view text; std::vector<SyntaxKind> kinds; };

    class LexerTest : public testing::TestWithParam<LexerCase> {};

    TEST_P(LexerTest, Kinds)
    {
        auto [text, expected] = GetParam();
        expected.push_back(SyntaxKind::EndOfFileToken);
        EXPECT_EQ(Kinds(text), expected) << "lexing " << text;
    }

    using enum SyntaxKind;
    INSTANTIATE_TEST_SUITE_P(Tokens, LexerTest, testing::Values(
        LexerCase{ "fn", { FnKeyword } },
        LexerCase{ "->", { ArrowToken } },
        LexerCase{ "-1", { MinusToken, IntLiteralToken } },                       // the minus is not part of the literal
        LexerCase{ "1.5e3", { FloatLiteralToken } },
        LexerCase{ "1..2", { IntLiteralToken, DotToken, DotToken, IntLiteralToken } },
        LexerCase{ "format", { IdentifierToken } }));                              // not `for` + `mat`
    ```

=== "C#"

    ```csharp
    public class LexerTests
    {
        static SyntaxKind[] Kinds(string text)
        {
            var source = new SourceText("test", text);
            return [.. new Lexer(source, new DiagnosticBag(source)).Lex().Select(t => t.Kind)];
        }

        [Theory]
        [InlineData("fn", new[] { SyntaxKind.FnKeyword })]
        [InlineData("->", new[] { SyntaxKind.ArrowToken })]
        [InlineData("-1", new[] { SyntaxKind.MinusToken, SyntaxKind.IntLiteralToken })]   // the minus is not part of the literal
        [InlineData("1.5e3", new[] { SyntaxKind.FloatLiteralToken })]
        [InlineData("1..2", new[] { SyntaxKind.IntLiteralToken, SyntaxKind.DotToken, SyntaxKind.DotToken, SyntaxKind.IntLiteralToken })]
        [InlineData("format", new[] { SyntaxKind.IdentifierToken })]                       // not `for` + `mat`
        public void Lexes(string text, SyntaxKind[] expected) =>
            Assert.Equal([.. expected, SyntaxKind.EndOfFileToken], Kinds(text));
    }
    ```

Test **pairs of tokens** as well as single ones: for every pair of token kinds, lex their texts joined with and without a space, and check that you get both back (unless they combine, like `-` and `>`). It finds longest-match bugs that single-token tests miss.

For the parser, test precedence by printing with explicit parentheses (this language has no `..` token yet, so `1..2` is two dots above):

=== "C++"

    ```cpp
    std::string Parenthesise(const ExpressionSyntax* e)            // every operation in parentheses
    {
        switch (e->kind)
        {
        case SyntaxKind::BinaryExpression:
        {
            auto* b = static_cast<const BinarySyntax*>(e);
            return std::format("({} {} {})", Parenthesise(b->left), b->op.text, Parenthesise(b->right));
        }
        case SyntaxKind::AssignmentExpression:
        {
            auto* a = static_cast<const AssignmentSyntax*>(e);
            return std::format("({} {} {})", Parenthesise(a->target), a->op.text, Parenthesise(a->value));
        }
        case SyntaxKind::UnaryExpression:
        {
            auto* u = static_cast<const UnarySyntax*>(e);
            return std::format("({}{})", u->op.text, Parenthesise(u->operand));
        }
        case SyntaxKind::MemberExpression:
        {
            auto* m = static_cast<const MemberSyntax*>(e);
            return std::format("({}.{})", Parenthesise(m->target), m->name.text);
        }
        case SyntaxKind::CallExpression:
        {
            auto* c = static_cast<const CallSyntax*>(e);
            std::string arguments;
            for (const ExpressionSyntax* a : c->arguments.items) arguments += (arguments.empty() ? "" : ", ") + Parenthesise(a);
            return std::format("({}({}))", Parenthesise(c->callee), arguments);
        }
        case SyntaxKind::ParenthesizedExpression: return Parenthesise(static_cast<const ParenthesizedSyntax*>(e)->inner);
        default: return std::string(e->FirstToken()->text);   // names and literals
        }
    }

    // Parenthesise(text) parses an expression and calls the function above.

    TEST(Parser, Precedence)
    {
        EXPECT_EQ(Parenthesise("a + b * c"), "(a + (b * c))");
        EXPECT_EQ(Parenthesise("a = b = c"), "(a = (b = c))");
        EXPECT_EQ(Parenthesise("-a.b(c)"), "(-((a.b)(c)))");
    }
    ```

=== "C#"

    ```csharp
    static string Parenthesise(ExpressionSyntax e) => e switch      // every operation in parentheses
    {
        BinarySyntax b => $"({Parenthesise(b.Left)} {Describe.Kind(b.Operator.Kind).Trim('\'')} {Parenthesise(b.Right)})",
        AssignmentSyntax a => $"({Parenthesise(a.Target)} {Describe.Kind(a.Operator.Kind).Trim('\'')} {Parenthesise(a.Value)})",
        UnarySyntax u => $"({Describe.Kind(u.Operator.Kind).Trim('\'')}{Parenthesise(u.Operand)})",
        MemberSyntax m => $"({Parenthesise(m.Target)}.{m.Name.Text})",
        CallSyntax c => $"({Parenthesise(c.Callee)}({string.Join(", ", c.Arguments.Items.Select(Parenthesise))}))",
        ParenthesizedSyntax p => Parenthesise(p.Inner),
        _ => e.Tokens().First().Text!,                                // names and literals
    };

    // Parenthesise(text) parses an expression and calls the function above.

    [Fact]
    public void Precedence()
    {
        Assert.Equal("(a + (b * c))", Parenthesise("a + b * c"));
        Assert.Equal("(a = (b = c))", Parenthesise("a = b = c"));
        Assert.Equal("(-((a.b)(c)))", Parenthesise("-a.b(c)"));
    }
    ```

## Snapshot tests

Print a stage's output, compare it with an approved file, and fail on any difference:

=== "C++"

    ```cpp
    void ExpectSnapshot(const std::string& name, const std::string& actual)
    {
        fs::path path = fs::path(SNAPSHOT_DIR) / (name + ".txt");
        bool update = std::getenv("UPDATE_SNAPSHOTS") != nullptr;
        if (update || !fs::exists(path))
        {
            std::ofstream(path, std::ios::binary) << actual;
            if (!update) ADD_FAILURE() << "new snapshot written to " << path << "; review and commit it";
            return;
        }
        EXPECT_EQ(actual, ReadFile(path)) << "snapshot " << name << " changed; set UPDATE_SNAPSHOTS=1 to accept";
    }

    TEST(Snapshots, SumToTree)
    {
        SourceText source("sum_to.lang", "fn sum_to(n: i32) -> i32 { var total = 0; return total + n; }");
        DiagnosticBag diagnostics(source);
        Parser parser(Lexer(source, diagnostics).Lex(), diagnostics);
        const FileSyntax* tree = parser.ParseFile();
        ExpectSnapshot("sum_to_tree", PrintTree(*tree->items[0]));   // or tokens, lowered code, LLVM IR
    }
    ```

=== "C#"

    ```csharp
    public static class Snapshot
    {
        // Snapshots live next to this source file, so editing one needs no rebuild.
        public static void Match(string name, string actual, [CallerFilePath] string testFile = "")
        {
            string path = Path.Combine(Path.GetDirectoryName(testFile)!, "snapshots", name + ".txt");
            bool update = Environment.GetEnvironmentVariable("UPDATE_SNAPSHOTS") is not null;
            if (update || !File.Exists(path))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                File.WriteAllText(path, actual);
                if (!update) Assert.Fail($"new snapshot written to {path}; review and commit it");
                return;
            }
            Assert.Equal(File.ReadAllText(path), actual);   // set UPDATE_SNAPSHOTS=1 to accept a change
        }
    }

    public class SnapshotTests
    {
        [Fact]
        public void SumToTree()
        {
            var source = new SourceText("sum_to.lang", "fn sum_to(n: i32) -> i32 { var total = 0; return total + n; }");
            var diagnostics = new DiagnosticBag(source);
            FileSyntax tree = new Parser(new Lexer(source, diagnostics).Lex(), diagnostics).ParseFile();
            Snapshot.Match("sum_to_tree", SyntaxPrinter.Print(tree.Items[0]));   // or tokens, lowered code, LLVM IR
        }
    }
    ```

- Review every snapshot change in the diff of the commit. A snapshot that is updated without looking is no test at all.
- Keep snapshots **stable**: no memory addresses, no hash-ordered output, no absolute paths. Sort anything that comes out of a dictionary.
- **LLVM IR snapshots** are useful for code generation, but fragile across LLVM versions and optimisation levels. Snapshot the unoptimised IR, and test optimised code by running it.

## Diagnostic tests

Mark expected errors in the source itself, next to the code that causes them:

```text
fn main() -> i32 {
    let x: i32 = 1.5;          //~ error E0201
    let y = undefined_name;    //~ error E0101
    return x;
}
```

=== "C++"

    ```cpp
    struct ExpectedDiagnostic
    {
        uint32_t line;
        std::string severity, code;
        auto operator<=>(const ExpectedDiagnostic&) const = default;
    };

    std::vector<ExpectedDiagnostic> ExpectedFromMarkers(const SourceText& source)   // "//~ error E0201" on a line
    {
        static const std::regex marker(R"(//~\s*(error|warning)\s+([EW]\d{4}))");
        std::vector<ExpectedDiagnostic> expected;
        std::string_view text = source.Text();
        for (auto it = std::cregex_iterator(text.data(), text.data() + text.size(), marker); it != std::cregex_iterator(); ++it)
            expected.push_back({ source.Position(uint32_t(it->position())).line, (*it)[1], (*it)[2] });
        return expected;
    }

    class DiagnosticTest : public testing::TestWithParam<fs::path> {};

    TEST_P(DiagnosticTest, MatchesMarkers)
    {
        SourceText source(GetParam().string(), ReadFile(GetParam()));
        std::vector<ExpectedDiagnostic> expected = ExpectedFromMarkers(source);
        std::vector<ExpectedDiagnostic> actual;
        for (const Diagnostic& d : Compilation().Compile(source).diagnostics)
            actual.push_back({ source.Position(d.span.start).line, d.GetSeverity() == Severity::Error ? "error" : "warning",
                               std::string(d.Info().code) });
        std::ranges::sort(expected);
        std::ranges::sort(actual);
        EXPECT_EQ(actual, expected);
    }

    std::vector<fs::path> CaseFiles(const char* folder)
    {
        std::vector<fs::path> files;
        for (const auto& entry : fs::directory_iterator(fs::path(CASES_DIR) / folder))
            if (entry.path().extension() == ".lang") files.push_back(entry.path());
        std::ranges::sort(files);
        return files;
    }

    INSTANTIATE_TEST_SUITE_P(Cases, DiagnosticTest, testing::ValuesIn(CaseFiles("diagnostics")),
                             [](const auto& info) { return info.param.stem().string(); });   // one test per file, by name
    ```

=== "C#"

    ```csharp
    public static class Cases
    {
        public static string[] Files(string folder) =>   // the case files are copied to the output directory
            [.. Directory.GetFiles(Path.Combine(AppContext.BaseDirectory, "cases", folder), "*.lang").Order()];

        public static TheoryData<string> In(string folder) => new(Files(folder));   // one test per file
    }

    public class DiagnosticTests
    {
        public static TheoryData<string> Files => Cases.In("diagnostics");

        static readonly Regex Marker = new(@"//~\s*(error|warning)\s+([EW]\d{4})");

        [Theory]
        [MemberData(nameof(Files))]
        public void MatchesMarkers(string file)
        {
            var source = new SourceText(file, File.ReadAllText(file));
            var expected = Marker.Matches(source.Text)                     // "//~ error E0201" on a line
                .Select(m => (source.Position(m.Index).Line, m.Groups[1].Value, m.Groups[2].Value))
                .Order().ToList();
            var actual = Compilation.Compile(source).Diagnostics
                .Select(d => (source.Position(d.Span.Start).Line, d.Severity == Severity.Error ? "error" : "warning", d.Descriptor.Code))
                .Order().ToList();
            Assert.Equal(expected, actual);
        }
    }
    ```

- Match on **codes**, not on message text, so rewording a message does not break every test. Have a few separate tests that do check the exact wording of important messages.
- For an exact span, mark it in the text with brackets that the test removes before compiling: `let x: i32 = [1.5];` says the error covers exactly `1.5`. Minsk uses this style.
- Every diagnostic the compiler can produce should have at least one test that triggers it. A table of codes against test files makes gaps visible.
- Test the **absence** of cascades: a file with one mistake produces exactly one error.

## End-to-end tests

```text
// tests/cases/sum_to.lang
// expect-exit: 55
// expect-output: Y

fn main() -> i32 { ... }
```

=== "C++"

    ```cpp
    struct RunResult
    {
        int64_t exitCode = 0;
        std::string output, panic;
        bool operator==(const RunResult&) const = default;
    };

    class Backend                                          // the evaluator, the JIT, and a linked executable
    {
    public:
        virtual ~Backend() = default;
        virtual RunResult Run(const CompileResult& program) = 0;
    };

    // EvaluatorBackend runs main in the reference evaluator, with a host putchar that records the output.
    // JitBackend and ExecutableBackend run the code generator's output: in process, or linked and run with a timeout.

    struct CaseHeader { std::optional<int64_t> exitCode; std::optional<std::string> output; };

    CaseHeader ParseHeader(std::string_view text)             // "// expect-exit: 55" and "// expect-output: Y" at the top
    {
        CaseHeader header;
        static const std::regex line(R"(^// expect-(exit|output): (.*)$)");
        std::istringstream lines{ std::string(text) };
        for (std::string l; std::getline(lines, l) && l.starts_with("//");)
            if (std::smatch m; std::regex_match(l, m, line))
            {
                if (m[1] == "exit") header.exitCode = std::stoll(m[2]);
                else header.output = m[2];
            }
        return header;
    }

    class EndToEnd : public testing::TestWithParam<fs::path>
    {
    protected:
        CompileResult Compile()
        {
            source_ = std::make_unique<SourceText>(GetParam().string(), ReadFile(GetParam()));
            CompileResult result = compilation_.Compile(*source_);
            for (const Diagnostic& d : result.diagnostics) ADD_FAILURE() << Render(d);
            return result;
        }
        std::unique_ptr<SourceText> source_;
        Compilation compilation_;                          // owns the trees and symbols the result points into
    };

    TEST_P(EndToEnd, MatchesHeader)
    {
        CompileResult program = Compile();
        ASSERT_TRUE(program.succeeded);
        CaseHeader header = ParseHeader(source_->Text());
        RunResult run = JitBackend().Run(program);            // fast: no linker, no process
        EXPECT_EQ(run.panic, "");
        if (header.exitCode) { EXPECT_EQ(run.exitCode, *header.exitCode); }
        if (header.output) { EXPECT_EQ(run.output, *header.output); }
    }

    INSTANTIATE_TEST_SUITE_P(Cases, EndToEnd, testing::ValuesIn(CaseFiles("run")), CaseName);
    ```

=== "C#"

    ```csharp
    public sealed record RunResult(long ExitCode, string Output, string? Panic);

    public interface IBackend                                               // the evaluator, the JIT, and a linked executable
    {
        RunResult Run(CompileResult program);
    }

    // EvaluatorBackend runs main in the reference evaluator, with a host putchar that records the output.
    // JitBackend and ExecutableBackend run the code generator's output: in process, or linked and run with a timeout.

    public sealed record CaseHeader(long? ExitCode, string? Output)
    {
        public static CaseHeader Parse(string text)                       // "// expect-exit: 55" and "// expect-output: Y" at the top
        {
            long? exitCode = null;
            string? output = null;
            foreach (string line in text.Split('\n').TakeWhile(l => l.StartsWith("//")))
            {
                if (line.StartsWith("// expect-exit: ")) exitCode = long.Parse(line["// expect-exit: ".Length..]);
                if (line.StartsWith("// expect-output: ")) output = line["// expect-output: ".Length..].TrimEnd('\r');
            }
            return new CaseHeader(exitCode, output);
        }
    }

    public class EndToEndTests
    {
        public static TheoryData<string> Files => Cases.In("run");

        static CompileResult Compile(string file)
        {
            CompileResult result = Compilation.Compile(new SourceText(file, File.ReadAllText(file)));
            Assert.True(result.Lowered is not null, string.Join("\n", result.Diagnostics.Select(DiagnosticRenderer.Render)));
            return result;
        }

        [Theory]
        [MemberData(nameof(Files))]
        public void MatchesHeader(string file)
        {
            CaseHeader header = CaseHeader.Parse(File.ReadAllText(file));
            RunResult run = new JitBackend().Run(Compile(file));           // fast: no linker, no process
            Assert.Null(run.Panic);
            if (header.ExitCode is long exitCode) Assert.Equal(exitCode, run.ExitCode);
            if (header.Output is string output) Assert.Equal(output, run.Output);
        }
    }
    ```

- **JIT in process** for most cases: no linker or process start, so thousands of cases run in seconds.
- **Build and run a real executable** for a smaller set: it tests the object file, the linker command, and calls into the C runtime the JIT may resolve differently.
- Always **verify the module** in tests, even when the program would run anyway.
- **Every backend implements one interface** (`Backend` above), so a case runs the same way through the evaluator, the JIT, and a linked executable, and the differential test below is two lines.
- Use a **timeout** for every run. A miscompiled loop does not end.

## Differential testing

The [reference evaluator](evaluator.md) from the first milestone is a second implementation of the language's meaning. Run every end-to-end case through both, and compare:

=== "C++"

    ```cpp
    TEST_P(EndToEnd, BackendsAgree)                            // differential: the evaluator is the oracle
    {
        CompileResult program = Compile();
        ASSERT_TRUE(program.succeeded);
        EXPECT_EQ(EvaluatorBackend().Run(program), JitBackend().Run(program));
    }
    ```

=== "C#"

    ```csharp
    [Theory]
    [MemberData(nameof(Files))]
    public void BackendsAgree(string file)                              // differential: the evaluator is the oracle
    {
        CompileResult program = Compile(file);
        Assert.Equal(new EvaluatorBackend().Run(program), new JitBackend().Run(program));
    }
    ```

`RunResult` compares the exit code, the output, and any panic message, so a panic in one backend and not the other is a difference too. When they disagree, one has a bug, and the case shows which construct. Keep the evaluator up to date with the language for as long as you can; it is far easier to get right than code generation.

## Robustness

- **Round trip**: printing the tokens and trivia of `parse(text)` gives back `text`, for every test file.
- **Every prefix** of every test file (cut at each character) must compile without crashing, and every span must lie inside the text. Prefixes are what an editor sends while someone types, and they find crashes in error recovery: the test below found a binder crash on `struct` with no name yet.

=== "C++"

    ```cpp
    TEST(Robustness, EveryPrefixCompiles)                       // what an editor sends while someone types
    {
        for (const fs::path& file : CaseFiles("run"))
        {
            std::string text = ReadFile(file);
            for (size_t length = 0; length <= text.size(); length++)
            {
                SourceText source("prefix", text.substr(0, length));
                CompileResult result = Compilation().Compile(source);   // must return, not crash or hang
                for (const Diagnostic& d : result.diagnostics) ASSERT_LE(d.span.End(), length) << "span outside the text";
            }
        }
    }
    ```

=== "C#"

    ```csharp
    public class RobustnessTests
    {
        [Fact]
        public void EveryPrefixCompiles()                                   // what an editor sends while someone types
        {
            foreach (string file in Cases.Files("run"))
            {
                string text = File.ReadAllText(file);
                for (int length = 0; length <= text.Length; length++)
                {
                    CompileResult result = Compilation.Compile(new SourceText("prefix", text[..length]));   // must return
                    Assert.All(result.Diagnostics, d => Assert.True(d.Span.End <= length, "span outside the text"));
                }
            }
        }
    }
    ```

- **Fuzz the front end**: feed random bytes, random token sequences, and mutated test files to the lexer, parser, and binder. The only assertions are that it returns, does not throw, and every reported span is inside the text.
- **Fuzz the whole compiler** with randomly generated valid programs (small expression trees with known values), compared against the evaluator. This finds miscompilations in constant folding and code generation.
- **Every bug gets a test**: reduce the program that triggered it to the smallest one that still fails, and add it as a case.

## C++ tips

- **GoogleTest**: `TEST_P` with `INSTANTIATE_TEST_SUITE_P` and `testing::ValuesIn(files)` gives one named test per case file, as above; pass a name generator so failures say `Cases/EndToEnd.MatchesHeader/sum_to`. Catch2's `GENERATE` and doctest's subcases do the same.
- **Find case files** from a path compiled in (`-DCASES_DIR="${CMAKE_CURRENT_SOURCE_DIR}/cases"` in CMake), so tests run from any working directory and editing a case needs no rebuild.
- **Give the types a printer** (`operator<<`, or GoogleTest's `PrintTo`), so a failed `EXPECT_EQ` on a `RunResult` or a list of diagnostics shows the values.
- **Run the suite under sanitizers** in CI (`-fsanitize=address,undefined`), and the language server's tests under `-fsanitize=thread`.
- Run compiled executables with a timeout: `boost::process`, `reproc`, or `posix_spawn` and `waitpid` with an alarm; kill the process when it expires.
- [libFuzzer](https://llvm.org/docs/LibFuzzer.html) (`-fsanitize=fuzzer`) calls a `LLVMFuzzerTestOneInput(data, size)` function with mutated inputs; compile the source text it is given, and the sanitizers report any crash.

## C# tips

- Any test framework works. With xUnit v3, a `[Theory]` whose `[MemberData]` returns `TheoryData<string>` of file paths gives one test per file, as above, each shown in the test explorer.
- [Verify](https://github.com/VerifyTests/Verify) is a .NET snapshot library: `await Verify(PrintTree(tree))` writes `*.received.txt`, compares it with `*.verified.txt`, and can open a diff tool. It replaces the hand-written `Snapshot.Match` above.
- Copy test case files to the output directory (`<None Include="cases/**" CopyToOutputDirectory="PreserveNewest" />`), or locate them from `[CallerFilePath]` so editing a case needs no rebuild.
- Run compiled executables with `Process.Start` and `RedirectStandardOutput = true`, and wait with `WaitForExitAsync(cancellationToken)` from a `CancellationTokenSource` with a timeout; kill the process on timeout.
- JIT tests share one process. Create a new LLJIT per test (or per test class) so a module from one test cannot satisfy a symbol in another, and dispose it with `LLVM.OrcDisposeLLJIT`.
- [SharpFuzz](https://github.com/Metalnem/sharpfuzz) runs .NET code under libFuzzer or AFL. A plain loop over random inputs, run in CI for a minute, already finds most parser crashes.
