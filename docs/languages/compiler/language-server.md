# Language server

A **language server** gives editors the compiler's knowledge: errors as you type, the type under the cursor, go to definition, completion. The **Language Server Protocol** (LSP) is the standard between the server and the editor, so one server works in VS Code, Visual Studio, Neovim, Helix, Zed, and others.

The work is mostly done by the rest of the compiler. If it already [recovers from errors](parser.md#error-recovery), keeps [spans](source-diagnostics.md) on everything, and [maps syntax to symbols](binding.md#c-tips), a useful server is a few hundred lines on top.

## The protocol

Messages are JSON-RPC 2.0, sent over stdin and stdout, each with a header:

```text
Content-Length: 77\r\n
\r\n
{"jsonrpc":"2.0","id":1,"method":"textDocument/hover","params":{"text":"é"}}
```

=== "C++"

    ```cpp
    std::optional<json> ReadMessage(std::istream& in)       // stdin must be in binary mode on Windows
    {
        size_t length = 0;
        std::string line;
        while (std::getline(in, line) && line != "\r")       // headers end with an empty line
            if (line.starts_with("Content-Length: ")) length = std::stoul(line.substr(16));
        if (!in || length == 0) return std::nullopt;         // end of input: the editor has gone
        std::string body(length, '\0');
        in.read(body.data(), std::streamsize(length));       // bytes, not characters: the body is UTF-8
        return json::parse(body);
    }

    void WriteMessage(std::ostream& out, const json& message)
    {
        std::string body = message.dump();
        out << "Content-Length: " << body.size() << "\r\n\r\n" << body << std::flush;
    }
    ```

=== "C#"

    ```csharp
    public static class JsonRpc
    {
        public static async Task<JsonNode?> ReadMessageAsync(Stream input, CancellationToken cancellationToken)
        {
            int length = 0;
            while (true)                                                    // headers end with an empty line
            {
                string? line = await ReadHeaderLineAsync(input, cancellationToken);
                if (line is null) return null;                              // end of input: the editor has gone
                if (line.Length == 0) break;
                if (line.StartsWith("Content-Length: ")) length = int.Parse(line["Content-Length: ".Length..]);
            }
            byte[] body = new byte[length];
            await input.ReadExactlyAsync(body, cancellationToken);          // bytes, not characters: the body is UTF-8
            return JsonNode.Parse(body);
        }

        // A StreamReader would buffer past the headers into the body, so read the ASCII header lines a byte at a time.
        static async Task<string?> ReadHeaderLineAsync(Stream input, CancellationToken cancellationToken)
        {
            var line = new StringBuilder();
            byte[] one = new byte[1];
            while (true)
            {
                if (await input.ReadAsync(one, cancellationToken) == 0) return null;
                if (one[0] == '\n') return line.ToString().TrimEnd('\r');
                line.Append((char)one[0]);
            }
        }

        public static async Task WriteMessageAsync(Stream output, JsonNode message, CancellationToken cancellationToken)
        {
            byte[] body = Encoding.UTF8.GetBytes(message.ToJsonString());
            await output.WriteAsync(Encoding.ASCII.GetBytes($"Content-Length: {body.Length}\r\n\r\n"), cancellationToken);
            await output.WriteAsync(body, cancellationToken);
            await output.FlushAsync(cancellationToken);
        }
    }
    ```

- The length is in **bytes**: `é` is two bytes in UTF-8, so the message above is 77 bytes for 76 characters. System.Text.Json writes non-ASCII characters as `\u00e9` escapes by default, which is also valid.
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

=== "C++"

    ```cpp
    class LanguageServer
    {
        struct Document { std::string text; int version; };

        std::ostream& out_;
        std::mutex writeMutex_, documentsMutex_;
        std::unordered_map<std::string, Document> documents_;
        std::jthread checker_;                               // last, so it is stopped before the rest is destroyed
        // Handle(message) dispatches on "method": initialize, didOpen, didChange, didClose, shutdown, ...
    };

    void DidOpen(const json& params)
    {
        const json& doc = params["textDocument"];
        {
            std::lock_guard lock(documentsMutex_);
            documents_[doc["uri"]] = { doc["text"], doc["version"] };
        }
        ScheduleCheck();
    }

    void DidChange(const json& params)
    {
        {
            std::lock_guard lock(documentsMutex_);
            Document& document = documents_.at(params["textDocument"]["uri"]);
            document.text = params["contentChanges"].back()["text"];   // full sync: the last change is the whole text
            document.version = params["textDocument"]["version"];
        }
        ScheduleCheck();
    }

    void DidClose(const json& params)
    {
        std::string uri = params["textDocument"]["uri"];
        {
            std::lock_guard lock(documentsMutex_);
            documents_.erase(uri);
        }
        Publish(uri, json::array());                     // or the editor keeps showing its old errors
    }
    ```

=== "C#"

    ```csharp
    public sealed class LanguageServer(Stream output)
    {
        sealed record Document(string Text, int Version);

        readonly ConcurrentDictionary<string, Document> _documents = new();
        readonly SemaphoreSlim _writeLock = new(1, 1);       // responses and checks write from different tasks
        CancellationTokenSource? _checkCancellation;
        Task _check = Task.CompletedTask;
        // HandleAsync(message) dispatches on "method": initialize, didOpen, didChange, didClose, shutdown, ...
    }

    void DidOpen(JsonNode parameters)
    {
        JsonNode doc = parameters["textDocument"]!;
        _documents[(string)doc["uri"]!] = new Document((string)doc["text"]!, (int)doc["version"]!);
        ScheduleCheck();
    }

    void DidChange(JsonNode parameters)
    {
        string uri = (string)parameters["textDocument"]!["uri"]!;
        string text = (string)parameters["contentChanges"]!.AsArray()[^1]!["text"]!;   // full sync: the last change is the whole text
        _documents[uri] = new Document(text, (int)parameters["textDocument"]!["version"]!);
        ScheduleCheck();
    }

    async Task DidCloseAsync(JsonNode parameters)
    {
        string uri = (string)parameters["textDocument"]!["uri"]!;
        _documents.TryRemove(uri, out _);
        await PublishAsync(uri, []);                                     // or the editor keeps showing its old errors
    }
    ```

Ask for **full-document sync** at first (each change sends the whole text). Switch to incremental sync, which sends only the edited range, when large files make it worthwhile.

## Diagnostics

=== "C++"

    ```cpp
    void ScheduleCheck()
    {
        // Assigning a new jthread stops the previous check (if it is still waiting or running) and joins it.
        checker_ = std::jthread([this](std::stop_token stop) {
            std::mutex m;
            std::condition_variable_any wake;
            std::unique_lock lock(m);
            wake.wait_for(lock, stop, std::chrono::milliseconds(200), [] { return false; });   // typing: wait for a pause
            if (stop.stop_requested()) return;           // a newer change arrived

            std::vector<std::pair<std::string, Document>> documents;
            {
                std::lock_guard documentsLock(documentsMutex_);
                documents.assign(documents_.begin(), documents_.end());
            }
            for (auto& [uri, document] : documents)       // front end only: no code generation
            {
                if (stop.stop_requested()) return;
                SourceText source(uri, document.text);
                json diagnostics = json::array();
                for (const Diagnostic& d : Compilation().Compile(source).diagnostics) diagnostics.push_back(ToLsp(d));
                Publish(uri, std::move(diagnostics));     // an empty list clears the file's old errors
            }
        });
    }

    json ToLsp(const Diagnostic& d)
    {
        return {
            { "range", { { "start", ToLspPosition(*d.source, d.span.start) }, { "end", ToLspPosition(*d.source, d.span.End()) } } },
            { "severity", d.GetSeverity() == Severity::Error ? 1 : 2 },
            { "code", d.Info().code },
            { "source", "lang" },
            { "message", d.message },
        };
    }

    json ToLspPosition(const SourceText& source, uint32_t offset)   // zero-based; `character` counts UTF-16 code units
    {
        LinePosition p = source.Position(offset);            // one-based, and the column counts bytes
        std::string_view before = source.LineText(p.line - 1).substr(0, p.column - 1);
        uint32_t character = 0;
        for (unsigned char c : before)
            if ((c & 0xC0) != 0x80) character += c >= 0xF0 ? 2 : 1;   // each code point's first byte; 4-byte ones need two units
        return { { "line", p.line - 1 }, { "character", character } };
    }
    ```

=== "C#"

    ```csharp
    void ScheduleCheck()
    {
        _checkCancellation?.Cancel();                                    // a newer change makes the running check useless
        var cancellation = _checkCancellation = new CancellationTokenSource();
        Task previous = _check;
        _check = Task.Run(async () =>
        {
            await previous.ContinueWith(_ => { });                       // one compile at a time: the type caches are not thread-safe
            await Task.Delay(200, cancellation.Token);                   // typing: wait for a pause
            foreach (var (uri, document) in _documents.ToArray())        // front end only: no code generation
            {
                cancellation.Token.ThrowIfCancellationRequested();
                var source = new SourceText(uri, document.Text);
                JsonNode?[] diagnostics = [.. Compilation.Compile(source).Diagnostics.Select(ToLsp)];
                await PublishAsync(uri, diagnostics);                    // an empty list clears the file's old errors
            }
        }, cancellation.Token);
    }

    static JsonNode ToLsp(Diagnostic d) => new JsonObject
    {
        ["range"] = new JsonObject { ["start"] = ToLspPosition(d.Source!, d.Span.Start), ["end"] = ToLspPosition(d.Source!, d.Span.End) },
        ["severity"] = d.Severity == Severity.Error ? 1 : 2,
        ["code"] = d.Descriptor.Code,
        ["source"] = "lang",
        ["message"] = d.Message,
    };

    // Zero-based. LSP counts UTF-16 code units by default, which is what a C# string index counts.
    public static JsonNode ToLspPosition(SourceText source, int offset)
    {
        var (line, column) = source.Position(offset);
        return new JsonObject { ["line"] = line - 1, ["character"] = column - 1 };
    }
    ```

**Positions** in LSP are zero-based `{ line, character }`, and by default `character` counts **UTF-16 code units**, which is exactly a C# string index. Convert with the same [line map](source-diagnostics.md#source-text-and-spans) used for error messages, subtracting one from each part. A C++ compiler that keeps UTF-8 text counts the line's code points instead, two units for each one outside the Basic Multilingual Plane (emoji), as `ToLspPosition` does; or, with LSP 3.17, offer `utf-8` in the `positionEncoding` capability when the editor lists it, and send byte columns.

Publish an **empty list** for files that no longer have errors, or the old errors stay in the editor. Only one check runs at a time: the C++ version stops and joins the previous thread, and the C# version waits for the previous task, because the compiler's type caches are not thread-safe.

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

=== "C++"

    ```cpp
    const SyntaxNode* NodeAt(const SyntaxNode* root, uint32_t offset)   // the innermost node whose span contains offset
    {
        const SyntaxNode* node = root;
        for (;;)
        {
            const SyntaxNode* next = nullptr;
            for (const SyntaxChild& child : node->Children())   // in source order: a binary search works too
            {
                auto* n = std::get_if<const SyntaxNode*>(&child);
                if (!n) continue;
                TextSpan span = (*n)->Span();
                if (span.start <= offset && offset <= span.End()) { next = *n; break; }   // <=: the cursor just after a name
            }
            if (!next) return node;
            node = next;
        }
    }
    ```

=== "C#"

    ```csharp
    public static SyntaxNode NodeAt(SyntaxNode root, int offset)        // the innermost node whose span contains offset
    {
        SyntaxNode node = root;
        while (true)
        {
            SyntaxNode? next = node.GetChildren()                         // in source order: a binary search works too
                .Select(c => c.Node)
                .FirstOrDefault(n => n is not null && n.Span.Start <= offset && offset <= n.Span.End);   // <=: just after a name
            if (next is null) return node;
            node = next;
        }
    }
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

## C++ tips

- **JSON**: [nlohmann/json](https://github.com/nlohmann/json) is the easy choice, as above; [simdjson](https://github.com/simdjson/simdjson) and [Glaze](https://github.com/stephenberry/glaze) are faster where messages are large (semantic tokens for a big file).
- **Binary stdin and stdout on Windows**: call `_setmode(_fileno(stdin), _O_BINARY)` (and the same for stdout) at start-up, or the C runtime turns `\r\n` into `\n` and the byte counts are wrong.
- **`std::jthread`** (C++20) carries a `stop_token`: assigning a new one stops and joins the old, which is the cancel-and-restart a check needs. Pass the token into the compiler and check it between items, so a long check stops promptly.
- **Never write to `std::cout`** from anywhere but the message writer. Send logging to `std::cerr`, and redirect `std::cout`'s buffer to it at start-up if libraries might print.
- Test the server under ThreadSanitizer (`-fsanitize=thread`): the document map, the output stream, and the check thread are shared.

## C# tips

- **Libraries**: [StreamJsonRpc](https://github.com/microsoft/vs-streamjsonrpc) handles the JSON-RPC framing and dispatch, and is used by Visual Studio itself; you then write the LSP message types (or generate them from the protocol's JSON metamodel). [OmniSharp.Extensions.LanguageServer](https://github.com/OmniSharp/csharp-language-server-protocol) provides the full protocol on top; check that its release activity suits you before depending on it.
- Writing the framing by hand is also short, as above: pass it `Console.OpenStandardInput()` and `Console.OpenStandardOutput()`. Do not wrap the input in a `StreamReader` for the headers: it buffers ahead into the body.
- Set `Console.Out` to stderr (`Console.SetOut(Console.Error)`) at startup, so any accidental `Console.WriteLine` cannot corrupt the protocol stream.
- Run each check on the thread pool with a `CancellationToken`, as above, and pass the token into the lexer, parser, and binder, checking it between items or statements.
- Publish the server as a single self-contained executable (`dotnet publish -r <rid> --self-contained -p:PublishSingleFile=true`), or as Native AOT for fast startup, so the editor extension does not need a .NET installation.
