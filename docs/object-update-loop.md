# Object Update Loop Reference

This document describes `update_and_draw_all_objects` (`thrust.6502:1372`), the
per-frame tick and redraw loop for every non-player object in the current level,
and the door logic that the door switches drive.

It is called from four places: the high-score screen setup and its tick loop
(`thrust.6502:9208`, `9220`), level start (`9536`) and the main `tick_loop`
(`9566`). Each call walks the level's object-type array from index `0` until it
reads the terminator `$FF`, then jumps (via `end_of_obj_type_table`) to
`end_of_objects_function`, which runs the once-per-frame tail described at the
end of this document.

The per-level object arrays are `level_N_obj_pos_X`, `_pos_Y`, `_pos_Y_EXT`,
`_obj_type` and `_gun_param` (`thrust.6502:6550` onwards). The loop reads them
through self-modified operands that `initialise_level_pointers` patches per
level. Levels hold between 4 and 19 objects; `level_obj_flags` has 20 entries.

## Object Types

Type IDs are the `OBJECT_*` constants at `thrust.6502:66`. Their order is
load-bearing: every per-type table is indexed by this byte, and several gates
are ordered comparisons (`CMP #OBJECT_fuel / BCS`, `CMP #OBJECT_pod_stand / BCS`).

| ID | Name | Destructible? | Behaviour in the loop |
|----|------|---------------|-----------------------|
| `$00` | `gun_up_right` | yes | fires (phase 9) |
| `$01` | `gun_down_right` | yes | fires |
| `$02` | `gun_up_left` | yes | fires |
| `$03` | `gun_down_left` | yes | fires |
| `$04` | `fuel` | yes | shield-tractor pickup (phase 8) |
| `$05` | `pod_stand` | no | ALIVE maintained per frame (phase 2a) |
| `$06` | `generator` | special | recharge / countdown, debris (phases 2b, 7, 10) |
| `$07` | `door_switch_right` | no | a hit latches `door_switch_counter_A` (phase 7) |
| `$08` | `door_switch_left` | no | as `$07` |

Door switches appear only in levels 3, 4 and 5 (`level_number` is 0-based),
two per level.

## `level_obj_flags[X]` Bit Layout

| Bit | Meaning |
|-----|---------|
| 0 | Drawn: the sprite is currently XOR-plotted on screen and must be erased before it moves or disappears. |
| 1 | Alive: `1` = draw, collide and run behaviour. `0` = the object is not drawn at all (it vanishes, it does not go dormant). |

Bits 2–7 are unused. The source has no named constants for these bits; it uses
`ORA #$02`, `AND #$FD`, `AND #$FE` and a `ROR` to test bit 0.
`initialise_level_pointers` sets every entry to `$02` (alive, not drawn) at the
start of each level, not on a retry, so destroyed objects stay destroyed after
a lost life. Its loop runs `LEVEL_MAX_OBJECTS + 1` = 32 times, so it also
writes `$02` over the first 12 bytes of `level_obj_plot_at_ptr_LO`, which
follows the 20-byte table. This is harmless: with the drawn bit clear, those
cached addresses are never read before being rewritten.

## The Per-Object Loop

The source has no phase banners; the numbering below is this document's.

### 1. Unpack `gun_param`

`level_N_gun_param[X]` (self-modified address) is unpacked as:

* Bits 2..4 (mask `$1C`) → `gun_base_angle`.
* Bits 0..1 → index into `gun_param_table` (`$01`, `$03`, `$07`, `$0F`)
  → `gun_angle_spread_mask`.

Every object has a `gun_param` byte, but only the gun types `$00..$03` use these
values (phase 9); the other types have `$00`.

### 2. Per-type ALIVE-bit maintenance

**2a. `pod_stand`**: sets ALIVE, then clears it again if
`pod_attached_flag_2 != 0`. `attach_pod_to_ship` sets that flag when the pod is
picked up, so the stand vanishes once the pod is lifted.

**2b. `generator`**: while `planet_countdown_timer` is in `$01..$7F`, ALIVE
follows `countdown_timer_ticks & $04` (clear when the bit is set), so the
generator blinks during the countdown. The countdown is only armed when the
generator is destroyed, so this is the end-of-planet warning, not a live
generator.

Other types only lose ALIVE through the destroy and pickup paths.

### 3. Sprite selection and dirty-rect check

Load sprite pointers for the type from `obj_sprite_data_A/B_table_LO/HI`
(`thrust.6502:9085`) into `plot_static_sprite`'s self-modified operands, and
clear `update_objects_flag` and `obj_plot_sprite_at_ptr+1`.

If the drawn bit is set, run `object_visibility_test` to compute this frame's
plot address (`obj_plot_sprite_at_ptr`, high byte `$00` = culled). If the
address is non-zero, equals the cached `level_obj_plot_at_ptr_{LO,HI}[X]`, and
ALIVE is still set, set `update_objects_flag = $FF` (no redraw) and jump to
phase 6. Otherwise fall into phase 4.

If the drawn bit is clear, skip straight to phase 5.

### 4. Erase old sprite

XOR-plot the sprite at the cached address (erasing it) and clear the drawn bit.

### 5. ALIVE gate

If ALIVE is clear, `JMP next_object`. Otherwise, if phase 3 did not already
run `object_visibility_test`, run it now so `current_obj_*` and
`obj_plot_sprite_at_ptr` are populated.

### 6. Planet-explode trigger

`pod_stand` skips to phase 7. For every other type, if
`planet_countdown_timer == $00` (expired; `$FF` means not armed):

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
from the tables at `thrust.6502:1246`. `obj_type_explosion_particle` and
`obj_type_score_value` have only five entries (`$00..$04`); for types `$05..$08`
the lookups read the bytes that follow, but those types never reach
`destroy_object` from a bullet, so the values are unused.

Iterate `X = 3..0` over the four player-bullet slots. For a live player bullet
(`particles_lifetime[X] != 0`, `particles_type[X] == 0`), test
`0 <= bullet_x - obj_x < width` and 16-bit `0 <= bullet_y - obj_y < height`.
On a hit, zero the bullet's lifetime (keeping `PARTICLE_flag`) and dispatch:

| Type | Hit behaviour |
|------|---------------|
| `door_switch_*` | `door_switch_counter_A = $FF`, then spawn hit debris (`L0F64`: a three-particle `PARTICLE_type_random_debris` burst at the bullet). `create_explosion` returns with `X = 0`, so after falling through the generator test into `L0F7D` (where `$07`/`$08` are inert) the `DEX / BMI` ends bullet testing for this object. |
| `generator` | Spawn hit debris; add `rnd & $1F` (plus any incoming carry) to `generator_total_damage` and store the sum in both `generator_recharge_counter` and `generator_total_damage`. No carry out: damage absorbed. Carry out and countdown not yet armed: set `generator_recharge_counter = $FF`, `planet_countdown_timer = PLANET_COUNTDOWN_SECONDS` (10), `countdown_timer_ticks = 1`. Both paths end bullet testing for this object. |
| `$00..$04` | `destroy_object`: clear ALIVE, explode at object + (2, 4), add `score_value` to `score_accumulation`. |
| `pod_stand` | Inert: next bullet. |

Every hit except one on the pod stand leaves the bullet loop, so at most one
hit per object per frame has an effect. Both exits (`delete_object` and the end
of `destroy_object`) jump to `remove_object_from_level_GUESS`, which despite its
name is the start of phase 8.

### 8. Shield-tractor fuel pickup

Runs only when `pod_destroying_player_timer` is negative (`$FF`, normal play),
for type `fuel`, with `pod_attached_flag_1 == 0` (no pod in tow) and
`shield_tractor_pressed`. The proximity test is one-sided: `obj_x - player_x`
must be `1..5` chars and `obj_y - player_y - 1` must be `0..$1B` rows with no
high-byte difference (the `- 1` is the carry left clear by the X test; the
fuel is below and slightly right of the ship's plot origin).

While engaged, `collecting_fuel_flag = 1` and `obj_tractor_counter[X]`
increments. At `$1A` (26 game frames, about 0.8 s at ~33 Hz) the fuel is
collected: ALIVE cleared, `$30` added to the score accumulator,
`collect_pod_fuel_sound`. `obj_tractor_counter` has 12 entries, which covers
every fuel object (the highest fuel index in any level is 11).

### 9. Hostile gun fire

Gun types `$00..$03` only (`CMP #OBJECT_fuel / BCS` skips everything else).
Gated by:

* `generator_recharge_counter == 0` (silenced while recharging or destroyed);
* `planet_countdown_timer` negative (not armed);
* `current_obj_visible_flag` set (the visibility test sets it when the
  object is less than 256 rows below `window_ypos`, before the finer
  screen-bounds checks, so it is a coarse "near the screen" test);
* `rnd < hostile_gun_shoot_probability`.

Shot angle:

```
angle = (gun_base_angle + (rnd_B & gun_angle_spread_mask) + (rnd & $03)) & ANGLE_MASK
```

so shots fall in a one-sided cone from `base` to `base + spread_mask + 3`.
The `PARTICLE_type_hostile_bullet` spawns at the object position plus
`gun_bullet_x_offset/gun_bullet_y_offset[type]` (`thrust.6502:2036`): x +4 for
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
2. If the drawn bit is clear, nothing is on screen, so there is nothing to
   erase; the object is simply plotted at its current position.
3. If the drawn bit is set and the new address matches the cache and the
   object is still alive, the on-screen sprite is already correct and both the
   erase and redraw are skipped.

Only a moved, culled or dead object pays for an XOR erase at the old address
followed (if still visible and alive) by an XOR plot at the new one. The
window scrolls in software, so any scroll changes every visible object's plot
address and forces the full erase/redraw for all of them.

## After the loop: `end_of_objects_function`

`end_of_objects_function` (`thrust.6502:1263`) runs once per call, after the
`$FF` terminator:

1. Add `score_accumulation` to the score.
2. `update_pod_tractor_beam`.
3. Every other frame, decrement `generator_recharge_counter` if non-zero.
4. Every `$21` frames (`countdown_timer_ticks` reload `$20`), if the planet
   countdown is armed: decrement it with a sound (unless already 0), draw the
   digit, and when it is 0 set `plot_ship_collision_detected = 1` and
   `pod_attached_flag_2 = $FF`.

## Doors

Doors are not objects. A door is a short run of `terrain_left_wall` rows that
the door logic overwrites every frame, so `landscape_draw` draws it as part of
the left wall. The switches and the door share two zero-page counters:

* `door_switch_counter_A` (`$6B`): set to `$FF` by any switch hit and
  decremented once per frame towards 0.
* `door_switch_counter_B` (`$6C`): the door's current opening, 0 = closed.

Both are cleared with the rest of zero page `$01..$9A` by `level_reset`, which
also runs on every retry.

### `tick_door_logic`

`tick_door_logic` (`thrust.6502:3320`) is called once per frame from the end of
`update_window_and_terrain_tables` (`thrust.6502:2982`), so it runs before the
object loop in the same frame. It decrements `door_switch_counter_A` if
non-zero, then dispatches on `level_number`: 3 → `level_3_door_logic`,
4 → `do_level_4_door_logic`, 5 → `do_level_5_door_logic`. Other levels return.

### Per-level routines

Each routine has the same structure:

1. **Range test.** `door_screen_ypos = door_y - window_ypos` (16-bit). Return
   unless the high byte is 0 and the low byte is below a per-level limit. The
   limit keeps every row the door writes inside the 256-row decoded terrain
   buffer.
2. **Counter update.** If `counter_A < OPEN`, set `counter_B = counter_A`
   (closing). Otherwise increment `counter_B` by one until it reaches `OPEN`
   (opening).
3. **Stamp the door.** Write wall X values into
   `terrain_left_wall[door_screen_ypos + terrain_window_y_index + row]`.
   Since `terrain_window_y_index` tracks `window_ypos_INT`, this index is the
   door's world row modulo 256.

| Level | Routine | Door Y | Range limit | `OPEN` | Shape written |
|-------|---------|--------|-------------|--------|---------------|
| 3 | `level_3_door_logic` (`3356`) | `$0269` | `$F1` | `$10` | 13 rows at X = `$AE - B` (a flat slab that slides left by B) |
| 4 | `do_level_4_door_logic` (`3414`) | `$0343` | `$E9` | `$15` | rows 1..21: X = `$98` for rows 1..B, `$A6` for rows B+1..21 (the closed section shrinks towards the bottom) |
| 5 | `do_level_5_door_logic` (`3476`) | `$0370` | `$EF` | `$12` | 15 rows: X = `$C0 - B` rising by 1 per row to `$C7 - B` at row 7, then falling back (a wedge that slides left by B) |

Here B is `door_switch_counter_B`.

### Timing

After a hit, the door opens by one unit per frame until `B = OPEN` (16, 21 or
18 frames), holds while `counter_A` runs down from `$FF` to `OPEN` (about 235
frames, roughly 7 s at ~33 Hz), then closes one unit per frame as `B` follows
`counter_A` down to 0. Hitting either switch again resets `counter_A` to `$FF`
and extends the open time.

`counter_A` decrements whether or not the door is in range, but `counter_B`
only changes while it is. If the player shoots a switch and the door is out of
range, the door's opening freezes; if `counter_A` has dropped below `OPEN` by
the time the door comes back into range, `B` jumps straight to `counter_A`.

## Per-Type Table Index

| Table | Purpose | Location |
|-------|---------|----------|
| `obj_type_width` / `obj_type_height` | AABB hitbox (9 entries) | `thrust.6502:1246`, `1249` |
| `obj_type_explosion_particle` | Particle type for destruction (5 entries) | `thrust.6502:1252` |
| `obj_type_score_value` | Score added on destruction (5 entries) | `thrust.6502:1255` |
| `object_type_cull_size_table` | Horizontal cull width for `object_visibility_test` | `thrust.6502:2108` |
| `obj_sprite_data_A/B_table_{LO,HI}` | Sprite pointers | `thrust.6502:9085` |
| `gun_bullet_x_offset` / `gun_bullet_y_offset` | Gun bullet spawn offset (4 entries) | `thrust.6502:2036`, `2039` |
| `gun_param_table` | Spread width LUT (4 entries) | `thrust.6502:2042` |
