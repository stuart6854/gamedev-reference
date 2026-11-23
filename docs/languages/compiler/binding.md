# Names, scopes, and symbols

The **binder** connects every name in the syntax tree to what it names, and builds a **bound tree**: the program with names replaced by symbols and every expression given a type. This page is the names half; [type checking and inference](types.md) is the types half. They run in the same walk. [Language design](../design.md#name-resolution-and-scoping) covers the scoping rules a language can choose; this is how to implement them.

## Symbols

A **symbol** is one declared thing. Every use of a name in the bound tree points at a symbol, never at a string.

=== "C++"

    ```cpp
    struct Symbol
    {
        Symbol(std::string name, const SyntaxNode* declaration) : name(std::move(name)), declaration(declaration) {}
        virtual ~Symbol() = default;
        const std::string name;
        const SyntaxNode* const declaration;           // for errors and go-to-definition; null for built-ins
    };

    struct FunctionSymbol final : Symbol
    {
        FunctionSymbol(std::string name, const SyntaxNode* declaration, bool isExtern)
            : Symbol(std::move(name), declaration), isExtern(isExtern) {}
        const FunctionType* GetType() const
        {
            std::vector<const Type*> types;
            for (auto* p : parameters) types.push_back(p->type);
            return Types::Function(types, returnType);
        }
        const bool isExtern;
        std::vector<const ParameterSymbol*> parameters;   // set in pass 2
        const Type* returnType = &Types::Void;
        const BoundBlock* body = nullptr;                 // set in pass 3
    };

    struct ParameterSymbol final : Symbol
    {
        ParameterSymbol(std::string name, const SyntaxNode* declaration, const Type* type, int index)
            : Symbol(std::move(name), declaration), type(type), index(index) {}
        const Type* const type;
        const int index;
    };

    struct LocalSymbol final : Symbol
    {
        LocalSymbol(std::string name, const SyntaxNode* declaration, const Type* type, bool isMutable)
            : Symbol(std::move(name), declaration), type(type), isMutable(isMutable) {}
        const Type* const type;
        const bool isMutable;
    };

    struct StructSymbol final : Symbol
    {
        StructSymbol(std::string name, const SyntaxNode* declaration) : Symbol(std::move(name), declaration), type(this) {}
        const StructType type;                            // a struct is also a type
        std::vector<const FieldSymbol*> fields;           // set in pass 2
        const FieldSymbol* Field(std::string_view n) const
        {
            for (auto* f : fields) if (f->name == n) return f;
            return nullptr;
        }
    };

    struct FieldSymbol final : Symbol
    {
        FieldSymbol(std::string name, const SyntaxNode* declaration, const Type* type, int index)
            : Symbol(std::move(name), declaration), type(type), index(index) {}
        const Type* const type;
        const int index;
    };

    struct BuiltinTypeSymbol final : Symbol                // i32, f32, bool, ...
    {
        explicit BuiltinTypeSymbol(const PrimitiveType* type) : Symbol(std::string(type->name), nullptr), type(type) {}
        const PrimitiveType* const type;
    };
    ```

=== "C#"

    ```csharp
    public abstract class Symbol(string name, SyntaxNode? declaration)
    {
        public string Name => name;
        public SyntaxNode? Declaration => declaration;     // for errors and go-to-definition; null for built-ins
        public override string ToString() => name;
    }

    public sealed class FunctionSymbol(string name, SyntaxNode declaration, bool isExtern) : Symbol(name, declaration)
    {
        public bool IsExtern => isExtern;
        public ImmutableArray<ParameterSymbol> Parameters { get; internal set; } = [];   // set in pass 2
        public TypeSymbol ReturnType { get; internal set; } = TypeSymbol.Void;
        public BoundBlock? Body { get; internal set; }                                     // set in pass 3
        public FunctionType Type => TypeSymbol.Function([.. Parameters.Select(p => p.Type)], ReturnType);
    }

    public sealed class ParameterSymbol(string name, SyntaxNode declaration, TypeSymbol type, int index) : Symbol(name, declaration)
    {
        public TypeSymbol Type => type;
        public int Index => index;
    }

    public sealed class LocalSymbol(string name, SyntaxNode declaration, TypeSymbol type, bool isMutable) : Symbol(name, declaration)
    {
        public TypeSymbol Type => type;
        public bool IsMutable => isMutable;
    }

    public sealed class StructSymbol : Symbol
    {
        public StructSymbol(string name, SyntaxNode declaration) : base(name, declaration) { Type = new StructType(this); }
        public StructType Type { get; }                                            // a struct is also a type
        public ImmutableArray<FieldSymbol> Fields { get; internal set; } = [];      // set in pass 2
    }

    public sealed class FieldSymbol(string name, SyntaxNode declaration, TypeSymbol type, int index) : Symbol(name, declaration)
    {
        public TypeSymbol Type => type;
        public int Index => index;
    }

    public sealed class BuiltinTypeSymbol(PrimitiveType type) : Symbol(type.Name, null)   // i32, f32, bool, ...
    {
        public PrimitiveType Type => type;
    }
    ```

Two locals called `i` in different loops are two symbols. Later stages (lowering, code generation) work only with symbols, so they never have to think about scopes or shadowing again.

## Scopes

A **scope** maps names to symbols, and has a parent:

=== "C++"

    ```cpp
    class Scope
    {
    public:
        explicit Scope(const Scope* parent) : parent_(parent) {}

        Symbol* TryDeclare(Symbol* symbol)            // the existing symbol if the name is taken in this scope, else null
        {
            auto [it, added] = symbols_.try_emplace(symbol->name, symbol);
            return added ? nullptr : it->second;
        }

        Symbol* Lookup(std::string_view name) const
        {
            for (const Scope* scope = this; scope; scope = scope->parent_)
                if (auto it = scope->symbols_.find(std::string(name)); it != scope->symbols_.end()) return it->second;
            return nullptr;
        }

        std::optional<std::string> ClosestName(std::string_view name) const;   // for "did you mean": see the tips

    private:
        const Scope* parent_;
        std::unordered_map<std::string, Symbol*> symbols_;
    };

    bool Binder::Declare(Scope& scope, Symbol* symbol, TextSpan nameSpan)
    {
        if (symbol->name.empty()) return false;                    // a missing name: the parser has reported it
        Symbol* existing = scope.TryDeclare(symbol);
        if (!existing) return true;
        Diagnostic& d = diagnostics_.Report<Diag::DuplicateDefinition>(nameSpan, symbol->name);
        if (existing->declaration) d.WithRelated(existing->declaration->Span(), "first defined here");
        return false;
    }
    ```

=== "C#"

    ```csharp
    public sealed class Scope(Scope? parent)
    {
        readonly Dictionary<string, Symbol> _symbols = [];
        public Scope? Parent => parent;

        public bool TryDeclare(Symbol symbol, out Symbol? existing)    // false if the name is already in this scope
        {
            if (_symbols.TryGetValue(symbol.Name, out existing)) return false;
            _symbols.Add(symbol.Name, symbol);
            return true;
        }

        public Symbol? Lookup(string name)
        {
            for (Scope? scope = this; scope is not null; scope = scope.Parent)
                if (scope._symbols.TryGetValue(name, out var symbol)) return symbol;
            return null;
        }

        // public string? ClosestName(string name): for "did you mean", see the tips
    }

    bool Declare(Scope scope, Symbol symbol, TextSpan nameSpan)
    {
        if (symbol.Name.Length == 0) return false;                // a missing name: the parser has reported it
        if (scope.TryDeclare(symbol, out Symbol? existing)) return true;
        Diagnostic d = diagnostics.Report(Diagnostics.DuplicateDefinition, nameSpan, symbol.Name);
        if (existing!.Declaration is not null) d.WithRelated(existing.Declaration.Span, "first defined here");
        return false;
    }
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
- **Shadowing**: allowing an inner `let x` to hide an outer `x` means `Declare` only checks the current scope. To forbid shadowing inside a function, also walk the parents up to the function scope.

## Binding in passes

Functions and structs can be used before they are declared, and can refer to each other. One walk in source order cannot handle that. Bind in passes, each over all files:

=== "C++"

    ```cpp
    const Scope& Binder::BindProgram(const std::vector<const FileSyntax*>& files)
    {
        for (const PrimitiveType* type : Types::Primitives)
            global_.TryDeclare(Make<BuiltinTypeSymbol>(type));     // built-in types are ordinary symbols
        std::vector<const ItemSyntax*> items;
        for (const FileSyntax* file : files) items.insert(items.end(), file->items.begin(), file->items.end());

        // 1. Declare: every struct, function, and extern gets a symbol. Nothing is resolved yet.
        std::vector<StructSymbol*> structs;
        std::vector<FunctionSymbol*> functions;
        for (const ItemSyntax* item : items)
        {
            if (auto* s = dynamic_cast<const StructSyntax*>(item))
            {
                auto* symbol = Make<StructSymbol>(std::string(s->name.text), s);
                if (Declare(global_, symbol, s->name.span)) structs.push_back(symbol);
            }
            else if (auto* f = dynamic_cast<const FunctionSyntax*>(item))
            {
                auto* symbol = Make<FunctionSymbol>(std::string(f->name.text), f, /*isExtern*/ false);
                if (Declare(global_, symbol, f->name.span)) functions.push_back(symbol);
            }
            else if (auto* e = dynamic_cast<const ExternSyntax*>(item))
            {
                auto* symbol = Make<FunctionSymbol>(std::string(e->name.text), e, /*isExtern*/ true);
                if (Declare(global_, symbol, e->name.span)) functions.push_back(symbol);
            }
        }

        // 2. Resolve signatures: field types, parameter types, return types.
        for (StructSymbol* s : structs)
        {
            auto* syntax = static_cast<const StructSyntax*>(s->declaration);
            for (const FieldSyntax* f : syntax->fields.items)
                s->fields.push_back(Make<FieldSymbol>(std::string(f->name.text), f, BindType(f->type), int(s->fields.size())));
        }
        for (FunctionSymbol* f : functions)
        {
            auto* fn = dynamic_cast<const FunctionSyntax*>(f->declaration);
            auto* ex = dynamic_cast<const ExternSyntax*>(f->declaration);
            const auto& parameters = fn ? fn->parameters : ex->parameters;
            const ReturnClauseSyntax* returnClause = fn ? fn->returnClause : ex->returnClause;
            for (const ParameterSyntax* p : parameters.items)
                f->parameters.push_back(Make<ParameterSymbol>(std::string(p->name.text), p, BindType(p->type), int(f->parameters.size())));
            f->returnType = returnClause ? BindType(returnClause->type) : &Types::Void;
        }
        CheckStructCycles(structs);                                // struct A { b: B } struct B { a: A } has infinite size

        // 3. Bind bodies: now every signature is known, in any order.
        for (FunctionSymbol* f : functions)
            if (auto* syntax = dynamic_cast<const FunctionSyntax*>(f->declaration)) f->body = BindFunctionBody(f, syntax);

        CheckEntryPoint(items);                                    // `main` exists and has the expected signature
        return global_;
    }
    ```

=== "C#"

    ```csharp
    public Scope BindProgram(IEnumerable<FileSyntax> files)
    {
        foreach (var type in TypeSymbol.Primitives)
            _global.TryDeclare(new BuiltinTypeSymbol(type), out _);   // built-in types are ordinary symbols
        var items = files.SelectMany(f => f.Items).ToList();

        // 1. Declare: every struct, function, and extern gets a symbol. Nothing is resolved yet.
        var structs = new List<(StructSymbol Symbol, StructSyntax Syntax)>();
        var functions = new List<(FunctionSymbol Symbol, FunctionSyntax? Syntax, SeparatedSyntaxList<ParameterSyntax> Parameters, ReturnClauseSyntax? Return)>();
        foreach (var item in items)
        {
            switch (item)
            {
                case StructSyntax s:
                    var structSymbol = new StructSymbol(s.Name.Text ?? "", s);
                    if (Declare(_global, structSymbol, s.Name.Span)) structs.Add((structSymbol, s));
                    break;
                case FunctionSyntax f:
                    var function = new FunctionSymbol(f.Name.Text ?? "", f, isExtern: false);
                    if (Declare(_global, function, f.Name.Span)) functions.Add((function, f, f.Parameters, f.ReturnClause));
                    break;
                case ExternSyntax e:
                    var external = new FunctionSymbol(e.Name.Text ?? "", e, isExtern: true);
                    if (Declare(_global, external, e.Name.Span)) functions.Add((external, null, e.Parameters, e.ReturnClause));
                    break;
            }
        }

        // 2. Resolve signatures: field types, parameter types, return types.
        foreach (var (symbol, syntax) in structs)
            symbol.Fields = [.. syntax.Fields.Items.Select((f, i) => new FieldSymbol(f.Name.Text ?? "", f, BindType(f.Type), i))];
        foreach (var (symbol, _, parameters, returnClause) in functions)
        {
            symbol.Parameters = [.. parameters.Items.Select((p, i) => new ParameterSymbol(p.Name.Text ?? "", p, BindType(p.Type), i))];
            symbol.ReturnType = returnClause is null ? TypeSymbol.Void : BindType(returnClause.Type);
        }
        CheckStructCycles(structs.Select(s => s.Symbol));          // struct A { b: B } struct B { a: A } has infinite size

        // 3. Bind bodies: now every signature is known, in any order.
        foreach (var (symbol, syntax, _, _) in functions)
            if (syntax is not null) symbol.Body = BindFunctionBody(symbol, syntax);

        CheckEntryPoint(items);                                   // `main` exists and has the expected signature
        return _global;
    }
    ```

=== "C++"

    ```cpp
    const BoundBlock* Binder::BindFunctionBody(FunctionSymbol* function, const FunctionSyntax* syntax)
    {
        function_ = function;
        Scope& scope = *Make<Scope>(&global_);
        for (const ParameterSymbol* p : function->parameters)
            Declare(scope, const_cast<ParameterSymbol*>(p), static_cast<const ParameterSyntax*>(p->declaration)->name.span);
        return BindBlock(syntax->body, scope);
    }

    const BoundBlock* Binder::BindBlock(const BlockSyntax* block, const Scope& parent)
    {
        Scope& scope = *Make<Scope>(&parent);
        std::vector<const BoundStatement*> statements;
        for (const StatementSyntax* s : block->statements) statements.push_back(BindStatement(s, scope));
        return Make<BoundBlock>(block, std::move(statements));
    }

    const BoundStatement* Binder::BindLet(const LetSyntax* syntax, Scope& scope)
    {
        const Type* declared = syntax->type ? BindType(syntax->type) : nullptr;
        const BoundExpression* initializer = nullptr;            // bound before declaring: `let x = x;` uses the outer x
        if (syntax->initializer)
            initializer = declared ? BindExpression(syntax->initializer, declared, scope)   // check: `let x: u8 = 300;` is an error
                                   : BindExpression(syntax->initializer, scope);           // synthesize: `let x = 300;` is an i32
        const Type* type = declared ? declared : initializer ? initializer->type : &Types::Error;
        if (!declared && !initializer && !syntax->name.isMissing)
            diagnostics_.Report<Diag::CannotInfer>(syntax->name.span, syntax->name.text);  // `var x;`: see inference
        auto* local = Make<LocalSymbol>(std::string(syntax->name.text), syntax, type, syntax->kind == SyntaxKind::VarStatement);
        Declare(scope, local, syntax->name.span);
        return Make<BoundLet>(syntax, local, initializer);
    }

    const BoundExpression* Binder::BindName(const NameSyntax* syntax, const Scope& scope)
    {
        const Token& name = syntax->name;
        Symbol* symbol = scope.Lookup(name.text);
        if (!symbol)
        {
            Diagnostic& d = diagnostics_.Report<Diag::UndefinedName>(name.span, name.text);
            if (auto suggestion = scope.ClosestName(name.text)) d.WithFix(name.span, *suggestion);   // "did you mean"
            return Make<BoundError>(syntax);
        }
        if (auto* local = dynamic_cast<const LocalSymbol*>(symbol)) return Make<BoundVariable>(syntax, local, local->type);
        if (auto* parameter = dynamic_cast<const ParameterSymbol*>(symbol)) return Make<BoundVariable>(syntax, parameter, parameter->type);
        if (auto* function = dynamic_cast<const FunctionSymbol*>(symbol)) return Make<BoundFunctionReference>(syntax, function);
        diagnostics_.Report<Diag::NotAValue>(name.span, name.text);   // a struct or type name used as a value
        return Make<BoundError>(syntax);
    }
    ```

=== "C#"

    ```csharp
    BoundBlock BindFunctionBody(FunctionSymbol function, FunctionSyntax syntax)
    {
        _function = function;
        var scope = new Scope(_global);
        foreach (var p in function.Parameters) Declare(scope, p, ((ParameterSyntax)p.Declaration!).Name.Span);
        return BindBlock(syntax.Body, scope);
    }

    BoundBlock BindBlock(BlockSyntax block, Scope parent)
    {
        var scope = new Scope(parent);
        return new BoundBlock(block, [.. block.Statements.Select(s => BindStatement(s, scope))]);
    }

    BoundLet BindLet(LetSyntax syntax, Scope scope)
    {
        TypeSymbol? declared = syntax.Type is null ? null : BindType(syntax.Type);
        BoundExpression? initializer = syntax.Initializer is null ? null       // bound before declaring: `let x = x;` uses the outer x
            : declared is null ? BindExpression(syntax.Initializer, scope)          // synthesize: `let x = 300;` is an i32
            : BindExpression(syntax.Initializer, declared, scope);                  // check: `let x: u8 = 300;` is an error
        TypeSymbol type = declared ?? initializer?.Type ?? TypeSymbol.Error;
        if (declared is null && initializer is null && !syntax.Name.IsMissing)
            diagnostics.Report(Diagnostics.CannotInfer, syntax.Name.Span, syntax.Name.Text!);   // `var x;`: see inference
        var local = new LocalSymbol(syntax.Name.Text ?? "", syntax, type, isMutable: syntax.Keyword.Kind == SyntaxKind.VarKeyword);
        Declare(scope, local, syntax.Name.Span);
        return new BoundLet(syntax, local, initializer);
    }

    BoundExpression BindName(NameSyntax syntax, Scope scope)
    {
        Token name = syntax.Name;
        Symbol? symbol = scope.Lookup(name.Text!);
        switch (symbol)
        {
            case null:
                Diagnostic d = diagnostics.Report(Diagnostics.UndefinedName, name.Span, name.Text!);
                if (scope.ClosestName(name.Text!) is string suggestion) d.WithFix(name.Span, suggestion);   // "did you mean"
                return new BoundError(syntax);
            case LocalSymbol or ParameterSymbol:
                return new BoundVariable(syntax, symbol);
            case FunctionSymbol f:
                return new BoundFunctionReference(syntax, f);
            default:
                diagnostics.Report(Diagnostics.NotAValue, name.Span, name.Text!);   // a struct or type name used as a value
                return new BoundError(syntax);
        }
    }
    ```

- **Declare locals after binding their initialiser**, so `let x = x + 1;` refers to an outer `x` (or is an error), never to itself.
- **Assignment checks mutability**: assigning to a `let` local or a parameter reports "cannot assign to immutable 'x'", pointing at the declaration as a related location. Assigning through a pointer (`p.x = 1` with `p: *Vec2`) changes memory, not the variable, so it is allowed for a `let p`.
- **Struct cycles**: walk field types depth-first and report a cycle unless it goes through a pointer. Without the check, code generation loops forever computing the size.

## The bound tree

The bound tree is the syntax tree's meaning, with everything later stages need and nothing they do not:

=== "C++"

    ```cpp
    struct BoundNode
    {
        explicit BoundNode(const SyntaxNode* syntax) : syntax(syntax) {}
        virtual ~BoundNode() = default;
        const SyntaxNode* const syntax;                // for error spans in later stages and debug info
    };

    struct BoundExpression : BoundNode
    {
        BoundExpression(const SyntaxNode* syntax, const Type* type) : BoundNode(syntax), type(type) {}
        const Type* const type;
    };

    struct BoundVariable final : BoundExpression       // a local or a parameter
    {
        BoundVariable(const SyntaxNode* s, const Symbol* symbol, const Type* type) : BoundExpression(s, type), symbol(symbol) {}
        const Symbol* const symbol;
    };

    struct BoundBinaryOperator { SyntaxKind token; BinaryOperatorKind kind; const Type* left; const Type* right; const Type* result; };

    struct BoundBinary final : BoundExpression
    {
        BoundBinary(const SyntaxNode* s, const BoundExpression* left, const BoundBinaryOperator* op, const BoundExpression* right)
            : BoundExpression(s, op->result), left(left), op(op), right(right) {}
        const BoundExpression* const left;
        const BoundBinaryOperator* const op;           // "i32 add", "f32 less-than": the operand types are part of it
        const BoundExpression* const right;
    };

    struct BoundConversion final : BoundExpression
    {
        BoundConversion(const SyntaxNode* s, const BoundExpression* operand, const Type* to) : BoundExpression(s, to), operand(operand) {}
        const BoundExpression* const operand;
    };

    struct BoundError final : BoundExpression
    {
        explicit BoundError(const SyntaxNode* s) : BoundExpression(s, &Types::Error) {}
    };

    // Also: BoundLiteral, BoundFunctionReference, BoundUnary, BoundCall, BoundFieldAccess, BoundStructLiteral, BoundAssignment.
    // Statements: BoundBlock, BoundLet, BoundExpressionStatement, BoundReturn, BoundIf, BoundWhile.
    ```

=== "C#"

    ```csharp
    public abstract class BoundNode(SyntaxNode syntax)
    {
        public SyntaxNode Syntax => syntax;                // for error spans in later stages and debug info
    }

    public abstract class BoundExpression(SyntaxNode syntax) : BoundNode(syntax)
    {
        public abstract TypeSymbol Type { get; }
    }

    public sealed class BoundVariable(SyntaxNode syntax, Symbol symbol) : BoundExpression(syntax)
    {
        public Symbol Symbol => symbol;                   // a LocalSymbol or ParameterSymbol
        public override TypeSymbol Type => symbol switch
        {
            LocalSymbol l => l.Type,
            ParameterSymbol p => p.Type,
            _ => throw new InvalidOperationException(),
        };
    }

    public sealed record BoundBinaryOperator(SyntaxKind Token, BinaryOperatorKind Kind, TypeSymbol Left, TypeSymbol Right, TypeSymbol Result);

    public sealed class BoundBinary(SyntaxNode syntax, BoundExpression left, BoundBinaryOperator op, BoundExpression right) : BoundExpression(syntax)
    {
        public BoundExpression Left => left;
        public BoundBinaryOperator Operator => op;        // "i32 add", "f32 less-than": the operand types are part of it
        public BoundExpression Right => right;
        public override TypeSymbol Type => op.Result;
    }

    public sealed class BoundConversion(SyntaxNode syntax, BoundExpression operand, TypeSymbol toType) : BoundExpression(syntax)
    {
        public BoundExpression Operand => operand;
        public override TypeSymbol Type => toType;
    }

    public sealed class BoundError(SyntaxNode syntax) : BoundExpression(syntax)
    {
        public override TypeSymbol Type => TypeSymbol.Error;
    }

    // Also: BoundLiteral, BoundFunctionReference, BoundUnary, BoundCall, BoundFieldAccess, BoundStructLiteral, BoundAssignment.
    // Statements: BoundBlock, BoundLet, BoundExpressionStatement, BoundReturn, BoundIf, BoundWhile.
    ```

- Each bound node keeps a reference to its **syntax**, for error spans in later stages and for debug info.
- **Conversions are nodes.** An `i32` widened to `i64`, or a literal given a type, becomes a `BoundConversion`, so code generation never has to work out an implicit conversion.
- **Operators are resolved**: `BoundBinaryOperator` says "signed 32-bit add" or "float compare less-than", not just `+`.

## Modules and imports

Once there is more than one file with its own namespace:

- Give each module its own scope under the global one, and an `import` adds the imported module's public symbols (or the module's name, for `math.sqrt`) to the importing scope.
- Run pass 1 for **every module** before pass 2 for any, so imports in both directions work.
- Report import cycles, or define an order for running modules' global initialisers, before allowing them.

## C++ tips

- **One owner for everything the binder makes**: symbols, scopes, and bound nodes go into the binder's `std::vector<std::shared_ptr<void>>` through `Make<T>`, and everything else holds plain pointers. `shared_ptr<void>` remembers each object's real destructor, so one list can own every type.
- **Pass 2 writes into symbols made in pass 1** (`f->parameters`, `s->fields`), so the binder works with non-`const` pointers; later stages see `const FunctionSymbol*` and cannot change them.
- `dynamic_cast` reads well for "which kind of symbol is this?", where there are only a few kinds. For syntax and bound nodes, switch on a `kind` field instead, as on the [syntax trees](syntax-trees.md#walking-trees) page.
- `std::unordered_map<std::string, Symbol*>` needs a `std::string` to look up. With C++20 heterogeneous lookup (a hash and equality with `is_transparent`), `find` takes the token's `std::string_view` without allocating.
- For "did you mean" suggestions, compute the edit distance against names visible from the scope, and suggest only when it is at most a third of the name's length. Report the suggestion as a [fix](source-diagnostics.md#reporting), so an editor can apply it.

## C# tips

- Make symbols `sealed class`es under `abstract class Symbol`, and fill in the parts known later (a function's body, a struct's fields) through `internal` setters used only by the binder. Everything after the binder treats them as read-only.
- A `Scope` is a `Dictionary<string, Symbol>` plus a `Scope? Parent`. Allocating one per block is fine: they are small and short-lived.
- For "did you mean" suggestions, compute the edit distance (Levenshtein, or Damerau-Levenshtein for swapped letters) against names visible from the scope, and suggest only when the distance is at most a third of the name's length. `BindName` above attaches it as a fix.
- Keep the binder's output in a `BoundProgram` record: the global scope, the function bodies (`ImmutableDictionary<FunctionSymbol, BoundBlock>`), and the diagnostics.
- An editor needs the reverse map too: from a syntax node to its symbol, for hover and go-to-definition. Record it in a `Dictionary<SyntaxNode, Symbol>` while binding, rather than recomputing it.
