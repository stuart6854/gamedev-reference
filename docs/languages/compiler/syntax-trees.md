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

```text
SyntaxNode (abstract) {
    kind
    span            // computed from the first and last token below this node
    children()      // nodes and tokens, in source order
}

Binary : Expression     { left, operator_token, right }
Call : Expression       { callee, open_paren, arguments (with separators), close_paren }
Let : Statement         { let_keyword, name_token, type_clause?, equals_token, initializer, semicolon }
Function : Item         { fn_keyword, name_token, open_paren, parameters, close_paren, return_clause?, body }
```

- **One node type per construct**, grouped under `Expression`, `Statement`, `Item`, and `TypeSyntax`. A generic `Node { kind, children[] }` is easy to build and miserable to use.
- **Immutable after parsing.** A tree that cannot change can be shared between threads, cached, and compared in tests. Later stages put their results in a new tree or in side tables.
- **Spans are derived** from the first and last tokens, so they are always right, including for nodes that start with a missing token.
- **Optional parts are explicit**: `return_clause` is absent, not an empty list, so "no return type" and "a return type that failed to parse" stay different.

### Parent pointers

The binder and the language server often ask "what contains this node?". Two ways to answer it:

- Fill in a **parent field** after parsing, in one walk over the tree. Simple; makes the node mutable for that one moment.
- Roslyn's **red-green tree**: an immutable "green" tree without parents or positions, wrapped on demand by "red" nodes that know both. It allows sharing unchanged subtrees during incremental re-parsing. Worth it for an editor working on large files; more than a first compiler needs.

### Information about nodes

Results of analysis (the symbol a name refers to, the type of an expression, whether a variable is captured) go in **side tables** keyed by node, or straight into the bound tree. Do not add mutable `Symbol` or `Type` fields to syntax nodes: it ties the parser to the binder, and breaks as soon as one tree is bound twice (an editor checking the same file with different settings).

## Walking trees

Most passes are a recursive function with one case per node kind:

```text
check(node):
    switch node:
        Binary b:  check(b.left); check(b.right); ...
        Call c:    check(c.callee); for a in c.arguments: check(a); ...
        Name n:    ...
        ...
        default:   internal_error("unhandled node kind {node.kind}")
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
├── FnKeyword "fn"
├── IdentifierToken "sum_to"
├── ParameterList
│   └── Parameter
│       ├── IdentifierToken "n"
│       ├── ColonToken
│       └── Type "i32"
├── ReturnClause
│   └── Type "i32"
└── Block
    ├── VarStatement ...
```

```text
print(node, indent, last):
    line = indent + ("└── " if last else "├── ") + node.kind
    if node is a token: line += " " + quote(token.text); if missing: line += " (missing)"
    output(line)
    children = node.children()
    for i, child in children:
        print(child, indent + ("    " if last else "│   "), i == len(children) - 1)
```

The printed tree is what [snapshot tests](testing.md#snapshot-tests) compare against. Print missing tokens clearly, so recovery shows up in the snapshot.

## Pretty-printing source

The reverse: turn a tree back into code. With a full-fidelity tree it is just the tokens and trivia in order, and **round-tripping** (`print(parse(text)) == text`) is a test that catches lost tokens. A formatter goes further, ignoring the original trivia and choosing its own spacing and line breaks.

## C# tips

- Make nodes `sealed class`es deriving from `abstract class SyntaxNode`, with `public required` properties set at construction. A `record` gives value equality, which you do not want for nodes: two `1 + 1` nodes in different places are different nodes.
- Generate the boilerplate. Each node type's `Kind`, `GetChildren()`, a visitor method, and an `Update(...)` for rewriters are mechanical. A [source generator](../../csharp/roslyn/source-generators.md) that reads the node classes, or an XML description of the nodes (Roslyn's approach), keeps them consistent.
- `switch` expressions over a closed hierarchy do not warn about missing cases in C# yet. End each with `_ => throw new UnreachableException($"Unexpected node {node.Kind}")` so a new node kind fails loudly in tests.
- Side tables: `Dictionary<SyntaxNode, Symbol>` uses reference equality for classes that do not override `Equals`, which is what you want. `ConditionalWeakTable` lets entries die with the tree, for caches in a long-running language server.
- For tree printing, `StringBuilder` and the box-drawing characters `├──`, `└──`, and `│` work in any UTF-8 terminal and in snapshot files.
