---
package: Microsoft.CodeAnalysis.Testing 1.1
---

# Testing

Analysers, fixes, and generators are functions from source code to diagnostics, edits, or new files, so they test well: give them a string of C#, check what comes out. A test runs in milliseconds, while checking by hand means rebuilding the plug-in and reloading a project.

## The test project

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <LangVersion>latest</LangVersion>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.*" />
    <PackageReference Include="xunit" Version="2.*" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.*" />
    <PackageReference Include="Microsoft.CodeAnalysis.CSharp.Analyzer.Testing" Version="1.1.2" />
    <PackageReference Include="Microsoft.CodeAnalysis.CSharp.CodeFix.Testing" Version="1.1.2" />
    <ProjectReference Include="..\GameTools.Generators\GameTools.Generators.csproj" />
    <ProjectReference Include="..\GameTools.CodeFixes\GameTools.CodeFixes.csproj" />
  </ItemGroup>
</Project>
```

The test project references the plug-ins as normal libraries, not as analysers, so tests can create them directly. Older versions of the testing packages had `.XUnit`, `.NUnit`, or `.MSTest` in the name. Those are deprecated; the current packages work with any test framework through `DefaultVerifier`.

## Analysers

The testing library compiles the test source, runs the analyser, and compares the diagnostics with markup in the source:

```csharp
using Microsoft.CodeAnalysis.CSharp.Testing;
using Microsoft.CodeAnalysis.Testing;

public class NotifyAnalyzerTests
{
    const string Attribute = """
        namespace GameTools
        {
            [System.AttributeUsage(System.AttributeTargets.Field)]
            internal sealed class NotifyAttribute : System.Attribute { }
        }
        """;

    static Task Verify(string source)
    {
        var test = new CSharpAnalyzerTest<NotifyAnalyzer, DefaultVerifier>
        {
            ReferenceAssemblies = ReferenceAssemblies.Net.Net80,
        };
        test.TestState.Sources.Add(source);
        test.TestState.Sources.Add(Attribute);
        return test.RunAsync();
    }

    [Fact]
    public Task Type_must_be_partial() => Verify("""
        using GameTools;
        public class {|GT0001:Stats|}
        {
            [Notify] int _health;
        }
        """);

    [Fact]
    public Task Partial_type_is_fine() => Verify("""
        using GameTools;
        public partial class Stats
        {
            [Notify] int _health;
        }
        """);
}
```

- `{|GT0001:Stats|}` says: "diagnostic GT0001 is reported on exactly `Stats`". The test fails if it is missing, on a different span, or if any **other** diagnostic from the analyser appears. A test with no markup checks that nothing is reported.
- The attribute is added as a second source file, because the generator that normally provides it is not running in an analyser test.
- `ReferenceAssemblies` picks the framework the test code compiles against. The packages are downloaded from NuGet on the first run and cached, so the first run needs network access.
- By default, only compiler **errors** in the test code fail the test; compiler warnings such as "field is never used" are ignored.

For Unity rules, add a source file that stubs the Unity types the rule looks for. The analyser only needs the names and the inheritance to match:

```csharp
const string UnityStubs = """
    namespace UnityEngine
    {
        public class Object { }
        public class Component : Object { public T GetComponent<T>() => default!; }
        public class Behaviour : Component { }
        public class MonoBehaviour : Behaviour { }
        public class Rigidbody : Component { }
    }
    """;

// VerifyLookups is the Verify helper above, using the lookup analyser and adding UnityStubs.
[Fact]
public Task GetComponent_in_Update_is_reported() => VerifyLookups("""
    using UnityEngine;
    public class Mover : MonoBehaviour
    {
        void Update() { var body = {|GT0010:GetComponent<Rigidbody>()|}; }
    }
    """);
```

## Code fixes

A code fix test gives the code before and after:

```csharp
[Fact]
public async Task Make_partial()
{
    var test = new CSharpCodeFixTest<NotifyAnalyzer, MakePartialFix, DefaultVerifier>
    {
        ReferenceAssemblies = ReferenceAssemblies.Net.Net80,
    };
    test.TestState.Sources.Add("""
        using GameTools;
        public class {|GT0001:Stats|}
        {
            [Notify] int _health;
        }
        """);
    test.FixedState.Sources.Add("""
        using GameTools;
        public partial class Stats
        {
            [Notify] int _health;
        }
        """);
    test.TestState.Sources.Add(Attribute);
    test.FixedState.Sources.Add(Attribute);
    await test.RunAsync();
}
```

The test applies the fix, compares the text exactly (whitespace included), and checks that no GT0001 remains. It also runs fix-all and checks that it gives the same result, which catches a missing `equivalenceKey`.

## Generators

Generators are easiest to test by running the compiler's generator driver directly:

```csharp
static readonly MetadataReference[] References =
    ((string)AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES")!)
        .Split(Path.PathSeparator)
        .Select(path => MetadataReference.CreateFromFile(path))
        .ToArray();

static (GeneratorDriverRunResult Result, Compilation Output) Run(string source)
{
    var compilation = CSharpCompilation.Create(
        "Tests",
        new[] { CSharpSyntaxTree.ParseText(source) },
        References,
        new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));

    GeneratorDriver driver = CSharpGeneratorDriver.Create(new NotifyGenerator().AsSourceGenerator());
    driver = driver.RunGeneratorsAndUpdateCompilation(compilation, out Compilation output, out _);
    return (driver.GetRunResult(), output);
}

[Fact]
public void Generates_property_that_compiles()
{
    var (result, output) = Run("""
        using GameTools;
        namespace Game
        {
            public partial class Stats
            {
                [Notify] int _health;
                public int Read() => Health;      // uses the generated property
            }
        }
        """);

    Assert.Empty(result.Diagnostics);
    Assert.Empty(output.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error));
    Assert.Contains(result.GeneratedTrees, t => t.FilePath.EndsWith("Game.Stats.Notify.g.cs"));
}
```

- `TRUSTED_PLATFORM_ASSEMBLIES` lists the test runner's own framework assemblies, which is an easy way to give the test compilation a full set of references.
- The most useful check is that the **output compiles**, with test source that uses the generated members. It catches most generator bugs without comparing text.
- To catch unintended changes to the generated text, compare it with a saved copy. The [Verify.SourceGenerators](https://github.com/VerifyTests/Verify.SourceGenerators) package does this as snapshot tests: the first run saves the output, and later runs fail and show a diff when it changes.
- For Unity, also compile the test with `new CSharpParseOptions(LanguageVersion.CSharp9)` (pass it to `ParseText` and to the driver), so generated code that needs a newer C# fails the test instead of failing in Unity.

### Additional files

Pass additional files to the driver as `AdditionalText` objects:

```csharp
sealed class InMemoryText(string path, string text) : AdditionalText
{
    public override string Path => path;
    public override SourceText GetText(CancellationToken ct = default) => SourceText.From(text);
}

GeneratorDriver driver = CSharpGeneratorDriver.Create(
    new[] { new IdTableGenerator().AsSourceGenerator() },
    additionalTexts: new AdditionalText[] { new InMemoryText("ItemIds.csv", "id,name\nwood,Wood\n9lives,Bad\n") });
```

That test expects one generated constant (`Wood`) and one GT0100 diagnostic for the row that starts with a digit.

### Checking the cache

A generator whose models are not equatable still produces the right output. It just re-runs everything on every keystroke, which nobody notices until the IDE becomes slow. Test for it: run the generator, make an unrelated edit, run it again, and check that the named step was not re-run:

```csharp
[Fact]
public void Unrelated_edit_is_cached()
{
    // StatsSource is any source with [Notify] fields, such as the one in the test above.
    var compilation = CSharpCompilation.Create("Tests",
        new[] { CSharpSyntaxTree.ParseText(StatsSource) },
        References,
        new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));

    GeneratorDriver driver = CSharpGeneratorDriver.Create(
        new[] { new NotifyGenerator().AsSourceGenerator() },
        driverOptions: new GeneratorDriverOptions(IncrementalGeneratorOutputKind.None, trackIncrementalGeneratorSteps: true));

    driver = driver.RunGenerators(compilation);
    driver = driver.RunGenerators(compilation.AddSyntaxTrees(CSharpSyntaxTree.ParseText("class Unrelated { }")));

    var steps = driver.GetRunResult().Results[0].TrackedSteps["NotifyTypes"];
    Assert.All(steps.SelectMany(s => s.Outputs), output =>
        Assert.True(output.Reason is IncrementalStepRunReason.Cached or IncrementalStepRunReason.Unchanged));
}
```

`TrackedSteps` is keyed by the names given with [`WithTrackingName`](source-generators.md#grouping-by-type). `Cached` means the step did not run; `Unchanged` means it ran but produced an equal value, so nothing after it ran. `Modified` or `New` here means a model is not equatable: look for an array, a symbol, or a syntax node inside it.
