# Parallel for and data layout

Most parallel work in a game is one loop over many items: update every particle, cull every object, step every agent. A **parallel for** splits that loop into batches and runs each batch as a job. Doing it well is mostly about batch sizes and about how the data is laid out.

## Batches

```text
parallel_for(count, batch_size, body):           // body(begin, end)
    batches = ceil(count / batch_size)
    counter = atomic(batches)
    for b in 0 .. batches - 1:
        begin = b * batch_size
        end = min(begin + batch_size, count)
        submit(Job { body over [begin, end), counter })
    wait(counter)
```

Each job gets a range, not a single item, so the scheduling cost is paid once per batch.

### Choosing a batch size

- **Too small**: scheduling dominates. A job costs somewhere around a microsecond to submit, steal, and finish; a batch should do much more work than that, at least 10 to 50 microseconds.
- **Too large**: some workers finish early and sit idle while others run long batches. With 8 workers and 8 batches, one slow batch decides the time.
- **A good start**: about 4 to 8 batches per worker, never under the minimum work size. Then measure: the best size depends on the work per item.

Work that varies per item (some agents path-find, most do not) needs more, smaller batches, so that the expensive ones are spread out.

### Splitting on demand

Instead of a fixed batch size, start with one job for the whole range, and split when other workers are idle:

```text
range_job(begin, end):
    while end - begin > min_batch and workers are idle:
        mid = (begin + end) / 2
        submit(range_job(mid, end))       // another worker can steal the upper half
        end = mid
    body(begin, end)
```

Large ranges are split into halves as long as someone can take them, and small ranges run without overhead. This is how Intel TBB's `parallel_for` and Rust's Rayon balance uneven work.

## Data access rules

A parallel loop is only correct if batches do not interfere:

1. **Each batch writes only its own range** of the output arrays.
2. **Shared data is read-only** for the whole loop. Nothing else writes it while the loop runs.
3. **No batch adds to or removes from a shared container.** A `push_back` from two threads corrupts the container.

Where a batch must produce a variable number of results (hits from a raycast batch, entities to destroy), give each batch its own output and combine them afterwards:

```text
outputs = array of lists, one per batch

body(begin, end, batch_index):
    for i in begin .. end - 1:
        if needs_destroying(i): outputs[batch_index].append(i)

after the loop:
    for list in outputs, in batch order: apply(list)
```

Combining in **batch order**, not in the order batches finished, keeps the result the same on every run.

## Reductions

A sum, minimum, or bounding box over all items: compute one partial result per batch, then combine the partials.

```text
partial = array(batches)
body(begin, end, b): partial[b] = sum of values[begin .. end - 1]
total = sum of partial, in index order
```

An atomic add per item gives the right total too, but every core then fights over one cache line, and it is often slower than the single-threaded loop.

Floating-point addition is not associative, so the total depends on how the items were grouped. To get the same result on every machine, make batch boundaries depend only on `count` and a fixed batch size, never on the number of workers, and combine partials in a fixed order. [Determinism tests](../testing/index.md#determinism-tests) catch it when this goes wrong.

## False sharing

Memory moves between cores in **cache lines** of 64 bytes. When two cores write different variables that sit in the same line, the line bounces between their caches on every write, and both slow down, although they never touch each other's data. This is **false sharing**.

```cpp
// Bad: per-worker counters packed together; neighbours share a cache line.
int hits[MAX_WORKERS];

// Good: each counter on its own cache line.
struct alignas(64) PaddedCount { int value; };
PaddedCount hits[MAX_WORKERS];
```

- Pad per-thread data (counters, partial results, allocator state) to 64 bytes, or use `std::hardware_destructive_interference_size` in C++17.
- Batches writing **contiguous ranges** of an array only share a line at the boundary between two batches, which is harmless. Splitting work by interleaving (worker k takes items k, k+N, k+2N...) puts every worker in every line, and is much slower.
- The symptom is a loop that gets slower as threads are added, without any locks.

## Layout for parallel loops

The single-threaded advice from [collections and data layout](../../csharp/performance/collections.md#arrays-of-structs-structs-of-arrays) matters more in parallel: each core has its own cache, and memory bandwidth is shared between all of them.

- Store the data a loop needs in contiguous arrays, ideally one array per field (structure of arrays), so each batch streams through memory.
- Keep the data a loop writes separate from data it only reads, so writes do not invalidate cache lines other cores are reading.
- A loop over an array of pointers to objects scattered across the heap is limited by memory latency, and adding cores barely helps.
- An [archetype ECS](../ecs/archetype-storage.md) gives this layout for free: a query is a list of tables, each with packed columns, and each table (or chunk of one) is a natural batch.

## Nested parallelism

A job inside a parallel loop that starts its own parallel loop (for each agent, a parallel search) multiplies jobs quickly, and its inner `wait` puts helping deep on the stack. Parallelise one level, usually the outermost loop with enough items. Use the inner loop only when the outer one is too short to keep every worker busy.
