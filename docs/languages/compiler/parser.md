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
| Assignment | `=` `+=` `-=` `*=` `/=` `%=` | right | (2, 1) |
| Logical or | `\|\|` | left | (3, 4) |
| Logical and | `&&` | left | (5, 6) |
| Equality | `==` `!=` | none (`a == b == c` is an error) | (7, 8) |
| Comparison | `<` `<=` `>` `>=` | none | (9, 10) |
| Additive | `+` `-` | left | (11, 12) |
| Multiplicative | `*` `/` `%` | left | (13, 14) |
| Cast | `as` | left | (15, 16) |
| Prefix | `-` `!` `*` `&` | | right power 17 |
| Postfix | call `f(x)`, member `a.b` | | left power 19 |

### How binding powers work

**The problem.** The parser reads tokens left to right, but the tree has to follow precedence and associativity, not reading order:

| Input | Left to right, or always recursing right | Correct |
| --- | --- | --- |
| `1 + 2 * 3` | `(1 + 2) * 3` | `1 + (2 * 3)` |
| `a - b - c` | `a - (b - c)` | `(a - b) - c` |
| `a = b = c` | `(a = b) = c` | `a = (b = c)` |

Every operand in the middle (`2`, `b`) sits between two operators, and the only question the parser answers is: **which of the two gets it?**

**Two pulls on each operand.** Think of each operator as pulling on its neighbours, with a left pull and a right pull: the (left, right) numbers in the table. The operand in the middle goes to whichever side pulls harder:

- `1 + 2 * 3`: `2` is pulled by `+`'s right (12) and `*`'s left (13). `*` wins: `1 + (2 * 3)`.
- `a - b - c`: `b` is pulled by the first `-`'s right (12) and the second `-`'s left (11). The first wins: `(a - b) - c`. A **higher right** power makes an operator win ties against its own kind: left-associative.
- `a = b = c`: `b` is pulled by the first `=`'s right (1) and the second's left (2). The second wins: `a = (b = c)`. A **higher left** power makes it right-associative. (This language then rejects the inner assignment in the binder: see [assignment](#assignment).)

Only which number is bigger at each operand matters, not the values themselves; leaving gaps lets new operators fit in between.

**The loop and the recursion.** Without postfix operators, casts, [assignment](#assignment), and error handling, the parser is this:

=== "C++"

    ```cpp
    ExpressionSyntax* Parser::ParseExpression(int minPower)    // the pull of the operator to my left
    {
        ExpressionSyntax* left = ParsePrefix();                // a literal, a name, ( ... ), or -x
        for (;;)
        {
            std::optional<BindingPower> power = InfixPower(Current().kind);
            if (!power || power->left < minPower) break;       // the operator to my left wins: let it have `left`
            Token op = Advance();
            ExpressionSyntax* right = ParseExpression(power->right);   // keeps going while operators out-pull `op`
            left = Make<BinarySyntax>(left, op, right);
        }
        return left;
    }
    ```

=== "C#"

    ```csharp
    ExpressionSyntax ParseExpression(int minPower)             // the pull of the operator to my left
    {
        ExpressionSyntax left = ParsePrefix();                 // a literal, a name, ( ... ), or -x
        while (true)
        {
            if (InfixPower(Current.Kind) is not var (leftPower, rightPower, _) || leftPower < minPower)
                break;                                         // the operator to my left wins: let it have `left`
            Token op = Advance();
            ExpressionSyntax right = ParseExpression(rightPower);      // keeps going while operators out-pull `op`
            left = new BinarySyntax(left, op, right);
        }
        return left;
    }
    ```

- **`minPower` is how hard the operator to the left pulls** on the expression being built. At the top there is none, so it is 0.
- **The `break` is the tug of war**: the next operator's left power against `minPower`. When the operator to the left wins, the call returns, and its caller attaches `left` to that operator.

**A trace of `1 + 2 * 3 - 4`.** Each indent is a recursive call:

| Step | Call | What happens |
| --- | --- | --- |
| 1 | A: `ParseExpression(0)` | `left = 1`. `+` has left 11 ≥ 0: take it, and parse its right side with `ParseExpression(12)` |
| 2 | → B: `ParseExpression(12)` | `left = 2`. `*` has left 13 ≥ 12: it out-pulls `+`. Take it, and call `ParseExpression(14)` |
| 3 | → → C: `ParseExpression(14)` | `left = 3`. `-` has left 11 < 14: it loses to `*`. Return `3` |
| 4 | ← B | `left = 2 * 3`. `-` has left 11 < 12: it loses to `+` too. Return `(2 * 3)` |
| 5 | ← A | `left = 1 + (2 * 3)`. `-` has left 11 ≥ 0: nothing to the left. Take it, and call `ParseExpression(12)` |
| 6 | → D: `ParseExpression(12)` | `left = 4`. End of input: return `4` |
| 7 | ← A | `left = (1 + (2 * 3)) - 4`. End of input: return |

A call keeps taking operators for as long as they pull harder than the one that started it. When a weaker one turns up, the calls unwind to the level where it belongs.

**Prefix, postfix, and parentheses** follow the same rule:

- **Unary minus** has right power 17: `ParsePrefix` takes the `-` and calls `ParseExpression(17)`. In `-a * b`, `*` (13) cannot beat 17, so the operand is `a`: `(-a) * b`.
- **Calls and member access** are postfix, with left power 19, more than any other operator, so they stay with what is just before them. The loop checks for `(` and `.` first: `a.b(c)` becomes `a`, then `a.b`, then `(a.b)(c)`, and since 19 > 17, `-a.b(c)` is `-(a.b(c))`.
- **Parentheses** work because `ParsePrefix`, on `(`, calls `ParseExpression(0)`, which resets the pull inside, and then expects `)`. Call arguments do the same between their commas.

To check your understanding, predict how `a - b + c`, `-x * y`, `a = b + c * d`, and `f(a, b).x` group, then print them with the [`Parenthesise` test helper](testing.md#unit-tests). Where one surprises you, find the operand in the middle and compare the two pulls on it.

### The full parser

The complete version adds the postfix operators, `as` casts, assignment nodes, chained-comparison errors, and the struct literal flag:

=== "C++"

    ```cpp
    struct BindingPower { int left, right; bool nonAssociative = false; };
    constexpr int PrefixPower = 17, PostfixPower = 19;

    bool IsAssignmentOperator(SyntaxKind kind)
    {
        switch (kind)
        {
        case SyntaxKind::EqualsToken: case SyntaxKind::PlusEqualsToken: case SyntaxKind::MinusEqualsToken:
        case SyntaxKind::StarEqualsToken: case SyntaxKind::SlashEqualsToken: case SyntaxKind::PercentEqualsToken: return true;
        default: return false;
        }
    }

    std::optional<BindingPower> InfixPower(SyntaxKind kind)
    {
        switch (kind)
        {
        case SyntaxKind::EqualsToken:      case SyntaxKind::PlusEqualsToken:  case SyntaxKind::MinusEqualsToken:
        case SyntaxKind::StarEqualsToken:  case SyntaxKind::SlashEqualsToken: case SyntaxKind::PercentEqualsToken:
                                                  return BindingPower{ 2, 1 };    // = += -= ...: right-associative
        case SyntaxKind::PipePipeToken:           return BindingPower{ 3, 4 };
        case SyntaxKind::AmpersandAmpersandToken: return BindingPower{ 5, 6 };
        case SyntaxKind::EqualsEqualsToken:
        case SyntaxKind::BangEqualsToken:         return BindingPower{ 7, 8, true };
        case SyntaxKind::LessToken:      case SyntaxKind::LessEqualsToken:
        case SyntaxKind::GreaterToken:   case SyntaxKind::GreaterEqualsToken:
                                                  return BindingPower{ 9, 10, true };
        case SyntaxKind::PlusToken:
        case SyntaxKind::MinusToken:              return BindingPower{ 11, 12 };
        case SyntaxKind::StarToken: case SyntaxKind::SlashToken:
        case SyntaxKind::PercentToken:            return BindingPower{ 13, 14 };
        case SyntaxKind::AsKeyword:               return BindingPower{ 15, 16 };
        default:                                  return std::nullopt;            // not an infix operator
        }
    }

    ExpressionSyntax* Parser::ParseExpression(int minPower, bool allowStructLiteral)
    {
        ExpressionSyntax* left = ParsePrefix(allowStructLiteral);
        for (;;)
        {
            SyntaxKind op = Current().kind;
            if (op == SyntaxKind::OpenParenToken || op == SyntaxKind::DotToken)   // postfix: call, member access
            {
                if (PostfixPower < minPower) break;
                left = ParsePostfix(left);
                continue;
            }
            std::optional<BindingPower> power = InfixPower(op);
            if (!power || power->left < minPower) break;
            Token opToken = Advance();
            if (op == SyntaxKind::AsKeyword)                       // the right side is a type, not an expression
            {
                left = Make<CastSyntax>(left, opToken, ParseType());
                continue;
            }
            ExpressionSyntax* right = ParseExpression(power->right, allowStructLiteral);
            if (IsAssignmentOperator(op))
            {
                left = Make<AssignmentSyntax>(left, opToken, right);   // its own node: not arithmetic
                continue;
            }
            left = Make<BinarySyntax>(left, opToken, right);
            std::optional<BindingPower> next = InfixPower(Current().kind);
            if (power->nonAssociative && next && next->left == power->left)        // a == b == c
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

    static bool IsAssignmentOperator(SyntaxKind kind) => kind is SyntaxKind.EqualsToken or SyntaxKind.PlusEqualsToken
        or SyntaxKind.MinusEqualsToken or SyntaxKind.StarEqualsToken or SyntaxKind.SlashEqualsToken or SyntaxKind.PercentEqualsToken;

    static (int Left, int Right, bool NonAssociative)? InfixPower(SyntaxKind kind) => kind switch
    {
        _ when IsAssignmentOperator(kind) => (2, 1, false),            // = += -= *= /= %=: right-associative
        SyntaxKind.PipePipeToken => (3, 4, false),
        SyntaxKind.AmpersandAmpersandToken => (5, 6, false),
        SyntaxKind.EqualsEqualsToken or SyntaxKind.BangEqualsToken => (7, 8, true),
        SyntaxKind.LessToken or SyntaxKind.LessEqualsToken
            or SyntaxKind.GreaterToken or SyntaxKind.GreaterEqualsToken => (9, 10, true),
        SyntaxKind.PlusToken or SyntaxKind.MinusToken => (11, 12, false),
        SyntaxKind.StarToken or SyntaxKind.SlashToken or SyntaxKind.PercentToken => (13, 14, false),
        SyntaxKind.AsKeyword => (15, 16, false),
        _ => null,                                                        // not an infix operator
    };

    ExpressionSyntax ParseExpression(int minPower = 0, bool allowStructLiteral = true)
    {
        ExpressionSyntax left = ParsePrefix(allowStructLiteral);
        while (true)
        {
            SyntaxKind op = Current.Kind;
            if (op is SyntaxKind.OpenParenToken or SyntaxKind.DotToken)  // postfix: call, member access
            {
                if (PostfixPower < minPower) break;
                left = ParsePostfix(left);
                continue;
            }
            if (InfixPower(op) is not var (leftPower, rightPower, nonAssociative) || leftPower < minPower) break;
            Token opToken = Advance();
            if (op == SyntaxKind.AsKeyword)                               // the right side is a type, not an expression
            {
                left = new CastSyntax(left, opToken, ParseType());
                continue;
            }
            ExpressionSyntax right = ParseExpression(rightPower, allowStructLiteral);
            if (IsAssignmentOperator(op))
            {
                left = new AssignmentSyntax(left, opToken, right);        // its own node: not arithmetic
                continue;
            }
            left = new BinarySyntax(left, opToken, right);
            if (nonAssociative && InfixPower(Current.Kind)?.Left == leftPower)    // a == b == c
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

### Assignment

`=` and the compound operators share the lowest binding power, (2, 1), so they are right-associative and everything else on either side binds first: `x = a + b * c` assigns the whole sum. Four decisions go with them.

**A node of its own.** `x = 1` is not arithmetic. Parsing it into an `AssignmentSyntax` (the full parser above does this for every assignment operator) means no later stage can mistake it for a `BinarySyntax` and look up an operator `=` for it:

=== "C++"

    ```cpp
    struct AssignmentSyntax final : ExpressionSyntax
    {
        AssignmentSyntax(ExpressionSyntax* target, Token op, ExpressionSyntax* value)
            : ExpressionSyntax(SyntaxKind::AssignmentExpression), target(target), op(op), value(value) {}
        void GetChildren(std::vector<SyntaxChild>& out) const override { out.insert(out.end(), { target, &op, value }); }
        ExpressionSyntax* const target;
        const Token op;                                // `=`, or a compound operator such as `+=`
        ExpressionSyntax* const value;
    };
    ```

=== "C#"

    ```csharp
    public sealed class AssignmentSyntax(ExpressionSyntax target, Token op, ExpressionSyntax value) : ExpressionSyntax
    {
        public ExpressionSyntax Target => target;
        public Token Operator => op;                      // `=`, or a compound operator such as `+=`
        public ExpressionSyntax Value => value;
        public override SyntaxKind Kind => SyntaxKind.AssignmentExpression;
        public override IEnumerable<SyntaxNodeOrToken> GetChildren() { yield return target; yield return op; yield return value; }
    }
    ```

**Statement or expression.** In C, an assignment is an expression with a value, so `a = b = c` works, and so does `if (x = 1)`, which is almost always a typo for `==`. The choices:

| Rule | `a = b = c` | `if x = 1` | Used by |
| --- | --- | --- | --- |
| An expression whose value is the assigned value | allowed | allowed, a classic bug | C, C++; C# and Java too, but there a condition must be `bool`, so only `if (b = true)` slips through |
| A statement, in the grammar | parse error | parse error | Go (Python is similar, with `a = b = c` as a special chained form) |
| Parsed as an expression, but its type is `void` and it may only stand as a whole statement | error | error, with a fix | Rust, Swift (in effect) |

The last keeps the parser simple, because assignment is one more operator in the loop, and puts the rule in the binder, which can give a useful message. A statement that is just an assignment binds it; an assignment anywhere else is reported, and when a `bool` was expected, the error offers `==` as a [fix](source-diagnostics.md#reporting):

=== "C++"

    ```cpp
    // In BindStatement: a whole expression statement is the one place an assignment may be.
    case SyntaxKind::ExpressionStatement:
    {
        auto* s = static_cast<const ExpressionStatementSyntax*>(syntax);
        if (s->expression->kind == SyntaxKind::AssignmentExpression)
            return Make<BoundExpressionStatement>(s, BindAssignment(static_cast<const AssignmentSyntax*>(s->expression), scope));
        return Make<BoundExpressionStatement>(s, BindExpression(s->expression, scope));
    }

    // In BindExpression, both modes: an assignment anywhere else.
    //     case SyntaxKind::AssignmentExpression: return BindAssignmentAsValue(assignment, expected, scope);

    // `if x = 1`, `let y = (x = 1);`, and the inner `=` of `a = b = c`.
    const BoundExpression* Binder::BindAssignmentAsValue(const AssignmentSyntax* syntax, const Type* expected, const Scope& scope)
    {
        Diagnostic& d = diagnostics_.Report<Diag::AssignmentAsValue>(syntax->op.span);
        if (expected == &Types::Bool && syntax->op.kind == SyntaxKind::EqualsToken)
            d.WithFix(syntax->op.span, "==");                      // `if x = 1`: almost always meant `==`
        BindAssignment(syntax, scope);                             // still check both sides
        return Make<BoundError>(syntax);                           // and report nothing more about it
    }
    ```

=== "C#"

    ```csharp
    // In BindStatement: a whole expression statement is the one place an assignment may be.
    ExpressionStatementSyntax { Expression: AssignmentSyntax a } e => new BoundExpressionStatement(e, BindAssignment(a, scope)),
    ExpressionStatementSyntax e => new BoundExpressionStatement(e, BindExpression(e.Expression, scope)),

    // In BindExpression, both modes: an assignment anywhere else.
    //     AssignmentSyntax a => BindAssignmentAsValue(a, expected, scope),

    // `if x = 1`, `let y = (x = 1);`, and the inner `=` of `a = b = c`.
    BoundExpression BindAssignmentAsValue(AssignmentSyntax syntax, TypeSymbol? expected, Scope scope)
    {
        Diagnostic d = diagnostics.Report(Diagnostics.AssignmentAsValue, syntax.Operator.Span);
        if (expected == TypeSymbol.Bool && syntax.Operator.Kind == SyntaxKind.EqualsToken)
            d.WithFix(syntax.Operator.Span, "==");                            // `if x = 1`: almost always meant `==`
        BindAssignment(syntax, scope);                                       // still check both sides
        return new BoundError(syntax);                                       // and report nothing more about it
    }
    ```

```text
main.lang:1:36: error E0213: an assignment has no value; it can only be a statement
  |
1 | fn main() -> i32 { var x = 1; if x = 2 { } return 0; }
  |                                    ^
  help: replace with '=='
```

**What can be assigned to.** The parser accepts any expression on the left, so `1 = 2` parses, and the binder decides. That keeps the grammar one rule, and lets the error say why: "cannot be assigned to" for `1` or `f()`, "immutable" for a `let`. A target is a variable, a field of an assignable struct, or anything through a pointer (`*p`, `p.x` with `p: *Vec2`):

=== "C++"

    ```cpp
    const BoundExpression* Binder::BindAssignment(const AssignmentSyntax* syntax, const Scope& scope)   // only as a whole statement
    {
        const BoundExpression* target = BindExpression(syntax->target, scope);
        if (target->type == &Types::Error) return Make<BoundError>(syntax);
        const BoundExpression* value = BindExpression(syntax->value, target->type, scope);   // check: `x += 1` with x: u8 adds a u8
        const Symbol* root = RootVariable(target);
        if (!root && !ThroughPointer(target))                      // 1 = 2, f() = 3, (a + b) = c
        {
            diagnostics_.Report<Diag::NotAssignable>(syntax->target->Span());
            return Make<BoundError>(syntax);
        }
        auto* local = dynamic_cast<const LocalSymbol*>(root);
        if (dynamic_cast<const ParameterSymbol*>(root) || (local && !local->isMutable))
        {
            diagnostics_.Report<Diag::ImmutableAssignment>(syntax->target->Span(), root->name)
                .WithRelated(root->declaration->Span(), "declared here");
            return Make<BoundError>(syntax);
        }
        if (syntax->op.kind == SyntaxKind::EqualsToken) return Make<BoundAssignment>(syntax, target, value);

        SyntaxKind arithmetic;                                     // += is +, -= is -, ...
        switch (syntax->op.kind)
        {
        case SyntaxKind::PlusEqualsToken:  arithmetic = SyntaxKind::PlusToken; break;
        case SyntaxKind::MinusEqualsToken: arithmetic = SyntaxKind::MinusToken; break;
        case SyntaxKind::StarEqualsToken:  arithmetic = SyntaxKind::StarToken; break;
        case SyntaxKind::SlashEqualsToken: arithmetic = SyntaxKind::SlashToken; break;
        default:                           arithmetic = SyntaxKind::PercentToken; break;
        }
        const BoundBinaryOperator* op = LookupBinaryOperator(arithmetic, target->type, target->type);
        if (!op) diagnostics_.Report<Diag::NoBinaryOperator>(syntax->op.span, syntax->op.text, target->type->Display(), target->type->Display());
        if (!op || value->type == &Types::Error) return Make<BoundError>(syntax);
        return Make<BoundCompoundAssignment>(syntax, target, op, value);
    }

    static const Symbol* RootVariable(const BoundExpression* e)   // x, x.a, x.a.b: the variable being changed
    {
        if (auto* v = dynamic_cast<const BoundVariable*>(e)) return v->symbol;
        if (auto* f = dynamic_cast<const BoundFieldAccess*>(e); f && f->receiver->type->kind == TypeKind::Struct) return RootVariable(f->receiver);
        return nullptr;                                            // through a pointer (or not assignable)
    }

    static bool ThroughPointer(const BoundExpression* e)          // *p, p.x, (*p).a.b: changes memory, not a variable
    {
        if (auto* u = dynamic_cast<const BoundUnary*>(e)) return u->op == UnaryOperatorKind::Dereference;
        if (auto* f = dynamic_cast<const BoundFieldAccess*>(e)) return ThroughPointer(f->receiver);
        return false;
    }
    ```

=== "C#"

    ```csharp
    BoundExpression BindAssignment(AssignmentSyntax syntax, Scope scope)   // only as a whole statement
    {
        BoundExpression target = BindExpression(syntax.Target, scope);
        if (target.Type == TypeSymbol.Error) return new BoundError(syntax);
        BoundExpression value = BindExpression(syntax.Value, target.Type, scope);   // check: `x += 1` with x: u8 adds a u8
        Symbol? root = RootVariable(target);
        if (root is null && !ThroughPointer(target))                     // 1 = 2, f() = 3, (a + b) = c
        {
            diagnostics.Report(Diagnostics.NotAssignable, syntax.Target.Span);
            return new BoundError(syntax);
        }
        if (root is ParameterSymbol or LocalSymbol { IsMutable: false })
        {
            diagnostics.Report(Diagnostics.ImmutableAssignment, syntax.Target.Span, root.Name)
                       .WithRelated(root.Declaration!.Span, "declared here");
            return new BoundError(syntax);
        }
        if (syntax.Operator.Kind == SyntaxKind.EqualsToken) return new BoundAssignment(syntax, target, value);

        SyntaxKind arithmetic = syntax.Operator.Kind switch                    // += is +, -= is -, ...
        {
            SyntaxKind.PlusEqualsToken => SyntaxKind.PlusToken,
            SyntaxKind.MinusEqualsToken => SyntaxKind.MinusToken,
            SyntaxKind.StarEqualsToken => SyntaxKind.StarToken,
            SyntaxKind.SlashEqualsToken => SyntaxKind.SlashToken,
            _ => SyntaxKind.PercentToken,
        };
        BoundBinaryOperator? op = Operators.LookupBinary(arithmetic, target.Type, target.Type);
        if (op is null || value.Type == TypeSymbol.Error)
        {
            if (op is null) diagnostics.Report(Diagnostics.NoBinaryOperator, syntax.Operator.Span, Describe.Kind(syntax.Operator.Kind).Trim('\''),
                                               target.Type.ToString()!, target.Type.ToString()!);
            return new BoundError(syntax);
        }
        return new BoundCompoundAssignment(syntax, target, op, value);
    }

    static Symbol? RootVariable(BoundExpression e) => e switch   // x, x.a, x.a.b: the variable being changed
    {
        BoundVariable v => v.Symbol,
        BoundFieldAccess { Receiver: var r } when r.Type is StructType => RootVariable(r),
        _ => null,                                               // through a pointer (or not assignable)
    };

    static bool ThroughPointer(BoundExpression e) => e switch   // *p, p.x, (*p).a.b: changes memory, not a variable
    {
        BoundUnary { Operator: UnaryOperatorKind.Dereference } => true,
        BoundFieldAccess f => ThroughPointer(f.Receiver),
        _ => false,
    };
    ```

**Compound assignment.** The lexer reads `+=` as one token (longest match, as for `->`), and the parser treats it like `=`. The binder checks that the arithmetic operator exists for the target's type, and [lowering](lowering.md#desugaring) rewrites `x += e` as `x = x + e`. The target must be **evaluated once**: in `next(p).x += 1`, `next` must be called once, not twice. Lowering computes any pointer in the target into a temporary first:

=== "C++"

    ```cpp
    void LowerCompoundAssignment(const BoundExpressionStatement* statement, const BoundCompoundAssignment* c)
    {
        const BoundExpression* target = EvaluateAddressOnce(c->target);
        const BoundExpression* sum = Own<BoundBinary>(c->syntax, target, c->op, c->value);
        Emit<BoundExpressionStatement>(statement->syntax, Own<BoundAssignment>(c->syntax, target, sum));
    }

    const BoundExpression* EvaluateAddressOnce(const BoundExpression* target)
    {
        if (dynamic_cast<const BoundVariable*>(target)) return target;   // reading a variable twice has no side effects
        if (auto* f = dynamic_cast<const BoundFieldAccess*>(target))
            return Own<BoundFieldAccess>(f->syntax, EvaluateAddressOnce(f->receiver), f->field);
        auto* d = dynamic_cast<const BoundUnary*>(target);
        if (!d || d->op != UnaryOperatorKind::Dereference)
            throw std::logic_error("the binder only allows variables, fields, and dereferences");
        if (dynamic_cast<const BoundVariable*>(d->operand)) return target;
        // *(any pointer expression): compute the pointer once, into a temporary.
        const LocalSymbol* temp = Own<LocalSymbol>(std::format("temp_{}", ++labelCount_), d->syntax, d->operand->type, false);
        Emit<BoundLet>(d->syntax, temp, d->operand);
        return Own<BoundUnary>(d->syntax, UnaryOperatorKind::Dereference, Own<BoundVariable>(d->syntax, temp, temp->type), d->type);
    }
    ```

=== "C#"

    ```csharp
    void LowerCompoundAssignment(BoundExpressionStatement statement, BoundCompoundAssignment c)
    {
        BoundExpression target = EvaluateAddressOnce(c.Target);
        var sum = new BoundBinary(c.Syntax, target, c.Operator, c.Value);
        _output.Add(new BoundExpressionStatement(statement.Syntax, new BoundAssignment(c.Syntax, target, sum)));
    }

    BoundExpression EvaluateAddressOnce(BoundExpression target)
    {
        switch (target)
        {
            case BoundVariable:                                         // reading a variable twice has no side effects
            case BoundUnary { Operator: UnaryOperatorKind.Dereference, Operand: BoundVariable }:
                return target;
            case BoundFieldAccess f:
                return new BoundFieldAccess(f.Syntax, EvaluateAddressOnce(f.Receiver), f.Field);
            case BoundUnary { Operator: UnaryOperatorKind.Dereference } d:          // *(any pointer expression)
                var temp = new LocalSymbol($"temp_{++_labelCount}", d.Syntax, d.Operand.Type, isMutable: false);
                _output.Add(new BoundLet(d.Syntax, temp, d.Operand));               // the pointer, computed once
                return new BoundUnary(d.Syntax, UnaryOperatorKind.Dereference, new BoundVariable(d.Syntax, temp), d.Type);
            default:
                throw new InvalidOperationException("the binder only allows variables, fields, and dereferences");
        }
    }
    ```

A plain variable, or a field of one, can safely appear twice: reading it has no side effects.

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
