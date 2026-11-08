# World streaming

An open world is too big to load at once. **World streaming** divides it into cells, keeps the cells around the player loaded, loads new ones ahead of the player in the background, unloads ones left behind, and keeps the precision of floating-point positions usable far from the origin.

## Cells

```text
Cell {
    coord               // (x, z) on a grid; (x, y, z) for tall or underground worlds
    bounds
    state               // Unloaded, Loading, Loaded, Activating, Active, Deactivating
    package             // the archive or files holding the cell's content
    hlod                // a cheap stand-in for the cell when it is far away
}
```

- A **uniform grid** (for example 128 m cells) is simple to reason about, edit, and stream. A quadtree of cells adapts to uneven density but is harder to work with; most engines use grids.
- Different content needs different ranges: grass is only needed within 50 m, buildings within 500 m, mountains everywhere. Use **several grids** (layers) with different cell sizes and load distances, each holding the content that suits it.
- Content that must always exist (the player, quest-critical characters, global managers) lives in an **always-loaded** layer outside the grid.

Each cell's content is a separate file in the editor (good for version control; several people can edit different parts of the world), and is [cooked](content/import-cook.md) into its own package so it can be loaded on its own.

## Choosing what to load

```text
update_streaming(player):
    for cell in cells near player:
        d = distance from player to cell.bounds
        if cell.state is Unloaded and d < LOAD_RADIUS:     request load, priority by distance
        if cell.state is Active and d > UNLOAD_RADIUS:     request unload
```

- **Hysteresis**: unload at a larger radius than load (`UNLOAD_RADIUS = LOAD_RADIUS + margin`). Otherwise a player standing near the boundary loads and unloads the same cell over and over.
- **Look ahead**: a fast player (a vehicle, a fast-travel landing) needs cells where they are going, not where they are. Load around a point predicted from velocity (`position + velocity × lead_time`), as well as around the player.
- **Priority**: nearer first, and cells in the view direction before cells behind. A cell the player is about to enter beats one at the edge of the radius.
- **Several sources**: the camera, the player, and any other point that needs the world (a second player, a cinematic camera, an AI vehicle across the map) each request cells. A cell stays loaded while any source wants it.

## Loading and activating

Loading has two halves with different costs:

| Step | Where | Cost |
| --- | --- | --- |
| **Load** the cell's data: read, decompress, and create GPU resources | Background threads, I/O, and the [resource system](patterns/resources.md#asynchronous-loading) | Bandwidth and memory |
| **Activate** it: create entities, register physics bodies, navmesh tiles, and scripts | Main thread, at a safe point in the frame | CPU time on the main thread |

Activation is where streaming hitches usually come from: creating a thousand entities and their physics bodies in one frame takes far longer than a frame. Spread it out:

```text
activate_budget_ms = 2

each frame:
    while time spent < activate_budget_ms and cells are waiting:
        activate the next batch of entities from the highest-priority waiting cell
```

Deactivation and unloading are time-sliced the same way, and freeing GPU resources waits until the GPU is done with them (see [deferred deletion](rendering/frames-in-flight.md#deferred-deletion)).

If the player outruns streaming (a cell they are entering is not loaded yet), there are only bad options: show the empty world, stop the player, or block until it loads. Detect it, log it as a bug, and tune radii, look-ahead, and package layout so it does not happen.

## Distant cells: HLOD

Beyond the load radius, the world should still be visible: mountains, skylines, distant towns. **Hierarchical LOD** builds, for each cell (or group of cells), one simplified merged mesh with one material and one texture atlas, during the content build.

- Far cells show only their HLOD: one draw call instead of thousands.
- When a cell loads, its real content fades in and its HLOD fades out.
- Generate HLODs automatically (merge, simplify, bake textures), with manual overrides for landmarks that must look right from far away.

## Persistent changes

A cell that unloads and loads again comes back as authored, unless its changes were saved. Opened chests, broken walls, dropped items, and dead enemies must be remembered:

```text
on deactivate(cell):
    cell_delta[cell.coord] = changes since the cell was authored (by stable object id)

on activate(cell):
    create the authored content
    apply cell_delta[cell.coord]: remove destroyed objects, restore changed state, create dropped items
```

The per-cell deltas are part of the save game, keyed the same way as the [world state](../unity/systems/saving/world-state.md) page describes: stable ids for authored objects, and records for objects created at run time.

### Objects that move between cells

An enemy chasing the player across a cell boundary must not be unloaded with the cell it started in. Either assign moving objects to the cell they are currently in (moving their record when they cross), or put them in the always-loaded layer while they are active. Characters far from the player whose behaviour still matters (a caravan travelling between towns) can keep a cheap **off-screen simulation**: a position on a road and a timetable, turned back into a full character when their cell loads.

## Precision far from the origin

`float` positions have about seven significant digits. The farther from the origin, the larger the gap between representable positions:

| Distance from origin | Gap between float values |
| --- | --- |
| 1 km | 0.06 mm |
| 10 km | 1 mm |
| 100 km | 8 mm |
| 1,000 km | 6 cm |

At around 10 km, millimetre gaps already show as jittering vertices on skinned characters, shaky first-person weapons, and z-fighting; physics becomes unstable before the visuals do. Two fixes are used:

### Origin rebasing

When the player moves more than a threshold (for example 2 km) from the origin, shift the whole world so the player is near the origin again:

```text
if length(player.position) > REBASE_DISTANCE:
    offset = snap(player.position, CELL_SIZE)      // whole cells, so the grid stays aligned
    for every loaded object: position -= offset
    physics broadphase, particles, audio emitters, navmesh: apply the offset
    world_origin += offset                          // a double, so true positions are still known
```

Everything near the player is always near the origin, where floats are precise. The cost is finding everything that stores a position: a missed system (a particle system, a cached path) ends up kilometres away after a rebase. Do it at a quiet moment, and broadcast it as an event every system handles.

### Double-precision positions

Store world positions as `double` (precise to well under a millimetre at millions of kilometres), and convert to `float` **relative to the camera** for rendering:

```text
render_position = float(world_position - camera_world_position)   // computed in double, then converted
```

The GPU only ever sees small, camera-relative values. Unreal Engine 5 takes this approach ("Large World Coordinates"). It touches every system that stores positions, and physics engines may still need their own origin shifting, but there is no global rebase event to miss.

## In the editor

Streaming applies to the editor too: a whole open world does not fit in an editor session either. Editors load cells around the editor camera, and let designers load specific regions explicitly. One file per cell (or per object, as Unreal's "one file per actor" does) lets several people edit the same world in version control without conflicts.
