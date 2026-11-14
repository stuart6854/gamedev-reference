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

```text
Parser { tokens, pos, diagnostics }

current       = tokens[pos]
peek(k)       = tokens[min(pos + k, len(tokens) - 1)]     // never past EndOfFile
at(kind)      = current.kind == kind

advance():
    token = current
    if token.kind != EndOfFile: pos += 1
    return token

eat(kind):                       // optional token
    if at(kind): return advance()
    return nothing

expect(kind):                    // required token
    if at(kind): return advance()
    report(expected(kind, found = current), at = end of the previous token)
    return missing_token(kind)   // zero-length token: the tree stays complete
```

`expect` never fails. It reports and returns a **missing token**, so `parse_let` can always build a `Let` node. Report at the end of the previous token, not at the next one, which may be on the next line.

## Items and statements

```text
parse_file():
    items = []
    while not at(EndOfFile):
        start = pos
        items.append(parse_item())
        if pos == start: skip_bad_token()            // always make progress
    return File(items, expect(EndOfFile))

parse_function():
    fn_kw  = expect(Fn)
    name   = expect(Identifier)
    open   = expect(OpenParen)
    params = parse_separated(parse_param, Comma, until = CloseParen)
    close  = expect(CloseParen)
    ret    = (eat(Arrow), parse_type()) if at(Arrow) else nothing
    body   = parse_block()
    return Function(fn_kw, name, open, params, close, ret, body)

parse_separated(parse_one, separator, until):
    items = []
    while not at(until) and not at(EndOfFile):
        start = pos
        items.append(parse_one())
        if not eat(separator): break                 // trailing separator allowed: loop sees `until`
        if pos == start: break
    return items

parse_block():
    open = expect(OpenBrace)
    statements = []
    while not at(CloseBrace) and not at(EndOfFile):
        start = pos
        statements.append(parse_statement())
        if pos == start: skip_bad_token()
    return Block(open, statements, expect(CloseBrace))

parse_statement():
    switch current.kind:
        Let:       return parse_let()
        Var:       return parse_var()
        Return:    return parse_return()
        If:        return parse_if()
        While:     return parse_while()
        OpenBrace: return parse_block()
        default:   return ExpressionStatement(parse_expression(), expect(Semicolon))

parse_if():
    if_kw = expect(If)
    condition = parse_expression(no_struct_literal = true)    // see below
    then = parse_block()
    else_clause = nothing
    if at(Else):
        else_kw = advance()
        else_clause = Else(else_kw, parse_if() if at(If) else parse_block())
    return If(if_kw, condition, then, else_clause)
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

```text
parse_expression(min_power = 0):
    left = parse_prefix()
    loop:
        op = current.kind
        if op is postfix:
            if postfix_power(op) < min_power: break
            left = parse_postfix(left)              // call, member access
            continue
        if op is not infix: break
        (lp, rp) = infix_power(op)
        if lp < min_power: break
        advance()
        if op == As:                                // the right side is a type, not an expression
            left = Cast(left, parse_type())
            continue
        right = parse_expression(rp)
        left = Binary(left, op, right)
        if op is non-associative and current.kind has the same precedence:
            report(chained_comparison(current.span))
    return left

parse_prefix():
    switch current.kind:
        IntLiteral, FloatLiteral, StringLiteral, True, False:
            return Literal(advance())
        Identifier:
            name = advance()
            if at(OpenBrace) and struct literals are allowed here:
                return parse_struct_literal(name)
            return Name(name)
        OpenParen:
            open = advance()
            inner = parse_expression()               // struct literals allowed again inside parentheses
            return Parenthesized(open, inner, expect(CloseParen))
        Minus, Bang, Star, Ampersand:
            op = advance()
            return Unary(op, parse_expression(17))
        default:
            report(expected_expression(current.span))
            return MissingExpression(at = current.span.start)   // do not consume: the caller decides

parse_postfix(left):
    if at(OpenParen):
        open = advance()
        args = parse_separated(parse_expression, Comma, until = CloseParen)
        return Call(left, open, args, expect(CloseParen))
    if at(Dot):
        dot = advance()
        return Member(left, dot, expect(Identifier))
```

### The struct literal ambiguity

`if v == origin { ... }` could be a comparison followed by a block, or a comparison with a struct literal `origin { ... }`. Rust's rule is simple and works: **struct literals are not allowed directly in the condition of `if` or `while`**. Inside parentheses they are fine again: `if v == (Vec2 { x: 0.0, y: 0.0 }) { ... }`. Pass a flag down through `parse_expression`, and reset it inside parentheses and argument lists.

### Generics and `<`

`a < b > (c)` is a comparison chain, or a call to a generic `a<b>` with argument `c`. Avoid the question when you add generics: use a syntax that is not ambiguous (`f[T](x)`, or `f::<T>(x)` as in Rust), or only allow `<` after a name in **type** position, where comparisons cannot appear.

## Error recovery

The aim is to report the first real error in each statement, then carry on as if the code were correct.

- **Missing tokens** come from `expect`, which inserts one and moves on. `let x = 5` followed by a new line gets "expected ';'" and a complete `Let` node.
- **Unexpected tokens** are skipped until a **synchronisation point**: a token that can start an item or statement (`fn`, `struct`, `let`, `var`, `if`, `while`, `return`), or a closing `}`. The skipped tokens go into the tree as **skipped trivia** or a `Bad` node, so the text is still covered.

```text
skip_bad_token():
    bad_start = current
    report(unexpected_token(current))               // once per run of bad tokens
    while not at(EndOfFile) and not starts_statement_or_item(current) and not at(CloseBrace):
        advance()
    record skipped tokens on the next node, or in a BadStatement(bad_start .. previous)
```

- **Always make progress.** Every loop over a list (items, statements, arguments) records `pos` at the top and skips a token if it did not move. A parser that can loop forever on one bad token will, the first time someone types into an editor.
- **Do not report at a missing node twice.** `parse_prefix` returns a `MissingExpression` without consuming anything, and the statement that follows reports nothing more about it.
- **Delimiters guide recovery.** On an error inside parentheses or braces, skip to the matching closer rather than to the next keyword, counting nesting as you go.

## More tips

**Design the grammar for one-token decisions.** If every statement and item starts with a distinct token (`let`, `fn`, `if`), the parser decides with `current.kind` alone. Each construct that needs more look-ahead is a place where parsing, error recovery, and error messages get harder.

**Look-ahead before backtracking.** Where one token is not enough, look further without consuming: `peek(1).kind == Colon` tells a named argument `f(x: 1)` from an expression. Fixed look-ahead keeps the parser linear.

**Speculative parsing, when unavoidable.** For a genuine ambiguity (a generic call `f<T>(x)` if you chose that syntax), save the position and the diagnostic count, try one parse, and rewind if it fails:

```text
try_parse(parse_fn):
    saved_pos = pos, saved_errors = len(diagnostics)
    result = parse_fn()
    if len(diagnostics) > saved_errors:          // it did not fit: undo everything
        pos = saved_pos
        truncate diagnostics to saved_errors
        return nothing
    return result
```

Keep this to one or two places; nested speculation can take exponential time.

**"Expected one of" messages.** Record each token kind tested with `at()` since the last token was consumed. When parsing fails, that set is exactly what would have been valid: "expected ',' or ')' after the argument". Clear it on `advance()`.

**Separate parsers for types and expressions.** `parse_type` and `parse_expression` should be different functions, called where each is expected. C-style casts (`(T)x`) need both at once and are ambiguous with parenthesised expressions; `x as T` avoids the problem.

**Leave semantics to the binder.** The parser should accept `5;` or `a + b;` as expression statements; "this expression has no effect" is a binder warning. A parser that rejects things it could parse produces worse messages and recovers worse.

**Attributes and doc comments.** Parse `#[...]` attributes into a list attached to the next item, and keep `///` doc comments as trivia on that item's first token. Both then reach the binder with the item they describe.

**Trailing separators everywhere.** Allow a trailing comma in every comma-separated list (parameters, arguments, fields, struct literals). It makes diffs one line shorter and generated code simpler, and `parse_separated` handles it already.

**Test precedence exhaustively.** For every pair of binary operators, parse `a op1 b op2 c` and check the grouping against the precedence table. It is a few lines of test code and catches every table mistake.

## C# tips

- Make the parser a class over `ImmutableArray<Token>` with an `int _position`. `Current`, `Peek(int)`, `NextToken()`, and `MatchToken(SyntaxKind)` are each one line.
- Put precedences in two `switch` expressions (`GetBinaryPower(SyntaxKind) => (int Left, int Right)` and `GetUnaryPower`), next to each other, so the table above is visible in the code.
- `parse_separated` returns a `SeparatedSyntaxList<T>` that keeps the separators as well as the items: a formatter and the language server's signature help both need the commas.
- Recursion depth follows nesting depth. Deeply nested input (a generated 10,000-term expression) can overflow the stack: count depth in `ParseExpression` and report "expression too deeply nested" past a limit, rather than crash. `RuntimeHelpers.EnsureSufficientExecutionStack()` throws a catchable exception instead of a crash.
- Return `null` from no parse function. Missing pieces are `MissingExpression` or missing tokens, so later stages never need null checks for broken input.
