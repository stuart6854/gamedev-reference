# Dependencies and job graphs

Most work comes in stages: animation must finish before IK, and physics before the camera reads the player's position. Instead of a job waiting inside itself for earlier jobs, give each job its **dependencies**, and let the scheduler start it when they are all done. Built up for every system in a frame, those dependencies form a **job graph**.

## Job handles with dependencies

```text
JobNode {
    job
    pending             // atomic: dependencies not yet finished
    continuations[]     // nodes waiting on this one
    done                // atomic bool
    lock                // protects continuations
}

schedule(job, depends_on = []) -> JobNode:
    node = JobNode { job, pending = 1 }            // 1 extra, so it cannot start while we add dependencies
    for dep in depends_on:
        lock dep
        if not dep.done:
            dep.continuations.append(node)
            node.pending += 1
        unlock dep
    release(node)                                   // drop the extra 1
    return node

release(node):
    if node.pending.fetch_sub(1, acq_rel) == 1:     // this was the last one
        submit(run_node(node))

run_node(node):
    node.job.function(node.job.data)
    lock node
    node.done = true
    waiting = node.continuations
    unlock node
    for c in waiting: release(c)
```

- The extra count of 1 during `schedule` stops the job starting before all of its dependencies have been added: without it, the first dependency could finish and start the job while the second is still being registered.
- Checking `done` and appending to `continuations` happen under the same lock as setting `done`. Otherwise a dependency could finish between the check and the append, and the new node would never be released.
- A job with no dependencies is submitted straight away by the final `release`.
- Waiting for the whole frame is waiting on a final node that depends on everything else.

`when_all(nodes)` is a node with no work and those dependencies: one handle that completes when all of them have. Unity's `JobHandle.CombineDependencies` is the same idea.

## Building the frame's graph

Systems declare what they access, instead of listing other systems:

```text
register(system, phase, reads = [Transform, Velocity], writes = [Position])
```

Two systems **conflict** when one writes something the other reads or writes. Conflicting systems run in their registered order; everything else may run at the same time. Build the edges in one pass over the systems in order:

```text
for each resource r:
    last_writer[r] = none
    readers_since_write[r] = []

for s in systems, in phase and registration order:
    deps = []
    for r in s.reads:
        if last_writer[r]: deps.append(last_writer[r])
    for r in s.writes:
        if last_writer[r]: deps.append(last_writer[r])
        deps += readers_since_write[r]          // readers must finish before s overwrites
    s.node = schedule(s.job, unique(deps))

    for r in s.reads: readers_since_write[r].append(s.node)
    for r in s.writes:
        last_writer[r] = s.node
        readers_since_write[r] = []
```

- **Read after write**: a reader depends on the last writer.
- **Write after read**: a writer depends on every reader since the last write, so it does not change data they are still reading.
- **Write after write**: a writer depends on the previous writer, keeping their order.
- Systems that only read the same data get no edges between them, and run in parallel.

Resources are component types, singletons (the physics world, the navmesh), and anything else systems share. Coarse resources ("all transforms") are simple but serialise more than necessary; finer ones ("transforms of the player") are faster and easier to get wrong.

The graph's shape rarely changes between frames, so build it once and rebuild only when systems are added or removed. Each frame then only resets the counters and submits the root nodes.

## Sync points

Some work cannot run on a worker:

- Calls into APIs that must be on one thread: rendering submission on some APIs, platform window and input calls.
- Structural changes to shared containers: creating and destroying entities, applying [deferred commands](../patterns/frame.md#deferred-commands).

Mark such systems as main-thread. The graph treats each one as depending on every earlier system that touches the same resources, and the main thread runs it when its dependencies are done, helping with other jobs while it waits. Each main-thread system in the middle of a frame is a point where parallel work drains, so group them, ideally at the end of a phase.

## Checking the declarations

A system that writes something it did not declare is a data race the graph cannot see. It shows up as a rare, unreproducible bug. Catch it in debug builds:

- Give access to data only through the declared resources (`ctx.write<Position>()`), and have the accessor check the declaration.
- Track, per resource, which job currently holds read or write access, and assert when another job's access conflicts. Unity's job safety system does this for `NativeContainer`s.
- Run the graph with one worker, in a random valid order each frame. A result that changes with the order points at a missing dependency.

## Seeing the graph

Draw the graph (systems as boxes, dependencies as arrows) from the same data the scheduler uses, and show each job's start and end times in a timeline profiler such as Tracy or Superluminal. The critical path (the longest chain of dependencies) decides the frame time. Shortening anything off that path does not help.
