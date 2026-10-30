# Browse by use

Pages grouped by what they are useful for. Each page lists its uses under its title; this page is generated from those lists by `scripts/gen_uses.py`.

- [Top-down survival](#top-down-survival) (2)
- [Hordes and crowds](#hordes-and-crowds) (4)
- [Stealth](#stealth) (3)
- [Shooters](#shooters) (3)
- [Strategy and tactics](#strategy-and-tactics) (4)
- [RPGs](#rpgs) (2)
- [Roguelikes](#roguelikes) (1)
- [Life and colony sims](#life-and-colony-sims) (2)
- [Open worlds](#open-worlds) (2)
- [Wildlife](#wildlife) (4)
- [Companions and NPCs](#companions-and-npcs) (2)
- [Multiplayer](#multiplayer) (1)

## Top-down survival

Scavenging, threats in the dark, and buildings to hide in, seen from above.

- [Fog of war and vision](unity/rendering/vision.md) — Only what the character can see is lit; rooms behind walls go dark, and zombies there are hidden.
- [Roof and wall cutaways](unity/rendering/cutaways.md) — Walking into a house hides its roof and upper floor, and the room stays dark with the roof's shadow.

## Hordes and crowds

Many agents at once: zombies, swarms, armies, and pedestrians.

- [Horde simulation](unity/ai/horde.md) — Thousands of zombies across the map, with full AI only for the few near the player.
- [Perception](unity/ai/perception.md) — A gunshot pulls every zombie within its radius towards where it was fired.
- [Spatial hash grid](data-structures/spatial-hash.md) — Each agent finds its neighbours for separation and flocking without testing every other agent.
- [Steering and crowds](unity/ai/steering.md) — Hundreds of agents head for one goal without stacking, and swarmers pursue where the player is going.

## Stealth

Being seen, being heard, and staying out of sight.

- [Fog of war and vision](unity/rendering/vision.md) — The player sees the guards' view cones and knows what is out of sight.
- [Perception](unity/ai/perception.md) — Guards fill an awareness meter faster when the player is close, lit, or standing up.
- [Spatial hash grid](data-structures/spatial-hash.md) — A noise or a sight check only looks at the agents in the cells around it.

## Shooters

Guns, projectiles, aiming, and the enemies that shoot back.

- [Perception](unity/ai/perception.md) — Turrets and cameras with a narrow cone, a long range, and no hearing.
- [Spatial hash grid](data-structures/spatial-hash.md) — Thousands of bullets test against the few targets in their cell.
- [Utility AI](unity/ai/utility.md) — Attack, take cover, reload, or retreat, scored by health, ammo, and distance.

## Strategy and tactics

RTS, 4X, and tactics games: selecting, commanding, and seeing the map.

- [Fog of war and vision](unity/rendering/vision.md) — Unexplored map is black, explored map is grey, and enemy units show only inside vision.
- [Horde simulation](unity/ai/horde.md) — Off-screen battles resolve cheaply while on-screen ones get full detail.
- [Roof and wall cutaways](unity/rendering/cutaways.md) — A see-through circle around the selected unit shows it behind cover.
- [Steering and crowds](unity/ai/steering.md) — A selected group spreads out at the destination instead of fighting over one point.

## RPGs

Stats, items, loot, and characters that grow.

- [Roof and wall cutaways](unity/rendering/cutaways.md) — In isometric RPGs, walls between the camera and the party dissolve, so the party is never hidden.
- [Spatial hash grid](data-structures/spatial-hash.md) — An explosion or a spell finds everything within its radius.

## Roguelikes

Runs, grids, randomness, and remembered maps.

- [Fog of war and vision](unity/rendering/vision.md) — Grid field of view, with remembered tiles drawn dimmed.

## Life and colony sims

Needs, schedules, and building a place to live.

- [Roof and wall cutaways](unity/rendering/cutaways.md) — Upper floors hide while the player works on the floor below.
- [Utility AI](unity/ai/utility.md) — Many needs compete smoothly, without a hand-written rule for every combination.

## Open worlds

Large maps, streaming, and a world that runs while you are away.

- [Horde simulation](unity/ai/horde.md) — Pedestrians and cars exist down every street, but only nearby ones are real.
- [Steering and crowds](unity/ai/steering.md) — Pedestrians follow a flow field through streets and avoid each other.

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

- [Spatial hash grid](data-structures/spatial-hash.md) — The server sends each client only the entities in the cells near it.
