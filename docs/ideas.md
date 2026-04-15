# Ideas / Future Work

Working title: **Thrust Next** — essentially Thrust meets Exile.

---

## Investigation tasks

### Make a test level

Use the level editor (`tools/level_editor.py`) to design a sandbox level for experimenting with new features. Export via `--import`/Ctrl+S and build with BeebAsm. The editor already supports terrain editing, object placement, and round-trip import/export.

### Understand the landscape drawing routine

Now documented in `docs/landscape-drawing.md`. Key points:
- RLE delta-compressed terrain with two interleaved decoder triples per wall
- 256-byte circular wall buffers at $0400/$0500
- EOR-based incremental rendering (only changed columns are redrawn each frame)
- Half-resolution vertical rendering (every other pixel row)

### Understand the dynamics implementation

Now documented in `docs/ship-physics.md`. Key points:
- Midpoint-based physics: all forces act on the centre of mass of the ship-pod system
- One-frame-behind Euler integration
- Q7.16 for X force, Q7.8 for Y force, Q8.16 for X position, Q16.8 for Y position
- Tether modelled as a rigid rod with angular velocity and damping
- Thrust magnitude halved when pod is attached (5 right shifts vs 4)

### Raster timing / cycle budget

No raster timing or cycle-counting infrastructure currently exists in the code. The IRQ handler (`thrust.6502:5296`) distinguishes vsync from Timer1 via `irq1_timer1_signal` but there are no budget annotations.

**To instrument:** set up Timer1 to fire at a known point in the frame, toggle a palette register or border colour at the start/end of key routines (landscape_draw, particles_update_and_draw, draw_player). This would reveal how much of each frame is spent on each system.

### Identify slowest code paths

Likely candidates based on code structure:
- `landscape_draw` (line 755): iterates all 73 visible scanlines, computing deltas and EOR-drawing columns
- `particles_update_and_draw` (line 5799): updates and redraws all 32 particles every frame
- `update_objects_loop` (line 1393): iterates all level objects for visibility, rendering, and collision
- Ship sprite plotting: 17 rotation frames + shield sprite, XOR-plotted with clipping

---

## Particle effects

### ~~Thrust particles from ship exhaust~~ — IMPLEMENTED (`_THRUST_PARTICLES`)

Implemented behind the `_THRUST_PARTICLES` build flag (SWRAM builds). Spawns debris particles at the ship exhaust point using angle-derived velocity with random spread.

---

## New enemy types

### Current enemies

Only gun emplacements exist, in 4 directional variants (types $00-$03). They fire probabilistically using the shared particle pool with type `PARTICLE_type_hostile_bullet` ($03). Gun firing angle is determined by `gun_base_angle` (3 bits from `gun_param`) plus random spread masked by `gun_angle_spread_mask` (2 bits from `gun_param`).

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

---

## Larger levels

### Current limits

- **Y axis:** Q16.8 format supports worlds up to 65535 rows deep. Existing levels use ~700-1500 rows. No hard limit here.
- **X axis:** 8-bit world X (0-255), wrapping at ~$B8-$DC. The visible viewport is 72 columns. World is ~184 columns wide.
- **RLE data size:** each level's terrain is stored as 4 arrays (left/right count + increment). The total size is limited by available ROM/RAM. Current levels use 7-30 segments per wall.
- **Wall buffers:** 256-byte circular buffers. Only 73 rows are visible at once, so 256 entries provide comfortable margin. Not a practical limit.
- **Object count:** terminated by $FF sentinel in the type array. No explicit limit, but all objects are checked every frame for visibility/collision, so very large counts would impact performance.

**Practical approach:** levels can be made significantly deeper without engine changes. Wider levels would require extending the X coordinate to 16 bits, which would touch many parts of the codebase.

---

## Gameplay / level concepts

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

---

## Advanced landscape features

### Current architecture

The terrain is fundamentally a corridor defined by two walls (left X and right X per Y row). The RLE format encodes each wall as a series of (count, x-increment) segments. The renderer draws exactly two wall edges per scanline using EOR delta plotting.

### Multiple / split paths

Would require replacing the single left/right wall model. Options:
- **Segment list per scanline:** store multiple (left, right) pairs per Y row. The renderer would iterate through segments instead of reading two fixed values. The RLE format would need to encode segment starts/ends.
- **Tile map:** replace the wall system entirely with a character-based tile map. Simpler data format but loses the smooth diagonal walls and would need a completely new renderer.

### Standalone landscape segments

Floating islands, pillars, or isolated walls cannot be represented in the current two-wall model. Would need:
- A separate "obstacle" layer rendered after the main walls
- Each obstacle defined as a rectangular or polygon region
- Collision detection against obstacle bounds in addition to wall checks at lines 5871-5874

### Variable wall slopes

Currently walls move by 0 or 1 column per scanline (the increment is applied every row). Steeper slopes are possible (increment > 1 per row), but shallow slopes (< 1 column per row) would require fractional increments. The 8-bit increment already supports this via unsigned wrapping — a value like $80 moves half a column per row on average, but the discrete steps would look jagged. True sub-pixel slopes would need a fixed-point accumulator in the RLE decoder.

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

### Keys and doors

Door switches (types $07 and $08) already exist in the object system. The current implementation likely toggles a terrain section. Extending this to a full key/door system would need:
- Key objects that disappear when the ship touches them, setting a flag
- Door objects that check the flag and open/close terrain sections
- Visual feedback (door animation, key collection effect)

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

### Pod must be object index 0

The tractor beam check at `thrust.6502:4572` reads `level_obj_flags` without an `,X` index, hardcoding it to object 0. All pod physics use single-instance variables. The level editor export enforces this by sorting type $05 first. See the "Support for multiple pods" section below for details on what would need to change.

### Support for multiple pods per level

The game currently only supports a single pod (type $05) per level. The tractor beam activation check at `thrust.6502:4572` reads `level_obj_flags` without an `,X` index, hardcoding it to object index 0. All pod physics and rendering use single-instance variables (`pod_xpos`, `pod_ypos`, `pod_attached_flag`, etc.), not arrays.

**To support multiple pods would require:**
- Changing `update_pod_tractor_beam` (line 4572) to use indexed access (`level_obj_flags,X`) with the current pod's object index stored in a variable
- Adding logic to select the nearest visible pod when the tractor beam is activated
- Either converting pod state variables to arrays (to track multiple attached/detached pods) or limiting the player to interacting with one pod at a time while allowing multiple to exist in the level

### First 255 terrain rows are fixed

The game's dual-triple terrain decoder initialises both triples with a hardcoded counter of $FF (255). The first 255 rows of each wall always use a single uniform increment (segment 1). Edits within this region cannot be represented in the RLE format. The level editor enforces this constraint in the encoder.

### 32 shared particle slots

All particle effects (player bullets, enemy bullets, debris, stars, exhaust) share a single 32-entry pool. Player bullets are limited to 4 simultaneous. Adding new particle-based features (thrust exhaust, new weapon types) increases contention for this fixed pool.
