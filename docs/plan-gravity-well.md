# Plan: gravity well object

**Status:** done (commits `0312d67`..`c3f4543`, plus the debris visualisation in [plan-gravity-well-debris.md](plan-gravity-well-debris.md)). Open follow-ups are listed in `docs/ideas.md` under "Gravity well follow-ups".

An invisible object type that, while the ship is inside its radius, adds a radial pull (or push) to the ship's force vector. Centre, radius and strength are authored per instance in the level editor. SWRAM-only, gated by `_GRAVITY_WELL` (`thrust.6502:40`), so the canonical non-SWRAM CRC `6389c446` is unaffected.

## Design summary

- **One object type, signed `strength` byte.** Positive = pull (well), negative = push (repulsor). Pull and push share the same code path; only the sign of the multiply result differs.
- **Linear ramp inside the radius**: no divide, no `1/r²`. Pull magnitude = high byte of `strength * (radius − r)`, zero outside. Maximum at the centre, no singularity.
- **Pixel-square Manhattan distance**: `r = 2·|dx| + |dy|`. One world X unit (a character, 4 pixels) is twice the height of one world Y unit (2 pixel rows), so doubling `|dx|` makes the region a diamond that is square on screen. No 16-bit square or sqrt.
- **Ship only.** Bullets, thrust particles and the pod's own integrator are not affected (follow-ups in `ideas.md`). The pull is applied to the `midpoint_*` reference point, which is the ship+pod centre of mass when tethered, so tethered physics stays consistent.
- **Adds to the constant gravity**, it does not replace it. A well pulling upward against downward gravity lightens the ship before reversing it.
- **Honours `OBJ_flag_disabled`**: a disabled well applies no force and emits no debris (used by the switches system).

## Object-type slot

```
OBJECT_gravity_well                 = $D        ; thrust.6502:127, inside IF _GRAVITY_WELL
```

Per-type table entries (all inside `IF _GRAVITY_WELL`):

| Table | Value | Line |
|-------|-------|------|
| `obj_type_width` | `$04` | `thrust.6502:1434` |
| `obj_type_height` | `$04` | `thrust.6502:1450` |
| `obj_type_explosion_particle` | `$00` (not destructible) | `thrust.6502:1467` |
| `obj_type_score_value` | `$00` | `thrust.6502:1484` |
| `object_type_cull_size_table` | `$44` | `thrust.6502:2350` |

The well is never drawn and never bullet-tested: `update_and_draw_all_objects` jumps straight to `next_object` for type `$0D` (`thrust.6502:1670-1680`). A placeholder `obj_sprite_data_A/B_gravity_well` exists in `tools/output/object_sprites.asm` only to keep the sprite tables indexed by type. Giving the well a plotted sprite would make it lethal through ship-vs-pixel collision, which is why it is visualised with debris particles instead.

## Data model per instance

The well uses the generic per-object data slots shared with lasers, mines, teleporters and doors. Position comes from the normal `level_N_obj_pos_X` / `_Y` / `_Y_EXT` arrays.

| Slot | Array | Meaning for a well |
|------|-------|--------------------|
| 0 | `level_N_obj_data_0` | unused (exported as 0) |
| 1 | `level_N_obj_data_1` | radius, unsigned, 1..127. 0 = inactive. |
| 2 | `level_N_obj_data_2` | strength, signed −127..+127 |

Slots 1 and 2 are found through `level_obj_data_1_lookup_LO/HI` and `level_obj_data_2_lookup_LO/HI` (`thrust.6502:10970-10988`), which live in SWRAM next to the laser code and are shared with the laser dx/dy SMC sites. No well-specific arrays or lookup tables were added, so the RAM cost is only the code and scratch bytes.

The radius must stay at or below 127: `radius − r` is passed to `multiply_signed_8x8` as a signed byte, so a larger value would flip the pull's sign near the centre. The editor's drag handle clamps to 0..127.

## Physics integration

`ship_input_thrust_calculate_force` (`thrust.6502:4267`) adds gravity only on 6 of every 16 ticks (`level_tick_counter AND $0F` in {0, 3, 5, 8, B, D}). `apply_gravity_wells_to_force` is called straight after the gravity add, inside the same tick gate (`thrust.6502:4315`), so the wells share gravity's update rate (about 12 times a second at the ~33Hz game frame rate).

`apply_gravity_wells_to_force` (`thrust.6502:11655`) walks the level's object list up to the `$FF` terminator, using its own SMC sites (`well_load_obj_type`, `well_load_obj_pos_x/_y/_y_ext`, `well_load_radius`, `well_load_strength`) patched in `initialise_level_pointers` (`thrust.6502:7318-7348`). For each object of type `OBJECT_gravity_well` that is not disabled and has a non-zero radius:

1. Save radius, strength and the well's world position into `well_*_save` scratch bytes.
2. Run the debris emit gate (see the debris plan). This happens whether or not the ship is in range.
3. `dy = obj_Y − midpoint_ypos` as a 16-bit subtract; skip the well if the result is outside −128..+127.
4. `dx = obj_X − midpoint_xpos_INT` as an 8-bit subtract (world X wraps, so two's complement gives the signed difference).
5. `r = 2·|dx| + |dy|`; skip if either the doubling or the add overflows 8 bits, or if `r ≥ radius`.
6. `pull = hi(strength * (radius − r))` via `multiply_signed_8x8`. Skip if the high byte is zero.
7. Add `sign(dy) * pull` to `force_vectory_FRAC/INT` and `sign(dx) * pull` to `force_vectorx_FRAC/INT`, each as a sign-extended 16-bit add. The full `pull` is applied to each axis; there is no per-axis split.

## Maths

- Region: `2·|dx| + |dy| < radius`. Reach is `radius` world Y units vertically and `radius/2` world X units horizontally, which are the same distance on screen.
- Magnitude: `hi(strength * (radius − r))`, in 1/256ths of `force_vector`. Strength 60 at radius 40 gives at most `hi(60 * 40) = 9`; the maximum possible is `hi(127 * 127) = 63`. Small negative products floor to −1 rather than 0, so a repulsor always pushes slightly inside its radius.
- Direction: the sign of each axis difference, applied at full magnitude. Two consequences of this:
  - On the diagonals the combined pull is about √2 stronger than on the axes.
  - A zero difference counts as positive (`BPL`), so a ship exactly level with or exactly above/below the centre is still pushed in +X or +Y on that axis, and at the exact centre it is pushed down-right. Both points are listed as follow-ups in `ideas.md` (per-axis scaling, centre-case symmetry).

## Cost

`multiply_signed_8x8` is about 220-380 cycles (8 shift-and-add iterations). Per gravity tick:

- each non-well object in the list: ~25 cycles to test and skip;
- each well with the ship out of range: ~100 cycles plus any debris emit;
- each well with the ship in range: ~450 cycles plus any debris emit.

With a handful of wells this is well under 1% of the 60,000-cycle game frame. The debris emit is the larger cost; see the debris plan.

## Editor support (`tools/level_editor.py`)

- Constants: `OBJECT_GRAVITY_WELL = 0x0D`, defaults `GRAVITY_WELL_DEFAULT_RADIUS = 40`, `GRAVITY_WELL_DEFAULT_STRENGTH = 60` for newly placed wells.
- Model fields: `well_radius`, `well_strength` on the object dict. Export writes them into `level_N_obj_data_1` / `_2`. Import reads the `obj_data` arrays, falling back to the older `level_N_well_radius` / `level_N_well_strength` arrays if present.
- Rendering: `_render_gravity_well` draws a centre dot and the diamond outline (`_well_screen_geometry` uses `r/2` world units on X and `r` on Y to match the game). The outline is blue for pull, red for push. The palette shows a pictogram, since the well has no sprite.
- Selection: wells are picked by their centre dot (`_hit_test_well`), because the normal sprite hit test skips them.
- Radius: drag the handle on the right-hand vertex (`_set_well_radius_from_screen`, clamped 0..127), or edit the Radius field in the properties panel.
- Strength: `[` / `]` nudge by −1 / +1 (Shift = ±10), clamped −127..+127; also editable in the properties panel.

## Things to watch out for

- **Radius ≤ 127.** See the data model. The properties-panel Radius field currently allows up to 255, which the runtime does not handle.
- **Visual centre vs resting point.** The pull targets `midpoint_*`, not the ship sprite origin, so the ship settles slightly off the plotted well centre (and further off when towing the pod).
- **Bullets, particles and the pod** are not pulled. Adding them means hooking `particles_update_and_draw` per particle per well, which is a separate cost.
