# Lexer

The lexer turns text into **tokens**: the words of the language. It decides where one token ends and the next begins, skips whitespace and comments, and records each token's span. The parser then never looks at characters.

## Tokens

=== "C++"

    ```cpp
    enum class SyntaxKind : uint8_t
    {
        IdentifierToken, IntLiteralToken, FloatLiteralToken, StringLiteralToken,
        FnKeyword, LetKeyword, /* ...one per keyword */
        PlusToken, MinusToken, ArrowToken, /* ...one per operator and delimiter */
        EndOfFileToken, BadToken,
    };

    struct TextSpan { uint32_t start = 0, length = 0; uint32_t End() const { return start + length; } };

    struct Token
    {
        SyntaxKind kind;
        TextSpan span;                                   // where it is in the source
        std::string_view text = {};                      // the characters: a view into the source text
        std::variant<std::monostate, uint64_t, double, std::string> value = {};   // the parsed number or string
        bool isMissing = false;                          // inserted by the parser's error recovery
        // leading trivia: whitespace and comments before it (optional; see below)
    };
    ```

=== "C#"

    ```csharp
    public enum SyntaxKind : byte
    {
        IdentifierToken, IntLiteralToken, FloatLiteralToken, StringLiteralToken,
        FnKeyword, LetKeyword, /* ...one per keyword */
        PlusToken, MinusToken, ArrowToken, /* ...one per operator and delimiter */
        EndOfFileToken, BadToken,
    }

    public readonly record struct Token(
        SyntaxKind Kind,
        TextSpan Span,              // where it is in the source
        string? Text = null,        // the characters, for identifiers and literals
        object? Value = null,       // the parsed number (ulong or double) or string
        bool IsMissing = false);    // inserted by the parser's error recovery
        // leading trivia: whitespace and comments before it (optional; see below)
    ```

- Give **each keyword and each operator its own kind** (`FnKeyword`, `LetKeyword`, `PlusToken`, `ArrowToken`). The parser then switches on kinds, never on text.
- End every token stream with an **`EndOfFileToken`** whose span is empty and at the end of the text. The parser can then always look at the current token without checking for the end.
- A character that starts no token becomes a **`BadToken`** with a diagnostic. Lexing continues.

## The main loop

=== "C++"

    ```cpp
    class Lexer
    {
    public:
        Lexer(const SourceText& source, DiagnosticBag& diagnostics) : text_(source.Text()), diagnostics_(diagnostics) {}
        std::vector<Token> Lex();

    private:
        char Peek(size_t offset = 0) const { return pos_ + offset < text_.size() ? text_[pos_ + offset] : '\0'; }
        TextSpan Span() const { return { uint32_t(start_), uint32_t(pos_ - start_) }; }    // the current token

        std::string_view text_;
        DiagnosticBag& diagnostics_;                     // see source text and diagnostics
        size_t pos_ = 0, start_ = 0;
        decltype(Token::value) value_;                   // set by Number() and String()
        // SkipTrivia, IdentifierOrKeyword, Number, String, and Punctuation are below
    };

    std::vector<Token> Lexer::Lex()
    {
        std::vector<Token> tokens;
        for (;;)
        {
            SkipTrivia();                                // whitespace and comments
            start_ = pos_;
            value_ = {};
            if (pos_ == text_.size())
            {
                tokens.push_back({ SyntaxKind::EndOfFileToken, Span() });
                return tokens;
            }
            char c = Peek();
            SyntaxKind kind = IsIdentifierStart(c) ? IdentifierOrKeyword()   // ASCII letter or '_'
                            : IsDigit(c)           ? Number()
                            : c == '"'             ? String()
                                                   : Punctuation();
            tokens.push_back({ kind, Span(), text_.substr(start_, pos_ - start_), std::move(value_) });
        }
    }

    SyntaxKind Lexer::IdentifierOrKeyword()
    {
        while (IsIdentifierPart(Peek())) pos_++;
        static const std::unordered_map<std::string_view, SyntaxKind> keywords = {
            { "fn", SyntaxKind::FnKeyword }, { "let", SyntaxKind::LetKeyword }, // ...
        };
        auto it = keywords.find(text_.substr(start_, pos_ - start_));
        return it != keywords.end() ? it->second : SyntaxKind::IdentifierToken;
    }
    ```

=== "C#"

    ```csharp
    public sealed class Lexer(SourceText source, DiagnosticBag diagnostics)   // see source text and diagnostics
    {
        readonly string text = source.Text;
        int _pos, _start;
        object? _value;                                  // set by Number() and String()

        char Peek(int offset = 0) => _pos + offset < text.Length ? text[_pos + offset] : '\0';
        TextSpan Span => TextSpan.FromBounds(_start, _pos);   // the current token

        public List<Token> Lex()
        {
            var tokens = new List<Token>();
            while (true)
            {
                SkipTrivia();                            // whitespace and comments
                _start = _pos;
                _value = null;
                if (_pos == text.Length)
                {
                    tokens.Add(new Token(SyntaxKind.EndOfFileToken, Span));
                    return tokens;
                }
                char c = Peek();
                SyntaxKind kind = IsIdentifierStart(c) ? IdentifierOrKeyword()   // ASCII letter or '_'
                                : char.IsAsciiDigit(c) ? Number()
                                : c == '"'             ? String()
                                :                        Punctuation();
                string? tokenText = kind <= SyntaxKind.StringLiteralToken ? text[_start.._pos] : null;   // identifiers and literals
                tokens.Add(new Token(kind, Span, tokenText, _value));
            }
        }

        SyntaxKind IdentifierOrKeyword()
        {
            while (IsIdentifierPart(Peek())) _pos++;
            return text[_start.._pos] switch
            {
                "fn" => SyntaxKind.FnKeyword,
                "let" => SyntaxKind.LetKeyword,
                // ...
                _ => SyntaxKind.IdentifierToken,
            };
        }

        // SkipTrivia, Number, String, and Punctuation are below
    }
    ```

Keywords are lexed as identifiers and then looked up in a table. A separate rule per keyword gets `format` wrong (it starts with `for`). `Peek` returns `'\0'` past the end, so no check needs a length test; the loops that could run off the end compare `pos` with the length directly.

## Punctuation: longest match

Multi-character operators win over their prefixes: `->` is one token, not `-` then `>`; `<=` is one token; `==` is not two `=`.

=== "C++"

    ```cpp
    SyntaxKind Lexer::Punctuation()
    {
        char c = Peek(), next = Peek(1);
        pos_++;
        auto pair = [&](char second, SyntaxKind two, SyntaxKind one)   // `two` if the next character is `second`
        {
            if (next != second) return one;
            pos_++;
            return two;
        };
        switch (c)
        {
        case '+': return SyntaxKind::PlusToken;
        case '-': return pair('>', SyntaxKind::ArrowToken, SyntaxKind::MinusToken);
        case '=': return pair('=', SyntaxKind::EqualsEqualsToken, SyntaxKind::EqualsToken);
        case '<': return pair('=', SyntaxKind::LessEqualsToken, SyntaxKind::LessToken);
        case '&': return pair('&', SyntaxKind::AmpersandAmpersandToken, SyntaxKind::AmpersandToken);
        case '|': if (next == '|') { pos_++; return SyntaxKind::PipePipeToken; } break;   // a single '|' is not a token
        case '(': return SyntaxKind::OpenParenToken;
        // ... the rest of the operators and delimiters
        }
        diagnostics_.Report<Diag::UnexpectedCharacter>(Span(), c);
        return SyntaxKind::BadToken;
    }
    ```

=== "C#"

    ```csharp
    SyntaxKind Punctuation()
    {
        char c = Peek(), next = Peek(1);
        _pos++;
        SyntaxKind Pair(char second, SyntaxKind two, SyntaxKind one)   // `two` if the next character is `second`
        {
            if (next != second) return one;
            _pos++;
            return two;
        }
        switch (c)
        {
            case '+': return SyntaxKind.PlusToken;
            case '-': return Pair('>', SyntaxKind.ArrowToken, SyntaxKind.MinusToken);
            case '=': return Pair('=', SyntaxKind.EqualsEqualsToken, SyntaxKind.EqualsToken);
            case '<': return Pair('=', SyntaxKind.LessEqualsToken, SyntaxKind.LessToken);
            case '&': return Pair('&', SyntaxKind.AmpersandAmpersandToken, SyntaxKind.AmpersandToken);
            case '|' when next == '|': _pos++; return SyntaxKind.PipePipeToken;   // a single '|' is not a token
            case '(': return SyntaxKind.OpenParenToken;
            // ... the rest of the operators and delimiters
        }
        diagnostics.Report(Diagnostics.UnexpectedCharacter, Span, c);
        return SyntaxKind.BadToken;
    }
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

=== "C++"

    ```cpp
    // Lexer members used here: std::optional<Diagnostic> literalError_ (the first error in the current number), and
    struct Digits { uint64_t value = 0; int count = 0; bool overflow = false; };

    template <Diag Id, class... Args> void Lexer::LiteralError(Args&&... args)   // keep the first; its span is set at the end
    {
        if (!literalError_) literalError_ = Diagnostic::Make<Id>({}, std::forward<Args>(args)...);
    }

    SyntaxKind Lexer::Number()
    {
        int base = 10;
        if (Peek() == '0' && (Peek(1) == 'x' || Peek(1) == 'X')) { base = 16; pos_ += 2; }
        else if (Peek() == '0' && (Peek(1) == 'b' || Peek(1) == 'B')) { base = 2; pos_ += 2; }

        literalError_.reset();
        std::string buffer;                              // the digits without separators, for floats
        Digits digits = ReadDigits(base, buffer);        // the integer part
        if (digits.count == 0) LiteralError<Diag::ExpectedDigits>(text_.substr(start_, pos_ - start_));   // "0x", "0xG"
        else if (base == 10 && digits.count > 1 && buffer[0] == '0') LiteralError<Diag::LeadingZeros>();

        bool isFloat = false;
        if (base == 10 && Peek() == '.' && IsDigit(Peek(1)))
        {
            isFloat = true;
            buffer += text_[pos_++];
            ReadDigits(10, buffer);
        }
        if (base == 10 && (Peek() == 'e' || Peek() == 'E'))
        {
            isFloat = true;
            buffer += text_[pos_++];
            if (Peek() == '+' || Peek() == '-') buffer += text_[pos_++];
            if (ReadDigits(10, buffer).count == 0) LiteralError<Diag::ExpectedExponentDigits>();  // "1e", "1e+"
        }

        size_t suffixStart = pos_;
        while (IsIdentifierPart(Peek())) pos_++;
        std::string_view suffix = text_.substr(suffixStart, pos_ - suffixStart);
        bool floatSuffix = suffix == "f32" || suffix == "f64";
        if (suffix.empty()) {}
        else if (IsDigit(suffix[0])) LiteralError<Diag::InvalidDigit>(suffix[0], base);    // "0b102"
        else if (!floatSuffix && !IsIntegerSuffix(suffix)) LiteralError<Diag::UnknownSuffix>(suffix);      // "12abc"
        else if (isFloat && !floatSuffix) LiteralError<Diag::FloatIntegerSuffix>(suffix);
        else if (base != 10 && floatSuffix) LiteralError<Diag::NonDecimalFloat>();

        isFloat = isFloat || floatSuffix;
        if (!isFloat && digits.overflow) LiteralError<Diag::IntegerTooLarge>();
        value_ = isFloat ? decltype(value_)(0.0) : decltype(value_)(uint64_t(0));   // the value after an error
        if (isFloat && !literalError_)
        {
            const char* first = buffer.data();
            const char* last = first + buffer.size();
            double d = 0;
            float f = 0;
            auto result = suffix == "f32" ? std::from_chars(first, last, f)          // rounded once, to float
                                          : std::from_chars(first, last, d);
            if (result.ec == std::errc::result_out_of_range) LiteralError<Diag::FloatOutOfRange>();
            else value_ = suffix == "f32" ? double(f) : d;
        }
        else if (!literalError_)
            value_ = digits.value;
        if (literalError_)                           // one error, over the whole literal
        {
            literalError_->span = Span();
            diagnostics_.Add(std::move(*literalError_));
        }
        return isFloat ? SyntaxKind::FloatLiteralToken : SyntaxKind::IntLiteralToken;
    }

    Lexer::Digits Lexer::ReadDigits(int base, std::string& buffer)   // digits and separators of one base
    {
        Digits d;
        for (;;)
        {
            char c = Peek();
            if (c == '_')
            {
                if (d.count == 0 || DigitValue(Peek(1)) >= base) LiteralError<Diag::MisplacedSeparator>();
                pos_++;
                continue;
            }
            int digit = DigitValue(c);                   // 0 to 15 for '0'-'9', 'a'-'f', 'A'-'F'; 99 for anything else
            if (digit >= base) break;
            if (d.value > (UINT64_MAX - digit) / base) d.overflow = true;
            else d.value = d.value * base + digit;
            buffer += c;
            d.count++;
            pos_++;
        }
        return d;
    }
    ```

=== "C#"

    ```csharp
    Diagnostic? _literalError;                           // the first error in the current number
    void LiteralError(Diagnostic diagnostic) => _literalError ??= diagnostic;   // keep the first; its span is set at the end

    SyntaxKind Number()
    {
        int numberBase = 10;
        if (Peek() == '0' && Peek(1) is 'x' or 'X') { numberBase = 16; _pos += 2; }
        else if (Peek() == '0' && Peek(1) is 'b' or 'B') { numberBase = 2; _pos += 2; }

        _literalError = null;
        var buffer = new StringBuilder();                // the digits without separators, for floats
        var (value, count, overflow) = ReadDigits(numberBase, buffer);   // the integer part
        if (count == 0) LiteralError(Diagnostic.Create(Diagnostics.ExpectedDigits, default, text[_start.._pos]));   // "0x", "0xG"
        else if (numberBase == 10 && count > 1 && buffer[0] == '0') LiteralError(Diagnostic.Create(Diagnostics.LeadingZeros, default));

        bool isFloat = false;
        if (numberBase == 10 && Peek() == '.' && char.IsAsciiDigit(Peek(1)))
        {
            isFloat = true;
            buffer.Append(text[_pos++]);
            ReadDigits(10, buffer);
        }
        if (numberBase == 10 && Peek() is 'e' or 'E')
        {
            isFloat = true;
            buffer.Append(text[_pos++]);
            if (Peek() is '+' or '-') buffer.Append(text[_pos++]);
            if (ReadDigits(10, buffer).Count == 0) LiteralError(Diagnostic.Create(Diagnostics.ExpectedExponentDigits, default));  // "1e", "1e+"
        }

        int suffixStart = _pos;
        while (IsIdentifierPart(Peek())) _pos++;
        string suffix = text[suffixStart.._pos];
        bool floatSuffix = suffix is "f32" or "f64";
        bool intSuffix = suffix is "i8" or "i16" or "i32" or "i64" or "u8" or "u16" or "u32" or "u64";
        if (suffix.Length == 0) { }
        else if (char.IsAsciiDigit(suffix[0])) LiteralError(Diagnostic.Create(Diagnostics.InvalidDigit, default, suffix[0], numberBase));   // "0b102"
        else if (!floatSuffix && !intSuffix) LiteralError(Diagnostic.Create(Diagnostics.UnknownSuffix, default, suffix));   // "12abc"
        else if (isFloat && intSuffix) LiteralError(Diagnostic.Create(Diagnostics.FloatIntegerSuffix, default, suffix));
        else if (numberBase != 10 && floatSuffix) LiteralError(Diagnostic.Create(Diagnostics.NonDecimalFloat, default));

        isFloat |= floatSuffix;
        if (!isFloat && overflow) LiteralError(Diagnostic.Create(Diagnostics.IntegerTooLarge, default));
        _value = isFloat ? 0.0 : 0UL;                    // the value after an error
        if (isFloat && _literalError is null)
        {
            string digits = buffer.ToString();
            double d = suffix == "f32"
                ? float.Parse(digits, NumberStyles.Float, CultureInfo.InvariantCulture)    // rounded once, to float
                : double.Parse(digits, NumberStyles.Float, CultureInfo.InvariantCulture);
            if (double.IsInfinity(d)) LiteralError(Diagnostic.Create(Diagnostics.FloatOutOfRange, default));
            else _value = d;
        }
        else if (_literalError is null)
            _value = value;
        if (_literalError is not null)               // one error, over the whole literal
        {
            _literalError.Span = Span;
            diagnostics.Add(_literalError);
        }
        return isFloat ? SyntaxKind.FloatLiteralToken : SyntaxKind.IntLiteralToken;
    }

    (ulong Value, int Count, bool Overflow) ReadDigits(int numberBase, StringBuilder buffer)   // digits and separators of one base
    {
        ulong value = 0;
        int count = 0;
        bool overflow = false;
        while (true)
        {
            char c = Peek();
            if (c == '_')
            {
                if (count == 0 || DigitValue(Peek(1)) >= numberBase) LiteralError(Diagnostic.Create(Diagnostics.MisplacedSeparator, default));
                _pos++;
                continue;
            }
            int digit = DigitValue(c);                   // 0 to 15 for '0'-'9', 'a'-'f', 'A'-'F'; 99 for anything else
            if (digit >= numberBase) break;
            if (value > (ulong.MaxValue - (ulong)digit) / (ulong)numberBase) overflow = true;
            else value = value * (ulong)numberBase + (ulong)digit;
            buffer.Append(c);
            count++;
            _pos++;
        }
        return (value, count, overflow);
    }
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

=== "C++"

    ```cpp
    SyntaxKind Lexer::String()
    {
        pos_++;                                          // the opening quote
        std::string builder;
        for (;;)
        {
            if (pos_ == text_.size() || Peek() == '\n')
            {
                diagnostics_.Report<Diag::UnterminatedString>(Span());   // the token ends here; lexing goes on
                break;
            }
            char c = text_[pos_++];
            if (c == '"') break;
            if (c != '\\') { builder += c; continue; }
            if (pos_ == text_.size() || Peek() == '\n') continue;   // a '\' at the end: reported as unterminated
            switch (char e = text_[pos_++])
            {
            case 'n': builder += '\n'; break;
            case 't': builder += '\t'; break;
            case '\\': case '"': builder += e; break;
            case 'u': UnicodeEscape(builder); break;     // \u{1F600}: reads the hex digits, appends the code point as UTF-8
            default: diagnostics_.Report<Diag::UnknownEscape>({ uint32_t(pos_ - 2), 2 }, e);
            }
        }
        value_ = std::move(builder);
        return SyntaxKind::StringLiteralToken;
    }
    ```

=== "C#"

    ```csharp
    SyntaxKind String()
    {
        _pos++;                                          // the opening quote
        var builder = new StringBuilder();
        while (true)
        {
            if (_pos == text.Length || Peek() == '\n')
            {
                diagnostics.Report(Diagnostics.UnterminatedString, Span);   // the token ends here; lexing goes on
                break;
            }
            char c = text[_pos++];
            if (c == '"') break;
            if (c != '\\') { builder.Append(c); continue; }
            if (_pos == text.Length || Peek() == '\n') continue;   // a '\' at the end: reported as unterminated
            char e = text[_pos++];
            switch (e)
            {
                case 'n': builder.Append('\n'); break;
                case 't': builder.Append('\t'); break;
                case '\\' or '"': builder.Append(e); break;
                case 'u': UnicodeEscape(builder); break; // \u{1F600}: reads the hex digits, appends new Rune(code point)
                default: diagnostics.Report(Diagnostics.UnknownEscape, new TextSpan(_pos - 2, 2), e); break;
            }
        }
        _value = builder.ToString();
        return SyntaxKind.StringLiteralToken;
    }
    ```

Stopping an unterminated string at the end of the line keeps one missing quote from swallowing the rest of the file.

## Trivia

**Trivia** is everything that is not a token: spaces, newlines, and comments.

=== "C++"

    ```cpp
    void Lexer::SkipTrivia()
    {
        for (;;)
        {
            char c = Peek();
            if (c == ' ' || c == '\t' || c == '\r' || c == '\n')
                pos_++;
            else if (c == '/' && Peek(1) == '/')
                while (pos_ < text_.size() && Peek() != '\n') pos_++;
            else if (c == '/' && Peek(1) == '*')
            {
                size_t commentStart = pos_;
                int depth = 1;                           // nested block comments: /* a /* b */ c */
                pos_ += 2;
                while (depth > 0 && pos_ < text_.size())
                {
                    if (Peek() == '/' && Peek(1) == '*') { depth++; pos_ += 2; }
                    else if (Peek() == '*' && Peek(1) == '/') { depth--; pos_ += 2; }
                    else pos_++;
                }
                if (depth > 0) diagnostics_.Report<Diag::UnterminatedComment>({ uint32_t(commentStart), 2 });
            }
            else
                return;
        }
    }
    ```

=== "C#"

    ```csharp
    void SkipTrivia()
    {
        while (true)
        {
            char c = Peek();
            if (c is ' ' or '\t' or '\r' or '\n')
                _pos++;
            else if (c == '/' && Peek(1) == '/')
                while (_pos < text.Length && Peek() != '\n') _pos++;
            else if (c == '/' && Peek(1) == '*')
            {
                int commentStart = _pos, depth = 1;      // nested block comments: /* a /* b */ c */
                _pos += 2;
                while (depth > 0 && _pos < text.Length)
                {
                    if (Peek() == '/' && Peek(1) == '*') { depth++; _pos += 2; }
                    else if (Peek() == '*' && Peek(1) == '/') { depth--; _pos += 2; }
                    else _pos++;
                }
                if (depth > 0) diagnostics.Report(Diagnostics.UnterminatedComment, new TextSpan(commentStart, 2));
            }
            else
                return;
        }
    }
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

## C++ tips

- Write the character tests yourself (`c >= 'a' && c <= 'z'`). `std::isalpha` and `std::isdigit` depend on the locale, and are undefined for negative `char` values, which every non-ASCII byte of UTF-8 is.
- Keep the source text alive for as long as the tokens: `Token::text` is a `std::string_view` into it. Load each file into a `std::string` owned by the compilation.
- `std::from_chars` (C++17; for floats, in libstdc++ since GCC 11 and in MSVC since 2019; check your version of libc++) parses floats correctly rounded and without the locale. `std::stod` and `strtod` read the decimal separator from the C locale.
- `std::unordered_map<std::string_view, SyntaxKind>` finds keywords without allocating. For a dozen keywords a `switch` on length, then a comparison, is as fast.
- With UTF-8 source, a non-ASCII byte outside a string or comment becomes a `BadToken` per byte. Decode a whole code point there and report it once.

## C# tips

- `char.IsLetter` and `char.IsDigit` accept every Unicode letter and digit, including Arabic-Indic digits. Decide whether identifiers may be Unicode; for digits use `char.IsAsciiDigit`.
- Build the keyword table once: `FrozenDictionary<string, SyntaxKind>`, or a `switch` expression on the text, which the C# compiler turns into a hash or length-based jump table. Look it up with the span (`.GetAlternateLookup<ReadOnlySpan<char>>()` on .NET 9 and later) to avoid allocating a string for every identifier.
- `SearchValues.Create("+-*/%=<>!&|^~")` with `span.IndexOfAnyExcept` skips runs of a character class quickly, such as whitespace or digits.
- `Token` as a `readonly record struct` keeps a token list compact. Storing `Text` only for identifiers and literals (the `kind <= StringLiteralToken` check relies on the enum's order) avoids a string per `(`.
- Parse an `f32` literal with `float.Parse`, as above: `(float)double.Parse(text)` rounds twice, and for some inputs lands one bit away from the correctly rounded `float`. Without `CultureInfo.InvariantCulture`, `1.5` fails to parse on machines whose decimal separator is a comma.
- The `StringBuilder` above is only needed for floats; a pooled `char` buffer, or a `stackalloc` span, avoids allocating one per number.
- `char.IsAsciiDigit`, `char.IsAsciiHexDigit`, and `char.IsAsciiLetter` (.NET 7) are the character tests: unlike `char.IsDigit`, they reject non-ASCII digits.
