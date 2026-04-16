# Object Update Loop Reference

This document describes `update_and_draw_all_objects` (`thrust.6502:1475`) — the
per-frame tick and redraw loop for every non-player object in the current level
(guns, fuel cells, the pod stand, the generator, door switches, and — in the
SWRAM build — the heavy turret).

The loop is called from the main game tick at four points (see
`thrust.6502:8483`, `8495`, `8758`, `8792`). Each call walks the level's
object-type array from index `0` until it hits the terminator byte `$FF`.

## Object Types

Type IDs live in `thrust.6502:102` (`OBJECT_*` constants). Their order is
load-bearing: every per-type table is indexed by this byte, and the Python
tooling (`tools/sprite_codec.py` `OBJECT_NAMES`) mirrors the same order.

| ID | Name | Destructible? | Fires? | Pickup? |
|----|------|---------------|--------|---------|
| `$00` | `gun_up_right` | yes | yes | — |
| `$01` | `gun_up_left` | yes | yes | — |
| `$02` | `gun_down_right` | yes | yes | — |
| `$03` | `gun_down_left` | yes | yes | — |
| `$04` | `fuel` | yes | — | shield-tractor |
| `$05` | `pod_stand` | — | — | touch (ship collides) |
| `$06` | `generator` | yes (recharging HP) | — | — |
| `$07` | `door_switch_right` | — (latches) | — | — |
| `$08` | `door_switch_left` | — (latches) | — | — |
| `$09` | `heavy_turret_up_right` (SWRAM) | yes | yes (heavy bullet) | — |

"Destructible" means a player bullet will destroy the object and remove it from
the level. `pod_stand` and `door_switch_*` are explicitly *not* destructible —
bullets pass through `pod_stand`, and door switches are latched by bullets
rather than destroyed.

## `level_obj_flags[X]` Bit Layout

The per-object flags byte drives the loop's state machine. Full layout is
annotated at `thrust.6502:5980`; the two bits the update loop cares about are:

| Bit | Name | Meaning |
|-----|------|---------|
| 0 | `MOVED` | Set by physics when the object's on-screen cell may have changed. Consumed by step 3 (visibility test) and cleared in step 4 (erase old). |
| 1 | `ALIVE` | `1` = render + apply behaviour. `0` = skip draw, collisions, and per-type ticks. |

Other bits (`$04`, `$08`, `$10`…) are used by non-update-loop code.

## The Per-Object Loop

The 11 phases below repeat for each object. Section banners (`\ --- N. ... ---`)
in the source align with the numbers here.

### 1. Unpack `gun_aim`

Load `level_N_gun_aim[X]` (self-modified address). The byte encodes two things:

* Bits 2..4 (mask `$1C`) → `gun_base_angle` — the base firing angle.
* Bits 0..1 → index into `gun_spread_mask_table` (`$01`, `$03`, `$07`, `$0F`)
  → `gun_angle_spread_mask` — the random-spread width.

Even non-firing objects have a `gun_aim` byte (typically zero). Only types in
`OBJECT_FIRING_TYPES` (`$00..$03`, `$09`) actually consult it in phase 9.

### 2. Per-type ALIVE-bit maintenance

Two object types mutate their own `ALIVE` bit every frame before rendering:

**2a. `pod_stand`** — always sets `ALIVE`, then clears it once
`pod_attached_flag_2 != 0` (the pod has been tractored off the stand). This is
what makes the sprite disappear when you lift the pod.

**2b. `generator`** — while `planet_countdown_timer` is in `$01..$7F`, the
generator blinks: `ALIVE` toggles on/off depending on
`countdown_timer_ticks & $04`. The generator has already been destroyed by this
point (`generator_recharge_counter == $FF`), so the blink is the expiring-base
visual warning, not a live enemy.

All other types leave `ALIVE` alone — it was set at level load and only gets
cleared in destroy / pickup paths.

### 3. Visibility cull + dirty-rect decision

Select the sprite pointers for the current type from
`obj_sprite_data_A/B_table_LO/HI` (indexed by `object_type`).

If `MOVED` is set, run `object_visibility_test`. This populates
`obj_plot_sprite_at_ptr` with either a screen address (visible) or `$0000`
(culled). Then compare:

* New plot ptr == cached `level_obj_plot_at_ptr_{LO,HI}[X]`?
* `ALIVE` still set?

If both hold, set `update_objects_flag = $FF` to tell phase 11 "no redraw
needed", and skip straight to phase 6 (bullet/player collision still runs).

### 4. Erase old sprite

If the decision in phase 3 was "needs redraw" (moved cell, culled, or just
died), plot the sprite at the *cached* position first. Because
`plot_static_sprite` is an XOR plotter, re-plotting at the old cell erases it.
Then clear `MOVED` (`AND #$FE`).

### 5. `ALIVE` gate

If `ALIVE` is clear now (e.g. we just erased a dead object), jump straight to
`next_object`. Everything from here on is for live objects.

If `ALIVE` is set but `obj_plot_sprite_at_ptr+1` wasn't set in phase 3 (because
`MOVED` was 0), run `object_visibility_test` now to populate it.

### 6. Planet-explode trigger

This is the end-of-level fail state. For **every non-`pod_stand`** object, if
`planet_countdown_timer` has counted all the way to `$00`, unconditionally
treat the ship as destroyed:

```
explosion_particle_type = 1 (ship explosion)
score_value             = 0
→ destroy_object
```

The `pod_stand` short-circuits to `bullet_test_object` unconditionally so that
you can still collide with it during the countdown.

### 7. Bullet collision (AABB × 4)

Load this type's hitbox (`obj_type_width/height`), score value
(`obj_type_score_value`) and explosion particle (`obj_type_explosion_particle`)
from the per-type tables at `thrust.6502:1326`.

Iterate `X = 3..0` over the four player-bullet slots. For each live player
bullet (`particles_type[X] == 0` and `lifetime != 0`), AABB-test against the
object. On a hit, kill the bullet's lifetime and dispatch on object type:

| Type | Hit behaviour |
|------|---------------|
| `door_switch_*` | Latch `door_switch_counter_A = $FF`, spawn debris, then fall through `handle_generator` (not a generator) into `check_generic_destructible`. Door switch IDs (`$07`/`$08`) are `>= pod_stand` (`$05`), so the `BCS` there treats them as inert. Net effect: switch latches, bullet is consumed, sprite is not destroyed. |
| `generator` | Spawn debris, add random damage to `generator_recharge_counter`. No overflow → `delete_object` (damage absorbed). Overflow → arm `planet_countdown_timer` for `PLANET_COUNTDOWN_SECONDS`, then `delete_object`. The generator sprite keeps rendering until the blink phase finishes. |
| type `< pod_stand` (`$00..$04`), or `heavy_turret` (SWRAM) | `destroy_object`: clear `ALIVE`, spawn explosion, award `score_value`. |
| `pod_stand`, `door_switch_*`, or any type `>= pod_stand` not whitelisted | Inert: `try_next_bullet`. |

Important: `destroy_object` does **not** return to `bullet_test_loop` — it
short-circuits to the post-bullet tail. Only one hit per object per frame.

### 8. Shield-tractor fuel pickup

**Type `fuel` only.** When:

* `pod_destroying_player_timer` has bit 7 set (normal gameplay — $FF idle);
* `pod_attached_flag_1 == 0` (pod isn't already on the ship);
* shield-tractor key is pressed; AND
* player is within `|dx| < 6` and `|dy| < $1C`, same Y high byte

…then increment `obj_tractor_counter[X]` by 1 per frame. Once it reaches
`$1A` (~26 frames, roughly half a second), the fuel cell is collected: `ALIVE`
cleared, `$30` added to score, pickup sound played.

### 9. Hostile gun fire

For firing types only (`$00..$03`, plus `heavy_turret` in SWRAM):

Gated by:

* generator still intact (`generator_recharge_counter == 0`);
* planet countdown not yet armed (`planet_countdown_timer` still $FF);
* object currently visible on-screen;
* per-frame probability check against `hostile_gun_shoot_probability`.

When firing, pick a shot angle as:

```
angle = gun_base_angle + (rnd & gun_angle_spread_mask) + (rnd & $03)
```

Bullets always fly in a one-sided cone from `base` to
`base + spread_mask + 3`. Spawn a `PARTICLE_type_hostile_bullet` (or
`_hostile_heavy_bullet` for heavy turrets) at the object position plus the
per-orientation offset from `gun_bullet_x/y_offset`.

The heavy turret uses the `OBJECT_gun_up_right` offsets via a remap rather than
extending the 4-entry offset tables.

### 10. Generator debris emitter

Every 8 game ticks (`level_tick_counter & $07 == 0`), the generator spawns a
single `PARTICLE_type_debris` drifting upward (`dy = $FF:$8E` ≈ `-0.445`
pixels/tick). Only runs while the generator is intact and the planet countdown
hasn't started. This is the constant chimney-smoke visual that tells you the
generator is alive.

### 11. Redraw at new position

If `update_objects_flag` was set to `$FF` in phase 3 (dirty-rect skipped
redraw), fall through to `next_object`.

Otherwise, plot the sprite at `obj_plot_sprite_at_ptr`, cache the new plot
address back into `level_obj_plot_at_ptr_{LO,HI}[X]` for next frame's
dirty-rect check, and advance to the next object.

## Dirty-Rect Optimisation

The loop avoids an unconditional erase+redraw every frame. Instead:

1. Each object caches the screen address it was last plotted to
   (`level_obj_plot_at_ptr_{LO,HI}[X]`).
2. When physics hasn't flagged `MOVED`, the loop doesn't even run the
   visibility test — it just plots straight from the cached address.
3. When `MOVED` is set *but* visibility says the object hasn't actually
   changed cell (sub-pixel motion) AND is still `ALIVE`, the loop sets
   `update_objects_flag` to suppress the redraw entirely.

Only when the object genuinely needs erasing (moved cell, culled, died) does
the loop XOR at the cached position and then XOR-plot at the new one.

## Per-Type Table Index

| Table | Purpose | Location |
|-------|---------|----------|
| `obj_type_width` / `obj_type_height` | AABB hitbox | `thrust.6502:1326` |
| `obj_type_explosion_particle` | Particle type for destruction explosion | `thrust.6502:1326` |
| `obj_type_score_value` | Points awarded when destroyed | `thrust.6502:1326` |
| `obj_sprite_data_A/B_table_{LO,HI}` | Sprite-data pointers per type | `tools/output/object_sprites.asm` (auto-generated) |
| `gun_bullet_x_offset` / `gun_bullet_y_offset` | Per-gun bullet spawn offset | `thrust.6502:1914` (4 entries, gun types only) |
| `gun_spread_mask_table` | 4-entry LUT for spread width | `thrust.6502:1918` |

## Adding a New Object Type

Because every per-type table is indexed by `object_type`, adding a new type is
a coordinated change across the Python tooling, the per-type tables, and the
CMP/BEQ dispatch sites at phases 2, 6, 7, 9, 10.

The checklist and a worked example (`OBJECT_heavy_turret_up_right = $09`) are
in `~/.claude/plans/stateless-foraging-narwhal.md`. The quick summary:

1. Append to Python `OBJECT_NAMES` / `OBJECT_TYPE_NAMES`.
2. Draw the sprite in `tools/sprite_editor.py`, save → regenerates
   `tools/output/object_sprites.asm`.
3. Add the `OBJECT_` constant in `thrust.6502:102`.
4. Extend `obj_type_width/height/explosion_particle/score_value` (with
   `IF _SWRAM_BUILD` guards if SWRAM-only).
5. Widen any ordering-based gates the new type needs to participate in
   (`try_gun_fire`, `check_generic_destructible`).
6. Add explicit CMP/BEQ branches for type-specific behaviour.
