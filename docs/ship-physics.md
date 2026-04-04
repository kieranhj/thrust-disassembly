# Ship Physics Technical Reference

## Overview

The physics simulation is built around a **midpoint** abstraction. All forces act on the midpoint (the centre of mass of the ship-pod system). The ship and pod positions are derived by offsetting from the midpoint in opposite directions along the tether vector. When the pod is detached, the midpoint equals the ship position.

---

## Tick Loop Execution Order

The main `tick_loop` (line 8483) calls physics functions in this order each frame:

```
 1. ship_input_rotate                          ; rotation input
 2. midpoint_add_force_vector                  ; integrate force into position + update tether angle
 3. draw_player_timed_to_vsync                 ; draws ship (calls calculate_attached_pod_vector)
 4. calculate_player_position_from_midpoint    ; derive ship/pod from midpoint +/- delta
 5. ship_input_thrust_calculate_force          ; gravity, thrust, drag, tether torque
```

The force computed in step 5 is integrated in step 2 of the **next** frame. This is a one-frame-behind Euler integration pattern.

---

## Fixed-Point Formats

| Variable | Bytes | Format | Notes |
|---|---|---|---|
| `force_vectorx` | 3 | Q7.16 signed | INT.FRAC.FRAC_LO |
| `force_vectory` | 2 | Q7.8 signed | INT.FRAC (less precision than X) |
| `midpoint_xpos` | 3 | Q8.16 unsigned | INT.FRAC.FRAC_LO (wraps horizontally) |
| `midpoint_ypos` | 3 | Q16.8 unsigned | INT_HI.INT.FRAC (tall world) |
| `tether_angle` | 3 | Q5.16 | angle_ship_to_pod (5-bit 0-31).FRAC.LO |
| `tether_angular_vel` | 3 | Q7.16 signed | INT.FRAC.LO |
| `player_velocityx` | 2 | Q7.8 signed | Frame-to-frame position delta |
| `player_velocityy` | 3 | Q15.8 signed | INT_HI.INT.FRAC |
| Angle lookup tables | 2 per entry | Q7.8 signed | 32 entries, elliptical magnitude |

---

## Rotation

`ship_input_rotate` (line 5153) reads keyboard input to adjust the ship angle:

- **CAPS LOCK** pressed: decrement `ship_angle` (rotate counter-clockwise)
- **CTRL** pressed: increment `ship_angle` (rotate clockwise)
- Result masked to 5 bits (`AND #$1F`): 32 discrete angles, 11.25 degrees each
- Angle 0 = pointing up, $10 (16) = pointing down
- Rate-limited: rotation skips every frame where `level_tick_counter AND 3 == 0` (3 out of 4 frames)

---

## Force Calculation

`ship_input_thrust_calculate_force` (line 3643) runs the full force update pipeline. It is **tick-gated**: gravity, thrust and drag only run on 6 of every 16 ticks (ticks $00, $03, $05, $08, $0B, $0D). On other ticks, the function returns immediately.

### Gravity

Applied unconditionally on active ticks, before thrust:

```
force_vectory_FRAC += gravity_FRAC
force_vectory_INT  += gravity_INT
```

Gravity is a level-specific 16-bit signed constant (`gravity_INT`/`gravity_FRAC` at ZP $A6/$A7). Positive Y is downward.

### Thrust

Thrust requires: ship not destroyed, fuel remaining, and SHIFT key pressed. When active, `use_fuel` and `run_engine` are called.

#### Angle-to-Force Lookup

The thrust direction comes from 32-entry lookup tables:

| Table | Address | Angle 0 (up) | Angle 8 (right) | Angle 16 (down) |
|-------|---------|-------------|-----------------|-----------------|
| `angle_to_y_INT/FRAC` | $0880/$08A0 | $FD.80 (-2.5) | $00.00 (0) | $02.80 (+2.5) |
| `angle_to_x_INT/FRAC` | $0980/$09A0 | $00.00 (0) | $01.40 (+1.25) | $00.00 (0) |

The Y range (~5.0) is larger than X (~2.5) to compensate for the non-square pixel aspect ratio in MODE 1.

#### Thrust Scaling

The table values are arithmetically right-shifted:
- **4 times** (divide by 16) normally
- **5 times** (divide by 32) when the pod is attached -- thrust is halved with the extra mass

The result is negated (thrust opposes the facing direction) and added to the force vector:

```
force_vectorx += -thrust_x_component
force_vectory += -thrust_y_component
```

X uses 3-byte precision (FRAC_LO, FRAC, INT); Y uses 2-byte (FRAC, INT).

### Drag / Damping

Applied on every active tick, whether thrusting or not:

**X drag** (strong):
```
force_vectorx -= force_vectorx / 64
```
Implemented as arithmetic-shift-right by 6 then subtraction. Each active tick multiplies by 63/64.

**Y drag** (weak):
```
force_vectory -= force_vectory / 256
```
Arithmetic-shift-right by 8 then subtraction. Each active tick multiplies by 255/256.

Y drag is much weaker because gravity continuously adds to Y velocity -- stronger drag would prevent the ship from falling properly.

---

## Tether Pendulum Physics

When the pod is attached, the tether connecting ship to pod behaves as a damped pendulum.

### Tether Torque from Thrust

On active ticks (except ticks $03 and $0B), the tangential component of thrust relative to the tether is computed:

1. **Relative angle**: `relative_angle = ship_angle - angle_ship_to_pod` (with sub-angle fractional offset from `tether_angle_FRAC`)

2. **Tangential force lookup**: The X-component of the thrust vector at the relative angle is read from `angle_to_x` tables. This represents the force component perpendicular to the tether -- the part that causes rotation rather than translation.

3. **Sub-angle interpolation**: A 15-iteration accumulation loop blends between adjacent angle table entries. The `lookup_top_nibble` table (`$10, $20, ..., $F0`) is compared against the top nibble of the fractional angle. When they match, the table index advances to the next angle entry. This produces a weighted sum where N samples use the base angle and (15-N) use the next, giving linear interpolation with 15 intermediate steps.

4. **Update angular velocity**:
   ```
   tether_angular_vel += tangential_thrust_component
   ```

### Angular Damping

After adding thrust torque, the old angular velocity (saved before the update) is shifted right by 6 (divided by 64) and subtracted:

```
tether_angular_vel -= old_tether_angular_vel / 64
```

This applies ~1.6% damping per active tick, preventing runaway rotation.

### No Gravity Torque

There is no explicit gravity torque term (no `sin(angle) * g`). This is physically correct: gravity acts equally on both the ship and pod, so it accelerates the centre of mass (the midpoint) without creating differential torque on the tether. The pendulum swings purely from thrust-induced torque and momentum.

---

## Position Integration

### Force to Midpoint Position

`midpoint_add_force_vector` (line 5186) integrates the force vector into the midpoint position each frame:

**X axis** (24-bit unsigned addition):
```
midpoint_xpos_FRAC_LO += force_vectorx_FRAC_LO
midpoint_xpos_FRAC    += force_vectorx_FRAC
midpoint_xpos_INT     += force_vectorx_INT
```

**Y axis** (24-bit addition with sign-extended carry into INT_HI):
```
midpoint_ypos_FRAC    += force_vectory_FRAC
midpoint_ypos_INT     += force_vectory_INT
midpoint_ypos_INT_HI  += sign_extension + carry
```

If `force_vectory_INT` is positive, carry-out increments INT_HI. If negative, lack of carry (borrow) decrements it.

### Tether Angle Integration

When the pod is attached, the tether swing angle is updated each frame:

```
tether_angle_LO   += tether_angular_vel_LO
tether_angle_FRAC += tether_angular_vel_FRAC
angle_ship_to_pod += tether_angular_vel_INT
angle_ship_to_pod  = angle_ship_to_pod AND $1F    ; wrap to 0-31
```

---

## Tether Angle to Delta Vector

`calculate_attached_pod_vector` (line 4388) converts the tether angle into a displacement vector (`midpoint_delta`) that offsets the ship and pod from the midpoint.

### Sub-Angle Interpolation

1. Round the fractional angle: `pod_angle_sub_frac = tether_angle_FRAC + $08`
2. Read base vector from angle tables at `angle_ship_to_pod` (with carry from rounding)
3. Run 15-iteration interpolation loop:
   - Compare `pod_angle_sub_frac` top nibble against `lookup_top_nibble[X]`
   - When they match, advance to the next angle table entry
   - Accumulate the table value at the current entry into the running sum
4. Arithmetic-shift-right the result by 2 (divide by 4)

The 16 accumulated samples divided by 4 give a net scaling of 4x the base table magnitude, with smooth interpolation between the 32 discrete angle steps.

### Tether Contraction During Destruction

During pod destruction, `top_nibble_index` is decremented by 2 each frame. This reduces the interpolation loop count, shrinking the delta vector. The tether visually contracts until destruction completes.

---

## Deriving Ship and Pod Positions

### Ship Position

`calculate_player_position_from_midpoint` (line 5249):

```
player_pos = midpoint + midpoint_delta
```

24-bit addition for X (FRAC_LO, FRAC, INT) and Y (FRAC, INT, INT_HI with sign extension).

### Pod Position

`calculate_pod_pos` (line 8822):

```
pod_pos = midpoint - midpoint_delta + centering_offset
```

The centering offsets (+4 for X, +5 for Y) align the pod sprite visually with the mathematical position.

### Velocity

Player velocity is computed as the frame-to-frame position difference:

```
player_velocityx = new_ship_xpos - old_player_xpos
player_velocityy = new_ship_ypos - old_player_ypos
```

Velocity is used for bullet velocity inheritance (bullets inherit the ship's velocity when fired).

---

## Pod Attachment

### Tractor Beam Activation (`do_pod_tractor_beam`, line 4491)

Attachment is a two-stage process using Manhattan distance from ship to pod:

1. Distance < $75: `tractor_beam_started_flag` is set (beam becomes visible)
2. Distance >= $84: `attach_pod_to_ship` is called (pod locks on)
3. Between $75 and $83: dead zone, no action

This prevents instant attachment and creates the visual tractor beam effect.

### Attachment Initialisation (`attach_pod_to_ship`, line 4526)

When the pod attaches:

1. **Calculate midpoint** as the average of ship and pod positions:
   ```
   midpoint = (player_pos + nearest_obj_pos) / 2
   ```

2. **Halve the force vector** (arithmetic shift right by 1) -- the combined system has twice the mass, so existing velocity produces half the acceleration.

3. **Binary search for initial tether angle**: A 7-level refinement search (4 candidates per level) finds the `angle_ship_to_pod` and `tether_angle_FRAC` whose computed delta vector best matches the actual ship-to-midpoint displacement.

4. **Calculate initial angular velocity** from the cross product of force and displacement:
   ```
   angular_vel = (force_y * delta_x - force_x * delta_y) / 4
   ```
   This projects the ship's linear momentum into rotational momentum around the tether -- how much of the existing velocity becomes swing.

---

## Physics Parameters Summary

| Parameter | Value | Effect |
|---|---|---|
| Angle steps | 32 (0-31) | 11.25 degrees per step |
| Rotation rate | 3 out of 4 frames | ~8.4 steps/second at 50fps |
| Physics tick rate | 6 out of 16 ticks | ~18.75 updates/second at 50fps |
| Thrust (normal) | table_value / 16 | ~0.16 per tick |
| Thrust (pod attached) | table_value / 32 | Half strength |
| X drag | 63/64 per active tick | Strong horizontal damping |
| Y drag | 255/256 per active tick | Weak vertical damping |
| Tether angular drag | vel - vel/64 per active tick | ~1.6% per tick |
| Tether torque gating | Skips ticks $03, $0B | 4 of 6 active ticks |

---

## Complete Per-Frame Data Flow

```
Input:
  CAPS LOCK / CTRL  -->  ship_angle (0-31)
  SHIFT             -->  thrust active flag

Physics Pipeline:
  1. ship_input_rotate
       keyboard -> ship_angle += 1 or -= 1

  2. midpoint_add_force_vector
       midpoint_pos += force_vector          (from previous frame)
       angle_ship_to_pod += tether_angular_vel

  3. calculate_attached_pod_vector
       angle_ship_to_pod -> midpoint_delta   (via trig tables + interpolation)

  4. calculate_player_position_from_midpoint
       player_pos = midpoint + delta
       pod_pos    = midpoint - delta
       velocity   = player_pos - old_player_pos

  5. ship_input_thrust_calculate_force
       force_vectory += gravity                         (always)
       force_vector  += thrust_from_angle               (if thrusting)
       tether_angular_vel += tangential_thrust           (if pod attached)
       tether_angular_vel -= tether_angular_vel / 64     (damping)
       force_vectorx *= 63/64                            (X drag)
       force_vectory *= 255/256                          (Y drag)

Output:
  player_xpos, player_ypos       -->  ship screen position
  pod_xpos, pod_ypos             -->  pod screen position
  player_velocityx, velocityy    -->  bullet velocity inheritance
  force_vector{x,y}              -->  fed back to step 2 next frame
  tether_angular_vel             -->  fed back to step 2 next frame
```
