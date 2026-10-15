# Known issues

Defects and stale comments found in the October 2026 docs review. Feature work lives in [ideas.md](ideas.md). Line numbers are as of commit `90eaadd`.

## Possible bugs

### Underground X clamp may stop scrolling (`_NO_WRAP_UNDERGROUND`)

`update_window_and_terrain_tables` (`thrust.6502:3363-3376`): below the no-wrap Y threshold, if `window_xpos_INT < 3` the code zeroes `window_scroll_x` whichever way the window is moving. The clamp also runs after the scroll has already been added, so it cannot stop `window_xpos_INT` going below 3 (e.g. scroll -2 from 3 lands on 1). Whether the window then sticks at the left edge depends on how `window_scroll_x` is recomputed next frame. **Not reproduced in an emulator.** Suggested fix: clamp before the add, and only when the scroll is negative.

### `_FAST_SPRITES` mirrored angles may be one pixel left

The original decode (`thrust.6502:4977-4983`) does `SEC`, then `EOR #$1F`, then `ADC plot_ship_pixel_column`, so mirrored angles (17-31) get +1. `tools/generate_ship_streams.py:126-129` computes `(raw ^ 0x1F) + pixel_column` with no +1. With `_FAST_SPRITES` on, mirrored frames would be drawn one pixel left of the original. Not checked in an emulator; compare angle 16 with angles 15/17 when rotating.

### Gravity well radius above 127

The engine is limited to 127 (see [plan-gravity-well.md](plan-gravity-well.md)). The radius drag handle clamps to 127 (`tools/level_editor.py:3140`), but the inspector field allows up to 255 (`level_editor.py:1188-1190`). Set the field's `max` to 127.

## Stale comments

| Location | Says | Actually |
|---|---|---|
| `thrust.6502:940` | `$49` = "73 visible half-res scanlines" | Offset from `terrain_window_y_index` to the first visible row; `landscape_draw` covers 111 scanlines |
| `thrust.6502:162`, `:348`, `:363` | "MODE 5" | MODE 1 ULA ($D8), 4 pixels per byte |
| `thrust.6502:6440` | `level_obj_flags` bits 2-7 unused | Bits 2-4 are `laser_beam_drawn` ($04), `laser_redraw_pending` ($08), `disabled` ($10) |
| `thrust.6502:6966` | Active checkpoint also set by a "pod-pickup snap" | No pickup snap was built |
| `thrust.6502:12462` | Switch refractory "8 frames" | `$14` = 20 frames (~0.6 s at 33 Hz) |
| `thrust.6502:12583` | Action slot `$05` reserved | `$05` is `pulse_door`; only `$0B-$0F` are reserved |
| `tools/level_editor.py:1296-1297` | `$07` = door switch L, `$08` = R | Engine: `$07` = `door_switch_right`, `$08` = `door_switch_left` |
| `thrust.6502:11373-11383` (`draw_laser_beam_at_obj_screen` header) | Endpoint from "the per-orientation (dx, dy) table" | Per-instance dx/dy from obj_data slots 1/2 via `laser_dx_temp`/`laser_dy_temp`; the tables are gone |
| `thrust.6502:13412-13424` (bobbing mines header) | Phase added to `vsync_count`, masked to `ANGLE_MASK`; Y only | Phase added to the per-mine `bobbing_mine_local_tick`, 256-entry sine table; `$0F` mines bob in X (see [plan-bobbing-mines.md](plan-bobbing-mines.md)) |

## Minor

- `WELL_DEBRIS_SPAWN_MASK` (`thrust.6502:11643`) is defined but unused, and its comment says "every 8 ticks"; the emit gate hard-codes `#$01`.
- `generate_ship_streams.py` also generates pod streams that nothing uses.
- The old `obj_menu` right-click code in `level_editor.py` is dead.
- The legacy `level_3/4/5_door_logic` routines are unreachable under `_SWITCHES` but are still assembled into the SWRAM build.
