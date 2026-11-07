# Unit testing

Automated tests for game and engine code: what is worth testing, how to structure code so it can be tested, and the kinds of test that suit games. [C# testing](csharp.md) and [C++ testing](cpp.md) show the same ideas with xUnit and with doctest and Catch2.

## What to test

Unit tests pay off on code with clear right answers, that is easy to break without noticing:

| Test | Examples |
| --- | --- |
| Rules and calculations | Damage, armour, and resistances; crafting recipes; stacking in an inventory; experience curves |
| Data structures | [Sparse sets](../../data-structures/sparse-set.md), [handle tables](../../data-structures/handle-table.md), [ring buffers](../../data-structures/ring-buffer.md), pools |
| Algorithms | Pathfinding, line of sight, [layout](../ui/layout.md), spatial queries, procedural generation from a seed |
| Maths | [Intersection tests](../../maths/intersections.md), quaternion helpers, interpolation |
| Serialisation | Save and load round trips, version migrations, network packet packing |
| Bugs that were fixed | A test that reproduces the bug, so it cannot come back |

They pay off poorly on how things look and feel: camera smoothness, animation blending, whether a jump is fun. Those need playtesting. Rendering and audio are better covered by a few [golden-file](#golden-files) and smoke tests than by unit tests.

## Making code testable

Most game code is hard to test because it reaches out for what it needs: the global clock, a random number generator, the input system, the scene. The fix is to let the caller pass those in.

### Separate the logic from the engine object

Put the rules in a plain class or plain functions, and keep the engine-facing object (a `MonoBehaviour`, an entity system) thin: it reads from the engine, calls the logic, and writes the result back.

```text
// Hard to test: needs a scene, a clock, physics, and a player.
TurretComponent.update():
    target = find_nearest_enemy_in_scene()
    if time.now - last_shot > cooldown: fire_at(target)

// Easy to test: a function of its inputs.
choose_target(turret_position, range, enemies[]) -> enemy or none
can_fire(now, last_shot, cooldown) -> bool

TurretComponent.update():
    target = choose_target(position, range, gather_enemies())
    if can_fire(clock.now, last_shot, cooldown): fire_at(target)
```

The component is too thin to need a test of its own. The functions it calls are where the bugs are, and they can be tested with a few lines each.

### Pass in time, randomness, and input

| Dependency | Pass in | A test uses |
| --- | --- | --- |
| Time | A clock, or `dt` as a parameter | A clock it advances by hand |
| Random numbers | A random generator, or a seed | A fixed seed, or a fake that returns chosen values |
| Input | The input state for this frame | A struct filled in by the test |
| Files and assets | An interface for loading | Data built in memory |
| Other systems | The interface the code actually uses | A fake |

A **fake** is a small, hand-written implementation for tests: an in-memory save store, an audio system that records which sounds were requested. Prefer fakes to mocking libraries for game code. Fakes are easy to read, and they test what the code did (the inventory now has three items), not which calls it made in which order, which breaks every time the code is reorganised.

## Kinds of test

### Example tests

The usual kind: set up a state, do one thing, check the result.

```text
test "damage is reduced by armour, to a minimum of 1":
    attacker = { damage: 10 }
    defender = { armour: 15, health: 100 }
    apply_damage(attacker, defender)
    check defender.health == 99
```

Name each test after the behaviour it checks, so a failing test's name says what broke.

### Table-driven tests

One test body, run with many rows of inputs and expected outputs. Good for rules with many cases and edge values:

```text
cases = [
    // damage, armour, expected
    (10, 0, 10),
    (10, 5, 5),
    (10, 15, 1),       // minimum damage
    (0, 0, 0),         // no damage stays no damage
]
for (damage, armour, expected) in cases:
    check damage_after_armour(damage, armour) == expected
```

### Round-trip tests

Anything with a writer and a reader: write a value, read it back, compare. Run it with edge cases (empty lists, maximum values, unusual characters in names) and with old save files kept as test data, so migrations keep working.

### Determinism tests

A lockstep multiplayer game or a replay system needs the simulation to give the same result from the same inputs. Test exactly that:

```text
test "simulation is deterministic":
    a = run_simulation(seed = 1234, inputs = recorded_inputs, ticks = 1000)
    b = run_simulation(seed = 1234, inputs = recorded_inputs, ticks = 1000)
    check hash(a.state) == hash(b.state)
```

Hash the whole simulation state every N ticks and compare the hashes, so a failure says **when** the runs diverged, not just that they did. Run it in the configurations you ship, because floating-point results can differ between compilers, optimisation settings, and CPUs.

### Golden files

For output that is large or hard to describe in assertions (a generated navmesh, a laid-out UI, a rendered image, a level from a seed), save a known-good output to a file in the repository, and compare against it:

```text
test "dungeon generation from seed 42":
    level = generate_dungeon(seed = 42)
    text = serialise(level)
    if UPDATE_GOLDEN: write golden/dungeon_42.txt = text
    else: check text == read golden/dungeon_42.txt
```

- Make the format **text** and **stable** (sorted keys, fixed float precision), so a failing test shows a readable diff and the golden file's history shows how the output changed.
- When a change is meant to alter the output, run with `UPDATE_GOLDEN`, then review the diff before committing it.
- For images, compare with a tolerance per pixel and a limit on the number of differing pixels. GPUs and drivers do not produce identical results.

## Running tests

- **Keep the unit tests fast**: a few seconds for the whole suite. Fast tests get run on every build; slow ones get skipped.
- **Run them in CI** on every push, in the build configurations you ship. Optimised builds find bugs that debug builds hide, such as uninitialised memory.
- **Separate slow tests** (determinism over many thousands of ticks, golden images) into their own group, and run them in CI rather than on every local build.
- **A test that fails at random is a bug.** It is usually a test depending on time, on random numbers without a seed, on the order of a hash map, or on another test's leftover state.
