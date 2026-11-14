# Reference evaluator

A small interpreter that runs the bound program directly, without LLVM. It is the first backend to write (step 1 of the [order of work](index.md#order-of-work)), and stays useful after code generation works:

- **A test oracle.** Every end-to-end case runs through the evaluator and the compiled code, and their results must match ([differential testing](testing.md#differential-testing)).
- **Compile-time evaluation.** `const` values, array sizes, and compile-time function calls run in the evaluator.
- **A REPL and quick experiments**, before the JIT exists, and on machines without LLVM.

It is not meant to be fast. It is meant to be **obviously correct**: simple enough that when it disagrees with the compiled code, the compiled code is the suspect.

## What it runs

Run the **lowered** program: flat statement lists with labels and gotos, the same input the [code generator](llvmsharp.md) gets. Then both backends share the binder and the lowering, and a disagreement points straight at code generation. (A separate evaluator over the unlowered bound tree is useful for testing the lowering itself.)

## Values

```text
Value =
    Int(bits: i64)              // every integer type; the type says how to read the bits
    Float(value: f64)           // f32 values are rounded to f32 after every operation
    Bool(value)
    Struct(fields: Value[])     // copied on assignment: value semantics
    Pointer(target: Slot)       // a reference to a local, a field, or an element
    Void
```

```text
normalise(bits, type):          // after every integer operation, keep only the type's bits
    if type.size == 64: return bits
    mask = (1 << type.size) - 1
    bits = bits & mask
    if type.is_signed and bits has bit (type.size - 1) set: bits -= (1 << type.size)    // sign-extend
    return bits
```

Normalising after every operation gives the **same wrap-around** as LLVM's `add` on an `i8`: `normalise(127 + 1, i8)` is −128. Unsigned 64-bit values keep their bits in the `i64`; comparisons and division on them must reinterpret the bits as unsigned.

## The loop

```text
call(function, arguments):
    if function is extern: return host_functions[function.name](arguments)
    frame = { locals: map Symbol -> Value }
    for (p, a) in zip(function.parameters, arguments): frame.locals[p] = a
    body = lowered statements of function
    labels = { statement.label: index for each Label statement in body }

    pc = 0
    steps = 0
    while pc < len(body):
        steps += 1
        if steps > STEP_LIMIT: panic("evaluation did not finish")       // a test must not hang
        s = body[pc]
        switch s:
            Label:            pc += 1
            Goto g:           pc = labels[g.label]
            ConditionalGoto g:
                c = eval(g.condition, frame)
                pc = labels[g.label] if c == g.jump_if_true else pc + 1
            Return r:         return eval(r.expression, frame) if r.expression else Void
            ExpressionStatement e: eval(e.expression, frame); pc += 1
    return Void

eval(expr, frame):
    switch expr:
        Literal l:        return l.value
        Variable v:       return frame.locals[v.symbol]
        Assignment a:     value = eval(a.value, frame); store(a.target, value, frame); return value
        Binary b:         return apply(b.operator, eval(b.left, frame), eval(b.right, frame))
        Unary u:          return apply(u.operator, eval(u.operand, frame))
        Conversion c:     return convert(eval(c.operand, frame), c.operand.type, c.type)
        Call c:           return call(c.function, [eval(a, frame) for a in c.arguments])
        FieldAccess f:    return eval(f.receiver, frame).fields[f.field.index]
```

- **Recursion depth**: count calls and panic past a limit, rather than overflow the host's stack on a runaway recursive test.
- **Host functions**: `putchar`, `print`, and engine functions are a table from name to a host implementation, so programs that call C still run in the evaluator. Record their output for tests to compare.
- **Struct values are copied** on assignment and when passed, so changing a copy never changes the original, matching the compiled code's value semantics.

## Matching the compiled semantics

The evaluator is only an oracle if it has the language's semantics, not the host's:

| Rule | Evaluator must |
| --- | --- |
| Integer overflow | normalise after every operation (wrap), or panic where the language traps |
| Division by zero, `MIN / -1` | panic with the same message as the compiled check |
| Shift by ≥ the bit width | apply the same masking or panic |
| Float to integer | saturate, with NaN as 0, exactly as `fptosi.sat` (see [numeric conversions](numeric-conversions.md#float-to-integer)) |
| `f32` arithmetic | round to `f32` after each operation, not only at the end |
| Bounds checks | panic with the same message |
| Evaluation order | left to right, as the compiled code |

Panics are a **result**, not a crash: the evaluator returns "panicked with message M at line L", and the compiled program's stderr and exit code must say the same.

## Compile-time evaluation

The same evaluator runs during binding for anything the language requires to be constant:

- `const N = 4 * 1024;` evaluates the initialiser and records the value on the symbol.
- Array lengths (`[N]f32`) and attribute arguments are evaluated the same way.
- Calling ordinary functions at compile time (`const TABLE = build_table();`) works for free, provided they only call functions the evaluator can run: no `extern` C calls unless the host table has them.

Limit steps and recursion strictly here: a compile-time loop that never ends must be a compile error, not a hung compiler.

## C# tips

- Represent `Value` as a small `readonly record struct` with a kind and a `long`/`double` payload, plus a `Value[]?` for structs. Most programs then evaluate without allocating.
- `normalise` in C#: `type.SizeInBits switch { 8 => type.IsSigned ? (sbyte)bits : (byte)bits, 16 => ..., 32 => type.IsSigned ? (int)bits : (uint)bits, _ => bits }`. Casts between integer types truncate in C#'s default `unchecked` context, which is exactly the masking above.
- For `f32` semantics, do the arithmetic in `float` (`(float)a + (float)b`), not in `double` with one rounding at the end.
- C#'s `(int)someFloat` saturates on .NET 9 and later, but conversions to smaller types do not; see the [C# tips on numeric conversions](numeric-conversions.md#c-tips).
- Throw a dedicated `EvaluationPanic` exception carrying the message and the syntax location, and catch it at the top of the evaluation, so a panic deep in a call stack unwinds cleanly.
