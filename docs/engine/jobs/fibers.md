# Fibers

A **fiber** is a stack and a saved set of registers that a thread can switch to and from, without involving the OS scheduler. In a fiber-based job system, every job runs on a fiber. When a job waits for a counter, its fiber is set aside and the worker switches to another fiber, so the job resumes later exactly where it stopped, possibly on a different worker.

Naughty Dog described this design in "Parallelizing the Naughty Dog Engine Using Fibers" (Christian Gyrling, GDC 2015), used for The Last of Us Remastered on PlayStation 4.

## Why

With the [helping](scheduler.md#waiting-by-helping) approach, a job that waits runs other jobs on top of its own stack. That has two problems: deep recursion, and the waiting job cannot resume until whatever it picked up has finished. Fibers solve both:

- Waiting costs a context switch, a few dozen instructions, and nothing runs on top of the waiting job's stack.
- The waiting job resumes as soon as its counter reaches zero, on whichever worker is free.
- Job code can wait anywhere, in the middle of a function, as ordinary sequential code. Without fibers, the code after a wait has to be split into a separate dependent job.

## The structure

```text
workers:      one thread per core, pinned, each running on a fiber
fiber pool:   e.g. 128 fibers with 64 KB stacks and 32 with 512 KB stacks
job queues:   by priority
wait list:    fibers waiting on a counter, with the value each one waits for

worker_loop():
    while running:
        if a waiting fiber's counter has reached its target:
            switch to that fiber                      // resume the waiting job
        else if job = next job:
            fiber = take a free fiber from the pool
            switch to fiber, running job               // the fiber returns to the pool when the job ends

wait(counter, target):
    if counter.load(acquire) <= target: return
    add (current fiber, counter, target) to the wait list
    switch to a free fiber running worker_loop          // this worker carries on with other work
    // execution continues here, on some worker, once the counter has reached target
```

The worker's own loop runs on a fiber too, so a worker always has something to switch to.

## Switching fibers

- **Windows** has fibers built in: `ConvertThreadToFiber`, `CreateFiber`, and `SwitchToFiber`.
- **POSIX** has `makecontext` and `swapcontext`, but they save and restore the signal mask with a system call on every switch, which makes them slow. Engines use a small hand-written assembly routine that saves the callee-saved registers and the stack pointer, and loads another set. Boost.Context provides tested versions for each platform and calling convention.

A switch saves only what the calling convention says must be preserved across a call, because the switch is itself a function call.

## Problems

### Thread-local storage

A fiber that waits on worker 2 can resume on worker 5. Anything the job read from thread-local storage before the wait is now the wrong thread's. Worse, the compiler may have cached the address of a thread-local variable in a register across the wait, so the code keeps using worker 2's variable after resuming on worker 5.

- Avoid `thread_local` in job code, or re-read it after every wait through a function the compiler cannot inline.
- MSVC's `/GT` option makes thread-local access fiber-safe, by not caching thread-local addresses.
- Per-thread allocators and per-thread output buffers must be looked up again after each wait.

### Locks

An OS mutex belongs to the thread that locked it. A job that locks a mutex, waits, and resumes on another worker then unlocks it from a different thread, which is undefined behaviour, and while it waits the mutex blocks every other job that needs it.

Never hold an OS mutex across a wait. Use spin locks for short critical sections, or locks that are aware of the job system, which put the waiting fiber on the wait list instead of blocking the thread.

### Resuming too early

Between a fiber adding itself to the wait list and finishing the switch away, the counter can reach its target, and another worker can try to resume the same fiber while it is still running. The fiber must be marked as "switching out" and only become resumable once the switch has completed, for example by having the next fiber publish it as resumable as its first action after the switch.

### Stacks

Each fiber has a fixed stack, and stack overflows in fibers corrupt neighbouring memory instead of crashing cleanly. Use guard pages (an inaccessible page below each stack) in development builds, keep a few fibers with large stacks for jobs known to need them, and avoid large arrays on the stack in job code.

### Tools

Debuggers show each thread's current fiber, not the waiting fibers, so the call stack of a job that is waiting cannot be seen without engine-specific debugger extensions. Profilers that sample stacks may misattribute time across switches. Instrumented profilers such as Tracy have explicit fiber support, which has to be wired into the switch function.

## When to use fibers

Fibers pay off in a large engine with deep chains of work that would otherwise need many small dependent jobs, on platforms the team controls, with time to build the tooling. For most engines, counters, [dependencies](dependencies.md), and limited helping are simpler, debuggable with normal tools, and fast enough. Start there, and move to fibers only when waits inside jobs become the main problem.
