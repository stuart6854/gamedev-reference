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

- Support `0x`, `0b`, and `_` separators (`1_000_000`) from the start; they are cheap here and annoying to add later.
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

## C# tips

- Lex over a `string` with an `int` position, and keep `Peek(offset)` returning `'\0'` past the end, so no condition needs a length check.
- `char.IsLetter` and `char.IsDigit` accept every Unicode letter and digit, including Arabic-Indic digits. Decide whether identifiers may be Unicode; for digits use `char.IsAsciiDigit`.
- Build the keyword table once: `FrozenDictionary<string, SyntaxKind>`, or a `switch` expression on the text, which the C# compiler turns into a hash or length-based jump table. Look it up with the span (`.GetAlternateLookup<ReadOnlySpan<char>>()` on .NET 9 and later) to avoid allocating a string for every identifier.
- `SearchValues.Create("+-*/%=<>!&|^~")` with `span.IndexOfAnyExcept` skips runs of a character class quickly, such as whitespace or digits.
- Make `Token` a `readonly record struct`: `SyntaxKind Kind`, `TextSpan Span`, and `object? Value`. Store `Text` only for identifiers and literals.
- Parse numbers with `long.TryParse` / `ulong.TryParse` and `double.TryParse(..., NumberStyles.Float, CultureInfo.InvariantCulture)`. Without the invariant culture, `1.5` fails to parse on machines whose decimal separator is a comma.
