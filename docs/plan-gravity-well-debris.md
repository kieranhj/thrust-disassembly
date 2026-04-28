# Plan: gravity-well debris visualisation

The gravity well is invisible in-game because giving it a sprite makes it lethal on collision. Visualise its position and field by spawning short-lived, non-lethal debris particles that drift inward toward the well centre — a "matter falling into a black hole" feel that also implicitly shows the radius.

## Decisions confirmed

- **Reuse `PARTICLE_type_debris` (`$01`)** — already non-lethal to the ship (only `PARTICLE_type_hostile_bullet` is checked in `test_particle_X_close_to_player` at `thrust.6502:6517`), and the existing particle update/draw path renders it for free. Don't define a new particle type.
- **Spawn cadence is well-driven, not frame-driven.** Hook into `apply_gravity_wells_to_force` (already a per-tick walk over wells) and gate by `level_tick_counter` so each well emits at most once every N ticks. Avoids burning the 32-slot particle pool.
- **No "ship inside radius" gate** — always-on emission, so the debris functions as a position marker even when the ship is far away. The user explicitly wants to see where wells are.
- **Spawn at the radius perimeter, velocity toward centre.** Looks like material being sucked in. Particle lifetime is sized so it reaches the centre as it expires — natural fade-in/out.
- **Repulsors invert the direction.** When `strength < 0` the particle spawns at the centre and flies outward to the radius. Same emitter, just sign-flipped velocity.
- **No new asm scratch state per well.** Whatever the spawn function needs lives in the existing well scratch slots or local registers.
- **Gated by `_GRAVITY_WELL`.** Non-SWRAM CRC `6389c446` stays anchored.

## Particle math

For a well at world `(WX, WY)` with radius `R`:

1. Pick a random angle `θ ∈ [0, 32)` using the existing 32-step angle system (`angle_to_x_*` / `angle_to_y_*` lookup tables).
2. **Spawn position** = `(WX, WY) + R * (sin θ, -cos θ)` — i.e. on the perimeter. Use the same lookups the gun-fire code uses.
3. **Velocity** = `-(spawn_pos - centre) / lifetime_frames` ≈ `-step_per_frame * (sin θ, -cos θ)`. Magnitude = `R / lifetime`.
4. **Lifetime** = a small fixed value (e.g. 24 frames). Long enough to be visible; short enough that the pool doesn't fill.
5. **Sign flip for repulsors:** if `strength < 0`, swap step 2 with `centre`, step 3 with `+(perimeter - centre)/lifetime`. Same magnitude, opposite direction.

The angle lookup tables already give us a unit vector per angle. Multiply by `R` to get the offset to the perimeter; multiply by `R / lifetime` to get the per-frame velocity. Both multiplies are by the same per-well constant — pre-compute once per emit.

The 32-angle system means perimeter samples are octagonal, not perfectly circular. Visually fine — particles chase the field, not the ring outline.

## Spawn cadence

- Each well emits one particle per spawn tick.
- Spawn ticks: gate on `level_tick_counter AND #SPAWN_MASK`. With `SPAWN_MASK = $07` that's one emit every 8 ticks per well.
- Per-well jitter: AND the tick counter with `$07` and compare against `(current_object AND $07)`, so wells in different slots fire on different ticks. Avoids all wells emitting on the same frame and clumping.
- Worst case: 8 wells × 1 emit per 8 ticks = 1 per tick = ~16/sec. Lifetime 24 frames ≈ 1 sec. Steady-state ~16 particles. Fits the 32-slot pool with headroom.

## Asm changes (`thrust.6502`)

1. **Constant near the laser/well section:**
   ```asm
   IF _GRAVITY_WELL
   WELL_DEBRIS_LIFETIME = $18                    ; 24 ticks
   WELL_DEBRIS_SPAWN_MASK = $07                  ; emit every 8 ticks per well
   ENDIF
   ```

2. **Inside `apply_gravity_wells_to_force`**, after the radius/strength load and before (or in parallel with) the pull math, run a "should this well emit a particle this frame?" gate. If yes, call a new `well_emit_debris_particle` subroutine:

   ```asm
   \\ Per-well emit gate. current_object is in current_object; well_radius_save
   \\ already loaded. Spawn one debris particle every SPAWN_MASK+1 ticks per
   \\ well, jittered by current_object so wells don't all emit simultaneously.
   LDA     level_tick_counter
   EOR     current_object
   AND     #WELL_DEBRIS_SPAWN_MASK
   BNE     well_emit_skip
   JSR     well_emit_debris_particle
   .well_emit_skip
   ```

   `well_emit_debris_particle` clobbers A/Y at minimum; X is current_object on entry and should be preserved (or restored from current_object after) since the walker uses it.

3. **`well_emit_debris_particle`** does:
   - `JSR particle_return_free_slot_in_Y` to claim a slot.
   - Random angle: `JSR rnd; AND #$1F` → A in `[0, 32)`. Save as `well_emit_angle` scratch.
   - Strength sign: load `well_load_strength` value (8-bit signed). If positive, "in" mode; if negative, "out" mode. (Could simply XOR the angle's lookup result by the sign.)
   - Compute spawn position. Use existing `angle_to_x_INT,Y` / `angle_to_y_INT,Y` tables (already used by `angle_to_bullet_dx_dy`). Multiply unit vector by radius:
     - `dx_perim = (angle_to_x_INT[θ] * radius) >> 7` (signed Q1.7-ish multiply via `multiply_signed_8x8`).
     - Same for Y.
     - `pos_x = WX + dx_perim`, `pos_y = WY + dy_perim` (16-bit Y add to handle EXT byte).
   - Compute velocity. `vel = -dx_perim / lifetime` per axis. Approximate as right-shift by `log2(lifetime)` if lifetime is a power of 2 (use 16 instead of 24 for the shift trick — 4 right-shifts), or do a divide. **Simplest: pick lifetime = 16 frames so velocity = `-dx_perim >> 4`** — saves a divide.
   - Repulsor branch: skip the negation, leave velocity outward.
   - Write `particles_xpos_INT/FRAC`, `particles_ypos_INT/FRAC/INT_HI`, `particles_dx_INT/FRAC`, `particles_dy_INT/FRAC`, `particles_type = PARTICLE_type_debris`, `particles_lifetime = (existing_PARTICLE_flag) | WELL_DEBRIS_LIFETIME`.
   - RTS.

4. **Re-walking concern:** `multiply_signed_8x8` clobbers ZP `$88..$8B` + `multiply_sign_ext`. `apply_gravity_wells_to_force` already uses these for the pull math. The emit's multiplies must not interleave with mid-pull state. Cleanest order: do the pull (which already returns to a known state), then the emit. Or, emit first then pull — the pull's multiply doesn't depend on prior multiply state.

5. **Particle timing.** `particle_return_free_slot_in_Y` is cheap (linear scan of 32 lifetimes). The whole emit (rnd, two multiplies, six 16-bit writes) is ~250-300 cycles. With 1 emit per tick worst case at 16 wells active in radius (impossible in practice — typical level has 1-3 wells), this is well under a scanline.

6. **No new RAM bytes** beyond a couple of zero-page-able scratches if needed (`well_emit_angle`, `well_emit_dx_perim`, `well_emit_dy_perim`). Actually, the existing `well_dx_signed`, `well_dy_signed`, `well_pull` scratch bytes are reused inside the emit since the pull math is already done by the time emit runs.

## Editor changes

None required — the editor's diamond outline + centre dot already shows the well's position and radius. Optionally:

- Render a few static "ring" sample points around the perimeter as a visual hint that debris spawns there. Cosmetic only.

## Suggested implementation order

1. **Test the emit in isolation:** add `well_emit_debris_particle` as a stub that just spawns a static debris particle at `(WX, WY)` (no math, no lifetime jitter). Verify a particle appears at every well.
2. **Add radius-perimeter spawn:** wire in the angle lookup + radius multiply. Verify particles appear *around* the well, not on top of it.
3. **Add inward velocity:** use the simple `>> 4` trick, lifetime 16. Verify particles move toward the centre.
4. **Repulsor branch:** flip sign for `strength < 0`.
5. **Per-well jitter:** add the `EOR current_object` to the spawn gate.
6. **Tuning:** adjust `SPAWN_MASK` and `WELL_DEBRIS_LIFETIME` if visuals feel too sparse / dense.

## Things to watch out for

- **`particle_return_free_slot_in_Y` can fall back to a random eviction** when no slots are free (line 6196). On a busy level, well debris could displace player bullets or stars momentarily. Acceptable — debris is short-lived and cheap.
- **Particle velocity precision.** `dx_perim >> 4` for 24-frame lifetime undershoots; for 16-frame it's exact. Use 16. If that's too short visually, do a real divide instead.
- **Y high-byte handling.** The well centre's Y is 16-bit (`obj_pos_Y_EXT:obj_pos_Y`). Particle Y is also 16-bit (`particles_ypos_INT_HI:particles_ypos_INT`). When adding `dy_perim` (signed 8-bit) to the well centre, propagate sign extension into the high byte. The existing well code already does this pattern when computing dy.
- **XOR plot interaction.** Debris is XOR-plotted. Two particles overlapping on the same pixel cancel. Visually fine for sparse debris, looks weird if a stream of particles converges on the centre and each new particle re-erases the last. Mitigation: keep spawn rate low and lifetimes long enough that particles spread out before reaching the centre.
- **Wells off-screen.** The emit runs even when the well is off-screen. Particles spawned off-screen will be invisible until / unless they enter the viewport. Probably fine — a well off-screen exerts no visible pull, so wasted emits are cheap and harmless. If profiling shows a hotspot, add an on-screen check using the existing visibility test.
- **Repulsor visuals.** When `strength < 0` particles move outward — same machinery, just opposite. Spawn at centre, fly to perimeter, expire. The lifetime sizing still works.
- **Centre singularity.** Particle's velocity is computed from the *spawn* position, not updated each frame, so they fly in a straight line toward the centre and overshoot. They expire near the centre because the lifetime equals the travel time. Slight overshoot before expiry is fine; if particles look like they "punch through" the centre, shorten lifetime by 1-2 frames.
