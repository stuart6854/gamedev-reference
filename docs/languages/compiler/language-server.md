# Language server

A **language server** gives editors the compiler's knowledge: errors as you type, the type under the cursor, go to definition, completion. The **Language Server Protocol** (LSP) is the standard between the server and the editor, so one server works in VS Code, Visual Studio, Neovim, Helix, Zed, and others.

The work is mostly done by the rest of the compiler. If it already [recovers from errors](parser.md#error-recovery), keeps [spans](source-diagnostics.md) on everything, and [maps syntax to symbols](binding.md#c-tips), a useful server is a few hundred lines on top.

## The protocol

Messages are JSON-RPC 2.0, sent over stdin and stdout, each with a header:

```text
Content-Length: 85\r\n
\r\n
{"jsonrpc":"2.0","id":1,"method":"textDocument/hover","params":{...}}
```

```text
read_message(stdin):
    headers = read lines until an empty line
    length = headers["Content-Length"]
    return parse_json(read exactly `length` bytes)       // bytes, not characters: the body is UTF-8
```

- **Requests** have an `id` and need exactly one response. **Notifications** have none and get no response.
- **Stdout is the protocol.** Anything else written to it (a stray `Console.WriteLine`, a library's log) corrupts the stream and the editor disconnects. Log to stderr, or to the editor through `window/logMessage`.

### Lifecycle

```text
→ initialize { capabilities the editor supports }
← result { capabilities the server supports: hover, definition, completion, ... }
→ initialized
→ textDocument/didOpen, didChange, hover, ...       // the session
→ shutdown
← result null
→ exit
```

Only advertise capabilities you implement. The editor then hides the rest.

## Keeping documents in sync

The editor owns the text. The server keeps a copy of each open document, updated by notifications:

```text
on didOpen(uri, text, version):   documents[uri] = (text, version); schedule_check(uri)
on didChange(uri, changes, version):
    apply each change to documents[uri].text           // full text, or a range plus new text
    schedule_check(uri)
on didClose(uri):                 remove documents[uri]; publish empty diagnostics for uri
```

Ask for **full-document sync** at first (each change sends the whole text). Switch to incremental sync, which sends only the edited range, when large files make it worthwhile.

## Diagnostics

```text
schedule_check(uri):
    cancel any check still running for this project
    after a short delay (100–300 ms, so typing does not start a compile per keystroke):
        compilation = compile(all open documents and the project's files)     // front end only: no code generation
        for each file:
            send textDocument/publishDiagnostics { uri, diagnostics: [to_lsp(d) for d in its diagnostics] }
```

**Positions** in LSP are zero-based `{ line, character }`, and by default `character` counts **UTF-16 code units**, which is exactly a C# string index. Convert with the same [line map](source-diagnostics.md#source-text-and-spans) used for error messages, subtracting one from each part.

Publish an **empty list** for files that no longer have errors, or the old errors stay in the editor.

## Features, in order of value

| Feature | Request | Needs from the compiler |
| --- | --- | --- |
| Errors as you type | `publishDiagnostics` | diagnostics with spans |
| Hover | `textDocument/hover` | node at a position, then its type or symbol |
| Go to definition | `textDocument/definition` | the symbol's declaration span |
| Outline | `textDocument/documentSymbol` | the file's items and their spans |
| Completion | `textDocument/completion` | the scope at a position, and member lists for `x.` |
| Signature help | `textDocument/signatureHelp` | the call around the cursor and the function's parameters |
| Find references | `textDocument/references` | every syntax node bound to a symbol |
| Rename | `textDocument/rename` | references, plus a check that the new name is free |
| Semantic highlighting | `textDocument/semanticTokens/full` | the kind of every name: type, function, parameter, local |
| Formatting | `textDocument/formatting` | a [pretty-printer](syntax-trees.md#pretty-printing-source) |

Most share one operation: **find the innermost node at a position**.

```text
node_at(tree, offset):
    node = tree.root
    loop:
        child = the child of node whose span contains offset     // children are in source order: binary search
        if no such child: return node
        node = child
```

Hover then looks up the node in the binder's syntax-to-symbol table, and shows the symbol's signature or the expression's type.

### Completion

Completion runs on **incomplete code**: the user has typed `player.he` and the statement has no semicolon yet. This is where error recovery pays off.

- After `.`, bind the expression before the dot, and offer the fields and methods of its type.
- Elsewhere, walk the scopes from the cursor outwards, offering every visible local, parameter, function, and type, plus keywords valid at that point.
- Filter by the typed prefix on the server, or send everything and let the editor filter; both work for small projects.

The binder must be able to say **which scope a position is in**. Record each block's scope and span while binding, so the server can find it later.

## Performance

- **Re-checking everything** on each change is fine up to tens of thousands of lines, if the front end is quick. Measure before building anything incremental.
- **Cancel stale work.** When a change arrives, cancel the compilation for the previous version; its results would be thrown away anyway.
- **Cache the parts that did not change**: syntax trees of unchanged files (keyed by text version), and the bound [standard library](standard-library.md#c-tips).
- Requests like hover must answer quickly. Answer from the **last completed** compilation, even if a newer one is still running, and map positions if the text has changed since.

## Robustness

An editor sends the server every half-typed state of every file. The server must never crash and never hang:

- Catch exceptions **per request**, and answer with an error response. One bad request must not end the session.
- Fuzz the front end with **every prefix** of every test file, as on the [testing page](testing.md#robustness).
- Respond to `shutdown` even mid-compilation.

## The editor side

For VS Code, a minimal extension is a `package.json` that registers the file extension and a few lines that start the server with the `vscode-languageclient` package. Most other editors need only a configuration entry: the command that starts the server and the file types it handles.

## C# tips

- **Libraries**: [StreamJsonRpc](https://github.com/microsoft/vs-streamjsonrpc) handles the JSON-RPC framing and dispatch, and is used by Visual Studio itself; you then write the LSP message types (or generate them from the protocol's JSON metamodel). [OmniSharp.Extensions.LanguageServer](https://github.com/OmniSharp/csharp-language-server-protocol) provides the full protocol on top; check that its release activity suits you before depending on it.
- Writing the framing by hand is also short: read headers from `Console.OpenStandardInput()` until a blank line, then read `Content-Length` bytes and parse them with `System.Text.Json`. Use `Console.OpenStandardOutput()` with a lock around each write, because responses and notifications come from several tasks.
- Set `Console.Out` to stderr (`Console.SetOut(Console.Error)`) at startup, so any accidental `Console.WriteLine` cannot corrupt the protocol stream.
- Run each check on the thread pool with a `CancellationToken`, and pass the token into the lexer, parser, and binder, checking it between items or statements.
- Publish the server as a single self-contained executable (`dotnet publish -r <rid> --self-contained -p:PublishSingleFile=true`), or as Native AOT for fast startup, so the editor extension does not need a .NET installation.
