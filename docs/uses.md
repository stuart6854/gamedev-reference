# Browse by use

Pages grouped by what they are useful for. Each page lists its uses under its title; this page is generated from those lists by `scripts/gen_uses.py`.

- [Top-down survival](#top-down-survival) (26)
- [Hordes and crowds](#hordes-and-crowds) (16)
- [Stealth](#stealth) (6)
- [Shooters](#shooters) (26)
- [Melee action](#melee-action) (6)
- [Strategy and tactics](#strategy-and-tactics) (13)
- [RPGs](#rpgs) (24)
- [Roguelikes](#roguelikes) (5)
- [Platformers](#platformers) (7)
- [Life and colony sims](#life-and-colony-sims) (8)
- [Base building](#base-building) (4)
- [Open worlds](#open-worlds) (12)
- [Wildlife](#wildlife) (4)
- [Companions and NPCs](#companions-and-npcs) (2)
- [Multiplayer](#multiplayer) (5)

## Top-down survival

Scavenging, threats in the dark, and buildings to hide in, seen from above.

- [Building and placement](unity/systems/building.md) — Barricades and walls built from scavenged materials.
- [Character movement](unity/mechanics/character-movement.md) — Reliable walking over stairs and slopes for a character on foot.
- [Continuous spawning](unity/ai/spawning.md) — A director that builds tension, peaks, and gives the player a breather.
- [Day and night cycle](unity/rendering/day-night.md) — Nights that are dangerous and lamps that switch on at dusk.
- [Enemy behaviour](unity/ai/enemy.md) — A simple threat to build on before adding perception.
- [Equipment](unity/systems/inventory/equipment.md) — Wearing armour and holding a weapon in each hand.
- [Fog of war and vision](unity/rendering/vision.md) — Only what the character can see is lit; rooms behind walls go dark, and zombies there are hidden.
- [Frustum and visibility tests](maths/frustum.md) — Spawning only outside the view, and checking line of sight, not just the cone.
- [Grid inventory](unity/systems/inventory/grid.md) — A backpack where an item's shape is a decision.
- [Health, damage, and stats](unity/systems/health.md) — Health, healing, and invulnerability after a hit.
- [Highlight and outline](unity/rendering/highlight-outline.md) — Outlining the container or door the player can use.
- [Interaction](unity/mechanics/interaction.md) — Opening doors and holding to search or pick up items.
- [List inventory](unity/systems/inventory/list.md) — Scavenged items stacked by type.
- [Loot tables](unity/systems/loot.md) — Containers and enemies that drop what the area should have.
- [MonoBehaviour lifecycle](unity/architecture/lifecycle.md) — Systems that read each other at startup without null references.
- [Post-processing with volumes](unity/rendering/post-processing.md) — A low-health look and grading that changes with the mood.
- [Roof and wall cutaways](unity/rendering/cutaways.md) — Walking into a house hides its roof and upper floor, and the room stays dark with the roof's shadow.
- [Save system](unity/systems/saving/save-system.md) — Autosave on a timer, blocked while in combat or dead.
- [Scenes and loading](unity/architecture/scenes.md) — Moving between town and interiors behind a loading screen.
- [Slots and hotbar](unity/systems/inventory/slots.md) — Quick slots for consumables and tools.
- [Top-down movement](unity/mechanics/top-down.md) — Moving one way while aiming another, with mouse or twin-stick aim.
- [Vectors, dot and cross products](maths/vectors.md) — The 2D perp dot says whether a threat is to the left or right of the player.
- [Versioning saves](unity/systems/saving/versioning.md) — Early-access updates that change items and the map under existing worlds.
- [Weapons](unity/combat/weapons.md) — Scarce ammo and reloads that matter.
- [Weight inventory](unity/systems/inventory/weight.md) — Carry weight that slows the player when overloaded.
- [World state](unity/systems/saving/world-state.md) — Looted containers stay empty, broken doors stay broken, and dropped items stay where they fell.

## Hordes and crowds

Many agents at once: zombies, swarms, armies, and pedestrians.

- [Archetype storage](engine/ecs/archetype-storage.md) — Systems that read position and velocity of every agent in tight loops.
- [Continuous spawning](unity/ai/spawning.md) — A trickle that rises over time, as in survivor-likes.
- [Damage numbers](unity/combat/damage-numbers.md) — Pooled popups that merge rapid hits on many enemies.
- [Enemy waves](unity/ai/waves.md) — Waves bought from a budget that grows each round.
- [Entities](engine/ecs/entities.md) — Creating and destroying thousands of agents without fragmentation.
- [Formation movement](unity/mechanics/formations.md) — Keeping a squad's shape as it marches.
- [Free list and slab pool](data-structures/free-list.md) — Storage for many same-sized agents that spawn and die constantly.
- [Frustum and visibility tests](maths/frustum.md) — Skipping work for agents the camera cannot see.
- [Handle table](data-structures/handle-table.md) — Ids for spawned agents that detect when the agent behind them died.
- [Horde simulation](unity/ai/horde.md) — Thousands of zombies across the map, with full AI only for the few near the player.
- [Object pooling](unity/architecture/pooling.md) — Enemies and their effects recycled during waves.
- [Perception](unity/ai/perception.md) — A gunshot pulls every zombie within its radius towards where it was fired.
- [Sparse set](data-structures/sparse-set.md) — Component storage for thousands of entities with packed iteration.
- [Sparse-set storage](engine/ecs/sparse-set-storage.md) — Status effects and tags that come and go every few frames.
- [Spatial hash grid](data-structures/spatial-hash.md) — Each agent finds its neighbours for separation and flocking without testing every other agent.
- [Steering and crowds](unity/ai/steering.md) — Hundreds of agents head for one goal without stacking, and swarmers pursue where the player is going.

## Stealth

Being seen, being heard, and staying out of sight.

- [Enemy behaviour](unity/ai/enemy.md) — Patrols and searches at the last seen position.
- [First-person camera](unity/cameras/first-person.md) — First-person exploration with a body that turns with the view.
- [Fog of war and vision](unity/rendering/vision.md) — The player sees the guards' view cones and knows what is out of sight.
- [Perception](unity/ai/perception.md) — Guards fill an awareness meter faster when the player is close, lit, or standing up.
- [Spatial hash grid](data-structures/spatial-hash.md) — A noise or a sight check only looks at the agents in the cells around it.
- [Vectors, dot and cross products](maths/vectors.md) — A dot product against a view direction is the cone test behind every guard's sight.

## Shooters

Guns, projectiles, aiming, and the enemies that shoot back.

- [Coordinate spaces](graphics/coordinate-spaces.md) — From a world point to the screen and back, for crosshairs and hit markers.
- [Enemy behaviour](unity/ai/enemy.md) — Enemies that patrol, chase, attack, and flee when hurt.
- [Enemy waves](unity/ai/waves.md) — Arena and tower-defence rounds with a clear break between them.
- [Event systems](unity/architecture/events.md) — HUD counters that update when ammo changes, without polling.
- [First-person camera](unity/cameras/first-person.md) — Mouse and stick look with a pitch clamp and head bob.
- [Fixed timestep and the accumulator](physics/fixed-timestep.md) — Smooth interpolated motion for physics-driven projectiles and bodies.
- [Free list and slab pool](data-structures/free-list.md) — Fixed-size blocks for bullets and impacts with no allocation in play.
- [Health, damage, and stats](unity/systems/health.md) — Headshot multipliers through hurtboxes.
- [Hit flash](unity/combat/hit-flash.md) — Feedback that a shot connected.
- [Integrators](physics/integrators.md) — Projectile arcs that land where the maths says.
- [Interpolation and easing](maths/interpolation.md) — Recoil and camera smoothing that feel the same at 30 and 144 fps.
- [Intersection tests](maths/intersections.md) — Hitscan against boxes and spheres without colliders, and bullet impacts on triangles.
- [Object pooling](unity/architecture/pooling.md) — Bullets, impacts, and muzzle flashes reused instead of instantiated.
- [Perception](unity/ai/perception.md) — Turrets and cameras with a narrow cone, a long range, and no hearing.
- [Post-processing with volumes](unity/rendering/post-processing.md) — A red vignette that pulses on damage.
- [Quaternions and rotations](maths/quaternions.md) — Turrets and characters that turn towards a target at a fixed rate.
- [Random distributions and shuffles](maths/random.md) — Weapon spread that clusters at the centre, from a triangular distribution.
- [Rigidbody movement](unity/mechanics/rigidbody-movement.md) — A body that takes knockback and explosion impulses.
- [Ring buffer](data-structures/ring-buffer.md) — A rolling frame-time or recoil history with a moving average.
- [Slots and hotbar](unity/systems/inventory/slots.md) — A hotbar that selects weapons with number keys.
- [Spatial hash grid](data-structures/spatial-hash.md) — Thousands of bullets test against the few targets in their cell.
- [State machines](unity/architecture/state-machines.md) — Enemy states that switch on clear rules.
- [Top-down movement](unity/mechanics/top-down.md) — Twin-stick shooters and isometric aiming.
- [Utility AI](unity/ai/utility.md) — Attack, take cover, reload, or retreat, scored by health, ammo, and distance.
- [Vectors, dot and cross products](maths/vectors.md) — Projecting onto a plane and reflecting give ricochets and slope-aligned aiming.
- [Weapons](unity/combat/weapons.md) — Hitscan and projectile guns with fire modes, spread, recoil, and reloads.

## Melee action

Swings, combos, hit feedback, and close-range fights.

- [Attack combos](unity/combat/combos.md) — Light and heavy chains with hit windows and an input buffer.
- [Hit flash](unity/combat/hit-flash.md) — A flash on every landed hit, so blows read clearly.
- [Quaternions and rotations](maths/quaternions.md) — Aligning to a slope while keeping a facing, and twist limits for bones.
- [Ring buffer](data-structures/ring-buffer.md) — Input history for fighting-game motions and jump buffering.
- [State machines](unity/architecture/state-machines.md) — Locomotion and attacks kept in separate machines.
- [Third-person orbit camera](unity/cameras/third-person.md) — A camera that keeps the character framed while fighting.

## Strategy and tactics

RTS, 4X, and tactics games: selecting, commanding, and seeing the map.

- [Coordinate spaces](graphics/coordinate-spaces.md) — Turning a mouse position into a world ray for selection and orders.
- [Drag selection](unity/mechanics/selection.md) — Box, click, and double-click selection of units.
- [Fog of war and vision](unity/rendering/vision.md) — Unexplored map is black, explored map is grey, and enemy units show only inside vision.
- [Formation movement](unity/mechanics/formations.md) — Groups that move in a line, box, or wedge and face the way the player chose.
- [Frustum and visibility tests](maths/frustum.md) — Off-screen indicators pointing at units and objectives.
- [Horde simulation](unity/ai/horde.md) — Off-screen battles resolve cheaply while on-screen ones get full detail.
- [Intersection tests](maths/intersections.md) — Clicking the ground plane under the cursor, and picking units by their bounds.
- [Quaternions and rotations](maths/quaternions.md) — Units that rotate to face a move order without snapping.
- [Roof and wall cutaways](unity/rendering/cutaways.md) — A see-through circle around the selected unit shows it behind cover.
- [Shared variables](unity/architecture/variables.md) — Live counts of units or enemies from a runtime set.
- [Steering and crowds](unity/ai/steering.md) — A selected group spreads out at the destination instead of fighting over one point.
- [Top-down strategy camera](unity/cameras/rts.md) — Edge pan, drag pan, rotation, and zoom to the cursor.
- [uGUI and UI Toolkit](unity/ui/choosing.md) — Lots of screens that must work at many resolutions.

## RPGs

Stats, items, loot, and characters that grow.

- [Attack combos](unity/combat/combos.md) — Weapon combos with damage types and hurtboxes.
- [Bootstrapping and services](unity/architecture/services.md) — Game-wide systems such as quests and inventories reachable from any scene.
- [Character movement](unity/mechanics/character-movement.md) — Third-person movement relative to the camera.
- [Damage numbers](unity/combat/damage-numbers.md) — Floating numbers coloured by damage type.
- [Equipment](unity/systems/inventory/equipment.md) — Gear slots whose stats apply while equipped.
- [Event systems](unity/architecture/events.md) — Quests, achievements, and UI reacting to deaths and pickups.
- [Grid inventory](unity/systems/inventory/grid.md) — Tetris-style loot screens.
- [Handle table](data-structures/handle-table.md) — Safe references from a quest or a target slot to an object that may be destroyed.
- [Health, damage, and stats](unity/systems/health.md) — Stats with modifiers, damage types, and resistances per limb.
- [Highlight and outline](unity/rendering/highlight-outline.md) — Highlighting interactable objects and selected characters.
- [Interaction](unity/mechanics/interaction.md) — Talking, looting, and using objects with prompts.
- [List inventory](unity/systems/inventory/list.md) — A sortable bag for crafting materials and loot.
- [Loot tables](unity/systems/loot.md) — Rarity tiers, guaranteed drops, and pity for rare items.
- [MonoBehaviour lifecycle](unity/architecture/lifecycle.md) — Spawned characters that get their data before they enable.
- [Random distributions and shuffles](maths/random.md) — Weighted loot, fair crit chances with pseudo-random distribution, and bell-curve stats.
- [Roof and wall cutaways](unity/rendering/cutaways.md) — In isometric RPGs, walls between the camera and the party dissolve, so the party is never hidden.
- [Save system](unity/systems/saving/save-system.md) — Several manual slots plus an autosave, each with a date and play time.
- [Scenes and loading](unity/architecture/scenes.md) — Areas that load additively, with the UI kept in one place.
- [Shared variables](unity/architecture/variables.md) — HUD bars and counters that read shared values without referencing the player.
- [Spatial hash grid](data-structures/spatial-hash.md) — An explosion or a spell finds everything within its radius.
- [Third-person orbit camera](unity/cameras/third-person.md) — An orbit camera that pulls in when walls get in the way.
- [uGUI and UI Toolkit](unity/ui/choosing.md) — Menus, inventories, and HUDs kept separate from game state.
- [Versioning saves](unity/systems/saving/versioning.md) — Long games where players keep saves across many patches.
- [Weight inventory](unity/systems/inventory/weight.md) — Encumbrance on top of an ordinary bag.

## Roguelikes

Runs, grids, randomness, and remembered maps.

- [Fog of war and vision](unity/rendering/vision.md) — Grid field of view, with remembered tiles drawn dimmed.
- [Loot tables](unity/systems/loot.md) — Seeded drops that replay with the run.
- [Random distributions and shuffles](maths/random.md) — Seeded runs that replay exactly, shuffle bags, and points spread over a map.
- [Sparse set](data-structures/sparse-set.md) — Fast sets of entity ids with constant-time add, remove, and clear.
- [Sparse-set storage](engine/ecs/sparse-set-storage.md) — Many entity types with unusual component combinations.

## Platformers

Jumps, slopes, and precise movement.

- [2D platformer](unity/mechanics/platformer-2d.md) — Variable jumps, slopes, and wall slides on a 2D body.
- [Character movement](unity/mechanics/character-movement.md) — Coyote time and jump buffering on a kinematic capsule.
- [Fixed timestep and the accumulator](physics/fixed-timestep.md) — Jumps that reach the same height at every frame rate.
- [Integrators](physics/integrators.md) — Choosing the integrator that keeps jump arcs exact.
- [Interpolation and easing](maths/interpolation.md) — Easing curves for jumps, landings, and UI that is not linear.
- [Rigidbody movement](unity/mechanics/rigidbody-movement.md) — Physics-driven movement that pushes props around.
- [State machines](unity/architecture/state-machines.md) — Idle, run, jump, and fall with a pause that resumes mid-jump.

## Life and colony sims

Needs, schedules, and building a place to live.

- [Building and placement](unity/systems/building.md) — Placing furniture and rooms.
- [Day and night cycle](unity/rendering/day-night.md) — Schedules tied to the time of day.
- [Drag selection](unity/mechanics/selection.md) — Selecting several colonists to give one order.
- [Entities](engine/ecs/entities.md) — Many small simulated things with ids that survive saves.
- [Interaction](unity/mechanics/interaction.md) — Interacting with furniture and objects around a home.
- [Roof and wall cutaways](unity/rendering/cutaways.md) — Upper floors hide while the player works on the floor below.
- [Top-down strategy camera](unity/cameras/rts.md) — A camera for watching and managing a settlement.
- [Utility AI](unity/ai/utility.md) — Many needs compete smoothly, without a hand-written rule for every combination.

## Base building

Placing, upgrading, and defending structures.

- [Building and placement](unity/systems/building.md) — Grid and free placement, sockets, and a cost paid from the inventory.
- [Intersection tests](maths/intersections.md) — Overlap tests for whether a placed piece fits.
- [Top-down strategy camera](unity/cameras/rts.md) — A top-down view for placing and managing structures.
- [World state](unity/systems/saving/world-state.md) — Placed pieces are spawned objects, saved with their prefab key and position.

## Open worlds

Large maps, streaming, and a world that runs while you are away.

- [Archetype storage](engine/ecs/archetype-storage.md) — Large simulations where most entities keep the same components.
- [Bootstrapping and services](unity/architecture/services.md) — Audio, saving, and settings that exist in every scene.
- [Continuous spawning](unity/ai/spawning.md) — Zones that wake enemies as the player approaches.
- [Day and night cycle](unity/rendering/day-night.md) — A clock that drives the sun, the sky, and the ambient light.
- [Horde simulation](unity/ai/horde.md) — Pedestrians and cars exist down every street, but only nearby ones are real.
- [Integrators](physics/integrators.md) — Vehicles and ropes that stay stable over long sessions.
- [Interpolation and easing](maths/interpolation.md) — Day and night colours, fades, and remapped values from one lerp.
- [Post-processing with volumes](unity/rendering/post-processing.md) — Local volumes for caves, underwater, and interiors.
- [Save system](unity/systems/saving/save-system.md) — One save that names the level to load, then puts the player back.
- [Scenes and loading](unity/architecture/scenes.md) — A persistent core with levels and chunks loaded on top.
- [Steering and crowds](unity/ai/steering.md) — Pedestrians follow a flow field through streets and avoid each other.
- [World state](unity/systems/saving/world-state.md) — Chunks that unload keep their state in memory, then in the save.

## Wildlife

Animals, flocks, and herds.

- [Horde simulation](unity/ai/horde.md) — Herds graze and migrate across a large map without a GameObject each.
- [Perception](unity/ai/perception.md) — Animals hear footsteps and flee before the player is in sight.
- [Steering and crowds](unity/ai/steering.md) — Birds, fish, and bats from separation, alignment, and cohesion.
- [Utility AI](unity/ai/utility.md) — Graze, drink, rest, or flee, with a little randomness so a herd does not move in lockstep.

## Companions and NPCs

Allies and characters with needs and opinions.

- [Perception](unity/ai/perception.md) — Allies notice threats the player has not seen, and call them out.
- [Utility AI](unity/ai/utility.md) — Survivors eat, sleep, scavenge, guard, or flee, chosen by hunger, fatigue, threat, and time of day.

## Multiplayer

Several players, one world.

- [Entities](engine/ecs/entities.md) — Command buffers that apply changes at a known point in the frame.
- [Fixed timestep and the accumulator](physics/fixed-timestep.md) — Deterministic steps that clients and server can agree on.
- [Handle table](data-structures/handle-table.md) — Small, copyable ids that can be sent over the network.
- [Ring buffer](data-structures/ring-buffer.md) — Snapshot buffers for interpolating other players' positions.
- [Spatial hash grid](data-structures/spatial-hash.md) — The server sends each client only the entities in the cells near it.
