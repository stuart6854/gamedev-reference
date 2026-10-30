---
uses:
  - name: Hordes and crowds
    text: Each agent finds its neighbours for separation and flocking without testing every other agent.
  - name: Stealth
    text: A noise or a sight check only looks at the agents in the cells around it.
  - name: Shooters
    text: Thousands of bullets test against the few targets in their cell.
  - name: RPGs
    text: An explosion or a spell finds everything within its radius.
  - name: Multiplayer
    text: The server sends each client only the entities in the cells near it.
---

# Spatial hash grid

Space cut into equal square cells, with each object filed under the cell it is in. "What is near this point" then looks at a few cells instead of every object. The cells are keys in a hash table, so only occupied cells cost memory and the world can be unbounded.

For \(n\) objects, testing every pair is \(O(n^2)\): 2,000 agents is two million distance checks a frame. With a grid, each agent checks only the agents in the cells around it, which is \(O(n)\) when the density is even.

## Grid or tree

| | Spatial hash grid | Fixed grid (array) | Quadtree / octree |
| --- | --- | --- | --- |
| World size | Unbounded | Bounded, known up front | Bounded root |
| Memory | Occupied cells only | Every cell | Nodes where objects are |
| Even density, similar sizes | Best | Best | Fine |
| Very uneven density | Crowded cells get slow | Crowded cells get slow | Adapts |
| Objects of very different sizes | Awkward | Awkward | Handles well |
| Moving objects | Cheap to rebuild every frame | Cheap to rebuild every frame | Costly to rebalance |

Agents in a game world are usually similar in size, evenly spread, and all moving. That is the grid's best case.

## Cells and keys

```text
cell(p) = (floor(p.x / s), floor(p.y / s))          // s is the cell size
key(cx, cy) = hash(cx, cy)
```

Use `floor`, not truncation. Truncation sends both \(-0.5\) and \(+0.5\) to cell 0, which makes cell 0 twice as wide and breaks every query near the origin.

A common hash for integer cells, from Teschner et al., is

\[
h = (c_x \cdot 73856093) \oplus (c_y \cdot 19349663) \oplus (c_z \cdot 83492791)
\]

with the products allowed to overflow. Take it modulo the bucket count, or mask it when the count is a power of two.

Two different cells can land in the same bucket. That is fine: a query checks each object's real distance anyway, so a collision costs a few extra checks, never a wrong answer. It does mean a query must not scan the same bucket twice; see the query below.

## Choosing the cell size

A radius query visits \((2\lceil r/s \rceil + 1)^2\) cells in 2D.

| Cell size \(s\) | Cells per query of radius \(r\) | Objects per cell | Effect |
| --- | --- | --- | --- |
| \(s = r\) | 9 | Moderate | The usual choice. |
| \(s = 2r\) | 9, but larger | Many | Fewer cells, more wasted distance checks. |
| \(s = r/2\) | 25 | Few | More cells to visit, fewer wasted checks. |

Set \(s\) to the most common query radius, such as the separation distance of a crowd. If queries vary a lot, use the smaller radius, or keep two grids.

Objects much larger than a cell either go into every cell they overlap, and the query de-duplicates, or they live in a separate list that every query checks. A handful of large objects in a list is usually simpler.

## Moving objects

Two ways to keep the grid current:

- **Move incrementally.** Store each object's current cell. When it moves, compute the new cell; if it differs, remove it from the old cell's list and add it to the new one. With a swap-remove and the object's index in its cell stored, both are \(O(1)\). Good when few objects move.
- **Rebuild every frame.** Throw the grid away and insert everything again. With everything moving, this is often faster: no per-object bookkeeping, and the rebuild can lay the cells out contiguously in memory.

The contiguous rebuild is a counting sort by bucket:

```text
build(points):
    counts[all buckets] = 0
    for each point i: bucket[i] = key(cell(points[i])) mod B; counts[bucket[i]] += 1
    start = prefix sums of counts            // start[b] is where bucket b begins
    for each point i: items[start[bucket[i]] + filled[bucket[i]]++] = i

query(center, radius):
    for each cell (cx, cy) overlapping the circle:
        b = key(cx, cy) mod B
        if b was already scanned in this query: continue
        for k from start[b] to start[b + 1] - 1:
            i = items[k]
            if distance²(points[i], center) <= radius²: report i
```

`items` ends up as one array of object indices, grouped by bucket, so a query reads a few short contiguous runs. With \(B\) about twice the object count, most buckets hold one cell.

## Reference implementation

Engine-neutral C#, in 2D. For a 3D game on the ground plane, pass `x` and `z`. It rebuilds every frame and stores indices into the caller's position arrays, so it works with any object type.

```csharp
using System;
using System.Collections.Generic;

/// <summary>
/// A 2D spatial hash rebuilt from position arrays. Queries return indices into those arrays.
/// </summary>
public sealed class SpatialHashGrid
{
    readonly float _inverseCellSize;
    readonly int _mask;
    readonly int[] _start;          // bucket b's items are _items[_start[b] .. _start[b + 1])
    readonly int[] _fill;
    readonly List<int> _scanned = new List<int>(16);

    int[] _items = Array.Empty<int>();
    int[] _bucketOf = Array.Empty<int>();
    float[] _x = Array.Empty<float>();
    float[] _y = Array.Empty<float>();
    int _count;

    public float CellSize { get; }

    /// <param name="cellSize">Usually the most common query radius.</param>
    /// <param name="bucketCount">About twice the largest object count. Rounded up to a power of two.</param>
    public SpatialHashGrid(float cellSize, int bucketCount)
    {
        if (cellSize <= 0f)
            throw new ArgumentOutOfRangeException(nameof(cellSize));

        CellSize = cellSize;
        _inverseCellSize = 1f / cellSize;

        int buckets = 1;
        while (buckets < Math.Max(1, bucketCount))
            buckets <<= 1;
        _mask = buckets - 1;
        _start = new int[buckets + 1];
        _fill = new int[buckets];
    }

    /// <summary>Files the first count points. Keep the arrays unchanged until the next Build.</summary>
    public void Build(float[] x, float[] y, int count)
    {
        _x = x;
        _y = y;
        _count = count;

        if (_items.Length < count)
        {
            _items = new int[count];
            _bucketOf = new int[count];
        }

        Array.Clear(_start, 0, _start.Length);
        for (int i = 0; i < count; i++)
        {
            int bucket = Bucket(Cell(x[i]), Cell(y[i]));
            _bucketOf[i] = bucket;
            _start[bucket + 1]++;
        }

        for (int b = 1; b < _start.Length; b++)
            _start[b] += _start[b - 1];

        Array.Copy(_start, _fill, _fill.Length);
        for (int i = 0; i < count; i++)
            _items[_fill[_bucketOf[i]]++] = i;
    }

    /// <summary>Appends the index of every point within radius of (x, y). Does not clear results.</summary>
    public void Query(float x, float y, float radius, List<int> results)
    {
        float radiusSquared = radius * radius;
        int minX = Cell(x - radius), maxX = Cell(x + radius);
        int minY = Cell(y - radius), maxY = Cell(y + radius);

        _scanned.Clear();
        for (int cy = minY; cy <= maxY; cy++)
        {
            for (int cx = minX; cx <= maxX; cx++)
            {
                int bucket = Bucket(cx, cy);
                if (_scanned.Contains(bucket))
                    continue; // two cells in range share this bucket
                _scanned.Add(bucket);

                for (int k = _start[bucket]; k < _start[bucket + 1]; k++)
                {
                    int i = _items[k];
                    float dx = _x[i] - x;
                    float dy = _y[i] - y;
                    if (dx * dx + dy * dy <= radiusSquared)
                        results.Add(i);
                }
            }
        }
    }

    int Cell(float value) => (int)MathF.Floor(value * _inverseCellSize);

    int Bucket(int cx, int cy) => unchecked(cx * 73856093 ^ cy * 19349663) & _mask;
}
```

The Unity [steering](../unity/ai/steering.md), [perception](../unity/ai/perception.md), and [horde simulation](../unity/ai/horde.md) pages use this class.

A query appends the point itself if it is one of the indexed points. Callers that want neighbours skip their own index.

## Language tips

=== "C++"

    - `std::unordered_map<std::uint64_t, std::vector<int>>` works and is slow: a heap allocation per cell, and pointer chasing per lookup. The flat counting-sort layout above is the one to use for anything rebuilt every frame.
    - Pack two 32-bit cell coordinates into one 64-bit key when a true map is needed: `(std::uint64_t(std::uint32_t(cx)) << 32) | std::uint32_t(cy)`. The casts keep negative coordinates from sign-extending into the high half.
    - Signed integer overflow is undefined behaviour in C++. Do the hash multiplications in `std::uint32_t`.

=== "C#"

    - `Dictionary<long, List<int>>` allocates a list per new cell. Fine for a grid of static objects filled once; avoid it for one rebuilt every frame.
    - `unchecked` makes the hash overflow wrap even in a project compiled with overflow checking.
    - In Unity, the counting sort and the queries suit Burst jobs: keep the arrays in `NativeArray<T>`. `NativeParallelMultiHashMap<int, int>` is the ready-made alternative, with parallel writes.

!!! warning "Common pitfalls"

    Truncating instead of flooring makes cell 0 twice as wide in each axis, and queries near the origin miss objects.

    A query that does not skip already-scanned buckets reports an object twice when two cells in range hash to the same bucket.

    Cells much smaller than the query radius visit many cells. Cells much larger check many far objects. Start with the cell size equal to the radius.

    A cell where hundreds of agents pile up, such as a doorway or a horde on the player, makes every query near it slow. Cap how many neighbours a query returns, or how many it checks.

    The grid stores indices into arrays the caller owns. Rebuilding with arrays reordered, or querying after removing objects without a rebuild, returns the wrong objects.
