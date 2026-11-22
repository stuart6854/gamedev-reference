# Source text and diagnostics

Every later stage points back at the source: a token knows where it starts, a type error underlines an expression, and debug info maps machine code to lines. Getting this right first makes every error message cheap to write.

## Source text and spans

Positions are stored as **offsets** into the text, not as lines and columns. An offset is one integer, cheap to compare and add, and stays valid however lines are counted. Lines and columns are worked out only when a message is shown.

=== "C++"

    ```cpp
    struct TextSpan
    {
        uint32_t start = 0, length = 0;                  // covers [start, start + length)
        uint32_t End() const { return start + length; }
        static TextSpan FromBounds(uint32_t start, uint32_t end) { return { start, end - start }; }
    };

    struct LinePosition { uint32_t line, column; };     // 1-based, for people

    class SourceText
    {
    public:
        SourceText(std::string path, std::string text) : path_(std::move(path)), text_(std::move(text))
        {
            lineStarts_.push_back(0);
            for (uint32_t i = 0; i < text_.size(); i++)
            {
                if (text_[i] == '\r' && i + 1 < text_.size() && text_[i + 1] == '\n') continue;   // CRLF: break after the \n
                if (text_[i] == '\n' || text_[i] == '\r') lineStarts_.push_back(i + 1);
            }
        }

        const std::string& Path() const { return path_; }
        std::string_view Text() const { return text_; }

        uint32_t LineOf(uint32_t offset) const          // 0-based: the last line start <= offset
        {
            return uint32_t(std::upper_bound(lineStarts_.begin(), lineStarts_.end(), offset) - lineStarts_.begin()) - 1;
        }

        LinePosition Position(uint32_t offset) const
        {
            uint32_t line = LineOf(offset);
            return { line + 1, offset - lineStarts_[line] + 1 };
        }

    private:
        std::string path_;
        std::string text_;                               // the whole file, decoded once
        std::vector<uint32_t> lineStarts_;               // offset of the first character of each line
    };
    ```

=== "C#"

    ```csharp
    public readonly record struct TextSpan(int Start, int Length)   // covers [Start, End)
    {
        public int End => Start + Length;
        public static TextSpan FromBounds(int start, int end) => new(start, end - start);
    }

    public readonly record struct LinePosition(int Line, int Column);   // 1-based, for people

    public sealed class SourceText
    {
        readonly int[] _lineStarts;                      // offset of the first character of each line

        public SourceText(string path, string text)
        {
            Path = path;
            Text = text;                                 // the whole file, decoded once
            var starts = new List<int> { 0 };
            for (int i = 0; i < text.Length; i++)
            {
                if (text[i] == '\r' && i + 1 < text.Length && text[i + 1] == '\n') continue;   // CRLF: break after the \n
                if (text[i] is '\n' or '\r') starts.Add(i + 1);
            }
            _lineStarts = [.. starts];
        }

        public string Path { get; }
        public string Text { get; }

        public int LineOf(int offset)                    // 0-based: the last line start <= offset
        {
            int index = Array.BinarySearch(_lineStarts, offset);
            return index >= 0 ? index : ~index - 1;      // not a line start: the complement of the insertion point
        }

        public LinePosition Position(int offset)
        {
            int line = LineOf(offset);
            return new LinePosition(line + 1, offset - _lineStarts[line] + 1);
        }
    }
    ```

- A span of **length 0** marks a point: a missing semicolon is reported at the end of the previous token.
- Merge spans to cover a whole construct: `span(first.start, last.end - first.start)` for a binary expression or a function.
- Columns are in characters (UTF-16 code units in C#). Editors that count bytes or grapheme clusters will be off on lines with non-ASCII text; the language server protocol states which unit it expects.
- Strip a UTF-8 byte order mark when decoding, or offset 0 is invisible.

## Diagnostics

A **diagnostic** is a message with a severity, a span, and a code:

- **code**: `E0201`, stable and searchable. Tests match on it, and users search for it.
- **severity**: error or warning.
- **message**: "expected 'i32', found 'f32'".
- **location**: the source file and span.
- **related locations**: extra spans with a label, such as "'x' is first defined here".
- **fixes**: text to insert or replace, which an editor can apply.

Each stage adds to a **diagnostic bag** rather than throwing. Exceptions are for bugs in the compiler, not for bugs in the user's code.

### Defining diagnostics

Put every diagnostic in **one table**: its name, code, severity, and message format. Adding one is then one line, wording stays consistent, a code cannot be used twice, and a test or a documentation page can list them all.

=== "C++"

    ```c
    // diagnostics.def: one line per diagnostic. Codes are never reused or renumbered; a deleted one leaves a gap.
    // Lexer: E00xx
    DIAGNOSTIC(UnexpectedCharacter, "E0001", Error,   "unexpected character '{}'")
    DIAGNOSTIC(InvalidDigit,        "E0013", Error,   "invalid digit '{}' for base {}")
    // Parser: E005x
    DIAGNOSTIC(ExpectedToken,       "E0050", Error,   "expected {}, found {}")
    // Binder: E01xx
    DIAGNOSTIC(UndefinedName,       "E0101", Error,   "the name '{}' does not exist in this scope")
    DIAGNOSTIC(DuplicateDefinition, "E0102", Error,   "'{}' is already defined in this scope")
    // Type checker: E02xx
    DIAGNOSTIC(TypeMismatch,        "E0201", Error,   "expected '{}', found '{}'")
    // Warnings: Wxxxx
    DIAGNOSTIC(UnusedVariable,      "W0001", Warning, "the variable '{}' is never used")
    ```

=== "C#"

    ```csharp
    public static class Diagnostics
    {
        // Codes are never reused or renumbered; a deleted one leaves a gap.
        // Lexer: E00xx
        public static readonly Descriptor<char> UnexpectedCharacter = new("E0001", Severity.Error, "unexpected character '{0}'");
        public static readonly Descriptor<char, int> InvalidDigit = new("E0013", Severity.Error, "invalid digit '{0}' for base {1}");
        // Parser: E005x
        public static readonly Descriptor<string, string> ExpectedToken = new("E0050", Severity.Error, "expected {0}, found {1}");
        // Binder: E01xx
        public static readonly Descriptor<string> UndefinedName = new("E0101", Severity.Error, "the name '{0}' does not exist in this scope");
        public static readonly Descriptor<string> DuplicateDefinition = new("E0102", Severity.Error, "'{0}' is already defined in this scope");
        // Type checker: E02xx
        public static readonly Descriptor<string, string> TypeMismatch = new("E0201", Severity.Error, "expected '{0}', found '{1}'");
        // Warnings: Wxxxx
        public static readonly Descriptor<string> UnusedVariable = new("W0001", Severity.Warning, "the variable '{0}' is never used");

        public static IEnumerable<DiagnosticDescriptor> All() =>
            typeof(Diagnostics).GetFields().Select(f => f.GetValue(null)).OfType<DiagnosticDescriptor>();
    }
    ```

The table turns into types that make a wrong call a compile error:

=== "C++"

    ```cpp
    enum class Severity : uint8_t { Error, Warning };

    enum class Diag : uint16_t                           // Diag::ExpectedToken, ...
    {
    #define DIAGNOSTIC(name, code, severity, format) name,
    #include "diagnostics.def"
    #undef DIAGNOSTIC
    };

    struct DiagnosticInfo { std::string_view code; Severity severity; std::string_view format; };

    inline constexpr DiagnosticInfo kDiagnostics[] = {   // indexed by Diag
    #define DIAGNOSTIC(name, code, severity, format) { code, Severity::severity, format },
    #include "diagnostics.def"
    #undef DIAGNOSTIC
    };

    consteval bool CodesAreUnique()
    {
        for (size_t i = 0; i < std::size(kDiagnostics); i++)
            for (size_t j = i + 1; j < std::size(kDiagnostics); j++)
                if (kDiagnostics[i].code == kDiagnostics[j].code) return false;
        return true;
    }
    static_assert(CodesAreUnique(), "two diagnostics share a code");
    ```

=== "C#"

    ```csharp
    public enum Severity { Error, Warning }

    public abstract class DiagnosticDescriptor(string code, Severity severity, string format)
    {
        public string Code => code;
        public Severity Severity => severity;
        public CompositeFormat Format { get; } = CompositeFormat.Parse(format);   // parsed once; bad braces throw at start-up
        public abstract int ArgumentCount { get; }
    }

    // One class per argument count. The type arguments fix what Report accepts.
    public sealed class Descriptor(string code, Severity severity, string format) : DiagnosticDescriptor(code, severity, format)
    {
        public override int ArgumentCount => 0;
    }
    public sealed class Descriptor<T>(string code, Severity severity, string format) : DiagnosticDescriptor(code, severity, format)
    {
        public override int ArgumentCount => 1;
    }
    public sealed class Descriptor<T1, T2>(string code, Severity severity, string format) : DiagnosticDescriptor(code, severity, format)
    {
        public override int ArgumentCount => 2;
    }

    // A unit test checks the table: unique codes, and placeholders matching the argument count.
    [Fact]
    public void DiagnosticTableIsConsistent()
    {
        var all = Diagnostics.All().ToList();
        Assert.Equal(all.Count, all.Select(d => d.Code).Distinct().Count());
        Assert.All(all, d => Assert.Equal(d.ArgumentCount, d.Format.MinimumArgumentCount));
    }
    ```

- **Group codes by stage** (`E00xx` lexer, `E005x` parser, `E01xx` binder), so a code says where to look in the compiler.
- **Never reuse a code.** Old forum posts, tests, and suppressions refer to it. Retire a diagnostic by deleting its line and leaving the gap.
- **Arguments are values, not formatted text.** Pass the type, the name, the token kind, and let the table's format say where they go. One place then decides how a type is printed in every message.
- The table is also the input for **documentation**: one explanation page per code, as `rustc --explain E0308` does, can be generated from it, with an example added by hand.

### Reporting

The bag fills in the source file, counts errors, and returns the new diagnostic so a caller can add related locations or fixes:

=== "C++"

    ```cpp
    struct RelatedLocation { TextSpan span; std::string message; };   // "'x' is first defined here"
    struct Fix { TextSpan span; std::string replacement; };            // replace the span; an empty span inserts

    struct Diagnostic
    {
        Diag id;
        TextSpan span;
        std::string message;
        const SourceText* source = nullptr;              // set by the bag
        std::vector<RelatedLocation> related = {};
        std::vector<Fix> fixes = {};

        const DiagnosticInfo& Info() const { return kDiagnostics[size_t(id)]; }
        Severity GetSeverity() const { return Info().severity; }

        template <Diag Id, class... Args>
        static Diagnostic Make(TextSpan span, Args&&... args)
        {
            static constexpr std::string_view format = kDiagnostics[size_t(Id)].format;
            return { Id, span, std::format(format, std::forward<Args>(args)...) };   // argument count checked at compile time
        }

        Diagnostic& WithRelated(TextSpan s, std::string m) { related.push_back({ s, std::move(m) }); return *this; }
        Diagnostic& WithFix(TextSpan s, std::string r) { fixes.push_back({ s, std::move(r) }); return *this; }
    };

    class DiagnosticBag
    {
    public:
        explicit DiagnosticBag(const SourceText& source) : source_(&source) {}

        template <Diag Id, class... Args>
        Diagnostic& Report(TextSpan span, Args&&... args)
        {
            return Add(Diagnostic::Make<Id>(span, std::forward<Args>(args)...));
        }

        Diagnostic& Add(Diagnostic diagnostic)
        {
            diagnostic.source = source_;
            if (diagnostic.GetSeverity() == Severity::Error) errorCount_++;
            return items_.emplace_back(std::move(diagnostic));   // valid until the next Add
        }

        size_t Count() const { return items_.size(); }
        bool HasErrors() const { return errorCount_ > 0; }
        const std::vector<Diagnostic>& Items() const { return items_; }

        void Truncate(size_t count)                      // roll back to an earlier Count(), for speculative parsing
        {
            while (items_.size() > count)
            {
                if (items_.back().GetSeverity() == Severity::Error) errorCount_--;
                items_.pop_back();
            }
        }

    private:
        const SourceText* source_;
        std::vector<Diagnostic> items_;
        size_t errorCount_ = 0;
    };
    ```

=== "C#"

    ```csharp
    public readonly record struct RelatedLocation(TextSpan Span, string Message);   // "'x' is first defined here"
    public readonly record struct Fix(TextSpan Span, string Replacement);            // replace the span; an empty span inserts

    public sealed class Diagnostic(DiagnosticDescriptor descriptor, TextSpan span, string message)
    {
        public DiagnosticDescriptor Descriptor => descriptor;
        public Severity Severity => descriptor.Severity;
        public string Message => message;
        public TextSpan Span { get; internal set; } = span;
        public SourceText? Source { get; internal set; }   // set by the bag
        public List<RelatedLocation> Related { get; } = [];
        public List<Fix> Fixes { get; } = [];

        public Diagnostic WithRelated(TextSpan span, string message) { Related.Add(new(span, message)); return this; }
        public Diagnostic WithFix(TextSpan span, string replacement) { Fixes.Add(new(span, replacement)); return this; }

        static readonly CultureInfo Invariant = CultureInfo.InvariantCulture;
        public static Diagnostic Create(Descriptor d, TextSpan span) => new(d, span, string.Format(Invariant, d.Format));
        public static Diagnostic Create<T>(Descriptor<T> d, TextSpan span, T arg) => new(d, span, string.Format(Invariant, d.Format, arg));
        public static Diagnostic Create<T1, T2>(Descriptor<T1, T2> d, TextSpan span, T1 a, T2 b) =>
            new(d, span, string.Format(Invariant, d.Format, a, b));
    }

    public sealed class DiagnosticBag(SourceText source) : IEnumerable<Diagnostic>
    {
        readonly List<Diagnostic> _items = [];

        public int Count => _items.Count;
        public int ErrorCount { get; private set; }
        public bool HasErrors => ErrorCount > 0;
        public Diagnostic this[int index] => _items[index];

        public Diagnostic Report(Descriptor d, TextSpan span) => Add(Diagnostic.Create(d, span));
        public Diagnostic Report<T>(Descriptor<T> d, TextSpan span, T arg) => Add(Diagnostic.Create(d, span, arg));
        public Diagnostic Report<T1, T2>(Descriptor<T1, T2> d, TextSpan span, T1 a, T2 b) => Add(Diagnostic.Create(d, span, a, b));

        public Diagnostic Add(Diagnostic diagnostic)
        {
            diagnostic.Source = source;
            if (diagnostic.Severity == Severity.Error) ErrorCount++;
            _items.Add(diagnostic);
            return diagnostic;
        }

        public void Truncate(int count)                  // roll back to an earlier Count, for speculative parsing
        {
            for (int i = count; i < _items.Count; i++)
                if (_items[i].Severity == Severity.Error) ErrorCount--;
            _items.RemoveRange(count, _items.Count - count);
        }

        public IEnumerator<Diagnostic> GetEnumerator() => _items.GetEnumerator();
        IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
    }
    ```

Reporting is then one line at each place a stage finds a problem:

=== "C++"

    ```cpp
    // The parser: a missing ';' can be fixed by inserting one.
    Diagnostic& d = diagnostics_.Report<Diag::ExpectedToken>({ end, 0 }, Describe(kind), Describe(Current().kind));
    if (kind == SyntaxKind::SemicolonToken) d.WithFix({ end, 0 }, ";");

    // The binder: point at both definitions.
    diagnostics_.Report<Diag::DuplicateDefinition>(name.span, name.text)
        .WithRelated(existing->declaration.span, "first defined here");

    // diagnostics_.Report<Diag::TypeMismatch>(span, "i32");   // compile error: the format needs two arguments
    ```

=== "C#"

    ```csharp
    // The parser: a missing ';' can be fixed by inserting one.
    Diagnostic d = diagnostics.Report(Diagnostics.ExpectedToken, new TextSpan(end, 0), Describe(kind), Describe(Current.Kind));
    if (kind == SyntaxKind.SemicolonToken) d.WithFix(new TextSpan(end, 0), ";");

    // The binder: point at both definitions.
    diagnostics.Report(Diagnostics.DuplicateDefinition, name.Span, name.Text!)
        .WithRelated(existing.Declaration.Span, "first defined here");

    // diagnostics.Report(Diagnostics.TypeMismatch, span, "i32");   // compile error: no overload takes one argument
    ```

- **One bag per source file**, created by the driver and passed to each stage that reads that file. Stages never print; the driver merges the bags, sorts by file and position, and decides how to show them (a terminal, a test, a language server).
- **Stop between stages on errors.** Check `HasErrors()` after binding and type checking, before lowering and code generation.
- **Speculative parsing rolls back** with `Truncate(savedCount)`, as in [the parser](parser.md#more-tips): diagnostics from a parse that was undone never reach the user.
- **Report once, then stay quiet**: a function that meets a missing token or an error node returns without reporting. See [avoiding cascades](#avoiding-cascades).
- **Fixes only when they are certain**: insert a missing `;` or `)`, or rename to the one name within edit distance 1. A language server turns them into quick fixes, and a wrong fix applied by a click is worse than none.
- **Cap the output**: after about 100 errors, print "too many errors" and stop. Past that, almost all of them are cascades.

### Writing good messages

- Say **what is wrong** and, where it is clear, **what was expected**: "expected ')' after the arguments", not "syntax error".
- Name the things involved, in the language's own syntax: types as written (`Vec2`, `i32`), not internal names.
- Point at the **smallest span** that explains it: the argument of the wrong type, not the whole call.
- Add a **related location** for the other half: a duplicate definition points at the first one too.
- Do not guess at a fix unless it is almost always right. "Did you mean `length`?" for a misspelt name (by edit distance against names in scope) is worth it; a wrong suggestion is worse than none.

### Avoiding cascades

One mistake should give one error. The standard tools:

- An **error type**: an expression that failed to type-check gets a special type that is compatible with everything and reports nothing further. See [type checking](types.md#the-error-type).
- **Missing nodes**: the parser inserts a placeholder for an absent token and reports once. See [error recovery](parser.md#error-recovery).
- **One report per name**: an undefined name is reported at its first use in a function, not at every use.
- **Stop before code generation** if there are errors. Later stages assume a correct tree.

### Showing them

```text
main.lang:12:13: error E0201: expected 'i32', found 'f32'
   |
12 |     total = total + 0.5;
   |             ^^^^^^^^^^^
main.lang:2:5: error E0102: 'x' is already defined in this scope
  |
2 | let x = 2;
  |     ^
  |
1 | let x = 1;
  |     ^ first defined here
main.lang:7:14: error E0050: expected ';', found identifier
  |
7 |     let y = 5
  |              ^
  help: insert ';'
```

=== "C++"

    ```cpp
    std::string Render(const Diagnostic& d)
    {
        const SourceText& source = *d.source;
        auto [line, column] = source.Position(d.span.start);
        std::string out = std::format("{}:{}:{}: {} {}: {}\n", source.Path(), line, column,
                                      d.GetSeverity() == Severity::Error ? "error" : "warning", d.Info().code, d.message);
        auto underline = [&](TextSpan span, std::string_view label)
        {
            auto [l, c] = source.Position(span.start);
            std::string_view text = source.LineText(l - 1);           // the line, without its line break
            uint32_t lineEnd = span.start - (c - 1) + uint32_t(text.size());
            uint32_t end = std::min(span.End(), lineEnd);               // a multi-line span: underline the first line
            uint32_t width = std::max(1u, end > span.start ? end - span.start : 0u);
            std::string gutter(std::to_string(l).size(), ' ');
            out += std::format("{} |\n{} | {}\n{} | {}{}{}{}\n", gutter, l, text, gutter, std::string(c - 1, ' '),
                               std::string(width, '^'), label.empty() ? "" : " ", label);
        };
        underline(d.span, "");
        for (const RelatedLocation& r : d.related) underline(r.span, r.message);
        for (const Fix& f : d.fixes)
            out += f.span.length == 0 ? std::format("  help: insert '{}'\n", f.replacement)
                                  : std::format("  help: replace with '{}'\n", f.replacement);
        return out;
    }
    ```

=== "C#"

    ```csharp
    public static string Render(Diagnostic d)
    {
        SourceText source = d.Source!;
        var (line, column) = source.Position(d.Span.Start);
        var output = new StringBuilder();
        string severity = d.Severity == Severity.Error ? "error" : "warning";
        output.Append($"{source.Path}:{line}:{column}: {severity} {d.Descriptor.Code}: {d.Message}\n");
        Underline(output, source, d.Span, "");
        foreach (var related in d.Related) Underline(output, source, related.Span, related.Message);
        foreach (var fix in d.Fixes)
            output.Append(fix.Span.Length == 0 ? $"  help: insert '{fix.Replacement}'\n" : $"  help: replace with '{fix.Replacement}'\n");
        return output.ToString();
    }

    static void Underline(StringBuilder output, SourceText source, TextSpan span, string label)
    {
        var (line, column) = source.Position(span.Start);
        string text = source.LineText(line - 1);                    // the line, without its line break
        int lineEnd = span.Start - (column - 1) + text.Length;
        int width = Math.Max(1, Math.Min(span.End, lineEnd) - span.Start);   // a multi-line span: underline the first line
        string gutter = new(' ', line.ToString(CultureInfo.InvariantCulture).Length);
        output.Append($"{gutter} |\n{line} | {text}\n{gutter} | {new string(' ', column - 1)}{new string('^', width)}");
        output.Append(label.Length > 0 ? $" {label}\n" : "\n");
    }
    ```

Use the same `path:line:col` format as other compilers, so editors and CI turn it into clickable links. Sort diagnostics by position before printing.

## C++ tips

- The `.def` file is an **X-macro**: each `#include` defines `DIAGNOSTIC` to produce one part (enum values, the info table, a list for documentation). Adding a diagnostic is one line, and the parts cannot get out of step.
- `std::format` checks a format string against its arguments at compile time when the string is a constant. `Make<Id>` reads it from the `constexpr` table, so a missing or extra argument is a compile error. A format chosen at run time needs `std::vformat` and fails with an exception instead.
- The reference `Report` returns is into the bag's `std::vector`: add related locations and fixes straight away, before the next report moves the storage.
- Store `const SourceText*` in diagnostics, and keep every `SourceText` alive for the whole compilation, for example in a `std::deque` owned by the driver.

## C# tips

- `SourceText` holds a `string` and an `int[]` of line starts. `Array.BinarySearch` returns the bitwise complement of the insertion point when the offset is not a line start: `line = index >= 0 ? index : ~index - 1`.
- `readonly record struct TextSpan(int Start, int Length)` with `End`, `Contains`, and a static `FromBounds(start, end)` covers almost every use.
- `Diagnostic` is a class rather than a record: `WithRelated` and `WithFix` add to the one the bag holds, and two identical messages at different times are still different diagnostics.
- Tests match on the descriptor (`Assert.Equal(Diagnostics.TypeMismatch, d.Descriptor)`) or its `Code`, never on message text.
- With hundreds of diagnostics, a [source generator](../../csharp/roslyn/source-generators.md) can read the table from a CSV or JSON file (an `AdditionalFiles` item) and write the `Diagnostics` class, as Roslyn does from its resource file.
- `CompositeFormat` (.NET 8) parses each format once. `string.Format` with it and too few arguments throws, which the table test above catches for every diagnostic.
- Hand the finished diagnostics on as an `ImmutableArray<Diagnostic>` once a file has been checked, so nothing can add to them afterwards.
- Read files with `File.ReadAllText(path)`, which detects and removes the byte order mark. Normalise nothing else: offsets must match the file as the editor sees it.
