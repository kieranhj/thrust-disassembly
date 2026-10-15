# Plan: per-laser endpoint (length + angle) configuration

**Status:** done (commits `00874b1`, `c9806e9`, `997f831`, `7877046`, `02e1112`, `a852e68`; later moved onto the generic `obj_data` slots).

Timed laser turrets (`OBJECT_laser_turret_*`, types `$09..$0C`, behind `_TIMED_LASER`) originally drew their beam with one of four hard-coded `(dx, dy)` pairs from `laser_beam_dx_table` / `laser_beam_dy_table`, picked by orientation. Each laser now carries its own `(dx, dy)`, authored in the editor. The four orientation types still choose the sprite and the barrel corner.

## Design

- **`(dx, dy)` rather than angle + length.** This is what `draw_line` needs and what an editor drag produces, so there is no sin/cos lookup at runtime.
- **Orientation and beam direction are independent.** An `$09 up_right` turret may fire down-left; the editor does not warn.
- **`gun_aim` (slot 0) keeps its 4+4 nibble split**: low nibble = phase index (× 8 frames), high nibble = duty index (× 4 + 4 frames), period 128 frames.
- **`laser_beam_dx/dy_table` are deleted** from the asm. The orientation defaults now live only in the editor.

## Data model

dx and dy use generic per-object data slots 1 and 2, shared with gravity wells (radius, strength) and bobbing mines:

| Slot | Array | Meaning for a laser |
|------|-------|---------------------|
| 0 | `level_N_obj_data_0` | `gun_aim` (phase / duty) |
| 1 | `level_N_obj_data_1` | dx, signed, in pixels (4 per character) |
| 2 | `level_N_obj_data_2` | dy, signed, in pixel rows |

The per-level base addresses are in `level_obj_data_1_lookup_LO/HI` and `level_obj_data_2_lookup_LO/HI` (`thrust.6502:10970-10988`, in SWRAM). The first implementation used dedicated `level_N_laser_dx_pixels` / `level_N_laser_dy_rows` arrays; the editor still accepts those names on import.

Orientation defaults, used for new lasers, for the reset key and for old exports with no dx/dy data:

| Type | dx | dy |
|------|----|----|
| `$09` up-right | +60 | −30 |
| `$0A` down-right | +60 | +30 |
| `$0B` up-left | −60 | −30 |
| `$0C` down-left | −60 | +30 |

## Game changes (`thrust.6502`)

1. **SMC loads.** `update_one_laser_beam` (`thrust.6502:11194`) loads slot 1 and slot 2 at `laser_load_dx` / `laser_load_dy` into the scratch bytes `laser_dx_temp` / `laser_dy_temp` (`thrust.6502:10948`). `initialise_level_pointers` patches these sites from the slot lookups inside `IF _TIMED_LASER` (`thrust.6502:7307-7316`).

2. **Beam geometry.** `draw_laser_beam_at_obj_screen` (`thrust.6502:11386`):
   - Start X = `(obj_screen_x + gun_bullet_x_offset[type − $09]) · 4`, in pixels; the beam is skipped if the barrel is at character 64 or beyond. Start Y = `obj_screen_y + 2 · gun_bullet_y_offset[type − $09]`, in pixel rows.
   - `range_x` = pixels to the screen edge in the dx direction (`255 − start_x` or `start_x`); `range_y` likewise for dy.
   - If `|dx| ≤ range_x` and `|dy| ≤ range_y`, the end point is just `start + (dx, dy)`.
   - Otherwise the beam is parameterised by `t_q` in Q0.7 (127 ≈ full length). For each axis that overflows, `laser_divide_q7` computes `(range << 7) / |d|`, a 7-iteration shift-and-subtract; `t_q` is the minimum of those and 127. The end point is `start + hi(2 · d · t_q)` per axis via `multiply_signed_8x8`.
   - The draw coordinates `draw_line_start_x/y`, `end_x/y` (`$88..$8B`) alias the multiply's zero-page operands, so the clip path keeps the coordinates in `laser_save_*` scratch and copies them back afterwards (fixed in `997f831`).
   - The beam is XOR-drawn with `draw_line` in the level's object colour (`OBJECT_COLOUR_BYTE`).

3. **Erase/redraw.** The screen position and the dx/dy used for the last draw are cached in `obj_laser_prev_screen_x/y` and `obj_laser_prev_dx/dy`, so the erase XORs exactly the pixels that were drawn, even if a switch action (`set_param` / `xor_param`) has rewritten slot 1 or 2 in the meantime. `OBJ_flag_laser_beam_drawn` (bit 2 of `level_obj_flags`) records that a beam is on screen. `OBJ_flag_laser_redraw_pending` (bit 3) forces one erase and redraw after a geometry change. When the beam is on, already drawn and the window has not scrolled, `update_one_laser_beam` returns without redrawing.

4. **Unchanged by this work:** the orientation type still selects the sprite (`obj_sprite_data_*_table_*`), the barrel offset (`gun_bullet_x/y_offset`) and the destructibility branch.

## Editor changes (`tools/level_editor.py`)

- **Model:** `laser_dx`, `laser_dy` on each object dict next to `gun_aim`. Export writes them into `level_N_obj_data_1` / `_2`. Import reads them from there, falls back to the legacy arrays, and finally to the orientation defaults (`LASER_BEAM_DX_PIXELS` / `LASER_BEAM_DY_ROWS`).
- **Endpoint drag handle:** with a laser selected, a dot is drawn at the beam tip; dragging it sets `laser_dx` / `laser_dy` (`_set_laser_endpoint_from_screen`, clamped −128..127).
- **Preview:** `_laser_beam_screen_coords` draws from the barrel corner (`LASER_BARREL_X_CHARS` / `LASER_BARREL_Y_ROWS`) using the same scale on both axes (`char_w_px / 4` per pixel), so the angle matches the game.
- **Reset:** `\` restores the selected laser's orientation default.
- **Properties panel** (`SCHEMA_LASER`): Phase (`[` / `]`), Duty (`,` / `.`), Beam dx and Beam dy (−127..127, Shift step 8).

## Things to watch out for

- **Range.** Signed 8-bit dx/dy reach ±127 pixels or rows, more than half the screen but not a full-width beam.
- **Cost.** A beam that needs clipping costs up to two 7-step divides and two `multiply_signed_8x8` calls, on top of `draw_line`. An unclipped beam needs neither. The fast path skips all of it on frames with no scroll and no state change.
- **Shared slots.** Slots 1 and 2 mean radius/strength for a gravity well and amplitude/state for a mine. The editor export ORs the laser and well fields into the same byte, relying on the unused pair being 0.
- **Stale comment.** The header of `draw_laser_beam_at_obj_screen` still mentions the per-orientation table and the hostile-bullet colour; the code uses per-instance dx/dy and `OBJECT_COLOUR_BYTE`.
