# Lexer

The lexer turns text into **tokens**: the words of the language. It decides where one token ends and the next begins, skips whitespace and comments, and records each token's span. The parser then never looks at characters.

## Tokens

```text
Token {
    kind            // Identifier, IntLiteral, FloatLiteral, StringLiteral, keyword or punctuation kind, EndOfFile, Bad
    span            // where it is in the source
    text            // the characters, for identifiers and literals
    value           // the parsed number or string, filled in by the lexer
    leading_trivia  // whitespace and comments before it (optional; see below)
}
```

- Give **each keyword and each operator its own kind** (`FnKeyword`, `LetKeyword`, `PlusToken`, `ArrowToken`). The parser then switches on kinds, never on text.
- End every token stream with an **EndOfFile** token whose span is empty and at the end of the text. The parser can then always look at the current token without checking for the end.
- A character that starts no token becomes a **Bad** token with a diagnostic. Lexing continues.

## The main loop

```text
lex(text):
    pos = 0
    tokens = []
    loop:
        skip_trivia()                         // whitespace and comments
        start = pos
        if pos == len(text):
            tokens.append(Token(EndOfFile, span(start, 0)))
            return tokens
        c = text[pos]
        kind =
            if is_letter(c) or c == '_':  identifier_or_keyword()
            elif is_digit(c):             number()
            elif c == '"':                string()
            else:                         punctuation()
        tokens.append(Token(kind, span(start, pos - start), ...))

identifier_or_keyword():
    while pos < len(text) and (is_letter_or_digit(text[pos]) or text[pos] == '_'): pos += 1
    word = text[start .. pos]
    return keywords.get(word, Identifier)     // "fn" -> FnKeyword, "let" -> LetKeyword, ...
```

Keywords are lexed as identifiers and then looked up in a table. A separate rule per keyword gets `format` wrong (it starts with `for`).

## Punctuation: longest match

Multi-character operators win over their prefixes: `->` is one token, not `-` then `>`; `<=` is one token; `==` is not two `=`.

```text
punctuation():
    c = text[pos]
    next = text[pos + 1] if pos + 1 < len(text) else '\0'
    pos += 1
    switch c:
        '+': return Plus
        '-': if next == '>': pos += 1; return Arrow
             return Minus
        '=': if next == '=': pos += 1; return EqualsEquals
             return Equals
        '<': if next == '=': pos += 1; return LessEquals
             return Less
        '&': if next == '&': pos += 1; return AmpersandAmpersand
             return Ampersand
        '(': return OpenParen
        // ... the rest of the operators and delimiters
        default:
            report(bad_character(span(pos - 1, 1), c))
            return Bad
```

One place where longest match is wrong: `>>` closing two generic argument lists, as in `List<List<i32>>`. Either lex `>` always as a single token and let the parser treat two adjacent `>` as a shift (checking that their spans touch), or have the parser split the token when it expects a `>`. Decide before adding generics.

## Numbers

```text
number():
    while is_digit_or_underscore(text[pos]): pos += 1
    is_float = false
    if text[pos] == '.' and is_digit(text[pos + 1]):    // "1." followed by a name is a member access, not a float
        is_float = true
        pos += 1
        while is_digit_or_underscore(text[pos]): pos += 1
    if text[pos] in "eE":
        is_float = true
        pos += 1
        if text[pos] in "+-": pos += 1
        require a digit, then while is_digit(text[pos]): pos += 1
    suffix = optional type suffix: "i32", "u8", "f32", ...
    digits = text[start .. end of number] without '_'
    value = parse digits as integer or float; on overflow report and use 0
    return is_float ? FloatLiteral : IntLiteral
```

- Support `0x`, `0b`, and `_` separators (`1_000_000`) from the start; they are cheap here and annoying to add later. In C#, [regular expressions](#regular-expressions-for-token-shapes) describe all the forms compactly.
- **Range-check later**, not in the lexer: whether `300` fits depends on the type it ends up with (`u8` or `i32`). The lexer stores the value in the widest type (a 64-bit unsigned integer, or a double) and the [type checker](types.md#literals) checks it.
- A leading `-` is **not** part of the literal: `x-1` must lex as `x`, `-`, `1`. Unary minus is an operator in the parser.

## Strings

```text
string():
    pos += 1                                     // opening quote
    builder = ""
    loop:
        if pos == len(text) or text[pos] == '\n':
            report(unterminated_string(span(start, pos - start)))
            break                                // the token ends here; lexing goes on
        c = text[pos]
        if c == '"': pos += 1; break
        if c == '\\':
            pos += 1
            switch text[pos]:
                'n': builder += '\n'
                't': builder += '\t'
                '\\', '"': builder += text[pos]
                'u': read "{hex}" and append that code point
                default: report(bad_escape(span(pos - 1, 2)))
            pos += 1
        else:
            builder += c
            pos += 1
    value = builder
    return StringLiteral
```

Stopping an unterminated string at the end of the line keeps one missing quote from swallowing the rest of the file.

## Trivia

**Trivia** is everything that is not a token: spaces, newlines, and comments.

```text
skip_trivia():
    loop:
        if is_whitespace(text[pos]): pos += 1
        elif text[pos] == '/' and text[pos + 1] == '/':
            while pos < len(text) and text[pos] != '\n': pos += 1
        elif text[pos] == '/' and text[pos + 1] == '*':
            depth = 1, pos += 2                   // nested block comments: /* a /* b */ c */
            while depth > 0 and pos < len(text):
                if starts_with("/*"): depth += 1; pos += 2
                elif starts_with("*/"): depth -= 1; pos += 2
                else: pos += 1
            if depth > 0: report(unterminated_comment)
        else: return
```

A compiler can throw trivia away. A **formatter**, a refactoring tool, or a language server needs it: attach the trivia to the following token (`leading_trivia`) and the text can be reproduced exactly. Keeping the spans is enough to start; the trivia text can be recovered from them.

**Doc comments** (`///`) are trivia that later stages read. Keep them as leading trivia and let the binder attach them to the declaration that follows.

## Lexing on demand

There are two ways to feed the parser:

| | All tokens first | One token at a time |
| --- | --- | --- |
| How | `lex()` returns an array; the parser indexes it | the parser calls `next_token()` |
| Look-ahead | free: `tokens[i + k]` | needs a small buffer |
| Context-sensitive lexing (string interpolation, `>>` in generics) | harder: the lexer runs before the parser knows the context | the parser can tell the lexer which mode to use |
| Memory | an array of tokens per file | no array |

An array is simpler and plenty fast for files of a few thousand lines. Change only if interpolated strings or other modes need the parser's help.

## More tips

**String interpolation.** `"hp: {hp + 1}!"` contains code inside a string. Give the lexer a **mode stack**: in string mode it reads text until `{`, then pushes code mode and counts braces; the `}` that brings the count back to zero pops back to string mode. Emit `InterpolatedStart`, `StringText`, the tokens of the expression, `StringText`, and `InterpolatedEnd`, and let the parser build the parts. A brace inside the embedded code (`{ f({x}) }`) must not end the interpolation early, which is why the count is needed.

**Multi-line and raw strings.** A `"""` string that spans lines usually strips the indentation of its closing delimiter from every line, as C# raw string literals and Swift do; that rule lets the string be indented with the code. Raw strings (no escapes) need a delimiter that cannot appear inside: let the number of quotes vary, as C# does.

**Contextual keywords.** Words that are keywords in one place only (`get` and `set` in a property, `where` after a generic signature) are lexed as **identifiers**, and the parser checks the text where the word is special. A new language version can then add one without breaking programs that use it as a name.

**Unicode identifiers.** If identifiers may be Unicode, follow [UAX #31](https://unicode.org/reports/tr31/): a start character from `XID_Start` (or `_`), then `XID_Continue`. Normalise to NFC before comparing names, or two identical-looking names (`é` precomposed and decomposed) will be different symbols.

**Newlines as separators.** For optional semicolons, Go's rule is simple and predictable: after a line whose last token is an identifier, a literal, `)`, `]`, `}`, or `return`, the lexer inserts a semicolon at the newline. The parser then sees a normal semicolon-terminated grammar.

**Interning.** Store each distinct identifier text once, in a table owned by the compilation, and give tokens the shared `string`. Names then compare by reference in the binder, and a file with ten thousand uses of `i` holds one `"i"`.

**Always make progress.** Every path through the main loop must consume at least one character, including the `Bad` token path. Assert it in debug builds; a lexer that returns a zero-length token for some character loops forever.

**Small things that surprise.** A `#!` line at the very start of a file (so scripts can be run directly) is trivia. A file may end without a newline, inside a comment, or inside a string. Tabs count as one column in spans, even if editors display them wider.

## Regular expressions for token shapes

The main loop stays hand-written, but the **shape** of a single token can be a regular expression: an identifier, or a number with its hex, binary, and octal forms, digit separators, exponents, and suffixes. The lexer loop decides which kind of token starts at the current character; the regex says how long it is and whether it is valid.

| Use a regex for | Keep hand-written |
| --- | --- |
| identifiers, number literals, a fixed set of suffixes | the main loop and the choice of token kind |
| validating a literal once its extent is known | operators (a `switch` is clearer and handles longest match) |
| | strings (escape decoding, interpolation modes, unterminated-string recovery) |
| | comments (nested block comments cannot be matched by a simple regex) |

### Matching at a position

`\G` anchors a match to exactly where the search starts, so `regex.Match(text, position)` only succeeds if the token starts at `position`. `[GeneratedRegex]` (.NET 7 and later) turns the pattern into C# at build time, with no start-up cost.

```csharp
public static partial class TokenShapes
{
    // ASCII identifiers. For Unicode ones (see "Unicode identifiers" above): \G[\p{L}_][\p{L}\p{Mn}\p{Nd}_]*
    [GeneratedRegex(@"\G[A-Za-z_][A-Za-z0-9_]*")]
    private static partial Regex Identifier();

    public static int IdentifierLength(string text, int position)
    {
        foreach (ValueMatch m in Identifier().EnumerateMatches(text, position))   // no allocation
            return m.Length;
        return 0;
    }
}
```

`EnumerateMatches` returns a `ValueMatch` (an index and a length) without allocating, which is all the identifier case needs. Groups need `Match`, which allocates; use it only where the groups are read.

### Numbers: scan, then validate

A strict number pattern on its own has a trap: it matches the **valid prefix** and stops. `0b102` would lex as `0b10` followed by a separate `2`, and `1_` as `1` followed by the identifier `_`, with no error. Lex numbers in two steps instead:

1. **Scan** loosely: everything a number could plausibly contain, so a malformed literal becomes one token.
2. **Validate** that token against the strict pattern, and report a diagnostic if it is not a complete match.

```csharp
// Step 1: how far does the literal go? A `.` only counts when a digit follows, so `1..2`
// and `x.1.foo()` still split; a sign only counts after an exponent, and not in hex.
[GeneratedRegex("""
    \G(?:
        0[xX][0-9A-Za-z_]*
      | [0-9](?:[eE][+-]|[0-9A-Za-z_]|\.(?=[0-9]))*
    )
    """, RegexOptions.IgnorePatternWhitespace)]
private static partial Regex NumberExtent();

// Step 2: the valid forms. `_?` between digits allows 1_000 but not 1_, 1__0, or 0x_FF.
[GeneratedRegex("""
    ^(?:
        0[xX](?<hex>[0-9a-fA-F](?:_?[0-9a-fA-F])*)
      | 0[bB](?<bin>[01](?:_?[01])*)
      | 0[oO](?<oct>[0-7](?:_?[0-7])*)
      | (?<int>[0-9](?:_?[0-9])*)
        (?<frac>\.[0-9](?:_?[0-9])*)?
        (?<exp>[eE][+-]?[0-9](?:_?[0-9])*)?
    )
    (?<suffix>[iu](?:8|16|32|64)|f(?:32|64))?$
    """, RegexOptions.IgnorePatternWhitespace)]
private static partial Regex NumberLiteral();
```

```csharp
SyntaxKind LexNumber()
{
    int length = 0;
    foreach (ValueMatch m in NumberExtent().EnumerateMatches(_text, _position)) { length = m.Length; break; }
    string token = _text.Substring(_position, length);
    var span = new TextSpan(_position, length);
    _position += length;

    Match match = NumberLiteral().Match(token);
    if (!match.Success)
    {
        _diagnostics.InvalidNumber(span, token);          // "invalid number literal '0b102'"
        _value = 0UL;
        return SyntaxKind.IntLiteral;                      // still a number token: the parser carries on
    }

    string Digits(string group) => match.Groups[group].Value.Replace("_", "");
    string suffix = match.Groups["suffix"].Value;
    _suffix = suffix;                                     // the type checker uses it

    if (match.Groups["hex"].Success) return Integer(Digits("hex"), NumberStyles.AllowHexSpecifier, span);
    if (match.Groups["bin"].Success) return Integer(Digits("bin"), NumberStyles.AllowBinarySpecifier, span);
    if (match.Groups["oct"].Success) return Octal(Digits("oct"), span);

    string text = Digits("int") + Digits("frac") + Digits("exp");
    if (match.Groups["frac"].Success || match.Groups["exp"].Success || suffix.StartsWith('f'))
    {
        _value = double.Parse(text, NumberStyles.Float, CultureInfo.InvariantCulture);
        return SyntaxKind.FloatLiteral;
    }
    return Integer(text, NumberStyles.None, span);
}

SyntaxKind Integer(string digits, NumberStyles style, TextSpan span)
{
    if (!ulong.TryParse(digits, style, CultureInfo.InvariantCulture, out ulong value))
        _diagnostics.NumberTooLarge(span);                 // more than 64 bits
    _value = value;
    return SyntaxKind.IntLiteral;
}

SyntaxKind Octal(string digits, TextSpan span)
{
    try { _value = Convert.ToUInt64(digits, 8); }
    catch (OverflowException) { _diagnostics.NumberTooLarge(span); _value = 0UL; }
    return SyntaxKind.IntLiteral;
}
```

What it gives for some inputs:

| Input | Token | Result |
| --- | --- | --- |
| `0xdead_beef` | `0xdead_beef` | integer 3735928559 |
| `0b1_0` | `0b1_0` | integer 2 |
| `2.5e-3` | `2.5e-3` | float 0.0025 |
| `1.5f32` | `1.5f32` | float 1.5, suffix `f32` |
| `0b102` | `0b102` | error: invalid number literal |
| `1_`, `1__0`, `0x_FF`, `12abc` | the whole text | error |
| `1..2` | `1` | integer; `..` and `2` are the next tokens |
| `0xE-1` | `0xE` | integer 14; `-` and `1` follow |
| `1.foo` | `1` | integer; `.` and `foo` follow |

- `NumberStyles.AllowBinarySpecifier` is .NET 8 and later; on older runtimes use `Convert.ToUInt64(digits, 2)`, as `Octal` does for base 8. There is no `NumberStyles` for octal.
- For more specific messages ("expected hex digits after '0x'", "'2' is not a binary digit"), check the prefix of a failed token and find the first character that is not valid for that base. The regex says **whether** the literal is valid; a few lines of code say **why** not.
- Range checking against the literal's type (`300u8`) still belongs to the [type checker](types.md#literals).

## C# tips

- Lex over a `string` with an `int` position, and keep `Peek(offset)` returning `'\0'` past the end, so no condition needs a length check.
- `char.IsLetter` and `char.IsDigit` accept every Unicode letter and digit, including Arabic-Indic digits. Decide whether identifiers may be Unicode; for digits use `char.IsAsciiDigit`.
- Build the keyword table once: `FrozenDictionary<string, SyntaxKind>`, or a `switch` expression on the text, which the C# compiler turns into a hash or length-based jump table. Look it up with the span (`.GetAlternateLookup<ReadOnlySpan<char>>()` on .NET 9 and later) to avoid allocating a string for every identifier.
- `SearchValues.Create("+-*/%=<>!&|^~")` with `span.IndexOfAnyExcept` skips runs of a character class quickly, such as whitespace or digits.
- Make `Token` a `readonly record struct`: `SyntaxKind Kind`, `TextSpan Span`, and `object? Value`. Store `Text` only for identifiers and literals.
- Parse numbers with `long.TryParse` / `ulong.TryParse` and `double.TryParse(..., NumberStyles.Float, CultureInfo.InvariantCulture)`. Without the invariant culture, `1.5` fails to parse on machines whose decimal separator is a comma.
