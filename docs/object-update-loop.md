# Object Update Loop Reference

This document describes `update_and_draw_all_objects` (`thrust.6502:1645`), the
per-frame tick and redraw loop for every non-player object in the current level.

It is called from four places: the high-score screen setup and its tick loop
(`thrust.6502:9332`, `9344`), level start (`9607`) and the main `tick_loop`
(`9641`). Each call walks the level's object-type array from index `0` until it
reads the terminator `$FF`, then jumps (via `end_of_obj_type_table`) to
`end_of_objects_function`, which runs the once-per-frame tail described at the
end of this document.

## Object Types

Type IDs are the `OBJECT_*` constants at `thrust.6502:111`. Their order is
load-bearing: every per-type table is indexed by this byte, and the Python
tooling (`tools/sprite_codec.py` `OBJECT_NAMES`) mirrors it.

| ID | Name | Build | Destructible? | Behaviour in the loop |
|----|------|-------|---------------|-----------------------|
| `$00` | `gun_up_right` | all | yes | fires (phase 9) |
| `$01` | `gun_down_right` | all | yes | fires |
| `$02` | `gun_up_left` | all | yes | fires |
| `$03` | `gun_down_left` | all | yes | fires |
| `$04` | `fuel` | all | yes | shield-tractor pickup (phase 8) |
| `$05` | `pod_stand` | all | no | ALIVE maintained per frame (phase 2a) |
| `$06` | `generator` | all | special | recharge / countdown, debris (phases 2b, 7, 10) |
| `$07` | `door_switch_right` | all | no | latches door counter or fires wiring (phase 7) |
| `$08` | `door_switch_left` | all | no | as `$07` |
| `$09`–`$0C` | `laser_turret_*` (up_right, down_right, up_left, down_left) | `_TIMED_LASER` | yes | sprite + bullets only; beam runs in `update_all_laser_beams` |
| `$0D` | `gravity_well` | `_GRAVITY_WELL` | — | skipped entirely; pull applied in `apply_gravity_wells_to_force` |
| `$0E` | `bobbing_mine` | `_BOBBING_MINES` | yes | vertical motion before draw; ship contact kills ship |
| `$0F` | `bobbing_mine_horizontal` | `_BOBBING_MINES` | yes | as `$0E`, horizontal motion |
| `$10` | `teleporter` | `_TELEPORTER` | — | no sprite; debris ring + ship-contact test, then skipped |
| `$11` | `door` | `_SWITCHES` | — | skipped; terrain carving runs in `tick_doors` |

All types from `$09` up exist only in the SWRAM build. The per-type tables
(`obj_type_width/height/explosion_particle/score_value`,
`object_type_cull_size_table`) have entries up to `$10`; `$11` never reaches a
table lookup because it is skipped before phase 1.

## `level_obj_flags[X]` Bit Layout

| Bit | Constant | Meaning |
|-----|----------|---------|
| 0 | `OBJ_flag_drawn` | Sprite is currently XOR-plotted on screen and must be erased before it moves or disappears. |
| 1 | `OBJ_flag_alive` | `1` = draw, collide and run behaviour. `0` = the object is not drawn at all (it vanishes, it does not go dormant). |
| 2 | `OBJ_flag_laser_beam_drawn` | Laser turret's beam is on screen (SWRAM). |
| 3 | `OBJ_flag_laser_redraw_pending` | Laser geometry changed via a wiring action; forces an erase/redraw (SWRAM). |
| 4 | `OBJ_flag_disabled` | Per-type behaviour suspended (gun fire, laser beam, mine motion and contact, well force, teleporter warp). The sprite still plots and bullets still hit it (SWRAM, set by switch wiring). |

Bits 5–7 are unused. The constants are at `thrust.6502:140`. (The banner
above `.level_obj_flags` still says bits 2–7 are unused; it predates bits 2–4.)

## SWRAM-only early outs

Before the original per-object body, the SWRAM build inserts type checks
straight after loading `gun_aim` (each block is under its own feature flag):

* `gravity_well` (`_GRAVITY_WELL`): `JMP next_object`. Wells have no sprite
  and no collision.
* `bobbing_mine` / `bobbing_mine_horizontal` (`_BOBBING_MINES`): call
  `update_bobbing_mine` / `update_bobbing_mine_horizontal`, which rewrite the
  object's `level_obj_pos_*` entry before the visibility test reads it. Both
  return immediately if `OBJ_flag_disabled` is set, freezing the mine. The
  mine then continues through the normal body.
* `teleporter` (`_TELEPORTER`): call `teleporter_emit_debris` (which also
  loads the pad position into `well_obj_*_save`) and
  `teleporter_check_ship_contact` (latches a pending warp unless disabled,
  pod tethered or pod lifted), then `JMP next_object`. The warp itself fires
  in `end_of_objects_function`.
* `door` (`_SWITCHES`): `JMP next_object`. Doors are not drawn or shootable.

## The Per-Object Loop

The phases below match the `\ --- N. ... ---` banners in the source.

### 1. Unpack `gun_aim`

`level_N_obj_data_0[X]` (self-modified address; slot 0 = `gun_aim`) is loaded
before the early outs and unpacked after them:

* Bits 2..4 (mask `$1C`) → `gun_base_angle`.
* Bits 0..1 → index into `gun_spread_mask_table` (`$01`, `$03`, `$07`, `$0F`)
  → `gun_angle_spread_mask`.

Every object has a slot-0 byte, but only the gun types `$00..$03` use these
values (phase 9). Other SWRAM types reuse slot 0 for their own parameters
(mine phase, for example).

### 2. Per-type ALIVE-bit maintenance

**2a. `pod_stand`**: sets `ALIVE`, then clears it again if
`pod_lifted_flag != 0`. This is what makes the stand's sprite vanish once the
pod is lifted.

**2b. `generator`**: while `planet_countdown_timer` is in `$01..$7F`, `ALIVE`
follows `countdown_timer_ticks & $04` (clear when the bit is set), so the
generator blinks during the countdown. The countdown is only armed when the
generator is destroyed, so this is the end-of-planet warning, not a live
generator.

Other types only lose `ALIVE` through the destroy and pickup paths (or the
SWRAM `set/clear/toggle_alive` wiring actions).

### 3. Sprite selection and dirty-rect check

Load sprite pointers for the type from `obj_sprite_data_A/B_table_LO/HI` into
`plot_static_sprite`'s self-modified operands, and clear `update_objects_flag`
and `obj_plot_sprite_at_ptr+1`.

If `OBJ_flag_drawn` is set, run `object_visibility_test` to compute this
frame's plot address (`obj_plot_sprite_at_ptr`, high byte `$00` = culled). If
the address is non-zero, equals the cached
`level_obj_plot_at_ptr_{LO,HI}[X]`, and `OBJ_flag_alive` is still set, set
`update_objects_flag = $FF` (no redraw) and jump to phase 6. Otherwise fall
into phase 4.

If `OBJ_flag_drawn` is clear, skip straight to phase 5.

### 4. Erase old sprite

XOR-plot the sprite at the cached address (erasing it) and clear
`OBJ_flag_drawn`.

### 5. `OBJ_flag_alive` gate

If `OBJ_flag_alive` is clear, `JMP next_object`. Otherwise, if phase 3 did not
already run `object_visibility_test`, run it now so `current_obj_*` and
`obj_plot_sprite_at_ptr` are populated.

### 6. Mine contact and planet-explode trigger

**Mine contact (`_BOBBING_MINES`)**: for `$0E`/`$0F`, unless
`OBJ_flag_disabled` is set, test the ship against the mine: 16-bit
`|dy| < $0B` rows and 8-bit `|dx| < 5` chars. On overlap set
`plot_ship_collision_detected = $FF` (kills the ship) and `JMP destroy_object`
(explodes the mine with its normal particle and score). This sits before the
trigger below so it also runs on the dirty-rect path.

**Planet-explode trigger**: `pod_stand` skips to phase 7. For every other type,
if `planet_countdown_timer == $00` (expired; `$FF` means not armed):

```
planet_explode_anim         = $0F   (if not already running)
pod_destroying_player_timer = POD_DESTROY_TIMER_INIT ($3C)
explosion_particle_type     = 1     (PARTICLE_type_debris)
score_value                 = 0
→ destroy_object
```

So each remaining object blows up, with no score, and the pod-destroying
timer is armed to kill the player.

### 7. Bullet collision

Load the type's hitbox (`obj_type_width/height`), explosion particle and score
from the tables at `thrust.6502:1428`.

Iterate `X = 3..0` over the four player-bullet slots. For a live player bullet
(`particles_lifetime[X] != 0`, `particles_type[X] == 0`), test
`0 <= bullet_x - obj_x < width` and 16-bit `0 <= bullet_y - obj_y < height`.
On a hit, zero the bullet's lifetime (keeping `PARTICLE_flag`) and dispatch:

| Type | Hit behaviour |
|------|---------------|
| `door_switch_*` | SWRAM (`_SWITCHES`): call `try_dispatch_switch_action`. If the switch has wiring entries it fires their actions (via `action_jump_table`: set/clear/toggle alive, destroy, pulse door, set/xor param, set/clear/toggle disabled) and returns carry clear; otherwise carry set and it falls back to the original latch. Original: `door_switch_counter_A = $FF`. Either way spawn hit debris, then fall through the generator test into `check_generic_destructible`, which treats `$07`/`$08` as inert and jumps to `try_next_bullet`. The bullet is consumed; `create_explosion` returns with X = 0, so the `DEX` ends the bullet loop for this object. |
| `generator` | Spawn hit debris; add `rnd & $1F` to `generator_recharge_increase` and store the sum in both `generator_recharge_counter` and `generator_recharge_increase`. No carry out: damage absorbed. Carry out and countdown not yet armed: set `generator_recharge_counter = $FF`, `planet_countdown_timer = PLANET_COUNTDOWN_SECONDS`, `countdown_timer_ticks = 1`. Both paths end bullet testing for this object. |
| `$00..$04`, `$09..$0C`, `$0E`, `$0F` | `destroy_object`: clear `ALIVE`, explode at object + (2, 4), add `score_value` to `score_accumulation`. |
| `pod_stand` and any other type | Inert: `try_next_bullet`. |

`destroy_object` and the generator path leave the bullet loop, so at most one
destroying hit is processed per object per frame.

### 8. Shield-tractor fuel pickup

Runs only when `pod_destroying_player_timer` is negative (`$FF`, normal play),
for type `fuel`, with `pod_tethered_flag == 0` and `shield_tractor_pressed`.
The proximity test is one-sided: `obj_x - player_x` must be `1..5` chars and
`obj_y - player_y - 1` must be `0..$1B` rows with no high-byte difference
(the fuel is below and slightly right of the ship's plot origin).

While engaged, `collecting_fuel_flag = 1` and `obj_tractor_counter[X]`
increments. At `$1A` (26 game frames, about 0.8 s at ~33 Hz) the fuel is
collected: `ALIVE` cleared, `$30` added to the score accumulator,
`collect_pod_fuel_sound`.

### 9. Hostile gun fire

Gun types `$00..$03` only (`CMP #OBJECT_fuel / BCS` skips everything else,
including laser turrets). Gated by:

* `OBJ_flag_disabled` clear (`_SWITCHES`);
* `generator_recharge_counter == 0` (silenced while recharging or destroyed);
* `planet_countdown_timer` negative (not armed);
* `current_obj_visible_flag` set (the visibility test sets it when the
  object is less than 256 rows below the window top, before the finer
  screen-bounds checks, so it is a coarse "near the screen" test);
* `rnd < hostile_gun_shoot_probability`.

Shot angle:

```
angle = (gun_base_angle + (rnd_B & gun_angle_spread_mask) + (rnd & $03)) & ANGLE_MASK
```

so shots fall in a one-sided cone from `base` to `base + spread_mask + 3`.
The `PARTICLE_type_hostile_bullet` spawns at the object position plus
`gun_bullet_x_offset/gun_bullet_y_offset[type]` (`thrust.6502:2272`): x +4 for
the right-facing guns, +1 for left; y +8 for the down-facing guns.

### 10. Generator debris emitter

When `level_tick_counter & $07 == 0`, for the generator while
`generator_recharge_counter == 0` and the countdown is not armed, spawn one
`PARTICLE_type_debris` at (x + 4, y) with `dy = $FF:$8E` (about -0.445
rows/frame, upward) and lifetime `PARTICLE_lifetime_generator`. This is the
smoke that shows the generator is live.

### 11. Redraw at new position

If `update_objects_flag` is set, or the plot address is `$0000` (culled), go to
`next_object`. Otherwise cache the address in
`level_obj_plot_at_ptr_{LO,HI}[X]` and call `plot_static_sprite`.

## Dirty-Rect Optimisation

1. Each object caches the screen address it was last plotted at.
2. If `OBJ_flag_drawn` is clear, nothing is on screen, so there is nothing to
   erase; the object is simply plotted at its current position.
3. If `OBJ_flag_drawn` is set and the new address matches the cache and the
   object is still alive, the on-screen sprite is already correct and both the
   erase and redraw are skipped.

Only a moved, culled or dead object pays for an XOR erase at the old address
followed (if still visible and alive) by an XOR plot at the new one. The
window scrolls in software, so any scroll changes every visible object's plot
address and forces the full erase/redraw for all of them.

## After the loop: `end_of_objects_function`

Runs once per call, after the `$FF` terminator:

1. `update_all_laser_beams` (`_TIMED_LASER`): a second pass over the object
   array that runs `update_one_laser_beam` for each `$09..$0C`.
2. `teleporter_dispatch_pending` (`_TELEPORTER`): performs any warp latched
   in the loop.
3. Add `score_accumulation` to the score.
4. `update_pod_tractor_beam`.
5. Every other frame, decrement `generator_recharge_counter` if non-zero.
6. Every `$21` frames (`countdown_timer_ticks` reload `$20`), if the planet
   countdown is armed: decrement it with a sound, draw the digit, and when it
   reaches 0 set `plot_ship_collision_detected = 1` and `pod_lifted_flag = $FF`.

Door terrain (`tick_doors`, SWRAM) and switch refractory timers
(`tick_switch_logic`) are ticked from `update_window_and_terrain_tables` via
`tick_door_logic`, not from this loop.

## Per-Type Table Index

| Table | Purpose | Location |
|-------|---------|----------|
| `obj_type_width` / `obj_type_height` | AABB hitbox | `thrust.6502:1428` |
| `obj_type_explosion_particle` | Particle type for destruction | `thrust.6502:1460` |
| `obj_type_score_value` | Score added on destruction | `thrust.6502:1477` |
| `object_type_cull_size_table` | Horizontal cull width for `object_visibility_test` | `thrust.6502:2344` |
| `obj_sprite_data_A/B_table_{LO,HI}` | Sprite pointers | `thrust1/obj_sprite_data.asm` (non-SWRAM); `tools/output/object_sprites.asm` (SWRAM, generated by `tools/sprite_editor.py`) |
| `gun_bullet_x_offset` / `gun_bullet_y_offset` | Gun bullet spawn offset (4 entries) | `thrust.6502:2272` |
| `gun_spread_mask_table` | Spread width LUT (4 entries) | `thrust.6502:2278` |

In the SWRAM build, `obj_type_explosion_particle` and `obj_type_score_value`
are padded with zeros for `$05..$08` inside the `_TIMED_LASER` block, so the
later entries only line up while `_TIMED_LASER` is enabled.

## Adding a New Object Type

Every per-type table is indexed by `object_type`, so a new type touches the
tooling, the tables and the dispatch sites:

1. Append to `OBJECT_NAMES` in `tools/sprite_codec.py` and `OBJECT_TYPE_NAMES`
   in `tools/visualise_levels.py`.
2. Draw the sprite in `tools/sprite_editor.py`; saving regenerates
   `tools/output/object_sprites.asm`.
3. Add the `OBJECT_` constant at `thrust.6502:111` under a feature flag.
4. Extend `obj_type_width/height/explosion_particle/score_value` and
   `object_type_cull_size_table` under the same flag.
5. Add any early-out or behaviour hook at the top of the loop, and widen the
   ordering-based gates the type needs (`try_gun_fire`,
   `check_generic_destructible`).
6. If the type has behaviour that switches can suspend, test
   `OBJ_flag_disabled` in it.
