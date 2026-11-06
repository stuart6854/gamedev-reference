---
package: Microsoft.CodeAnalysis.CSharp 4.3
---

# Generator examples

Three more generators built the same way as the [`[Notify]` generator](source-generators.md): each finds its input, copies it into an equatable model, and writes source from the model. They use the `EquatableArray<T>` from that page.

## Fast enum names

`Enum.ToString()` and `Enum.Parse` use reflection and allocate. That shows up in profiles when enums are logged, used as dictionary keys through their names, or written to save files every frame. Generate a `switch` instead:

```csharp
// Written by hand
[FastEnum]
public enum Biome { Forest, Desert, Tundra }

// Generated
public static partial class BiomeExtensions
{
    public static string ToStringFast(this global::Game.Biome value) => value switch
    {
        global::Game.Biome.Forest => "Forest",
        global::Game.Biome.Desert => "Desert",
        global::Game.Biome.Tundra => "Tundra",
        _ => value.ToString(),
    };

    public static bool TryParseFast(string name, out global::Game.Biome value)
    {
        switch (name)
        {
            case "Forest": value = global::Game.Biome.Forest; return true;
            case "Desert": value = global::Game.Biome.Desert; return true;
            case "Tundra": value = global::Game.Biome.Tundra; return true;
        }
        value = default;
        return false;
    }
}
```

### Model

```csharp
record EnumModel(
    string Namespace, string Name, string FullName, string Accessibility,
    EquatableArray<string> Members);

static EnumModel ToModel(INamedTypeSymbol e)
{
    var seen = new HashSet<object?>();
    var members = ImmutableArray.CreateBuilder<string>();
    foreach (IFieldSymbol f in e.GetMembers().OfType<IFieldSymbol>())
    {
        // Two names with the same value would be two identical switch cases, which
        // does not compile. Keep the first name for each value.
        if (f.HasConstantValue && seen.Add(f.ConstantValue))
            members.Add(f.Name);
    }

    return new EnumModel(
        e.ContainingNamespace.IsGlobalNamespace ? "" : e.ContainingNamespace.ToDisplayString(),
        e.Name,
        e.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
        IsVisibleOutside(e) ? "public" : "internal",
        new EquatableArray<string>(members.ToImmutable()));
}

// A public method cannot take a less visible type (error CS0051), so the extension
// class is public only if the enum and every type it is nested in are public.
static bool IsVisibleOutside(INamedTypeSymbol type)
{
    for (INamedTypeSymbol? t = type; t is not null; t = t.ContainingType)
        if (t.DeclaredAccessibility != Accessibility.Public) return false;
    return true;
}
```

### Pipeline

```csharp
var enums = context.SyntaxProvider.ForAttributeWithMetadataName(
    "GameTools.FastEnumAttribute",
    predicate: static (node, _) => node is EnumDeclarationSyntax,
    transform: static (ctx, _) => ToModel((INamedTypeSymbol)ctx.TargetSymbol));

context.RegisterSourceOutput(enums, static (spc, e) =>
    spc.AddSource($"{e.FullName.Replace("global::", "")}.FastEnum.g.cs", Emit(e)));
```

`Emit` writes the class above with a loop over `e.Members`. Leave `[Flags]` enums out (check for `System.FlagsAttribute` in the transform), or fall back to `value.ToString()` for them: a combined value such as `Read | Write` has no single case.

## A type registry

Polymorphic save data needs a stable id for each saved type, and a way to create an instance from an id. Finding the types by reflection at start-up costs time, and fails when IL2CPP's stripping removed a type that was never referenced directly. A generator builds the table at compile time, and the `new` in the generated code keeps every type from being stripped.

```csharp
// Written by hand
[SaveType("door")]  public sealed class DoorState : ISaveState { /* ... */ }
[SaveType("chest")] public sealed class ChestState : ISaveState { /* ... */ }

// Generated
namespace GameTools.Generated
{
    internal static class SaveTypeRegistry
    {
        public static object? Create(string id) => id switch
        {
            "chest" => new global::Game.ChestState(),
            "door" => new global::Game.DoorState(),
            _ => null,
        };

        public static string? IdOf(global::System.Type type)
        {
            if (type == typeof(global::Game.ChestState)) return "chest";
            if (type == typeof(global::Game.DoorState)) return "door";
            return null;
        }
    }
}
```

```csharp
record SaveTypeModel(string Id, string FullName);

var saveTypes = context.SyntaxProvider.ForAttributeWithMetadataName(
        "GameTools.SaveTypeAttribute",
        predicate: static (node, _) => node is ClassDeclarationSyntax,
        transform: static (ctx, _) =>
            ctx.Attributes[0].ConstructorArguments is [{ Value: string id }]
                ? new SaveTypeModel(id, ctx.TargetSymbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat))
                : null)
    .Where(static m => m is not null)
    .Select(static (m, _) => m!);

context.RegisterSourceOutput(saveTypes.Collect(), static (spc, all) =>
{
    var unique = all
        .GroupBy(t => t.Id)
        .Select(g => g.First())             // duplicates are reported by the analyser
        .OrderBy(t => t.Id, StringComparer.Ordinal)
        .ToList();
    spc.AddSource("GameTools.SaveTypeRegistry.g.cs", Emit(unique));
});
```

- This needs **all** the types at once, so it collects them. One file is generated per assembly, and the registry is `internal` so each assembly has its own. A game with saved types in several assemblies registers each assembly's table at start-up.
- Keep only the first type for each id. Two identical cases in the `switch` would not compile, and the error would point into generated code, which is confusing. The [duplicate-id analyser](analyzers.md#checks-across-the-whole-compilation) reports it on the attributes instead.
- Sort by id so the output does not depend on the order files were processed in.
- `new T()` needs a parameterless constructor. Check for one in the transform (`InstanceConstructors.Any(c => c.Parameters.Length == 0)`) and leave the type out if there is none, or report it from the analyser.

## Generating from a data file

Item ids, input action names, and localisation keys often live in data files. Generating constants from the file turns a typo in code (`"iron_oer"`) into a compile error.

```text
id,name,stack
wood,Wood,50
iron_ore,Iron ore,20
```

```csharp
// Generated from ItemIds.csv
public static class ItemIds
{
    public const string Wood = "wood";
    public const string IronOre = "iron_ore";

    public static readonly string[] All = { Wood, IronOre };
}
```

The file reaches the generator as an **additional file**. In a .NET project:

```xml
<ItemGroup>
  <AdditionalFiles Include="Data\ItemIds.csv" />
</ItemGroup>
```

In Unity, name it `ItemIds.GameTools.Generators.additionalfile`, where `GameTools.Generators` is the analyser's name, anywhere under `Assets` (see [Unity setup](index.md#unity-setup)). The generator below takes the class name from the first part of the file name, so the same code handles both.

### Model and parsing

```csharp
record IdRow(string Id, string Identifier);
record IdError(int Line, string Message);
record IdTable(string Path, string ClassName, EquatableArray<IdRow> Rows, EquatableArray<IdError> Errors);

static IdTable Parse(string path, string text, CancellationToken ct)
{
    string className = Path.GetFileName(path).Split('.')[0];
    var rows = ImmutableArray.CreateBuilder<IdRow>();
    var errors = ImmutableArray.CreateBuilder<IdError>();
    var seen = new HashSet<string>();

    string[] lines = text.Split('\n');
    for (int i = 1; i < lines.Length; i++)          // line 0 is the header
    {
        ct.ThrowIfCancellationRequested();
        string line = lines[i].Trim();
        if (line.Length == 0) continue;

        string id = line.Split(',')[0].Trim();
        string identifier = ToPascalCase(id);
        if (!SyntaxFacts.IsValidIdentifier(identifier))
            errors.Add(new IdError(i, $"'{id}' does not make a valid C# name"));
        else if (!seen.Add(identifier))
            errors.Add(new IdError(i, $"'{id}' is a duplicate of an earlier id"));
        else
            rows.Add(new IdRow(id, identifier));
    }

    return new IdTable(path, className,
        new EquatableArray<IdRow>(rows.ToImmutable()),
        new EquatableArray<IdError>(errors.ToImmutable()));
}

static string ToPascalCase(string id) =>
    string.Concat(id.Split('_', '-', ' ')
        .Where(p => p.Length > 0)
        .Select(p => char.ToUpperInvariant(p[0]) + p.Substring(1)));
```

`SyntaxFacts.IsValidIdentifier` (from `Microsoft.CodeAnalysis.CSharp`) rejects names that start with a digit or contain other symbols. Errors are stored as a line number and a message, not as a `Location`, so the model stays equatable.

### Pipeline

```csharp
static readonly DiagnosticDescriptor BadId = new(
    id: "GT0100",
    title: "Invalid id in data file",
    messageFormat: "{0}",
    category: "GameTools",
    defaultSeverity: DiagnosticSeverity.Error,
    isEnabledByDefault: true);

var tables = context.AdditionalTextsProvider
    .Where(static f => Path.GetFileName(f.Path).Split('.')[0].EndsWith("Ids", StringComparison.Ordinal))
    .Select(static (f, ct) => Parse(f.Path, f.GetText(ct)?.ToString() ?? "", ct));

context.RegisterSourceOutput(tables, static (spc, table) =>
{
    foreach (IdError e in table.Errors)
    {
        var lines = new LinePositionSpan(new LinePosition(e.Line, 0), new LinePosition(e.Line, 0));
        spc.ReportDiagnostic(Diagnostic.Create(BadId, Location.Create(table.Path, default, lines), e.Message));
    }
    spc.AddSource($"{table.ClassName}.g.cs", Emit(table));
});
```

- Read the file with `AdditionalText.GetText`, never `File.ReadAllText`. The compiler tracks changes to additional files, so editing the CSV re-runs the generator; a file read directly is invisible to it, and the output goes stale. With `EnforceExtendedAnalyzerRules` on, direct file access is warning RS1035.
- `Location.Create(path, span, lineSpan)` points a diagnostic at a line in a non-code file. Most IDEs show it in the error list and jump to the line.
- Generate the class even when some rows have errors, leaving those rows out. Otherwise one bad line breaks every use of every id.

The same pattern turns any table into code: input action names from an exported actions file, or animation parameter names written out by an editor tool so `Animator.StringToHash` never sees a typo.
