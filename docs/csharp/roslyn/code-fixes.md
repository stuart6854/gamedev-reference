---
package: Microsoft.CodeAnalysis.CSharp.Workspaces 4.3
---

# Code fixes

A code fix provider offers light-bulb actions for diagnostics, and edits the document when one is chosen. Code fixes are an IDE feature: the compiler, `dotnet build`, and Unity never run them. This page adds fixes for the [`[Notify]` analyser's](analyzers.md#rules-for-the-generators-attributes) rules.

## A separate project

Code fixes need `Microsoft.CodeAnalysis.CSharp.Workspaces`, the IDE's document and project model. The compiler does not ship it, so an analyser assembly that references it can fail to load in a command-line build (rule RS1038 warns about this). Put fixes in their own project:

```text
GameTools.Generators/     generators and analysers; references Microsoft.CodeAnalysis.CSharp
GameTools.CodeFixes/      code fixes; references the above and Microsoft.CodeAnalysis.CSharp.Workspaces
```

```xml
<!-- GameTools.CodeFixes.csproj -->
<PropertyGroup>
  <TargetFramework>netstandard2.0</TargetFramework>
  <LangVersion>latest</LangVersion>
</PropertyGroup>
<ItemGroup>
  <PackageReference Include="Microsoft.CodeAnalysis.CSharp.Workspaces" Version="4.3.0" PrivateAssets="all" />
  <ProjectReference Include="..\GameTools.Generators\GameTools.Generators.csproj" />
</ItemGroup>
```

Ship both DLLs as analysers. In a NuGet package, both go in `analyzers/dotnet/cs`.

## Make the type partial

```csharp
[ExportCodeFixProvider(LanguageNames.CSharp, Name = nameof(MakePartialFix)), Shared]
public sealed class MakePartialFix : CodeFixProvider
{
    public override ImmutableArray<string> FixableDiagnosticIds =>
        ImmutableArray.Create(NotifyAnalyzer.MustBePartial.Id);

    public override FixAllProvider GetFixAllProvider() => WellKnownFixAllProviders.BatchFixer;

    public override async Task RegisterCodeFixesAsync(CodeFixContext context)
    {
        SyntaxNode? root = await context.Document.GetSyntaxRootAsync(context.CancellationToken).ConfigureAwait(false);
        Diagnostic diagnostic = context.Diagnostics[0];
        TypeDeclarationSyntax? decl = root?
            .FindNode(diagnostic.Location.SourceSpan)
            .FirstAncestorOrSelf<TypeDeclarationSyntax>();
        if (decl is null) return;

        context.RegisterCodeFix(
            CodeAction.Create(
                title: "Make type partial",
                createChangedDocument: ct => MakePartialAsync(context.Document, decl, ct),
                equivalenceKey: "MakePartial"),
            diagnostic);
    }

    static async Task<Document> MakePartialAsync(Document document, TypeDeclarationSyntax decl, CancellationToken ct)
    {
        DocumentEditor editor = await DocumentEditor.CreateAsync(document, ct).ConfigureAwait(false);
        editor.ReplaceNode(decl, (node, generator) =>
            generator.WithModifiers(node, generator.GetModifiers(node).WithPartial(true)));
        return editor.GetChangedDocument();
    }
}
```

- `FixableDiagnosticIds` decides which diagnostics offer this fix. Reuse the analyser's descriptor, so the id is written once.
- The diagnostic was reported at the type's name, so `FindNode` returns the identifier's parent and `FirstAncestorOrSelf` climbs to the declaration.
- `CodeAction.Create` takes a function, not a finished document. The IDE only runs it when the user previews or applies the fix, so registering a fix stays cheap.
- `SyntaxGenerator` (the `generator` argument) handles the details of editing modifiers: `partial` goes immediately before `class`, where C# requires it, and the whitespace and comments around it are kept. Building the token by hand with `SyntaxFactory` means handling those yourself.

## Remove readonly

The same pattern fixes GT0003. The diagnostic is on the field's name, but modifiers belong to the whole field declaration:

```csharp
static async Task<Document> RemoveReadOnlyAsync(Document document, SyntaxNode reported, CancellationToken ct)
{
    var field = reported.FirstAncestorOrSelf<FieldDeclarationSyntax>();
    if (field is null) return document;

    DocumentEditor editor = await DocumentEditor.CreateAsync(document, ct).ConfigureAwait(false);
    editor.ReplaceNode(field, (node, generator) =>
        generator.WithModifiers(node, generator.GetModifiers(node).WithIsReadOnly(false)));
    return editor.GetChangedDocument();
}
```

`int _a, _b;` is one declaration with two variables, so removing `readonly` changes both. That is fine here, since `[Notify]` on the declaration applies to both. Splitting the declaration would be a bigger fix.

## Fix all

`GetFixAllProvider` lets the user apply a fix to every occurrence in the document, project, or solution at once. `WellKnownFixAllProviders.BatchFixer` does it by computing each fix separately and merging the text changes, which works as long as fixes do not overlap.

The `equivalenceKey` groups fixes for this: only fixes with the same key are applied together. Give each distinct action its own constant key. Without one, fix-all does nothing.

Two cases where the batch fixer is wrong:

- Fixes that overlap, such as two diagnostics in the same declaration. The batch fixer drops changes that conflict.
- Fixes that change other files, such as renaming a symbol everywhere it is used. Write a custom `FixAllProvider` for these, or don't offer fix-all.

## Fixes that change the solution

A fix that touches more than the current document (adding a file, renaming across the project) uses `createChangedSolution` instead:

```csharp
CodeAction.Create(
    title: "Rename to match the save id",
    createChangedSolution: ct => RenameAsync(document.Project.Solution, symbol, newName, ct),
    equivalenceKey: "RenameToId");
```

Implement the rename with `Renamer.RenameSymbolAsync` from `Microsoft.CodeAnalysis.Rename`. It finds every reference through the semantic model, the same as the IDE's own rename. Its overloads changed between versions, so check the one in the Workspaces version you reference.

## In Unity

Unity loads analyser DLLs into its own compiler, which has no `Workspaces`. Unity also lists only DLLs with the `RoslynAnalyzer` label as analysers in the `.csproj` files it generates for the IDE.

- Label `GameTools.Generators.dll`. The rules and generators then work in Unity and in the IDE.
- Labelling `GameTools.CodeFixes.dll` too makes the IDE offer the fixes, but Unity's compiler also tries to load it. Check the Console for warnings about loading it. If it does not load cleanly, leave it unlabelled: everything except the light bulb still works.
