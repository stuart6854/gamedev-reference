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

```text
lexer_cases = [
    ("fn",      [FnKeyword]),
    ("->",      [Arrow]),
    ("-1",      [Minus, IntLiteral]),             // the minus is not part of the literal
    ("1.5e3",   [FloatLiteral]),
    ("1..2",    [IntLiteral, DotDot, IntLiteral]),
    ("format",  [Identifier]),                    // not `for` + `mat`
]

for (text, expected) in lexer_cases:
    assert kinds(lex(text)) == expected + [EndOfFile]
```

Test **pairs of tokens** as well as single ones: for every pair of token kinds, lex their texts joined with and without a space, and check that you get both back (unless they combine, like `-` and `>`). It finds longest-match bugs that single-token tests miss.

For the parser, test precedence by printing with explicit parentheses:

```text
assert parenthesise(parse_expression("a + b * c"))   == "(a + (b * c))"
assert parenthesise(parse_expression("a = b = c"))   == "(a = (b = c))"
assert parenthesise(parse_expression("-a.b(c)"))     == "(-((a.b)(c)))"
```

## Snapshot tests

Print a stage's output, compare it with an approved file, and fail on any difference:

```text
snapshot_test(name, input):
    actual = print_tree(parse(input))              // or tokens, lowered code, LLVM IR
    path = "snapshots/{name}.txt"
    if not exists(path) or environment says UPDATE_SNAPSHOTS:
        write(path, actual)
        if not updating: fail("new snapshot written; review and commit it")
    else:
        assert actual == read(path), show a diff
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

```text
diagnostic_test(file):
    expected = for each line with "//~ severity CODE": (line number, severity, code)
    actual   = (line, severity, code) for each diagnostic from compiling the file
    assert sorted(actual) == sorted(expected)
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

```text
run_case(file):
    header = parse the expect-* comments at the top
    result = compile(file)
    assert no errors
    if header has expect-output or uses the C runtime:
        emit an object file, link it, run the executable with a timeout
        assert exit code and stdout match
    else:
        JIT main in process, call it, assert its return value     // fast: no linker, no process
```

- **JIT in process** for most cases: no linker or process start, so thousands of cases run in seconds.
- **Build and run a real executable** for a smaller set: it tests the object file, the linker command, and calls into the C runtime the JIT may resolve differently.
- Always **verify the module** in tests, even when the program would run anyway.
- Use a **timeout** for every run. A miscompiled loop does not end.

## Differential testing

The tree-walking evaluator from the first milestone is a second implementation of the language's meaning. Run every end-to-end case through both, and compare:

```text
for case in cases:
    assert evaluate(bind(parse(case))) == jit_and_run(case)
```

When they disagree, one has a bug, and the case shows which construct. Keep the evaluator up to date with the language for as long as you can; it is far easier to get right than code generation.

## Robustness

- **Round trip**: `print_tokens_and_trivia(parse(text)) == text` for every test file, and for every prefix of every test file (cut at each character). Prefixes are what an editor sends while someone types, and they find crashes in error recovery.
- **Fuzz the front end**: feed random bytes, random token sequences, and mutated test files to the lexer, parser, and binder. The only assertions are that it returns, does not throw, and every reported span is inside the text.
- **Fuzz the whole compiler** with randomly generated valid programs (small expression trees with known values), compared against the evaluator. This finds miscompilations in constant folding and code generation.
- **Every bug gets a test**: reduce the program that triggered it to the smallest one that still fails, and add it as a case.

## C# tips

- Any test framework works. With xUnit v3, a `[Theory]` whose `[MemberData]` lists `Directory.GetFiles("cases", "*.lang")` gives one test per file, each shown by name in the test explorer.
- [Verify](https://github.com/VerifyTests/Verify) is a .NET snapshot library: `await Verify(PrintTree(tree))` writes `*.received.txt`, compares it with `*.verified.txt`, and can open a diff tool. It handles the update-and-review workflow above.
- Copy test case files to the output directory (`<None Include="cases/**" CopyToOutputDirectory="PreserveNewest" />`), or locate them from `[CallerFilePath]` so editing a case needs no rebuild.
- Run compiled executables with `Process.Start` and `RedirectStandardOutput = true`, and wait with `WaitForExitAsync(cancellationToken)` from a `CancellationTokenSource` with a timeout; kill the process on timeout.
- JIT tests share one process. Create a new LLJIT per test (or per test class) so a module from one test cannot satisfy a symbol in another, and dispose it with `LLVM.OrcDisposeLLJIT`.
- [SharpFuzz](https://github.com/Metalnem/sharpfuzz) runs .NET code under libFuzzer or AFL. A plain loop over random inputs, run in CI for a minute, already finds most parser crashes.
