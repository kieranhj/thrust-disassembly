# Sprite Draw Performance Analysis

## Overview

Thrust draws four kinds of sprite every frame: the **ship** (17 rotation frames, mirrored to 32 angles, plus shield), the **pod** (towed payload) and its **tether line**, **static objects** (guns, fuel, generator, door switches, pod stand; laser turrets and bobbing mines in SWRAM builds), and **particles** (bullets, stars, debris; thrust exhaust in SWRAM builds). All use XOR (EOR) drawing: erase by redrawing at the old position, then draw at the new one. Data formats and routines are described in `sprite-drawing.md`.

**Target platform:** BBC Micro Model B, 2 MHz 6502. Vsync is 50 Hz (40,000 cycles; 39,936 exact), but the game loop waits until the centisecond clock reaches 3 before resetting it (`draw_player_timed_to_vsync`), so a game frame is at least 3 cs = **60,000 cycles** (~33 frames/s). Percentages below are of the 60,000-cycle game frame. When a frame's work exceeds 60,000 cycles the frame simply takes longer.

Cycle counts use standard NMOS 6502 timings. Unless stated, they assume no page-crossing penalties: `abs,X`/`abs,Y`/`(zp),Y` loads and read-modify sources take +1 when the index crosses a page, and taken branches take +1 when the target is in another page. For the ship and pod the screen operand `EOR (ptr),Y` crosses a page roughly a quarter of the time (Y offsets reach `$78`), adding about 0.3 cycles per pixel on average.

---

## Frame Budget Context

The main game loop (`tick_loop`, `thrust.6502:9626`) runs these phases in order:

| Phase | Routine | Colour marker |
|---|---|---|
| 1 | `hide_landscape`, `ship_input_rotate`, `midpoint_add_force_vector`, `update_window_and_terrain_tables` | Yellow |
| 2 | `draw_player_timed_to_vsync` → `draw_ship_line_and_pod` (tether erase, ship + pod, tether draw) | Red (during the draw) |
| 3 | `update_and_draw_all_objects` (static sprites) | Blue |
| 4 | `landscape_draw` (terrain) | Magenta |
| 5 | `tick_fuel_pickup_draw_beams` (fuel beams), `ship_input_fire` | none |
| 6 | `particles_update_and_draw` (bullets, stars, debris) | Cyan |
| 7 | pause test, fuel display, sound, thrust force, etc. | Green |

`draw_player_timed_to_vsync` draws the player as soon as User VIA timer 1 has fired (`irq1_timer1_signal`) while it waits for the 3 cs clock, or after the wait if the timer hasn't fired. The `SET_BG_COL` markers (enabled with `_DEBUG_RASTERS`) colour the background during each phase for timing on hardware.

From `landscape-draw-performance.md`, `landscape_draw` costs ~11,600 cycles (19%) with a static view and ~25,000 cycles (42%) when scrolling typically.

---

## Ship Sprite Rendering

### Data Format

Single-stream: each byte < `$80` is a pixel position, each byte ≥ `$80` a row advance, and `$81`-`$FE` also give the first pixel of the new row. `$80` is an empty row.

Frame 0 (upright) is 38 pixels in 16 rows with 15 row advances and no empty rows. Across the 17 frames: 38-41 pixels, 13-16 non-empty rows, 15-20 row advances of which 0-4 are empty (`$80`). The shield has 44 pixels.

### Plot Routine (`plot_ship_loop`, `thrust.6502:4962`)

Three self-modified `LDA sprite_data,X` instructions are patched to the same address: one in the main loop and one after each kind of row advance, so the row-advance code re-reads the current byte and drops straight back into the pixel decode.

#### Per-Pixel Cycle Count (Draw Mode)

In draw mode the collision test site holds `JMP plot_ship_loop`.

```
plot_ship_loop:
    LDX  plot_ship_index         ; 3  (ZP)
    INX                          ; 2
    STX  plot_ship_index         ; 3  (ZP)
    LDA  sprite_data,X           ; 4  (abs,X — self-modified)
    BMI  row_advance             ; 2  (not taken)
plot_ship_inner_loop:
    SEC                          ; 2
    CMP  #$FF                    ; 2  (self-modified: CMP #$FF or EOR #$1F)
    ADC  plot_ship_pixel_column  ; 3  (ZP)
    TAY                          ; 2
    AND  #$3C                    ; 2
    ROL  A                       ; 2
    STA  plot_ship_at_y_offset   ; 3  (ZP)
    TYA                          ; 2
    AND  #$03                    ; 2
    TAX                          ; 2
    LDA  pixel_masks_3,X         ; 4  (abs,X — self-modified)
    LDY  plot_ship_at_y_offset   ; 3  (ZP)
    EOR  (plot_ship_at_ptr),Y    ; 5  (ind,Y)
    STA  (plot_ship_at_ptr),Y    ; 6  (ind,Y)
    JMP  plot_ship_loop          ; 3  (patched over AND abs,X)
                                 ; ----
                                 ; 57 cycles per pixel
```

#### Per-Pixel Cycle Count (Erase Mode, No Collision)

In erase mode the site holds `AND pixel_masks_1,X`, followed by `BEQ plot_ship_loop`:

```
    ...same as above through STA...
    AND  pixel_masks_1,X         ; 4  (abs,X)
    BEQ  plot_ship_loop          ; 3  (taken = no collision)
                                 ; ----
                                 ; 61 cycles per pixel
```

#### Per-Pixel Cycle Count (Erase Mode, Collision Detected)

```
    AND  pixel_masks_1,X         ; 4
    BEQ  (not taken)             ; 2
    LDA  #$FF                    ; 2
    STA  plot_ship_collision_detected ; 3  (ZP)
    JMP  plot_ship_loop          ; 3
                                 ; ----
                                 ; 68 cycles per pixel
```

#### Row Advance (Within Character Cell)

A byte ≥ `$80` takes the BMI and re-reads the byte after moving down a row:

```
    BMI  L1F1F                   ; 3  (taken: +1 over the pixel path)
    CMP  #$FF                    ; 2
    BEQ  plot_ship_return        ; 2  (not taken)
    LDX  plot_ship_index         ; 3  (ZP — redundant, X is unchanged)
    DEC  plot_ship_row_counter   ; 5  (ZP)
    BMI  L1F35                   ; 2  (not taken)
    INC  plot_ship_at_ptr        ; 5  (ZP)
    LDA  sprite_data,X           ; 4  (abs,X — re-read same byte)
    CMP  #$80                    ; 2
    BNE  plot_ship_inner_loop    ; 3  (taken: pixel data)
                                 ; ----
                                 ; +29 cycles on top of the 57/61-cycle pixel
```

For an empty row (`$80`) the BNE falls through to `JMP plot_ship_loop`: the whole iteration costs 45 cycles and plots nothing.

#### Row Advance (Character Row Crossing)

When `plot_ship_row_counter` goes negative (every 8th row), `INC plot_ship_at_ptr` (5) is replaced by:

```
    BMI  L1F35                   ; 3  (taken: +1)
    LDA  #$07                    ; 2
    STA  plot_ship_row_counter   ; 3  (ZP)
    CLC                          ; 2
    LDA  plot_ship_at_ptr        ; 3  (ZP)
    ADC  #$39                    ; 2
    STA  plot_ship_at_ptr        ; 3  (ZP)
    LDA  plot_ship_at_ptr+1      ; 3  (ZP)
    ADC  #$02                    ; 2
    STA  plot_ship_at_ptr+1      ; 3  (ZP)
                                 ; ----
                                 ; +19 cycles over a normal row advance
```

`$0239` = `$0240 - 7` steps from the bottom row of one cell to the top row of the cell below. A 16-row sprite crosses one or two boundaries depending on its starting row (two in 7 cases out of 8).

The end marker (`$FF`) costs 26 cycles including the RTS.

### Setup (`plot_ship_or_shield`, `thrust.6502:4906`)

Called once per pass:

```
Opcode/mask patching (4 x LDA # + STA abs)  ; 24
LDA plot_ship_sprite_number + BPL           ; 6
CMP #$11 + BCC (unmirrored)                 ; 5
TAY + 2 x LDA table,Y + 6 x STA abs         ; 34
Row counter init (LDA/AND/EOR/STA)          ; 10
LDX #$00 + JMP plot_ship_start              ; 5
                                            ; ----
                                            ; ~84 cycles (~104 mirrored, +6 for the JSR)
```

### Screen Address Calculation (`thrust.6502:4827`)

Done once per frame, before the draw pass; the erase pass reuses `old_plot_ship_at_ptr`.

```
Pixel column (PLA, 3 x ROL, AND, 2 x STA)   ; 18
Y contribution (shift chain + ADC $38)      ; 46
X contribution (mult_by_8 lookup, 16-bit)   ; 26
Pixel row offset (AND #7 + ADC + 2 x STA)   ; 14
                                            ; ----
                                            ; ~104 cycles
```

Before this, `update_shield_tractor_draw_ship_and_pod` spends ~120 cycles turning the midpoint and tether delta into the ship's window position (more for the shield, which adds an angle offset).

### Collision Test Mode Copy

Each pass starts by copying the 3-byte AND or JMP template into the test site:

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

Ship frame 0 (38 pixels, 15 row advances, 2 character row crossings):

| Component | Erase | Draw |
|---|---|---|
| Mode copy (3 bytes) | 43 | 43 |
| Old state restore / position calc | 24 | ~120 |
| Screen address calculation | — | 104 |
| Setup (`plot_ship_or_shield` + JSR) | 90 | 90 |
| Pixel plotting (38 pixels) | 38 × 61 = 2,318 | 38 × 57 = 2,166 |
| Row advances (15) | 15 × 29 = 435 | 15 × 29 = 435 |
| Char row crossings (2) | 2 × 19 = 38 | 2 × 19 = 38 |
| End marker | 26 | 26 |
| **Subtotal** | **~2,970** | **~3,020** |

**Total ship per frame: ~6,000 cycles (10% of the game frame).** Frames with empty rows add 45 cycles per `$80`; mirrored angles add ~20 cycles of setup per pass. Under mirroring `EOR #$1F` replaces `CMP #$FF`, both 2 cycles.

---

## Pod Sprite Rendering

### Data Format

Same single-stream format. One frame, `pod_sprite_data` (`thrust.6502:2650`): 28 pixels in 11 rows, 15 row advances of which 4 are empty leading rows.

### Plot Routine (`plot_pod_sprite`, `thrust.6502:5664`)

A near-clone of the ship plotter with three self-modified `LDA` instructions. Differences that affect timing:

- The decode uses `CLC` (2) instead of `SEC` + `CMP #$FF` (4), but `STA pod_temp` / `LDA pod_temp` (3+3) instead of `TAY`/`TYA` (2+2): the pixel still costs **57 cycles** (draw) and **61** (erase, no collision)
- No row counter: a row advance tests `(ptr AND 7) == 7` (LDA/AND/CMP/BEQ, 9 cycles) instead of `LDX`/`DEC`/`BMI` (10). A row advance with a pixel costs +28; a crossing adds 14 more; an empty row costs 42
- The screen address is computed inline in the draw pass (~100 cycles); the erase pass enters at `L21B6` with the saved address
- `set_plot_pod_sprite_mask_addr` (28 cycles including JSR/RTS) runs twice in the draw pass (the first call is redundant) and once in the erase pass
- The collision flag store address is self-modified (`plot_pod_sprite_addr_zp`); it is always set to `plot_pod_collision_detected`

### Per-Frame Pod Cost

The pod is erased if it was drawn last frame and drawn only while tethered.

| Component | Erase | Draw |
|---|---|---|
| Orchestration, mode copy, position calc | ~100 | ~150 |
| Screen address + mask setup (`plot_pod_sprite`) | — | ~130 |
| `L21B6` setup (mask + 6 pointer stores) | 63 | 63 |
| Pixel plotting (28 pixels) | 28 × 61 = 1,708 | 28 × 57 = 1,596 |
| Row advances with pixel (11) | 11 × 28 = 308 | 11 × 28 = 308 |
| Empty rows (4) | 4 × 42 = 168 | 4 × 42 = 168 |
| Char row crossings (~2) + end marker | ~54 | ~54 |
| **Subtotal** | **~2,400** | **~2,470** |

**Total pod per frame: ~4,900 cycles (8%).** Zero when no pod is attached.

---

## Tether Line Rendering

### Algorithm

The tether is a Bresenham line (`draw_line`, `thrust.6502:8269`) plotted with XOR using `pixel_masks_1` ANDed with `plot_line_pixels_byte` = `level_line_pixels_byte`: `LANDSCAPE_COLOUR_BYTE` `$F0` (colour 2), or `$FF` (colour 3) once `invisible_landscape_flag` is set. `draw_ship_line_and_pod` erases the old line before the ship and pod are drawn and draws the new one after. The same routine draws the fuel pickup beams (with `plot_line_pixels_byte` = `$0F`).

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
                                 ; 28 cycles (plot only)

plot_line_bresenham_1:
    JSR  step_function           ; 6 + body + RTS (self-modified target)
                                 ;   pixels_ptr_add_7: 13 + 6, ~22 avg with byte wrap
                                 ;   pixels_ptr_increment: 12 + 6, ~21 avg with row wrap
    LDA  bresenham_error         ; 3  (ZP)
    CLC                          ; 2
    ADC  draw_line_delta_minor   ; 3  (ZP)
    BCS  plot_line_bresenham_2   ; 2  (not taken)
    CMP  draw_line_delta_major   ; 3  (ZP)
    BCS  plot_line_bresenham_2   ; 2  (not taken)
    STA  bresenham_error         ; 3  (ZP)
                                 ; ----
                                 ; ~67-74 cycles per pixel, major step only
```

A pixel that also steps the minor axis goes through `plot_line_bresenham_2` (SBC, STA, a second JSR to a step function, JMP), adding ~30 cycles. A typical tether pixel is **~85 cycles**.

### Per-Frame Tether Cost

Line length depends on the tether angle. Assume ~40 pixels.

| Component | Erase | Draw |
|---|---|---|
| `draw_line` setup incl. `calculate_pixels_ptr` | ~250 | ~250 |
| Per-pixel plotting (40 pixels) | 40 × 85 = 3,400 | 40 × 85 = 3,400 |
| **Subtotal** | **~3,650** | **~3,650** |

**Total tether per frame: ~7,300 cycles (12%).** Only drawn while the pod is attached; with the pod sprite, towing adds ~12,000 cycles per frame.

---

## Static Object Sprite Rendering

### Data Format

Two streams: stream A gives byte offsets (Y for `(ptr),Y`) and row-advance markers; stream B gives whole MODE 1 screen bytes to XOR. One EOR writes up to 4 pixels.

### Plot Routine (`plot_static_sprite`, `thrust.6502:2449`)

```
Setup:
    LDX  current_object          ; 3  (ZP)
    LDA  level_obj_flags,X       ; 4  (abs,X)
    ORA  #OBJ_flag_drawn         ; 2
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

#### Per-Byte Plot (No Row Advance)

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
                                 ; 24 cycles per byte
```

At 4 pixels per byte that is 6 cycles per pixel, but many object bytes carry only one or two set pixels (e.g. `$88`, `$11`), so 8-24 cycles per pixel is more realistic. Either way it is far cheaper than the ship's 57.

#### Row Advance (Within Character Cell)

```
    LDY  sprite_data_A,X         ; 4
    BPL  L11D3                   ; 2  (not taken: bit 7 set)
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
                                 ; 47 cycles (row advance + first byte)
```

#### Row Advance (Character Row Crossing)

When `sprite_rows_to_boundary` reaches zero, the `BNE` falls through to:

```
    BNE  L11D3                   ; 2  (not taken)
    DEC  plot_sprite_at_ptr      ; 5  (ZP — undo the INC)
    LDA  plot_sprite_at_ptr      ; 3  (ZP)
    ADC  #$39                    ; 2  (carry clear from CPY #$FF)
    STA  plot_sprite_at_ptr      ; 3  (ZP)
    LDA  plot_sprite_at_ptr+1    ; 3  (ZP)
    ADC  #$02                    ; 2
    STA  plot_sprite_at_ptr+1    ; 3  (ZP)
    LDA  #$08                    ; 2
    STA  sprite_rows_to_boundary ; 3  (ZP)
    TYA                          ; 2  (redundant: Y is already masked)
    AND  #$7F                    ; 2
    TAY                          ; 2
                                 ; ----
                                 ; 78 cycles (crossing + first byte)
```

### Object Sprite Sizes

Cost per plot pass = 34 setup + 24 per byte + 23 per row advance + 31 per crossing + ~16 end/RTS (+6 JSR), assuming ~2 crossings (1 for the teleporter).

| Object | Byte plots | Row advances | Cost per pass |
|---|---|---|---|
| Gun (`$00`-`$03`) | 33 | 13-14 | ~1,200 |
| Fuel (`$04`) | 44 | 13 | ~1,460 |
| Pod stand (`$05`) | 37 (44 in SWRAM data) | 19 | ~1,430 (~1,600) |
| Generator (`$06`) | 43 | 17 | ~1,530 |
| Door switch (`$07`, `$08`) | 16 | 14 | ~810 |
| Laser turret (`$09`-`$0C`, SWRAM) | 33 | 13-14 | ~1,200 |
| Bobbing mine (`$0E`, `$0F`, SWRAM) | 20 | 12 | ~860 |

Gravity wells (`$0D`), teleporters (`$10`) and doors (`$11`) skip the sprite code. Laser turret beams are drawn separately (`update_one_laser_beam`) and are not counted here.

### Object Update Loop (`update_and_draw_all_objects`, `thrust.6502:1645`)

Each object in the list (10-20 in the shipped levels; 20 slots, 32 in SWRAM builds) costs, before any plotting:

1. Type load, gun-aim unpack, pod stand / generator flag updates: ~60 cycles (+~40 in SWRAM builds for the gravity well / mine / teleporter / door type checks)
2. Four sprite-pointer patches (`LDA abs,Y` + `STA abs`): 32 cycles
3. `object_visibility_test`: ~60 cycles when culled on Y, ~100 when culled on X, ~200 when visible (including `calculate_object_plot_addr`)
4. Dirty-rect compare against `level_obj_plot_at_ptr_LO/HI`: ~40 cycles
5. Bullet test against the 4 player-bullet slots: ~100 cycles when all are empty. This runs for every live object, on screen or not
6. Tractor, gun-fire and generator-debris checks and plot tail: ~40-60 cycles (more when a gun fires)

#### Per-Object Cost (Visible, Position Unchanged)

The dirty-rect check skips both erase and redraw:

```
    ~60 + 32 + 200 + 40 + 100 + 60 = ~500 cycles
```

#### Per-Object Cost (Visible, Position Changed)

```
    Overhead + erase + draw + bookkeeping
    ~500 + ~1,200 + ~1,200 + ~50 = ~3,000 cycles (gun; ~3,500 for fuel or generator)
```

#### Per-Object Cost (Off-Screen)

```
    ~60 + 32 + ~80 + 100 + ~60 + ~20 = ~350 cycles
```

A destroyed object (alive flag clear, not drawn) costs ~120 cycles.

### Per-Frame Object Cost

Object screen positions change whenever the window moves (scrolling is in software), so during scrolling every visible object is erased and redrawn. Assume a level with 18 objects:

| Scenario | Objects | Cost |
|---|---|---|
| Static view | 8 visible unchanged, 10 off-screen | 8×500 + 10×350 = **~7,600** |
| Scrolling | 8 visible redrawn, 10 off-screen | 8×3,000 + 10×350 = **~27,500** |
| Fast scroll | 6 visible redrawn, 12 off-screen | 6×3,000 + 12×350 = **~22,200** |

**Object cost per frame: ~7,600-27,500 cycles (13-46%).** While scrolling, objects cost about as much as the landscape.

---

## Particle Rendering

### Data Format

Each particle is one screen byte pattern written to two consecutive bytes, i.e. the same byte on two adjacent scanlines (row 7 is clamped to row 6 so both stay in one cell). `particles_xpos_byte_mask` (`$CC`, `$66`, `$66`, `$33`) makes it 2 pixels wide, so a particle is 2×2 pixels. The pool has 32 slots (`PARTICLE_table_max = $1F`).

### Per-Particle Cycle Count

#### Erase Phase (`PARTICLE_flag` set in lifetime)

```
    LDA  particles_lifetime,X    ; 4  (abs,X)
    BPL  skip                    ; 2  (not taken)
    AND  #($FF EOR PARTICLE_flag); 2
    STA  particles_lifetime,X    ; 5  (abs,X)
    LDA  particles_scraddr_LO,X  ; 4  (abs,X)
    STA  particle_write_ptr      ; 3  (ZP)
    LDA  particles_scraddr_HI,X  ; 4  (abs,X)
    STA  particle_write_ptr+1    ; 3  (ZP)
    LDY  #$00                    ; 2
    LDA  particles_pixels_byte,X ; 4  (abs,X)
    PHA                          ; 3
    EOR  (particle_write_ptr),Y  ; 5
    STA  (particle_write_ptr),Y  ; 6
    PLA                          ; 4
    INY                          ; 2
    EOR  (particle_write_ptr),Y  ; 5
    STA  (particle_write_ptr),Y  ; 6
                                 ; ----
                                 ; 64 cycles
```

Each slot also pays 5 cycles to clear `particle_collision_flag` first.

#### Update Phase (physics + visibility)

```
    Lifetime decrement                         ; 15
    test_particle_X_close_to_player            ; 21 (JSR, type test, RTS) for non-bullets
    particle_move_index_X                      ; ~94 (JSR, two 16-bit adds, Y high byte)
    Pixel byte lookup + JMP                    ; 14
    Visibility test (Y range)                  ; 21
    Visibility test (terrain walls)            ; 26
    Visibility test (X range, screen rows)     ; 37
                                               ; ----
                                               ; ~228 cycles
```

Stars are stationary but still go through `particle_move_index_X`.

#### Draw Phase (visible particle)

```
    Set PARTICLE_flag                          ; 11
    Screen address (shift chain + mult_by_8)   ; 74
    Row clamp + low-byte add + save            ; 23
    Pixel column and mask lookup               ; 40
    EOR byte 1 + collision test                ; 20
    EOR byte 2 + collision test                ; 26
    Collision flag test + loop                 ; 16
                                               ; ----
                                               ; ~210 cycles
```

### Per-Frame Particle Cost

Typical active particles: 5-15 (stars and occasional bullets, plus exhaust in SWRAM builds).

| Component | Per particle | 10 particles |
|---|---|---|
| Erase (if drawn last frame) | 69 | 690 |
| Update (physics + visibility) | 228 | 2,280 |
| Draw (if visible) | 210 | 2,100 |
| **Total per active particle** | **~507** | **~5,070** |
| Inactive slot (lifetime = 0) | 26 | 22 × 26 = 572 |

Plus `particles_generate_stars` (every other frame, near the top of the level): ~100 cycles.

**Typical particle cost per frame: ~5,700 cycles (9.5%) for 10 active particles.** 15 active: ~8,200. All 32 active: ~16,000.

---

## Complete Frame Budget

"Physics + input + sound" is a rough estimate, not a measured figure.

### Scenario 1: Static View, No Pod

| System | Cycles | % of 60,000 |
|---|---|---|
| Landscape draw | 11,600 | 19% |
| Ship (erase + draw) | 6,000 | 10% |
| Objects (8 visible unchanged, 10 off-screen) | 7,600 | 13% |
| Particles (10 active) | 5,700 | 10% |
| Physics + input + sound | ~3,000 | 5% |
| **Total** | **~33,900** | **57%** |

About 26,000 cycles to spare; the loop waits out the rest of the 3 cs.

### Scenario 2: Scrolling, Pod Attached

| System | Cycles | % of 60,000 |
|---|---|---|
| Landscape draw | 25,000 | 42% |
| Ship (erase + draw) | 6,000 | 10% |
| Pod (erase + draw) | 4,900 | 8% |
| Tether line (erase + draw) | 7,300 | 12% |
| Objects (8 visible redrawn) | 27,500 | 46% |
| Particles (10 active) | 5,700 | 10% |
| Physics + input + sound | ~3,000 | 5% |
| **Total** | **~79,400** | **132%** |

The frame takes ~4 cs instead of 3, so the game drops to ~25 frames/s.

### Scenario 3: Fast Scroll, No Pod

| System | Cycles | % of 60,000 |
|---|---|---|
| Landscape draw | ~40,000 | 67% |
| Ship (erase + draw) | 6,000 | 10% |
| Objects (6 redrawn) | 22,200 | 37% |
| Particles (15 active) | 8,200 | 14% |
| Physics + input + sound | ~3,000 | 5% |
| **Total** | **~79,400** | **132%** |

Again ~4 cs per frame.

---

## Bottleneck Analysis

### Cycles per Pixel by System

| System | Cycles per write | Pixels per write | Cycles/pixel |
|---|---|---|---|
| Ship (draw) | 57 | 1 | 57 |
| Ship (erase) | 61 | 1 | 61 |
| Ship, `_FAST_SPRITES` (draw / erase) | 33 / 37 | 1 | 33 / 37 |
| Pod (draw) | 57 | 1 | 57 |
| Tether line | ~85 | 1 | ~85 |
| Object sprite | 24 | 1-4 | 6-24 |
| Particle (erase + draw only) | ~280 | 4 | ~70 |
| Landscape | 27 | 4 | 6.75 |

The ship and pod cost several times more per pixel than objects: per-pixel single-colour drawing with run-time coordinate decode versus pre-built screen bytes.

### Time Breakdown by Operation (Ship Pixel)

Of the 57 cycles per ship pixel (draw mode):

| Operation | Cycles | % |
|---|---|---|
| Loop overhead (LDX/INX/STX) | 8 | 14% |
| Data fetch (LDA sprite_data,X + BMI) | 6 | 11% |
| X coordinate decode (SEC → TAX) | 22 | 39% |
| Mask table lookup | 4 | 7% |
| Screen offset load (LDY) | 3 | 5% |
| Screen read-modify-write (EOR + STA indirect) | 11 | 19% |
| Collision skip (JMP) | 3 | 5% |
| **Total overhead** | **46** | **81%** |
| **Actual screen write** | **11** | **19%** |

Coordinate decode and loop management dominate.

---

## Optimisation Suggestions

Status as of the current source: #4 is implemented behind `_FAST_SPRITES` (off by default); #6 and #8 were already in the original code; the rest are not implemented.

### 1. Pre-decode Ship Sprite Coordinates

**Status:** superseded by #4.

Pre-processing the sprite data into `(offset, mask)` pairs removes the 22-cycle decode and gives a 24-cycle loop like the objects', but the pixel column is added at run time, so the decoded data either needs 4 variants (one per pixel column) or keeps the ADC/AND/ROL decode, which saves little. With 4 variants this becomes #4.

### 2. Unroll the Ship Plot Loop (Save ~6 cycles/pixel)

**Status:** not implemented.

Unrolling the pixel loop keeps the index in X (still `INX` per pixel) and drops the `LDX`/`STX plot_ship_index` pair (6 cycles):

```asm
    ; Unrolled body (repeated N times):
    INX
    LDA  sprite_data,X
    BMI  row_advance_N
    ; ...pixel plot (no LDX/STX)...
```

The decode clobbers X (`TAX` for the mask index), so the body would also need to keep the index elsewhere (or use Y for the mask), which eats into the saving. **Savings:** up to 6 × 38 × 2 ≈ 450 cycles/frame. **Cost:** ~40 bytes per unrolled copy, plus a row-advance target per copy.

### 3. Replace Indirect Addressing with Self-Modified Absolute

**Status:** not implemented; probably not worth it.

`EOR abs,Y` (4) + `STA abs,Y` (5) instead of `EOR (ptr),Y` (5) + `STA (ptr),Y` (6) saves 2 cycles per pixel, but every row advance must then update two operand addresses (`INC abs` × 2 = 12 cycles instead of `INC zp` = 5) and crossings must patch both high bytes. For frame 0 (38 pixels, 15 row advances) that is 76 saved against ~105 added: a net loss.

### 4. Two-Stream Ship Format (implemented: `_FAST_SPRITES`)

**Status:** implemented in commit 4ed77ea, behind `_FAST_SPRITES = (_SWRAM_BUILD AND FALSE)`, so not in the default build. `tools/generate_ship_streams.py` writes `tools/output/ship_twostream_data.asm` from the original sprite data: 32 angles × 4 pixel columns, plus 4 shield variants, ~12KB including pointer tables, assembled into sideways RAM bank `SPRITE_BANK` (5) and saved as the `Sprites` file. The plotter is the second `plot_ship_or_shield` / `plot_ship_ts_loop` (`thrust.6502:13918`).

The loop is longer than the object loop because stream B holds both-bitplane masks (needed for the collision test) and is reduced to the ship colour at run time:

```asm
plot_ship_ts_loop:
    INX                          ; 2
    LDY  stream_A,X              ; 4  (self-modified)
    BPL  plot_ship_ts_pixel      ; 3
plot_ship_ts_pixel:
    LDA  stream_B,X              ; 4  (self-modified)
    STA  ship_ts_mask_temp       ; 4  (absolute)
    AND  #$0F                    ; 2  (self-modified: $0F ship, $FF shield)
    EOR  (plot_ship_at_ptr),Y    ; 5
    STA  (plot_ship_at_ptr),Y    ; 6
    JMP  plot_ship_ts_loop       ; 3  (erase: AND ship_ts_mask_temp + BEQ = 4+3)
                                 ; ----
                                 ; 33 cycles draw, 37 erase
```

A row advance adds 24 cycles (crossing +16 more). Empty rows are stored as a `$80` entry with a `$00` mask, so they cost a full (no-op) plot. For frame 0 one pass costs ~1,670 (draw) / ~1,820 (erase) against ~2,670 / ~2,820, saving **~2,000 cycles per frame** (3% of the game frame), less ~50 cycles of `SET_RAM_BANK` switching. Setup is ~71 cycles.

Mirroring and the pixel column are baked into the data. The generator mirrors with `(x EOR $1F)`, but the original decode adds 1 for mirrored angles (carry set from the `SEC`), so mirrored angles may be one pixel left of the original in this build; this has not been checked in an emulator.

### 5. Shared Ship/Pod Plot Routine

**Status:** not implemented. The pod still uses `plot_pod_sprite`; the generator emits `pod_ts_*` streams but nothing references them.

With the two-stream plotter the pod could use the same loop (4 pixel-column variants of a 28-pixel sprite, ~250 bytes) and `plot_pod_sprite` (~200 bytes of code) could go. This saves ~1,600 cycles/frame while towing, at the same per-pixel rate as #4.

### 6. Skip Unchanged Objects

**Status:** already in the original code. `update_and_draw_all_objects` compares the new plot address from `object_visibility_test` with `level_obj_plot_at_ptr_LO/HI` and skips both erase and redraw when it is unchanged and the object is alive. During scrolling every visible object's address changes, so nothing is saved then; reusing the old pixels would need a hardware or copy-based scroll.

### 7. Inline the Particle Hostile-Bullet Check (Save ~12 cycles/particle)

**Status:** not implemented.

`test_particle_X_close_to_player` is called for every live particle but only acts on hostile bullets (type 3). For other particles the call costs 21 cycles (JSR, LDA, CMP, BNE, RTS). Testing the type inline costs 9:

```asm
    LDA  particles_type,X        ; 4
    CMP  #PARTICLE_type_hostile_bullet ; 2
    BNE  skip_proximity          ; 3 (taken for non-bullets)
    JSR  test_particle_X_close_to_player
.skip_proximity:
```

**Savings:** ~12 cycles per non-bullet particle, ~120 cycles/frame for 10 particles.

### 8. Object Visibility Early-Out on Y

**Status:** already in the original code. `object_visibility_test` returns as soon as the Y high byte or Y range fails, before computing X.

### 9. Batch Object Sprite Data Pointer Setup (Save ~16 cycles/object)

**Status:** not implemented.

The update loop patches four operand bytes per object (4 × (4+4) = 32 cycles) for every object, including destroyed and off-screen ones. Placing each type's B stream at a fixed offset from its A stream would halve this, or the patching could move after the alive and visibility checks. **Savings:** ~16 cycles per object, ~300 cycles/frame for 18 objects.

### Other Small Inefficiencies

- The bullet test (~100 cycles) runs for every live object, including off-screen ones. Skipping it when no player bullet is active would save ~1,000-1,500 cycles per frame in a typical level
- `plot_ship_loop` reloads X (`LDX plot_ship_index`) on row advance although X is unchanged: 3 cycles per row advance
- `plot_pod_sprite` calls `set_plot_pod_sprite_mask_addr` twice: 28 cycles per draw
- `plot_static_sprite` repeats `TYA`/`AND #$7F`/`TAY` on a character-row crossing: 6 cycles per crossing

---

## Summary of Optimisation Opportunities

| # | Optimisation | Cycles saved/frame | Size impact | Status |
|---|---|---|---|---|
| 4 | Two-stream ship format | ~2,000 | ~12KB data (SWRAM bank 5) | Implemented (`_FAST_SPRITES`, off) |
| 5 | Pod on the two-stream plotter | ~1,600 (towing only) | ~250 bytes data, −200 bytes code | Not implemented |
| — | Skip bullet test with no live player bullets | ~1,000-1,500 | ~10 bytes | Not implemented |
| 2 | Unrolled ship plot loop | up to ~450 | ~320 bytes | Not implemented |
| 9 | Batch / defer object pointer setup | ~300 | ~20 bytes | Not implemented |
| 7 | Inline particle type check | ~120 | ~7 bytes | Not implemented |
| 3 | Self-modified absolute EOR | net loss | +10 bytes | Not worth it |
| 1 | Pre-decoded coordinates | — | — | Superseded by #4 |
| 6 | Skip unchanged objects | — | — | Already in original |
| 8 | Object Y early-out | — | — | Already in original |

The two-stream ship plotter cuts the ship from 57 to 33 cycles per pixel and saves ~2,000 cycles per frame; putting the pod on it as well would save another ~1,600 while towing. The tether line (~7,300) and especially object redraws during scrolling (~22,000-27,500) cost more than the ship and pod together, so they are the larger targets after the landscape (see `landscape-draw-performance.md`).
