# Source text and diagnostics

Every later stage points back at the source: a token knows where it starts, a type error underlines an expression, and debug info maps machine code to lines. Getting this right first makes every error message cheap to write.

## Source text and spans

Positions are stored as **offsets** into the text, not as lines and columns. An offset is one integer, cheap to compare and add, and stays valid however lines are counted. Lines and columns are worked out only when a message is shown.

```text
SourceText {
    path
    text                    // the whole file, decoded once
    line_starts             // offset of the first character of each line
}

TextSpan { start, length }  // end = start + length; covers [start, end)
```

```text
build_line_starts(text):
    starts = [0]
    for i in 0 .. len(text):
        if text[i] == '\r' and i + 1 < len(text) and text[i + 1] == '\n': continue   // CRLF: break after the \n
        if text[i] == '\n' or text[i] == '\r': starts.append(i + 1)
    return starts

line_of(offset):            // 0-based; binary search for the last start <= offset
    return upper_bound(line_starts, offset) - 1

position(offset):
    line = line_of(offset)
    return (line + 1, offset - line_starts[line] + 1)      // 1-based for people
```

- A span of **length 0** marks a point: a missing semicolon is reported at the end of the previous token.
- Merge spans to cover a whole construct: `span(first.start, last.end - first.start)` for a binary expression or a function.
- Columns are in characters (UTF-16 code units in C#). Editors that count bytes or grapheme clusters will be off on lines with non-ASCII text; the language server protocol states which unit it expects.
- Strip a UTF-8 byte order mark when decoding, or offset 0 is invisible.

## Diagnostics

A **diagnostic** is a message with a severity, a span, and a code:

```text
Diagnostic {
    severity        // Error, Warning, Info
    code            // "E0012": stable, searchable, and what tests match on
    message         // "cannot assign 'f32' to a variable of type 'i32'"
    location        // SourceText and TextSpan
    related         // optional extra spans: "'x' is declared here"
}
```

Each stage adds to a **diagnostic bag** rather than throwing. Exceptions are for bugs in the compiler, not for bugs in the user's code.

Put every message in one place, so wording stays consistent and codes are not reused:

```text
Diagnostics.undefined_name(span, name):
    report(Error, "E0101", span, "the name '{name}' does not exist in this scope")

Diagnostics.type_mismatch(span, expected, found):
    report(Error, "E0201", span, "expected '{expected}', found '{found}'")
```

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
```

```text
render(d):
    (line, col) = d.text.position(d.span.start)
    print "{path}:{line}:{col}: {severity} {code}: {message}"
    line_text = text of that line, without the line break
    print gutter, line number, line_text
    end = min(d.span.end, end of that line)
    print spaces up to col, then "^" repeated max(1, end - span.start)
```

Use the same `path:line:col` format as other compilers, so editors and CI turn it into clickable links. Sort diagnostics by position before printing.

## C# tips

- `SourceText` holds a `string` and an `int[]` of line starts. `Array.BinarySearch` returns the bitwise complement of the insertion point when the offset is not a line start: `line = index >= 0 ? index : ~index - 1`.
- `readonly record struct TextSpan(int Start, int Length)` with `End`, `Contains`, and a static `FromBounds(start, end)` covers almost every use.
- Make `Diagnostic` a `sealed record`, and `DiagnosticBag` a small class wrapping a `List<Diagnostic>` with one method per message. Return `ImmutableArray<Diagnostic>` from each stage.
- Keep codes as `const string` fields in one static class, so tests can match `Codes.TypeMismatch` instead of message text.
- Read files with `File.ReadAllText(path)`, which detects and removes the byte order mark. Normalise nothing else: offsets must match the file as the editor sees it.
