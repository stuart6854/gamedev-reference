# Lowering and control flow

**Lowering** rewrites the bound tree into a smaller language: fewer kinds of node, and control flow made of labels and jumps. Code generation then handles only a handful of constructs, and the checks that need to see control flow (missing returns, uninitialised variables) run on a graph instead of a tree.

## Desugaring

Each rewrite replaces a convenient construct with plainer ones the backend already handles. Run them as **rewriters** over the bound tree, after type checking, so errors still refer to what the user wrote.

| Written | Lowered to |
| --- | --- |
| `x += e` | `x = x + e` (evaluating the address of `x` once, if it has side effects) |
| `for i in 0..n { body }` | `var i = 0; while i < n { body; i = i + 1; }`, with `continue` jumping to the increment |
| `a && b` | `if a { b } else { false }`, as jumps (below) |
| `if` as an expression | a temporary local, assigned in each branch |
| method call `v.len()` | `Vec2_len(&v)` |
| generic call `max<i32>(a, b)` | a call to the monomorphised `max_i32` |

Keep each rewrite small and separate. Many short passes are easier to test than one large one.

## Labels and jumps

Structured statements become **labels**, **gotos**, and **conditional gotos**:

```text
while cond { body }               if cond { then } else { else }

  goto check                         goto_if_false cond, else_label
continue_label:                      then
  body                               goto end_label
check:                             else_label:
  goto_if_true cond, continue_label   else
break_label:                       end_label:
```

=== "C++"

    ```cpp
    // Members used here: result_ (the flat statement list), Emit<T>(...) (create a statement and append it),
    // and NewLabel(name) (a fresh label, numbered for debugging).

    void LowerWhile(const BoundWhile* w)
    {
        const BoundLabel* continueLabel = NewLabel("while_continue");
        const BoundLabel* check = NewLabel("while_check");
        const BoundLabel* breakLabel = NewLabel("while_break");
        // break and continue inside the body would jump to breakLabel and continueLabel (check, for continue)
        Emit<BoundGoto>(w->syntax, check);
        Emit<BoundLabelStatement>(w->syntax, continueLabel);
        LowerStatement(w->body);
        Emit<BoundLabelStatement>(w->syntax, check);
        LowerCondition(w->condition, continueLabel, /*jumpIfTrue*/ true);
        Emit<BoundLabelStatement>(w->syntax, breakLabel);
    }

    void LowerIf(const BoundIf* i)
    {
        const BoundLabel* end = NewLabel("if_end");
        if (!i->elseBranch)
        {
            LowerCondition(i->condition, end, /*jumpIfTrue*/ false);   // goto_if_false cond, end
            LowerStatement(i->then);
            Emit<BoundLabelStatement>(i->syntax, end);
            return;
        }
        const BoundLabel* elseLabel = NewLabel("if_else");
        LowerCondition(i->condition, elseLabel, false);
        LowerStatement(i->then);
        Emit<BoundGoto>(i->syntax, end);
        Emit<BoundLabelStatement>(i->syntax, elseLabel);
        LowerStatement(i->elseBranch);
        Emit<BoundLabelStatement>(i->syntax, end);
    }
    ```

=== "C#"

    ```csharp
    // Members used here: _output (the flat statement list) and NewLabel(name) (a fresh label, numbered for debugging).

    void LowerWhile(BoundWhile w)
    {
        BoundLabel continueLabel = NewLabel("while_continue"), check = NewLabel("while_check"), breakLabel = NewLabel("while_break");
        // break and continue inside the body would jump to breakLabel and continueLabel (check, for continue)
        _output.Add(new BoundGoto(w.Syntax, check));
        _output.Add(new BoundLabelStatement(w.Syntax, continueLabel));
        LowerStatement(w.Body);
        _output.Add(new BoundLabelStatement(w.Syntax, check));
        LowerCondition(w.Condition, continueLabel, jumpIfTrue: true);
        _output.Add(new BoundLabelStatement(w.Syntax, breakLabel));
    }

    void LowerIf(BoundIf i)
    {
        BoundLabel end = NewLabel("if_end");
        if (i.Else is null)
        {
            LowerCondition(i.Condition, end, jumpIfTrue: false);        // goto_if_false cond, end
            LowerStatement(i.Then);
            _output.Add(new BoundLabelStatement(i.Syntax, end));
            return;
        }
        BoundLabel elseLabel = NewLabel("if_else");
        LowerCondition(i.Condition, elseLabel, jumpIfTrue: false);
        LowerStatement(i.Then);
        _output.Add(new BoundGoto(i.Syntax, end));
        _output.Add(new BoundLabelStatement(i.Syntax, elseLabel));
        LowerStatement(i.Else);
        _output.Add(new BoundLabelStatement(i.Syntax, end));
    }
    ```

Conditions lower to jumps directly, which is where short-circuit operators go: `a && b` jumps away as soon as `a` is false, so `b` is only evaluated when needed. A constant condition (`while true`) becomes a plain jump, or nothing, so the flow checks below see the real shape of the loop.

=== "C++"

    ```cpp
    void LowerCondition(const BoundExpression* condition, const BoundLabel* label, bool jumpIfTrue)
    {
        if (auto* u = dynamic_cast<const BoundUnary*>(condition); u && u->op == UnaryOperatorKind::LogicalNot)
            return LowerCondition(u->operand, label, !jumpIfTrue);
        if (auto* b = dynamic_cast<const BoundBinary*>(condition);
            b && (b->op->kind == BinaryOperatorKind::LogicalAnd || b->op->kind == BinaryOperatorKind::LogicalOr))
        {
            bool isAnd = b->op->kind == BinaryOperatorKind::LogicalAnd;
            if (isAnd != jumpIfTrue)                    // && jumping if false, || jumping if true: either side decides
            {
                LowerCondition(b->left, label, jumpIfTrue);
                LowerCondition(b->right, label, jumpIfTrue);
                return;
            }
            const BoundLabel* skip = NewLabel("skip");  // a && b, jump if true: both must hold
            LowerCondition(b->left, skip, !isAnd);      // the left side decides it the other way: skip
            LowerCondition(b->right, label, jumpIfTrue);
            Emit<BoundLabelStatement>(b->syntax, skip);
            return;
        }
        if (auto* literal = dynamic_cast<const BoundLiteral*>(condition); literal && std::holds_alternative<bool>(literal->value))
        {
            if (std::get<bool>(literal->value) == jumpIfTrue) Emit<BoundGoto>(condition->syntax, label);   // `while true`
            return;                                     // a constant: a plain jump, or none
        }
        Emit<BoundConditionalGoto>(condition->syntax, condition, label, jumpIfTrue);
    }
    ```

=== "C#"

    ```csharp
    void LowerCondition(BoundExpression condition, BoundLabel label, bool jumpIfTrue)
    {
        switch (condition)
        {
            case BoundUnary { Operator: UnaryOperatorKind.LogicalNot } negation:
                LowerCondition(negation.Operand, label, !jumpIfTrue);
                return;
            case BoundBinary { Operator.Kind: BinaryOperatorKind.LogicalAnd } both when !jumpIfTrue:
                LowerCondition(both.Left, label, false);                  // either side false: jump
                LowerCondition(both.Right, label, false);
                return;
            case BoundBinary { Operator.Kind: BinaryOperatorKind.LogicalOr } either when jumpIfTrue:
                LowerCondition(either.Left, label, true);                    // either side true: jump
                LowerCondition(either.Right, label, true);
                return;
            case BoundBinary { Operator.Kind: BinaryOperatorKind.LogicalAnd or BinaryOperatorKind.LogicalOr } b:
            {
                BoundLabel skip = NewLabel("skip");                       // a && b, jump if true: both must hold
                bool isAnd = b.Operator.Kind == BinaryOperatorKind.LogicalAnd;
                LowerCondition(b.Left, skip, jumpIfTrue: !isAnd);        // a decides it the other way: skip
                LowerCondition(b.Right, label, jumpIfTrue);
                _output.Add(new BoundLabelStatement(b.Syntax, skip));
                return;
            }
            case BoundLiteral { Value: bool constant }:                   // `while true`: fold to a plain jump, or none
                if (constant == jumpIfTrue) _output.Add(new BoundGoto(condition.Syntax, label));
                return;
            default:
                _output.Add(new BoundConditionalGoto(condition.Syntax, condition, label, jumpIfTrue));
                return;
        }
    }
    ```

`&&` and `||` outside a condition (`let both = a && b;`) can stay operators, which the [evaluator](evaluator.md#the-loop) and the code generator short-circuit themselves. Lowering them to jumps there too needs a temporary local, assigned in each branch, and care to keep evaluation order when the operator is nested inside a call's arguments.

After lowering, a function body is a **flat list** of statements: expressions, assignments, labels, gotos, conditional gotos, and returns.

## Control-flow graph

Split the flat list into **basic blocks**: runs of statements with one entry at the top and one exit at the bottom.

=== "C++"

    ```cpp
    struct BasicBlock
    {
        std::string name;
        std::vector<const BoundStatement*> statements = {};
        std::vector<BasicBlock*> successors = {}, predecessors = {};
    };

    struct ControlFlowGraph
    {
        BasicBlock entry{ "entry" }, exit{ "exit" };
        std::vector<std::unique_ptr<BasicBlock>> blocks;

        static std::unique_ptr<ControlFlowGraph> Build(const std::vector<const BoundStatement*>& statements)
        {
            auto graph = std::make_unique<ControlFlowGraph>();
            auto current = std::make_unique<BasicBlock>();
            auto finish = [&] {
                current->name = std::format("b{}", graph->blocks.size());
                graph->blocks.push_back(std::move(current));
                current = std::make_unique<BasicBlock>();
            };
            for (const BoundStatement* s : statements)
            {
                if (dynamic_cast<const BoundLabelStatement*>(s))   // a label starts a block
                {
                    if (!current->statements.empty()) finish();
                    current->statements.push_back(s);
                    continue;
                }
                current->statements.push_back(s);
                if (dynamic_cast<const BoundGoto*>(s) || dynamic_cast<const BoundConditionalGoto*>(s) || dynamic_cast<const BoundReturn*>(s))
                    finish();                               // a jump ends one
            }
            if (!current->statements.empty()) finish();

            std::unordered_map<const BoundLabel*, BasicBlock*> blockOfLabel;
            for (auto& b : graph->blocks)
                if (auto* l = dynamic_cast<const BoundLabelStatement*>(b->statements[0])) blockOfLabel[l->label] = b.get();

            graph->Connect(&graph->entry, graph->blocks.empty() ? &graph->exit : graph->blocks[0].get());
            for (size_t i = 0; i < graph->blocks.size(); i++)   // edges
            {
                BasicBlock* b = graph->blocks[i].get();
                BasicBlock* next = i + 1 < graph->blocks.size() ? graph->blocks[i + 1].get() : &graph->exit;
                const BoundStatement* last = b->statements.back();
                if (auto* g = dynamic_cast<const BoundGoto*>(last)) graph->Connect(b, blockOfLabel.at(g->label));
                else if (auto* c = dynamic_cast<const BoundConditionalGoto*>(last))
                {
                    graph->Connect(b, blockOfLabel.at(c->label));
                    graph->Connect(b, next);
                }
                else if (dynamic_cast<const BoundReturn*>(last)) graph->Connect(b, &graph->exit);
                else graph->Connect(b, next);               // falls through
            }
            return graph;
        }

        void Connect(BasicBlock* from, BasicBlock* to)
        {
            if (std::find(from->successors.begin(), from->successors.end(), to) != from->successors.end()) return;
            from->successors.push_back(to);
            to->predecessors.push_back(from);
        }
    };
    ```

=== "C#"

    ```csharp
    public sealed class BasicBlock(string name)
    {
        public string Name => name;
        public List<BoundStatement> Statements { get; } = [];
        public List<BasicBlock> Successors { get; } = [];
        public List<BasicBlock> Predecessors { get; } = [];
        public override string ToString() => name;
    }

    public sealed class ControlFlowGraph
    {
        public BasicBlock Entry { get; } = new("entry");
        public BasicBlock Exit { get; } = new("exit");
        public List<BasicBlock> Blocks { get; } = [];

        public static ControlFlowGraph Build(ImmutableArray<BoundStatement> statements)
        {
            var graph = new ControlFlowGraph();
            var current = new BasicBlock("b0");
            foreach (var s in statements)
            {
                if (s is BoundLabelStatement)                                // a label starts a block
                {
                    if (current.Statements.Count > 0) graph.Blocks.Add(current);
                    current = new BasicBlock($"b{graph.Blocks.Count}");
                    current.Statements.Add(s);
                    continue;
                }
                current.Statements.Add(s);
                if (s is BoundGoto or BoundConditionalGoto or BoundReturn) // a jump ends one
                {
                    graph.Blocks.Add(current);
                    current = new BasicBlock($"b{graph.Blocks.Count}");
                }
            }
            if (current.Statements.Count > 0) graph.Blocks.Add(current);

            var blockOfLabel = new Dictionary<BoundLabel, BasicBlock>();
            foreach (var b in graph.Blocks)
                if (b.Statements[0] is BoundLabelStatement l) blockOfLabel[l.Label] = b;

            graph.Connect(graph.Entry, graph.Blocks.Count > 0 ? graph.Blocks[0] : graph.Exit);
            for (int i = 0; i < graph.Blocks.Count; i++)                     // edges
            {
                BasicBlock b = graph.Blocks[i];
                BasicBlock next = i + 1 < graph.Blocks.Count ? graph.Blocks[i + 1] : graph.Exit;
                switch (b.Statements[^1])
                {
                    case BoundGoto g: graph.Connect(b, blockOfLabel[g.Label]); break;
                    case BoundConditionalGoto c: graph.Connect(b, blockOfLabel[c.Label]); graph.Connect(b, next); break;
                    case BoundReturn: graph.Connect(b, graph.Exit); break;
                    default: graph.Connect(b, next); break;                   // falls through
                }
            }
            return graph;
        }

        void Connect(BasicBlock from, BasicBlock to)
        {
            if (from.Successors.Contains(to)) return;
            from.Successors.Add(to);
            to.Predecessors.Add(from);
        }
    }
    ```

These blocks map one-to-one onto [LLVM basic blocks](llvmsharp.md#control-flow), which is the main reason to build them here.

## Flow checks

With the graph, several checks become simple searches:

**Unreachable code.** Walk from the entry block; any block not visited is dead. Warn once, at its first statement: "unreachable code".

**Missing return.** In a function that returns a value, if the **exit** can be reached from any block that falls through without a `return`, report "not all code paths return a value" at the function's closing brace. A `void` function instead gets an implicit `return` at the end.

```text
fn sign(x: i32) -> i32 {
    if x > 0 { return 1; }
    if x < 0 { return -1; }
}                                   // error: the block after the second `if` falls through to exit
```

**Definite assignment.** For `var x;` without an initialiser, a use of `x` is an error if some path from the entry reaches it without an assignment:

=== "C++"

    ```cpp
    static void CheckDefiniteAssignment(const ControlFlowGraph& graph, const std::unordered_set<const BasicBlock*>& reachable,
                                        DiagnosticBag& diagnostics)
    {
        std::unordered_map<const LocalSymbol*, size_t> index;
        for (auto& b : graph.blocks)
            for (const BoundStatement* s : b->statements)
                if (auto* let = dynamic_cast<const BoundLet*>(s)) index.try_emplace(let->local, index.size());
        if (index.empty()) return;

        std::unordered_map<const BasicBlock*, Bits> assignedOut{ { &graph.entry, Bits(index.size(), false) } };
        for (auto& b : graph.blocks) assignedOut[b.get()] = Bits(index.size(), true);   // "all": loops then converge

        for (bool changed = true; changed;)             // repeat until nothing changes
        {
            changed = false;
            for (auto& b : graph.blocks)
            {
                Bits assigned = AssignedIn(*b, assignedOut, index.size());
                Walk(*b, assigned, index, nullptr);
                if (assigned != assignedOut[b.get()]) { assignedOut[b.get()] = std::move(assigned); changed = true; }
            }
        }
        for (auto& b : graph.blocks)                    // then report reads before assignment
            if (reachable.contains(b.get()))
            {
                Bits assigned = AssignedIn(*b, assignedOut, index.size());
                Walk(*b, assigned, index, &diagnostics);
            }
    }

    static Bits AssignedIn(const BasicBlock& b, std::unordered_map<const BasicBlock*, Bits>& assignedOut, size_t count)
    {
        Bits result(count, true);                       // the intersection over predecessors
        for (const BasicBlock* p : b.predecessors)
            for (size_t i = 0; i < count; i++) result[i] = result[i] && assignedOut[p][i];
        return result;
    }

    // Walk(block, assigned, index, report) goes through the block's statements in order: an assignment or a `let` with an
    // initialiser sets the local's bit, `&x` sets it too (it may be written through), and with `report` set, a read of a
    // local whose bit is clear is reported.
    ```

=== "C#"

    ```csharp
    static void CheckDefiniteAssignment(ControlFlowGraph graph, HashSet<BasicBlock> reachable, DiagnosticBag diagnostics)
    {
        var locals = graph.Blocks.SelectMany(b => b.Statements).OfType<BoundLet>().Select(l => l.Local).Distinct().ToList();
        if (locals.Count == 0) return;
        var index = locals.Select((l, i) => (l, i)).ToDictionary(p => p.l, p => p.i);

        var assignedOut = new Dictionary<BasicBlock, BitArray> { [graph.Entry] = new(locals.Count, false) };
        foreach (var b in graph.Blocks) assignedOut[b] = new BitArray(locals.Count, true);   // "all": loops then converge

        bool changed = true;
        while (changed)                                                   // repeat until nothing changes
        {
            changed = false;
            foreach (var b in graph.Blocks)
            {
                BitArray assigned = AssignedIn(b, assignedOut);
                Walk(b, assigned, index, report: null);
                if (!Same(assigned, assignedOut[b])) { assignedOut[b] = assigned; changed = true; }
            }
        }
        foreach (var b in graph.Blocks)                                   // then report reads before assignment
            if (reachable.Contains(b)) Walk(b, AssignedIn(b, assignedOut), index, diagnostics);
    }

    static BitArray AssignedIn(BasicBlock b, Dictionary<BasicBlock, BitArray> assignedOut)
    {
        var result = new BitArray(assignedOut[b].Length, true);           // intersection over predecessors
        foreach (var p in b.Predecessors) result.And(assignedOut[p]);
        return result;
    }

    // Walk(block, assigned, index, report) goes through the block's statements in order: an assignment or a `let` with an
    // initialiser sets the local's bit, `&x` sets it too (it may be written through), and with `report` set, a read of a
    // local whose bit is clear is reported.
    ```

Start every block's `assignedOut` (except the entry's) as **all variables**, not empty, or a loop's back edge will make everything look unassigned. The analysis pass passes no bag; only the final walk, with the fixed point reached, reports.

## Constant folding

Evaluate operations on constants at compile time: `60 * 60 * 24` becomes `86400`. LLVM does this too, so the reasons to fold in the front end are **language rules**, not speed:

- **Constant declarations** (`const SECONDS_PER_DAY = 60 * 60 * 24;`) and **array sizes** need a value the compiler knows.
- **Errors** for things that are certainly wrong: division by a constant zero, or a constant that overflows its type.
- **Branches on constants** (`if DEBUG { ... }`) can be removed before code generation, along with their warnings about unreachable code.

Fold with the language's semantics, not C#'s or C++'s: wrap-around or trap on overflow as the language specifies, and the same float behaviour as the target (an `f32` computation folded in `double` gives a different result).

## An IR of your own?

There are two ways to reach LLVM from here:

| | Lowered bound tree straight to LLVM | Your own IR, then LLVM |
| --- | --- | --- |
| Work | least: one code generator walks the flat statement lists | an IR, a lowering to it, and then the code generator |
| Optimisations you write | none needed: LLVM does them | language-specific ones (devirtualisation, escape analysis, removing bounds checks) |
| Other backends (an interpreter, a VM, a debugger) | each walks the bound tree itself | all share the IR |

Start without one. Add an IR when there is a second backend, or a language-level optimisation that LLVM cannot see.

## C++ tips

- **Ownership of lowered code**: the flat list mixes statements from the bound tree (owned by the binder) with labels and jumps lowering creates. Keep the new ones in the `LoweredFunction` beside the list (`owned`), so the list can hold plain pointers to both.
- **Labels compare by address**, as above: `std::unordered_map<const BoundLabel*, BasicBlock*>` finds a label's block.
- **Bit sets**: `std::vector<bool>` is fine for a few dozen locals; `std::vector<uint64_t>` with manual masking, or `boost::dynamic_bitset`, is faster for the intersection when functions have hundreds.
- Basic blocks are `unique_ptr`s, so the `successors` and `predecessors` pointers stay valid as the block list grows.

## C# tips

- Write a `BoundTreeRewriter` base class with one virtual `RewriteXxx` per bound node, each of which rewrites the children and rebuilds the node only when a child changed (`ReferenceEquals` on each). Every lowering pass then overrides one or two methods.
- `BoundLabel` is a small class with a name for debugging (`while_check_3`). Compare labels by reference.
- Data-flow sets over a function's locals fit in a `BitArray`, as above, or a `ulong[]` with one bit per local. `BitArray.And` does the intersection in place.
- Keep a debug printer for the lowered form too. A test that prints the labels and gotos for a `while` loop catches most lowering bugs before they reach LLVM.
