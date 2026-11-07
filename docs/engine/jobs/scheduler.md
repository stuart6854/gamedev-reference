# Scheduler

The scheduler owns the worker threads and decides which job each one runs next. This page builds one with per-worker queues, work stealing, counters to know when work is done, and waiting that keeps the waiting thread busy.

## Jobs

```text
Job {
    function            // void (*)(void* data)
    data                // pointer to the job's parameters
    counter             // atomic int to decrement when the job finishes, or null
}
```

A job is a function pointer and a pointer to its data: small, copyable, and not allocated on its own. Allocate job data from a per-frame or per-thread linear allocator (see [frame allocators](../patterns/frame.md#frame-allocators)), not with `new` per job. A frame may run thousands of jobs, and the general heap's lock becomes the bottleneck.

## Workers

```text
start(worker_count = hardware_threads - 1):
    for i in 0 .. worker_count - 1:
        start thread running worker_loop(i)
    // the main thread is worker index worker_count; it runs jobs while it waits
```

One worker per hardware thread, minus one for the main thread, which also runs jobs whenever it waits (see [waiting](#waiting-by-helping)). Keep threads that block out of the pool: the render thread waits on the GPU, and file and network I/O wait on the OS. A worker that blocks takes a core out of the pool. Give I/O its own small set of threads.

On consoles, workers are usually pinned to cores. On PC, leave scheduling to the OS: pinning fights with other programs and with the OS's own placement on hybrid CPUs that mix fast and efficient cores.

## Queues

A single shared queue makes every worker contend for one lock. Give each worker its own **double-ended queue** instead:

- The owner pushes and pops at the **bottom**. Its newest job is the one whose data is most likely still in its cache, and the owner rarely competes with anyone.
- Idle workers **steal** from the **top** of another worker's queue: the oldest jobs, which are usually the biggest pieces of work, so one steal brings plenty to do.

```text
worker_loop(i):
    while running:
        job = queues[i].pop_bottom()
        if not job: job = steal()
        if not job: job = global_queue.pop()      // jobs submitted from threads outside the pool
        if job: run(job)
        else: sleep_until_work()

steal():
    start = random index
    for k in 0 .. worker_count:
        victim = (start + k) mod (worker_count + 1)
        if victim != self:
            job = queues[victim].steal_top()
            if job: return job
    return none

run(job):
    job.function(job.data)
    if job.counter: job.counter.fetch_sub(1, release)
```

Start the steal search at a random worker, so idle workers spread out over victims instead of all trying worker 0 first.

The lock-free version of this queue is the **Chase–Lev deque**. Its pop and steal race on the last item and need careful atomics and memory ordering to get right. Start with a deque protected by a small lock per worker: with one queue per worker, the lock is almost never contended, and it is easy to get correct. Replace it only if a profile shows time in that lock.

## Sleeping and waking

Workers with nothing to do must sleep, or they burn a core and its power budget spinning. Waking them must be cheap, because jobs are submitted constantly.

```text
work_available: semaphore

submit(job):
    queues[current_worker].push_bottom(job)
    work_available.release(1)                  // wake at most one sleeping worker

sleep_until_work():
    spin briefly, checking the queues          // a job often arrives within microseconds
    work_available.acquire()                    // then sleep in the OS
```

- Release the semaphore once per job, not once per sleeping worker, so a single job does not wake every thread (a "thundering herd").
- Spin for a short time (a few microseconds, with a CPU pause instruction) before sleeping. Going to sleep and waking up again costs tens of microseconds, longer than many jobs.
- When submitting a batch of N jobs, release the semaphore `min(N, idle workers)` times in one call.

## Counters

A **counter** tracks how many jobs in a group have not finished:

```text
counter = atomic(N)
for i in 0 .. N - 1:
    submit(Job { function, data[i], counter })

wait(counter)        // returns when counter reaches 0
```

Each job decrements the counter when it finishes. A counter replaces a handle per job: waiting for 100 jobs is one counter, not 100 handles.

The decrement uses **release** ordering and the waiter's read uses **acquire**, so everything a job wrote before finishing is visible to the thread that sees the counter reach zero. Without that pairing, the waiter can see the count reach zero and still read the job's old output.

## Waiting by helping

A worker that waits for a counter must not just block. It would take a core out of the pool, and if every worker waits on jobs that sit in their queues, nothing runs and the game hangs. Instead, run other jobs while waiting:

```text
wait(counter):
    while counter.load(acquire) > 0:
        job = queues[self].pop_bottom() or steal()
        if job: run(job)
        else: pause, or briefly yield
```

The waiting thread keeps the pool's throughput up, and often runs the very jobs it is waiting for.

Helping has two costs:

- **Stack depth.** A job that waits runs another job on top of its own stack frame, which may wait and run another. Deep chains can overflow the stack. Keep waits rare inside jobs: prefer [dependencies](dependencies.md), which start follow-on work when a job finishes instead of waiting inside a job.
- **Latency.** While helping, the waiter may pick up a long unrelated job, and only notice its counter reached zero after that job is done. The main thread waiting for this frame's work can end up running next frame's streaming work. Let the main thread help only with jobs from its own group, or mark jobs with a priority and have waiters help only with high-priority ones.

[Fibers](fibers.md) remove both problems by switching away from the waiting job entirely, at the cost of a much more complex system.

## Rules for job code

- **Do not block.** No file I/O, no waiting on the GPU, no long-held locks. A blocked job blocks its worker.
- **Do not allocate from the general heap** in hot jobs. Use per-thread or per-frame allocators.
- **Make job data self-contained.** Copy what the job needs into its data, or point to data nobody writes while the job runs. See [data access rules](parallel-for.md#data-access-rules).
- **Keep jobs between about 10 microseconds and 1 millisecond.** Shorter jobs spend more time in scheduling than in work; longer ones leave other workers idle at the end of the frame.
