---
package: Microsoft.CodeAnalysis.CSharp 4.3
---

# Analysers

An analyser registers callbacks for the kinds of code it cares about, and reports diagnostics from them. This page writes rules for the [`[Notify]` generator's](source-generators.md) attribute, a Unity performance rule, a check that needs the whole compilation, and a suppressor that silences other analysers' false positives.

## Structure

```csharp
[DiagnosticAnalyzer(LanguageNames.CSharp)]
public sealed class NotifyAnalyzer : DiagnosticAnalyzer
{
    public static readonly DiagnosticDescriptor MustBePartial = new(
        id: "GT0001",
        title: "Type with [Notify] fields must be partial",
        messageFormat: "'{0}' has [Notify] fields, so it must be declared partial",
        category: "GameTools",
        defaultSeverity: DiagnosticSeverity.Error,
        isEnabledByDefault: true);

    public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics =>
        ImmutableArray.Create(MustBePartial /* , ... */);

    public override void Initialize(AnalysisContext context)
    {
        context.ConfigureGeneratedCodeAnalysis(GeneratedCodeAnalysisFlags.None);
        context.EnableConcurrentExecution();
        // register callbacks here
    }
}
```

- **Ids** are permanent: users suppress and configure rules by id. Pick a prefix for your project and never reuse a number.
- `messageFormat` takes `{0}`-style arguments, passed when the diagnostic is created. Put the name of the offending thing in the message: the error list shows the message without the code.
- `ConfigureGeneratedCodeAnalysis(None)` skips generated files. Without it, an analyser checks generated code, which the user cannot fix.
- `EnableConcurrentExecution` lets the compiler call callbacks on several threads. Keep callbacks free of shared mutable state, or make it thread-safe.

The callbacks:

| Register | Called for | Use for |
| --- | --- | --- |
| `RegisterSymbolAction` | Each declared symbol of the kinds given | Rules about declarations: types, fields, methods. |
| `RegisterSyntaxNodeAction` | Each syntax node of the kinds given | Rules about how code is written. |
| `RegisterOperationAction` | Each operation of the kinds given | Rules about what method bodies do. |
| `RegisterCompilationStartAction` | Once per compilation, before the others | Looking up types once, and keeping per-compilation state. |
| `RegisterCompilationEndAction` (inside a start action) | Once, after everything else | Rules that need to see everything. |

## Rules for the generator's attributes

The [generator](source-generators.md#finding-the-fields) quietly skips code it cannot handle. The analyser tells the user why:

| Id | Rule |
| --- | --- |
| GT0001 | The containing type must be `partial`. |
| GT0002 | The containing type must not be nested or generic. |
| GT0003 | The field must not be `readonly`; the generated setter assigns it. |
| GT0004 | The generated property name must not clash with an existing member. |

```csharp
public override void Initialize(AnalysisContext context)
{
    context.ConfigureGeneratedCodeAnalysis(GeneratedCodeAnalysisFlags.None);
    context.EnableConcurrentExecution();
    context.RegisterCompilationStartAction(start =>
    {
        INamedTypeSymbol? notify = start.Compilation.GetTypeByMetadataName("GameTools.NotifyAttribute");
        if (notify is null) return;         // the generator is not running here
        start.RegisterSymbolAction(c => AnalyzeField(c, notify), SymbolKind.Field);
    });
}

static void AnalyzeField(SymbolAnalysisContext context, INamedTypeSymbol notify)
{
    var field = (IFieldSymbol)context.Symbol;
    if (!field.GetAttributes().Any(a => SymbolEqualityComparer.Default.Equals(a.AttributeClass, notify)))
        return;

    INamedTypeSymbol type = field.ContainingType;
    Location fieldLocation = field.Locations[0];

    foreach (SyntaxReference reference in type.DeclaringSyntaxReferences)
    {
        if (reference.GetSyntax(context.CancellationToken) is TypeDeclarationSyntax decl &&
            !decl.Modifiers.Any(SyntaxKind.PartialKeyword))
        {
            context.ReportDiagnostic(Diagnostic.Create(MustBePartial, decl.Identifier.GetLocation(), type.Name));
        }
    }

    if (type.ContainingType is not null || type.IsGenericType)
        context.ReportDiagnostic(Diagnostic.Create(NotNestedOrGeneric, fieldLocation, type.Name));

    if (field.IsReadOnly)
        context.ReportDiagnostic(Diagnostic.Create(NotReadOnly, fieldLocation, field.Name));

    string property = NotifyGenerator.PropertyName(field.Name);
    if (type.GetMembers(property).Any(m => !m.IsImplicitlyDeclared && !IsGenerated(m)))
        context.ReportDiagnostic(Diagnostic.Create(NameClash, fieldLocation, field.Name, property));
}

static bool IsGenerated(ISymbol symbol) =>
    symbol.Locations.All(l => l.SourceTree?.FilePath.EndsWith(".Notify.g.cs") == true);
```

- Look the attribute up **once per compilation**, in the start action, then compare symbols. Comparing attribute names as strings on every field is slower and matches unrelated attributes with the same name.
- `GetTypeByMetadataName` returns null when the type does not exist. Use that to switch the whole analyser off in assemblies the generator does not run in.
- When the attribute is `internal` and several assemblies have their own copy, `GetTypeByMetadataName` returns the one in the assembly being compiled.
- A partial type can have several declarations, and `partial` must be on all of them. Report at each declaration's name that lacks it, so the light bulb appears in the right place for the [make-partial code fix](code-fixes.md).
- Analysers see generated code, so the generated `Health` property is a member of the type. `IsGenerated` stops the clash check from reporting the property it is checking for. The generator and analyser share `PropertyName`, so the two cannot drift apart.

## A Unity rule: lookups in Update

`GetComponent` and the `Find` family search, and they are often written in `Update` where they run every frame. A rule that warns on them:

```csharp
static readonly DiagnosticDescriptor LookupInUpdate = new(
    id: "GT0010",
    title: "Component or object lookup in a per-frame method",
    messageFormat: "'{0}' is called every frame in '{1}'; cache the result in Awake or Start",
    category: "Performance",
    defaultSeverity: DiagnosticSeverity.Warning,
    isEnabledByDefault: true);

static readonly ImmutableHashSet<string> Lookups = ImmutableHashSet.Create(
    "GetComponent", "GetComponents", "GetComponentInChildren", "GetComponentsInChildren",
    "GetComponentInParent", "GetComponentsInParent",
    "Find", "FindWithTag", "FindObjectOfType", "FindObjectsOfType",
    "FindFirstObjectByType", "FindAnyObjectByType", "FindObjectsByType");

static readonly ImmutableHashSet<string> PerFrame = ImmutableHashSet.Create(
    "Update", "LateUpdate", "FixedUpdate", "OnGUI");

public override void Initialize(AnalysisContext context)
{
    context.ConfigureGeneratedCodeAnalysis(GeneratedCodeAnalysisFlags.None);
    context.EnableConcurrentExecution();
    context.RegisterCompilationStartAction(start =>
    {
        INamedTypeSymbol? behaviour = start.Compilation.GetTypeByMetadataName("UnityEngine.MonoBehaviour");
        if (behaviour is null) return;
        start.RegisterOperationAction(c => Analyze(c, behaviour), OperationKind.Invocation);
    });
}

static void Analyze(OperationAnalysisContext context, INamedTypeSymbol behaviour)
{
    var call = (IInvocationOperation)context.Operation;
    IMethodSymbol target = call.TargetMethod;
    if (!Lookups.Contains(target.Name) ||
        target.ContainingNamespace?.ToDisplayString() != "UnityEngine")
        return;

    if (context.ContainingSymbol is not IMethodSymbol method ||
        !PerFrame.Contains(method.Name) || method.Parameters.Length != 0 ||
        !InheritsFrom(method.ContainingType, behaviour))
        return;

    context.ReportDiagnostic(Diagnostic.Create(
        LookupInUpdate, call.Syntax.GetLocation(), target.Name, method.Name));
}

static bool InheritsFrom(INamedTypeSymbol? type, INamedTypeSymbol baseType)
{
    for (; type is not null; type = type.BaseType)
        if (SymbolEqualityComparer.Default.Equals(type, baseType)) return true;
    return false;
}
```

- An **operation** action sees every call however it is written: `GetComponent<Rigidbody>()`, `this.GetComponent<Rigidbody>()`, `other.gameObject.GetComponent(typeof(Rigidbody))`. A syntax action would have to recognise each form.
- `GetComponent` on another object in `Update`, such as the collider just hit, is sometimes correct. Leave the rule a warning so it can be suppressed in those places with `#pragma warning disable GT0010`.
- The rule only checks the per-frame method's own body, not methods it calls. Following calls needs a call graph, which an analyser should not build on every keystroke.

## Checks across the whole compilation

Duplicate [save type ids](generator-examples.md#a-type-registry) can be in different files. A symbol action sees one type at a time, so the check gathers ids as it goes and compares them at the end:

```csharp
static readonly DiagnosticDescriptor DuplicateId = new(
    id: "GT0020",
    title: "Duplicate save type id",
    messageFormat: "Save type id '{0}' is also used by '{1}'",
    category: "GameTools",
    defaultSeverity: DiagnosticSeverity.Error,
    isEnabledByDefault: true,
    customTags: WellKnownDiagnosticTags.CompilationEnd);

context.RegisterCompilationStartAction(start =>
{
    INamedTypeSymbol? attribute = start.Compilation.GetTypeByMetadataName("GameTools.SaveTypeAttribute");
    if (attribute is null) return;
    var found = new ConcurrentBag<(string Id, string Type, Location Location)>();

    start.RegisterSymbolAction(c =>
    {
        foreach (AttributeData a in c.Symbol.GetAttributes())
        {
            if (SymbolEqualityComparer.Default.Equals(a.AttributeClass, attribute) &&
                a.ConstructorArguments is [{ Value: string id }])
            {
                Location location = a.ApplicationSyntaxReference?.GetSyntax(c.CancellationToken).GetLocation()
                                    ?? c.Symbol.Locations[0];
                found.Add((id, c.Symbol.Name, location));
            }
        }
    }, SymbolKind.NamedType);

    start.RegisterCompilationEndAction(end =>
    {
        foreach (var group in found.GroupBy(f => f.Id).Where(g => g.Count() > 1))
        {
            var entries = group.ToList();
            foreach (var entry in entries)
            {
                string other = entries.First(e => e != entry).Type;
                end.ReportDiagnostic(Diagnostic.Create(DuplicateId, entry.Location, entry.Id, other));
            }
        }
    });
});
```

- The state (`found`) lives inside the start action, so each compilation gets its own. A static field would mix compilations together in the IDE, which analyses many at once.
- `ConcurrentBag` because symbol actions run on several threads.
- Compilation-end diagnostics must be tagged `CompilationEnd` (rule RS1037 checks it). IDEs only run them in a full build or a full-solution analysis, not while typing, because they need every file. Expect them to appear on build.

## Configuring severity

Users choose how strict each rule is. In a .NET project, in `.editorconfig`:

```ini
[*.cs]
dotnet_diagnostic.GT0010.severity = none        # off
dotnet_diagnostic.GT0003.severity = error
```

In Unity, use `.ruleset` files (see [Unity setup](index.md#unity-setup)):

```xml
<?xml version="1.0" encoding="utf-8"?>
<RuleSet Name="Game rules" ToolsVersion="16.0">
  <Rules AnalyzerId="GameTools.Generators" RuleNamespace="GameTools.Generators">
    <Rule Id="GT0010" Action="None" />
    <Rule Id="GT0003" Action="Error" />
  </Rules>
</RuleSet>
```

Choose the default severity carefully. Errors stop the build, so use them for code that will not work (a type that is not `partial` gets no properties). Warnings suit advice, such as the per-frame lookups.

## Suppressors

Sometimes another analyser, or the compiler, warns about code that is correct because of something it does not know. A `DiagnosticSuppressor` sees those diagnostics and can hide individual ones, with a stated reason.

Fields filled in by an injection system through reflection are a common case. The compiler warns that they are never assigned (CS0649), and the IDE suggests making them `readonly` (IDE0044):

```csharp
[DiagnosticAnalyzer(LanguageNames.CSharp)]
public sealed class InjectFieldSuppressor : DiagnosticSuppressor
{
    static readonly SuppressionDescriptor NeverAssigned = new(
        id: "GTSP0001",
        suppressedDiagnosticId: "CS0649",
        justification: "Fields marked [Inject] are assigned by the injector.");

    static readonly SuppressionDescriptor MakeReadOnly = new(
        id: "GTSP0002",
        suppressedDiagnosticId: "IDE0044",
        justification: "Fields marked [Inject] are assigned by the injector.");

    public override ImmutableArray<SuppressionDescriptor> SupportedSuppressions =>
        ImmutableArray.Create(NeverAssigned, MakeReadOnly);

    public override void ReportSuppressions(SuppressionAnalysisContext context)
    {
        INamedTypeSymbol? inject = context.Compilation.GetTypeByMetadataName("GameTools.InjectAttribute");
        if (inject is null) return;

        foreach (Diagnostic diagnostic in context.ReportedDiagnostics)
        {
            SyntaxTree? tree = diagnostic.Location.SourceTree;
            if (tree is null) continue;

            SyntaxNode node = tree.GetRoot(context.CancellationToken).FindNode(diagnostic.Location.SourceSpan);
            SemanticModel model = context.GetSemanticModel(tree);
            if (model.GetDeclaredSymbol(node, context.CancellationToken) is IFieldSymbol field &&
                field.GetAttributes().Any(a => SymbolEqualityComparer.Default.Equals(a.AttributeClass, inject)))
            {
                SuppressionDescriptor descriptor = diagnostic.Id == "CS0649" ? NeverAssigned : MakeReadOnly;
                context.ReportSuppression(Suppression.Create(descriptor, diagnostic));
            }
        }
    }
}
```

- `ReportedDiagnostics` only contains diagnostics whose ids appear in `SupportedSuppressions`, so the loop never sees anything else.
- A suppressor can hide warnings, from the compiler or from other analysers, but not errors.
- The suppression is per diagnostic, not per rule, so CS0649 still reports on fields without `[Inject]`. Prefer this to turning the rule off for the whole project.
- Microsoft.Unity.Analyzers already uses suppressors for Unity's own cases, such as CS0649 on `[SerializeField]` fields, and "unused method" on Unity messages like `Update`.
