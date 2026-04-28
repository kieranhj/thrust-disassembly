# Ideas / Future Work

Working title: **Thrust Next** — essentially Thrust meets Exile.

---

## Index

Open work items, one line each. Full details in the sections below; completed work in [Completed](#completed) at the bottom.

### Enemies, weapons & hazards
- [New enemy bullet types](#new-enemy-bullet-types) — heavy / explosive / laser / rocket / guided / EMP variants on the existing particle system
- [Mini power nodes](#mini-power-nodes) — shootable destructibles that punch authored holes in terrain
- [Landing bubbles](#landing-bubbles) — soft capture points that hold the ship and recharge it
- [Fans / turbines](#fans--turbines) — directional force emitters over rectangular regions
- [Rotating gun emplacements](#rotating-gun-emplacements) — per-frame angle sweep, fires when aim crosses player
- [Bobbing mines](#bobbing-mines) — passive sine-wave hazards with destroy-on-contact
- [Hot areas](#hot-areas) — heat accumulation degrades flight; offset by a heatsink upgrade
- [Water as a general element](#water-as-a-general-element) — submerged regions with modified physics

### Gravity wells — open follow-ups
- [Well sprite](#gravity-well-follow-ups) — replace the type $0D early-exit with a real non-lethal sprite
- [Centre-case symmetry fix](#gravity-well-follow-ups) — handle `dx == dy == 0` cleanly
- [Per-axis half-scaling](#gravity-well-follow-ups) — drop pull/2 at 45° so corner pull isn't √2 stronger
- [Apply pull to thrust particles](#gravity-well-follow-ups) — ship's exhaust bends through the field as a cue

### Gravity field variants
- [Gravity flipper / null / paired / bullet-affecting fields](#gravity-field-objects-other-variants) — siblings of the implemented well

### Timed lasers — open follow-ups
- [Beam telegraph](#timed-lasers-follow-ups) — visual warning before the on-phase
- [Optimised line draw](#timed-lasers-follow-ups) — Bresenham erase + redraw per laser per frame is generic
- [Shield interaction](#timed-lasers-follow-ups) — beam currently kills through shield; investigate
- [Shootable behaviour toggles](#timed-lasers-follow-ups) — switch retargets a laser's `gun_aim` (see switch system)
- [Rotating lasers](#timed-lasers-follow-ups) — per-frame `(dx, dy)` sweep; depends on faster line draw

### Engine / editor
- [Custom directional line drawing routine](#custom-directional-line-drawing-routine) — walk-until-hit; renderer + collision query in one
- [Configurable switches and triggers](#configurable-switches-and-triggers) — per-level wiring tables and editor UX for shoot-to-toggle puzzles

### Ship upgrades
- [Upgrade system](#ship-upgrades) — nine candidate upgrades feeding the Metroidvania reward loop

### Levels & worldbuilding
- [More than 6 levels / level packs](#more-than-6-levels--level-packs) — bake more or stream from disc per gravity cycle
- [Metroidvania structure](#metroidvania-structure) — one large interconnected map with gated upgrades
- [Escape the flooding mine](#escape-the-flooding-mine) — race upward against a rising water line
- [Puzzle-oriented levels](#puzzle-oriented-levels) — compose mechanics into self-contained logic puzzles
- [Multiple / split landscape paths](#multiple--split-paths) — replace the two-wall corridor model
- [Standalone landscape segments](#standalone-landscape-segments) — floating islands / isolated obstacles

### Mission types
- [Land safely / collect-and-deliver / briefings / popups](#new-mission-types) — table of new mission requirements
- [Rescue NPCs](#rescue-npcs) — Choplifter-style pickups paying into the upgrade economy
- [Keys and doors](#keys-and-doors) — full key/door system extending the existing $07/$08 switches

### Stretch goals
- [Enemy Thrust ship](#enemy-thrust-ship) — AI-piloted ship sharing the player's physics model

### Engine constraints (acknowledged, not currently planned)
- [Pod must be object index 0](#pod-must-be-object-index-0)
- [Support for multiple pods per level](#support-for-multiple-pods-per-level)
- [First 255 terrain rows are fixed](#first-255-terrain-rows-are-fixed)
- [32 shared particle slots](#shared-particle-slots)
- [Expanding X axis to 16 bits](#expanding-x-axis-to-16-bits) — currently infeasible
- [Variable wall slopes](#variable-wall-slopes) — currently infeasible

---

## Enemies, weapons & hazards

### Current enemies (for reference)

- **Gun emplacements** (types `$00..$03`, all builds). Fire probabilistically using the shared particle pool with type `PARTICLE_type_hostile_bullet` ($03). Firing angle is `gun_base_angle` (3 bits from `gun_aim`) plus random spread masked by `gun_angle_spread_mask` (2 bits from `gun_aim`).
- **Timed laser turrets** (types `$09..$0C`, SWRAM). See [Completed](#completed) for the implementation summary and [follow-ups](#timed-lasers-follow-ups) below.
- **Gravity well** (type `$0D`, SWRAM). See [Completed](#completed) and [follow-ups](#gravity-well-follow-ups).

### New enemy bullet types

The particle system's `particles_type` field ($07A0) could be extended with new type values. Collision handling at lines 5981-6020 already branches on particle type, so new behaviours can be added there.

| Type | Behaviour | Implementation notes |
|------|-----------|---------------------|
| Standard bullet | Absorbed by shield, no impulse | Current hostile bullet behaviour already works this way |
| Heavy bullet | Absorbed by shield, applies impulse to ship | On shield collision, add bullet velocity to `force_vectorx/y` instead of just killing the particle |
| Explosive | Knocks out shield temporarily, applies impulse | Add a `shield_disabled_timer`; when hit, set timer and force shield off for N frames |
| Laser / railgun | Bounces off shield, passes through destructibles | On shield hit, reflect velocity vector; skip object collision checks |
| Rocket | Straight-line propelled projectile | Constant velocity (no gravity), longer lifetime, larger collision box |
| Guided rocket | Steers toward player with limited turn rate | Each frame, adjust velocity toward player position by a small angle delta |
| EMP | Knocks out shield and tractor beam temporarily | Disable both systems via timers; visual effect using star particles |

**Considerations:**
- The particle pool is fixed at 32 entries — rockets and guided missiles need careful lifetime management
- New bullet types would need new `particles_type` values and corresponding collision branches
- Guided rockets need per-frame angle updates, adding CPU cost proportional to active guided missiles

### Mini power nodes

Small destructible objects that, when shot, explode and take out a pre-defined chunk of the landscape around them. Not landscape deformation — each node has an authored "hole shape" that gets blitted into the terrain wall buffers when triggered. Could open up hidden passages, create shortcuts, or remove terrain blocking a mission objective.

**Implementation notes:** the hole shape could be stored as a list of (row, new-left, new-right) triples patched into `terrain_left_wall`/`terrain_right_wall` on trigger. Visual effect reuses the existing explosion particle burst.

### Landing bubbles

Soft capture points that hold the ship in place while it recharges fuel or shield, then dissipate after a fixed duration or when recharge completes. Different from a landing pad: the bubble locks the ship regardless of approach angle, but each bubble is single-use.

**Implementation notes:** on contact, zero the ship's velocity and disable physics updates until the timer expires or the player thrusts out. Visual could be a pulsing circle drawn with XOR particles around the ship.

### Fans / turbines

Directional force emitters — an alternative to the radial gravity nodes. Each fan applies a constant force vector to the ship while inside its column of influence. Useful for vertical shafts (upward fans assist ascent) or horizontal corridors (blow the ship sideways).

**Implementation notes:** rectangular region test; on overlap, add a fixed vector to `force_vectorx/y`. Animated blade sprite for visual feedback.

### Rotating gun emplacements

Like the existing gun types $00-$03 but with a continuously rotating aim angle instead of fixed cardinal directions. Fires when the aim passes near the player, or on a fixed timer regardless of aim. Already have the 17 rotation frames from the ship sprite system — could reuse the same angle indexing.

**Implementation notes:** per-frame `gun_base_angle` increment; existing particle spawn code handles the rest.

### Bobbing mines

Passive hazards that float in place, bobbing gently up and down on a sine wave. Destroy on contact with ship or bullet, exploding with a blast radius.

**Implementation notes:** Y position is `base_y + sin(frame_counter + phase) * amplitude`. Phase offset per mine so a group doesn't bob in lockstep. Collision is a simple circle test; on contact, spawn an explosion particle burst and apply radial impulse to the ship if close enough.

### Hot areas

Regions (near reactors, lava, engines) where the ship accumulates heat over time. As heat rises, flight degrades: thrust magnitude drops, handling becomes sluggish, and eventually the ship takes damage. The player must leave the hot area and "rest" in a safe region to cool down, or dunk into water (see below) for fast cooling. A heatsink upgrade extends safe dwell time.

**Implementation notes:** a single-byte `ship_heat` counter increments each frame while in a hot region, decrements elsewhere. Thrust scaling and damage thresholds read this value. Heat zones can be defined as rectangular regions or tied to specific object types (reactor, lava tiles). Visual feedback: hull colour shift via palette, or heat-shimmer particles emitted from the ship when hot.

### Water as a general element

Distinct from the flooding-mine scenario below: water as a static (or slowly-animated) environmental feature that the ship can enter, not just avoid. Possibilities:
- **Submerged regions** with modified physics: reduced gravity, heavy damping on velocity (drag), thrust still works but is weaker
- **Water as terrain hazard:** instant destruction on contact (simple version, matches the flooding mine)
- **Floating objects:** pods or pickups that float on the water surface
- **Bubbles released by thrust** when submerged, using the existing particle pool

**Implementation notes:** rendering-wise, the timer-based palette switch described in the flooding-mine section works for a static water line too. Physics changes would branch on `ship_ypos > water_line_y` to swap in alternate gravity/damping constants.

---

## Gravity well follow-ups

The well object (type `$0D`) is implemented — see [Completed](#completed). Open items:

- **Sprite:** the engine currently early-exits to `next_object` for type `$0D` to avoid plotting a non-existent sprite. A real sprite would let the well show up in-game (subtle field shimmer, swirl, etc.) and remove the early-exit.
- **Centre-case symmetry:** at exact `dx == dy == 0` the per-axis sign multiplication yields `+pull` on both axes (BPL treats 0 as positive). Minor visual artefact only; gravity drags the ship out anyway.
- **Per-axis half-scaling:** v1 applies the full pull to each axis. At a 45° corner this is √2 stronger than on-axis — flip to per-axis `pull/2` if it feels too aggressive in play.
- **Apply pull to thrust particles too.** Currently the well pulls the ship and emits its own debris ring; routing the same per-frame force into active `PARTICLE_type_debris` particles spawned by the ship's exhaust would let the player *see* the field bend their trail as a visual cue, without needing a sprite. Slot naturally next to the existing well walker.

### Gravity field objects (other variants)

Siblings of the implemented well, sharing the same data layout:

- **Gravity flipper:** inverts the Y component of gravity while the ship is inside the radius.
- **Gravity null:** zeroes gravity inside the radius (fly like in open space). Could share the well's data layout — reserve `strength == 0` to mean "null mode" or use a separate flag bit. Implementation needs the loop to run *before* `add_gravity_to_force_vector` so it can suppress the gravity add, instead of the current "add on top".
- **Paired generators/repulsors acting on ship *and* pod:** the pod has its own physics state (`pod_xpos`, `pod_ypos`, velocity) — extending the field check to the pod as well means the tethered system can be yanked around by the environment, not just the ship. Since the tether is a rigid rod, asymmetric forces on ship vs pod create interesting angular dynamics.
- **Fields that act on bullets:** apply the same force to active particles of type `PARTICLE_type_player_bullet` and/or hostile bullet. Bending a player bullet around a corner to hit a turret tucked in an alcove opens up real puzzle geometry. Costs more per frame (force applied to every bullet inside every field) but the bullet count is bounded by the 32-slot particle pool.

**Implementation notes:** the existing gravity constant is applied per frame in the physics update. A check against object position/radius could substitute a modified gravity value before integration. Multiple overlapping fields would need a priority rule. Bullet-affecting fields slot naturally into `particles_update_and_draw` (line 5799) — per-particle force application already exists for gravity.

---

## Timed lasers follow-ups

Timed laser turrets (types `$09..$0C`) are implemented — see [Completed](#completed). Open items:

- **No telegraph / warning before the on-phase.** Rely on the cycle being long enough that the player can read the rhythm.
- **Optimised line draw.** The Bresenham line plotter is generic; a faster routine will be needed as the laser count grows (per-laser draw + erase XORs every frame). Worth profiling once a level uses several lasers at once. See [custom directional line drawing routine](#custom-directional-line-drawing-routine).
- **Shield interaction.** Hasn't been investigated. Currently the beam destroys the player even with shield held — same path as terrain pixels do.
- **Shootable behaviour toggles.** Let the player change a laser's config by shooting a switch object — toggle on/off, swap horizontal/vertical orientation, change duty/period. The existing door-switch object types ($07/$08) become the carrier; their action targets `gun_aim` on the wired laser instead of (or as well as) terrain. The general design — per-switch wiring table, action codes, editor UX — is in [Configurable switches and triggers](#configurable-switches-and-triggers).
- **Rotating lasers.** Same idea as rotating gun emplacements but with the beam: increment the beam endpoint's `(dx, dy)` each frame around a circle. The expensive part is the per-frame Bresenham erase + re-draw, which a custom line-draw routine makes feasible. Probably budget-constrained to one or two rotators per level until profiled.

---

## Custom directional line drawing routine

Generalise the laser draw path: given a start pixel and direction `(dx, dy)`, walk along the ray and plot pixels until either the screen edge or an existing non-background pixel (landscape, sprite) is hit. Acts as both renderer and collision query. Uses:

- Lasers terminate naturally at terrain instead of clipping to a fixed length, so a beam through a tunnel mouth lights up only the open part.
- A "feeler" for AI or homing rockets — same routine, returning the hit point instead of plotting.
- Cheaper than full Bresenham draw + separate collision because the early-out on first non-background pixel does both jobs in one walk. Would replace the current generic `draw_line` for laser beams once it's written.

---

## Configurable switches and triggers

A meta-mechanic that lets the level designer wire shoot-the-button switches to changes in other objects (lasers, doors, fields), entirely from the editor. This is the foundation for puzzles: ordering challenges, gated laser grids, "shoot all four switches to unlock the exit" rooms, etc.

### Current state (level 3/4/5 doors)

The existing system is the bare minimum that the original game needed and is hardcoded:

- **Two switch object types** ($07 right, $08 left) that, when shot, set the global byte `door_switch_counter_A = $FF` (`thrust.6502:1817`). All switches on a level set the same byte — there is no per-switch state.
- `tick_door_logic` (`thrust.6502:3294`) runs every frame: decrements `door_switch_counter_A` toward zero, then `CMP level_number` and dispatches to one of three hardcoded routines: `level_3_door_logic`, `do_level_4_door_logic`, `do_level_5_door_logic`.
- Each per-level routine hardcodes:
  - **Where the door is** (window-Y test before doing anything: `LDA #$69 SBC window_ypos_INT` etc.)
  - **What the door looks like** (writes specific bytes into specific `terrain_left_wall,Y` rows — width 13 for level 3, 21 for level 4, two-segment diamond for level 5)
  - **Animation curve** (`door_switch_counter_B` chases `_A` while open, increments back when closing)
- Outcome: a single one-shot timed door per level, written into the *left wall* only, that re-closes on a fixed timer. No level can have two independent doors. No switch can target anything other than terrain. Levels 0/1/2 ignore switches entirely.

### Proposed generalised model

Introduce a per-level **wiring table** that maps each switch object to a target object and an action. Replace the `level_number` dispatch with a generic walker.

**Switch state.** Per-switch latch byte instead of one global counter — either an array indexed by object index, or a small bit field if 8 switches per level is enough. State is one of:
- `latched` (just shot, action is firing or pulsing)
- `idle` (default)

For toggle-style targets the state is the *target's* state, not the switch's; the switch only fires the transition.

**Wiring entry (per switch):**

| Field | Bytes | Purpose |
|-------|-------|---------|
| target object index | 1 | which level object to act on (`$FF` = "modify terrain", same as today) |
| action code | 1 | toggle / pulse / cycle / set / `gun_aim` mask write |
| value or duration | 1-2 | action argument (e.g. new `gun_aim`, pulse frame count, cycle list pointer) |

Three wiring bytes per switch × ~8 switches per level = ~24 bytes per level. Comparable to the existing per-laser endpoint arrays.

**Action codes worth supporting:**

- **`toggle_laser`** — flip a bit in the target's `gun_aim` (e.g. swap horizontal/vertical orientation, or invert duty bit) so the laser visibly changes behaviour. Cheapest to implement: just XOR a stored mask into `gun_aim,X`.
- **`set_laser_aim`** — write a stored value into target's `gun_aim`. Lets a switch reset a laser to a specific phase / duty.
- **`cycle_laser`** — step `gun_aim` through a small list of values (stored inline in the wiring table or as a separate list). Each shot advances by one. Ordering puzzles fall out of this naturally.
- **`pulse_door`** — mimic current behaviour: write a hole into terrain for N frames then close. Door geometry now travels in the wiring entry (row, width, location) rather than being hardcoded. Probably needs a separate "door object" type so the geometry is editor-placeable.
- **`flip_well`** — invert a gravity well's `strength` sign. Pull becomes push, opens routes that were previously closed.
- **`destroy_object` / `spawn_object`** — wholesale enable/disable a target by setting/clearing its `OBJ_flag_alive` bit. Useful for "shoot the switch to drop the force field" without animating anything.

The dispatch for these is a single jump table indexed by action code, so adding new actions is cheap.

### State and ordering

The single global counter has to go. Two replacements depending on ambition:

1. **Per-target state byte.** Each *target* object has a "current mode" byte (already true for lasers via `gun_aim`). Switches just write into it. Easy. No ordering memory.
2. **Per-level switch bit field.** A byte (or two) of "switch-was-triggered" flags. Targets can read the field and react to combinations (e.g. "laser turns off only if all four switches are set"). This is the path to ordering puzzles — combinations and sequences become expressible by giving the target a small predicate over the bit field.

Approach 1 alone covers most cases. Approach 2 layered on top opens up puzzle design without changing the action set.

### Editor UX

- Switch placement is unchanged — drop a $07/$08 object as today.
- Selecting a switch shows its **wiring**: a thin coloured line drawn from the switch sprite to its target object. The target is also subtly highlighted while the switch is selected.
- Right-click on a target while a switch is selected = "rewire to this object". Very direct, no menu navigation.
- A small popup (or status-bar field, in the same style as the laser `(dx, dy)` readout) shows the current action code and value. `[`/`]` cycles action codes; up/down nudges the value byte.
- Doors stop being level-specific: a door-object type with editable position and width, triggered via a switch's `pulse_door` action. Levels 3/4/5 of the original game become regular wirings against this generic door object — no hardcoded routines.
- Visual feedback in-editor for puzzle authoring: when a switch is hovered, draw the resulting state delta (e.g. show the laser in its post-shot config) so the designer can see the puzzle without simulating it.

### Engine implications

- `tick_door_logic` becomes `tick_switch_logic`: walk the wiring table, advance any pulses/cycles, write the resulting bytes into target objects' state. No more `level_number` test. The current per-level door routines collapse into the `pulse_door` action's body — generic door drawing into terrain given a (row, width, screen-Y) tuple.
- Hostile-bullet collision against switch objects already exists (it's how shooting them is detected). The collision hook just sets the switch's per-instance latch byte instead of the global counter.
- Per-level wiring table lives alongside the existing object arrays in `tools/output/thrust_levels_export*.asm`, exported by the editor like everything else.

### Puzzle implications

Once switches can target anything and the editor exposes wiring, a few puzzle archetypes follow naturally:

- **Sequence locks.** Four switches must be shot in a specific order. Each switch's `cycle_laser` action depends on the previous laser being in a specific state, so out-of-order shots reset the chain.
- **Mutually-exclusive switches.** Two switches each toggle the *same* laser between horizontal and vertical; the player must pick the orientation that matches the path they need. Re-shootable, encouraging trial.
- **Field flips for routing bullets.** A switch flips a gravity well from pull to push so the player's bullets curve to a hidden target — combines with the "fields act on bullets" idea.
- **Timed corridors.** A switch sets a laser's duty to a long-off phase; the player has a window to fly through before duty creeps back up via a separate `cycle_laser` somewhere else.

### Migration path

Don't break the original game. Two-step rollout:

1. Implement the wiring system behind a build flag (`_CONFIGURABLE_SWITCHES`). Original level-3/4/5 doors keep their hardcoded routines while the flag is off, anchoring the canonical CRC.
2. With the flag on, generate equivalent wiring entries for the original doors during level export — the editor reads the original level 3/4/5 doors and writes them out as a wired pulse_door + generic door object pair. New levels use the system natively.

This mirrors how `_TIMED_LASER` and `_GRAVITY_WELL` were introduced.

---

## Ship upgrades

An upgrade system feeds directly into the Metroidvania structure — and with rescue NPCs (see [Rescue NPCs](#rescue-npcs)) acting as the currency, upgrades become the reward loop. Candidates:

| Upgrade | Effect | Implementation notes |
|---------|--------|---------------------|
| Reinforced shield | Survive or bounce off a wall impact instead of exploding | Wall collision handler checks an upgrade flag before triggering destruction; on bounce, reflect velocity with damping |
| Absorbing shield | Reduces knockback impulse from heavy bullets / explosions | Scale the incoming impulse by an upgrade-dependent factor before adding to `force_vectorx/y` |
| Heavier bullets | Player bullets deal more damage or pass through weak terrain | New `particles_type` variant, or a damage multiplier read on hit |
| Inertial dampers | Passive velocity bleed — ship comes to rest faster when not thrusting | Apply a small per-frame scalar reduction to `vel_x`/`vel_y` when thrust is off |
| Improved handling | Faster rotation, finer aim increments | Scale the rotation delta applied per frame by the upgrade factor |
| Docking computer | Auto-hover mode: engine automatically applies gravity-cancelling thrust | When enabled, substitute a computed thrust value that zeroes net Y force; drains fuel faster than idle |
| Bigger fuel tank | Higher max fuel, longer flight time | Raise the fuel cap; no other physics change |
| Heatsink | Extends safe time in hot areas (see [Hot areas](#hot-areas)) | Scale `ship_heat` accumulation rate down |
| Tractor range / strength | Longer tether, faster pod slew, or tolerates more angle stress | Adjust tether constants; the physics already reads these as values |

Upgrades could be persistent across a run (Metroidvania) or per-level purchases at a shop screen between levels.

---

## Levels & worldbuilding

### Current limits (for reference)

- **Y axis:** Q16.8 format supports worlds up to 65535 rows deep. Existing levels use ~700-1500 rows. No hard limit here.
- **X axis:** 8-bit world X (0-255), wrapping at ~$B8-$DC. The visible viewport is 72 columns. World is ~184 columns wide.
- **RLE data size:** each level's terrain is stored as 4 arrays (left/right count + increment). The total size is limited by available ROM/RAM. Current levels use 7-30 segments per wall.
- **Wall buffers:** 256-byte circular buffers. Only 73 rows are visible at once, so 256 entries provide comfortable margin. Not a practical limit.
- **Object count:** terminated by $FF sentinel in the type array. No explicit limit, but all objects are checked every frame for visibility/collision, so very large counts would impact performance.

Levels can be made significantly deeper without engine changes. Wider levels would require extending the X coordinate to 16 bits, which is currently infeasible — see [engine constraints](#expanding-x-axis-to-16-bits).

### More than 6 levels / level packs

The game ships with 6 levels baked into `level_data.6502` (`terrain_left_wall_count_0` through `terrain_right_wall_inc_5`), loaded by `initialise_level_pointers` (line 6274). The "reverse gravity every 6 levels" mechanic at `thrust.6502:6841` implies the original design treats 6 as a loop length, not a hard cap on unique content.

**Increase the baked-in count:** add more level-data arrays and extend the pointer tables. Limited by available memory — each level is a handful of RLE arrays plus an object table, so dozens fit comfortably if there's RAM/ROM to spare. Keep the 6-level gravity cycle intact as a cadence marker (levels 1-6 normal gravity, 7-12 inverted, etc.) or re-tune it.

**Level packs loaded from disc:** instead of baking all levels into the binary, keep one pack (6 levels, or whatever the current cycle length is) resident at a time and load the next pack from disc between missions. This is how most BBC disc games handled large level counts. Each pack is a single file containing the RLE arrays and object tables for its levels; loading reuses the existing `OSFILE`/`OSWORD` disc routines already linked in. Pack size should match the gravity cycle (currently 6) so the reverse-gravity logic keeps working naturally — if the cycle length changes, the pack size follows.

**Considerations:**
- Level pointer tables become pack-relative rather than absolute
- Disc access between levels is noticeable but acceptable (Thrust already loads from disc at boot)
- Opens the door to user-authored level packs via the level editor's export — just drop a new pack file onto the disc image
- Save-game support (current level number + pack identifier) becomes more important since players won't grind through all content in one sitting

### Metroidvania structure

One large interconnected map rather than discrete levels. The player starts with basic thrust and weapons, gradually acquiring upgrades that open up previously inaccessible areas:

- **Ship upgrades:** stronger thrust (navigate tighter shafts against gravity), improved shield (survive new hazard types), tractor beam range extension, new weapon types
- **Gate mechanics:** areas blocked by terrain or hazards that require specific upgrades — e.g., a narrow vertical shaft too deep to escape without upgraded thrust, a corridor lined with turrets that require a shield upgrade to survive
- **Bosses:** large gun emplacements or enemy ships guarding key upgrades. Could be multi-phase — destroy shield generators around a core, then hit the core
- **Secrets:** hidden passages behind destructible walls, reward rooms with extra fuel or bonus upgrades. False walls that look solid but can be flown through
- **Save points / fuel stations:** the generator (type $06) could double as a checkpoint. Respawn at the last generator visited rather than restarting the whole map
- **Map progression:** start at a surface base, descend into increasingly hostile cave systems. Each major section has a distinct visual theme (palette swap per region) and introduces new enemy types

The existing level data format could support this — one very deep level with many objects. The main challenge is memory: a large interconnected map needs more RLE terrain data and more objects than the current per-level arrays allow. Could use banked memory or stream terrain data from disc.

### Escape the flooding mine

Start at the bottom of a deep vertical mine and race upward. A rising water level chases the player — touch the water and it's game over.

**Water rendering:** two approaches:

1. **Timer-based palette switch (Exile style):** set up a raster interrupt that fires at the water line's screen position. Below the interrupt, swap the palette so all colours shift to blue/dark variants. Cheap in CPU — just a palette write in the IRQ handler. The water line advances by moving the timer trigger point up by a few scanlines each frame. Limitation: only works for a horizontal water line, no waves or splashing.
2. **Software rendering:** EOR-draw a horizontal band of colour across the screen below the water line. Since the water rises slowly (a few rows per frame), only the newly-flooded rows need drawing each frame — similar to how the terrain delta rendering works. More flexible (could add wave effects at the surface) but costs more CPU.

**Gameplay mechanics:**
- Water rises at a steady rate, creating constant upward pressure
- Horizontal doors (already supported as types $07/$08) act as barriers that temporarily hold back the water, buying the player time — but they eventually burst or leak
- Fuel management becomes critical: thrust hard to stay ahead but risk running dry
- Optional side chambers with fuel pickups, accessible only by briefly diving below the main path and racing back up
- The mine gets narrower and more complex as the player ascends, requiring precise navigation under time pressure

### Puzzle-oriented levels

Levels designed as self-contained logic puzzles rather than pure dexterity challenges. The new environmental objects (gravity fields, fans, bullet-deflecting fields, power nodes, landing bubbles) are the building blocks. Example puzzle structures:

- **Key-and-lock:** shoot a power node to open a passage, but the node is behind a corner — only reachable by routing a bullet through a gravity-bending field
- **Gravity maze:** a chamber where the player must chain gravity flippers to navigate, since raw thrust can't reach the exit
- **Bullet billiards:** destroy a target by setting up a bullet that bounces or bends through multiple gravity fields
- **Escort with a twist:** carry the pod through a region where gravity fields pull ship and pod in opposite directions — the player has to time their path so the tether doesn't snap
- **Time-lock:** a timed laser turret guards the exit; the only safe window requires first disabling a fan that would otherwise blow the ship into the beam

Each level becomes a small "what order do I do this in" problem rather than "how fast can I fly through." Fits well with the Metroidvania structure — optional puzzle rooms gate extra upgrades.

### Multiple / split paths

The terrain is fundamentally a corridor defined by two walls (left X and right X per Y row). The RLE format encodes each wall as a series of (count, x-increment) segments. The renderer draws exactly two wall edges per scanline using EOR delta plotting. Multiple paths would require replacing the single left/right wall model. Options:

- **Segment list per scanline:** store multiple (left, right) pairs per Y row. The renderer would iterate through segments instead of reading two fixed values. The RLE format would need to encode segment starts/ends.
- **Tile map:** replace the wall system entirely with a character-based tile map. Simpler data format but loses the smooth diagonal walls and would need a completely new renderer.

### Standalone landscape segments

Floating islands, pillars, or isolated walls cannot be represented in the current two-wall model. Would need:
- A separate "obstacle" layer rendered after the main walls
- Each obstacle defined as a rectangular or polygon region
- Collision detection against obstacle bounds in addition to wall checks at lines 5871-5874

---

## New mission types

The current game loop is: collect pod, escape through ceiling, destroy reactor (optional). New mission types would require:

| Mission | Requirements |
|---------|-------------|
| Collect the pod | Already implemented |
| Land safely | Add landing pad object type; detect ship velocity < threshold and angle near vertical when touching pad |
| Collect and deliver | Track cargo state (empty/carrying/delivered); add delivery zone object type |
| Mission briefing | Text display before level start; could reuse the existing string rendering (`draw_string`, line 2240) |
| Mid-mission popup | Pause game, overlay text, resume on keypress |
| Keys and doors | New object types for keys (collectible) and doors (blocking terrain). Door switch types $07/$08 already exist — extend the mechanism |

### Rescue NPCs

Little characters scattered around the level — civilians, stranded miners, survivors — that the player can pick up with the tractor beam (same mechanism as the pod) for a cash bonus. Like *Choplifter* or *Airlift*: fly down, hover over the NPC, suck them up, fly them home. Cash from rescues funds ship upgrades between missions.

**Implementation notes:**
- NPCs are a new object type with their own sprite. They stand on terrain (or walk back and forth between two points for a bit of life)
- Tractor beam already tethers objects — the code path at `update_pod_tractor_beam` (line 4572) is hardcoded to object 0, so either extend that to iterate other pickup-type objects, or use a simpler "proximity pickup" model where NPCs vanish when the ship hovers close enough
- Each NPC must be delivered to a drop-off zone (existing base, or a dedicated rescue pad) for the bonus to register — encourages full round trips, not just grab-and-dump
- Limit on carry capacity (one at a time? or a counter?) adds a risk/reward dimension — do you go for more rescues or cash in what you have?
- If carrying multiple NPCs conflicts with the single-pod constraint, start with "one rescue at a time"

### Keys and doors

Door switches (types $07 and $08) already exist in the object system. The current implementation likely toggles a terrain section. Extending this to a full key/door system would need:

- Key objects that disappear when the ship touches them, setting a flag
- Door objects that check the flag and open/close terrain sections
- Visual feedback (door animation, key collection effect)

See also [Configurable switches and triggers](#configurable-switches-and-triggers), which subsumes much of this.

---

## Stretch goals

### Enemy Thrust ship

An AI-controlled ship using the same physics model as the player. Would need:

- Separate state variables for position, velocity, angle, thrust
- AI decision loop: navigate toward player, avoid terrain, fire weapons
- Terrain avoidance using the wall arrays (check `terrain_left_wall` and `terrain_right_wall` ahead of travel direction)
- Significant CPU budget — the physics simulation for one ship is already substantial

This would be the most ambitious addition. A simpler version could follow a pre-scripted path rather than full AI navigation.

---

## Engine constraints to be aware of

Acknowledged limits of the current architecture. Not active work items unless a feature explicitly needs them lifted.

### Pod must be object index 0

The tractor beam check at `thrust.6502:4572` reads `level_obj_flags` without an `,X` index, hardcoding it to object 0. All pod physics use single-instance variables. The level editor export enforces this by sorting type $05 first. See [Support for multiple pods](#support-for-multiple-pods-per-level) for what changing this would entail.

### Support for multiple pods per level

The game currently only supports a single pod (type $05) per level. The tractor beam activation check at `thrust.6502:4572` reads `level_obj_flags` without an `,X` index, hardcoding it to object index 0. All pod physics and rendering use single-instance variables (`pod_xpos`, `pod_ypos`, `pod_tethered_flag`, etc.), not arrays.

**To support multiple pods would require:**
- Changing `update_pod_tractor_beam` (line 4572) to use indexed access (`level_obj_flags,X`) with the current pod's object index stored in a variable
- Adding logic to select the nearest visible pod when the tractor beam is activated
- Either converting pod state variables to arrays (to track multiple attached/detached pods) or limiting the player to interacting with one pod at a time while allowing multiple to exist in the level

### First 255 terrain rows are fixed

The game's dual-triple terrain decoder initialises both triples with a hardcoded counter of $FF (255). The first 255 rows of each wall always use a single uniform increment (segment 1). Edits within this region cannot be represented in the RLE format. The level editor enforces this constraint in the encoder.

### 32 shared particle slots

All particle effects (player bullets, enemy bullets, debris, stars, exhaust) share a single 32-entry pool. Player bullets are limited to 4 simultaneous. Adding new particle-based features (thrust exhaust, new weapon types) increases contention for this fixed pool.

### Expanding X axis to 16 bits

Widening the world X coordinate from 8 to 16 bits would touch the physics integration, `landscape_draw` world-to-screen conversion, terrain wall decoder, X wrap logic, object visibility checks, and every ZP variable and lookup derived from `window_xpos_INT` / `ship_xpos_INT`. The cycle budget is already tight, and adding a high byte to every per-frame X computation would push multiple hot paths (landscape_draw, particles, object iteration) over frame. Parked for now — revisit only if a specific level design genuinely needs a world wider than 256 columns, and budget a significant refactor.

### Variable wall slopes

Currently walls move by 0 or 1 column per scanline (the increment is applied every row). Steeper slopes are possible (increment > 1 per row), but shallow slopes (< 1 column per row) would require fractional increments. The 8-bit increment already supports this via unsigned wrapping — a value like $80 moves half a column per row on average, but the discrete steps would look jagged. True sub-pixel slopes would need a fixed-point accumulator in the RLE decoder, which changes the format and the hot-path decoder. Not worth it without a concrete design need.

---

## Completed

Implemented features and finished investigations, newest first. Each entry links to the relevant code or documentation.

### Features

- **Generic per-object extra-data slots** — `level_N_obj_data_0/1/2`, with each object type interpreting the slots itself (slot 0 = gun_aim; slots 1/2 = laser dx/dy or well radius/strength). Laser and well code share the slot 1/2 lookups via separate SMC sites; the two well-specific lookup tables were dropped. SWRAM build shrank by 256 bytes; non-SWRAM CRC remains anchored at `6389c446`. Adding a new object type with config bytes is now a code change only — no new export array, no new SMC patch, no new lookup table.
- **Lasers draw in object colour** — beam now uses `OBJECT_COLOUR_BYTE` (`$FF`, logical colour 3) instead of `hostile_bullet_pixel_byte` so it reads as part of the level palette. Ship-vs-pixel collision still works (any non-zero pixel under the ship triggers it).
- **Gravity well** (`_GRAVITY_WELL`, SWRAM build, type `$0D`). While the ship's midpoint is inside the well's Manhattan radius, a linear-ramp pull toward the centre is added to `force_vector{x,y}` once per gravity tick. Hooked from `apply_gravity_wells_to_force` after the constant-gravity add. Per-instance `radius` (unsigned 0..127, 0 = inactive) and `strength` (signed). Pull magnitude is the high byte of `strength * (radius − r)` where `r = |dx| + |dy|`. Editor places `$0D` with a centre dot plus Manhattan-radius diamond (blue pull, red repulsor). Debris ring spawned around each well per gravity tick visualises the field. Open follow-ups in [main body](#gravity-well-follow-ups).
- **Timed laser turrets** (`_TIMED_LASER`, SWRAM build, types `$09..$0C`). Four orientations replacing the old heavy-turret slot. Beam is XOR-drawn via Bresenham `draw_line`; ship-vs-pixel hit detection picks it up automatically. Per-laser state in `level_obj_flags` bit 2 (`OBJ_flag_laser_beam_drawn`) plus cached `obj_laser_prev_screen_x/y`. Per-instance config: `gun_aim` low nibble = phase index (×8 frames), high nibble = duty index (×4+4 frames); period fixed at 128 frames. Per-instance beam endpoint `(dx, dy)` stored in obj_data slots 1/2. Editor lets the designer drag the beam tip and adjust phase/duty live. Open follow-ups in [main body](#timed-lasers-follow-ups).
- **Thrust particles from ship exhaust** (`_THRUST_PARTICLES`, SWRAM build) — debris particles spawned at the ship exhaust point with angle-derived velocity and random spread.
- **Disabling X wrap underground** (`_NO_WRAP_UNDERGROUND`, build flag). Per-level Y threshold can skip the X wrap logic when the player is below a configurable depth. Build flag, ZP variables, per-level data tables, level editor support (draggable no-wrap line), and a skip check at `check_x_wrap` are implemented. Right-side wrap works; left-side wrap is broken (when `window_xpos_INT` approaches zero, wall lookup goes wrong and the right wall fills the screen with terrain). Likely root cause: `landscape_draw` world-to-screen subtraction or terrain wall array indexing breaking down at low window X. Flag is left `FALSE` for now — revisit alongside any 16-bit world X work.

### Investigations

- **Test level made.** Sandbox level for experimenting with new features, edited via `tools/level_editor.py` and round-tripped through `--import` / Ctrl+S.
- **Landscape drawing** — documented in `docs/landscape-drawing.md`. RLE delta-compressed terrain with two interleaved decoder triples per wall; 256-byte circular wall buffers at $0400/$0500; EOR-based incremental rendering; half-resolution vertical rendering.
- **Ship dynamics** — documented in `docs/ship-physics.md`. Midpoint-based physics; one-frame-behind Euler integration; Q7.16 X force, Q7.8 Y force, Q8.16 X position, Q16.8 Y position; tether modelled as a rigid rod with angular velocity and damping; thrust halved when pod attached.
- **Raster timing / cycle budget.** No raster timing or cycle-counting infrastructure currently exists. The IRQ handler (`thrust.6502:5296`) distinguishes vsync from Timer1 via `irq1_timer1_signal` but there are no budget annotations. To instrument: set up Timer1 to fire at a known point in the frame, toggle a palette register or border colour at the start/end of key routines (landscape_draw, particles_update_and_draw, draw_player) to reveal how much of each frame is spent on each system.
- **Slowest code paths.** Likely candidates based on code structure: `landscape_draw` (line 755) iterates all 73 visible scanlines; `particles_update_and_draw` (line 5799) updates and redraws all 32 particles; `update_objects_loop` (line 1393) iterates all level objects; ship sprite plotting renders 17 rotation frames + shield, XOR-plotted with clipping.
