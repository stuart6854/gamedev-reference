# Roadmap

Topics that do not have a page yet. When a page is written, its topic is deleted from this list. Finished work is not ticked and not struck through.

Pages that already exist are not listed here.

## Planned

### Movement

- Dash
- Wall run
- Ledge climb
- Grappling hook
- Drag selection methods (RTS-style box/marquee selection: screen-space rectangle vs world-space frustum/volume selection, lasso selection, add/remove with modifier keys, click vs drag threshold, double-click to select all of a type, drawing the selection rectangle in UI)
- Formation movement (keeping a selected group's shape on a move order: line, box, and wedge slots, slot assignment, facing, and regrouping around obstacles)

### Cameras

- RTS camera (pan with keys and screen edges, zoom, rotate, bounds; pairs with drag selection)
- First-person camera (mouse look, pitch clamp, sensitivity, head bob)

### Combat

- Attack combos (melee combo chains, input buffering, animation-driven combo windows)
- Hit flash
- Damage numbers

### Architecture

- MonoBehaviour lifecycle (Awake, OnEnable, Start, and what each may assume about other components; script execution order; what belongs in Update, FixedUpdate, and LateUpdate)
- Bootstrapping and services (singletons, a service locator, a persistent systems scene)
- Command pattern (undo and redo, for building and editor-style tools)

### Game systems

- Gameplay abilities with cooldowns
- Timed buffs and debuffs (durations, stacking rules, and refresh on top of the existing stat modifiers)
- Loot tables (weighted random drops, rarity tiers, nested tables, guaranteed/pity drops)
- Enemy wave spawning
- Fog of war

### Presentation

- Shaders and materials
- Water shaders
- URP renderer features
- Post-processing

### Animation

- Ragdolls

### AI

- Utility AI
- Line of sight and hearing perception
- Steering behaviours

### Networking

- Networking concepts: authority models, tick rate, client-side prediction and reconciliation, entity interpolation, and lag compensation
- Unity Netcode for GameObjects

### Space and curves

- Bézier curves and splines (Unity Splines package)
- Spatial partitioning (grids, quadtrees)

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
