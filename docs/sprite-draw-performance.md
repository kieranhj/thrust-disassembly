# Sprite Draw Performance Analysis

## Overview

Thrust renders four categories of sprite every frame: the **ship** (17 rotation angles + shield), the **pod** (towed payload), **static objects** (guns, fuel, generator, door switches, pod stand), and **particles** (bullets, thrust exhaust, stars, debris). All sprites use XOR (EOR) drawing for flicker-free erase-then-draw animation.

**Target platform:** BBC Micro Model B, 2 MHz 6502A. At 50 Hz, one frame = 40,000 cycles (39,936 exact).

---

## Frame Budget Context

The main game loop (`tick_loop`, line 8649) calls rendering routines in this order:

| Phase | Routine | Colour marker |
|---|---|---|
| 1 | `draw_player_timed_to_vsync` (ship + pod + tether line) | Red |
| 2 | `update_and_draw_all_objects` (static sprites) | Blue |
| 3 | `landscape_draw` (terrain) | Magenta |
| 4 | `tick_fuel_pickup_draw_beams` (fuel beams) | — |
| 5 | `particles_update_and_draw` (bullets, exhaust, stars) | Cyan |

The background colour debug markers (`SET_BG_COL`) in the source allow visual timing on hardware — each colour band on the border shows the time spent in that phase.

The landscape draw alone consumes ~64% of the frame during typical scrolling (see `landscape-draw-performance.md`). This leaves roughly **14,000 cycles** for all sprite drawing, physics, input, and sound. Understanding the sprite costs is critical for determining whether the frame budget is achievable.

---

## Ship Sprite Rendering

### Data Format

Ship sprites use a single-stream format where each byte < `$80` is a pixel position and each byte >= `$80` is a row advance marker. Values `$81`–`$FE` serve double duty: they signal "end of row" AND encode the first pixel of the next row (bit 7 is masked out during coordinate extraction).

Ship sprite 0 (upright) has 38 pixels across 16 rows. Across all 17 rotation frames, pixel counts range from 38–41 with 13–16 rows.

### Plot Routine (`plot_ship_loop`, line 4379)

The ship plotter uses three self-modified `LDA sprite_data,X` instructions, all patched to the same data address. This avoids an extra branch — after a row advance, execution falls directly into the appropriate re-read instruction without needing to reload X.

#### Per-Pixel Cycle Count (Draw Mode)

In draw mode, the collision test site is patched to `JMP plot_ship_loop` (3 cycles), bypassing the `AND + BEQ` test.

```
plot_ship_loop:
    LDX  plot_ship_index         ; 3  (ZP)
    INX                          ; 2
    STX  plot_ship_index         ; 3  (ZP)
    LDA  sprite_data,X           ; 4  (abs,X — self-modified)
    BMI  row_advance             ; 2  (not taken)
plot_ship_inner_loop:
    SEC                          ; 2
    CMP  #$FF                    ; 2  (self-modified: CMP keeps A, clears carry)
    ADC  plot_ship_pixel_column  ; 3  (ZP)
    TAY                          ; 2
    AND  #$3C                    ; 2
    ROL  A                       ; 2
    STA  plot_ship_at_y_offset   ; 3  (ZP)
    TYA                          ; 2
    AND  #$03                    ; 2
    TAX                          ; 2
    LDA  pixel_masks_1,X         ; 4  (abs,X — self-modified)
    LDY  plot_ship_at_y_offset   ; 3  (ZP)
    EOR  (plot_ship_at_ptr),Y    ; 5  (ind,Y)
    STA  (plot_ship_at_ptr),Y    ; 6  (ind,Y)
    JMP  plot_ship_loop          ; 3  (self-modified: replaces AND+BEQ)
                                 ; ----
                                 ; 59 cycles per pixel
```

#### Per-Pixel Cycle Count (Erase Mode, No Collision)

In erase mode, the collision test site is `AND pixel_masks_1,X` + `BEQ plot_ship_loop`:

```
    ...same as above through STA...
    AND  pixel_masks_1,X         ; 4  (abs,X)
    BEQ  plot_ship_loop          ; 3  (taken = no collision)
                                 ; ----
                                 ; 63 cycles per pixel
```

#### Per-Pixel Cycle Count (Erase Mode, Collision Detected)

```
    AND  pixel_masks_1,X         ; 4
    BEQ  (not taken)             ; 2
    LDA  #$FF                    ; 2
    STA  collision_detected      ; 3  (ZP)
    JMP  plot_ship_loop          ; 3
                                 ; ----
                                 ; 70 cycles per pixel
```

#### Row Advance (Within Character Cell)

When a byte >= `$80` is encountered, the code advances to the next pixel row:

```
    LDA  sprite_data,X           ; 4  (abs,X)
    BMI  L1F1F                   ; 3  (taken)
    CMP  #$FF                    ; 2
    BEQ  return                  ; 2  (not taken)
    LDX  plot_ship_index         ; 3  (ZP — reload X)
    DEC  plot_ship_row_counter   ; 5  (ZP)
    BMI  char_crossing           ; 2  (not taken)
    INC  plot_ship_at_ptr        ; 5  (ZP)
    LDA  sprite_data,X           ; 4  (abs,X — re-read same byte)
    CMP  #$80                    ; 2
    BNE  inner_loop              ; 3  (taken: pixel data)
                                 ; ----
                                 ; 35 cycles overhead
```

If the re-read value is `$80` (empty row, no pixel), the branch falls through to `JMP plot_ship_loop` (+3 cycles, total 38), and the pixel plot is skipped entirely.

#### Row Advance (Character Row Crossing)

When `plot_ship_row_counter` goes negative (every 8th pixel row):

```
    DEC  plot_ship_row_counter   ; 5  (ZP)
    BMI  char_crossing           ; 3  (taken)
    LDA  #$07                   ; 2
    STA  plot_ship_row_counter   ; 3  (ZP)
    CLC                          ; 2
    LDA  plot_ship_at_ptr        ; 3  (ZP)
    ADC  #$39                    ; 2
    STA  plot_ship_at_ptr        ; 3  (ZP)
    LDA  plot_ship_at_ptr+1      ; 3  (ZP)
    ADC  #$02                    ; 2
    STA  plot_ship_at_ptr+1      ; 3  (ZP)
    LDA  sprite_data,X           ; 4  (re-read)
    CMP  #$80                    ; 2
    BNE  inner_loop              ; 3
                                 ; ----
                                 ; 55 cycles overhead (vs 35 normal)
```

The offset `$0239` = `$0240 - 7` accounts for the 7 bytes traversed within the character cell before the boundary.

### Setup (`plot_ship_or_sheild`, line 4323)

Called once per draw or erase pass:

```
Setup sprite data pointers:
    6 x STA (self-mod addrs)     ; 24  (abs stores)
    2 x LDA table,Y              ; 8   (abs,Y)
    TAY + initial LDAs           ; ~10
                                 ; ----
                                 ; ~42 cycles

Opcode/operand patching:
    LDA + STA (mask addr LO)     ; 6
    LDA + STA (mask addr HI)     ; 6
    LDA + STA (opcode)           ; 6
    LDA + STA (operand)          ; 6
                                 ; ----
                                 ; ~24 cycles

Row counter init:
    LDA + AND + EOR + STA        ; 10
    LDX #$00                     ; 2
    JMP plot_ship_start          ; 3
                                 ; ----
                                 ; 15 cycles

Total setup: ~81 cycles
```

### Screen Address Calculation (line 4261)

```
Y contribution (shift chain):
    LDA + STA (clear)            ; 5
    LDA + CLC + AND              ; 6
    5 x ROR/ROR                  ; 10
    2 x ADC + STA                ; 10
                                 ; ----
                                 ; ~31 cycles

X contribution (table lookup):
    LDY + 2x(LDA + ADC + STA)   ; 17
                                 ; ----
                                 ; ~17 cycles

Pixel row offset:
    LDA + AND + ADC + STA        ; 10
                                 ; ----
                                 ; ~10 cycles

Total screen addr calc: ~58 cycles
```

### Collision Test Mode Copy

The erase/draw orchestration copies 3 bytes to switch between AND-mode and JMP-mode:

```
    LDX  #$02                    ; 2
    .loop:
    LDA  code,X                  ; 4  (abs,X)
    STA  target,X                ; 5  (abs,X)
    DEX                          ; 2
    BPL  loop                    ; 3  (taken x2, not taken x1)
                                 ; ----
                                 ; 2 + 3*(4+5+2) + 2*3 + 2 = 43 cycles
```

### Per-Frame Ship Cost

Using ship sprite 0 (38 pixels, 16 rows, ~2 character row crossings):

| Component | Erase | Draw |
|---|---|---|
| Mode copy (3 bytes) | 43 | 43 |
| Setup (`plot_ship_or_sheild`) | 81 | 81 |
| Screen address calculation | 58 | 58 |
| Old state restore/save | ~30 | ~30 |
| Pixel plotting (38 pixels) | 38 × 63 = 2,394 | 38 × 59 = 2,242 |
| Row advances (14 normal) | 14 × 35 = 490 | 14 × 35 = 490 |
| Row advances (2 char crossing) | 2 × 55 = 110 | 2 × 55 = 110 |
| **Subtotal** | **3,206** | **3,054** |

**Total ship per frame: ~6,260 cycles (15.7% of frame)**

For mirrored sprites (angles 9–16), the `EOR #$1F` opcode is used instead of `CMP #$FF`. This EOR flips the pixel X coordinate for horizontal mirroring. The cycle count is identical — the opcode `EOR imm` takes the same 2 cycles as `CMP imm`.

---

## Pod Sprite Rendering

### Data Format

The pod uses the identical single-stream format as the ship. It has a single sprite (no rotation), stored at `pod_sprite_data` (line 2263). The pod sprite has 28 pixels across 11 rows.

### Plot Routine (`plot_pod_sprite`, line 5074)

The pod plotter is a near-clone of the ship plotter, with the same three self-modified `LDA` instructions for the data stream and the same pixel plotting logic. The key differences:

- Includes inline screen address calculation (ship does this externally)
- Calls `set_plot_pod_sprite_mask_addr` (JSR, ~40 cycles) twice — once for setup, once before the plot loop
- The collision flag STA address is self-modified (`plot_pod_sprite_addr_zp`), allowing the same routine to write to different collision flag ZP addresses

#### Per-Pixel Cost

Identical to ship: **59 cycles** (draw), **63 cycles** (erase, no collision).

### Per-Frame Pod Cost

Only drawn when the pod is attached (tether active). With 28 pixels and 11 rows (~1 char crossing):

| Component | Erase | Draw |
|---|---|---|
| Mode copy + orchestration | ~80 | ~80 |
| Screen address calculation | ~58 | ~58 |
| `set_plot_pod_sprite_mask_addr` (×2) | ~80 | ~80 |
| Sprite data pointer setup | ~30 | ~30 |
| Pixel plotting (28 pixels) | 28 × 63 = 1,764 | 28 × 59 = 1,652 |
| Row advances (10 normal) | 10 × 35 = 350 | 10 × 35 = 350 |
| Row advances (1 char crossing) | 55 | 55 |
| **Subtotal** | **2,417** | **2,305** |

**Total pod per frame: ~4,722 cycles (11.8% of frame)**

This cost is zero when the pod is not attached.

---

## Tether Line Rendering

### Algorithm

The tether line uses a Bresenham line-drawing algorithm (`draw_line`, line 7135). It plots individual pixels using XOR with `pixel_masks_1` (colour 3). The line is drawn twice per frame: once to erase the old line, once to draw the new line.

### Per-Pixel Cost

```
plot_line_pixels:
    LDY  pixel_column_index      ; 3  (ZP)
    LDA  pixel_masks_1,Y         ; 4  (abs,Y)
    AND  plot_line_pixels_byte   ; 3  (ZP)
    LDY  #$00                    ; 2
    EOR  (plot_pixels_ptr),Y     ; 5  (ind,Y)
    STA  (plot_pixels_ptr),Y     ; 6  (ind,Y)
    DEX                          ; 2
    BNE  plot_line_bresenham_1   ; 3  (taken)
                                 ; ----
                                 ; 28 cycles per pixel (plot only)

plot_line_bresenham_1:
    JSR  step_function           ; 6 + ~20 (self-modified JSR target)
    LDA  bresenham_error         ; 3  (ZP)
    CLC                          ; 2
    ADC  draw_line_delta_minor   ; 3  (ZP)
    BCS  bresenham_2             ; 2  (not taken, common case)
    CMP  draw_line_delta_major   ; 3  (ZP)
    BCS  bresenham_2             ; 2  (not taken)
    STA  bresenham_error         ; 3  (ZP)
                                 ; ----
                                 ; ~44 cycles (minor step only)
                                 ; ~60 cycles (major + minor step)
```

Typical per-pixel (mixed stepping): **~50 cycles**.

### Per-Frame Tether Cost

The tether line length depends on the distance between ship and pod. Typical range: 20–60 pixels.

| Component | Erase | Draw |
|---|---|---|
| Setup (`draw_line` + Bresenham init) | ~120 | ~120 |
| Screen address calc (`calculate_pixels_ptr`) | ~50 | ~50 |
| Per-pixel plotting (40 pixels typical) | 40 × 50 = 2,000 | 40 × 50 = 2,000 |
| **Subtotal** | **~2,170** | **~2,170** |

**Total tether per frame: ~4,340 cycles (10.9% of frame)**

Only drawn when the pod is attached. Combined with the pod sprite, attaching the tether adds ~9,000 cycles to each frame.

---

## Static Object Sprite Rendering

### Data Format

Objects use a two-stream format. Stream A provides byte offsets (Y register values for indirect addressing) and row-advance markers. Stream B provides complete MODE 1 screen bytes — 4 pixels per byte with 2-bit colour depth — that are XOR'd onto the screen. This is more efficient than per-pixel plotting for wider, denser sprites.

### Plot Routine (`plot_static_sprite`, line 2064)

```
Setup:
    LDX  current_object          ; 3  (ZP)
    LDA  level_obj_flags,X       ; 4  (abs,X)
    ORA  #$01                    ; 2
    STA  level_obj_flags,X       ; 5  (abs,X)
    LDA  plot_sprite_at_ptr      ; 3  (ZP)
    AND  #$07                    ; 2
    EOR  #$07                    ; 2
    STA  sprite_rows_to_boundary ; 3  (ZP)
    INC  sprite_rows_to_boundary ; 5  (ZP)
    LDX  #$00                    ; 2
    JMP  L11DB                   ; 3
                                 ; ----
                                 ; 34 cycles setup
```

#### Per-Byte-Plot (No Row Advance)

```
L11DB:
    LDY  sprite_data_A,X         ; 4  (abs,X — self-modified)
    BPL  L11D3                   ; 3  (taken: value < $80)
L11D3:
    LDA  sprite_data_B,X         ; 4  (abs,X — self-modified)
    EOR  (plot_sprite_at_ptr),Y  ; 5  (ind,Y)
    STA  (plot_sprite_at_ptr),Y  ; 6  (ind,Y)
    INX                          ; 2
                                 ; ----
                                 ; 24 cycles per byte-plot
```

Each byte-plot writes 4 pixels in a single EOR, making this **6 cycles per pixel** — vastly more efficient than the per-pixel ship format (59 cycles per pixel).

#### Row Advance (Within Character Cell)

```
    LDY  sprite_data_A,X         ; 4
    BPL  ...                     ; 2  (not taken: bit 7 set)
    CPY  #$FF                    ; 2
    BNE  L11B3                   ; 3  (taken: not end marker)
L11B3:
    INC  plot_sprite_at_ptr      ; 5  (ZP)
    TYA                          ; 2
    AND  #$7F                    ; 2
    TAY                          ; 2
    DEC  sprite_rows_to_boundary ; 5  (ZP)
    BNE  L11D3                   ; 3  (taken)
L11D3:
    LDA  sprite_data_B,X         ; 4
    EOR  (ptr),Y                 ; 5
    STA  (ptr),Y                 ; 6
    INX                          ; 2
                                 ; ----
                                 ; 47 cycles (row advance + first byte-plot)
```

#### Row Advance (Character Row Crossing)

When `sprite_rows_to_boundary` reaches zero:

```
    DEC  sprite_rows_to_boundary ; 5
    BNE  ...                     ; 2  (not taken)
    DEC  plot_sprite_at_ptr      ; 5  (ZP — undo the INC)
    LDA  plot_sprite_at_ptr      ; 3  (ZP)
    ADC  #$39                    ; 2
    STA  plot_sprite_at_ptr      ; 3  (ZP)
    LDA  plot_sprite_at_ptr+1    ; 3  (ZP)
    ADC  #$02                    ; 2
    STA  plot_sprite_at_ptr+1    ; 3  (ZP)
    LDA  #$08                   ; 2
    STA  sprite_rows_to_boundary ; 3  (ZP)
    TYA                          ; 2
    AND  #$7F                    ; 2
    TAY                          ; 2
                                 ; ----
                                 ; 78 cycles (crossing + first byte-plot)
```

### Object Sprite Sizes

| Object | Stream A+B bytes | Rows | Char crossings | Typical cost |
|---|---|---|---|---|
| Gun (any direction) | 33 | ~14 | 1 | ~1,000 |
| Fuel | 44 | ~14 | 1 | ~1,300 |
| Pod stand | 37 | ~19 | 2 | ~1,200 |
| Generator | 43 | ~18 | 2 | ~1,350 |
| Door switch (either) | 16 | ~14 | 1 | ~600 |

### Object Update Loop (`update_and_draw_all_objects`, line 1438)

For each object, the loop:
1. Reads object type and gun parameters (self-modified addresses) — ~25 cycles
2. Sets up 4 self-modified sprite data pointers — ~32 cycles
3. Calls `object_visibility_test` — ~40 cycles (cull) or ~80 cycles (visible)
4. If visible and position changed: erase at old position + draw at new position = 2 × plot cost
5. If visible and unchanged: skip both draws — ~10 cycles
6. Gun firing logic, bullet collision, fuel pickup — ~50-200 cycles (conditional)

#### Per-Object Overhead (Visible, Position Unchanged)

The most common case during static camera:
```
    Type/param load + pointer setup + visibility test + position compare + skip
    ~25 + 32 + 80 + 20 + 10 = ~167 cycles
```

#### Per-Object Cost (Visible, Position Changed)

```
    Overhead + screen addr calc + erase + draw
    ~167 + 58 + ~1,100 + ~1,100 = ~2,425 cycles (typical gun/fuel)
```

#### Per-Object Cost (Off-Screen, Culled)

```
    Type/param load + pointer setup + visibility fail
    ~25 + 32 + 40 = ~97 cycles
```

### Per-Frame Object Cost

A typical level has 15–25 objects. During scrolling, perhaps 8–12 are visible. Of those, most have changed position (the viewport moved).

| Scenario | Visible | Off-screen | Cost |
|---|---|---|---|
| Static view | 10 unchanged, 12 culled | — | 10×167 + 12×97 = **2,834** |
| Slow scroll | 10 redrawn, 12 culled | — | 10×2,425 + 12×97 = **25,414** |
| Fast scroll | 8 redrawn, 14 culled | — | 8×2,425 + 14×97 = **20,758** |

**Typical object cost per frame: ~2,800–25,400 cycles (7–64% of frame)**

Objects are the second most expensive rendering system after the landscape during scrolling.

---

## Particle Rendering

### Data Format

Particles are not traditional sprites — each particle is a single byte-pair (2 adjacent screen bytes) XOR'd at a computed screen address. The particle system supports up to 32 simultaneous particles (`PARTICLE_table_max = $1F`).

### Per-Particle Cycle Count

#### Erase Phase (particle has `PARTICLE_flag` set in lifetime)

```
    LDA  particles_lifetime,X    ; 4  (abs,X)
    BPL  skip                    ; 2  (not taken)
    AND  #($FF EOR flag)         ; 2
    STA  particles_lifetime,X    ; 5  (abs,X)
    LDA  scraddr_LO,X           ; 4  (abs,X)
    STA  particle_write_ptr      ; 3  (ZP)
    LDA  scraddr_HI,X           ; 4  (abs,X)
    STA  particle_write_ptr+1    ; 3  (ZP)
    LDY  #$00                    ; 2
    LDA  pixels_byte,X           ; 4  (abs,X)
    PHA                          ; 3
    EOR  (particle_write_ptr),Y  ; 5
    STA  (particle_write_ptr),Y  ; 6
    PLA                          ; 4
    INY                          ; 2
    EOR  (particle_write_ptr),Y  ; 5
    STA  (particle_write_ptr),Y  ; 6
                                 ; ----
                                 ; ~64 cycles (erase 2 bytes = 8 pixels)
```

#### Update Phase (physics + visibility)

```
    Lifetime decrement             ; ~10
    test_particle_X_close_to_player ; 6 (JSR) + ~30 (body) = ~36
    particle_move_index_X          ; 6 (JSR) + ~40 (position update) = ~46
    Pixel byte lookup              ; ~10
    Visibility test (Y range)      ; ~20
    Visibility test (terrain)      ; ~15
    Visibility test (X range)      ; ~15
                                   ; ----
                                   ; ~152 cycles
```

#### Draw Phase (visible particle)

```
    Screen address calculation     ; ~58 (same shift chain as ship)
    Pixel row clamping             ; ~10
    Pixel column lookup            ; ~15
    EOR byte 1                     ; 5+6 = 11
    Collision test byte 1          ; ~10
    EOR byte 2                     ; 5+6 = 11
    Collision test byte 2          ; ~10
    Store screen address           ; ~8
                                   ; ----
                                   ; ~133 cycles
```

### Per-Frame Particle Cost

Typical active particles: 5–15 (stars + thrust exhaust + occasional bullets).

| Component | Per particle | 10 particles |
|---|---|---|
| Erase (if drawn last frame) | 64 | 640 |
| Update (physics + visibility) | 152 | 1,520 |
| Draw (if visible) | 133 | 1,330 |
| Inactive slot (lifetime = 0) | ~8 | varies |
| **Total per active particle** | **~349** | **3,490** |

Plus `particles_generate_stars` overhead: ~200 cycles.

**Typical particle cost per frame: ~3,700 cycles (9.3% of frame)**

Worst case (32 active particles): ~11,400 cycles.

---

## Complete Frame Budget

### Scenario 1: Static View, No Pod

| System | Cycles | % of frame |
|---|---|---|
| Landscape draw | 11,580 | 29.0% |
| Ship (erase + draw) | 6,260 | 15.7% |
| Objects (10 visible, unchanged) | 2,834 | 7.1% |
| Particles (10 active) | 3,700 | 9.3% |
| Physics + input + sound | ~3,000 | 7.5% |
| **Total** | **~27,374** | **68.4%** |

Comfortable headroom — **~12,600 cycles spare**.

### Scenario 2: Slow Scroll, Pod Attached

| System | Cycles | % of frame |
|---|---|---|
| Landscape draw | 25,460 | 63.7% |
| Ship (erase + draw) | 6,260 | 15.7% |
| Pod (erase + draw) | 4,722 | 11.8% |
| Tether line (erase + draw) | 4,340 | 10.9% |
| Objects (10 visible, redrawn) | 25,414 | 63.5% |
| Particles (10 active) | 3,700 | 9.3% |
| Physics + input + sound | ~3,000 | 7.5% |
| **Total** | **~72,896** | **182.2%** |

**This exceeds the frame budget by 82%.** The game relies on the system clock timing in `draw_player_timed_to_vsync` — it waits for at least 3 centisecond ticks (0.03 seconds) per frame, which is 60,000 cycles at 2 MHz. This gives roughly 1.5 frames worth of time. Additionally, the game naturally runs at a variable frame rate; scrolling with the pod attached and many visible objects will drop to ~25 fps.

### Scenario 3: Fast Scroll, No Pod, Many Objects

| System | Cycles | % of frame |
|---|---|---|
| Landscape draw | 42,000 | 105.0% |
| Ship (erase + draw) | 6,260 | 15.7% |
| Objects (8 redrawn) | 20,758 | 51.9% |
| Particles (15 active) | 5,400 | 13.5% |
| Physics + input + sound | ~3,000 | 7.5% |
| **Total** | **~77,418** | **193.6%** |

Again well over budget — the game visibly drops frames during fast scrolling.

---

## Bottleneck Analysis

### Cycles per Pixel by System

| System | Cycles/pixel | Pixels/byte | Effective cycles/pixel |
|---|---|---|---|
| Ship (draw) | 59 | 1 | 59.0 |
| Ship (erase) | 63 | 1 | 63.0 |
| Pod (draw) | 59 | 1 | 59.0 |
| Tether line | ~50 | 1 | ~50.0 |
| Object sprite | 24 | 4 | **6.0** |
| Particle | ~22 | 8 | **~2.8** |
| Landscape | 27 | 4 | **6.75** |

The ship and pod are **10× more expensive per pixel** than objects. This is the fundamental cost of per-pixel single-colour wireframe drawing vs. per-byte multi-colour block drawing.

### Time Breakdown by Operation (Ship Pixel)

Of the 59 cycles per ship pixel (draw mode):

| Operation | Cycles | % |
|---|---|---|
| Loop overhead (LDX/INX/STX) | 8 | 13.6% |
| Data fetch (LDA sprite_data,X + BMI) | 6 | 10.2% |
| X coordinate decode (SEC→TAX) | 19 | 32.2% |
| Mask table lookup | 4 | 6.8% |
| Screen offset load (LDY) | 3 | 5.1% |
| Screen read-modify-write (EOR+STA indirect) | 11 | 18.6% |
| Collision skip (JMP) | 3 | 5.1% |
| **Total overhead** | **48** | **81.4%** |
| **Actual screen write** | **11** | **18.6%** |

Only 18.6% of the per-pixel time is spent on actual screen writes. The coordinate decoding (32.2%) and loop management (13.6%) dominate.

---

## Optimisation Suggestions

### 1. Pre-decode Ship Sprite Coordinates (Save ~19 cycles/pixel)

**Current cost:** 19 cycles of X coordinate decoding per pixel (SEC, CMP/EOR, ADC, TAY, AND, ROL, STA, TYA, AND, TAX).

**Proposal:** Pre-process sprite data at level load into a decoded format where each byte directly provides:
- The screen byte offset (what `plot_ship_at_y_offset` becomes)
- The pixel mask table index

Store these as two parallel arrays per sprite frame (like the object two-stream format). The plot loop becomes:

```asm
    LDY  sprite_offset,X         ; 4  (abs,X)
    LDA  sprite_mask,X           ; 4  (abs,X)
    EOR  (plot_ship_at_ptr),Y    ; 5
    STA  (plot_ship_at_ptr),Y    ; 6
    INX                          ; 2
    BNE  loop                    ; 3
                                 ; ----
                                 ; 24 cycles per pixel
```

**Savings:** 35 cycles/pixel. For 38 pixels × 2 passes = **2,660 cycles/frame** (~6.7% of frame).

**Trade-off:** Each decoded sprite needs 2 bytes per pixel × ~40 pixels × 17 frames = ~1,360 bytes of pre-decoded data. The original compressed data is ~650 bytes total. However, this eliminates the need for the sub-character pixel column (`plot_ship_pixel_column`) addition, so the pre-decoded data would need 4 variants (one per pixel column offset 0–3), requiring ~5,440 bytes. This may be prohibitive.

**Alternative:** Pre-decode only the `(offset, mask_index)` pair without baking in the pixel column. Keep the pixel column addition but skip the bitfield extraction:

```asm
    LDA  sprite_offset_raw,X    ; 4  (abs,X)
    ADC  pixel_column            ; 3  (ZP)
    TAY                          ; 2
    AND  #$3C                    ; 2
    ROL  A                       ; 2
    STA  y_offset                ; 3  (ZP)
    ; ...still need mask lookup from low 2 bits...
```

This doesn't actually save much because the coordinate encoding IS the bottleneck, and it can't be simplified without pre-baking the pixel column.

### 2. Unroll the Ship Plot Loop (Save ~8 cycles/pixel)

**Current cost:** 8 cycles loop overhead (LDX/INX/STX at `plot_ship_loop`).

**Proposal:** Unroll the pixel loop body N times, using a computed jump to enter at the right offset for the pixel count. The sprite data stream pointer advances implicitly via INX within the unrolled body. Row advance checks (BMI) remain inline.

```asm
    ; Unrolled body (repeated N times):
    INX
    LDA  sprite_data,X
    BMI  row_advance_N
    ; ...pixel plot (no LDX/STX)...
```

**Savings:** 8 cycles/pixel × 38 pixels = 304 cycles per pass, 608 per frame. Modest but free in terms of data size.

**Trade-off:** Code size increases by ~40 bytes per unrolled iteration. Unrolling 8 iterations adds ~320 bytes. The row advance handling becomes more complex (each unrolled slot needs its own row advance target that falls through correctly).

### 3. Replace Indirect Addressing with Self-Modified Absolute (Save ~2 cycles/pixel)

**Current:** `EOR (plot_ship_at_ptr),Y` (5 cycles) + `STA (plot_ship_at_ptr),Y` (6 cycles) = 11 cycles.

**Proposal:** Self-modify the address operand and use absolute indexed:

```asm
    EOR  screen_addr,Y           ; 4  (self-modified abs,Y)
    STA  screen_addr,Y           ; 5  (self-modified abs,Y)
                                 ; ----
                                 ; 9 cycles (saves 2)
```

**Savings:** 2 cycles/pixel × 38 × 2 = 152 cycles/frame.

**Trade-off:** Two more self-modified code sites. The address must be updated on every row advance. Low risk, low reward.

### 4. Combined Two-Stream Ship Format (Save ~35 cycles/pixel)

**Proposal:** Convert ship sprites to the same two-stream format used by objects. Pre-compute a stream A (screen byte offsets including row advances) and stream B (pixel mask bytes). The plot loop becomes identical to `plot_static_sprite`:

```asm
    LDY  stream_A,X              ; 4
    BPL  plot                    ; 3
    ; row advance...
.plot:
    LDA  stream_B,X              ; 4
    EOR  (ptr),Y                 ; 5
    STA  (ptr),Y                 ; 6
    INX                          ; 2
                                 ; ----
                                 ; 24 cycles per pixel (same as objects)
```

**Savings:** 35 cycles/pixel × 38 × 2 = **2,660 cycles/frame**.

**Trade-off:** Loses the per-pixel-column flexibility — the stream B mask bytes would need to be pre-computed for each of the 4 possible sub-character pixel columns. This means 4 copies of each sprite's B stream: 4 × ~40 bytes × 17 frames = ~2,720 bytes. Stream A is shared across all pixel columns (same offsets), adding ~40 × 17 = 680 bytes. Total: ~3,400 bytes vs ~650 bytes original.

However, this approach also eliminates the need for the pixel mask table lookup, the coordinate decoding, and the loop overhead in one stroke. **The ship would plot at the same speed as objects.**

The collision detection would need to be modified — instead of per-pixel AND-masking, the erase pass would AND the screen byte with the mask before EOR and check for residue. This is actually simpler and costs the same ~4 cycles.

**This is the highest-impact single change for sprite performance.**

### 5. Shared Ship/Pod Plot Routine (Save ~200 bytes code)

The pod plotter is a near-exact copy of the ship plotter. If the ship is converted to the two-stream format (suggestion 4), both ship and pod can share `plot_static_sprite`. The pod already has only one frame, so the data expansion is minimal (~28 bytes × 4 pixel columns = 112 bytes for stream B, + 28 bytes for stream A = ~140 bytes).

**Savings:** ~200 bytes of code (the entire pod plot routine). No speed improvement, but code size reduction frees space for the expanded sprite data.

### 6. Skip Unchanged Objects Early (Save ~2,000 cycles/frame when scrolling)

**Current:** When scrolling, every visible object is erased and redrawn even if the object hasn't moved in world space — only the viewport has moved, so the screen position changes.

**Proposal:** Instead of comparing old and new screen addresses (which always differ during scrolling), add a "viewport delta" fast path:

1. At frame start, compute `viewport_delta_x` and `viewport_delta_y`
2. For each visible object, if the object hasn't moved in world space, apply the viewport delta to the old screen address to get the new address
3. If the delta is zero (no scrolling), skip the erase/draw entirely

This doesn't reduce the per-object cost when scrolling is happening, but it avoids the full erase+draw cycle when the camera is stationary — which is the common case when the player is hovering near an object.

### 7. Reduce Particle Physics Overhead (Save ~5 cycles/particle)

**Current:** `test_particle_X_close_to_player` is called for every particle via JSR (6 cycles) even though it only applies to hostile bullets (type 3). Most particles are stars or exhaust.

**Proposal:** Inline the type check before the JSR:

```asm
    LDA  particles_type,X        ; 4
    CMP  #PARTICLE_type_hostile_bullet ; 2
    BNE  skip_proximity          ; 3 (taken for non-bullets)
    JSR  test_particle_X_close_to_player ; 6 + body
.skip_proximity:
```

**Savings:** ~30 cycles per non-bullet particle (avoids JSR+RTS + body of proximity test). For 10 non-bullet particles: ~300 cycles/frame.

### 8. Object Visibility Early-Out on Y (Save ~10 cycles/object when off-screen)

The object visibility test (`object_visibility_test`) checks both Y and X range. Y range failures are slightly more expensive because of the `EXT` byte comparison. Adding an early exit after the Y range check (before computing X) saves the X range calculation cycles for objects that are vertically off-screen.

The current code already does this to some degree, but the flow could be tightened.

### 9. Batch Object Sprite Data Pointer Setup (Save ~16 cycles/object)

**Current:** 4 separate `LDA table,Y` + `STA self_mod_addr` sequences = 4 × (4+4) = 32 cycles.

**Proposal:** Use a pair of 16-bit pointer copies instead, or restructure the sprite data tables so that A and B streams for each type are at a fixed offset from each other, requiring only 2 pointer setups instead of 4.

**Savings:** ~16 cycles per object × 22 objects = ~352 cycles/frame. Marginal.

---

## Summary of Optimisation Opportunities

| # | Optimisation | Cycles saved/frame | Code size impact | Complexity |
|---|---|---|---|---|
| 4 | Two-stream ship format | ~2,660 | +2,750 bytes data | High |
| 1 | Pre-decoded coordinates | ~2,660 | +700–5,400 bytes | Medium |
| 2 | Unrolled ship plot loop | ~608 | +320 bytes | Medium |
| 5 | Shared ship/pod routine | ~0 (code size only) | −200 bytes code | Low |
| 7 | Inline particle type check | ~300 | −10 bytes | Low |
| 3 | Self-modified absolute EOR | ~152 | +10 bytes | Low |
| 6 | Skip unchanged objects | ~2,000 (static only) | +30 bytes | Medium |
| 9 | Batch pointer setup | ~352 | +20 bytes | Low |
| 8 | Object Y early-out | ~220 | +5 bytes | Low |

The single highest-impact change is converting ship sprites to the two-stream object format (#4). This would reduce the ship from **59 cycles/pixel to 24 cycles/pixel** — a 2.5× speedup in the most expensive per-pixel operation — at the cost of ~2,750 bytes of pre-computed sprite data. Combined with sharing the plot routine with the pod (#5), the total sprite rendering cost drops from ~15,300 cycles (ship + pod + tether) to ~8,500 cycles, saving roughly **17% of the frame budget**.

For the game's actual bottleneck (the landscape draw at 64% of frame), see `landscape-draw-performance.md` — reducing sprite costs widens the headroom available for landscape rendering during scrolling.
