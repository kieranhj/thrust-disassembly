# Ideas / Future Work

Working title: **Thrust Next** — essentially Thrust meets Exile.

---

## Index

Open work items, one line each. Full details in the sections below; completed work in [Completed](#completed) at the bottom. Known defects and stale comments are in [bugs.md](bugs.md).

### Enemies, weapons & hazards
- [New enemy bullet types](#new-enemy-bullet-types) — heavy / explosive / laser / rocket / guided / EMP variants on the existing particle system
- [Mini power nodes](#mini-power-nodes) — shootable destructibles that punch authored holes in terrain
- [Landing bubbles](#landing-bubbles) — soft capture points that hold the ship and recharge it
- [Fans / turbines](#fans--turbines) — directional force emitters over rectangular regions
- [Rotating gun emplacements](#rotating-gun-emplacements) — per-frame angle sweep, fires when aim crosses player
- [Hot areas](#hot-areas) — heat accumulation degrades flight; offset by a heatsink upgrade
- [Water as a general element](#water-as-a-general-element) — submerged regions with modified physics

### Gravity wells — open follow-ups
- [Well sprite](#gravity-well-follow-ups) — replace the type $0D early-exit with a real non-lethal sprite
- [Zero-axis sign fix](#gravity-well-follow-ups) — `dx == 0` or `dy == 0` still gets +pull on that axis
- [Pull direction / magnitude](#gravity-well-follow-ups) — force is always diagonal at √2 × pull; scale per axis by direction
- [Apply pull to thrust particles](#gravity-well-follow-ups) — ship's exhaust bends through the field as a cue
- [Apply pull to bullets](#gravity-well-follow-ups) — bend bullets around corners for puzzle geometry

### Timed lasers — open follow-ups
- [Beam telegraph](#timed-lasers-follow-ups) — visual warning before the on-phase
- [Optimised line draw](#timed-lasers-follow-ups) — Bresenham erase + redraw per laser per frame is generic
- [Shield interaction](#timed-lasers-follow-ups) — beam currently kills through shield; investigate
- [Rotating lasers](#timed-lasers-follow-ups) — per-frame `(dx, dy)` sweep; depends on faster line draw

### Engine / editor
- [Custom directional line drawing routine](#custom-directional-line-drawing-routine) — walk-until-hit; renderer + collision query in one
- [Hostile bullets activate switches](#hostile-bullets-activate-switches) — let stray turret fire trigger switches to enable ricochet / self-defeat puzzles
- [Cycle / sequence-lock action](#switches--triggers-follow-ups) — `cycle_param` action that steps through a list, enabling order-dependent puzzles

### Ship upgrades
- [Upgrade system](#ship-upgrades) — nine candidate upgrades feeding the Metroidvania reward loop

### Levels & worldbuilding
- [More than 6 levels / level packs](#more-than-6-levels--level-packs) — bake more or stream from disc per gravity cycle
- [Multiple / split landscape paths](#multiple--split-paths) — replace the two-wall corridor model
- [Standalone landscape segments](#standalone-landscape-segments) — floating islands / isolated obstacles
- [Disconnected caverns](#disconnected-caverns) — sealed sub-levels reachable only via teleporter pads; primitives shipped, editor navigation / validation open

### Mission types
- [Land safely / collect-and-deliver / briefings / popups](#new-mission-types) — table of new mission requirements
- [Rescue NPCs](#rescue-npcs) — Choplifter-style pickups paying into the upgrade economy
- [Keys](#keys) — collectible keys that arm specific switches; doors and switch wiring already shipped
- [Metroidvania structure](#metroidvania-structure) — one large interconnected map with gated upgrades
- [Escape the flooding mine](#escape-the-flooding-mine) — race upward against a rising water line
- [Puzzle-oriented levels](#puzzle-oriented-levels) — compose mechanics into self-contained logic puzzles

### Stretch goals
- [Enemy Thrust ship](#enemy-thrust-ship) — AI-piloted ship sharing the player's physics model

### Engine constraints (acknowledged, not currently planned)
- [Pod must be object index 0](#pod-must-be-object-index-0)
- [Support for multiple pods per level](#support-for-multiple-pods-per-level)
- [First 255 terrain rows are fixed](#first-255-terrain-rows-are-fixed)
- [32 shared particle slots](#32-shared-particle-slots)
- [Expanding X axis to 16 bits](#expanding-x-axis-to-16-bits) — currently infeasible; analysis in [`16bit-world-x-plan.md`](16bit-world-x-plan.md)
- [Variable wall slopes](#variable-wall-slopes) — currently infeasible

---

## Enemies, weapons & hazards

### Current enemies (for reference)

- **Gun emplacements** (types `$00..$03`, all builds). Fire probabilistically using the shared particle pool with type `PARTICLE_type_hostile_bullet` ($03). Firing angle is `gun_base_angle` (bits 2-4 of `gun_aim`) plus random spread masked by `gun_angle_spread_mask` (bits 0-1 of `gun_aim`, via `gun_spread_mask_table`). `gun_aim` is obj_data slot 0, unpacked on every object update.
- **Timed laser turrets** (types `$09..$0C`, SWRAM). See [Completed](#completed) for the implementation summary and [follow-ups](#timed-lasers-follow-ups) below.
- **Gravity well** (type `$0D`, SWRAM). See [Completed](#completed) and [follow-ups](#gravity-well-follow-ups).

### New enemy bullet types

The particle system's `particles_type` table ($07A0) could take new type values. The pixel-collision handling in `particles_update_and_draw` (`thrust.6502:6670-6713`) already branches on particle type, so new behaviours can be added there.

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

Like the existing gun types $00-$03 but with a continuously rotating aim angle instead of a fixed diagonal. Fires when the aim passes near the player, or on a fixed timer regardless of aim. The ship sprite's 17 rotation frames could be reused with the same angle indexing.

**Implementation notes:** `gun_base_angle` is re-derived from `gun_aim` (obj_data slot 0) on every object update, so rotate by incrementing the base-angle bits of slot 0 each frame; the existing particle spawn code handles the rest.

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

The well object (type `$0D`) is implemented — see [Completed](#completed). Plans: [`plan-gravity-well.md`](plan-gravity-well.md), [`plan-gravity-well-debris.md`](plan-gravity-well-debris.md). Open items:

- **Sprite:** `update_and_draw_all_objects` jumps straight to `next_object` for type `$0D` (`thrust.6502:1676`), so the well has no sprite and no collision. A real sprite (shimmer, swirl) would make it visible in-game without relying on the debris ring.
- **Zero-axis sign:** `apply_gravity_wells_to_force` applies `sign(dy) * pull` and `sign(dx) * pull`, with `BPL` treating 0 as positive. Whenever `dx == 0` or `dy == 0`, that axis still gets `+pull` (right / down) instead of none. Most visible directly above, below or level with the centre.
- **Pull direction and magnitude:** because both axes always get the full pull, the force is always on one of the four diagonals with magnitude √2 × pull, whatever the ship's actual bearing. Scaling each axis by the direction (as the debris emitter's `well_dir_dx/dy_factor` tables do) would make the pull radial; at minimum, halve it per axis if corner pull feels too strong.
- **Apply pull to thrust particles.** The ship's exhaust particles are `PARTICLE_type_debris`. Applying the well's force to them would let the player see the field bend the trail, without needing a sprite. Fits next to the existing well walker.
- **Apply pull to bullets.** Apply the same force to `PARTICLE_type_player_bullet` and/or hostile bullets inside the radius. Bending a player bullet round a corner to hit a turret in an alcove opens up puzzle geometry. Fits into `particles_update_and_draw` (`thrust.6502:6489`), which already applies per-particle gravity. Cost scales with bullets × wells, bounded by the 32-slot pool.

### Gravity field objects (other variants) — obsolete

Superseded by [Y-banded level parameters](#completed): bands give per-region gravity overrides (including reverse and zero gravity) keyed off Y depth, which covers what the flipper / null variants were for. Kept for context; not planned.

- ~~Gravity flipper: inverts the Y component of gravity while the ship is inside the radius.~~
- ~~Gravity null: zeroes gravity inside the radius.~~
- ~~Paired generators/repulsors acting on ship *and* pod.~~

---

## Timed lasers follow-ups

Timed laser turrets (types `$09..$0C`) are implemented — see [Completed](#completed); endpoint plan in [`plan-laser-endpoint.md`](plan-laser-endpoint.md). Open items:

- **No telegraph before the on-phase.** For now the player has to learn the rhythm.
- **Optimised line draw.** `draw_line` is a generic Bresenham plotter. A beam whose geometry changes is erased and redrawn by XOR (unchanged beams take a fast path that skips both). Profile once a level has several lasers. See [custom directional line drawing routine](#custom-directional-line-drawing-routine).
- **Shield interaction.** Not investigated. The beam kills the player even with the shield held, via the same pixel-collision path as terrain.
- **Shootable behaviour toggles.** Done via the switch system: a switch can `set_param` / `xor_param` a laser's phase/duty (slot 0) or beam dx/dy (slots 1/2); `OBJ_flag_laser_redraw_pending` forces the beam to redraw at the new geometry.
- **Rotating lasers.** Sweep the endpoint `(dx, dy)` round a circle each frame. The cost is the per-frame erase and redraw, so this depends on a faster line routine; probably one or two rotators per level until profiled.

---

## Custom directional line drawing routine

Generalise the laser draw path: from a start pixel and direction `(dx, dy)`, walk the ray plotting pixels until the screen edge or the first non-background pixel (landscape, sprite). One routine is both renderer and collision query. Uses:

- Lasers stop at terrain instead of clipping to a fixed length, so a beam through a tunnel mouth lights only the open part.
- A "feeler" for AI or homing rockets: the same walk, returning the hit point instead of plotting.
- Cheaper than a full `draw_line` plus a separate collision test, since the early-out does both in one walk. Would replace `draw_line` for laser beams.

---

## Switches & triggers follow-ups

The core system is shipped — see [Completed](#completed). Plan: [`plan-switches-and-triggers.md`](plan-switches-and-triggers.md). Open follow-ups:

- **`cycle_param` action.** Step the target's parameter through an authored value list, one step per trigger. This is what sequence-lock puzzles need. `set_param` / `xor_param` cover direct writes and toggles; cycling needs a list pointer per wiring entry and a per-switch "current step" byte. Action codes `$0B..$0F` in `action_jump_table` are reserved (`action_none`) for this kind of addition.
- **Switch state visualisation in-game.** A switch that has fired looks the same as an idle one. A palette swap or sprite change would help the player read puzzle state.
- **Per-switch "accepts hostile fire" flag.** All switches are player-bullet-only. See [Hostile bullets activate switches](#hostile-bullets-activate-switches).
- **Predicate triggers (combinations).** Each wiring entry fires whenever its switch is shot. "Fire only when all four switches are latched" needs a per-switch latched state plus a mask check before dispatch, layered on the current dispatcher.

### Puzzle archetypes

These motivated the system. With switches and generic doors shipped, most are now authored in the editor rather than needing engine work:

- **Sequence locks**: need `cycle_param`.
- **Mutually-exclusive switches**: two switches each `xor_param` the same target. Authorable now.
- **Field flips for routing bullets**: `xor_param` the sign bit of a well's strength. Authorable, but only useful once wells pull bullets (see [gravity well follow-ups](#gravity-well-follow-ups)).
- **Timed corridors**: `set_param` a laser's phase/duty. Authorable now.

## Hostile bullets activate switches

Only player bullets can activate switches. In `check_planet_explode_trigger`, the `bullet_test_object` loop walks particle slots `X = 3..0` only (the four player-bullet slots, `thrust.6502:1929`) and skips any particle whose `particles_type` is non-zero (`:1935-1936`), so `PARTICLE_type_hostile_bullet` ($03) never reaches `handle_door_switch` / `try_dispatch_switch_action`.

Letting hostile bullets trigger switches opens a new puzzle type: turrets that defeat themselves. Place a switch where a turret's bullets will end up (bent by a gravity well, or after a field flip) and the level is solved by surviving until the turret hits its own switch. Combines with the gravity-well [bullet pull](#gravity-well-follow-ups) follow-up.

**Implementation:** relax the type filter at `:1935-1936` to also accept type `$03` for switch objects, and walk all 32 particle slots rather than slots 0-3. Cost is a wider AABB sweep per shootable object per frame; the switch action path is the same whichever side fired.

**Risk:** existing player-only puzzles could be tripped by a stray turret bullet. Gate it with a per-switch "accepts hostile fire" flag, packed into a free bit of the wiring row and exposed through the existing inspector schema.

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
- **X axis:** 8-bit world X (0-255). The window wraps forward at `WORLD_X_WRAP_THRESHOLD` ($B8) and backward at 0 or >= $DC. The viewport is 72 columns (`SCREEN_WIDTH_CHARS`), so the world is ~184 columns wide.
- **RLE data size:** each level's terrain is stored as 4 arrays (left/right count + increment). The total size is limited by available ROM/RAM. Current levels use 7-30 segments per wall.
- **Wall buffers:** 256-byte circular buffers (`terrain_left_wall` $0400, `terrain_right_wall` $0500). `landscape_draw` covers 111 rows, with 73 decoded rows above and 72 below as margin. Not a practical limit.
- **Object count:** terminated by $FF sentinel in the type array. No explicit limit, but all objects are checked every frame for visibility/collision, so very large counts would impact performance.

Levels can be made significantly deeper without engine changes. Wider levels would require extending the X coordinate to 16 bits, which is currently infeasible — see [engine constraints](#expanding-x-axis-to-16-bits).

### More than 6 levels / level packs

The game has 6 levels (original data in `thrust1/level_data.asm`, `terrain_left_wall_count_0` through `terrain_right_wall_inc_5`; the SWRAM build uses the editor export `tools/output/thrust_levels_export2.asm`), set up by `initialise_level_pointers` (`thrust.6502:7183`). `reverse_gravity_flag` is inverted every 6 levels (`thrust.6502:9460`), so the original design treats 6 as a loop length, not a cap on unique content.

**Increase the baked-in count:** add more level-data arrays and extend the pointer tables. Limited by available memory — each level is a handful of RLE arrays plus an object table, so dozens fit comfortably if there's RAM/ROM to spare. Keep the 6-level gravity cycle intact as a cadence marker (levels 1-6 normal gravity, 7-12 inverted, etc.) or re-tune it.

**Level packs loaded from disc:** keep one pack resident and load the next from disc between missions, as most BBC disc games did. Each pack is one file holding the RLE arrays and object tables for its levels, loaded with the MOS `OSFILE` call (defined at `thrust.6502:708` but not currently called; the game uses `OSBYTE`/`OSWORD` for keys, sound and the clock). Pack size should match the gravity cycle (currently 6) so the reverse-gravity logic keeps working; if the cycle changes, the pack size follows.

**Considerations:**
- The relocated code starts at `$0A60`, over the area DFS normally uses for workspace and buffers (`$0E00-$18FF`), so mid-game disc access needs that workspace reclaimed or re-initialised (not yet checked)
- Level pointer tables become pack-relative rather than absolute
- Disc access between levels is noticeable but acceptable (Thrust already loads from disc at boot)
- Opens the door to user-authored level packs via the level editor's export — just drop a new pack file onto the disc image
- Save-game support (current level number + pack identifier) becomes more important since players won't grind through all content in one sitting

### Multiple / split paths

The terrain is fundamentally a corridor defined by two walls (left X and right X per Y row). The RLE format encodes each wall as a series of (count, x-increment) segments. The renderer draws exactly two wall edges per scanline using EOR delta plotting. Multiple paths would require replacing the single left/right wall model. Options:

- **Segment list per scanline:** store multiple (left, right) pairs per Y row. The renderer would iterate through segments instead of reading two fixed values. The RLE format would need to encode segment starts/ends.
- **Tile map:** replace the wall system entirely with a character-based tile map. Simpler data format but loses the smooth diagonal walls and would need a completely new renderer.

### Standalone landscape segments

Floating islands, pillars, or isolated walls cannot be represented in the current two-wall model. Would need:
- A separate "obstacle" layer rendered after the main walls
- Each obstacle defined as a rectangular or polygon region
- Particle collision against obstacle bounds in addition to the wall checks in `particles_update_and_draw` (`thrust.6502:6560-6564`). Ship collision is pixel-based, so a drawn obstacle would be detected for free.

### Disconnected caverns

Use the existing two-wall RLE plus the [teleporter](#completed) system to fake a network of separate cave systems inside one level. A run of rows where `left_wall == right_wall` (zero-width corridor) reads in-game as a solid rock band — the player can't fly through it. After that band the walls re-open into a fresh chamber that is unreachable by flight but can be entered by stepping on a teleporter pad whose destination checkpoint sits inside the new chamber.

Combined with [Y-banded level parameters](#completed), each chamber can have its own gravity sign, palette, etc., so the chambers feel like distinct sub-levels rather than just disconnected rooms with the same physics. Layout becomes a hub-and-spokes topology:

- **Surface / hub band:** flyable terrain with one or more outbound teleporters.
- **Solid divider:** a band of rows with `left == right` walls — visually a continuous rock layer.
- **Sub-cavern:** new walls open out, gravity may invert via a Y-band override, with its own pickups / objects / return teleporter.
- **Repeat:** stack multiple dividers for a multi-room level.

**Why this is a cheap way to expand worlds:**
- No engine work beyond what has shipped (RLE, teleporters, Y-bands, rock-band export).
- The Y axis allows many thousands of rows; a divider band costs a couple of RLE segments per wall.
- Object count is the more likely pressure, since each cavern needs its own pads, switches and hazards. Every object is visited every frame.

**Editor support to add:**
- Better navigation to teleporter destinations. The wiring line exists but doesn't help with off-screen targets. A pan-to-destination key (`Enter` with a pad selected) was proposed in the [teleporter plan](plan-teleporter.md) but not built.
- Optional "go to next cavern" navigation in the editor: sort caverns by Y, shortcut keys to jump the camera between them.
- Validation: warn if a cavern has no outbound teleporter (player would be trapped) or no inbound teleporter (cavern would be unreachable).

**Composes well with:**
- [Metroidvania structure](#metroidvania-structure) — gated upgrades unlock teleporters into new caverns.
- [Switches & triggers](#switches--triggers-follow-ups) — switches in cavern A enable a teleporter in cavern B, sequencing exploration.
- [Keys](#keys) — teleporters that need a key to activate, found in another cavern.

Respawn uses a player-tracked active checkpoint (`_LAST_USED_CHECKPOINT`, see [Completed](#completed)), so dying inside a sub-cavern respawns inside it. The pod-carry anti-cheat uses a per-segment watermark (`deepest_checkpoint_visited`) that resets on teleport.

**Status of the underlying primitives:**

The editor exports rock bands. `_clamp_converging_walls` keeps any contiguous run of rows where the painted walls touch (`left == right == X`), pins them to one X (zero delta across the band), and carries on encoding into the next open cavern. Encoding stops one row past the last open row so the decoder's `$FF, $00` terminator freezes the walls on a closed row, not mid-cavern. Round-trip verified: open / band / open / closed bottom decodes identically, and the existing 6-level export is unchanged. The editor's Shift+click "pinch" tool (wall mode) paints `L = R` rows directly.

Band detection is **sticky**: once a row enters a band (painted gap `<= 1`), following rows with gap `<= 1` snap to the band's entry X even if the painted X drifts. The line tool paints each wall independently, so a hand-drawn band can converge at a slightly different X on each row; without the snap that would render as wobble inside solid rock. The band ends at the first row whose gap re-opens (`> 1`).

Caveats and follow-ups:

1. **Seg1 constraint (engine).** The RLE decoder starts segment 1 with a hardcoded 255-row counter, so the first 255 rows of each wall follow one linear delta. Divider bands must sit below row 255. See [Engine constraints](#first-255-terrain-rows-are-fixed).
2. **Transition rows (to verify in play).** Rows where walls snap open → `left == right` → open are the most likely place for EOR artefacts. The clamp stops one wall crossing the other's previous position, so it should be safe; if a transition glitches, converge over a couple of rows instead of snapping.
3. **Editor visualisation.** Rows with `right - left <= 1` between the first and last open rows are drawn as solid rock, so bands are visible while painting.

---

## New mission types

The current game loop is: collect pod, escape through ceiling, destroy reactor (optional). New mission types would require:

| Mission | Requirements |
|---------|-------------|
| Collect the pod | Already implemented |
| Land safely | Add landing pad object type; detect ship velocity < threshold and angle near vertical when touching pad |
| Collect and deliver | Track cargo state (empty/carrying/delivered); add delivery zone object type |
| Mission briefing | Text display before level start; could reuse the existing message rendering (`write_message`, `thrust.6502:4179`) |
| Mid-mission popup | Pause game, overlay text, resume on keypress |
| Keys | Pickup objects that arm one or more switches when collected; lookup integrates with the existing wiring table |

### Rescue NPCs

Little characters scattered around the level — civilians, stranded miners, survivors — that the player can pick up with the tractor beam (same mechanism as the pod) for a cash bonus. Like *Choplifter* or *Airlift*: fly down, hover over the NPC, suck them up, fly them home. Cash from rescues funds ship upgrades between missions.

**Implementation notes:**
- NPCs are a new object type with their own sprite. They stand on terrain (or walk back and forth between two points for a bit of life)
- Tractor beam already tethers objects — the code path at `update_pod_tractor_beam` (`thrust.6502:5205`) is hardcoded to object 0, so either extend that to iterate other pickup-type objects, or use a simpler "proximity pickup" model where NPCs vanish when the ship hovers close enough
- Each NPC must be delivered to a drop-off zone (existing base, or a dedicated rescue pad) for the bonus to register — encourages full round trips, not just grab-and-dump
- Limit on carry capacity (one at a time? or a counter?) adds a risk/reward dimension — do you go for more rescues or cash in what you have?
- If carrying multiple NPCs conflicts with the single-pod constraint, start with "one rescue at a time"

### Keys

Generic doors (`OBJECT_door = $11`) and the switch wiring table both shipped — see [Completed](#completed). The remaining piece is collectible keys that *arm* a switch on pickup, so a designer can require "find the key, then shoot the switch" rather than just "shoot the switch."

**Implementation sketch:**
- New `OBJECT_key` type with a small sprite. Contact with the ship destroys the key (existing `destroy_object` path) and sets a per-level "keys held" bit field.
- New switch action `requires_key` (or a per-switch flag on existing actions): on trigger, check the bit field — if the matching key bit is unset, the action no-ops and emits a "locked" feedback (sound / brief sprite flash).
- Editor: pair keys to switches via the same wiring UX, or via a tag/colour ID so multiple switches can share one key.
- Composes with [disconnected caverns](#disconnected-caverns) and the [Metroidvania structure](#metroidvania-structure) — keys gate teleporters, teleporters gate keys, etc.

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
- Horizontal doors (the `flat_window` shape of `OBJECT_door` $11, opened by a wired switch) act as barriers that temporarily hold back the water, buying the player time — but they eventually burst or leak
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

The tractor beam check in `update_pod_tractor_beam` (`thrust.6502:5209`) reads `level_obj_flags` without an `,X` index, hardcoding it to object 0. All pod physics use single-instance variables. The level editor export enforces this by sorting type $05 first. See [Support for multiple pods](#support-for-multiple-pods-per-level) for what changing this would entail.

### Support for multiple pods per level

The game supports one pod (type $05) per level. Besides the unindexed `level_obj_flags` read above, all pod physics and rendering use single-instance variables (`pod_xpos_INT`, `pod_ypos_INT_HI`, `pod_tethered_flag`, etc.), not arrays.

**To support multiple pods would require:**
- Changing `update_pod_tractor_beam` (`thrust.6502:5205`) to use indexed access (`level_obj_flags,X`) with the current pod's object index stored in a variable
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

- **Configurable switches & triggers** (`_SWITCHES`, SWRAM build). Switch hits are dispatched through a per-level wiring table instead of the `level_number`-keyed door routines. The editor exports five parallel arrays per level, one row per wiring entry (`level_N_switch_obj_indices`, `_target`, `_action`, `_arg_a`, `_arg_b`; `$FF`-terminated, 8 rows max). When a player bullet hits a `$07`/`$08` switch, `try_dispatch_switch_action` walks the table and fires every row for that switch in order (multi-trigger, "Option F": one switch, several actions). Each row has a refractory byte in `level_switch_state`, set to `$14` (20 frames, ~0.6s) on firing and counted down by `tick_switch_logic`. Unwired switches fall back to the legacy `door_switch_counter_A` latch, which still exists and is drained each frame. Actions in `action_jump_table`: `destroy`, `pulse_door` (see doors below), `set_param` (write `arg_b` into obj_data slot `arg_a`), `xor_param` (XOR the slot with a mask: laser phase/duty, well sign, etc.), and `set_disabled` / `clear_disabled` / `toggle_disabled`. `set_alive` / `clear_alive` / `toggle_alive` (`$01..$03`) remain in the engine but are hidden in the editor; `$0B..$0F` are reserved. `OBJ_flag_disabled` (`$10`) keeps an object drawn and shootable but suspends its behaviour (gun fire, laser beam, mine motion and contact, well pull, teleporter warp); mines use a per-mine `bobbing_mine_local_tick` so a disabled mine freezes in place. Editor: inspector wiring list per switch (Action / Target ref with `Pick` / action args, Delete, "+ Add wiring"), orange wiring lines with arrowheads to each target, export validation of dangling or pod targets. Phases A (scaffolding), B (editor wiring), C (dispatcher + alive/destroy), then set/xor_param, multi-trigger and the disabled trio. Plan: [`plan-switches-and-triggers.md`](plan-switches-and-triggers.md). Follow-ups: [cycle_param, hostile-bullet triggers, predicates](#switches--triggers-follow-ups). Non-SWRAM CRC still `6389c446`.
- **Generic doors object** (`OBJECT_door = $11`, SWRAM build). One editor-placeable object type replaces the hardcoded `level_3/4/5_door_logic` routines. Each door has an anchor (X, Y), shape (`slot` / `notch_v` / `flat_window`), width (rows), max carve depth, and a packed obj_data slot 0: bit 7 = side, bit 6 = open direction (flat_window only), bits 0-1 = shape. Three render paths: `render_slot` (rectangular hole), `render_notch_v` (V-shaped pinch; also auto-carves the matching V-recess into the opposite wall), and `render_flat_window` (rows open progressively along Y, top-down or bottom-up). `tick_doors` runs each door's state machine, with an explicit `door_phase` (opening / holding / closing) so it can't bounce mid-close. Opened by the `pulse_door` switch action; a re-trigger during hold re-latches the timer. The original doors (engine `level_number` 3/4/5, i.e. editor levels 4-6) were migrated to wired switch + door pairs. In the SWRAM build `tick_door_logic` now just jumps to `tick_doors`; the legacy per-level routines are still assembled but unreachable (they stay live when `_SWITCHES = FALSE`, anchoring the CRC). Editor: shape-accurate previews (closed fill + open outline), drag handles for height (top/bottom) and depth (outer edge), direction arrow, door pictogram in the palette, and per-shape inspector fields (Shape, Direction or Wall, Opens for flat_window, Height, Open depth). Commit series D1 (slot + framework), D2 (notch_v + pulse_door re-latch), D3 (flat_window + open direction).
- **Editor UI overhaul — right-pane inspector + sprite palette** (tooling, no engine impact). A fixed 300px right-hand pane replaces the overloaded status bar and the right-click placement menu: a schema-driven inspector on top (40%) and a palette below (60%). Each selection (level when nothing is selected, band, checkpoint, object by type) maps to a list of `Field`s with `kind` ∈ `byte`/`signed_byte`/`word`/`colour`/`enum`/`ref`/`readonly`/`header`/`button`. Numeric fields use a `-`/`+` spinner (Shift = `shift_step`); enums use ◄/► steppers. Clicking a numeric value starts text entry (decimal, `$`/`&`/`0x` hex, signed), which suppresses global shortcuts. Colour fields are an inline 8-swatch row plus an optional inherit cell. Refs (teleporter destination, switch targets) have a `Pick` button that arms a one-shot canvas click. Placement: click a palette tile to arm, left-click on the canvas drops one and disarms (Shift keeps it armed); door, teleporter and gravity well get pictogram tiles. Wall mode gained a Shift+click pinch tool (`L = R`, drag to extend), a dotted crosshair, and a red/blue row highlight. The status bar shows mode / level / file / `X=`/`Y=` / `L=`/`R=` at the cursor row plus a contextual hint. Plan: [`plan-editor-ui-overhaul.md`](plan-editor-ui-overhaul.md). **Deferred:** slider widget; one schema-driven hotkey dispatcher replacing the legacy `_adjust_selected_*` handlers (keys still go through those); Tab / Shift+Tab focus cycle; red flash on out-of-range commit; drag-to-place; palette tiles for checkpoint/band creation (right-click still creates); draggable divider and resizable pane; removing the dead `obj_menu` code; multi-select; inspector tabs; search/filter; batched undo; level-properties dialog.
- **Last-used checkpoint respawn** (`_LAST_USED_CHECKPOINT`, SWRAM build). Replaces the engine's height-based checkpoint scan with a player-tracked active index. Two persistent ZP bytes (`active_checkpoint_index` at `$00AA`, `deepest_checkpoint_visited` at `$00AB`) sit outside the ZP-clear range so they hold across deaths; both reset to `INITIAL_CHECKPOINT` (`$00`) on level start in `initialise_level_pointers`. Per-frame `update_active_checkpoint` walks bidirectionally — retreats while `midpoint_y < cp[active-1].y`, advances while `midpoint_y > cp[active+1].y` — and bumps the deepest watermark on each advance. `level_reset` simplifies to `LDY active_checkpoint_index; JMP active_checkpoint_loaded` (historical scan and pod-flag direction flip both bypassed). Respawn-with-pod rule at the load site: if `cp[active].y` is above death Y, bump Y to `min(active+1, deepest_visited)` (anti-cheat, prevents free upward travel via death loop); whichever phase landed Y, drop the pod if Y equals `deepest_visited` (matches original game's "respawn at the bottom drops the pod" feel, applied to the segment-local watermark instead of `cp[size-1]`). Teleporter warp writes both trackers to the destination index so the watermark cap can never reference a checkpoint the player hasn't actually been to — fixes the disconnected-caverns case where dying in a sub-cavern would have matched a checkpoint above the divider band. Editor exports checkpoints sorted ascending by Y so index 0 is always the topmost spawn (level-start anchor); teleporter `obj_data_0` indices are remapped through the sort permutation. Plan in [`docs/plan-respawn-logic.md`](plan-respawn-logic.md).
- **Teleporter pads** (`_TELEPORTER`, SWRAM build, type `$10`). One-way warp pads that send the ship to one of the level's checkpoints (destination index in obj_data slot 0). `update_and_draw_all_objects` skips the sprite plot and calls `teleporter_emit_debris` (outward debris on a per-pad cadence, offset by `TELEPORTER_CENTRE_X/Y_OFFSET` to centre on the pad) and `teleporter_check_ship_contact` (AABB |dx| < 5 chars, |dy| < 8 px; refused while the pod is tethered or lifted). A hit latches `teleporter_pending_index`; `teleporter_dispatch_pending` runs at end of frame and calls `teleporter_perform_warp`, which writes the destination into `active_checkpoint_index` and `deepest_checkpoint_visited`, clears `level_reset_with_pod_flag`, plays the teleport-out animation and `enter_orbit_sound`, resets the stack and `JMP level_retry`. (The original midpoint-nudge approach was replaced when last-used-checkpoint respawn landed.) `teleporter_just_warped` / `teleporter_overlap_this_frame` stop re-triggering while the ship is still on a pad. Editor: palette pictogram, inspector Destination ref with `Pick`, `[`/`]` cycle destination, cyan ring plus wiring line and arrowhead to the destination checkpoint. A placeholder 12×8 sprite keeps the sprite tables aligned but is never plotted. Plan: [`plan-teleporter.md`](plan-teleporter.md).
- **Bobbing mines** (`_BOBBING_MINES`, SWRAM build, types `$0E` vertical and `$0F` horizontal). Passive sine-wave hazards with `phase` (slot 0) and signed `amplitude` (slot 1); slot 2 holds the previous offset. One cycle per 256 frames (~7.8s at ~33 frames/s), from a 256-entry signed Q.7 sin table indexed by `(phase + bobbing_mine_local_tick[X]) & $FF`. The per-mine tick (originally the global `level_tick_counter`) is cleared at level start and frozen while the mine is disabled. `update_bobbing_mine[_horizontal]` runs per mine per frame in `update_and_draw_all_objects` and applies `new_offset − slot_2` to `level_obj_pos_Y` (16-bit) or `level_obj_pos_X` (8-bit, wraps). Bullets destroy mines via `check_generic_destructible` → `destroy_object`. Ship contact is an AABB test in `check_planet_explode_trigger` (`do_mine_ship_contact_test`) that destroys the mine and sets `plot_ship_collision_detected = $FF` so both explode. 12×12 spike-ball sprite made with `sprite_codec.py` / `sprite_editor.py`; a 1×4 gravity-well placeholder sprite was added to keep the tables aligned. Editor: palette tiles, amplitude bar, inspector Amplitude/Phase; `[`/`]` amp ±1 (Shift ±10), `,`/`.` phase ±1 (Shift ±8). **Note:** the contact thresholds (`|dx| < 5` chars, `|dy| < 11` px) were tuned by feel; revisit if either sprite changes size. Plan: [`plan-bobbing-mines.md`](plan-bobbing-mines.md).
- **Y-banded level parameters — gravity and palette** (`_Y_BANDS`, SWRAM build). Per-level sorted list of Y thresholds, each with a gravity byte and optional landscape / object colour overrides (`$FF` = inherit the level default). `update_active_band` runs once per frame: it reseeds `gravity_FRAC` / `gravity_SIGN` from the level base (applying `reverse_gravity_flag`), pre-fills the colour targets with level defaults, then applies the deepest band whose Y is at or above the player (`band_y_HI` / `band_y_LO`, terminated by `$FF` in the high byte). Band gravity is sign-extended (bit 7 → `gravity_SIGN`), so `$80..$FF` give upward gravity; level-base gravity is sign-extended too, so negative base gravity works. Respawn runs the spawn Y through `update_active_band` before the orientation test, so dying in a reverse-gravity band respawns the right way up. The palette is only re-applied when the active band index changes (`band_current_active_index`), so `hide_landscape` / `show_landscape` can still drive it between transitions; `level_reset` invalidates the cache so the respawn animation already uses the band colours. Editor: Band mode (`B`), draggable full-width lines, inspector fields, `[`/`]` or `,`/`.` step gravity ±1 (Shift ±$10), `K`/`J` cycle the colour overrides (`inherit → 1..7 → inherit`), signed gravity on band labels. Exporter sorts bands by Y and emits two colour-override arrays alongside the gravity array. Other overrides (X-wrap, hazard flags, blending) deferred. Non-SWRAM CRC still `6389c446`.
- **Generic per-object extra-data slots** — `level_N_obj_data_0/1/2`, with each object type interpreting the slots itself (slot 0 = gun_aim; slots 1/2 = laser dx/dy or well radius/strength). Laser and well code share the slot 1/2 lookups via separate SMC sites; the two well-specific lookup tables were dropped. SWRAM build shrank by 256 bytes; non-SWRAM CRC remains anchored at `6389c446`. Adding a new object type with config bytes is now a code change only — no new export array, no new SMC patch, no new lookup table.
- **Lasers draw in object colour** — beam now uses `OBJECT_COLOUR_BYTE` (`$FF`, logical colour 3) instead of `hostile_bullet_pixel_byte` so it reads as part of the level palette. Ship-vs-pixel collision still works (any non-zero pixel under the ship triggers it).
- **Gravity well** (`_GRAVITY_WELL`, SWRAM build, type `$0D`). `apply_gravity_wells_to_force`, called from `ship_input_thrust_calculate_force` after the constant-gravity add (same tick gating), walks the objects; for each enabled well with the ship midpoint inside its diamond (`r = 2|dx| + |dy|` < radius; the 2× makes the diamond pixel-square), it adds `sign(dx)·pull` and `sign(dy)·pull` to `force_vector{x,y}`, where pull is the high byte of `strength × (radius − r)`. Per-instance `radius` (slot 1, effectively 1..127; 0 = inactive) and signed `strength` (slot 2; negative = repulsor). A debris ring (`well_emit_debris_particle`) visualises the field. The object loop skips wells entirely (no sprite, no collision). Editor: centre dot plus diamond (blue pull, red repulsor), radius drag handle, palette pictogram. Plans: [`plan-gravity-well.md`](plan-gravity-well.md), [`plan-gravity-well-debris.md`](plan-gravity-well-debris.md). Follow-ups in [main body](#gravity-well-follow-ups).
- **Timed laser turrets** (`_TIMED_LASER`, SWRAM build, types `$09..$0C`). Four orientations, replacing the old heavy-turret slot. The beam is XOR-drawn with Bresenham `draw_line`, so ship-vs-pixel collision catches it. Per-laser state: `OBJ_flag_laser_beam_drawn` (bit 2 of `level_obj_flags`) plus cached `obj_laser_prev_screen_x/y`; an unchanged beam skips the erase/redraw. Config: `gun_aim` low nibble = phase (×8 frames), high nibble = duty (×4+4 frames), period fixed at 128 frames; beam endpoint `(dx, dy)` in obj_data slots 1/2. Editor: drag the beam tip, inspector phase/duty/dx/dy. Plan: [`plan-laser-endpoint.md`](plan-laser-endpoint.md). Follow-ups in [main body](#timed-lasers-follow-ups).
- **Thrust particles from ship exhaust** (`_THRUST_PARTICLES`, SWRAM build) — debris particles spawned at the ship exhaust point with angle-derived velocity and random spread.
- **Disabling X wrap underground** (`_NO_WRAP_UNDERGROUND`, SWRAM build, enabled). Per-level Y threshold (`level_no_wrap_y_table_LO/HI`; `$FFFF` = always wrap) below which `check_x_wrap` in `update_window_and_terrain_tables` skips the X wrap and instead clamps `window_scroll_x` so the window can't scroll below `window_xpos_INT` = 3. The clamp works around the left-wall lookup breaking at small window X underground (the right wall filled the screen); right-side behaviour is unaffected. Editor: draggable no-wrap line (right-click places / removes in wall mode) and the No-wrap Y inspector field. A proper fix for low window X belongs with any [16-bit world X](16bit-world-x-plan.md) work.

### Investigations

- **Test level made.** Sandbox level for experimenting with new features, edited via `tools/level_editor.py` and round-tripped through `--import` / Ctrl+S.
- **Landscape drawing** — documented in `docs/landscape-drawing.md`. RLE delta-compressed terrain with two interleaved decoder triples per wall; 256-byte circular wall buffers at $0400/$0500; EOR-based incremental rendering; half-resolution vertical rendering.
- **Ship dynamics** — documented in `docs/ship-physics.md`. Midpoint-based physics; one-frame-behind Euler integration; Q7.16 X force, Q7.8 Y force, Q8.16 X position, Q16.8 Y position; tether modelled as a rigid rod with angular velocity and damping; thrust halved when pod attached.
- **Raster timing / cycle budget.** Two SWRAM-only debug flags exist. `_DEBUG_RASTERS` (off by default) enables the `SET_BG_COL` macro, which writes the background palette entry (`raster_set_bg`) at the start and end of key routines so their cost shows as colour bands. `_DEBUG_FRAME_TIME` (on by default) shows the centiseconds elapsed per game frame in the status bar. The game frame is at least 3cs (60,000 cycles, ~33 frames/s); the physics is tuned to that rate. The IRQ handler is `irq1_handler` (`thrust.6502:5943`), which tells vsync from Timer1 via `irq1_timer1_signal`. Detailed costings: [`landscape-draw-performance.md`](landscape-draw-performance.md), [`sprite-draw-performance.md`](sprite-draw-performance.md).
- **Slowest code paths.** `landscape_draw` (`thrust.6502:933`) covers 111 scanlines: ~11,600 cycles static, ~25,000 typical (~42% of the 60,000-cycle game frame). Others: `particles_update_and_draw` (`thrust.6502:6489`) updates and redraws all 32 particle slots; `update_objects_loop` in `update_and_draw_all_objects` (`thrust.6502:1651`) visits every level object; ship plotting XOR-draws one of 17 rotation frames (plus shield) with clipping.
