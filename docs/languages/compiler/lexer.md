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

### The forms

| Form | Examples | Notes |
| --- | --- | --- |
| Decimal integer | `0`, `42`, `1_000_000` | no leading zeros: `007` is an error (see [octal](#octal)) |
| Hexadecimal | `0xFF`, `0xdead_beef` | digits in either case; prefer a lowercase `0x` |
| Binary | `0b1010`, `0b1111_0000` | bit masks and flags |
| Float | `3.14`, `1e10`, `2.5e-3`, `1E+3` | decimal only; digits are needed on **both** sides of the `.` |
| Type suffix | `7u8`, `255i32`, `0xFFu8`, `1.5f32`, `1f32` | an integer with a float suffix is a float |

- **Digit separators** (`_`) are allowed only **between** digits: not `1_`, `1__0`, or `0x_FF`. That makes every literal read one way.
- **No `.5` and no `1.`**. A leading dot clashes with member access, and a trailing one with method calls on literals (`1.max(2)`) and ranges (`1..2`). Requiring a digit after the `.` keeps those working: `1..2` lexes as `1`, `..`, `2`.
- **No hex floats** (`0x1.8p3`). They are useful for exact float constants in maths libraries, and nowhere else.
- **No float suffix on hex**: `0x1f32` is the hex number 7986, because `f`, `3`, and `2` are hex digits. Integer suffixes are fine, since `i` and `u` are not.
- A leading `-` is **not** part of the literal: `x-1` must lex as `x`, `-`, `1`. Unary minus is an operator in the parser.

### Scanning

One function lexes every form. It always consumes the whole literal, valid or not, so a mistake gives **one token and one error**, never a valid prefix followed by junk (`0b102` as `0b10` and `2`).

```text
number():
    start = pos
    base = 10
    if text[pos] == '0' and text[pos + 1] in "xX": base = 16; pos += 2
    elif text[pos] == '0' and text[pos + 1] in "bB": base = 2; pos += 2

    (value, count, overflow) = digits(base, buffer)          // the integer part
    if count == 0:            report(expected digits after the prefix)       // "0x", "0xG"
    if base == 10 and count > 1 and buffer[0] == '0': report(leading zeros are not allowed)

    is_float = false
    if base == 10 and text[pos] == '.' and is_digit(text[pos + 1]):
        is_float = true; buffer += '.'; pos += 1
        digits(10, buffer)
    if base == 10 and text[pos] in "eE":
        is_float = true; buffer += 'e'; pos += 1
        if text[pos] in "+-": buffer += text[pos]; pos += 1
        if digits(10, buffer).count == 0: report(expected digits in the exponent)   // "1e", "1e+"

    suffix = the run of letters, digits, and '_' that follows
    if suffix starts with a digit:   report(invalid digit '{suffix[0]}' for base {base})     // "0b102"
    elif suffix not in known:        report(unknown suffix '{suffix}')                       // "12abc", "3u7"
    elif is_float and suffix is an integer suffix: report(a float cannot have suffix '{suffix}')
    elif base != 10 and suffix is a float suffix:  report(hex and binary literals cannot be floats)

    if is_float or suffix is a float suffix:
        value = parse_float(buffer, as f32 if suffix == "f32" else f64)
        return FloatLiteral
    if overflow: report(integer literal is too large)
    return IntLiteral

digits(base, buffer):                    // reads digits and separators of one base
    value = 0, count = 0, overflow = false
    loop:
        c = text[pos]
        if c == '_':
            if count == 0 or not is_digit_in_base(text[pos + 1], base):
                report('_' must be between digits)
            pos += 1
            continue
        d = digit_value(c)               // '0'-'9', 'a'-'f', 'A'-'F'; otherwise none
        if d is none or d >= base: break
        if value > (MAX_U64 - d) / base: overflow = true
        else: value = value * base + d
        buffer += c, count += 1, pos += 1
    return (value, count, overflow)
```

- Report **one** error per literal (keep the first), and still return a number token, with value 0, so the parser carries on without a cascade.
- The integer value is built **digit by digit** with an overflow check, which works for every base and needs no parsing library.
- A float is **not** built digit by digit: repeated multiplication accumulates rounding errors. Collect its digits (without separators) and hand them to a correctly rounded parser. An `f32` literal is parsed directly as `f32`; parsing as `f64` and then rounding to `f32` can be off by one in the last bit.
- **Range-check later**, not in the lexer: whether `300` fits depends on the type it ends up with (`u8` or `i32`). The lexer stores the value in the widest type (a 64-bit unsigned integer, or a double), and the [type checker](types.md#literals) checks it against the suffix or the context.

| Input | Token | Result |
| --- | --- | --- |
| `0xdead_beef`, `0b1_0` | the whole text | integers 3735928559 and 2 |
| `2.5e-3`, `1.5f32`, `1f32` | the whole text | floats; `1f32` is a float because of its suffix |
| `0xFFu8` | `0xFFu8` | integer 255, suffix `u8` |
| `0x1f32` | `0x1f32` | integer 7986: the `f32` is hex digits |
| `18446744073709551616` | the whole text | error: integer literal is too large |
| `1_`, `1__0`, `0x_FF` | the whole text | error: `_` must be between digits |
| `0x`, `0xG` | the whole text | error: expected digits after `0x` |
| `0b102` | `0b102` | error: invalid digit `2` for base 2 |
| `12abc`, `3u7` | the whole text | error: unknown suffix |
| `1e`, `1e+` | the whole text | error: expected digits in the exponent |
| `007` | `007` | error: leading zeros are not allowed |
| `1.`, `1..2`, `1.foo` | `1` | integer; the `.` starts the next token |
| `0xE-1` | `0xE` | integer 14; `-` and `1` follow |

### Octal

**Usually not worth it.** Octal's main use today is Unix file permissions (`0o755`), which game code rarely writes. It costs little to add, but every form you add is one more thing to document and test.

What **is** worth it is deciding what a leading zero means:

- C, C++, and JavaScript's old rule makes `010` octal, so `010 == 8`. People pad numbers with zeros to line up columns of data, and get wrong values without any error. Never copy this.
- Treating `010` as decimal 10 (as Rust does) is safe, but means `010` silently changes meaning for anyone who expects C's rule.
- **Rejecting** leading zeros (as Python 3 does, with "leading zeros are not allowed") is the clearest: the code above does this. `0` itself is fine.

If you do add octal later, use an explicit `0o` prefix (`0o755`), like Rust, Python, Swift, and JavaScript: it is one more branch next to `0x` and `0b`, with base 8.

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

## C# tips

- Lex over a `string` with an `int` position, and keep `Peek(offset)` returning `'\0'` past the end, so no condition needs a length check.
- `char.IsLetter` and `char.IsDigit` accept every Unicode letter and digit, including Arabic-Indic digits. Decide whether identifiers may be Unicode; for digits use `char.IsAsciiDigit`.
- Build the keyword table once: `FrozenDictionary<string, SyntaxKind>`, or a `switch` expression on the text, which the C# compiler turns into a hash or length-based jump table. Look it up with the span (`.GetAlternateLookup<ReadOnlySpan<char>>()` on .NET 9 and later) to avoid allocating a string for every identifier.
- `SearchValues.Create("+-*/%=<>!&|^~")` with `span.IndexOfAnyExcept` skips runs of a character class quickly, such as whitespace or digits.
- Make `Token` a `readonly record struct`: `SyntaxKind Kind`, `TextSpan Span`, and `object? Value`. Store `Text` only for identifiers and literals.
- Build integer values with the digit loop above (`ulong`, with the `(ulong.MaxValue - d) / base` overflow check), rather than `ulong.Parse`, so decimal, hex, and binary share one path and separators need no stripping.
- Parse floats from the collected digits with `double.Parse(text, NumberStyles.Float, CultureInfo.InvariantCulture)`, or `float.Parse` for an `f32` literal: `(float)double.Parse(text)` rounds twice, and for some inputs lands one bit away from the correctly rounded `float`. Without the invariant culture, `1.5` fails to parse on machines whose decimal separator is a comma.
- Collect the digits into a `StringBuilder` or a pooled `char` buffer only for floats; integers need no buffer at all.
- `char.IsAsciiDigit` and `char.IsAsciiHexDigit` (.NET 7) are the digit tests: unlike `char.IsDigit`, they reject non-ASCII digits.
