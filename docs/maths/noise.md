---
uses:
  - name: Open worlds
    text: Terrain height, biomes, and scattered vegetation from a seed, with no stored map.
  - name: Roguelikes
    text: Cave and overworld generation that is different every run and the same for every seed.
  - name: Top-down survival
    text: Resource placement, fog density, and wind that varies smoothly across the map.
---

# Noise

Random numbers are different at every point. **Noise** is randomness that changes smoothly: nearby inputs give nearby outputs, but there is no visible pattern at a larger scale. It is the basis of procedural terrain, clouds, fire, wind, camera shake, and natural-looking placement. This page builds value and gradient noise, layers them into fractal noise, and shapes the result.

All noise here is a pure function of position and seed: `noise(x, y, seed)`. The same inputs always give the same output, so a world never needs storing, only its seed.

## Hashing lattice points

Noise starts from random values at integer grid points (the **lattice**). They must be random but repeatable, so they come from a hash of the coordinates and the seed, not from a generator:

```text
hash(ix, iy, seed) -> u32:
    h = seed
    h = (h ^ ix) * 0x27d4eb2d
    h = (h ^ iy) * 0x165667b1
    h = h ^ (h >> 15)
    h = h * 0x2c1b3c6d
    h = h ^ (h >> 12)
    return h                    // all arithmetic wraps at 32 bits

hash01(ix, iy, seed) = hash(ix, iy, seed) / 4294967295.0
```

Any good integer hash works (this one mixes with multiplications by odd constants and shifts). The classic alternative is Ken Perlin's 256-entry permutation table, `perm[perm[ix & 255] + (iy & 255)]`, which repeats every 256 units and needs a different table per seed.

## Value noise

Interpolate the random values at the four corners of the cell around the point:

```text
fade(t) = t * t * t * (t * (t * 6 - 15) + 10)          // 6t^5 - 15t^4 + 10t^3

value_noise(x, y, seed):
    ix, iy = floor(x), floor(y)
    fx, fy = x - ix, y - iy
    a = hash01(ix,     iy,     seed)
    b = hash01(ix + 1, iy,     seed)
    c = hash01(ix,     iy + 1, seed)
    d = hash01(ix + 1, iy + 1, seed)
    u, v = fade(fx), fade(fy)
    return lerp(lerp(a, b, u), lerp(c, d, u), v)        // 0 .. 1
```

The **fade** curve has zero first and second derivatives at 0 and 1, so the noise is smooth across cell edges. Plain linear interpolation shows the grid as creases. Value noise is cheap, but its features line up with the grid, which shows as blocky patterns.

## Gradient (Perlin) noise

Instead of a random value at each lattice point, put a random **direction** (gradient) there. The noise at a point is a blend of each corner's gradient dotted with the offset from that corner:

```text
GRADIENTS_2D = 8 unit vectors at 45° steps

gradient_noise(x, y, seed):
    ix, iy = floor(x), floor(y)
    fx, fy = x - ix, y - iy

    corner(cx, cy):
        g = GRADIENTS_2D[hash(ix + cx, iy + cy, seed) & 7]
        return dot(g, (fx - cx, fy - cy))

    u, v = fade(fx), fade(fy)
    return lerp(lerp(corner(0, 0), corner(1, 0), u),
                lerp(corner(0, 1), corner(1, 1), u), v)
```

- The result is roughly **−0.7 to 0.7** in 2D (the theoretical limit is ±√½), and usually much smaller. Remap it with `noise * 0.5 / 0.7 + 0.5`, or measure the range of your implementation and normalise to that.
- It is **zero at every lattice point**, because the offset from the corner is zero there. Sampling at integer coordinates returns a constant. Scale the input by a non-integer frequency, or add an offset.
- Features are rounder and less grid-aligned than value noise. This is the noise most tools mean by "Perlin noise".

**Simplex noise** (also by Ken Perlin) uses a triangular lattice instead of squares: fewer corners per sample (3 in 2D, 4 in 3D instead of 4 and 8), fewer directional artefacts, and it scales better to 3D and 4D. OpenSimplex2 is a widely used patent-free variant. For 3D and 4D (animated 3D) noise, prefer simplex.

## Fractal noise (fBm)

One layer of noise has features of one size. Natural shapes have detail at every scale: mountains, then hills on the mountains, then rocks. Add several layers (**octaves**), each at a higher frequency and lower amplitude:

```text
fbm(x, y, seed, octaves = 5, lacunarity = 2.0, gain = 0.5):
    sum = 0, amplitude = 1, frequency = 1, total = 0
    for i in 0 .. octaves - 1:
        sum += amplitude * gradient_noise(x * frequency, y * frequency, seed + i)
        total += amplitude
        frequency *= lacunarity
        amplitude *= gain
    return sum / total                                  // same range as one octave
```

| Parameter | Effect | Typical |
| --- | --- | --- |
| `octaves` | How many layers of detail. Each costs one more noise sample | 4 to 8 |
| `lacunarity` | How much finer each octave is | 2.0 (use 1.9 to 2.1 to avoid octaves lining up) |
| `gain` (persistence) | How much weaker each octave is. Higher is rougher | 0.4 to 0.6 |
| Base frequency | The size of the largest features: `fbm(x * f, y * f)` | 1 / (feature size in world units) |

Giving each octave a different seed (`seed + i`) stops their zero points lining up at the origin.

Stop adding octaves once they are smaller than a pixel or a vertex: detail finer than the sampling is invisible, or shows as aliasing.

## Shaping the result

Raw fBm looks like rolling hills everywhere. Most of the art is in reshaping it:

```text
ridged(x, y)    = 1 - abs(gradient_noise(x, y))         // sharp crests: mountain ridges, veins
billow(x, y)    = abs(gradient_noise(x, y))             // rounded lumps: clouds, rocks
terraced(h, n)  = floor(h * n) / n                      // flat steps: mesas, rice terraces
islands(h, d)   = h - d * d                             // d = distance from the centre, 0..1: land falls into sea at the edges
```

- Use `ridged` per octave inside the fBm loop for mountain ranges.
- **Redistribute** heights with a curve: `pow(h, 2)` flattens low ground into plains and keeps peaks steep. A curve authored by a designer (an `AnimationCurve` in Unity) gives direct control.
- **Masks**: multiply mountain noise by a low-frequency noise, so mountains only appear in some regions.

### Domain warping

Offset the input position by another noise before sampling. The result looks folded and flowing, like geology or marble:

```text
warp(x, y):
    qx = fbm(x,       y,       seed + 10)
    qy = fbm(x + 5.2, y + 1.3, seed + 20)
    return fbm(x + strength * qx, y + strength * qy, seed)
```

The offsets (5.2, 1.3) make the two warp noises independent. `strength` around 1 to 4 (in noise units) gives visible folding. Warping twice, with the second warp sampling the first's result, exaggerates it further, at three times the cost.

## Common uses

| Use | Recipe |
| --- | --- |
| Terrain height | fBm, redistributed, with ridged noise masked into mountain regions |
| Biomes | Two low-frequency noises (temperature and moisture), looked up in a table of biomes |
| Placement | Place a tree where `noise(x, y) > threshold`, or use noise as a density for [scattered points](random.md) |
| Caves | 3D noise, solid where above a threshold; or 2D noise with a cellular automaton pass |
| Camera shake, flicker, wind | 1D noise over time: `noise(time * frequency, seed)` per axis. Smooth, unlike `random()` each frame |
| Animated clouds and water | 3D noise with time as the third axis, or 2D noise with a scrolling domain warp |

### Tiling

Noise that must wrap seamlessly (a tiling texture, a world that wraps around) needs the lattice to repeat: wrap the integer coordinates before hashing, `hash(ix mod period, iy mod period)`, with the period a whole number of cells at every octave. Unity.Mathematics' `noise.pnoise` takes a period directly.

## Cellular (Worley) noise

A different family: scatter one random point per cell, and return the distance to the nearest point (F1), or the second nearest (F2):

```text
cellular(x, y, seed):
    ix, iy = floor(x), floor(y)
    f1 = infinity
    for oy in -1 .. 1:
        for ox in -1 .. 1:
            cx, cy = ix + ox, iy + oy
            point = (cx + hash01(cx, cy, seed), cy + hash01(cx, cy, seed + 1))
            f1 = min(f1, distance((x, y), point))
    return f1
```

F1 looks like cells or scales; `F2 − F1` gives the edges between cells: cracked mud, stone walls, Voronoi regions for territories.

## In Unity

- `Mathf.PerlinNoise(x, y)` returns 2D gradient noise in roughly 0 to 1 (it can slightly exceed both ends). It has no seed parameter: offset the inputs by large random amounts from your seeded generator instead. Avoid integer inputs, which all return the same value.
- **Unity.Mathematics** (`using static Unity.Mathematics.noise;`) has `cnoise` (classic Perlin), `snoise` (simplex), `pnoise` (periodic Perlin), and `cellular` (Worley, returning F1 and F2), in 2D, 3D, and 4D, returning roughly −1 to 1. They work in Burst jobs, so a whole heightmap can be generated in parallel.
- **Shader Graph** has Simple Noise (value), Gradient Noise, and Voronoi nodes, for noise evaluated per pixel on the GPU.
- Bake noise into a texture when the same values are read many times per frame (terrain textures, VFX). Evaluate it directly when it is read once, or must be infinite.
