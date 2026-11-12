# Names, scopes, and symbols

The **binder** connects every name in the syntax tree to what it names, and builds a **bound tree**: the program with names replaced by symbols and every expression given a type. This page is the names half; [type checking and inference](types.md) is the types half. They run in the same walk. [Language design](../design.md#name-resolution-and-scoping) covers the scoping rules a language can choose; this is how to implement them.

## Symbols

A **symbol** is one declared thing. Every use of a name in the bound tree points at a symbol, never at a string.

```text
Symbol (abstract) { name, declaration (syntax node, for errors and go-to-definition) }

FunctionSymbol  : Symbol { parameters: ParameterSymbol[], return_type, is_extern, body (bound, filled in later) }
ParameterSymbol : Symbol { type, index }
LocalSymbol     : Symbol { type, is_mutable }
StructSymbol    : Symbol { fields: FieldSymbol[] }   // also a type: see the types page
FieldSymbol     : Symbol { type, index }
```

Two locals called `i` in different loops are two symbols. Later stages (lowering, code generation) work only with symbols, so they never have to think about scopes or shadowing again.

## Scopes

A **scope** maps names to symbols, and has a parent:

```text
Scope { parent, symbols: map name -> Symbol }

declare(scope, symbol):
    if symbol.name in scope.symbols:
        report(duplicate_definition(symbol.declaration, previous = scope.symbols[symbol.name].declaration))
        return false
    scope.symbols[symbol.name] = symbol
    return true

lookup(scope, name):
    while scope:
        if name in scope.symbols: return scope.symbols[name]
        scope = scope.parent
    return nothing
```

The chain for code inside a function body:

```text
global scope         // structs, functions, externs, built-in types (i32, f32, bool)
  └─ function scope  // parameters
       └─ block      // locals of the outer block
            └─ block // locals of a nested block or loop body
```

- **Built-in types live in an outer scope** like any other symbol, so a user `struct i32` gives an ordinary duplicate error, and lookup needs no special cases.
- **Types and values** can share one namespace (simpler: `Vec2` cannot also be a function) or have two (C-style). One namespace makes struct literals and calls easier to parse and bind.
- **Shadowing**: allowing an inner `let x` to hide an outer `x` means `declare` only checks the current scope. To forbid shadowing inside a function, also walk the parents up to the function scope.

## Binding in passes

Functions and structs can be used before they are declared, and can refer to each other. One walk in source order cannot handle that. Bind in passes, each over all files:

```text
bind_program(files):
    // 1. Declare: every struct, function, and extern gets a symbol. Nothing is resolved yet.
    for item in all items: declare(global, new symbol for item)

    // 2. Resolve signatures: field types, parameter types, return types.
    for s in structs: s.fields = [FieldSymbol(f.name, bind_type(f.type), i) for i, f in s.syntax.fields]
    for f in functions and externs:
        f.parameters = [ParameterSymbol(p.name, bind_type(p.type), i) for i, p in f.syntax.params]
        f.return_type = bind_type(f.syntax.return_type) if present else void

    check_struct_cycles(structs)          // struct A { b: B } struct B { a: A } has infinite size

    // 3. Bind bodies: now every signature is known, in any order.
    for f in functions: f.body = bind_function_body(f)

    check_entry_point(global)             // `main` exists and has the expected signature
```

```text
bind_function_body(f):
    scope = Scope(parent = global)
    for p in f.parameters: declare(scope, p)
    return bind_block(f.syntax.body, scope)

bind_block(block, parent):
    scope = Scope(parent)
    return BoundBlock([bind_statement(s, scope) for s in block.statements])

bind_let(stmt, scope):
    initializer = bind_expression(stmt.initializer, scope)       // before declaring: `let x = x;` uses the outer x
    type = bind_type(stmt.type) if stmt.type else initializer.type
    local = LocalSymbol(stmt.name, type, is_mutable = stmt is var)
    declare(scope, local)
    return BoundLet(local, convert(initializer, type))

bind_name(expr, scope):
    symbol = lookup(scope, expr.name)
    if symbol is nothing:
        report(undefined_name(expr.span, expr.name, suggestion = closest name in scope))
        return BoundError(expr)
    if symbol is LocalSymbol or ParameterSymbol: return BoundVariable(symbol)
    if symbol is FunctionSymbol: return BoundFunctionReference(symbol)
    report(not_a_value(expr.span, symbol))                         // e.g. a struct name used as a value
    return BoundError(expr)
```

- **Declare locals after binding their initialiser**, so `let x = x + 1;` refers to an outer `x` (or is an error), never to itself.
- **Assignment checks mutability**: assigning to a `let` local or a parameter reports "cannot assign to immutable 'x'", pointing at the declaration as a related location.
- **Struct cycles**: walk field types depth-first and report a cycle unless it goes through a pointer. Without the check, code generation loops forever computing the size.

## The bound tree

The bound tree is the syntax tree's meaning, with everything later stages need and nothing they do not:

```text
BoundExpression { type }

BoundLiteral          { value }
BoundVariable         { symbol: LocalSymbol | ParameterSymbol }
BoundBinary           { left, operator: BoundBinaryOperator, right }      // the operator knows its operand and result types
BoundCall             { function: FunctionSymbol, arguments }
BoundFieldAccess      { receiver, field: FieldSymbol }
BoundConversion       { operand, to_type }                                // implicit conversions made explicit
BoundAssignment       { target: BoundExpression, value }
BoundError            { syntax }                                           // type is the error type

BoundStatement: BoundLet, BoundExpressionStatement, BoundReturn, BoundIf, BoundWhile, BoundBlock
```

- Each bound node keeps a reference to its **syntax**, for error spans in later stages and for debug info.
- **Conversions are nodes.** An `i32` widened to `i64`, or a literal given a type, becomes a `BoundConversion`, so code generation never has to work out an implicit conversion.
- **Operators are resolved**: `BoundBinaryOperator` says "signed 32-bit add" or "float compare less-than", not just `+`.

## Modules and imports

Once there is more than one file with its own namespace:

- Give each module its own scope under the global one, and an `import` adds the imported module's public symbols (or the module's name, for `math.sqrt`) to the importing scope.
- Run pass 1 for **every module** before pass 2 for any, so imports in both directions work.
- Report import cycles, or define an order for running modules' global initialisers, before allowing them.

## C# tips

- Make symbols `sealed class`es under `abstract class Symbol`, and fill in the parts known later (a function's body, a struct's fields) through `internal` setters used only by the binder. Everything after the binder treats them as read-only.
- A `Scope` is a `Dictionary<string, Symbol>` plus a `Scope? Parent`. Allocating one per block is fine: they are small and short-lived.
- For "did you mean" suggestions, compute the edit distance (Levenshtein, or Damerau-Levenshtein for swapped letters) against names visible from the scope, and suggest only when the distance is at most a third of the name's length.
- Keep the binder's output in a `BoundProgram` record: the global scope, the function bodies (`ImmutableDictionary<FunctionSymbol, BoundBlock>`), and the diagnostics.
- An editor needs the reverse map too: from a syntax node to its symbol, for hover and go-to-definition. Record it in a `Dictionary<SyntaxNode, Symbol>` while binding, rather than recomputing it.
