# Sprite Drawing Technical Reference

## Screen Layout

The game configures the ULA for MODE 1 (4 colours, 2 bits per pixel) but reprograms the 6845 CRTC to create a custom 72-character-wide display.

| Constant | Value | Description |
|---|---|---|
| `SCREEN_BASE_ADDR` | `$3C80` | Start of screen memory |
| `SCREEN_WIDTH_CHARS` | 72 | Character columns across screen |
| `SCREEN_CHAR_ROW_BYTES` | `$0240` (576) | Bytes per character row (72 * 8) |
| `SCREEN_START_ADDR` | `$4100` | Gameplay area (after 2 status bar rows) |

### MODE 1 Pixel Format

Each screen byte encodes 4 pixels using interleaved bitplanes:

| Pixel | Bit 7 | Bit 6 | Bit 5 | Bit 4 | Bit 3 | Bit 2 | Bit 1 | Bit 0 |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| 0     | H     |       |       |       | L     |       |       |       |
| 1     |       | H     |       |       |       | L     |       |       |
| 2     |       |       | H     |       |       |       | L     |       |
| 3     |       |       |       | H     |       |       |       | L     |

H = high bitplane, L = low bitplane. The two bits per pixel select one of 4 colours.

### Character Cell Memory

Within a character cell, 8 consecutive bytes represent 8 pixel rows (top to bottom). To move right one character column, add 8 bytes. To move down one character row, add `$0240` bytes.

### Pixel Mask Tables

Three tables provide per-pixel-column masks for the three non-black colours:

```
pixel_masks_1:  $88, $44, $22, $11   ; colour 3 (both bitplanes)
pixel_masks_2:  $80, $40, $20, $10   ; colour 2 (high bitplane)
pixel_masks_3:  $08, $04, $02, $01   ; colour 1 (low bitplane)
```

Index 0 = leftmost pixel in byte, index 3 = rightmost.

---

## Screen Address Calculation

All three sprite routines compute screen addresses using the same fundamental algorithm. Given a viewport-relative position (X integer, Y integer):

### Y Contribution (Character Row)

The Y coordinate is split into a character row (bits 7-3) and a pixel row within the cell (bits 2-0). The character row is multiplied by `$0240` using shift-and-add:

```
addr = $3800 + (Y AND $F8) * 72
```

The code achieves this through a chain of ROR instructions that distribute the product across the high and low address bytes, then adds `$38` as the screen base high byte.

### X Contribution (Character Column)

The integer X position indexes into the `mult_by_8` lookup table (`mult_by_8_LO` at `$09C0`, `mult_by_8_HI` at `$0A10`) which provides `X * 8` as a 16-bit value. This byte offset is added to the row address.

### Pixel Row Offset

The low 3 bits of Y (`AND #$07`) are added to the address low byte to select the exact scanline within the character cell.

### Sub-Character Pixel Column

The top 2 bits of the fractional X byte give a pixel offset (0-3) within a screen byte. This is extracted via three ROL instructions and `AND #$03`, then stored as the "pixel column" and added to each sprite data pixel position during rendering.

---

## XOR (EOR) Drawing

All sprites are drawn using XOR. Each pixel is toggled:

```asm
LDA  mask_table,X       ; pixel mask for this column
EOR  (screen_ptr),Y     ; XOR with screen contents
STA  (screen_ptr),Y     ; write back
```

XOR is self-inverting: drawing the same sprite at the same position twice perfectly restores the original screen contents. This enables efficient erasure -- to remove a sprite, simply redraw it at its previous position.

### Erase-Then-Draw Cycle

Each frame follows the same pattern for all sprite types:

1. **Erase**: Restore the previous position from saved `old_*` variables, XOR-plot the sprite to remove it
2. **Calculate**: Compute the new screen position from world coordinates
3. **Draw**: XOR-plot the sprite at the new position
4. **Save**: Store the new position into `old_*` variables for next frame's erasure

### Collision Detection via XOR

Collision is detected during the **erase** pass, not during drawing. After XOR-erasing a pixel, the result is AND-masked with the pixel mask. In the collision-free case, XOR restores the pixel to zero and the AND result is zero. If another sprite has overwritten the pixel since it was drawn, the XOR produces a non-zero result, signalling a collision.

This is managed through self-modifying code. Three bytes at the collision test site are patched to either:
- `AND pixel_masks_1,X` -- active collision detection (used during erase pass)
- `JMP plot_loop` -- skip collision detection (used during draw pass)

---

## Ship Sprite Rendering

### Sprite Data Format

Ship sprites use a single-stream format where each byte serves dual purposes via bit 7:

| Value | First Read (BMI test) | Second Read (after row advance) |
|-------|----------------------|-------------------------------|
| `$00`-`$7F` | Pixel data -- plot this pixel | N/A (not a control byte) |
| `$80` | Control: row end | Empty row marker (skip) |
| `$81`-`$FE` | Control: row end | Pixel data for first pixel of new row |
| `$FF` | Control: end of sprite | N/A |

The key insight is that bytes `$81`-`$FE` encode both "end of current row" and "first pixel position of the next row" in a single byte. Bit 7 triggers the row-advance logic, and the full byte value is harmlessly reused as pixel data because the column calculation masks only use bits 0-5:

- `AND #$3C` extracts the character column byte offset (bits 5-2)
- `AND #$03` extracts the pixel position within the byte (bits 1-0)
- Bit 7 falls outside both masks and is ignored

### Pixel Column Encoding

Each pixel data byte encodes an X position relative to the sprite origin. The byte is processed as follows:

```asm
ADC  plot_ship_pixel_column   ; add sub-character offset (0-3)
TAY                           ; save combined value
AND  #$3C                     ; bits 5-2 = character column * 4
ROL  A                        ; * 2 = byte offset (8 bytes per column)
STA  plot_ship_at_y_offset    ; screen byte offset from base
TYA
AND  #$03                     ; bits 1-0 = pixel within byte (0-3)
TAX                           ; index into pixel mask table
```

The byte offset is used as the Y register for indirect indexed addressing: `EOR (plot_ship_at_ptr),Y`.

### Self-Modifying Code

The ship plotter uses four self-modified code sites:

| Site | What Changes | Purpose |
|------|-------------|---------|
| `ship_sprite_addr_1/2/3` | LDA operand address | Select which sprite frame data to read |
| `ship_pixel_mask_test` | 3-byte instruction | Enable/disable collision detection |
| `plot_ship_write_opcode` | `CMP` vs `EOR` opcode | Normal vs. mirrored X coordinate flip |
| `ship_load_pixel_mask` | Mask table address | Ship colour (masks_1) vs shield colour (masks_3) |

Three separate `LDA sprite_data,X` instructions are patched to the same sprite data address. This avoids an extra branch -- after a row advance, the code falls directly into the appropriate re-read instruction.

### Character Row Boundary Crossing

`plot_ship_row_counter` tracks remaining pixel rows in the current character cell, initialised to `7 - (Y AND 7)`. Each row advance decrements the counter and increments the screen pointer by 1. When the counter goes negative:

```asm
; Reset counter and jump to next character row
LDA  #$07
STA  plot_ship_row_counter
CLC
LDA  plot_ship_at_ptr
ADC  #$39              ; low byte: +$39
STA  plot_ship_at_ptr
LDA  plot_ship_at_ptr+1
ADC  #$02              ; high byte: +$02 = total +$0239
STA  plot_ship_at_ptr+1
```

The offset `$0239` = `$0240 - 7` accounts for the 7 bytes already traversed within the character cell before crossing the boundary.

### Ship Sprite State Variables

| Variable | Address | Purpose |
|---|---|---|
| `plot_ship_at_ptr` | $0072 | Current screen write address (16-bit) |
| `plot_ship_pixel_column` | $0075 | Sub-byte pixel offset (0-3) |
| `plot_ship_row_counter` | $0070 | Rows remaining before char row boundary |
| `plot_ship_at_y_offset` | $0071 | Byte offset for current pixel |
| `plot_ship_collision_detected` | $002A | Set to $FF on collision during erase |
| `old_plot_ship_at_ptr` | $000E | Previous frame screen address |
| `old_plot_ship_pixel_column` | $0010 | Previous frame pixel column |
| `old_plot_ship_sprite_number` | $0011 | Previous frame sprite index |

---

## Pod Sprite Rendering

The pod sprite uses the same single-stream data format as the ship, with the same dual-purpose bit-7 encoding. The rendering algorithm is functionally identical but implemented as a separate routine with its own set of self-modifying code sites.

### Pod-Specific Differences

- The pod has a single sprite (no rotation frames), stored at `pod_sprite_data`
- Position is derived from `midpoint - midpoint_delta` (the pod is on the opposite side of the tether midpoint from the ship)
- The Y position undergoes a ROL (multiply by 2) during coordinate conversion
- Collision detection occurs during the erase pass and sets `plot_pod_collision_detected` ($002B)

### Pod State Variables

| Variable | Address | Purpose |
|---|---|---|
| `plot_pod_sprite_at_ptr` | $0077 | Current screen write address (16-bit) |
| `pod_pixel_column` | $0076 | Sub-byte pixel offset (0-3) |
| `pod_screen_addr_LO/HI` | $0079/$007A | Snapshot of initial screen address for saving |
| `pod_sprite_data_index` | $0073 | Current byte index into sprite data |
| `plot_pod_collision_detected` | $002B | Set to $FF on collision during erase |
| `old_plot_pod_sprite_at_ptr` | $003F | Previous frame screen address |
| `old_pod_pixel_column` | $0041 | Previous frame pixel column |
| `pod_sprite_plotted_flag` | $0017 | 1 if pod is currently drawn on screen |

### Pod Erase/Draw Orchestration

`draw_pod_and_collision_test` manages the full lifecycle:

1. Patch `AND pixel_masks_1,X` into the collision test site
2. If `pod_sprite_plotted_flag` is set: restore old position from saved variables, call plot routine to XOR-erase (collision active)
3. Patch `JMP plot_pod_loop` into the collision test site (disable collision)
4. Calculate new pod position from `midpoint - delta`
5. If pod is attached: call `plot_pod_sprite` to draw at new position, save position to `old_*` variables

---

## Static Object Sprite Rendering

Objects (guns, fuel, pod stand, generator, door switches) use a different **two-stream** sprite data format and a separate plotting routine.

### Two-Stream Data Format

Each object sprite is defined by two parallel byte arrays:

**Stream A** (offsets/control):
| Value | Meaning |
|-------|---------|
| `$00`-`$7F` | Y register offset for `(ptr),Y` addressing -- selects screen byte |
| `$80`-`$FE` | Row advance marker. Low 7 bits = Y offset for first pixel of new row |
| `$FF` | End of sprite |

**Stream B** (pixel data):
Each byte is a complete MODE 1 screen byte (4 pixels, 2 bitplanes) to XOR onto the screen. Stream B bytes are consumed in lockstep with stream A pixel offsets.

### Static Sprite Plotting Algorithm

```
for each byte pair (A[i], B[i]):
    if A[i] == $FF:
        return                        ; end of sprite
    if A[i] bit 7 set:
        advance screen ptr to next pixel row
        if crossed character row boundary:
            add $0239 to screen ptr
            reset row counter to 8
        Y = A[i] AND $7F              ; strip control bit
    else:
        Y = A[i]                      ; direct byte offset
    screen[ptr + Y] ^= B[i]           ; XOR plot
```

The two-stream approach suits static objects because they use full-byte pixel patterns (multiple pixels per write) rather than single-pixel plotting. This is more efficient for wider, denser sprites.

### Object Update Loop

The object system iterates over all level objects each frame:

1. Load object type (0-8) from level data
2. Look up sprite data pointers from `obj_sprite_data_A/B_table` indexed by type
3. Check `level_obj_flags` bit 0 (currently drawn on screen)
4. If drawn: run visibility test at new position. If position unchanged, skip. Otherwise XOR-erase at old position.
5. Check bit 1 (should be active): if set, XOR-draw at new position and save address
6. Special case: generator (type 6) flashes by toggling bit 1 during countdown

### Object Visibility Culling

Before drawing, `object_visibility_test` checks:

- **Y range**: `current_obj_ypos - window_ypos` must be within a single 256-pixel page (`EXT` bytes must match), then within scanlines `$11`-`$7E` after status bar offset
- **X range**: `current_obj_xpos - window_xpos` compared against per-type `object_type_cull_size_table` values (`$44`-`$47`), which account for the 72-column screen width

---

## Summary of Sprite System Architecture

| Feature | Ship | Pod | Static Objects |
|---------|------|-----|----------------|
| Data format | Single-stream, bit-7 dual-purpose | Single-stream, bit-7 dual-purpose | Two parallel streams (offset + pixel) |
| Pixel granularity | Per-pixel (mask table lookup) | Per-pixel (mask table lookup) | Per-byte (full 4-pixel patterns) |
| Colour selection | Self-modified mask table pointer | Self-modified mask table pointer | Baked into stream B data |
| Collision detection | XOR residue test during erase | XOR residue test during erase | None (objects are static scenery) |
| Position memory | `old_plot_ship_*` ZP vars | `old_plot_pod_*` ZP vars | `level_obj_plot_at_ptr` arrays |
| Frame cycle | Erase old, draw new | Erase old, draw new | Erase if moved, draw if active |
| Sprite count | 18 frames (17 rotation + shield) | 1 frame | 9 types |
| Self-modifying code | 4 sites (data addr, collision, mirror, colour) | 3 sites (data addr, collision, mask) | 2 sites (data A addr, data B addr) |
