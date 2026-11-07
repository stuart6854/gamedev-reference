# C# testing

Unit tests for C# game code with xUnit, and the NUnit equivalents. The ideas behind them, and what is worth testing, are on the [unit testing](index.md) page.

## The test project

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <IsPackable>false</IsPackable>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.*" />
    <PackageReference Include="xunit" Version="2.*" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.*" />
    <ProjectReference Include="..\Game.Logic\Game.Logic.csproj" />
  </ItemGroup>
</Project>
```

```bash
dotnet test
```

```bash
dotnet test --filter "FullyQualifiedName~Inventory"
```

Keep the game logic in a project (`Game.Logic`) that does not depend on the engine, so the tests can reference it. In Unity, that is an assembly definition with **No Engine References** ticked. It can then be built as a normal .NET project for fast tests, as well as used in Unity.

## Tests

```csharp
public class InventoryTests
{
    [Fact]
    public void Adding_to_a_partial_stack_fills_it_first()
    {
        // Arrange
        var inventory = new Inventory(slots: 4);
        inventory.Add(Items.Wood, 30);              // stack size 50

        // Act
        inventory.Add(Items.Wood, 30);

        // Assert
        Assert.Equal(50, inventory.CountInSlot(0));
        Assert.Equal(10, inventory.CountInSlot(1));
    }

    [Fact]
    public void Adding_to_a_full_inventory_returns_the_leftover()
    {
        var inventory = new Inventory(slots: 1);
        int leftover = inventory.Add(Items.Wood, 70);
        Assert.Equal(20, leftover);
    }
}
```

- xUnit creates a **new instance** of the test class for each test, so fields set in the constructor are fresh every time. Use the constructor for set-up and `IDisposable.Dispose` for clean-up.
- One behaviour per test, named as a sentence. When `Adding_to_a_full_inventory_returns_the_leftover` fails, the name says what broke.
- Use the arrange, act, assert layout, with blank lines between the parts. Most tests need no comments beyond that.

### Table-driven tests

```csharp
[Theory]
[InlineData(10, 0, 10)]
[InlineData(10, 5, 5)]
[InlineData(10, 15, 1)]     // minimum damage
[InlineData(0, 0, 0)]
public void Armour_reduces_damage(int damage, int armour, int expected)
{
    Assert.Equal(expected, Combat.DamageAfterArmour(damage, armour));
}
```

Each `[InlineData]` row is reported as a separate test. For rows that are not compile-time constants (vectors, objects), use `[MemberData(nameof(Cases))]` with a static property returning `IEnumerable<object[]>`, or `TheoryData<...>` for type safety.

### Floating-point results

```csharp
Assert.Equal(0.7071, MathF.Sin(MathF.PI / 4), 4);          // to 4 decimal places
Assert.Equal(expected, actual, tolerance: 1e-5);           // within an absolute tolerance

static void AssertClose(Vector3 expected, Vector3 actual, float tolerance = 1e-5f) =>
    Assert.True(Vector3.Distance(expected, actual) <= tolerance,
                $"Expected {expected}, got {actual}");
```

Never compare floats computed in different ways with exact equality. Write small helpers like `AssertClose` for your vector and quaternion types, with a message that shows both values.

### Exceptions

```csharp
var ex = Assert.Throws<ArgumentOutOfRangeException>(() => inventory.Remove(slot: 9));
Assert.Equal("slot", ex.ParamName);
```

## Fakes

```csharp
public interface IClock { double Now { get; } }

public sealed class FakeClock : IClock
{
    public double Now { get; private set; }
    public void Advance(double seconds) => Now += seconds;
}

[Fact]
public void Turret_fires_again_after_its_cooldown()
{
    var clock = new FakeClock();
    var turret = new TurretLogic(clock, cooldown: 2.0);

    Assert.True(turret.TryFire());
    clock.Advance(1.9);
    Assert.False(turret.TryFire());
    clock.Advance(0.1);
    Assert.True(turret.TryFire());
}
```

The same pattern covers random numbers (a seeded generator, or a fake returning queued values), save storage (a dictionary instead of files), and other systems (a fake audio system that records requested sound ids). Mocking libraries such as NSubstitute and Moq build fakes automatically, which helps for wide interfaces, but hand-written fakes are clearer for the small interfaces game code usually has.

## Shared set-up

For expensive set-up shared by many tests, such as loading a big data table, xUnit uses fixtures:

```csharp
public sealed class ItemDatabaseFixture
{
    public ItemDatabase Items { get; } = ItemDatabase.Load("TestData/items.json");
}

public class CraftingTests : IClassFixture<ItemDatabaseFixture>
{
    readonly ItemDatabase _items;
    public CraftingTests(ItemDatabaseFixture fixture) => _items = fixture.Items;
}
```

The fixture is created once for all tests in the class. Treat it as read-only: a test that changes shared state makes other tests pass or fail depending on the order they run in.

## NUnit equivalents

Unity's Test Framework is built on NUnit, so tests that may also run in Unity are often written with it:

| xUnit | NUnit |
| --- | --- |
| `[Fact]` | `[Test]` |
| `[Theory]` + `[InlineData(1, 2)]` | `[TestCase(1, 2)]` |
| `[MemberData]` | `[TestCaseSource]` |
| Constructor, `Dispose` | `[SetUp]`, `[TearDown]` |
| `IClassFixture<T>` | `[OneTimeSetUp]`, `[OneTimeTearDown]` |
| `Assert.Equal(expected, actual)` | `Assert.That(actual, Is.EqualTo(expected))` |
| `Assert.Equal(e, a, tolerance: t)` | `Assert.That(a, Is.EqualTo(e).Within(t))` |
| `Assert.Throws<T>(...)` | `Assert.Throws<T>(...)` |

NUnit, unlike xUnit, uses **one instance** of a test class for all its tests. Reset fields in `[SetUp]`, or state leaks from one test into the next.

## Allocation and performance checks

"This method does not allocate" can be a test: warm the method up, then compare `GC.GetAllocatedBytesForCurrentThread()` before and after calling it many times, and assert the difference is 0. Keep timing out of unit tests: the time a test takes varies with the machine and its load, so timing assertions fail at random. Benchmarks belong in a separate benchmark project.
