# C++ testing

Unit tests for a C++ engine with doctest or Catch2, built and run by CMake, with the engine's core running headless. The ideas behind them are on the [unit testing](index.md) page.

## doctest or Catch2

| | doctest | Catch2 v3 |
| --- | --- | --- |
| Shipped as | One header | A compiled library |
| Compile time | Very fast; designed for it | Slower, but v3 no longer compiles everything in each test file |
| Tests inside the engine's own source files | Yes; compiled out with `DOCTEST_CONFIG_DISABLE` | Not designed for it |
| Extras | Basic | Matchers, generators, built-in benchmarks |

Both use almost the same syntax. doctest suits an engine that wants tests next to the code they test, or cares most about build time. Catch2 has more built in.

## Tests

```cpp
// doctest
#include <doctest/doctest.h>
#include "core/handle_table.h"

TEST_CASE("a handle is invalid after its object is destroyed")
{
    HandleTable<int> table;
    Handle h = table.create(42);
    REQUIRE(table.get(h) != nullptr);

    table.destroy(h);
    CHECK(table.get(h) == nullptr);

    SUBCASE("and a new object in the same slot does not revive it")
    {
        Handle h2 = table.create(7);
        CHECK(h2.index == h.index);
        CHECK(table.get(h) == nullptr);
        CHECK(*table.get(h2) == 7);
    }
}
```

```cpp
// Catch2 v3
#include <catch2/catch_test_macros.hpp>

TEST_CASE("a handle is invalid after its object is destroyed", "[core][handles]")
{
    HandleTable<int> table;
    Handle h = table.create(42);
    table.destroy(h);
    CHECK(table.get(h) == nullptr);

    SECTION("and a new object in the same slot does not revive it")
    {
        Handle h2 = table.create(7);
        CHECK(table.get(h) == nullptr);
    }
}
```

- `REQUIRE` stops the test when it fails; `CHECK` records the failure and carries on. Use `REQUIRE` when later lines would crash without it (a null pointer), and `CHECK` otherwise, so one run reports every failure.
- **Subcases** (doctest) and **sections** (Catch2) run the test case once per leaf, each time from the top. Set-up shared by several checks goes at the top of the test case, and each subcase gets a fresh copy. This replaces fixture classes for most tests.
- Tags (`[core][handles]` in Catch2; `TEST_SUITE` in doctest) select groups of tests on the command line: `engine_tests "[handles]"` or `engine_tests -ts=handles`.

### Floating-point results

```cpp
CHECK(length(v) == doctest::Approx(1.0f).epsilon(1e-5));          // doctest

#include <catch2/matchers/catch_matchers_floating_point.hpp>
CHECK_THAT(length(v), Catch::Matchers::WithinAbs(1.0, 1e-5));     // Catch2
```

Write helpers for vectors and quaternions that compare each component with a tolerance, and that print both values on failure. Give the types an `operator<<` (or a `doctest::StringMaker` / `Catch::StringMaker` specialisation), so failures show `(1, 0, 0.0001)` instead of `{?}`.

### Table-driven tests

```cpp
TEST_CASE("armour reduces damage")
{
    struct Case { int damage, armour, expected; };
    const Case cases[] = {
        { 10, 0, 10 },
        { 10, 5, 5 },
        { 10, 15, 1 },      // minimum damage
        { 0, 0, 0 },
    };
    for (const Case& c : cases)
    {
        CAPTURE(c.damage);
        CAPTURE(c.armour);
        CHECK(damage_after_armour(c.damage, c.armour) == c.expected);
    }
}
```

`CAPTURE` adds the values to the failure message, so a failure says which row failed. Catch2's `GENERATE` runs the whole test case once per value instead, with each run reported separately.

## Building with CMake

Build the engine as libraries, with the executable a thin layer on top. Tests then link the same libraries the game does:

```cmake
add_library(engine_core STATIC src/core/handle_table.cpp src/core/jobs.cpp ...)
add_library(engine_sim  STATIC src/sim/combat.cpp src/sim/inventory.cpp ...)
target_link_libraries(engine_sim PUBLIC engine_core)

add_executable(game src/main.cpp)
target_link_libraries(game PRIVATE engine_sim engine_render engine_audio)

# Tests
find_package(doctest REQUIRED)
add_executable(engine_tests tests/main.cpp tests/handle_table_tests.cpp tests/combat_tests.cpp)
target_link_libraries(engine_tests PRIVATE engine_sim doctest::doctest)

enable_testing()
include(doctest)                      # from doctest's scripts/cmake; Catch2: include(Catch)
doctest_discover_tests(engine_tests)  # Catch2: catch_discover_tests(engine_tests)
```

```cpp
// tests/main.cpp: doctest's main, in exactly one file
#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
```

```bash
ctest --test-dir build --output-on-failure
```

`doctest_discover_tests` and `catch_discover_tests` register each test case with CTest separately, so `ctest` reports them one by one, can run them in parallel (`-j`), and IDEs list them. With Catch2 v3, link `Catch2::Catch2WithMain` instead of writing a `main`.

## Running headless

Tests must not open a window, create a GPU device, or play sound. Split each subsystem so the parts worth testing do not need those:

- The **simulation** (gameplay, physics, AI, the ECS) links only `engine_core`, and takes time and input as arguments. It never touches the renderer.
- Systems that are needed but not tested get **null implementations**: a renderer whose submit does nothing, an audio system that records the sound ids it was asked to play. The same null implementations run a dedicated server.
- The **file system** goes through an interface, so tests read assets from memory or from a small test-data folder, never from the developer's game install.

An engine that can run without a window has two more uses: a dedicated server, and **smoke tests** in CI that load each level, run a few hundred ticks with bots, and fail on any error in the log.

## Sanitizers

Run the test suite with sanitizers in CI. They find memory errors in exactly the code the tests run, with a stack trace:

```cmake
# A separate CMake configuration for sanitizer builds (Clang or GCC).
target_compile_options(engine_tests PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
target_link_options(engine_tests PRIVATE -fsanitize=address,undefined)
```

AddressSanitizer catches use after free, buffer overflows, and leaks; UndefinedBehaviorSanitizer catches signed overflow, bad shifts, and misaligned access, many of the bugs the [bit manipulation](../../data-structures/bits.md#shift-pitfalls) page warns about. ThreadSanitizer, in its own build, finds data races in job system tests. MSVC supports AddressSanitizer with `/fsanitize=address`.

## Determinism and golden files in C++

The [determinism](index.md#determinism-tests) and [golden-file](index.md#golden-files) tests need a few C++-specific precautions:

- **Floating point** must be computed the same way in every build: no `-ffast-math` (it lets the compiler reorder operations), and the same instruction set (do not let one build use FMA instructions and another not). Check the hashes on every platform you ship, from the same recorded inputs.
- **Iteration order** of `std::unordered_map` depends on the implementation and on insertion history. Never let it decide simulation order, or the order of a serialised golden file. Sort first, or use ordered containers.
- **Uninitialised memory** makes hashes of structs differ between runs. Hash fields one by one, not the raw bytes of structs with padding, and initialise every field.
- **Threads** must not decide the order of results. Write each job's results into its own slot, and combine them in a fixed order.
