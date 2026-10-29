# Random distributions and shuffles

Getting randomness that is reproducible, unbiased, and shaped the way the design wants: seeded generators, ranges, weighted picks, shuffles, shuffle bags, distributions other than uniform, and randomness that feels fair to players.

## Seeded generators

A pseudo-random generator is a function from a state to the next state and an output. The same seed gives the same sequence, which is what makes a replay, a procedural level, or a bug report reproducible.

| Generator | Where | Notes |
| --- | --- | --- |
| `UnityEngine.Random` | Unity, global | One shared state for the whole game. `Random.InitState(seed)` seeds it, `Random.state` saves and restores it. Main thread only. |
| `System.Random` | .NET | An object with its own state. Not thread-safe. `new System.Random()` seeds from the clock. |
| `Unity.Mathematics.Random` | Unity Mathematics | A small struct. Works in Burst and jobs. The seed must not be 0. |
| xorshift, PCG, SplitMix64 | Write your own | A few lines each. Same output on every platform and runtime, which matters for lockstep networking. |

### Separate streams

One shared generator couples every system that uses it. Add one extra call in the particle code, and every loot roll after it changes. For anything that must be reproducible, give each system its own generator, seeded from a master seed:

```text
master = Generator(level_seed)
loot_rng    = Generator(master.next())
terrain_rng = Generator(master.next())
ai_rng      = Generator(master.next())
```

Cosmetic randomness, such as particle jitter, can keep using the global generator.

### Randomness from a hash

When the random value belongs to a place or an id, not to a moment, hash the inputs instead of keeping a generator:

```text
value(seed, x, y) = hash(seed, x, y) / 2^32        // in [0, 1)
```

Tile \((12, 7)\) then gets the same variant whatever order tiles are generated in, and nothing has to be stored. Any good integer hash works; xxHash and PCG's output function are common choices. Do not use `GetHashCode` on strings for this in .NET: it is randomised per process.

## Ranges

| Want | Formula | Notes |
| --- | --- | --- |
| Float in \([a, b)\) | \(a + (b - a)\,u\), \(u \in [0, 1)\) | Unity's `Random.Range(float, float)` includes \(b\). |
| Integer in \([0, n)\) | Rejection, or multiply-high | `rand() % n` is biased when \(n\) does not divide the generator's range. |
| Integer in \([a, b]\) | \(a + \text{int}(0, b - a + 1)\) | Unity's `Random.Range(int, int)` and `System.Random.Next(int, int)` exclude the upper bound. |
| A chance of \(p\) | \(u < p\) | Not \(\le\): with \(p = 0\), \(u\) can be exactly 0. |

The modulo bias: a generator with 16 outputs, taken modulo 6, gives 0 to 3 three times each and 4 and 5 twice each. With 32-bit outputs and small \(n\) the bias is tiny, but it is real for large \(n\). Library range functions already handle it.

## Weighted picks

Roll \(r \in [0, W)\), with \(W\) the total weight, and walk the entries subtracting each weight until \(r\) falls inside one:

```text
pick(weights):
    r = uniform(0, total(weights))
    for i, w in weights:
        if r < w: return i
        r -= w
    return last index with w > 0       // floating-point rounding
```

That is \(O(n)\) per pick. With the prefix sums stored, a binary search makes it \(O(\log n)\). Walker's alias method makes it \(O(1)\) after an \(O(n)\) setup, for very large tables picked from very often. Both need rebuilding when a weight changes.

## Shuffles

### Fisher–Yates

```text
shuffle(a):
    for i from a.length - 1 down to 1:
        j = uniform integer in [0, i]   // inclusive of i
        swap a[i], a[j]
```

Every permutation is equally likely, in \(O(n)\). The common mistake is drawing `j` from the whole array every time, \([0, n)\). That makes \(n^n\) equally likely swap sequences for \(n!\) permutations, and since \(n^n\) is not a multiple of \(n!\), some orders come up more often than others.

Stopping after \(k\) steps leaves the last \(k\) slots as a uniform random sample of \(k\) items, without repeats. That is the way to deal \(k\) cards.

### Shuffle bags

Uniform randomness repeats and goes dry: the same item three times, then nothing of another for a long stretch. A shuffle bag holds a fixed mix, shuffled, and is drawn from until empty, then refilled:

```text
draw():
    if bag is empty:
        bag = copy of contents
        shuffle(bag)
        if bag.last == previous draw and bag has 2 or more items:
            swap bag.last with a random other item
    return bag.pop()
```

Over each refill, every item appears exactly as often as it is in the contents. The Tetris 7-bag is one of each piece per bag. The extra swap stops the same item appearing twice across the refill boundary.

## Non-uniform distributions

### Shapes from uniform

| Distribution | Recipe | Use |
| --- | --- | --- |
| Triangular on \([-1, 1]\) | \(u_1 - u_2\) | Weapon spread that clusters at the centre. |
| Roughly normal | Sum of 3 or more uniforms, rescaled | Cheap bell curve for stats. |
| Normal, mean 0, deviation 1 | Box–Muller: \(\sqrt{-2\ln u_1}\,\cos(2\pi u_2)\) | Exact. Clamp or reroll the tails a game cannot allow. |
| Exponential, rate \(\lambda\) | \(-\ln(1 - u)/\lambda\) | Time until the next random event, such as a lightning strike, averaging \(1/\lambda\). |
| Biased towards 0 | \(u^k\), \(k > 1\) | Rare high values, such as a large critical bonus. |

In Box–Muller, use \(1 - u_1\) if the generator can return exactly 0, since \(\ln 0\) is \(-\infty\).

### Points in shapes

A uniform point in a disc of radius \(R\) is

\[
r = R\sqrt{u_1}, \qquad \phi = 2\pi u_2
\]

Without the square root, points bunch at the centre, because the inner rings have less area than the outer ones. Unity's `Random.insideUnitCircle` already does this correctly, as do `insideUnitSphere` and `onUnitSphere`.

A uniform point inside a sphere or other shape can also come from rejection: pick in the bounding box, and try again if it is outside. For a sphere, about 52% of tries land inside.

Points that are random but never too close to each other, such as trees, are Poisson disc samples. Bridson's algorithm generates them in \(O(n)\).

## Fairness

Players judge streaks, not averages. A 25% critical strike chance misses 10 times in a row about 1 time in 18, which feels broken.

### Pseudo-random distribution

Raise the chance with every failure and reset it on success. On the \(N\)-th attempt since the last success, the chance is \(C \cdot N\). \(C\) is chosen so the long-run rate is still the nominal \(p\):

| Nominal \(p\) | \(C\) |
| --- | --- |
| 5% | 0.00380 |
| 10% | 0.01475 |
| 15% | 0.03222 |
| 20% | 0.05570 |
| 25% | 0.08474 |
| 30% | 0.11895 |
| 40% | 0.20155 |
| 50% | 0.30210 |

At 25%, the first attempt after a success has an 8.5% chance, and success is certain by the 12th. Long droughts and long streaks both become rare. Dota 2 uses this for critical strikes and bashes.

\(C\) has no closed form. Find it numerically: for a candidate \(C\), the expected number of attempts per success is \(E = \sum_N N\,P(\text{first success at } N)\), and the rate is \(1/E\). Bisect on \(C\) until the rate equals \(p\).

The [pity counter on loot tables](../unity/systems/loot.md#pity) is the same idea with a hard cap instead of a ramp.

!!! warning "Common pitfalls"

    `Random.Range(0, 10)` with two `int`s never returns 10. With two `float`s it can.

    A new `System.Random` made for each roll, seeded from the clock, returns the same value for every roll in the same millisecond. Keep one generator and draw from it.

    A shuffle that draws the swap index from the whole array is biased. Draw from \([0, i]\).

    A random point in a circle from a random radius and angle bunches at the centre. Take the square root of the radius.

    Two systems sharing one seeded generator stop being reproducible the moment either changes how many numbers it draws.
