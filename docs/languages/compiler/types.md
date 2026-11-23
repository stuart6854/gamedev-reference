# Type checking and inference

The other half of the [binder](binding.md): every expression gets a type, every operation is checked against its operands, and local variables without a written type get one from their use. The rules here are for a statically typed language with **local** inference: function signatures are written out, and types inside a body are worked out.

## Representing types

=== "C++"

    ```cpp
    enum class TypeKind : uint8_t { Primitive, Struct, Pointer, Function, Error, Variable };

    struct Type
    {
        explicit Type(TypeKind kind) : kind(kind) {}
        virtual ~Type() = default;
        virtual std::string Display() const = 0;       // as the user writes it: *Vec2, fn(i32) -> f32
        const TypeKind kind;
    };

    struct PrimitiveType final : Type
    {
        PrimitiveType(PrimitiveKind primitive, std::string_view name, int bits)
            : Type(TypeKind::Primitive), primitive(primitive), name(name), bits(bits) {}
        std::string Display() const override { return std::string(name); }
        bool IsInteger() const { return primitive <= PrimitiveKind::U64; }
        bool IsSigned() const { return primitive <= PrimitiveKind::I64; }
        bool IsFloat() const { return primitive == PrimitiveKind::F32 || primitive == PrimitiveKind::F64; }
        const PrimitiveKind primitive;
        const std::string_view name;
        const int bits;
    };

    struct PointerType final : Type
    {
        explicit PointerType(const Type* pointee) : Type(TypeKind::Pointer), pointee(pointee) {}
        std::string Display() const override { return "*" + pointee->Display(); }
        const Type* const pointee;
    };

    // StructType { const StructSymbol* symbol }, FunctionType { parameters, returnType }, ErrorType, and TypeVariable (below) are alike.

    namespace Types
    {
        inline const PrimitiveType I8{ PrimitiveKind::I8, "i8", 8 }, I16{ PrimitiveKind::I16, "i16", 16 },
            I32{ PrimitiveKind::I32, "i32", 32 }, I64{ PrimitiveKind::I64, "i64", 64 },
            U8{ PrimitiveKind::U8, "u8", 8 }, U16{ PrimitiveKind::U16, "u16", 16 },
            U32{ PrimitiveKind::U32, "u32", 32 }, U64{ PrimitiveKind::U64, "u64", 64 },
            F32{ PrimitiveKind::F32, "f32", 32 }, F64{ PrimitiveKind::F64, "f64", 64 },
            Bool{ PrimitiveKind::Bool, "bool", 1 }, Void{ PrimitiveKind::Void, "void", 0 };
        inline const ErrorType Error;
        inline const PrimitiveType* const Primitives[] = { &I8, &I16, &I32, &I64, &U8, &U16, &U32, &U64, &F32, &F64, &Bool, &Void };

        inline const PointerType* Pointer(const Type* pointee)    // one PointerType per pointee
        {
            static std::unordered_map<const Type*, std::unique_ptr<PointerType>> cache;
            auto& slot = cache[pointee];
            if (!slot) slot = std::make_unique<PointerType>(pointee);
            return slot.get();
        }

        inline const FunctionType* Function(const std::vector<const Type*>& parameters, const Type* returnType)
        {
            static std::vector<std::unique_ptr<FunctionType>> cache;   // few distinct signatures: a linear search is fine
            for (auto& f : cache)
                if (f->returnType == returnType && f->parameters == parameters) return f.get();
            return cache.emplace_back(std::make_unique<FunctionType>(parameters, returnType)).get();
        }
    }
    ```

=== "C#"

    ```csharp
    public abstract class TypeSymbol
    {
        public static readonly PrimitiveType I8 = new(PrimitiveKind.I8, "i8"), I16 = new(PrimitiveKind.I16, "i16"),
            I32 = new(PrimitiveKind.I32, "i32"), I64 = new(PrimitiveKind.I64, "i64"),
            U8 = new(PrimitiveKind.U8, "u8"), U16 = new(PrimitiveKind.U16, "u16"),
            U32 = new(PrimitiveKind.U32, "u32"), U64 = new(PrimitiveKind.U64, "u64"),
            F32 = new(PrimitiveKind.F32, "f32"), F64 = new(PrimitiveKind.F64, "f64"),
            Bool = new(PrimitiveKind.Bool, "bool"), Void = new(PrimitiveKind.Void, "void");
        public static readonly ErrorType Error = new();
        public static readonly PrimitiveType[] Primitives = [I8, I16, I32, I64, U8, U16, U32, U64, F32, F64, Bool, Void];

        static readonly Dictionary<TypeSymbol, PointerType> Pointers = [];
        static readonly List<FunctionType> Functions = [];

        public static PointerType Pointer(TypeSymbol pointee)          // one PointerType per pointee
        {
            if (!Pointers.TryGetValue(pointee, out var type)) Pointers[pointee] = type = new PointerType(pointee);
            return type;
        }

        public static FunctionType Function(IReadOnlyList<TypeSymbol> parameters, TypeSymbol returnType)
        {
            foreach (var f in Functions)                               // few distinct signatures: a linear search is fine
                if (f.ReturnType == returnType && f.Parameters.SequenceEqual(parameters)) return f;
            var type = new FunctionType([.. parameters], returnType);
            Functions.Add(type);
            return type;
        }

        public bool IsInteger => this is PrimitiveType { Kind: >= PrimitiveKind.I8 and <= PrimitiveKind.U64 };
        public bool IsFloat => this is PrimitiveType { Kind: PrimitiveKind.F32 or PrimitiveKind.F64 };
        public bool IsNumeric => IsInteger || IsFloat;
    }

    public sealed class PointerType : TypeSymbol
    {
        internal PointerType(TypeSymbol pointee) { Pointee = pointee; }
        public TypeSymbol Pointee { get; }
        public override string ToString() => "*" + Pointee;
    }

    // PrimitiveType { Kind, Name, IsSigned, Bits }, StructType { Symbol }, FunctionType { Parameters, ReturnType }, ErrorType,
    // and TypeVariable (below) are alike: an internal constructor, so only the factories create them.
    ```

- **Create each type once** and compare by reference. Primitives are singletons; constructed types like `*Vec2` come from a cache (`pointer_to(Vec2)` always returns the same object). Equality is then `a == b`.
- **Struct types are nominal**: two structs with the same fields are different types, because they are different symbols.
- Give each type a display form for messages (`Display()` in C++, `ToString()` in C#) that prints it as the user writes it: `*Vec2`, `fn(i32) -> f32`.

## Checking expressions

=== "C++"

    ```cpp
    const BoundExpression* Binder::BindBinary(const BinarySyntax* syntax, const Scope& scope)
    {
        // A literal takes its type from the other operand: in `length_sq(v) == 25.0`, 25.0 is an f32.
        const BoundExpression* left;
        const BoundExpression* right;
        if (IsNumberLiteral(syntax->right) && !IsNumberLiteral(syntax->left))
        {
            left = BindExpression(syntax->left, scope);
            right = IsNumeric(left->type) ? BindExpression(syntax->right, left->type, scope) : BindExpression(syntax->right, scope);
        }
        else if (IsNumberLiteral(syntax->left) && !IsNumberLiteral(syntax->right))
        {
            right = BindExpression(syntax->right, scope);
            left = IsNumeric(right->type) ? BindExpression(syntax->left, right->type, scope) : BindExpression(syntax->left, scope);
        }
        else
        {
            left = BindExpression(syntax->left, scope);
            right = BindExpression(syntax->right, scope);
        }
        if (left->type == &Types::Error || right->type == &Types::Error)
            return Make<BoundError>(syntax);                       // already reported
        const BoundBinaryOperator* op = LookupBinaryOperator(syntax->op.kind, left->type, right->type);
        if (!op)
        {
            diagnostics_.Report<Diag::NoBinaryOperator>(syntax->op.span, syntax->op.text, left->type->Display(), right->type->Display());
            return Make<BoundError>(syntax);
        }
        return Make<BoundBinary>(syntax, Convert(left, op->left), op, Convert(right, op->right));
    }

    const std::vector<BoundBinaryOperator>& BinaryOperators()
    {
        static const std::vector<BoundBinaryOperator> table = [] {
            using K = SyntaxKind;
            using B = BinaryOperatorKind;
            std::vector<BoundBinaryOperator> t;
            std::pair<K, B> arithmetic[] = { { K::PlusToken, B::Add }, { K::MinusToken, B::Subtract }, { K::StarToken, B::Multiply },
                                             { K::SlashToken, B::Divide }, { K::PercentToken, B::Remainder } };
            std::pair<K, B> comparison[] = { { K::EqualsEqualsToken, B::Equals }, { K::BangEqualsToken, B::NotEquals },
                                             { K::LessToken, B::Less }, { K::LessEqualsToken, B::LessOrEqual },
                                             { K::GreaterToken, B::Greater }, { K::GreaterEqualsToken, B::GreaterOrEqual } };
            for (const PrimitiveType* type : Types::Primitives)    // narrow to wide: lookup prefers the narrowest
            {
                if (!IsNumeric(type)) continue;
                for (auto [token, kind] : arithmetic) t.push_back({ token, kind, type, type, type });
                for (auto [token, kind] : comparison) t.push_back({ token, kind, type, type, &Types::Bool });
            }
            const Type* b = &Types::Bool;
            t.push_back({ K::EqualsEqualsToken, B::Equals, b, b, b });
            t.push_back({ K::BangEqualsToken, B::NotEquals, b, b, b });
            t.push_back({ K::AmpersandAmpersandToken, B::LogicalAnd, b, b, b });
            t.push_back({ K::PipePipeToken, B::LogicalOr, b, b, b });
            return t;
        }();
        return table;
    }

    const BoundBinaryOperator* LookupBinaryOperator(SyntaxKind token, const Type* left, const Type* right)
    {
        for (const auto& op : BinaryOperators())                   // an exact match first
            if (op.token == token && op.left == left && op.right == right) return &op;
        for (const auto& op : BinaryOperators())                   // then one both operands convert to
            if (op.token == token && IsImplicitConversion(left, op.left) && IsImplicitConversion(right, op.right)) return &op;
        return nullptr;
    }
    ```

=== "C#"

    ```csharp
    BoundExpression BindBinary(BinarySyntax syntax, Scope scope)
    {
        // A literal takes its type from the other operand: in `length_sq(v) == 25.0`, 25.0 is an f32.
        BoundExpression left, right;
        if (IsLiteral(syntax.Right) && !IsLiteral(syntax.Left))
        {
            left = BindExpression(syntax.Left, scope);
            right = left.Type.IsNumeric ? BindExpression(syntax.Right, left.Type, scope) : BindExpression(syntax.Right, scope);
        }
        else if (IsLiteral(syntax.Left) && !IsLiteral(syntax.Right))
        {
            right = BindExpression(syntax.Right, scope);
            left = right.Type.IsNumeric ? BindExpression(syntax.Left, right.Type, scope) : BindExpression(syntax.Left, scope);
        }
        else
        {
            left = BindExpression(syntax.Left, scope);
            right = BindExpression(syntax.Right, scope);
        }
        if (left.Type == TypeSymbol.Error || right.Type == TypeSymbol.Error)
            return new BoundError(syntax);                                     // already reported
        BoundBinaryOperator? op = Operators.LookupBinary(syntax.Operator.Kind, left.Type, right.Type);
        if (op is null)
        {
            diagnostics.Report(Diagnostics.NoBinaryOperator, syntax.Operator.Span, Describe.Kind(syntax.Operator.Kind).Trim('\''),
                               left.Type.ToString()!, right.Type.ToString()!);
            return new BoundError(syntax);
        }
        return new BoundBinary(syntax, Convert(left, op.Left), op, Convert(right, op.Right));
    }

    public static class Operators
    {
        static readonly BoundBinaryOperator[] Table = Build();

        static BoundBinaryOperator[] Build()
        {
            var table = new List<BoundBinaryOperator>();
            var numeric = TypeSymbol.Primitives.Where(t => t.IsNumeric).ToArray();   // narrow to wide: lookup prefers the narrowest
            (SyntaxKind, BinaryOperatorKind)[] arithmetic = [(SyntaxKind.PlusToken, BinaryOperatorKind.Add), (SyntaxKind.MinusToken, BinaryOperatorKind.Subtract),
                (SyntaxKind.StarToken, BinaryOperatorKind.Multiply), (SyntaxKind.SlashToken, BinaryOperatorKind.Divide), (SyntaxKind.PercentToken, BinaryOperatorKind.Remainder)];
            (SyntaxKind, BinaryOperatorKind)[] comparison = [(SyntaxKind.EqualsEqualsToken, BinaryOperatorKind.Equals), (SyntaxKind.BangEqualsToken, BinaryOperatorKind.NotEquals),
                (SyntaxKind.LessToken, BinaryOperatorKind.Less), (SyntaxKind.LessEqualsToken, BinaryOperatorKind.LessOrEqual),
                (SyntaxKind.GreaterToken, BinaryOperatorKind.Greater), (SyntaxKind.GreaterEqualsToken, BinaryOperatorKind.GreaterOrEqual)];
            foreach (var t in numeric)
            {
                foreach (var (token, kind) in arithmetic) table.Add(new(token, kind, t, t, t));
                foreach (var (token, kind) in comparison) table.Add(new(token, kind, t, t, TypeSymbol.Bool));
            }
            var b = TypeSymbol.Bool;
            table.Add(new(SyntaxKind.EqualsEqualsToken, BinaryOperatorKind.Equals, b, b, b));
            table.Add(new(SyntaxKind.BangEqualsToken, BinaryOperatorKind.NotEquals, b, b, b));
            table.Add(new(SyntaxKind.AmpersandAmpersandToken, BinaryOperatorKind.LogicalAnd, b, b, b));
            table.Add(new(SyntaxKind.PipePipeToken, BinaryOperatorKind.LogicalOr, b, b, b));
            return [.. table];
        }

        public static BoundBinaryOperator? LookupBinary(SyntaxKind token, TypeSymbol left, TypeSymbol right) =>
            Table.FirstOrDefault(o => o.Token == token && o.Left == left && o.Right == right)
            ?? Table.FirstOrDefault(o => o.Token == token && Conversions.IsImplicit(left, o.Left) && Conversions.IsImplicit(right, o.Right));
    }
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

Decide which conversions happen **implicitly** and which need `as`. A strict default suits a systems language; [numeric types and conversions](numeric-conversions.md) covers promotion, overflow, and what each explicit conversion does:

| From → to | Implicit | Explicit (`as`) |
| --- | --- | --- |
| same type | yes | yes |
| integer → wider integer of the same signedness | yes | yes |
| integer → narrower, or signed ↔ unsigned | no | yes (truncates or reinterprets) |
| integer ↔ float | no | yes |
| `f32` → `f64` | yes | yes |
| anything → `bool` | no | no: write `x != 0` |

=== "C++"

    ```cpp
    const BoundExpression* Binder::Convert(const BoundExpression* expression, const Type* target)   // implicit conversions only
    {
        if (expression->type == &Types::Error || target == &Types::Error) return expression;
        if (expression->type == target) return expression;
        if (IsImplicitConversion(expression->type, target)) return Make<BoundConversion>(expression->syntax, expression, target);
        diagnostics_.Report<Diag::TypeMismatch>(expression->syntax->Span(), target->Display(), expression->type->Display());
        return Make<BoundError>(expression->syntax);
    }

    bool IsImplicitConversion(const Type* from, const Type* to)
    {
        if (from == to) return true;
        auto* f = AsPrimitive(from);
        auto* t = AsPrimitive(to);
        if (!f || !t) return false;
        if (f->IsInteger() && t->IsInteger()) return f->IsSigned() == t->IsSigned() && t->bits > f->bits;   // widening, same signedness
        return f == &Types::F32 && t == &Types::F64;
    }
    ```

=== "C#"

    ```csharp
    BoundExpression Convert(BoundExpression expression, TypeSymbol target)   // implicit conversions only
    {
        if (expression.Type == TypeSymbol.Error || target == TypeSymbol.Error) return expression;
        if (expression.Type == target) return expression;
        if (Conversions.IsImplicit(expression.Type, target)) return new BoundConversion(expression.Syntax, expression, target);
        diagnostics.Report(Diagnostics.TypeMismatch, expression.Syntax.Span, target.ToString()!, expression.Type.ToString()!);
        return new BoundError(expression.Syntax);
    }

    public static class Conversions
    {
        public static bool IsImplicit(TypeSymbol from, TypeSymbol to)
        {
            if (from == to) return true;
            if (from is not PrimitiveType f || to is not PrimitiveType t) return false;
            if (f.IsInteger && t.IsInteger) return f.IsSigned == t.IsSigned && t.Bits > f.Bits;   // widening, same signedness
            return f == TypeSymbol.F32 && t == TypeSymbol.F64;
        }
    }
    ```

### Literals

An integer literal like `300` has no type of its own until its context gives it one. Simple and predictable rules:

- With an expected type (`let x: u8 = 300;`, or an argument to an `i64` parameter), the literal takes that type, and a value that does not fit is an error: "literal 300 does not fit in 'u8'".
- Without one (`let x = 300;`), integers default to `i32` and floats to `f64` (or `f32`, for a game language; pick one and document it).
- In a binary operation, a literal takes the **other operand's** type: `x + 1` with `x: u8` adds two `u8`s, and `length_sq(v) == 25.0` compares two `f32`s. Without this rule, the example program would fail to type-check, because an `f32` and a default `f64` literal have no common `==` operator.
- This needs the expected type passed **down** into the expression, which is what bidirectional checking does.

## Bidirectional checking

Two modes, instead of one:

=== "C++"

    ```cpp
    // Synthesize: work the type out from the expression alone (names, calls, operators).
    const BoundExpression* BindExpression(const ExpressionSyntax* syntax, const Scope& scope);
    // Check: the type is known; check the expression against it.
    const BoundExpression* BindExpression(const ExpressionSyntax* syntax, const Type* expected, const Scope& scope);
    ```

=== "C#"

    ```csharp
    // Synthesize: work the type out from the expression alone (names, calls, operators).
    BoundExpression BindExpression(ExpressionSyntax syntax, Scope scope);
    // Check: the type is known; check the expression against it.
    BoundExpression BindExpression(ExpressionSyntax syntax, TypeSymbol expected, Scope scope);
    ```

=== "C++"

    ```cpp
    const BoundExpression* Binder::BindExpression(const ExpressionSyntax* syntax, const Type* expected, const Scope& scope)   // check
    {
        if (auto* p = dynamic_cast<const ParenthesizedSyntax*>(syntax)) return BindExpression(p->inner, expected, scope);
        bool negate = false;
        const ExpressionSyntax* operand = syntax;
        if (auto* u = dynamic_cast<const UnarySyntax*>(syntax); u && u->op.kind == SyntaxKind::MinusToken) { negate = true; operand = u->operand; }
        if (auto* literal = dynamic_cast<const LiteralSyntax*>(operand))
        {
            const Token& token = literal->token;
            if (token.kind == SyntaxKind::IntLiteralToken && !IntegerSuffixType(token))
            {
                if (IsInteger(expected)) return CheckIntegerLiteral(literal, negate, expected, syntax);
                if (IsFloat(expected) && !negate)                  // `let x: f32 = 1;`
                    return Make<BoundLiteral>(syntax, double(std::get<uint64_t>(token.value)), expected);
            }
            if (token.kind == SyntaxKind::FloatLiteralToken && !FloatSuffixType(token) && IsFloat(expected) && !negate)
                return Make<BoundLiteral>(syntax, std::get<double>(token.value), expected);
        }
        return Convert(BindExpression(syntax, scope), expected);   // synthesize, then convert
    }

    const BoundExpression* Binder::CheckIntegerLiteral(const LiteralSyntax* literal, bool negate, const Type* type, const SyntaxNode* syntax)
    {
        if (!syntax) syntax = literal;
        uint64_t magnitude = std::get<uint64_t>(literal->token.value);
        auto* p = static_cast<const PrimitiveType*>(type);
        uint64_t max = p->IsSigned() ? (uint64_t(1) << (p->bits - 1)) - 1 : p->bits == 64 ? UINT64_MAX : (uint64_t(1) << p->bits) - 1;
        bool fits = negate ? p->IsSigned() && magnitude <= max + 1 : magnitude <= max;   // -128 fits in i8, 128 does not
        if (!fits)
        {
            diagnostics_.Report<Diag::LiteralOutOfRange>(syntax->Span(), std::format("{}{}", negate ? "-" : "", magnitude), p->name);
            return Make<BoundError>(syntax);
        }
        LiteralValue value = p->IsSigned() ? LiteralValue(negate ? int64_t(0 - magnitude) : int64_t(magnitude)) : LiteralValue(magnitude);
        return Make<BoundLiteral>(syntax, value, type);
    }
    ```

=== "C#"

    ```csharp
    BoundExpression BindExpression(ExpressionSyntax syntax, TypeSymbol expected, Scope scope)
    {
        switch (syntax)
        {
            case LiteralSyntax { Token.Kind: SyntaxKind.IntLiteralToken } i when IntegerSuffixType(i.Token) is null:
                if (expected.IsInteger) return CheckIntegerLiteral(i, negate: false, expected);
                if (expected.IsFloat) return new BoundLiteral(i, (double)(ulong)i.Token.Value!, expected);   // `let x: f32 = 1;`
                break;
            case UnarySyntax { Operator.Kind: SyntaxKind.MinusToken, Operand: LiteralSyntax { Token.Kind: SyntaxKind.IntLiteralToken } i }
                    when expected.IsInteger && IntegerSuffixType(i.Token) is null:
                return CheckIntegerLiteral(i, negate: true, expected, syntax);
            case LiteralSyntax { Token.Kind: SyntaxKind.FloatLiteralToken } f when FloatSuffixType(f.Token) is null && expected.IsFloat:
                return new BoundLiteral(f, f.Token.Value!, expected);
            case ParenthesizedSyntax p:
                return BindExpression(p.Inner, expected, scope);
        }
        return Convert(BindExpression(syntax, scope), expected);                // synthesize, then convert
    }

    BoundExpression CheckIntegerLiteral(LiteralSyntax literal, bool negate, TypeSymbol type, SyntaxNode? syntax = null)
    {
        syntax ??= literal;
        ulong magnitude = (ulong)literal.Token.Value!;
        var p = (PrimitiveType)type;
        ulong max = p.IsSigned ? (1UL << (p.Bits - 1)) - 1 : p.Bits == 64 ? ulong.MaxValue : (1UL << p.Bits) - 1;
        bool fits = negate ? p.IsSigned && magnitude <= max + 1 : magnitude <= max;   // -128 fits in i8, 128 does not
        if (!fits)
        {
            diagnostics.Report(Diagnostics.LiteralOutOfRange, syntax.Span, (negate ? "-" : "") + magnitude, type.ToString()!);
            return new BoundError(syntax);
        }
        object value = p.IsSigned ? (negate ? (long)(0 - magnitude) : (long)magnitude) : magnitude;
        return new BoundLiteral(syntax, value, type);
    }
    ```

`let x: u8 = 300;` checks `300` against `u8`. A call argument is checked against its parameter type. A `return` value is checked against the return type. Only where nothing is expected, as in `let x = 300;`, does the binder synthesize and use the defaults. A struct literal needs no case of its own: it checks each field value against its field's type while it is synthesized. For local inference this is usually all you need, and its errors are easy to explain because each one happens in one place.

## Inference with type variables

Bidirectional checking cannot type `var total;` followed later by `total = 0.5;`, or a generic function's arguments. For those, give unknown types a **type variable** and solve constraints by **unification**:

=== "C++"

    ```cpp
    enum class TypeRestriction : uint8_t { None, Integer, Float };   // a literal's variable: "some integer" or "some float"

    struct TypeVariable final : Type
    {
        TypeVariable(int id, TypeRestriction restriction) : Type(TypeKind::Variable), id(id), restriction(restriction) {}
        std::string Display() const override { return binding ? binding->Display() : std::format("T{}", id); }
        const int id;
        const TypeRestriction restriction;
        const Type* binding = nullptr;
    };

    class Unifier
    {
    public:
        explicit Unifier(DiagnosticBag& diagnostics) : diagnostics_(diagnostics) {}

        TypeVariable* Fresh(TypeRestriction restriction = TypeRestriction::None)
        {
            return variables_.emplace_back(std::make_unique<TypeVariable>(nextId_++, restriction)).get();
        }

        static const Type* Resolve(const Type* t)                  // follow bindings to the current answer
        {
            while (t->kind == TypeKind::Variable && static_cast<const TypeVariable*>(t)->binding)
                t = static_cast<const TypeVariable*>(t)->binding;
            return t;
        }

        void Unify(const Type* a, const Type* b, TextSpan span)    // make a and b the same type, or report
        {
            a = Resolve(a);
            b = Resolve(b);
            if (a == b) return;
            if (a->kind == TypeKind::Variable)
            {
                auto* va = const_cast<TypeVariable*>(static_cast<const TypeVariable*>(a));   // variables are the one mutable type
                if (Occurs(va, b)) { diagnostics_.Report<Diag::InfiniteType>(span); return; }
                if (!Allows(va->restriction, b)) { Mismatch(a, b, span); return; }
                if (b->kind == TypeKind::Variable)
                {
                    auto* vb = const_cast<TypeVariable*>(static_cast<const TypeVariable*>(b));
                    if (vb->restriction == TypeRestriction::None && va->restriction != TypeRestriction::None)
                    {
                        vb->binding = va;                          // keep the restriction: bind the unrestricted one
                        return;
                    }
                }
                va->binding = b;
                return;
            }
            if (b->kind == TypeKind::Variable) return Unify(b, a, span);
            if (a->kind == TypeKind::Pointer && b->kind == TypeKind::Pointer)
                return Unify(static_cast<const PointerType*>(a)->pointee, static_cast<const PointerType*>(b)->pointee, span);
            if (a->kind == TypeKind::Function && b->kind == TypeKind::Function)
            {
                auto* fa = static_cast<const FunctionType*>(a);
                auto* fb = static_cast<const FunctionType*>(b);
                if (fa->parameters.size() == fb->parameters.size())
                {
                    for (size_t i = 0; i < fa->parameters.size(); i++) Unify(fa->parameters[i], fb->parameters[i], span);
                    return Unify(fa->returnType, fb->returnType, span);
                }
            }
            Mismatch(a, b, span);
        }

        static const Type* Default(const Type* t)                  // at the end of a function
        {
            t = Resolve(t);
            if (t->kind != TypeKind::Variable) return t;
            switch (static_cast<const TypeVariable*>(t)->restriction)
            {
            case TypeRestriction::Integer: return &Types::I32;
            case TypeRestriction::Float: return &Types::F64;
            default: return t;                                     // an unrestricted variable: "cannot infer"
            }
        }

    private:
        static bool Allows(TypeRestriction r, const Type* t)
        {
            auto* v = t->kind == TypeKind::Variable ? static_cast<const TypeVariable*>(t) : nullptr;
            if (r == TypeRestriction::Integer) return IsInteger(t) || (v && v->restriction != TypeRestriction::Float);
            if (r == TypeRestriction::Float) return IsFloat(t) || (v && v->restriction != TypeRestriction::Integer);
            return true;
        }

        static bool Occurs(const TypeVariable* v, const Type* t)   // would binding v to t make t contain itself?
        {
            t = Resolve(t);
            if (t == v) return true;
            if (t->kind == TypeKind::Pointer) return Occurs(v, static_cast<const PointerType*>(t)->pointee);
            if (t->kind == TypeKind::Function)
            {
                auto* f = static_cast<const FunctionType*>(t);
                for (const Type* p : f->parameters) if (Occurs(v, p)) return true;
                return Occurs(v, f->returnType);
            }
            return false;
        }

        void Mismatch(const Type* a, const Type* b, TextSpan span) { diagnostics_.Report<Diag::TypeMismatch>(span, a->Display(), b->Display()); }

        DiagnosticBag& diagnostics_;
        int nextId_ = 1;
        std::vector<std::unique_ptr<TypeVariable>> variables_;
    };
    ```

=== "C#"

    ```csharp
    public enum TypeRestriction { None, Integer, Float }   // a literal's variable: "some integer" or "some float"

    public sealed class TypeVariable(int id, TypeRestriction restriction) : TypeSymbol
    {
        public int Id => id;
        public TypeRestriction Restriction => restriction;
        public TypeSymbol? Binding { get; set; }
        public override string ToString() => Binding?.ToString() ?? $"T{id}";
    }

    public sealed class Unifier(DiagnosticBag diagnostics)
    {
        int _nextId = 1;

        public TypeVariable Fresh(TypeRestriction restriction = TypeRestriction.None) => new(_nextId++, restriction);

        public static TypeSymbol Resolve(TypeSymbol t)                  // follow bindings to the current answer
        {
            while (t is TypeVariable { Binding: TypeSymbol bound }) t = bound;
            return t;
        }

        public void Unify(TypeSymbol a, TypeSymbol b, TextSpan span)    // make a and b the same type, or report
        {
            a = Resolve(a);
            b = Resolve(b);
            if (a == b) return;
            if (a is TypeVariable va)
            {
                if (Occurs(va, b)) { diagnostics.Report(Diagnostics.InfiniteType, span); return; }
                if (!Allows(va.Restriction, b)) { Mismatch(a, b, span); return; }
                if (b is TypeVariable vb && vb.Restriction == TypeRestriction.None && va.Restriction != TypeRestriction.None)
                {
                    vb.Binding = va;                                    // keep the restriction: bind the unrestricted one
                    return;
                }
                va.Binding = b;
                return;
            }
            if (b is TypeVariable) { Unify(b, a, span); return; }
            if (a is PointerType pa && b is PointerType pb) { Unify(pa.Pointee, pb.Pointee, span); return; }
            if (a is FunctionType fa && b is FunctionType fb && fa.Parameters.Count == fb.Parameters.Count)
            {
                for (int i = 0; i < fa.Parameters.Count; i++) Unify(fa.Parameters[i], fb.Parameters[i], span);
                Unify(fa.ReturnType, fb.ReturnType, span);
                return;
            }
            Mismatch(a, b, span);
        }

        static bool Allows(TypeRestriction r, TypeSymbol t) => r switch
        {
            TypeRestriction.Integer => t.IsInteger || t is TypeVariable { Restriction: not TypeRestriction.Float },
            TypeRestriction.Float => t.IsFloat || t is TypeVariable { Restriction: not TypeRestriction.Integer },
            _ => true,
        };

        static bool Occurs(TypeVariable v, TypeSymbol t)                // would binding v to t make t contain itself?
        {
            t = Resolve(t);
            return t == v || t switch
            {
                PointerType p => Occurs(v, p.Pointee),
                FunctionType f => f.Parameters.Any(p => Occurs(v, p)) || Occurs(v, f.ReturnType),
                _ => false,
            };
        }

        void Mismatch(TypeSymbol a, TypeSymbol b, TextSpan span) =>
            diagnostics.Report(Diagnostics.TypeMismatch, span, a.ToString()!, b.ToString()!);

        public static TypeSymbol Default(TypeSymbol t) => Resolve(t) switch   // at the end of a function
        {
            TypeVariable { Restriction: TypeRestriction.Integer } => TypeSymbol.I32,
            TypeVariable { Restriction: TypeRestriction.Float } => TypeSymbol.F64,
            var other => other,                                          // an unrestricted variable: "cannot infer"
        };
    }
    ```

```text
var total;                 // total: T1
total = 0;                 // unify(T1, {integer literal}) — see below
total = total + 1;         // operands unify with T1
return total;              // unify(T1, i32): T1 = i32
```

- **Literals** get a type variable restricted to "some integer" (or "some float"). Unifying it with `i32` binds it; if nothing binds it by the end of the function, `Default` applies the default.
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

## C++ tips

- **Types compare by pointer**: primitives are `inline const` objects in a namespace, and the factories (`Types::Pointer`, `Types::Function`) return the same object for the same arguments. Code then reads `if (t == &Types::Bool)`.
- The factory caches are function-local `static`s, which are thread-safe to create but not to fill: compile one file per thread with its own cache, or guard the maps with a mutex.
- **`const Type*` everywhere** except type variables, which inference binds. The unifier casts away `const` on them only, which is safe because every `TypeVariable` is created non-`const` by `Fresh`.
- The operator table is built once in a function-local `static` from loops over the numeric types: adding a type adds its operators.

## C# tips

- Model types as `sealed class`es under `abstract class TypeSymbol`, with `internal` constructors and static factories that cache, as above. The caches are plain `Dictionary` and `List`: use `ConcurrentDictionary` or a lock if several files are bound in parallel.
- Keep the operator table as data, as above: `BoundBinaryOperator` records searched linearly. It is short, and a new numeric type gets its operators from the loop.
- `ToString()` on each type should return the display form, so it appears correctly in the debugger and in messages.
- Literal values: the lexer stores them as `ulong` or `double`. Range-check with `value <= (ulong)sbyte.MaxValue` and similar for each target type, then store the checked value in the bound literal as a `long` (integers) or `double` (floats), which is what [code generation](llvmsharp.md#expressions) expects. A negative literal is a unary minus applied to a positive one, so `-128` as an `i8` needs the check to look at the negation; fold the two into one constant once the check passes.
