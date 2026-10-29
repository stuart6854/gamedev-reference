# Roadmap

Topics that do not have a page yet. When a page is written, its topic is deleted from this list. Finished work is not ticked and not struck through.

Pages that already exist are not listed here.

## Planned

### Maths

- Vectors, dot and cross products (facing tests, projection, signed angles, change of basis)
- Random distributions and shuffles (seeded generators, weighted picks, Fisher–Yates, shuffle bags, distributions other than uniform)
- Intersection tests (ray against sphere, box, plane, and triangle; box against box with the separating axis test)
- Frustum and visibility tests (is a point or bounds on screen, frustum planes, culling, and off-screen indicators)

### Data structures

- Spatial hash grid (uniform cells keyed by hashed coordinates, neighbour and radius queries, choosing a cell size, moving objects between cells)
- Quadtree and octree (subdividing by density, insert, remove, and query, loose bounds for moving objects, when a grid is better)

### Movement

- Dash
- Wall run
- Ledge climb
- Grappling hook
- Drag selection methods (RTS-style box/marquee selection: screen-space rectangle vs world-space frustum/volume selection, lasso selection, add/remove with modifier keys, click vs drag threshold, double-click to select all of a type, drawing the selection rectangle in UI; pairs with the [top-down strategy camera](unity/cameras/rts.md))
- Formation movement (keeping a selected group's shape on a move order: line, box, and wedge slots, slot assignment, facing, and regrouping around obstacles)

### Cameras

- Camera framing (keeping several subjects in view: a group or target bounding volume, zoom to fit, look-ahead, dead zones)

### Combat

- Lock-on targeting (target selection and cycling, breaking lock on distance or sight, strafing around the target, and the camera framing player and target)
- Attack combos (melee combo chains, input buffering, animation-driven combo windows)

### Architecture

- Command pattern (undo and redo, for building and editor-style tools)

### Game systems

- Gameplay abilities with cooldowns
- Timed buffs and debuffs (durations, stacking rules, and refresh on top of the existing stat modifiers)
- Loot tables (weighted random drops, rarity tiers, nested tables, guaranteed/pity drops)
- Enemy wave spawning
- Fog of war
- Grid tactics (movement range by flood fill, attack ranges, line of sight on a grid, and path cost)

### Presentation

- Shaders and materials
- Water shaders
- URP renderer features
- Post-processing

### Animation

- Ragdolls
- Procedural animation (IK legs that plant and step for spiders and mechs, body height and tilt from foot positions)

### AI

- Utility AI
- Line of sight and hearing perception
- Steering behaviours

### Networking

- Networking concepts: authority models, tick rate, client-side prediction and reconciliation, entity interpolation, and lag compensation
- Unity Netcode for GameObjects

### Space and curves

- Bézier curves and splines (Unity Splines package)
- Spline-based meshes (roads, fences, pipes, and rails extruded or instanced along a spline in the editor)
- Spatial partitioning (grids, quadtrees)
- Hex grids (axial and cube coordinates, neighbours, distance, rounding, and world conversion)

### Editor

- Custom inspectors
- Property drawers
- Other editor extensions

### Interface

- UI topics: UI Toolkit, drag and drop, and the surrounding UI

### World

- Noise for procedural generation
- Dungeon-like procedural generation (rooms and corridors, BSP, random walk / drunkard's walk, graph-based room layouts)
- Day and night cycle

## Ideas / maybe later

Not committed. These stay here until one of them is promoted into Planned, or written and then removed.

### Game systems

- Checkpoints and respawn
- Minimap

### Animation

- Animation Rigging foot IK and look-at
- Root motion

### AI

- Behaviour trees

### Narrative

- Dialogue trees
- Quests and objectives
- Timeline cutscenes

### World generation

- Wave function collapse
- Marching cubes

### Simulation

- Vehicles (`WheelCollider`)
- Buoyancy
- Verlet ropes and cloth

### Rendering

- Decals
- VFX Graph primer
- LOD
- Terrain basics

### Game flow

- Input rebinding UI
- Localisation
- Addressables
- Async scene loading and a loading screen
- Save and load (JSON)
- Audio manager

### Performance

- Profiler walkthrough
- Jobs and Burst
- GPU instancing
- ECS intro

### Tools

- Debug drawing
- In-game console
- Unity Test Framework

### Navigation

- A* pathfinding

### Game feel

- Screen shake
- Hit stop
- Knockback
