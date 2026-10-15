# Ship Physics Technical Reference

## Overview

The physics simulation is built around a **midpoint**. All forces act on the midpoint (the centre of mass of the ship-pod system). Ship and pod positions are derived by offsetting from the midpoint in opposite directions along the tether vector (`midpoint_delta`). With no pod attached, the tether angle is not integrated, so the delta is a constant offset and the midpoint simply tracks the ship.

The velocity vector (`velocity_vectorx`/`velocity_vectory`) is added to the midpoint every frame. Gravity, thrust and drag modify it on 6 of every 16 frames.

---

## Tick Loop Execution Order

`tick_loop` (`thrust.6502:9555`) runs the physics-related routines in this order each frame (other calls omitted):

```
 1. ship_input_rotate                          ; rotation input
 2. midpoint_add_velocity_vector               ; integrate velocity into midpoint + integrate tether angle
 3. draw_player_timed_to_vsync                 ; -> draw_ship_line_and_pod
                                               ;    -> update_shield_tractor_draw_ship_and_pod
                                               ;       -> calculate_attached_pod_vector (midpoint_delta)
 4. update_player_and_pod_states               ; tether contraction; calculate_pod_pos
 5. update_and_draw_all_objects                ; ... update_pod_tractor_beam (pod pickup)
 6. calculate_player_position_from_midpoint    ; ship = midpoint + delta; player_velocity
 7. ship_input_thrust_calculate_force          ; gravity, thrust, tether torque, drag
```

The velocity computed in step 7 is integrated in step 2 of the **next** frame (one-frame-behind Euler integration). The game frame is a minimum of 3 centiseconds (`draw_player_timed_to_vsync` waits for the system clock to reach 3), so about 33 frames/s, and per-second figures below use 33 Hz.

---

## Fixed-Point Formats

| Variable | Bytes | Format | Notes |
|---|---|---|---|
| `velocity_vectorx` | 3 | Q7.16 signed | INT.FRAC.FRAC_LO (ZP $14/$13/$12) |
| `velocity_vectory` | 2 | Q7.8 signed | INT.FRAC (ZP $16/$15) |
| `midpoint_xpos` | 3 | Q8.16 unsigned | INT.FRAC.FRAC_LO (ZP $09/$08/$07), wraps horizontally |
| `midpoint_ypos` | 3 | Q16.8 unsigned | INT_HI.INT.FRAC (ZP $0C/$0B/$0A) |
| `tether_angle` | 3 | Q5.16 | `angle_ship_to_pod` (0-31).`tether_angle_FRAC`.`tether_angle_LO` (ZP $1D/$1C/$1B) |
| `tether_angular_vel` | 3 | Q7.16 signed | INT.FRAC.LO (ZP $20/$1F/$1E) |
| `gravity` | 2 | Q7.8 signed | `gravity_INT`.`gravity_FRAC` (ZP $A6/$A7) |
| `player_xpos` | 2 | Q8.8 | Ship X has no FRAC_LO byte |
| `player_velocityx` | 2 | Q7.8 signed | Frame-to-frame ship position delta |
| `player_velocityy` | 3 | Q15.8 signed | INT_HI.INT.FRAC |
| Angle lookup tables | 2 per entry | Q7.8 signed | 32 entries; Y amplitude 2.5, X amplitude 1.25 |

---

## Rotation

`ship_input_rotate` (`thrust.6502:6104`):

- CAPS LOCK (`INKEY_capslock`) decrements `ship_angle`
- CTRL (`INKEY_ctrl`) increments `ship_angle`
- Result masked with `ANGLE_MASK` ($1F): 32 angles, 11.25 degrees each
- Angle 0 = pointing up, $08 = right, $10 = down
- Rate limit: the routine returns early when `level_tick_counter AND 3 == 0`, so rotation happens on 3 of every 4 frames (~25 steps/s, a full turn in ~1.3s)

---

## Force Calculation

`ship_input_thrust_calculate_force` (`thrust.6502:4128`).

**Entry check.** If `pod_destroying_player_timer` is running (bit 7 clear, i.e. a death/pod-destruction countdown is in progress) and no pod is attached (`pod_attached_flag_1 == 0`) and `player_ship_destroyed_flag` is zero, the velocity vector is zeroed (X INT/FRAC and Y INT/FRAC; `velocity_vectorx_FRAC_LO` is left alone) and the routine returns.

**Tick gating.** Otherwise the routine only proceeds when `level_tick_counter AND $0F` is one of $00, $03, $05, $08, $0B, $0D (6 of 16 frames, ~12 updates/s). On other frames it returns immediately.

### Gravity

Added first on every active tick:

```
velocity_vectory += gravity_INT:gravity_FRAC
```

Positive Y is downward. `initialise_level_pointers` (`thrust.6502:7293`) loads `gravity_FRAC` from `level_gravity_FRAC_table` ($05, $07, $09, $0B, $0C, $0D for levels 0-5) and sets `gravity_INT` to $00, so normal gravity is always downward; the level value is not sign-extended. When `reverse_gravity_flag` is set (it toggles every 6 levels), `gravity_FRAC` is EORed with $FF and `gravity_INT` becomes $FF, giving upward gravity of -(g+1)/256.

### Thrust

Thrust requires `pod_destroying_player_timer` negative (no death countdown), `fuel_just_ran_out_flag` clear and SHIFT (`INKEY_shift`) pressed. It calls `use_fuel` and `run_engine`.

#### Angle-to-Velocity Lookup

The thrust direction comes from 32-entry tables that `main_entry` copies from `lookup_angle_to_*` (`thrust.6502:11133`) down to page $08:

| Table | Address | Angle 0 (up) | Angle 8 (right) | Angle 16 (down) |
|-------|---------|-------------|-----------------|-----------------|
| `angle_to_y_FRAC/INT` | $0880/$08A0 | $FD.80 (-2.5) | $00.00 (0) | $02.80 (+2.5) |
| `angle_to_x_FRAC/INT` | $0980/$09A0 | $00.00 (0) | $01.40 (+1.25) | $00.00 (0) |

The tables are -2.5·cos and +1.25·sin of the angle. The Y amplitude is twice the X amplitude because X and Y world units are not the same size on screen.

#### Thrust Scaling

The table value at `ship_angle` is shifted right:

- **4 times** (divide by 16) normally
- **5 times** (divide by 32) when `pod_attached_flag_1` is set, so thrust is halved when carrying the pod

The integer byte is rebuilt as $00 or $FF from the sign, so this is an arithmetic shift. The result is added directly to the velocity vector; the table already points the vector the way the ship faces (angle 0 gives negative Y, i.e. up), so no negation is needed:

```
velocity_vectorx += angle_to_x[ship_angle] >> n     ; 3 bytes: FRAC_LO, FRAC, INT
velocity_vectory += angle_to_y[ship_angle] >> n     ; 2 bytes: FRAC, INT
```

Per active tick this is at most 2.5/16 ≈ 0.16 in Y and 1.25/16 ≈ 0.08 in X.

### Drag

Applied on every active tick, thrusting or not, after thrust and tether torque:

**X drag:**
```
velocity_vectorx -= velocity_vectorx >> 6        ; x 63/64 per active tick
```
24-bit arithmetic shift right by 6, then subtraction.

**Y drag:**
```
velocity_vectory -= velocity_vectory >> 8        ; x 255/256 per active tick
```
16-bit arithmetic shift right by 8, then subtraction.

Weak Y drag balances gravity at a high terminal velocity: equilibrium is reached when `velocity_vectory / 256 == gravity`, i.e. `velocity_vectory` = 256 × g (e.g. $07.00 for g = $07).

---

## Tether Pendulum Physics

### Tether Torque from Thrust

This block sits inside the thrust path, so it runs only on active ticks **while thrusting**, and is skipped on ticks $03 and $0B (4 of the 6 active ticks). It does not test `pod_attached_flag_1`; without a pod the result is harmless because `midpoint_add_velocity_vector` only integrates the tether angle when the pod is attached or a death countdown is running.

1. **Relative angle**: `ship_angle - angle_ship_to_pod` with the fraction `0 - tether_angle_FRAC`, rounded by +$08 and masked to 0-31.

2. **Tangential component**: the `angle_to_x` table (1.25·sin) is read at the relative angle. This is the thrust component perpendicular to the tether.

3. **Sub-angle interpolation**: one base sample plus 15 loop iterations (X = $0E down to 0), 16 samples in all. Each iteration compares the top nibble of the fractional angle against `lookup_top_nibble[X]` (`$10, $20, ..., $F0`, `thrust.6502:4615`); on a match the table index advances to the next angle. The first samples use the base angle and the rest the next angle, giving linear interpolation in 16ths.

4. **Scale and add**: the 16-sample sum is arithmetically shifted right once (8 × the table value) and added one byte down, into `tether_angular_vel_LO`/`_FRAC` with sign extension into `_INT`:
   ```
   tether_angular_vel += (sum16 >> 1) / 256
   ```

### Angular Damping

Immediately after the torque add, the angular velocity saved before the update (`prev_tether_vel_*`) is arithmetically shifted right by 6 and subtracted (the subtraction starts with CLC, so it removes one extra LSB):

```
tether_angular_vel -= old_tether_angular_vel >> 6
```

About 1.6% per application. Because it lives in the same block, damping only happens while thrusting on torque ticks; with the thrust key released the pendulum keeps swinging undamped.

### No Gravity Torque

There is no gravity torque term. Gravity is applied to the midpoint, which accelerates ship and pod equally and so cannot rotate the tether. The pendulum swings only from thrust torque and the angular velocity set at pickup.

---

## Position Integration

### Velocity to Midpoint Position

`midpoint_add_velocity_vector` (`thrust.6502:6137`) runs every frame:

**X axis** (24-bit addition, wraps):
```
midpoint_xpos (FRAC_LO, FRAC, INT) += velocity_vectorx (FRAC_LO, FRAC, INT)
```

**Y axis** (16-bit signed velocity into 24-bit position):
```
midpoint_ypos_FRAC += velocity_vectory_FRAC
midpoint_ypos_INT  += velocity_vectory_INT
```
If `velocity_vectory_INT` is positive, a carry out increments `midpoint_ypos_INT_HI`; if negative, no carry (borrow) decrements it.

### Tether Angle Integration

Then, if `pod_destroying_player_timer` is running or `pod_attached_flag_1` is set:

```
tether_angle_LO   += tether_angular_vel_LO
tether_angle_FRAC += tether_angular_vel_FRAC
angle_ship_to_pod  = (angle_ship_to_pod + tether_angular_vel_INT + carry) AND $1F
```

---

## Tether Angle to Delta Vector

`calculate_attached_pod_vector` (`thrust.6502:5071`) converts the tether angle into `midpoint_delta`, the vector from the midpoint to the ship. It is called every frame from `update_shield_tractor_draw_ship_and_pod` and repeatedly by the pickup angle search.

1. Round the fraction: `pod_angle_sub_frac = tether_angle_FRAC + $08`, carrying into the angle index (`angle_ship_to_pod`, masked to 0-31).
2. Load the base X and Y table entries into `midpoint_deltax`/`midpoint_deltay`.
3. Loop `tether_length + 1` times (X from `tether_length` down to 0): compare the top nibble of `pod_angle_sub_frac` with `lookup_top_nibble[X]`, advance the index on a match, add the current entry to the accumulators.
4. Arithmetic shift right by 2. X keeps a third byte (`midpoint_deltax_FRAC_LO`); Y is two bytes.

With `tether_length` = $0E there are 16 samples, so after the divide by 4 the delta is 4 × the table magnitude (X up to 5, Y up to 10), interpolated between the 32 angle steps.

### Tether Contraction During Destruction

`tether_length` is set to $0E at level start/respawn (`level_reset`). While `pod_destroying_player_timer` is running, `update_player_and_pod_states` (`thrust.6502:9741`) decrements it by 2 each frame. Fewer samples means a shorter delta, so the tether visibly contracts. When it goes negative the ship (`destroy_player_ship`) or attached pod (`destroy_attached_pod`) is destroyed.

---

## Deriving Ship and Pod Positions

### Ship Position

`calculate_player_position_from_midpoint` (`thrust.6502:6200`):

```
new_ship_pos = midpoint + midpoint_delta
```

X is a 16-bit add (FRAC, INT); neither `midpoint_xpos_FRAC_LO` nor `midpoint_deltax_FRAC_LO` is added in. Y is 24-bit (FRAC, INT, plus a sign-extended INT_HI).

### Velocity

The same routine computes the frame-to-frame ship movement before storing the new position:

```
player_velocityx = new_ship_xpos - player_xpos     ; borrow seeded from the midpoint FRAC_LO change
player_velocityy = new_ship_ypos - player_ypos     ; 3 bytes
```

`player_velocity` is added to bullet velocity when firing (`ship_input_fire`, `thrust.6502:7789`).

### Pod Position

`calculate_pod_pos` (`thrust.6502:9908`), called from `update_player_and_pod_states`:

```
pod_pos = midpoint - midpoint_delta + (4, 5)
```

X is FRAC/INT; Y uses whole units only (midpoint INT/INT_HI minus `midpoint_deltay_INT`; the result's low byte is stored in the confusingly named `pod_ypos_FRAC`). The +4/+5 offsets align the pod sprite with the mathematical position.

---

## Pod Attachment

### Tractor Beam (`do_pod_tractor_beam`, `thrust.6502:5225`)

Called from `update_pod_tractor_beam` (run at the end of the object loop) when the pod or its stand is on screen, the pod has not yet been lifted (`pod_attached_flag_2` clear) and the shield/tractor key is held; releasing the key clears `tractor_beam_started_flag`. It does nothing while a death countdown is running. `get_distance_ship_to_pod_tractor` (`thrust.6502:7900`) returns an approximate distance, `min + 3 × max` of |dy| and |dx × 4| in window coordinates, saturating at $FF:

1. Distance < `TRACTOR_BEAM_ACTIVATE_DIST` ($75): `tractor_beam_started_flag` is set and the beam line is drawn.
2. Distance >= `TRACTOR_BEAM_ATTACH_DIST` ($84): `attach_pod_to_ship` is called, which attaches only if `tractor_beam_started_flag` is already set.
3. $75-$83: no change.

So the pod is picked up when the ship, having first come within $75 with the beam on, pulls away past $84 and the tether goes taut.

### Attachment Initialisation (`attach_pod_to_ship`, `thrust.6502:5293`)

1. Set `pod_attached_flag_1`, `pod_attached_flag_2` and `level_reset_with_pod_flag` to $FF.

2. **Midpoint** = average of ship and pod (`nearest_obj_*pos`). X averages INT.FRAC (`midpoint_xpos_FRAC_LO` is not touched). Y averages INT_HI.INT, with $80 added to the ship's FRAC for rounding.

3. **Halve the velocity vector** (arithmetic shift right by 1), conserving momentum now that the mass has doubled.

4. **Target vector** = ship − midpoint, X scaled ×4 and Y ×2 to match the scaled tether vectors.

5. **Angle search**: 7 passes, each testing 3 candidate angles. The step starts at $0A.AB (32/3 angle units) and halves each pass; after each pass the best angle (smallest `min + 3 × max` error between `calculate_attached_pod_vector` and the target, via `get_distance_ship_to_pod_tractor_ext`) is kept and the start is rewound by half the new step. This is an atan2 done by search, yielding `angle_ship_to_pod` and `tether_angle_FRAC`.

6. **Initial angular velocity** from the cross product of velocity and displacement:
   ```
   tether_angular_vel (INT.FRAC) = ((vel_y << 4) * delta_x - (vel_x << 4) * delta_y) >> 2
   ```
   using `attach_pod_calculate_signed_multiply` on the top bits of each velocity component and the scaled target deltas. This turns the part of the ship's motion perpendicular to the tether into swing.

---

## Physics Parameters Summary

| Parameter | Value | Effect |
|---|---|---|
| Angle steps | 32 (0-31) | 11.25 degrees per step |
| Rotation rate | 3 of 4 frames | ~25 steps/s at 33fps |
| Physics tick rate | 6 of 16 frames | ~12 updates/s at 33fps |
| Gravity | $05-$0D / 256 per active tick | Per level; reversed every 6 levels |
| Thrust (normal) | table / 16 | ≤ 0.16 (Y), ≤ 0.08 (X) per active tick |
| Thrust (pod attached) | table / 32 | Half strength |
| X drag | × 63/64 per active tick | Strong horizontal damping |
| Y drag | × 255/256 per active tick | Weak vertical damping |
| Tether torque | thrusting, active ticks except $03, $0B | 4 of 6 active ticks |
| Tether angular drag | vel − vel/64 | Only when torque runs |

---

## Per-Frame Data Flow

```
Input:
  CAPS LOCK / CTRL  -->  ship_angle (0-31)
  SHIFT             -->  thrust

  1. ship_input_rotate
       ship_angle += 1 or -= 1               (3 of 4 frames)

  2. midpoint_add_velocity_vector
       midpoint_pos += velocity_vector       (from previous frame)
       tether_angle += tether_angular_vel    (if attached / dying)

  3. calculate_attached_pod_vector           (inside draw_player_timed_to_vsync)
       tether_angle -> midpoint_delta

  4. calculate_pod_pos                       (update_player_and_pod_states)
       pod_pos = midpoint - delta + (4,5)

  6. calculate_player_position_from_midpoint
       ship_pos = midpoint + delta
       player_velocity = ship_pos - old ship_pos

  7. ship_input_thrust_calculate_force       (6 of 16 frames)
       velocity_vectory += gravity
       if thrusting:
         velocity_vector += table[ship_angle] >> 4 (>> 5 with pod)
         if tick not $03/$0B:
           tether_angular_vel += tangential thrust
           tether_angular_vel -= old_vel / 64
       velocity_vectorx *= 63/64
       velocity_vectory *= 255/256
```
