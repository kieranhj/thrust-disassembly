# Plan: 16-Bit World X Coordinates

**Status:** not started. No `_WIDE_WORLD` flag or X high-byte variables exist;
world X is still 8-bit everywhere.

## Context

World X is 8-bit, in character columns (4 pixels each). On the surface,
`update_window_and_terrain_tables` keeps `window_xpos_INT` inside `$01..$B7`:
when it reaches `WORLD_X_WRAP_THRESHOLD` (`$B8` = 256 − 72) every X position is
shifted by `WORLD_X_WRAP_FORWARD` (`+$49`), and when it is `$00` or `$DC..$FF`
it is shifted by `WORLD_X_WRAP_BACKWARD` (`−$49`) (`thrust.6502:175`,
`3362`). Terrain and object positions are not shifted, so the level data has to
repeat itself across the wrap: the unique surface is about `$B7` = 183 columns,
roughly 2.5 screens of the 72-column viewport.

In the SWRAM build `_NO_WRAP_UNDERGROUND` disables the wrap when the player is
below a per-level Y (`no_wrap_y_INT/_HI`); there the window is only clamped at
`window_xpos_INT < 3` on the left, so an underground section can use most of
the 0–255 range but cannot be wider.

16-bit X would allow worlds far wider than this, for the interconnected maps
described in `docs/ideas.md`. It touches most systems; this document lists what
must change, estimates the cost, and identifies the risky parts.

---

## Scope of Change

### Systems Affected

| System | Severity | Location | Notes |
|--------|----------|----------|-------|
| Zero page variables | Medium | thrust.6502 | ~6–10 new bytes |
| World X wrap | **Major rewrite** | `update_window_and_terrain_tables`, thrust.6502:3362–3469 | 16-bit compares and adds for every entity, or removed in favour of hard world edges |
| Window follow | Medium | `compute_x_scroll_speed`, thrust.6502:3277 | `midpoint_xpos − window_xpos` becomes 16-bit; result stays an 8-bit window offset |
| Terrain wall arrays | **Major rewrite** | `terrain_left_wall` $0400, `terrain_right_wall` $0500 | Need high bytes (512 extra bytes, or rearchitect) |
| Terrain RLE decoder | **Major rewrite** | `initialise_landscape` .. `terrain_subtract_xpos_fn`, thrust.6502:1102–1361 | Accumulators become 16-bit; both accumulate and subtract paths |
| landscape_draw | **Major rewrite** | thrust.6502:933–1094 | World-to-screen subtract and clamp become 16-bit; self-mod SBC trick changes |
| draw_terrain (unrolled) | None | thrust.6502:13729 | Takes screen column + width; unchanged |
| Object visibility | Major | `object_visibility_test`, thrust.6502:2286 | 16-bit X subtract; level data gains an X high byte |
| Object collision tests | Major | bullet AABB thrust.6502:1931; fuel tractor 2089; mine contact 1879; teleporter contact 12174 | 16-bit dx with high-byte reject |
| Gravity wells | Medium | `apply_gravity_wells_to_force`, thrust.6502:11761 | dx is 8-bit signed and relies on wrap |
| Doors / terrain carving | Medium | `level_3_door_logic` 3538, `do_level_4_door_logic` 3596, `door_update_one` 12857 | Write 8-bit world X into the wall arrays |
| Particle system | Major | $0600–$07BF | `particles_xpos_INT` needs a high-byte array (32 bytes) |
| Particle movement | Low | `particle_move_index_X`, thrust.6502:6787 | 2-byte add becomes 3-byte with sign-extended dx |
| Particle-terrain collision + cull | Major | `particles_update_and_draw`, thrust.6502:6560–6575 | 16-bit compare against walls; 16-bit world-to-screen |
| Particle spawns | Low | `create_explosion` 6226, `create_new_player_bullet` 8010, `try_gun_fire` 2140, generator debris, `particles_generate_stars` 6830, `create_thrust_particle` 10873, well/teleporter debris | Copy the X high byte |
| Particle-near-player test | Low | `test_particle_X_close_to_player`, thrust.6502:6722 | 16-bit dx |
| Midpoint force integration | Medium | `midpoint_add_force_vector`, thrust.6502:6069 | 3-byte add becomes 4-byte (sign-extend `force_vectorx_INT`) |
| Player position | Medium | `calculate_player_position_from_midpoint`, thrust.6502:6132 | `new_ship_xpos`, `player_xpos`, `old_player_xpos` need high bytes; velocity stays small |
| Pod position | Medium | `calculate_pod_pos` 9987, `attach_pod_to_ship` 5301 | Same pattern as the ship |
| Level reset / checkpoints | Medium | `level_reset`, thrust.6502:7086, 7101 | Reset tables hold 8-bit `window_xpos` / `midpoint_xpos` |
| Ship-to-pod distance | None | `get_distance_ship_to_pod_tractor`, thrust.6502:8181 | Uses window-relative `ship/pod_window_xpos`; unaffected |
| Tether line drawing | None | `calculate_line_coordinates`, thrust.6502:8791 | Window-relative; unaffected |
| Level data + editor | Major | `thrust1/level_data.asm` (non-SWRAM), `tools/output/thrust_levels_export2.asm` (SWRAM, from `tools/level_editor.py`) | New `level_N_obj_pos_X_EXT` arrays, following the Y pattern |

The window-relative coordinates (`player_xdist_in_window_INT`,
`ship_window_xpos_INT`, `pod_window_xpos_INT`) stay 8-bit. Only the places that
convert between world and window coordinates, or compare two world positions,
need 16-bit arithmetic.

---

## Detailed Analysis by System

### 1. Zero Page

New high-byte variables, following the Y naming (`_INT_HI` / `_EXT`):

| New variable | Purpose |
|--------------|---------|
| `window_xpos_EXT` | Window world X high byte |
| `midpoint_xpos_INT_HI` | Midpoint world X high byte |
| `player_xpos_INT_HI` | Ship world X high byte |
| `old_player_xpos_INT_HI` | Previous ship X high byte |
| `pod_xpos_INT_HI` | Pod world X high byte |
| `nearest_obj_xpos_INT_HI` | Nearest object X high byte |
| `current_obj_xpos_EXT` | Current object X high byte (scratch) |
| `new_ship_xpos_INT_HI` | Scratch in `calculate_player_position_from_midpoint` |

`force_vectorx` and `player_velocityx` can sign-extend on the fly rather than
store a high byte.

**Availability:** persistent ZP runs `$0000–$007F` and `$00A1–$00AB`
(`$00A8–$00AB` are now used by `_NO_WRAP_UNDERGROUND` and
`_LAST_USED_CHECKPOINT`). `$0080` upwards is per-routine scratch, heavily
overlaid. `$00AC–$00FB` (80 bytes) is free, which is ample.

### 2. Terrain Wall Arrays — the hardest problem

**Current:** `terrain_left_wall` at $0400 and `terrain_right_wall` at $0500,
256 bytes each, one 8-bit world X per entry, indexed by a circular Y index
(`terrain_window_y_index`).

#### Option A: split LO/HI arrays (recommended)

Keep $0400/$0500 as the low bytes and add `terrain_left_wall_HI` and
`terrain_right_wall_HI` as two more page-aligned 256-byte arrays. Indexing is
unchanged; the cost is 512 bytes of page-aligned RAM.

Low memory is full: $02EF–$03DD holds the four `terrain_draw_table_*` caches
(two 111-entry tables, one per wall, with `_1`/`_3` aliased 17 bytes before
`_2`/`_4`), $0600–$07BF the particle arrays and $07C0–$07FF the sound
parameters. The high-byte arrays have to go elsewhere (see Memory Impact).

#### Option B: keep 8-bit arrays, store window-relative X

The RLE decoder would subtract `window_xpos` as it fills the arrays.

**Pros:** arrays stay 8-bit; landscape_draw's inner loop is unchanged.
**Cons:** every horizontal scroll must adjust all 512 entries (~15c each,
~7,700c per scrolling frame), and positions more than 255 columns from the
window no longer fit. Worse than Option A.

#### Option C: interleaved 16-bit entries

512 bytes per wall, indexed by `Y*2`. Breaks the single-byte circular index;
not worth it.

### 3. landscape_draw (`thrust.6502:933–1094`)

**Current per wall per scanline** (111 scanlines, every other pixel row):

```
LDA terrain_left_wall,Y    ; 4c
SBC #imm                   ; 2c  self-modified to window_xpos-1, entered with C=0
BCS in_range               ; 3c  borrow → clamp to 0
CMP #SCREEN_WIDTH_CHARS    ; 2c
BCC ok                     ; 3c  else clamp to 72
```

About 14c for the conversion and clamp.

**16-bit version:**

```
SEC                        ; 2c
LDA terrain_left_wall,Y    ; 4c
SBC window_xpos_INT        ; 3c
STA temp                   ; 3c
LDA terrain_left_wall_HI,Y ; 4c
SBC window_xpos_EXT        ; 3c
BNE off_left_or_right      ; 2c  $FF → clamp 0, otherwise clamp 72
LDA temp                   ; 3c
CMP #SCREEN_WIDTH_CHARS    ; 2c
BCC ok                     ; 3c
```

About 29c, so ~15c extra per wall: 2 × 111 × 15 ≈ **3,300c per frame**,
about 5.5% of the 60,000-cycle (3 cs) game frame.

Mitigations:

1. Self-modify both immediates (`SBC #lo`, `SBC #hi`) and keep the low result
   in X (`TAX`/`TXA`): roughly 23c, ~2,000c extra per frame.
2. Keep a per-frame copy of the walls already converted for rows whose high
   byte matches `window_xpos_EXT`; not obviously a win given the XOR delta
   scheme already skips unchanged rows' drawing but not their conversion.

### 4. Terrain RLE Decoder (`thrust.6502:1102–1361`)

`terrain_process` runs all four triples (two per wall, writing rows `Y` and
`Y−1`) through `terrain_accumulate_xpos_fn` or `terrain_subtract_xpos_fn` for
each row scrolled. The X accumulator is passed in A and stored in
`terrain_{left,right}_wall_{1,2}_xpos` (in the terrain variable block after
`terrain_process`, not in ZP).

**Current accumulate:**

```
CLC
ADC (terrain_data_x_increment_ptr),Y  ; 8-bit add
```

**16-bit:** the increment can stay a signed byte, sign-extended into the high
byte:

```
LDX #$00
LDA (terrain_data_x_increment_ptr),Y
BPL pos
DEX                                   ; X = $FF for negative increments
.pos
CLC
ADC xpos_LO : STA xpos_LO
TXA
ADC xpos_HI : STA xpos_HI
```

The subtract path needs the mirror image. The X register already carries the
run counter, so the routines' register contract changes. Cost is ~10–15c per
triple per scrolled row: negligible. Each triple gains an `_xpos_HI` byte
(4 bytes), and `initialise_landscape` must clear them.

### 5. World X Wrap (`thrust.6502:3362–3469`)

**Current:** 8-bit tests on `window_xpos_INT` against `$00`/`$DC` and
`WORLD_X_WRAP_THRESHOLD`, then the delta is added to `window_xpos`,
`midpoint_xpos`, `player_xpos`, `old_player_xpos` and all 32
`particles_xpos_INT` (`shift_particles_x_loop`), followed by a fix-up of the
draw-table caches (`wrap_fix_cache_loop`, X = 17..127) for rows where both walls
are clamped to the same screen edge.

With 16-bit X the wrap could become a per-level world width with 16-bit
compares and adds (32 × ~10c extra for the particles, only on wrap frames), or
be dropped for wide levels in favour of hard edges, as `_NO_WRAP_UNDERGROUND`
already does underground. Either way the wrap constants become per-level data.

### 6. Object System

**Level data:** add `level_N_obj_pos_X_EXT` arrays alongside `level_N_obj_pos_Y`
/ `level_N_obj_pos_Y_EXT`.

**Self-modifying loads** (`object_visibility_test`, `thrust.6502:2286`): add a
fourth self-modified load for `level_0_obj_pos_X_EXT,X`, with matching
pointer-table entries in `initialise_level_pointers` (`thrust.6502:7183`).
The other self-modified readers of `level_0_obj_pos_X` need the same:
`apply_gravity_wells_to_force`, `teleporter_emit_debris`, the destroy action
(`act_dest_load_x`), `door_update_one`, and `update_bobbing_mine_horizontal`
(which also writes X back, so its add must carry into the high byte).

**Visibility:** currently `current_obj_xpos_INT − window_xpos_INT` compared
against `object_type_cull_size_table`. With 16 bits, a non-zero high byte of the
difference is an immediate cull.

**Collision tests:** bullet AABB, fuel tractor proximity, mine contact,
teleporter contact and gravity-well dx all take 8-bit X differences; each needs
a 16-bit subtract with a high-byte reject.

### 7. Particle System

Add `particles_xpos_INT_HI` (32 bytes). There is no room in $0600–$07FF, so it
needs a new home. Every particle spawn copies the high byte from its source.

**Movement** (`particle_move_index_X`): add a third byte with the sign of
`particles_dx_INT` (~20c per live particle; up to ~640c with all 32 slots in
use, normally far fewer).

**Terrain collision and cull** (`particles_update_and_draw`, 6560–6575):
`particles_xpos_INT` is compared directly with `terrain_left/right_wall,Y` and
then converted to screen X by subtracting `window_xpos_INT`. Both become 16-bit.

### 8. Ship / Pod / Midpoint Position

**Midpoint force integration** (`midpoint_add_force_vector`): the X add is
`FRAC_LO → FRAC → INT`; add a fourth byte with the sign of
`force_vectorx_INT`.

**Ship position** (`calculate_player_position_from_midpoint`): `new_ship_xpos
= midpoint_xpos + midpoint_deltax` gains a high byte (sign of
`midpoint_deltax_INT`), as do `player_xpos` and `old_player_xpos`.
`player_velocityx` is a small difference and stays 2 bytes.

**Pod position** (`calculate_pod_pos`, `attach_pod_to_ship`): same pattern.

### 9. Distance Calculations

`get_distance_ship_to_pod_tractor` works on `ship_window_xpos` and
`pod_window_xpos`, which are window-relative, so its `BVS` overflow check is
unaffected. The window-relative values are derived from
`player_xdist_in_window_INT` (`midpoint_xpos − window_xpos`, section "Window
follow" in the table), which is where the 16-bit subtract goes.

---

## Performance Impact Summary

Estimates against the 60,000-cycle game frame.

| System | Extra cycles | Frequency | Share of frame |
|--------|--------------|-----------|----------------|
| landscape_draw (2 walls × 111 scanlines) | ~3,300c (~2,000c with self-mod) | every frame | ~5.5% (~3.3%) |
| Terrain RLE decode | ~50c per scrolled row | when scrolling vertically | negligible |
| X-wrap entity shift | ~350c | wrap frames only | negligible |
| Object visibility and collision | ~10c per object | every frame | ~200c for 20 objects |
| Particle movement, cull, terrain test | ~30c per live particle | every frame | up to ~1,000c |
| Midpoint / ship / pod | ~30c | every frame | <0.1% |
| **Typical total** | **~4,000c** | | **~7%** |

landscape_draw dominates; the per-scanline 16-bit subtract is unavoidable with
Option A.

---

## Memory Impact

| Item | Bytes | Location |
|------|-------|----------|
| New ZP variables | ~8 | $00AC+ |
| `terrain_left_wall_HI` | 256 | page-aligned RAM needed |
| `terrain_right_wall_HI` | 256 | page-aligned RAM needed |
| `particles_xpos_INT_HI` | 32 | no room in $0600–$07FF |
| Level data X_EXT arrays | 1 per object | level data |
| Terrain triple `_xpos_HI` | 4 | terrain variable block |
| Code size increase | ~300–500 | various |
| **Total RAM** | **~560 + code** | |

Low memory ($0200–$07FF) is fully allocated: OS vectors, the draw-table caches
at $02EF–$03DD, the wall arrays at $0400–$05FF, particles at $0600–$07BF and
sound parameters at $07C0–$07FF. Options:

- Put the high-byte arrays in sideways RAM. The SWRAM build already runs code
  from bank 4 at $8000–$BFFF (bank 5 holds sprites); SWRAM is as fast as main
  RAM, so the only constraint is that bank 4 is paged in whenever the arrays
  are touched, which is already the case for SWRAM code.
- Shrink the particle pool from 32 to 24 slots, freeing 112 bytes of $0600 –
  not a whole page, so this only helps the particle high-byte array.

This plan is only practical in the SWRAM build.

---

## Level Data and Tooling

### Level data

- Add `.level_N_obj_pos_X_EXT` arrays (one byte per object).
- Terrain RLE increments stay signed 8-bit; add high bytes for the initial X of
  each wall triple.
- Per-level reset/checkpoint tables need X high bytes for `window_xpos` and
  `midpoint_xpos`.
- Only the SWRAM export (`tools/output/thrust_levels_export2.asm`) needs to
  change; `thrust1/level_data.asm` is the non-SWRAM original.

### tools/level_editor.py

- Object X becomes 16-bit in the editor's model and export.
- The canvas needs to scroll horizontally over wide worlds.
- The editor already reads and writes `level_N_obj_pos_Y_EXT`; follow that
  pattern.

### initialise_level_pointers

- Add pointer-table entries for `level_N_obj_pos_X_EXT` and patch the new
  self-modified loads.

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| landscape_draw cost (~3–5% of frame) | **High** | Profile with `_DEBUG_FRAME_TIME`; self-mod both immediates |
| Finding 512 bytes for wall high bytes | **High** | Use SWRAM; map page usage first |
| 8-bit X assumptions in untouched code | **Medium** | Grep every `_xpos_INT`, `obj_pos_X` and `terrain_*_wall` use; the SWRAM features (doors, wells, mines, teleporters, lasers) added many |
| RLE sign-extension bugs | **Medium** | Compare decoded wall arrays against the 8-bit build on existing levels |
| Wrap correctness at 16-bit boundaries | **Medium** | Test with a world just over 256 columns |
| Editor canvas for wide worlds | **Low** | Viewport already scrolls |

---

## Suggested Implementation Order

1. ZP and variable declarations.
2. Memory layout for the wall high bytes and particle high bytes.
3. Terrain wall arrays and RLE decoder.
4. landscape_draw.
5. Window follow and X wrap (or hard edges).
6. Object system: level data, visibility, collision tests, doors, wells.
7. Particle system: high byte, movement, terrain test, spawns.
8. Ship / pod / midpoint position, level reset.
9. Level editor and export.
10. Test with a world just over 256 columns.

---

## Verification

- Gate everything on a new SWRAM-only flag (e.g. `_WIDE_WORLD = (_SWRAM_BUILD
  AND TRUE)`).
- Non-SWRAM build: CRC32 must still be `6389c446`.
- Wide-world test level (> 256 columns): terrain renders correctly past column
  255, wrap or edges behave, every object type is visible and interactable at
  high X, particles spawn/move/collide correctly, and ship-terrain collision
  works.
- Measure landscape_draw before and after.
