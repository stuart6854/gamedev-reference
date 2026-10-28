# Ring buffer

A fixed-capacity queue in one array. Pushing writes at the back, popping reads from the front, and both wrap around the end of the array, so nothing moves and nothing allocates after creation. Also called a circular buffer.

Typical uses:

- Input history and buffering, such as "was jump pressed in the last 0.1 seconds".
- The last N frame times, for a graph or a moving average.
- Recent log lines for an in-game console.
- Network snapshots waiting to be interpolated.
- A queue between two threads, such as audio or a job feeding the main thread.

## When it is full

The capacity is fixed, so every ring buffer picks one of two policies:

| Policy | Push when full | Use for |
| --- | --- | --- |
| **Reject** | Returns false. The caller decides. | Work queues and commands, where dropping an item is a bug. |
| **Overwrite** | Drops the oldest item and pushes. | History: input, frame times, logs, snapshots, where only the latest N matter. |

## Layout

An array, the index of the oldest item, and a count:

```text
items[capacity]
head  = 0       // index of the oldest item
count = 0
```

The item at position `i` from the front is at `items[(head + i) % capacity]`. Keeping a count, rather than only a head and a tail, avoids the classic ambiguity where `head == tail` could mean empty or full. The other fixes for that ambiguity are below.

## Operations

```text
push(value):                            // reject when full
    if count == capacity: return false
    items[(head + count) % capacity] = value
    count += 1
    return true

push_overwrite(value):                  // drop the oldest when full
    if count == capacity:
        items[head] = value             // the oldest slot becomes the newest
        head = (head + 1) % capacity
    else:
        items[(head + count) % capacity] = value
        count += 1

pop():
    if count == 0: return nothing
    value = items[head]
    clear items[head]                   // see the language tips
    head = (head + 1) % capacity
    count -= 1
    return value

at(i):                                  // 0 is the oldest
    return items[(head + i) % capacity]

from_newest(i):                         // 0 is the newest
    return items[(head + count - 1 - i) % capacity]

clear():
    head = 0
    count = 0
```

Callers check `i < count` before `at` or `from_newest`. Written this way, every index inside the brackets is non-negative, which matters below.

## Power-of-two capacity

With a capacity that is a power of two, `% capacity` becomes `& (capacity - 1)`, a single AND. Round the requested capacity up when the buffer is created.

That also allows a layout with no count at all: two unsigned counters that only ever increase, and wrap at the integer's own limit.

```text
MASK  = capacity - 1                    // capacity is a power of two
read  = 0                               // total items ever popped
write = 0                               // total items ever pushed

size()   = write - read                 // unsigned subtraction, correct across wrap
empty()  = write == read
full()   = write - read == capacity

push(value):
    if full(): return false
    items[write & MASK] = value
    write += 1

pop():
    if empty(): return nothing
    value = items[read & MASK]
    read += 1
    return value
```

`write - read` stays right after `write` wraps past the top of a 32-bit integer, because unsigned subtraction is arithmetic modulo \(2^{32}\), and \(2^{32}\) is a multiple of the capacity. The capacity must be at most \(2^{31}\). This layout is also the one a single-producer, single-consumer queue uses, because each counter has exactly one writer.

## Iterating

Front to back is `at(0)` to `at(count - 1)`. For a bulk copy, or to hand the contents to an API that takes a contiguous span, the items are at most two runs:

```text
first  = items[head .. min(head + count, capacity))
second = items[0 .. head + count - capacity)       // empty unless the items wrap
```

Copy `first` then `second`, and the result is in order.

## Examples

### Input history

Keep each press with its time, overwriting the oldest. A fighting-game motion such as down, down-forward, forward is a match of the sequence against the history, newest first:

```text
history = ring buffer of { input, time }, capacity 16, overwrite

on input pressed:
    history.push_overwrite({ input, now })

matches(sequence, window):
    j = sequence.length - 1             // match the last input first
    for i in 0 .. history.count:
        e = history.from_newest(i)
        if now - e.time > window: return false
        if e.input == sequence[j]:
            j -= 1
            if j < 0:
                history.clear()         // one motion, one move
                return true
    return false
```

Walking from the newest means the first entry outside the window ends the search. Other inputs between the steps are skipped, which is the usual leniency. The same buffer with a one-item sequence is a jump buffer.

### Moving average

Keep a running sum alongside the buffer. Subtract the item about to be overwritten, then add the new one:

```text
push_sample(x):
    if samples.count == capacity:
        sum -= samples.at(0)
    samples.push_overwrite(x)
    sum += x

average() = sum / samples.count
```

With floats, the running sum drifts by rounding error over hours. Recompute it from the items every few thousand pushes, or keep it as a double.

### Snapshot interpolation

Snapshots arrive in time order, so the buffer stays sorted. To draw at `render_time`, find the newest snapshot at or before it, and the one after it:

```text
for i in 0 .. snaps.count - 1:
    older = snaps.from_newest(i + 1)
    newer = snaps.from_newest(i)
    if older.time <= render_time <= newer.time:
        t = (render_time - older.time) / (newer.time - older.time)
        return lerp(older, newer, t)
```

`t` is the [inverse lerp](../maths/interpolation.md#inverse-lerp) of the render time between the two snapshots.

## Between two threads

A ring buffer with one producer thread and one consumer thread needs no lock, using the free-running counters above:

- Only the producer writes `write`. Only the consumer writes `read`.
- The producer writes the item, then publishes `write` with a **release** store. The consumer loads `write` with an **acquire** load before reading the item. Without that pairing, the consumer can see the new counter before the item it describes.
- The same pairing runs the other way for `read`, so the producer does not overwrite a slot the consumer is still reading.
- Put `read` and `write` on different cache lines. Otherwise every push and pop bounces one cache line between the two cores.

Two producers or two consumers break the scheme: both can claim the same slot. That needs a different queue, or a lock.

## Language tips

=== "C++"

    - For a compile-time capacity, use `std::array<T, N>` and `static_assert((N & (N - 1)) == 0)` for the mask version. For a runtime capacity, a `std::unique_ptr<T[]>` sized once.
    - `std::deque` is not a ring buffer. It allocates in chunks as it grows and has no fixed capacity.
    - `pop` should move out: `T value = std::move(items[head]);`. For a type that owns memory, reset the slot afterwards so the buffer does not hold a moved-from object's resources.
    - For the two-thread queue, the counters are `std::atomic<std::uint32_t>`, using `store(..., std::memory_order_release)` and `load(std::memory_order_acquire)`. Pad them apart with `alignas(64)`. `std::hardware_destructive_interference_size` is the portable name, where the standard library provides it.

=== "C#"

    - `Queue<T>` is a ring buffer inside, but it grows when full and has no overwrite. Use a `T[]` with `head` and `count` fields for a fixed capacity.
    - In `pop`, set the vacated slot to `default` when `T` is a reference type or contains references, so the garbage collector can free it. Use `RuntimeHelpers.IsReferenceOrContainsReferences<T>()` to skip that for plain structs.
    - The two runs from [Iterating](#iterating) map onto `new ReadOnlySpan<T>(items, start, length)`, which copies nothing.
    - C#'s `%` keeps the sign of the left side, so `-1 % 8` is `-1`. Any formula that subtracts before the modulo, such as `(head - 1) % capacity`, must add `capacity` first: `(head - 1 + capacity) % capacity`.
    - For the two-thread queue, publish with `Volatile.Write(ref _write, value)` and read with `Volatile.Read(ref _write)`. They give release and acquire ordering.

!!! warning "Common pitfalls"

    `head == tail` is both empty and full in a head-and-tail layout. Keep a count, leave one slot always unused, or use free-running counters. Do not mix two of them.

    Indexing back from the head with `(head - i) % capacity` goes negative with signed integers in C, C++, and C#, and jumps to a huge index with unsigned ones. Add the capacity before the modulo, or index from the front as `at` does.

    Overwrite and reject are different queues. A command queue that silently overwrites loses commands with no error.

    A free-running counter layout with a capacity that is not a power of two is wrong after the counter wraps, because \(2^{32}\) is no longer a multiple of the capacity.

    Holding a reference to an item across a push is unsafe in overwrite mode: the next push can overwrite that slot.
