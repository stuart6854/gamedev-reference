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

```text
lower_while(w):
    continue_label = new_label(), check = new_label(), break_label = new_label()
    push (break_label, continue_label) for break and continue inside the body
    return [
        Goto(check),
        Label(continue_label),
        lower(w.body),
        Label(check),
        ConditionalGoto(lower(w.condition), continue_label, jump_if = true),
        Label(break_label),
    ]
```

Short-circuit operators lower the same way, so `b` is only evaluated when needed:

```text
a && b    →   result = false
              goto_if_false a, done
              result = b
            done:
```

After lowering, a function body is a **flat list** of statements: expressions, assignments, labels, gotos, conditional gotos, and returns.

## Control-flow graph

Split the flat list into **basic blocks**: runs of statements with one entry at the top and one exit at the bottom.

```text
build_cfg(statements):
    blocks = []
    current = new block
    for s in statements:
        if s is Label:                         // a label starts a block
            if current is not empty: blocks.append(current)
            current = new block starting at s
        else:
            current.append(s)
            if s is Goto, ConditionalGoto, or Return:     // a jump ends one
                blocks.append(current)
                current = new block
    if current is not empty: blocks.append(current)

    for each block b:                          // edges
        last = b.last statement
        if last is Goto:            edge(b, block of last.label)
        elif last is ConditionalGoto: edge(b, block of last.label); edge(b, next block)
        elif last is Return:        edge(b, exit)
        else:                       edge(b, next block, or exit if none)    // falls through
    return blocks
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

```text
assigned_in[b]  = intersection of assigned_out[p] for each predecessor p     // entry: {}
assigned_out[b] = assigned_in[b] ∪ variables assigned in b

repeat until nothing changes                // a forward data-flow analysis; loops need the repeat
then: a read of x in block b, before any assignment to x in b, is an error unless x ∈ assigned_in[b]
```

Start every `assigned_out` (except the entry) as **all variables**, not empty, or a loop's back edge will make everything look unassigned.

## Constant folding

Evaluate operations on constants at compile time: `60 * 60 * 24` becomes `86400`. LLVM does this too, so the reasons to fold in the front end are **language rules**, not speed:

- **Constant declarations** (`const SECONDS_PER_DAY = 60 * 60 * 24;`) and **array sizes** need a value the compiler knows.
- **Errors** for things that are certainly wrong: division by a constant zero, or a constant that overflows its type.
- **Branches on constants** (`if DEBUG { ... }`) can be removed before code generation, along with their warnings about unreachable code.

Fold with the language's semantics, not C#'s: wrap-around or trap on overflow as the language specifies, and the same float behaviour as the target (an `f32` computation folded in `double` gives a different result).

## An IR of your own?

There are two ways to reach LLVM from here:

| | Lowered bound tree straight to LLVM | Your own IR, then LLVM |
| --- | --- | --- |
| Work | least: one code generator walks the flat statement lists | an IR, a lowering to it, and then the code generator |
| Optimisations you write | none needed: LLVM does them | language-specific ones (devirtualisation, escape analysis, removing bounds checks) |
| Other backends (an interpreter, a VM, a debugger) | each walks the bound tree itself | all share the IR |

Start without one. Add an IR when there is a second backend, or a language-level optimisation that LLVM cannot see.

## C# tips

- Write a `BoundTreeRewriter` base class with one virtual `RewriteXxx` per bound node, each of which rewrites the children and rebuilds the node only when a child changed (`ReferenceEquals` on each). Every lowering pass then overrides one or two methods.
- `BoundLabel` is a small class with a name for debugging (`while_check_3`). Compare labels by reference.
- Represent a block's statements as `ImmutableArray<BoundStatement>` and the graph as lists of predecessor and successor blocks. Data-flow sets over a function's locals fit in a `BitArray` or `ulong[]`, with one bit per local.
- Keep a debug printer for the lowered form too. A test that prints the labels and gotos for a `while` loop catches most lowering bugs before they reach LLVM.
