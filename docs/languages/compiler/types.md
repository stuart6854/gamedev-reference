# Type checking and inference

The other half of the [binder](binding.md): every expression gets a type, every operation is checked against its operands, and local variables without a written type get one from their use. The rules here are for a statically typed language with **local** inference: function signatures are written out, and types inside a body are worked out.

## Representing types

```text
Type (abstract)

PrimitiveType   { kind: i8 | i16 | i32 | i64 | u8 | ... | f32 | f64 | bool | void }
StructType      { symbol: StructSymbol }
PointerType     { pointee: Type }
FunctionType    { parameters: Type[], return_type: Type }
ErrorType                                  // one instance
TypeVariable    { id, binding: Type? }     // only during inference; see below
```

- **Create each type once** and compare by reference. Primitives are singletons; constructed types like `*Vec2` come from a cache (`pointer_to(Vec2)` always returns the same object). Equality is then `a == b`.
- **Struct types are nominal**: two structs with the same fields are different types, because they are different symbols.
- Write a `display(type)` for messages that prints types as the user writes them: `*Vec2`, `fn(i32) -> f32`.

## Checking expressions

```text
bind_binary(expr, scope):
    // A literal takes its type from the other operand: in `length_sq(v) == 25.0`, 25.0 is an f32.
    if expr.right is a literal and expr.left is not:
        left = bind_expression(expr.left, scope)
        right = check(expr.right, left.type) if left.type is numeric else bind_expression(expr.right, scope)
    elif expr.left is a literal and expr.right is not:
        right = bind_expression(expr.right, scope)
        left = check(expr.left, right.type) if right.type is numeric else bind_expression(expr.left, scope)
    else:
        left = bind_expression(expr.left, scope)
        right = bind_expression(expr.right, scope)
    if left.type is ErrorType or right.type is ErrorType:
        return BoundError(expr)                             // already reported
    op = lookup_binary_operator(expr.operator, left.type, right.type)
    if op is nothing:
        report(no_operator(expr.operator_token.span, expr.operator, left.type, right.type))
        return BoundError(expr)
    return BoundBinary(convert(left, op.left_type), op, convert(right, op.right_type))

lookup_binary_operator(token, l, r):
    // a table: (token, left type, right type) -> (operator kind, left type, right type, result type)
    //   (+, i32, i32)   -> (IntAdd,     i32, i32, i32)
    //   (+, f32, f32)   -> (FloatAdd,   f32, f32, f32)
    //   (<, i32, i32)   -> (IntLess,    i32, i32, bool)
    //   (==, bool, bool) -> (BoolEquals, bool, bool, bool)
    //   (&&, bool, bool) -> (LogicalAnd, bool, bool, bool)
```

The same pattern covers everything else:

| Construct | Check |
| --- | --- |
| `if` / `while` condition | convertible to `bool` |
| call `f(a, b)` | `f` is a function; argument count matches; each argument converts to its parameter type; result is the return type |
| `a.x` | `a` is a struct (or a pointer to one, if `.` auto-dereferences); `x` is one of its fields |
| `Vec2 { x: .., y: .. }` | every field given exactly once; each value converts to the field's type |
| `x = v` | `x` is assignable (a mutable local, a field of one, or `*p`); `v` converts to its type |
| `return v` | `v` converts to the function's return type; `return;` only in a `void` function |
| `e as T` | the conversion from `e`'s type to `T` is an allowed explicit one |

### Conversions

Decide which conversions happen **implicitly** and which need `as`. A strict default suits a systems language:

| From → to | Implicit | Explicit (`as`) |
| --- | --- | --- |
| same type | yes | yes |
| integer → wider integer of the same signedness | yes | yes |
| integer → narrower, or signed ↔ unsigned | no | yes (truncates or reinterprets) |
| integer ↔ float | no | yes |
| `f32` → `f64` | yes | yes |
| anything → `bool` | no | no: write `x != 0` |

```text
convert(expr, target):                              // implicit only
    if expr.type is ErrorType or target is ErrorType: return expr
    if expr.type == target: return expr
    if implicit_conversion_exists(expr.type, target): return BoundConversion(expr, target)
    report(type_mismatch(expr.syntax.span, expected = target, found = expr.type))
    return BoundError(expr.syntax)
```

### Literals

An integer literal like `300` has no type of its own until its context gives it one. Simple and predictable rules:

- With an expected type (`let x: u8 = 300;`, or an argument to an `i64` parameter), the literal takes that type, and a value that does not fit is an error: "literal 300 does not fit in 'u8'".
- Without one (`let x = 300;`), integers default to `i32` and floats to `f64` (or `f32`, for a game language; pick one and document it).
- In a binary operation, a literal takes the **other operand's** type: `x + 1` with `x: u8` adds two `u8`s, and `length_sq(v) == 25.0` compares two `f32`s. Without this rule, the example program would fail to type-check, because an `f32` and a default `f64` literal have no common `==` operator.
- This needs the expected type passed **down** into the expression, which is what bidirectional checking does.

## Bidirectional checking

Two modes, instead of one:

```text
synthesize(expr) -> type           // work the type out from the expression alone: names, calls, operators
check(expr, expected)              // the type is known; check the expression against it
```

```text
check(expr, expected):
    switch expr:
        IntLiteral:    if fits(expr.value, expected) and expected is an integer type: give it expected
                       elif expected is a float type: give it expected        // `let x: f32 = 1;`
                       else: report and return error
        FloatLiteral:  if expected is a float type: give it expected
                       else: convert(synthesize(expr), expected)       // reports f64 vs i32
        StructLiteral: check each field value against the field's type
        If expression: check both branches against expected
        default:       convert(synthesize(expr), expected)
```

`let x: u8 = 300;` calls `check(300, u8)`. A call argument is checked against its parameter type. A `return` value is checked against the return type. Only where nothing is expected, as in `let x = 300;`, does the binder synthesize and use the defaults. For local inference this is usually all you need, and its errors are easy to explain because each one happens in one place.

## Inference with type variables

Bidirectional checking cannot type `var total;` followed later by `total = 0.5;`, or a generic function's arguments. For those, give unknown types a **type variable** and solve constraints by **unification**:

```text
fresh() = TypeVariable(next_id++, binding = nothing)

resolve(t):                                        // follow bindings to the current answer
    while t is TypeVariable and t.binding: t = t.binding
    return t

unify(a, b, span):                                 // make a and b the same type, or report
    a = resolve(a), b = resolve(b)
    if a == b: return
    if a is TypeVariable:
        if occurs(a, b): report(infinite_type(span)); return
        a.binding = b; return
    if b is TypeVariable: return unify(b, a, span)
    if a is PointerType and b is PointerType: return unify(a.pointee, b.pointee, span)
    if a is FunctionType and b is FunctionType and same arity:
        for (p, q) in zip(a.parameters, b.parameters): unify(p, q, span)
        return unify(a.return_type, b.return_type, span)
    report(type_mismatch(span, a, b))
```

```text
var total;                 // total: T1
total = 0;                 // unify(T1, {integer literal}) — see below
total = total + 1;         // operands unify with T1
return total;              // unify(T1, i32): T1 = i32
```

- **Literals** get a type variable restricted to "some integer" (or "some float"). Unifying it with `i32` binds it; if nothing binds it by the end of the function, apply the default.
- **Solve per function.** After binding a body, resolve every type variable. Any left unbound and unrestricted is "cannot infer the type of 'x'; add a type annotation", reported at the declaration.
- **Overloaded operators** need a known type to pick an operator. Record them as pending, and pick once the types are resolved.
- This is the core of **Hindley-Milner** inference. Full HM adds **generalisation** (inferring generic functions); with written signatures and local inference, you do not need it.

## The error type

When an expression fails to type-check, give it the **error type** and report once:

- The error type converts to and from everything, without a message.
- Any operation with an error-typed operand returns an error type without reporting.
- A local whose initialiser has the error type gets the error type, so its later uses stay quiet too.

Without this, one misspelt name produces a cascade: the binary operator fails, the call it is an argument to fails, the assignment fails.

## Generics later

When generics arrive:

- **Type parameters** are another kind of type (`TypeParameter { name, constraints }`), declared in the function's scope.
- At each call, give each type parameter a fresh type variable and unify parameter types with argument types, which infers `T` from `max(3, 4)`.
- Check the body once, against the type parameters and their constraints, not once per use, so errors are about the generic code, not its instantiations.
- **Monomorphise** in code generation: one LLVM function per distinct set of type arguments, as in [language design](../design.md#type-systems).

## C# tips

- Model types as `sealed class`es under `abstract class TypeSymbol`, with private constructors and static factories that cache: `TypeSymbol.Pointer(Vec2)` looks up a `Dictionary<TypeSymbol, PointerType>`.
- Put primitive types in static readonly fields (`TypeSymbol.I32`, `TypeSymbol.Error`), so checks read as `if (type == TypeSymbol.Bool)`.
- Keep the operator table as data: an array of `BoundBinaryOperator` records (`SyntaxKind`, `Kind`, `Left`, `Right`, `Result`), searched linearly. It is short, and adding an operator is one line.
- `ToString()` on each type should return the display form, so it appears correctly in the debugger and in messages.
- Literal values: the lexer stores them as `ulong` or `double`. Range-check with `value <= (ulong)sbyte.MaxValue` and similar for each target type, then store the checked value in the bound literal as a `long` (integers) or `double` (floats), which is what [code generation](llvmsharp.md#expressions) expects. A negative literal is a unary minus applied to a positive one, so `-128` as an `i8` needs the check to look at the negation; fold the two into one constant once the check passes.
