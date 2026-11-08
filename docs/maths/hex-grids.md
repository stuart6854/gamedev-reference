---
uses:
  - name: Strategy and tactics
    text: Movement ranges, distances, and line of sight on a hex map with no diagonal special cases.
  - name: Base building
    text: Hex tiles for settlement and territory layouts.
---

# Hex grids

Hexagons have six neighbours, all the same distance away, so movement and distance have none of the diagonal special cases of a square grid. The cost is that coordinates are less obvious. The coordinate systems here follow Amit Patel's [Hexagonal Grids](https://www.redblobgames.com/grids/hexagons/) at Red Blob Games, which is the standard reference.

## Orientation

| | Pointy-top | Flat-top |
| --- | --- | --- |
| Shape | A vertex at the top | A flat edge at the top |
| Rows | Horizontal rows, alternate rows shifted half a hex | Vertical columns, alternate columns shifted |
| Width × height of one hex | √3 · size × 2 · size | 2 · size × √3 · size |

`size` is the distance from the centre to a corner. Choose one orientation per game; the maths below is for pointy-top, with flat-top conversions noted.

## Coordinate systems

### Cube and axial

Treat each hex as a point on the plane `q + r + s = 0` in 3D. The three axes run along the three directions of hex rows:

```text
Cube  { q, r, s }  with q + r + s == 0
Axial { q, r }     with s = -q - r implied
```

**Axial** is cube with the third coordinate dropped, because it is always derivable. Store axial; compute `s` when an algorithm needs it. Almost every hex algorithm is simple in cube coordinates and awkward in any other.

### Offset

Offset coordinates are row and column, like a square grid with every other row shifted. They are natural for storing a rectangular map in a 2D array, and for displaying coordinates to players, but neighbours and distances depend on whether the row is odd or even. Convert to axial for any maths, and back for storage:

```text
// "odd-r": pointy-top, odd rows shifted right
offset_to_axial(col, row) = (col - (row - (row & 1)) / 2, row)
axial_to_offset(q, r)     = (q + (r - (r & 1)) / 2, r)
```

`row & 1` (not `row % 2`) keeps negative rows correct, and the division is exact because the numerator is always even.

## Neighbours

```text
DIRECTIONS = [ (+1, 0), (+1, -1), (0, -1), (-1, 0), (-1, +1), (0, +1) ]    // axial

neighbour(h, i) = h + DIRECTIONS[i]
```

Unlike offset coordinates, the six offsets are the same for every hex. The diagonal neighbours (the six hexes two steps away between the direct neighbours) are `(+2, -1), (+1, -2), (-1, -1), (-2, +1), (-1, +2), (+1, +1)`.

## Distance

The number of steps between two hexes:

```text
distance(a, b):
    dq = a.q - b.q
    dr = a.r - b.r
    ds = (-a.q - a.r) - (-b.q - b.r)
    return (abs(dq) + abs(dr) + abs(ds)) / 2
```

Each step changes two of the three cube coordinates by one, so the total change divided by two is the step count. It is exact, and matches pathfinding on an empty map.

## Hex to world, and back

```text
// Pointy-top
hex_to_world(q, r) = (size * (√3 * q + √3/2 * r),  size * (3/2 * r))

world_to_hex(x, y):
    q = (√3/3 * x - 1/3 * y) / size
    r = (2/3 * y) / size
    return cube_round(q, r)

// Flat-top
hex_to_world(q, r) = (size * (3/2 * q),  size * (√3/2 * q + √3 * r))
world_to_hex(x, y) = cube_round((2/3 * x) / size, (-1/3 * x + √3/3 * y) / size)
```

The world position is the hex centre; `y` here is whichever world axis runs "down the map" (z in a 3D game on the ground plane).

### Rounding

`world_to_hex` gives fractional coordinates. Rounding q and r separately is wrong near corners. Round all three cube coordinates, then fix the one that changed most, so that `q + r + s` stays zero:

```text
cube_round(fq, fr):
    fs = -fq - fr
    q, r, s = round(fq), round(fr), round(fs)
    dq, dr, ds = abs(q - fq), abs(r - fr), abs(s - fs)
    if dq > dr and dq > ds: q = -r - s
    else if dr > ds:        r = -q - s
    return (q, r)
```

This is how a mouse click becomes a hex: ray-cast to the ground plane, then `world_to_hex`.

## Lines

The hexes on a straight line between two hexes, for line of sight and for drawing paths:

```text
line(a, b):
    n = distance(a, b)
    result = []
    for i in 0 .. n:
        t = (n == 0) ? 0 : i / n
        q = lerp(a.q + 1e-6, b.q + 1e-6, t)
        r = lerp(a.r + 1e-6, b.r + 1e-6, t)
        result.append(cube_round(q, r))
    return result
```

The tiny nudge stops points that land exactly on the edge between two hexes from rounding inconsistently. Line of sight is then "no blocking hex in `line(a, b)` except the ends". For smoother sight lines, test the line against the hexes' actual edges instead, as on the [frustum and visibility](frustum.md) page.

## Ranges and rings

```text
// Every hex within n steps of the centre.
range(centre, n):
    for q in -n .. n:
        for r in max(-n, -q - n) .. min(n, -q + n):
            yield centre + (q, r)

// Every hex exactly n steps away, walking around the ring.
ring(centre, n):
    if n == 0: yield centre; return
    h = centre + DIRECTIONS[4] * n
    for side in 0 .. 5:
        for step in 0 .. n - 1:
            yield h
            h = neighbour(h, side)
```

- `range` gives `3n² + 3n + 1` hexes: an area-of-effect radius, or a vision radius before line-of-sight checks.
- `ring` starts at the hex `n` steps in direction 4 and walks the six sides. Rings at increasing `n` give a **spiral**, useful for searching outward for the nearest free hex.
- **Movement range with costs or obstacles** is a breadth-first search (or Dijkstra for varying terrain costs) over `neighbour`, stopping at the movement budget.

## Rotation

Rotating a hex 60° around the origin permutes and negates the cube coordinates:

```text
rotate_clockwise(q, r, s)     = (-r, -s, -q)
rotate_anticlockwise(q, r, s) = (-s, -q, -r)
```

To rotate around another hex, subtract it, rotate, add it back. Rotating multi-hex buildings and area-of-effect shapes is a loop of this over their hexes.

## Storing a map

| Map shape | Storage |
| --- | --- |
| Rectangular | 2D array indexed by offset coordinates (`axial_to_offset`) |
| Hexagonal (a big hexagon of radius N) | 2D array of `(2N + 1) × (2N + 1)` indexed by `(q + N, r + N)`; corners unused |
| Sparse or unbounded | Hash map from axial `(q, r)` to tile data, or a [spatial hash](../data-structures/spatial-hash.md) of chunks |

Pack `(q, r)` into one integer for hash keys, with each coordinate offset to be non-negative (see [packing fields](../data-structures/bits.md#packing-fields)).

## In Unity

- A **Grid** component with **Cell Layout** set to **Hexagon** lays out a hexagonal Tilemap. The Cell Swizzle setting chooses the orientation: XYZ is pointy-top, YXZ flat-top.
- Its cell coordinates are **offset** coordinates, shifting every other row (or column). `Grid.WorldToCell` and `Grid.CellToWorld` convert between world space and those cells. Convert cells to axial with the offset functions above before doing distance, range, or line maths, and back to place tiles. Check which rows Unity shifts (place a tile at cell (0, 1) and see which way it moves) and pick the matching odd or even formula.
- For 3D hex maps without Tilemap, `hex_to_world` gives each tile's position on the XZ plane.
