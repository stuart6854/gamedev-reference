# Syntax trees

The parser's output, and the input to every later stage. The design choices here are how much of the source the tree keeps, whether it can change, and how code walks it.

## Concrete or abstract

| | Concrete syntax tree (full fidelity) | Abstract syntax tree |
| --- | --- | --- |
| Keeps | every token, including `(`, `,`, `;`, and (through trivia) comments and whitespace | only what affects meaning |
| `(a + b)` | a `Parenthesized` node holding both parentheses and the inner `Binary` | the `Binary` node |
| Can reproduce the source exactly | yes | no |
| Needed by | formatters, refactorings, a language server, errors that point at a `)` | a compiler that only compiles |

A good middle for a new compiler: **syntax nodes that keep their tokens** (so spans and missing-token errors are exact), plus a separate **bound tree** from the [binder](binding.md) that drops the punctuation and adds symbols and types. The syntax tree is what was written; the bound tree is what it means.

## Node design

=== "C++"

    ```cpp
    using SyntaxChild = std::variant<const SyntaxNode*, const Token*>;   // a node or a token

    struct SyntaxNode
    {
        explicit SyntaxNode(SyntaxKind kind) : kind(kind) {}
        virtual ~SyntaxNode() = default;
        virtual void GetChildren(std::vector<SyntaxChild>& out) const = 0;   // nodes and tokens, in source order

        TextSpan Span() const                           // from the first and last token below this node
        {
            const Token* first = FirstToken();          // depth first through GetChildren
            const Token* last = LastToken();
            return first ? TextSpan::FromBounds(first->span.start, last->span.End()) : TextSpan{};
        }

        const SyntaxKind kind;                          // SyntaxKind has a value per node type as well as per token
    };

    struct ExpressionSyntax : SyntaxNode { using SyntaxNode::SyntaxNode; };
    // StatementSyntax, ItemSyntax, and TypeSyntax are the same

    struct BinarySyntax final : ExpressionSyntax
    {
        BinarySyntax(ExpressionSyntax* left, Token op, ExpressionSyntax* right)
            : ExpressionSyntax(SyntaxKind::BinaryExpression), left(left), op(op), right(right) {}
        void GetChildren(std::vector<SyntaxChild>& out) const override { out.insert(out.end(), { left, &op, right }); }
        ExpressionSyntax* const left;
        const Token op;
        ExpressionSyntax* const right;
    };

    struct CallSyntax final : ExpressionSyntax
    {
        CallSyntax(ExpressionSyntax* callee, Token open, SeparatedList<ExpressionSyntax> arguments, Token close)
            : ExpressionSyntax(SyntaxKind::CallExpression), callee(callee), open(open), arguments(std::move(arguments)), close(close) {}
        void GetChildren(std::vector<SyntaxChild>& out) const override
        {
            out.insert(out.end(), { callee, &open });
            arguments.AppendTo(out);
            out.push_back(&close);
        }
        ExpressionSyntax* const callee;
        const Token open;
        const SeparatedList<ExpressionSyntax> arguments;
        const Token close;
    };

    struct LetSyntax final : StatementSyntax
    {
        LetSyntax(Token keyword, Token name, std::optional<Token> colon, TypeSyntax* type, std::optional<Token> equals,
                  ExpressionSyntax* initializer, Token semicolon)
            : StatementSyntax(keyword.kind == SyntaxKind::VarKeyword ? SyntaxKind::VarStatement : SyntaxKind::LetStatement),
              keyword(keyword), name(name), colon(colon), type(type), equals(equals), initializer(initializer), semicolon(semicolon) {}
        void GetChildren(std::vector<SyntaxChild>& out) const override
        {
            out.insert(out.end(), { &keyword, &name });
            AppendIf(out, colon);
            AppendIf(out, type);
            AppendIf(out, equals);
            AppendIf(out, initializer);
            out.push_back(&semicolon);
        }
        const Token keyword, name;
        const std::optional<Token> colon;
        TypeSyntax* const type;
        const std::optional<Token> equals;
        ExpressionSyntax* const initializer;
        const Token semicolon;
    };

    template <class T> static void AppendIf(std::vector<SyntaxChild>& out, const T* p) { if (p) out.push_back(p); }
    static void AppendIf(std::vector<SyntaxChild>& out, const std::optional<Token>& t) { if (t) out.push_back(&*t); }
    ```

=== "C#"

    ```csharp
    public readonly struct SyntaxNodeOrToken          // a node or a token
    {
        public SyntaxNode? Node { get; }
        public Token Token { get; }
        public bool IsToken => Node is null;
        SyntaxNodeOrToken(SyntaxNode? node, Token token) { Node = node; Token = token; }
        public static implicit operator SyntaxNodeOrToken(SyntaxNode node) => new(node, default);
        public static implicit operator SyntaxNodeOrToken(Token token) => new(null, token);
    }

    public abstract class SyntaxNode
    {
        public abstract SyntaxKind Kind { get; }
        public abstract IEnumerable<SyntaxNodeOrToken> GetChildren();   // nodes and tokens, in source order

        public TextSpan Span                           // from the first and last token below this node
        {
            get
            {
                var tokens = Tokens().ToList();
                return tokens.Count == 0 ? default : TextSpan.FromBounds(tokens[0].Span.Start, tokens[^1].Span.End);
            }
        }

        public IEnumerable<Token> Tokens()
        {
            foreach (var child in GetChildren())
            {
                if (child.IsToken) yield return child.Token;
                else foreach (var t in child.Node!.Tokens()) yield return t;
            }
        }
    }

    public abstract class ExpressionSyntax : SyntaxNode;
    // StatementSyntax, ItemSyntax, and TypeSyntax are the same

    public sealed class BinarySyntax(ExpressionSyntax left, Token op, ExpressionSyntax right) : ExpressionSyntax
    {
        public ExpressionSyntax Left => left;
        public Token Operator => op;
        public ExpressionSyntax Right => right;
        public override SyntaxKind Kind => SyntaxKind.BinaryExpression;
        public override IEnumerable<SyntaxNodeOrToken> GetChildren() { yield return left; yield return op; yield return right; }
    }

    public sealed class CallSyntax(ExpressionSyntax callee, Token open, SeparatedSyntaxList<ExpressionSyntax> arguments, Token close) : ExpressionSyntax
    {
        public ExpressionSyntax Callee => callee;
        public SeparatedSyntaxList<ExpressionSyntax> Arguments => arguments;
        public override SyntaxKind Kind => SyntaxKind.CallExpression;
        public override IEnumerable<SyntaxNodeOrToken> GetChildren()
        {
            yield return callee; yield return open;
            foreach (var child in arguments.GetChildren()) yield return child;
            yield return close;
        }
    }

    public sealed class LetSyntax(Token keyword, Token name, Token? colon, TypeSyntax? type, Token? equals, ExpressionSyntax? initializer,
                                  Token semicolon) : StatementSyntax
    {
        public Token Keyword => keyword;
        public Token Name => name;
        public TypeSyntax? Type => type;
        public ExpressionSyntax? Initializer => initializer;
        public override SyntaxKind Kind => keyword.Kind == SyntaxKind.VarKeyword ? SyntaxKind.VarStatement : SyntaxKind.LetStatement;
        public override IEnumerable<SyntaxNodeOrToken> GetChildren()
        {
            yield return keyword; yield return name;
            if (colon is Token c) yield return c;
            if (type is not null) yield return type;
            if (equals is Token e) yield return e;
            if (initializer is not null) yield return initializer;
            yield return semicolon;
        }
    }
    ```

- **One node type per construct**, grouped under `ExpressionSyntax`, `StatementSyntax`, `ItemSyntax`, and `TypeSyntax`. A generic `Node { kind, children[] }` is easy to build and miserable to use.
- **Immutable after parsing.** A tree that cannot change can be shared between threads, cached, and compared in tests. Later stages put their results in a new tree or in side tables.
- **Spans are derived** from the first and last tokens, so they are always right, including for nodes that start with a missing token. Computing them on each call walks the subtree; cache them in a field if a profiler shows it matters.
- **Optional parts are explicit**: a function's return clause is null when absent, not an empty list, so "no return type" and "a return type that failed to parse" stay different.

### Parent pointers

The binder and the language server often ask "what contains this node?". Two ways to answer it:

- Fill in a **parent field** after parsing, in one walk over the tree. Simple; makes the node mutable for that one moment.
- Roslyn's **red-green tree**: an immutable "green" tree without parents or positions, wrapped on demand by "red" nodes that know both. It allows sharing unchanged subtrees during incremental re-parsing. Worth it for an editor working on large files; more than a first compiler needs.

### Information about nodes

Results of analysis (the symbol a name refers to, the type of an expression, whether a variable is captured) go in **side tables** keyed by node, or straight into the bound tree. Do not add mutable `Symbol` or `Type` fields to syntax nodes: it ties the parser to the binder, and breaks as soon as one tree is bound twice (an editor checking the same file with different settings).

## Walking trees

Most passes are a recursive function with one case per node kind:

=== "C++"

    ```cpp
    const BoundExpression* Binder::BindExpression(const ExpressionSyntax* syntax, const Scope& scope)
    {
        switch (syntax->kind)                           // the kind says which node type it is
        {
        case SyntaxKind::LiteralExpression: return BindLiteral(static_cast<const LiteralSyntax*>(syntax));
        case SyntaxKind::NameExpression:    return BindName(static_cast<const NameSyntax*>(syntax), scope);
        case SyntaxKind::BinaryExpression:  return BindBinary(static_cast<const BinarySyntax*>(syntax), scope);
        case SyntaxKind::CallExpression:    return BindCall(static_cast<const CallSyntax*>(syntax), scope);
        // ... one case per expression kind
        case SyntaxKind::MissingExpression: return Make<BoundError>(syntax);   // the parser has reported it
        default: throw std::logic_error(std::format("unexpected expression {}", KindName(syntax->kind)));
        }
    }
    ```

=== "C#"

    ```csharp
    BoundExpression BindExpression(ExpressionSyntax syntax, Scope scope) => syntax switch
    {
        LiteralSyntax l => BindLiteral(l),
        NameSyntax n => BindName(n, scope),
        BinarySyntax b => BindBinary(b, scope),
        CallSyntax c => BindCall(c, scope),
        // ... one case per expression type
        MissingExpressionSyntax => new BoundError(syntax),       // the parser has reported it
        _ => throw new UnreachableException($"unexpected expression {syntax.Kind}"),
    };
    ```

| Style | How | Trade-off |
| --- | --- | --- |
| Pattern matching | `switch` on node type in each pass | Short and direct; the compiler can warn about missing cases if the hierarchy is closed |
| Visitor | a `Visit(XxxSyntax)` method per type, with `Accept` on each node | A base walker can do the default recursion, so a pass overrides only what it cares about |
| Generic walk | `for child in node.children(): walk(child)` | Good for "find all names" queries, useless for anything that needs to know the node's shape |

A **rewriter** is a walker that returns a node, rebuilding a parent only when one of its children changed. [Lowering](lowering.md) is a chain of rewriters over the bound tree.

## Printing trees

A tree printer is the most useful debugging and testing tool in the compiler:

```text
Function
├── FnKeyword
├── IdentifierToken "sum_to"
├── OpenParenToken
├── Parameter
│   ├── IdentifierToken "n"
│   ├── ColonToken
│   └── NamedType
│       └── IdentifierToken "i32"
├── CloseParenToken
├── ReturnClause
│   ├── ArrowToken
│   └── NamedType
│       └── IdentifierToken "i32"
└── Block
    ├── OpenBraceToken
    ├── VarStatement ...
```

=== "C++"

    ```cpp
    void PrintTree(std::string& out, const SyntaxChild& child, const std::string& indent, bool last)
    {
        out += indent + (last ? "└── " : "├── ");
        if (auto* token = std::get_if<const Token*>(&child))
        {
            out += KindName((*token)->kind);
            if ((*token)->kind <= SyntaxKind::StringLiteralToken) out += std::format(" \"{}\"", (*token)->text);  // identifiers, literals
            if ((*token)->isMissing) out += " (missing)";
            out += '\n';
            return;
        }
        const SyntaxNode* node = std::get<const SyntaxNode*>(child);
        out += std::string(KindName(node->kind)) + '\n';
        auto children = node->Children();
        for (size_t i = 0; i < children.size(); i++)
            PrintTree(out, children[i], indent + (last ? "    " : "│   "), i == children.size() - 1);
    }

    std::string PrintTree(const SyntaxNode& root)                  // the root on its own line, then its children
    {
        std::string out = std::string(KindName(root.kind)) + '\n';
        auto children = root.Children();
        for (size_t i = 0; i < children.size(); i++) PrintTree(out, children[i], "", i == children.size() - 1);
        return out;
    }
    ```

=== "C#"

    ```csharp
    public static class SyntaxPrinter
    {
        public static string Print(SyntaxNode node)
        {
            var output = new StringBuilder();
            output.Append(node.Kind).Append('\n');
            PrintChildren(output, node, "");
            return output.ToString();
        }

        static void PrintChildren(StringBuilder output, SyntaxNode node, string indent)
        {
            var children = node.GetChildren().ToList();
            for (int i = 0; i < children.Count; i++)
            {
                bool last = i == children.Count - 1;
                output.Append(indent).Append(last ? "└── " : "├── ");
                if (children[i].Node is SyntaxNode child)
                {
                    output.Append(child.Kind).Append('\n');
                    PrintChildren(output, child, indent + (last ? "    " : "│   "));
                }
                else
                {
                    Token token = children[i].Token;
                    output.Append(token.Kind);
                    if (token.Text is not null) output.Append(" \"").Append(token.Text).Append('"');
                    if (token.IsMissing) output.Append(" (missing)");
                    output.Append('\n');
                }
            }
        }
    }
    ```

The printed tree is what [snapshot tests](testing.md#snapshot-tests) compare against. Print missing tokens clearly, so recovery shows up in the snapshot.

## Pretty-printing source

The reverse: turn a tree back into code. With a full-fidelity tree it is just the tokens and trivia in order, and **round-tripping** (`print(parse(text)) == text`) is a test that catches lost tokens. A formatter goes further, ignoring the original trivia and choosing its own spacing and line breaks.

## C++ tips

- **Ownership**: the parser owns the nodes (see [the parser's C++ tips](parser.md#c-tips)), and nodes point at each other with plain pointers. Keep the parser's node list alive as long as anything reads the tree.
- **Fields are `const`**, set by the constructor, so a tree cannot change after parsing.
- **Dispatch on `kind`** with a `switch` and `static_cast`, as above: cheaper than `dynamic_cast` and visible in one place. With `-Wswitch` (on in `-Wall`), a `switch` over the enum without a `default` warns about a missing kind.
- `GetChildren` appends into a caller's vector rather than returning one, so a walk can reuse one buffer. `std::variant<const SyntaxNode*, const Token*>` keeps tokens and nodes in one list, in source order.
- Tokens are stored by value in nodes, and children point at them: a token's address is stable because nodes never move once allocated.

## C# tips

- Make nodes `sealed class`es with primary constructors, as above. A `record` gives value equality, which you do not want for nodes: two `1 + 1` nodes in different places are different nodes.
- Generate the boilerplate. Each node type's `Kind`, `GetChildren()`, a visitor method, and an `Update(...)` for rewriters are mechanical. A [source generator](../../csharp/roslyn/source-generators.md) that reads the node classes, or an XML description of the nodes (Roslyn's approach), keeps them consistent.
- `switch` expressions over a closed hierarchy do not warn about missing cases in C# yet. End each with `_ => throw new UnreachableException(...)`, as above, so a new node kind fails loudly in tests.
- Side tables: `Dictionary<SyntaxNode, Symbol>` uses reference equality for classes that do not override `Equals`, which is what you want. `ConditionalWeakTable` lets entries die with the tree, for caches in a long-running language server.
- For tree printing, `StringBuilder` and the box-drawing characters `├──`, `└──`, and `│` work in any UTF-8 terminal and in snapshot files.
