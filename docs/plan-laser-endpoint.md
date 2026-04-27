# Plan: per-laser endpoint (length + angle) configuration

Currently each laser uses one of four hardcoded `(dx, dy)` pairs from
`laser_beam_dx_table` / `laser_beam_dy_table` in `thrust.6502`, indexed by
orientation type. The four orientations give visual variety and pick the
barrel corner, but the level designer can't change beam length or angle
per-instance. Goal: store per-instance `(dx, dy)` so each laser's endpoint
is authored in the editor; the four orientation types remain visual presets.

## Decisions confirmed

- **Parameterise as `(dx, dy)`** rather than angle + length — matches what the
  asm needs for `draw_line` and what the editor naturally produces from a
  drag. No sin/cos lookup required at runtime.
- **Mismatched orientation + dx/dy is allowed**, e.g. an `$09 up_right` sprite
  with a beam pointing down-left. Editor lets it through without a warning;
  trust the level designer.
- **`gun_aim` keeps its current 4+4 nibble split** (low = phase, high = duty).
  dx/dy live in their own bytes.
- **Delete `laser_beam_dx/dy_table` from the asm** once the runtime reads
  per-instance values. The defaults the editor stamps onto a new laser
  move into the editor's Python constants.

## Data model

Two new bytes per object slot, signed:

| Symbol                       | Type            | Range            |
|------------------------------|-----------------|------------------|
| `level_N_laser_dx_pixels`    | 8-bit signed    | −128..127 BBC px |
| `level_N_laser_dy_rows`      | 8-bit signed    | −128..127 rows   |

These are parallel to `level_N_obj_pos_X` etc., one byte per object index.
Non-laser slots ignore them, same as `gun_aim`.

**Defaults for unset entries** (existing levels pre-dating these arrays, or new
laser placed in editor): the orientation-type's existing direction —
`(+60, −30)` for `$09`, `(+60, +30)` for `$0A`, `(−60, −30)` for `$0B`,
`(−60, +30)` for `$0C` — so behaviour matches today's build before the user
has touched anything.

## Game changes (`thrust.6502`)

1. Two new SMC sites in `update_one_laser_beam`, modelled on
   `laser_load_object_type` and `laser_load_gun_aim`:

   ```asm
   .laser_load_dx
       LDA level_0_laser_dx_pixels,X        ; **SMC** patched by initialise_level_pointers
       laser_load_dx_addr_LO = laser_load_dx+1
       laser_load_dx_addr_HI = laser_load_dx+2
       STA laser_clip_t_x_max               ; reuse: stash dx (still unused at this point)

   .laser_load_dy
       LDA level_0_laser_dy_rows,X          ; **SMC**
       laser_load_dy_addr_LO = laser_load_dy+1
       laser_load_dy_addr_HI = laser_load_dy+2
       STA laser_dy_temp                    ; new scratch byte
   ```

2. Two new lookup tables, `level_laser_dx_lookup_LO/HI` and
   `level_laser_dy_lookup_LO/HI`, mirroring `level_obj_type_lookup_*`. These
   hold the per-level base addresses of the new arrays.

3. `initialise_level_pointers` patches the new SMC addresses, gated by
   `IF _TIMED_LASER` (one block, parallel to the existing
   `laser_load_object_type` patch).

4. `draw_laser_beam_at_obj_screen` drops the `laser_beam_dx_table` /
   `laser_beam_dy_table` lookups and uses the cached per-instance `dx, dy`
   instead. The proportional-clipping math stays in spirit but the slope is
   no longer fixed at 2:1, so:
   - `t_x_max` = `(255 − start_x) / |dx|` for right-facing, `start_x / |dx|`
     for left-facing.
   - `t_y_max` = same pattern for Y.
   - `t_clip = min(t_x_max, t_y_max, |dy|)` (or `|dx|` — pick whichever axis
     parameterises t consistently; |dy| was the choice with the fixed slope).
   - End coords: `start + sign(d) * t_clip * (|dy| / |d_axis|)` etc.

   The divides by |dx| and |dy| are real — no longer power-of-two halving.
   Use a small unsigned-divide subroutine; the inputs are bounded (|dx|, |dy|
   ≤ 127). Two divisions per laser per frame (worst case) is well within
   budget.

5. The orientation type still picks the sprite (via `obj_sprite_data_*_table_*`),
   the barrel offset (via `gun_bullet_x_offset` / `gun_bullet_y_offset`
   indexed by `(type − $09)`), and the destructibility branch — all unchanged.

6. Per-level data: extend the editor's level export with the new arrays.
   Existing test levels: write the type-driven defaults so behaviour after
   the rebuild matches what the user sees today.

7. **Cleanup:** remove `laser_beam_dx_table` / `laser_beam_dy_table` from
   `thrust.6502` once nothing references them.

## Editor changes (`tools/level_editor.py`)

1. **Level data model:** add `laser_dx`, `laser_dy` keys to each object dict
   alongside `gun_aim`. Loader fills them from the new export arrays, or from
   the orientation-type defaults if missing (back-compat with old exports).

2. **Endpoint drag handle:** when a laser is selected, draw a small filled
   circle at the beam's end-point (already computed for the preview line)
   and make it click-draggable. Dragging updates `laser_dx`, `laser_dy` in
   BBC pixel/row units. Same `grab_dx/grab_dy` offset trick as the recent
   object-drag fix.

3. **Beam preview:** `_render_laser_beam` reads `obj["laser_dx"]` /
   `obj["laser_dy"]` instead of the hardcoded `LASER_BEAM_DX_PIXELS` /
   `LASER_BEAM_DY_ROWS` dicts. The aspect / scaling math stays as-is —
   the `row_h_px / 2` factor still applies.

4. **Reset-to-default hotkey** (e.g., `\` or backspace) so the designer can
   always get back to a sensible direction without dragging precisely.

5. **Status bar:** add `dx`, `dy` numerics next to the existing `duty` / `phase`
   info, e.g. `dx=+60 dy=-30 duty=20f phase=32f`.

6. **Export / import:** emit and parse `level_N_laser_dx_pixels`,
   `level_N_laser_dy_rows`. Padding for non-laser slots: emit `0, 0` (game
   ignores them).

## Suggested implementation order

Each step is independently testable — at the end of step 2 the runtime works
with whatever defaults the level data has; the editor work in 3–4 just lets
the designer change them.

1. **Asm SMC + lookup tables + `initialise_level_pointers` wiring**, gated
   by `IF _TIMED_LASER`. Default the level data to today's per-orientation
   `(dx, dy)` so the build is byte-for-byte unchanged in behaviour.
2. **Asm: switch `draw_laser_beam_at_obj_screen`** to read per-instance
   `(dx, dy)` and rework the proportional-clip math for arbitrary slopes.
   Build, verify visually that lasers still draw correctly.
3. **Editor: model fields + endpoint drag handle + status bar.** Verify in
   the editor that drag changes the preview line.
4. **Editor: export / import the new arrays.** Round-trip test: edit, export,
   build, run, confirm in-game beam matches editor preview.
5. **Cleanup:** delete `laser_beam_dx_table` / `laser_beam_dy_table` from
   `thrust.6502`.
6. **Update `docs/ideas.md`:** the "Beam direction and length" caveat under
   Timed laser turrets goes away.

## Things to watch out for

- **8-bit signed `dx`/`dy` range** ±127 covers more than a screen but not the
  full 256-row world Y span. If a designer wants a near-vertical full-screen
  beam they may need to clamp.
- **Existing pre-rebuild SSDs** are fine to lose; the canonical non-SWRAM CRC
  `6389c446` doesn't change since this is all under `_TIMED_LASER` /
  `_SWRAM_BUILD`.
- **Per-laser divides** are the only new runtime cost. Cap the implementation
  on shift-and-subtract (≤ 8 iterations); inputs are bounded.
- **`level_obj_flags` bit 2** (`OBJ_flag_laser_beam_drawn`) keeps its meaning
  unchanged. The cached `obj_laser_prev_screen_x/y` machinery is unaffected
  by the dx/dy change.
