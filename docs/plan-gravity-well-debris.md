# Plan: gravity-well debris visualisation

**Status:** done (commits `893f0cd`, `9462ac2`). The emitter is `well_emit_debris_particle` (`thrust.6502:11888`), called from the emit gate in `apply_gravity_wells_to_force`. The teleporter (`_TELEPORTER`) reuses the same routine in repulsor mode for its pad fountain.

The gravity well (see [plan-gravity-well.md](plan-gravity-well.md)) has no sprite, because a plotted sprite would be lethal through ship-vs-pixel collision. Its position and extent are shown instead by short-lived, non-lethal debris particles: a pull well draws debris in from its perimeter to its centre, a repulsor throws debris out from its centre to its perimeter.

Polish items left for later:
- **More spawn directions.** The 8 fixed points on the diamond give a visibly 8-spoked pattern. A small random jitter along each edge, or more directions, would turn it into a cloud.
- **Well centre vs ship resting point.** The pull targets `midpoint_*` (the ship+pod centre of mass when tethered), so the ship settles slightly off the debris centre, which is the well's true `obj_pos`. Aligning them without breaking tethered-pod physics needs more thought.

## Design

- **Reuses `PARTICLE_type_debris` (`$01`).** Only `PARTICLE_type_hostile_bullet` is checked in `test_particle_X_close_to_player` (`thrust.6502:6722`), so debris never kills the ship, and the existing particle update/draw path plots it. No new particle type.
- **Emission is driven by the well walk**, not a separate per-frame pass. It runs inside `apply_gravity_wells_to_force`, so it shares the gravity tick gate.
- **Always on.** There is no "ship in range" test; the debris marks where wells are even when the ship is far away. A disabled well (`OBJ_flag_disabled`) or one with radius 0 emits nothing.
- **Pull** (`strength ≥ 0`): spawn on the perimeter, fly to the centre.
- **Push** (`strength < 0`): spawn at the centre, fly out to the perimeter.
- **Lifetime equals travel time**, so particles expire as they arrive.
- **Gated by `_GRAVITY_WELL`**; the non-SWRAM CRC `6389c446` is unaffected.

## Particle maths

The perimeter is the same pixel-square diamond as the pull region (`2·|dx| + |dy| = radius`). Directions come from two 8-entry Q0.7 tables (`well_dir_dx_factor` / `well_dir_dy_factor`, `thrust.6502:11635`), giving the 4 vertices and the 4 edge midpoints:

| dir | X factor | Y factor | offset (X, Y) |
|-----|----------|----------|---------------|
| 0 | `$3F` | `$00` | (r/2, 0) |
| 1 | `$1F` | `$3F` | (r/4, r/2) |
| 2 | `$00` | `$7F` | (0, r) |
| 3 | `$E1` | `$3F` | (−r/4, r/2) |
| 4 | `$C1` | `$00` | (−r/2, 0) |
| 5 | `$E1` | `$C1` | (−r/4, −r/2) |
| 6 | `$00` | `$81` | (0, −r) |
| 7 | `$1F` | `$C1` | (r/4, −r/2) |

The X factors are half the Y factors because a world X unit is twice the on-screen size of a world Y unit.

1. `dir = rnd AND 7`.
2. `offset = hi(2 · factor[dir] · radius)` per axis (`multiply_signed_8x8`, then `ASL`/`ROL` to undo the Q0.7 scaling).
3. Spawn position: pull → `obj_pos + offset` (X wraps at 8 bits; Y offset is sign-extended into `particles_ypos_INT_HI`); push → `obj_pos` itself.
4. Velocity per axis, as Q8.8 in `particles_d{x,y}_INT/FRAC`: pull → `−offset · 16 / 256 = −offset/16`; push → `+offset/16`. Computed with a signed multiply by `$10`.
5. `particles_type = PARTICLE_type_debris`; `particles_lifetime = (old AND PARTICLE_flag) OR WELL_DEBRIS_LIFETIME`.

`WELL_DEBRIS_LIFETIME = $10` (16 frames). Lifetime decrements once per game frame, so after 16 frames the particle has moved exactly `offset` and expires at the centre (pull) or on the perimeter (push). Using a power of two turns the divide into the multiply-by-16 above.

## Spawn cadence

The gate in `apply_gravity_wells_to_force` (`thrust.6502:11717-11729`):

```asm
        LDA     level_tick_counter
        EOR     current_object
        AND     #$01
        BNE     well_emit_skip
        JSR     well_emit_debris_particle
    .well_emit_skip
```

The walk only runs on gravity ticks (`level_tick_counter AND $0F` in {0, 3, 5, 8, B, D}). An earlier `AND #$07` stagger never fired for most slots, because `tick AND 7` on those ticks is only ever 0, 3 or 5. The parity stagger means adjacent slots fire on different ticks, but it is uneven:

- even-numbered object slots emit on ticks 0 and 8: 2 particles per 16 frames (about 4 a second at ~33Hz);
- odd-numbered slots emit on ticks 3, 5, B and D: 4 per 16 frames (about 8 a second).

With a 16-frame lifetime that is 2 or 4 live particles per well. A level with four wells adds about 12 particles to the 32-slot pool.

The constant `WELL_DEBRIS_SPAWN_MASK = $01` is defined next to the lifetime but the gate uses the literal `#$01`.

## Asm summary (`thrust.6502`)

- Scratch (`thrust.6502:11608-11627`): `well_obj_x_save`, `well_obj_y_lo_save`, `well_obj_y_hi_save` hold the well's world position so the emitter can use it after the pull maths has reused the other scratch; `well_emit_dir`, `well_emit_offset_x/y`, `well_emit_slot` belong to the emitter.
- `well_emit_debris_particle` claims a slot with `particle_return_free_slot_in_Y` (`thrust.6502:6377`), saves it in `well_emit_slot` (because `multiply_signed_8x8` clobbers X), and restores `X = current_object` before returning.
- The emit runs before the pull maths for that well. Both use `multiply_signed_8x8` but neither depends on multiply state left by the other.
- Cost per emit: four `multiply_signed_8x8` calls (~220-380 cycles each), the free-slot scan (up to ~400 cycles when the pool is busy) and the stores: roughly 1,500-1,900 cycles. Only one well in two emits on any gravity tick, so a few wells cost a few per cent of the 60,000-cycle game frame on those ticks.

## Editor

No editor change was needed: the diamond outline and centre dot drawn by `_render_gravity_well` already show the well's position and radius (blue for pull, red for push).

## Things to watch out for

- **Pool pressure.** When no slot is free, `particle_return_free_slot_in_Y` falls back to any slot whose lifetime is below `PARTICLE_lifetime_generator`, and then to a random slot. On a busy level debris can displace a bullet or star for a frame. Acceptable because the debris is short-lived.
- **XOR plotting.** Debris is XOR-plotted, so two particles on the same pixel cancel. With pull wells, particles converge on the centre at the end of their life; the low spawn rate keeps this from being noticeable.
- **Off-screen wells** still emit. The particles are invisible until they enter the view. If profiling shows a cost, add an on-screen test before the emit.
- **Overshoot.** Velocity is fixed at spawn, so particles fly in a straight line. Because lifetime equals travel time they expire on arrival; `dx/16` is exact, so there is no drift.
