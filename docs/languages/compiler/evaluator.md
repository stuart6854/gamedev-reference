# Reference evaluator

A small interpreter that runs the bound program directly, without LLVM. It is the first backend to write (step 1 of the [order of work](index.md#order-of-work)), and stays useful after code generation works:

- **A test oracle.** Every end-to-end case runs through the evaluator and the compiled code, and their results must match ([differential testing](testing.md#differential-testing)).
- **Compile-time evaluation.** `const` values, array sizes, and compile-time function calls run in the evaluator.
- **A REPL and quick experiments**, before the JIT exists, and on machines without LLVM.

It is not meant to be fast. It is meant to be **obviously correct**: simple enough that when it disagrees with the compiled code, the compiled code is the suspect.

## What it runs

Run the **lowered** program: flat statement lists with labels and gotos, the same input the [code generator](llvmsharp.md) gets. Then both backends share the binder and the lowering, and a disagreement points straight at code generation. (A separate evaluator over the unlowered bound tree is useful for testing the lowering itself.)

## Values

=== "C++"

    ```cpp
    struct Value
    {
        enum class Kind : uint8_t { Void, Int, Float, Bool, Struct, Pointer };
        Kind kind = Kind::Void;
        int64_t bits = 0;               // Int: every integer type; the type says how to read the bits. Bool: 0 or 1
        double number = 0;              // Float: f32 values are rounded to f32 after every operation
        std::vector<Value> fields = {}; // Struct: copied with the value, so assignment copies it
        Slot* target = nullptr;         // Pointer: a local, or a field in one
        std::vector<int> path = {};

        static Value Int(int64_t bits) { return { .kind = Kind::Int, .bits = bits }; }
        static Value Float(double number) { return { .kind = Kind::Float, .number = number }; }
        static Value Bool(bool b) { return { .kind = Kind::Bool, .bits = b }; }
        static Value Struct(std::vector<Value> fields) { return { .kind = Kind::Struct, .fields = std::move(fields) }; }
        static Value Pointer(Slot* target, std::vector<int> path) { return { .kind = Kind::Pointer, .target = target, .path = std::move(path) }; }
    };

    struct Slot { Value value; };       // a local's storage: pointers refer to it
    ```

=== "C#"

    ```csharp
    public sealed class Slot                               // a local's storage: pointers refer to it
    {
        public Value Value;
    }

    public readonly record struct Value(ValueKind Kind, long Bits = 0, double Float = 0, Value[]? Fields = null, Slot? Target = null, int[]? Path = null)
    {
        public static readonly Value Void = new(ValueKind.Void);
        public static Value Int(long bits) => new(ValueKind.Int, Bits: bits);   // every integer type; the type says how to read the bits
        public static Value FromFloat(double value) => new(ValueKind.Float, Float: value);   // f32 values are rounded after every operation
        public static Value FromBool(bool value) => new(ValueKind.Bool, Bits: value ? 1 : 0);
        public static Value Struct(Value[] fields) => new(ValueKind.Struct, Fields: fields);
        public static Value Pointer(Slot target, int[] path) => new(ValueKind.Pointer, Target: target, Path: path);   // a local, or a field in one

        public bool AsBool => Bits != 0;
        public Value Copy() => Kind == ValueKind.Struct ? Struct([.. Fields!.Select(f => f.Copy())]) : this;   // value semantics
    }
    ```

Integer values are cut down to their type's width after every operation:

=== "C++"

    ```cpp
    // After every integer operation, keep only the type's bits.
    int64_t Normalise(int64_t bits, const PrimitiveType* type)
    {
        if (type->bits == 64) return bits;
        uint64_t mask = (uint64_t(1) << type->bits) - 1;
        uint64_t value = uint64_t(bits) & mask;
        if (type->IsSigned() && (value >> (type->bits - 1)) & 1) value |= ~mask;   // sign-extend
        return int64_t(value);
    }
    ```

=== "C#"

    ```csharp
    // After every integer operation, keep only the type's bits. Casts truncate in an unchecked context, which is the masking.
    public static long Normalise(long bits, PrimitiveType type) => unchecked(type.Bits switch
    {
        8 => type.IsSigned ? (sbyte)bits : (byte)bits,
        16 => type.IsSigned ? (short)bits : (ushort)bits,
        32 => type.IsSigned ? (int)bits : (uint)bits,
        _ => bits,
    });
    ```

Normalising after every operation gives the **same wrap-around** as LLVM's `add` on an `i8`: `Normalise(127 + 1, i8)` is −128. Unsigned 64-bit values keep their bits in the `i64`; comparisons and division on them must reinterpret the bits as unsigned.

## The loop

=== "C++"

    ```cpp
    using Frame = std::unordered_map<const Symbol*, std::unique_ptr<Slot>>;

    Value Call(const FunctionSymbol* function, const std::vector<Value>& arguments, TextSpan at = {})
    {
        if (function->isExtern) return hostFunctions_.at(function->name)(arguments);   // putchar, print, engine functions
        if (++depth_ > kDepthLimit) throw EvaluationPanic("recursion too deep", at);
        std::unordered_map<const Symbol*, std::unique_ptr<Slot>> frame;   // unique_ptr: pointers to slots stay valid
        for (size_t i = 0; i < arguments.size(); i++)
            frame[function->parameters[i]] = std::make_unique<Slot>(arguments[i]);

        const std::vector<const BoundStatement*>& body = bodies_.at(function).body;
        std::unordered_map<const BoundLabel*, size_t> labels;
        for (size_t i = 0; i < body.size(); i++)
            if (auto* l = dynamic_cast<const BoundLabelStatement*>(body[i])) labels[l->label] = i;

        size_t pc = 0;
        while (pc < body.size())
        {
            const BoundStatement* s = body[pc];
            if (++steps_ > kStepLimit) throw EvaluationPanic("evaluation did not finish", s->syntax->Span());   // a test must not hang
            if (dynamic_cast<const BoundLabelStatement*>(s)) pc++;
            else if (auto* g = dynamic_cast<const BoundGoto*>(s)) pc = labels.at(g->label);
            else if (auto* c = dynamic_cast<const BoundConditionalGoto*>(s))
                pc = (Eval(c->condition, frame).bits != 0) == c->jumpIfTrue ? labels.at(c->label) : pc + 1;
            else if (auto* let = dynamic_cast<const BoundLet*>(s))
            {
                frame[let->local] = std::make_unique<Slot>(let->initializer ? Eval(let->initializer, frame) : Value{});
                pc++;
            }
            else if (auto* e = dynamic_cast<const BoundExpressionStatement*>(s)) { Eval(e->expression, frame); pc++; }
            else if (auto* r = dynamic_cast<const BoundReturn*>(s))
            {
                Value result = r->value ? Eval(r->value, frame) : Value{};
                depth_--;
                return result;
            }
        }
        depth_--;
        return {};
    }


    Value Eval(const BoundExpression* e, Frame& frame)
    {
        if (auto* v = dynamic_cast<const BoundVariable*>(e)) return frame.at(v->symbol)->value;   // a copy: structs too
        if (auto* a = dynamic_cast<const BoundAssignment*>(e))
        {
            Value value = Eval(a->value, frame);
            auto [slot, path] = Location(a->target, frame);  // a local, a field path in one, or through a pointer
            Store(slot, path, value);
            return value;
        }
        if (auto* b = dynamic_cast<const BoundBinary*>(e)) return EvalBinary(b, frame);
        if (auto* c = dynamic_cast<const BoundConversion*>(e)) return Convert(Eval(c->operand, frame), c->operand->type, c->type);
        if (auto* c = dynamic_cast<const BoundCall*>(e))
        {
            std::vector<Value> arguments;
            for (const BoundExpression* a : c->arguments) arguments.push_back(Eval(a, frame));   // left to right
            return Call(c->function, arguments, c->syntax->Span());
        }
        if (auto* f = dynamic_cast<const BoundFieldAccess*>(e)) return Eval(f->receiver, frame).fields[f->field->index];
        // ... literals, unary operators, struct literals
        throw std::logic_error("cannot evaluate this expression");
    }
    ```

=== "C#"

    ```csharp
    public Value Call(FunctionSymbol function, Value[] arguments, TextSpan at = default)
    {
        if (function.IsExtern) return hostFunctions[function.Name](arguments);   // putchar, print, engine functions
        if (++_depth > DepthLimit) throw new EvaluationPanic("recursion too deep", at);
        var frame = new Dictionary<Symbol, Slot>();
        for (int i = 0; i < arguments.Length; i++) frame[function.Parameters[i]] = new Slot { Value = arguments[i] };

        ImmutableArray<BoundStatement> body = bodies[function];
        var labels = new Dictionary<BoundLabel, int>();
        for (int i = 0; i < body.Length; i++)
            if (body[i] is BoundLabelStatement l) labels[l.Label] = i;

        int pc = 0;
        while (pc < body.Length)
        {
            if (++_steps > StepLimit) throw new EvaluationPanic("evaluation did not finish", body[pc].Syntax.Span);   // a test must not hang
            switch (body[pc])
            {
                case BoundLabelStatement:
                    pc++;
                    break;
                case BoundGoto g:
                    pc = labels[g.Label];
                    break;
                case BoundConditionalGoto g:
                    pc = Eval(g.Condition, frame).AsBool == g.JumpIfTrue ? labels[g.Label] : pc + 1;
                    break;
                case BoundLet l:
                    frame[l.Local] = new Slot { Value = l.Initializer is null ? Value.Void : Eval(l.Initializer, frame) };
                    pc++;
                    break;
                case BoundExpressionStatement e:
                    Eval(e.Expression, frame);
                    pc++;
                    break;
                case BoundReturn r:
                    _depth--;
                    return r.Value is null ? Value.Void : Eval(r.Value, frame);
            }
        }
        _depth--;
        return Value.Void;
    }


    Value Eval(BoundExpression e, Dictionary<Symbol, Slot> frame)
    {
        switch (e)
        {
            case BoundVariable v:
                return frame[v.Symbol].Value.Copy();         // a struct is copied when read
            case BoundAssignment a:
            {
                Value value = Eval(a.Value, frame);
                var (slot, path) = Location(a.Target, frame);  // a local, a field path in one, or through a pointer
                Store(slot, path, value.Copy());
                return value;
            }
            case BoundBinary b:
                return EvalBinary(b, frame);
            case BoundConversion c:
                return Convert(Eval(c.Operand, frame), c.Operand.Type, c.Type, c.Syntax.Span);
            case BoundCall c:
                return Call(c.Function, [.. c.Arguments.Select(a => Eval(a, frame))], c.Syntax.Span);   // left to right
            case BoundFieldAccess f:
                return Eval(f.Receiver, frame).Fields![f.Field.Index];
            // ... literals, unary operators, struct literals
            default:
                throw new InvalidOperationException($"cannot evaluate {e.GetType().Name}");
        }
    }
    ```

Binary operators carry the semantics: short circuits, unsigned comparisons, the division checks, and wrapping:

=== "C++"

    ```cpp
    Value EvalBinary(const BoundBinary* b, Frame& frame)
    {
        BinaryOperatorKind op = b->op->kind;
        Value left = Eval(b->left, frame);
        if (op == BinaryOperatorKind::LogicalAnd && !left.bits) return Value::Bool(false);   // b->right is not evaluated
        if (op == BinaryOperatorKind::LogicalOr && left.bits) return Value::Bool(true);
        Value right = Eval(b->right, frame);
        const Type* t = b->op->left;

        if (t == &Types::Bool)
        {
            if (op == BinaryOperatorKind::Equals) return Value::Bool(left.bits == right.bits);
            if (op == BinaryOperatorKind::NotEquals) return Value::Bool(left.bits != right.bits);
            return Value::Bool(right.bits);             // && and || after the short circuit
        }
        if (IsFloat(t))
        {
            if (t == &Types::F32)                       // f32 arithmetic in float, not double
                return FloatOp(op, float(left.number), float(right.number));
            return FloatOp(op, left.number, right.number);
        }

        auto* type = AsPrimitive(t);
        bool isSigned = type->IsSigned();
        int64_t l = left.bits, r = right.bits;
        uint64_t ul = uint64_t(l), ur = uint64_t(r);    // unsigned: reinterpret the bits
        switch (op)
        {
        case BinaryOperatorKind::Equals: return Value::Bool(l == r);
        case BinaryOperatorKind::NotEquals: return Value::Bool(l != r);
        case BinaryOperatorKind::Less: return Value::Bool(isSigned ? l < r : ul < ur);
        case BinaryOperatorKind::LessOrEqual: return Value::Bool(isSigned ? l <= r : ul <= ur);
        case BinaryOperatorKind::Greater: return Value::Bool(isSigned ? l > r : ul > ur);
        case BinaryOperatorKind::GreaterOrEqual: return Value::Bool(isSigned ? l >= r : ul >= ur);
        default: break;
        }
        if (op == BinaryOperatorKind::Divide || op == BinaryOperatorKind::Remainder)
        {
            if (r == 0) throw EvaluationPanic("division by zero", b->syntax->Span());
            int64_t min = type->bits == 64 ? INT64_MIN : -(int64_t(1) << (type->bits - 1));
            if (isSigned && l == min && r == -1) throw EvaluationPanic("overflow in division", b->syntax->Span());
        }
        uint64_t result;                                // wrapping arithmetic in uint64_t: signed overflow is undefined in C++
        switch (op)
        {
        case BinaryOperatorKind::Add: result = ul + ur; break;
        case BinaryOperatorKind::Subtract: result = ul - ur; break;
        case BinaryOperatorKind::Multiply: result = ul * ur; break;
        case BinaryOperatorKind::Divide: result = isSigned ? uint64_t(l / r) : ul / ur; break;
        default: result = isSigned ? uint64_t(l % r) : ul % ur; break;
        }
        return Value::Int(Normalise(int64_t(result), type));   // wrap like LLVM's add on an i8
    }
    ```

=== "C#"

    ```csharp
    Value EvalBinary(BoundBinary b, Dictionary<Symbol, Slot> frame)
    {
        BinaryOperatorKind op = b.Operator.Kind;
        Value left = Eval(b.Left, frame);
        if (op == BinaryOperatorKind.LogicalAnd && !left.AsBool) return Value.FromBool(false);   // b.Right is not evaluated
        if (op == BinaryOperatorKind.LogicalOr && left.AsBool) return Value.FromBool(true);
        Value right = Eval(b.Right, frame);
        TypeSymbol t = b.Operator.Left;

        if (t == TypeSymbol.Bool)
            return Value.FromBool(op switch
            {
                BinaryOperatorKind.Equals => left.AsBool == right.AsBool,
                BinaryOperatorKind.NotEquals => left.AsBool != right.AsBool,
                _ => right.AsBool,                                         // && and || after the short circuit
            });
        if (t.IsFloat)
        {
            if (t == TypeSymbol.F32)                                       // f32 arithmetic in float, not double
            {
                float x = (float)left.Float, y = (float)right.Float;
                return FloatResult(op, x, y, (x, y) => (float)(op switch
                {
                    BinaryOperatorKind.Add => x + y, BinaryOperatorKind.Subtract => x - y, BinaryOperatorKind.Multiply => x * y,
                    BinaryOperatorKind.Divide => x / y, _ => x % y,
                }));
            }
            return FloatResult(op, left.Float, right.Float, (x, y) => op switch
            {
                BinaryOperatorKind.Add => x + y, BinaryOperatorKind.Subtract => x - y, BinaryOperatorKind.Multiply => x * y,
                BinaryOperatorKind.Divide => x / y, _ => x % y,
            });
        }

        var type = (PrimitiveType)t;
        long l = left.Bits, r = right.Bits;
        bool signed = type.IsSigned;
        switch (op)
        {
            case BinaryOperatorKind.Equals: return Value.FromBool(l == r);
            case BinaryOperatorKind.NotEquals: return Value.FromBool(l != r);
            case BinaryOperatorKind.Less: return Value.FromBool(signed ? l < r : (ulong)l < (ulong)r);   // unsigned: reinterpret the bits
            case BinaryOperatorKind.LessOrEqual: return Value.FromBool(signed ? l <= r : (ulong)l <= (ulong)r);
            case BinaryOperatorKind.Greater: return Value.FromBool(signed ? l > r : (ulong)l > (ulong)r);
            case BinaryOperatorKind.GreaterOrEqual: return Value.FromBool(signed ? l >= r : (ulong)l >= (ulong)r);
        }
        if (op is BinaryOperatorKind.Divide or BinaryOperatorKind.Remainder)
        {
            if (r == 0) throw new EvaluationPanic("division by zero", b.Syntax.Span);
            long min = type.Bits == 64 ? long.MinValue : -(1L << (type.Bits - 1));
            if (signed && l == min && r == -1) throw new EvaluationPanic("overflow in division", b.Syntax.Span);
        }
        long result = unchecked(op switch
        {
            BinaryOperatorKind.Add => l + r,
            BinaryOperatorKind.Subtract => l - r,
            BinaryOperatorKind.Multiply => l * r,
            BinaryOperatorKind.Divide => signed ? l / r : (long)((ulong)l / (ulong)r),
            _ => signed ? l % r : (long)((ulong)l % (ulong)r),
        });
        return Value.Int(Normalise(result, type));                         // wrap like LLVM's add on an i8
    }
    ```

- **Recursion depth**: count calls and panic past a limit, as `Call` does, rather than overflow the host's stack on a runaway recursive test.
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

## C++ tips

- **Do integer arithmetic in `uint64_t`**, as `EvalBinary` does: signed overflow is undefined behaviour in C++, and the optimiser may assume `a + 1 > a`. Unsigned arithmetic wraps by definition, and `Normalise` then gives the bits their type.
- **Clamp before converting a float to an integer.** An out-of-range `int64_t(f)` is undefined behaviour, not a saturating conversion; `Convert` compares against the type's range first.
- **`f32` arithmetic in `float`**: C++ may evaluate `float` expressions at higher precision only where `FLT_EVAL_METHOD` is non-zero (old x87 code); on x64 and ARM64 it is 0, and `float(a) + float(b)` rounds once.
- **Value semantics come free**: `Value` holds its struct fields in a `std::vector<Value>`, so copying a `Value` copies the struct. Pointers refer to `Slot`s held by `unique_ptr`, whose addresses stay valid as the frame grows.
- Throw an `EvaluationPanic` (a `std::runtime_error` with the span) and catch it at the top of the evaluation.

## C# tips

- `Value` is a small `readonly record struct` with a kind and a `long`/`double` payload, plus a `Value[]?` for structs. Most programs then evaluate without allocating; only structs need `Copy()`.
- `Normalise` relies on casts between integer types truncating. Wrap it in `unchecked(...)`, as above, so it still works in a project built with `<CheckForOverflowUnderflow>`.
- For `f32` semantics, do the arithmetic in `float` (`(float)a + (float)b`), not in `double` with one rounding at the end.
- C#'s `(int)someFloat` saturates on .NET 9 and later, but conversions to smaller types do not; see the [C# tips on numeric conversions](numeric-conversions.md#c-tips).
- Throw a dedicated `EvaluationPanic` exception carrying the message and the syntax location, and catch it at the top of the evaluation, so a panic deep in a call stack unwinds cleanly.
