# Parser

The parser turns tokens into a [syntax tree](syntax-trees.md). [Language design](../design.md#lexing-and-parsing) introduces recursive descent for statements and Pratt parsing for expressions. This page builds the whole parser for the example language: the grammar, the helpers, every construct, and recovery from errors.

## The grammar

Write it down before the parser, and keep it next to the code. Each rule becomes one function.

```text
file        = item* EOF
item        = function | struct | extern
function    = "fn" IDENT "(" params? ")" ("->" type)? block
extern      = "extern" "fn" IDENT "(" params? ")" ("->" type)? ";"
struct      = "struct" IDENT "{" (field ("," field)* ","?)? "}"
params      = param ("," param)* ","?
param       = IDENT ":" type
field       = IDENT ":" type
type        = IDENT | "*" type                         // i32, Vec2, *u8

block       = "{" statement* "}"
statement   = let | var | return | if | while | block | expr_stmt
let         = "let" IDENT (":" type)? "=" expr ";"
var         = "var" IDENT (":" type)? ("=" expr)? ";"
return      = "return" expr? ";"
if          = "if" expr block ("else" (if | block))?
while       = "while" expr block
expr_stmt   = expr ";"

expr        = see the precedence table
```

## Helpers

=== "C++"

    ```cpp
    class Parser
    {
    public:
        Parser(std::vector<Token> tokens, DiagnosticBag& diagnostics)
            : tokens_(std::move(tokens)), diagnostics_(diagnostics) {}
        FileSyntax* ParseFile();

    private:
        const Token& Current() const { return tokens_[pos_]; }
        const Token& Peek(size_t k) const { return tokens_[std::min(pos_ + k, tokens_.size() - 1)]; }  // never past EndOfFile
        bool At(SyntaxKind kind) const { return Current().kind == kind; }

        Token Advance()
        {
            Token token = Current();
            if (token.kind != SyntaxKind::EndOfFileToken) pos_++;
            return token;
        }

        std::optional<Token> Eat(SyntaxKind kind)       // an optional token
        {
            if (At(kind)) return Advance();
            return std::nullopt;
        }

        Token Expect(SyntaxKind kind)                   // a required token
        {
            if (At(kind)) return Advance();
            uint32_t end = pos_ > 0 ? tokens_[pos_ - 1].span.End() : 0;          // the end of the previous token
            Diagnostic& d = diagnostics_.Report<Diag::ExpectedToken>({ end, 0 }, Describe(kind), Describe(Current().kind));
            if (kind == SyntaxKind::SemicolonToken) d.WithFix({ end, 0 }, ";");     // safe to insert: editors offer it
            return Token{ .kind = kind, .span = { end, 0 }, .isMissing = true };  // zero length: the tree stays complete
        }

        template <class T, class... Args> T* Make(Args&&... args)   // allocate a node the parser owns
        {
            nodes_.push_back(std::make_unique<T>(std::forward<Args>(args)...));
            return static_cast<T*>(nodes_.back().get());
        }

        std::vector<Token> tokens_;
        size_t pos_ = 0;
        DiagnosticBag& diagnostics_;                   // see source text and diagnostics
        std::vector<std::unique_ptr<SyntaxNode>> nodes_;   // every node; SyntaxNode has a virtual destructor
    };
    ```

=== "C#"

    ```csharp
    public sealed class Parser(List<Token> tokens, DiagnosticBag diagnostics)
    {
        int _pos;

        Token Current => tokens[_pos];
        Token Peek(int k) => tokens[Math.Min(_pos + k, tokens.Count - 1)];   // never past EndOfFile
        bool At(SyntaxKind kind) => Current.Kind == kind;

        Token Advance()
        {
            Token token = Current;
            if (token.Kind != SyntaxKind.EndOfFileToken) _pos++;
            return token;
        }

        Token? Eat(SyntaxKind kind) => At(kind) ? Advance() : null;          // an optional token

        Token Expect(SyntaxKind kind)                                        // a required token
        {
            if (At(kind)) return Advance();
            int end = _pos > 0 ? tokens[_pos - 1].Span.End : 0;             // the end of the previous token
            Diagnostic d = diagnostics.Report(Diagnostics.ExpectedToken, new TextSpan(end, 0), Describe(kind), Describe(Current.Kind));
            if (kind == SyntaxKind.SemicolonToken) d.WithFix(new TextSpan(end, 0), ";");   // safe to insert: editors offer it
            return new Token(kind, new TextSpan(end, 0), IsMissing: true);   // zero length: the tree stays complete
        }

    }
    ```

`Describe(kind)` gives a kind's text for messages (`';'`, `identifier`). `Expect` never fails. It reports and returns a **missing token**, so `ParseLet` can always build a `LetSyntax` node. Report at the end of the previous token, not at the next one, which may be on the next line.

## Items and statements

=== "C++"

    ```cpp
    FileSyntax* Parser::ParseFile()
    {
        std::vector<ItemSyntax*> items;
        while (!At(SyntaxKind::EndOfFileToken))
        {
            size_t start = pos_;
            if (StartsItem(Current().kind)) items.push_back(ParseItem());   // fn, struct, extern
            if (pos_ == start) SkipBadTokens();                             // always make progress
        }
        return Make<FileSyntax>(std::move(items), Expect(SyntaxKind::EndOfFileToken));
    }

    FunctionSyntax* Parser::ParseFunction()
    {
        Token fnKeyword = Expect(SyntaxKind::FnKeyword);
        Token name = Expect(SyntaxKind::IdentifierToken);
        Token open = Expect(SyntaxKind::OpenParenToken);
        auto parameters = ParseSeparated<ParameterSyntax>([this] { return ParseParameter(); },
                                                          SyntaxKind::CommaToken, SyntaxKind::CloseParenToken);
        Token close = Expect(SyntaxKind::CloseParenToken);
        ReturnClauseSyntax* returnClause = nullptr;     // absent unless there is a '->'
        if (At(SyntaxKind::ArrowToken))
        {
            Token arrow = Advance();
            returnClause = Make<ReturnClauseSyntax>(arrow, ParseType());
        }
        BlockSyntax* body = ParseBlock();
        return Make<FunctionSyntax>(fnKeyword, name, open, std::move(parameters), close, returnClause, body);
    }

    template <class T> struct SeparatedList { std::vector<T*> items; std::vector<Token> separators; };

    template <class T, class ParseOne>
    SeparatedList<T> Parser::ParseSeparated(ParseOne parseOne, SyntaxKind separator, SyntaxKind until)
    {
        SeparatedList<T> list;
        while (!At(until) && !At(SyntaxKind::EndOfFileToken))
        {
            list.items.push_back(parseOne());
            std::optional<Token> comma = Eat(separator);
            if (!comma) break;                          // a trailing separator is fine: the loop sees `until`
            list.separators.push_back(*comma);
        }
        return list;
    }

    BlockSyntax* Parser::ParseBlock()
    {
        Token open = Expect(SyntaxKind::OpenBraceToken);
        std::vector<StatementSyntax*> statements;
        while (!At(SyntaxKind::CloseBraceToken) && !At(SyntaxKind::EndOfFileToken))
        {
            size_t start = pos_;
            if (StartsStatement(Current().kind)) statements.push_back(ParseStatement());   // a keyword or an expression
            if (pos_ == start) SkipBadTokens();
        }
        return Make<BlockSyntax>(open, std::move(statements), Expect(SyntaxKind::CloseBraceToken));
    }

    StatementSyntax* Parser::ParseStatement()
    {
        switch (Current().kind)
        {
        case SyntaxKind::LetKeyword:     return ParseLet();
        case SyntaxKind::VarKeyword:     return ParseVar();
        case SyntaxKind::ReturnKeyword:  return ParseReturn();
        case SyntaxKind::IfKeyword:      return ParseIf();
        case SyntaxKind::WhileKeyword:   return ParseWhile();
        case SyntaxKind::OpenBraceToken: return ParseBlock();
        default:
            ExpressionSyntax* expression = ParseExpression();
            return Make<ExpressionStatementSyntax>(expression, Expect(SyntaxKind::SemicolonToken));
        }
    }

    IfSyntax* Parser::ParseIf()
    {
        Token ifKeyword = Expect(SyntaxKind::IfKeyword);
        ExpressionSyntax* condition = ParseExpression(0, /*allowStructLiteral*/ false);   // see below
        BlockSyntax* then = ParseBlock();
        ElseClauseSyntax* elseClause = nullptr;
        if (At(SyntaxKind::ElseKeyword))
        {
            Token elseKeyword = Advance();
            StatementSyntax* body = At(SyntaxKind::IfKeyword) ? static_cast<StatementSyntax*>(ParseIf()) : ParseBlock();
            elseClause = Make<ElseClauseSyntax>(elseKeyword, body);
        }
        return Make<IfSyntax>(ifKeyword, condition, then, elseClause);
    }
    ```

=== "C#"

    ```csharp
    public FileSyntax ParseFile()
    {
        var items = new List<ItemSyntax>();
        while (!At(SyntaxKind.EndOfFileToken))
        {
            int start = _pos;
            if (StartsItem(Current.Kind)) items.Add(ParseItem());          // fn, struct, extern
            if (_pos == start) SkipBadTokens();                             // always make progress
        }
        return new FileSyntax(items, Expect(SyntaxKind.EndOfFileToken));
    }

    FunctionSyntax ParseFunction()
    {
        Token fnKeyword = Expect(SyntaxKind.FnKeyword);
        Token name = Expect(SyntaxKind.IdentifierToken);
        Token open = Expect(SyntaxKind.OpenParenToken);
        var parameters = ParseSeparated(ParseParameter, SyntaxKind.CommaToken, SyntaxKind.CloseParenToken);
        Token close = Expect(SyntaxKind.CloseParenToken);
        ReturnClauseSyntax? returnClause = null;        // absent unless there is a '->'
        if (At(SyntaxKind.ArrowToken))
            returnClause = new ReturnClauseSyntax(Advance(), ParseType());
        BlockSyntax body = ParseBlock();
        return new FunctionSyntax(fnKeyword, name, open, parameters, close, returnClause, body);
    }

    SeparatedSyntaxList<T> ParseSeparated<T>(Func<T> parseOne, SyntaxKind separator, SyntaxKind until) where T : SyntaxNode
    {
        var items = new List<T>();
        var separators = new List<Token>();
        while (!At(until) && !At(SyntaxKind.EndOfFileToken))
        {
            items.Add(parseOne());
            if (Eat(separator) is not Token comma) break;   // a trailing separator is fine: the loop sees `until`
            separators.Add(comma);
        }
        return new SeparatedSyntaxList<T>(items, separators);
    }

    BlockSyntax ParseBlock()
    {
        Token open = Expect(SyntaxKind.OpenBraceToken);
        var statements = new List<StatementSyntax>();
        while (!At(SyntaxKind.CloseBraceToken) && !At(SyntaxKind.EndOfFileToken))
        {
            int start = _pos;
            if (StartsStatement(Current.Kind)) statements.Add(ParseStatement());   // a keyword or an expression
            if (_pos == start) SkipBadTokens();
        }
        return new BlockSyntax(open, statements, Expect(SyntaxKind.CloseBraceToken));
    }

    StatementSyntax ParseStatement() => Current.Kind switch
    {
        SyntaxKind.LetKeyword => ParseLet(),
        SyntaxKind.VarKeyword => ParseVar(),
        SyntaxKind.ReturnKeyword => ParseReturn(),
        SyntaxKind.IfKeyword => ParseIf(),
        SyntaxKind.WhileKeyword => ParseWhile(),
        SyntaxKind.OpenBraceToken => ParseBlock(),
        _ => new ExpressionStatementSyntax(ParseExpression(), Expect(SyntaxKind.SemicolonToken)),
    };

    IfSyntax ParseIf()
    {
        Token ifKeyword = Expect(SyntaxKind.IfKeyword);
        ExpressionSyntax condition = ParseExpression(allowStructLiteral: false);   // see below
        BlockSyntax then = ParseBlock();
        ElseClauseSyntax? elseClause = null;
        if (At(SyntaxKind.ElseKeyword))
        {
            Token elseKeyword = Advance();
            StatementSyntax body = At(SyntaxKind.IfKeyword) ? ParseIf() : ParseBlock();
            elseClause = new ElseClauseSyntax(elseKeyword, body);
        }
        return new IfSyntax(ifKeyword, condition, then, elseClause);
    }
    ```

Requiring braces around `if` and `while` bodies removes the dangling-else problem and the need for parentheses around conditions.

## Expressions

Operators bind by **binding power**: higher binds tighter. Each infix operator has a left and a right power; left-associative operators have the right one higher, right-associative ones the left one higher.

| Precedence | Operators | Associativity | (left, right) power |
| --- | --- | --- | --- |
| Assignment | `=` | right | (2, 1) |
| Logical or | `\|\|` | left | (3, 4) |
| Logical and | `&&` | left | (5, 6) |
| Equality | `==` `!=` | none (`a == b == c` is an error) | (7, 8) |
| Comparison | `<` `<=` `>` `>=` | none | (9, 10) |
| Additive | `+` `-` | left | (11, 12) |
| Multiplicative | `*` `/` `%` | left | (13, 14) |
| Cast | `as` | left | (15, 16) |
| Prefix | `-` `!` `*` `&` | | right power 17 |
| Postfix | call `f(x)`, member `a.b` | | left power 19 |

=== "C++"

    ```cpp
    struct BindingPower { int left, right; bool nonAssociative = false; };
    constexpr int PrefixPower = 17, PostfixPower = 19;

    std::optional<BindingPower> InfixPower(SyntaxKind kind)    // the table above
    {
        switch (kind)
        {
        case SyntaxKind::EqualsToken:             return BindingPower{ 2, 1 };   // right-associative
        case SyntaxKind::PipePipeToken:           return BindingPower{ 3, 4 };
        case SyntaxKind::AmpersandAmpersandToken: return BindingPower{ 5, 6 };
        case SyntaxKind::EqualsEqualsToken:
        case SyntaxKind::BangEqualsToken:         return BindingPower{ 7, 8, true };
        case SyntaxKind::LessToken:    case SyntaxKind::LessEqualsToken:
        case SyntaxKind::GreaterToken: case SyntaxKind::GreaterEqualsToken:
                                                  return BindingPower{ 9, 10, true };
        case SyntaxKind::PlusToken:
        case SyntaxKind::MinusToken:              return BindingPower{ 11, 12 };
        case SyntaxKind::StarToken: case SyntaxKind::SlashToken:
        case SyntaxKind::PercentToken:            return BindingPower{ 13, 14 };
        case SyntaxKind::AsKeyword:               return BindingPower{ 15, 16 };
        default:                                  return std::nullopt;           // not an infix operator
        }
    }

    ExpressionSyntax* Parser::ParseExpression(int minPower, bool allowStructLiteral)   // declared with = 0, = true
    {
        ExpressionSyntax* left = ParsePrefix(allowStructLiteral);
        for (;;)
        {
            SyntaxKind op = Current().kind;
            if (op == SyntaxKind::OpenParenToken || op == SyntaxKind::DotToken)  // postfix: call, member access
            {
                if (PostfixPower < minPower) break;
                left = ParsePostfix(left);
                continue;
            }
            std::optional<BindingPower> power = InfixPower(op);
            if (!power || power->left < minPower) break;
            Token opToken = Advance();
            if (op == SyntaxKind::AsKeyword)            // the right side is a type, not an expression
            {
                left = Make<CastSyntax>(left, opToken, ParseType());
                continue;
            }
            ExpressionSyntax* right = ParseExpression(power->right, allowStructLiteral);
            left = Make<BinarySyntax>(left, opToken, right);
            std::optional<BindingPower> next = InfixPower(Current().kind);
            if (power->nonAssociative && next && next->left == power->left)      // a == b == c
                diagnostics_.Report<Diag::ChainedComparison>(Current().span);
        }
        return left;
    }

    ExpressionSyntax* Parser::ParsePrefix(bool allowStructLiteral)
    {
        switch (Current().kind)
        {
        case SyntaxKind::IntLiteralToken: case SyntaxKind::FloatLiteralToken: case SyntaxKind::StringLiteralToken:
        case SyntaxKind::TrueKeyword:     case SyntaxKind::FalseKeyword:
            return Make<LiteralSyntax>(Advance());
        case SyntaxKind::IdentifierToken:
        {
            Token name = Advance();
            if (allowStructLiteral && At(SyntaxKind::OpenBraceToken)) return ParseStructLiteral(name);
            return Make<NameSyntax>(name);
        }
        case SyntaxKind::OpenParenToken:
        {
            Token open = Advance();
            ExpressionSyntax* inner = ParseExpression(); // struct literals are allowed again inside parentheses
            return Make<ParenthesizedSyntax>(open, inner, Expect(SyntaxKind::CloseParenToken));
        }
        case SyntaxKind::MinusToken: case SyntaxKind::BangToken: case SyntaxKind::StarToken: case SyntaxKind::AmpersandToken:
        {
            Token op = Advance();
            return Make<UnarySyntax>(op, ParseExpression(PrefixPower, allowStructLiteral));
        }
        default:
            diagnostics_.Report<Diag::ExpectedExpression>(Current().span, Describe(Current().kind));
            return Make<MissingExpressionSyntax>(Current().span.start);   // do not consume: the caller decides
        }
    }

    ExpressionSyntax* Parser::ParsePostfix(ExpressionSyntax* left)
    {
        if (At(SyntaxKind::OpenParenToken))
        {
            Token open = Advance();
            auto arguments = ParseSeparated<ExpressionSyntax>([this] { return ParseExpression(); },
                                                              SyntaxKind::CommaToken, SyntaxKind::CloseParenToken);
            return Make<CallSyntax>(left, open, std::move(arguments), Expect(SyntaxKind::CloseParenToken));
        }
        Token dot = Expect(SyntaxKind::DotToken);
        return Make<MemberSyntax>(left, dot, Expect(SyntaxKind::IdentifierToken));
    }
    ```

=== "C#"

    ```csharp
    const int PrefixPower = 17, PostfixPower = 19;

    static (int Left, int Right, bool NonAssociative)? InfixPower(SyntaxKind kind) => kind switch   // the table above
    {
        SyntaxKind.EqualsToken => (2, 1, false),                         // right-associative
        SyntaxKind.PipePipeToken => (3, 4, false),
        SyntaxKind.AmpersandAmpersandToken => (5, 6, false),
        SyntaxKind.EqualsEqualsToken or SyntaxKind.BangEqualsToken => (7, 8, true),
        SyntaxKind.LessToken or SyntaxKind.LessEqualsToken
            or SyntaxKind.GreaterToken or SyntaxKind.GreaterEqualsToken => (9, 10, true),
        SyntaxKind.PlusToken or SyntaxKind.MinusToken => (11, 12, false),
        SyntaxKind.StarToken or SyntaxKind.SlashToken or SyntaxKind.PercentToken => (13, 14, false),
        SyntaxKind.AsKeyword => (15, 16, false),
        _ => null,                                                       // not an infix operator
    };

    ExpressionSyntax ParseExpression(int minPower = 0, bool allowStructLiteral = true)
    {
        ExpressionSyntax left = ParsePrefix(allowStructLiteral);
        while (true)
        {
            SyntaxKind op = Current.Kind;
            if (op is SyntaxKind.OpenParenToken or SyntaxKind.DotToken) // postfix: call, member access
            {
                if (PostfixPower < minPower) break;
                left = ParsePostfix(left);
                continue;
            }
            if (InfixPower(op) is not var (leftPower, rightPower, nonAssociative) || leftPower < minPower) break;
            Token opToken = Advance();
            if (op == SyntaxKind.AsKeyword)                              // the right side is a type, not an expression
            {
                left = new CastSyntax(left, opToken, ParseType());
                continue;
            }
            ExpressionSyntax right = ParseExpression(rightPower, allowStructLiteral);
            left = new BinarySyntax(left, opToken, right);
            if (nonAssociative && InfixPower(Current.Kind)?.Left == leftPower)   // a == b == c
                diagnostics.Report(Diagnostics.ChainedComparison, Current.Span);
        }
        return left;
    }

    ExpressionSyntax ParsePrefix(bool allowStructLiteral)
    {
        switch (Current.Kind)
        {
            case SyntaxKind.IntLiteralToken or SyntaxKind.FloatLiteralToken or SyntaxKind.StringLiteralToken
                or SyntaxKind.TrueKeyword or SyntaxKind.FalseKeyword:
                return new LiteralSyntax(Advance());
            case SyntaxKind.IdentifierToken:
                Token name = Advance();
                if (allowStructLiteral && At(SyntaxKind.OpenBraceToken)) return ParseStructLiteral(name);
                return new NameSyntax(name);
            case SyntaxKind.OpenParenToken:
                Token open = Advance();
                ExpressionSyntax inner = ParseExpression();              // struct literals are allowed again inside parentheses
                return new ParenthesizedSyntax(open, inner, Expect(SyntaxKind.CloseParenToken));
            case SyntaxKind.MinusToken or SyntaxKind.BangToken or SyntaxKind.StarToken or SyntaxKind.AmpersandToken:
                Token op = Advance();
                return new UnarySyntax(op, ParseExpression(PrefixPower, allowStructLiteral));
            default:
                diagnostics.Report(Diagnostics.ExpectedExpression, Current.Span, Describe(Current.Kind));
                return new MissingExpressionSyntax(Current.Span.Start);  // do not consume: the caller decides
        }
    }

    ExpressionSyntax ParsePostfix(ExpressionSyntax left)
    {
        if (At(SyntaxKind.OpenParenToken))
        {
            Token open = Advance();
            var arguments = ParseSeparated(() => ParseExpression(), SyntaxKind.CommaToken, SyntaxKind.CloseParenToken);
            return new CallSyntax(left, open, arguments, Expect(SyntaxKind.CloseParenToken));
        }
        Token dot = Expect(SyntaxKind.DotToken);
        return new MemberSyntax(left, dot, Expect(SyntaxKind.IdentifierToken));
    }
    ```

### The struct literal ambiguity

`if v == origin { ... }` could be a comparison followed by a block, or a comparison with a struct literal `origin { ... }`. Rust's rule is simple and works: **struct literals are not allowed directly in the condition of `if` or `while`**. Inside parentheses they are fine again: `if v == (Vec2 { x: 0.0, y: 0.0 }) { ... }`. Pass a flag down through `ParseExpression`, and reset it inside parentheses and argument lists (both call `ParseExpression()` with the default).

### Generics and `<`

`a < b > (c)` is a comparison chain, or a call to a generic `a<b>` with argument `c`. Avoid the question when you add generics: use a syntax that is not ambiguous (`f[T](x)`, or `f::<T>(x)` as in Rust), or only allow `<` after a name in **type** position, where comparisons cannot appear.

## Error recovery

The aim is to report the first real error in each statement, then carry on as if the code were correct.

- **Missing tokens** come from `expect`, which inserts one and moves on. `let x = 5` followed by a new line gets "expected ';'" and a complete `Let` node.
- **Unexpected tokens** are skipped until a **synchronisation point**: a keyword that starts an item or statement (`fn`, `struct`, `let`, `var`, `if`, `while`, `return`), a closing `}`, or just past a `;`. The block and file loops only call a parse function for a token that can start what they expect, and skip anything else, so one stray `)` gives one error. The skipped tokens go into the tree as **skipped trivia** or a `Bad` node, so the text is still covered.

=== "C++"

    ```cpp
    void Parser::SkipBadTokens()
    {
        Token first = Advance();                        // at least one token, so the caller always makes progress
        diagnostics_.Report<Diag::UnexpectedToken>(first.span, Describe(first.kind));   // once per run of bad tokens
        Token last = first;
        while (last.kind != SyntaxKind::SemicolonToken && !IsSyncPoint(Current().kind))   // keywords, '}', end of file
            last = Advance();
        // Keep first .. last as skipped-token trivia on the next token, or in a BadStatement, so the tree covers the text.
    }
    ```

=== "C#"

    ```csharp
    void SkipBadTokens()
    {
        Token first = Advance();                        // at least one token, so the caller always makes progress
        diagnostics.Report(Diagnostics.UnexpectedToken, first.Span, Describe(first.Kind));   // once per run of bad tokens
        Token last = first;
        while (last.Kind != SyntaxKind.SemicolonToken && !IsSyncPoint(Current.Kind))   // keywords, '}', end of file
            last = Advance();
        // Keep first .. last as skipped-token trivia on the next token, or in a BadStatement, so the tree covers the text.
    }
    ```

- **Always make progress.** Every loop over a list (items, statements) records the position at the top and skips if it did not move; `SkipBadTokens` always consumes at least one token. A parser that can loop forever on one bad token will, the first time someone types into an editor.
- **Do not report at a missing node twice.** `ParsePrefix` returns a `MissingExpressionSyntax` without consuming anything, and the statement that follows reports nothing more about it.
- **Delimiters guide recovery.** On an error inside parentheses or braces, skip to the matching closer rather than to the next keyword, counting nesting as you go.

## More tips

**Design the grammar for one-token decisions.** If every statement and item starts with a distinct token (`let`, `fn`, `if`), the parser decides with `current.kind` alone. Each construct that needs more look-ahead is a place where parsing, error recovery, and error messages get harder.

**Look-ahead before backtracking.** Where one token is not enough, look further without consuming: `Peek(1).kind == ColonToken` tells a named argument `f(x: 1)` from an expression. Fixed look-ahead keeps the parser linear.

**Speculative parsing, when unavoidable.** For a genuine ambiguity (a generic call `f<T>(x)` if you chose that syntax), save the position and the diagnostic count, try one parse, and rewind if it fails:

=== "C++"

    ```cpp
    template <class ParseFn>
    auto Parser::TryParse(ParseFn parse) -> decltype(parse())   // nullptr if it did not fit
    {
        size_t savedPos = pos_, savedCount = diagnostics_.Count();
        auto result = parse();
        if (diagnostics_.Count() > savedCount)          // it did not fit: undo everything
        {
            pos_ = savedPos;
            diagnostics_.Truncate(savedCount);
            return nullptr;
        }
        return result;
    }
    ```

=== "C#"

    ```csharp
    T? TryParse<T>(Func<T> parse) where T : class      // null if it did not fit
    {
        int savedPos = _pos, savedCount = diagnostics.Count;
        T result = parse();
        if (diagnostics.Count > savedCount)             // it did not fit: undo everything
        {
            _pos = savedPos;
            diagnostics.Truncate(savedCount);
            return null;
        }
        return result;
    }
    ```

Keep this to one or two places; nested speculation can take exponential time.

**"Expected one of" messages.** Record each token kind tested with `At()` since the last token was consumed. When parsing fails, that set is exactly what would have been valid: "expected ',' or ')' after the argument". Clear it in `Advance()`.

**Separate parsers for types and expressions.** `ParseType` and `ParseExpression` should be different functions, called where each is expected. C-style casts (`(T)x`) need both at once and are ambiguous with parenthesised expressions; `x as T` avoids the problem.

**Leave semantics to the binder.** The parser should accept `5;` or `a + b;` as expression statements; "this expression has no effect" is a binder warning. A parser that rejects things it could parse produces worse messages and recovers worse.

**Attributes and doc comments.** Parse `#[...]` attributes into a list attached to the next item, and keep `///` doc comments as trivia on that item's first token. Both then reach the binder with the item they describe.

**Trailing separators everywhere.** Allow a trailing comma in every comma-separated list (parameters, arguments, fields, struct literals). It makes diffs one line shorter and generated code simpler, and `ParseSeparated` handles it already.

**Test precedence exhaustively.** For every pair of binary operators, parse `a op1 b op2 c` and check the grouping against the precedence table. It is a few lines of test code and catches every table mistake.

## C++ tips

- **Evaluation order.** C++ does not specify the order of function arguments, so `Make<LetSyntax>(Advance(), Expect(SyntaxKind::IdentifierToken), ...)` can read the tokens in the wrong order. Consume each piece into a local first, as the code above does, leaving at most one parse call among the arguments. C# evaluates arguments left to right, so its version can nest them.
- **Node ownership.** The parser owns every node through `nodes_`, and the tree uses plain pointers. Move the vector into the compilation, or use an arena (a bump allocator with nodes destroyed together), so the tree lives as long as the stages that read it. Nodes from a failed `TryParse` stay in the arena unused, which is harmless.
- **Optional parts** are `nullptr` (`returnClause`, `elseClause`); optional tokens are `std::optional<Token>`.
- **Recursion depth** follows nesting depth. Count it in `ParseExpression` and report "expression too deeply nested" past a limit, since a stack overflow in C++ is a crash with no message.

## C# tips

- Keep `InfixPower` next to the prefix and postfix powers, as above, so the precedence table is visible in one place in the code.
- `ParseSeparated` returns a `SeparatedSyntaxList<T>` that keeps the separators as well as the items: a formatter and the language server's signature help both need the commas.
- Recursion depth follows nesting depth. Deeply nested input (a generated 10,000-term expression) can overflow the stack: count depth in `ParseExpression` and report "expression too deeply nested" past a limit, rather than crash. `RuntimeHelpers.EnsureSufficientExecutionStack()` throws a catchable exception instead of a crash.
- Return `null` from no parse function (only optional parts, such as the return clause, are null). Missing pieces are `MissingExpressionSyntax` or missing tokens, so later stages never need null checks for broken input.
