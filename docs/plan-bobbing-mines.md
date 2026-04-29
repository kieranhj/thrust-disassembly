# Plan: Bobbing mines

Passive radial hazard object: floats in place, bobbing up/down on a sine wave around a base Y. Destroyed by bullets (explosion + score). Ship contact is handled by the existing ship-vs-pixel collision against the mine's drawn sprite — no bespoke ship-mine collision routine needed. Per-instance phase offset so a group doesn't bob in lockstep.

SWRAM-only behind a new build flag; non-SWRAM canonical CRC `6389c446` stays anchored.

## 1. Build flag and object type

- Add `_BOBBING_MINES = (_SWRAM_BUILD AND TRUE)` alongside the other feature flags near `thrust.6502:42`.
- Allocate `OBJECT_bobbing_mine = $0E` (single radial type — no orientation variants).
- Add `IF _BOBBING_MINES`-gated entries in the per-type parallel tables:
  - `obj_type_width` / `obj_type_height` (`:1408,:1417`) — sized to the new sprite.
  - `obj_type_explosion_particle` (`:1426`) — generic destruction debris.
  - `obj_type_score_value` (`:1436`).
  - `object_type_cull_size_table` (`:2167`).
  - `obj_sprite_data_A_table_LO/HI` and `_B_*` — point at the new sprite.

## 2. Per-instance data layout

Reuses the existing generic obj_data slot mechanism — no new export arrays, no new SMC patch sites.

| Slot | Field |
|------|-------|
| `obj_data_0` | Phase byte (combined with frame counter to index trig table) |
| `obj_data_1` | Amplitude (signed-ish 7-bit pixels) |
| `obj_data_2` | Blast radius / damage byte (reserved; see open questions) |

Base Y stays in `level_obj_pos_Y` / `_EXT`. Each frame the routine computes `displayed_y = base_y + sin_offset` and writes the result into the live `current_obj_ypos_INT/EXT` zp slots before cull/draw run. The level arrays themselves are never mutated.

## 3. Per-frame sin update

Hook inside `update_and_draw_all_objects` near `:1618`, in the same place the gravity-well type bypasses gun_aim unpacking. For `OBJECT_bobbing_mine`:

```
phase     = obj_data_0[X]
idx       = (vsync_count + phase) AND <trig-table mask>
sin_int   = angle_to_y_INT[idx]
sin_frac  = angle_to_y_FRAC[idx]
offset    = scale_by_amplitude(sin, obj_data_1[X])    ; signed
displayed_y = base_y + sign_extend(offset)
write displayed_y into current_obj_ypos_INT / current_obj_ypos_EXT
```

Multiply uses the shared `multiply_*` zp helpers already used by gravity wells. Cost ~40 cycles per mine per frame — acceptable for the expected handful of mines per level.

The existing draw pipeline (`object_visibility_test`, dirty-rect compare, XOR erase + redraw) reads from `current_obj_ypos_INT/EXT` and just works once those zp values are patched. The dirty-rect compare invalidates each frame because Y changed — that's correct.

## 4. Collision

Bullet contact only. Extend the destructible-type test in `check_generic_destructible` (`:1870`) to accept `$0E`; falls through to existing `destroy_object` → `create_explosion`. No new collision code path.

Ship contact is handled implicitly by the existing ship-vs-pixel collision against the mine's plotted sprite — falls out of the standard render-then-test loop. No separate proximity test required.

## 5. Sprite

New ~8×8 spiked-ball sprite added near the other static sprite blocks at `thrust.6502:2326+`, gated behind `_BOBBING_MINES`. Reuses `plot_static_sprite` (`:2265`); no bespoke plot routine. New labels wired into the existing `obj_sprite_data_*` tables.

## 6. Editor support (`tools/level_editor.py`)

- Register `OBJECT_bobbing_mine = 0x0E` in `OBJECT_TYPE_NAMES`; add an icon to `SPRITE_DATA`.
- Per-mine object dict fields: `mine_phase`, `mine_amp`, `mine_blast` — packed into obj_data slots 0/1/2 by the existing slot-write export path. Round-trip via the existing import path.
- Key bindings (mirroring laser dx/dy and well strength UX):
  - `[` / `]` — phase
  - `,` / `.` — amplitude (shift = ±10)
  - `;` / `'` — blast / damage byte
- Visual: dotted vertical bar showing amplitude extent at the mine's base Y, reusing the well-radius render scaffolding.

## 7. Risks / open questions

- Confirm the shared multiply zp slots are free across the per-object update window (`:1599`–`:1735`).
- Phase byte stores 0..255 but the trig table index is narrower; clamp / document in the editor.
- One-frame Euler lag: mines are kinematic, ship physics unaffected. Bullet-vs-mine and ship-vs-mine-pixel both use current-frame state.
- Blast radius / damage byte (slot 2) — open whether to bother in v1, or leave the byte reserved and just rely on the standard explosion.
