# Sprite Drawing Technical Reference

Cycle costs for everything described here are in `sprite-draw-performance.md`.

## Screen Layout

The ULA is programmed for MODE 1 pixels (4 colours, 2 bits per pixel, 4 pixels per byte) and the 6845 CRTC is reprogrammed for a custom 72-character-wide display.

| Constant | Value | Description |
|---|---|---|
| `SCREEN_BASE_ADDR` | `$3C80` | Start of screen memory |
| `SCREEN_WIDTH_CHARS` | 72 | Character columns across screen |
| `SCREEN_CHAR_ROW_BYTES` | `$0240` (576) | Bytes per character row (72 * 8) |
| `SCREEN_START_ADDR` | `$4100` | Gameplay area (after 2 status bar rows) |

### MODE 1 Pixel Format

Each screen byte holds 4 pixels as two interleaved bitplanes:

| Pixel | Bit 7 | Bit 6 | Bit 5 | Bit 4 | Bit 3 | Bit 2 | Bit 1 | Bit 0 |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| 0     | H     |       |       |       | L     |       |       |       |
| 1     |       | H     |       |       |       | L     |       |       |
| 2     |       |       | H     |       |       |       | L     |       |
| 3     |       |       |       | H     |       |       |       | L     |

H = high bitplane, L = low bitplane. The two bits select one of 4 colours.

### Character Cell Memory

Within a character cell, 8 consecutive bytes are 8 pixel rows (top to bottom). Moving right one character column adds 8 bytes; moving down one character row adds `$0240`.

### Pixel Mask Tables

Three tables give per-pixel-column masks for the three non-black colours:

```
pixel_masks_1:  $88, $44, $22, $11   ; colour 3 (both bitplanes)
pixel_masks_2:  $80, $40, $20, $10   ; colour 2 (high bitplane)
pixel_masks_3:  $08, $04, $02, $01   ; colour 1 (low bitplane)
```

Index 0 = leftmost pixel in the byte, index 3 = rightmost.

---

## Screen Address Calculation

The ship, pod, particle and line plotters compute screen addresses with the same shift chain. Given a viewport-relative position (X integer, Y integer):

### Y Contribution (Character Row)

Y is split into a character row (bits 7-3) and a pixel row within the cell (bits 2-0). The character row is multiplied by `$0240` with shift-and-add:

```
addr = $3800 + (Y AND $F8) * 72
```

A chain of ROR instructions spreads the product across the high and low address bytes, then `SCREEN_ADDR_HI_OFFSET` (`$38`) is added to the high byte.

### X Contribution (Character Column)

The integer X position indexes the `mult_by_8` lookup table (`mult_by_8_LO` at `$09C0`, `mult_by_8_HI` at `$0A10`), which gives `X * 8` as a 16-bit value. This byte offset is added to the row address.

### Pixel Row Offset

The low 3 bits of Y (`AND #$07`) are added to the address low byte to select the scanline within the character cell.

### Sub-Character Pixel Column

The top 2 bits of the fractional X byte give a pixel offset (0-3) within a screen byte. It is extracted with three ROLs and `AND #PIXEL_COLUMN_MASK` (`$03`), stored as the "pixel column", and added to each sprite pixel position during rendering.

Static objects use a separate routine, `calculate_object_plot_addr`, which works in whole character columns (no pixel column) and builds the same address with LSR/ROR.

---

## XOR (EOR) Drawing

All sprites are drawn with XOR. Each pixel is toggled:

```asm
LDA  mask_table,X       ; pixel mask for this column
EOR  (screen_ptr),Y     ; XOR with screen contents
STA  (screen_ptr),Y     ; write back
```

Drawing the same sprite at the same position twice restores the original screen, so a sprite is erased by redrawing it at its previous position.

### Erase-Then-Draw Cycle

Each frame, for each sprite:

1. **Erase**: restore the previous position from the saved `old_*` variables and XOR-plot the sprite to remove it
2. **Calculate**: compute the new screen position from world coordinates
3. **Draw**: XOR-plot the sprite at the new position
4. **Save**: store the new position in the `old_*` variables for next frame's erase

### Collision Detection via XOR

Ship and pod collisions are detected during the **erase** pass. After XOR-erasing a pixel, the result is ANDed with the pixel mask (`pixel_masks_1`, both bitplanes). If nothing has been drawn over the pixel since it was plotted, the erase restores the original (black) pixel and the AND gives zero. If something else (terrain, an object, a bullet) has been drawn there, the residue is non-zero and the collision flag is set.

The 3-byte collision test site is patched with one of:
- `AND pixel_masks_1,X` (followed in the code by `BEQ loop`): collision test, used for the erase pass
- `JMP plot_loop`: skips the test, used for the draw pass

The templates are `ship_AND_pixel_mask_CODE` / `ship_SKIP_pixel_mask_CODE` (ship) and `ship_AND_pixel_mask_CODE` / `ship_fn_SKIP_pixel_mask_CODE` (pod), copied in by a 3-byte loop before each pass.

---

## Ship Sprite Rendering

`update_shield_tractor_draw_ship_and_pod` (`thrust.6502:4656`) runs the erase and draw passes; both call `plot_ship_or_shield` (`thrust.6502:4906`), which sets up the self-modified code and jumps into `plot_ship_loop`.

### Sprite Data Format

Ship sprites use a single-stream format in which bit 7 of each byte marks a row advance:

| Value | First read (BMI test) | Re-read after row advance |
|-------|----------------------|-------------------------------|
| `$00`-`$7F` | Pixel: plot it | n/a |
| `$80` | Row advance | Empty row: no pixel plotted |
| `$81`-`$FE` | Row advance | First pixel of the new row |
| `$FF` | End of sprite | n/a |

A byte in `$81`-`$FE` both ends the current row and gives the first pixel of the next one. Bit 7 is harmless when the byte is reused as pixel data because the column decode only uses bits 0-5:

- `AND #$3C` extracts the character column (bits 5-2)
- `AND #$03` extracts the pixel within the byte (bits 1-0)

If the first byte of a sprite has bit 7 set, the first row is skipped (row 0 is empty).

The 17 rotation frames (`ship_sprite_0_data` to `ship_sprite_16_data`) hold 38-41 pixels each across 13-16 non-empty rows; the shield (`sheild_sprite_data`) has 44 pixels. Frame 0 (upright) is 38 pixels in 16 rows.

### Pixel Column Decode

Each pixel byte is an X position relative to the sprite origin:

```asm
SEC
CMP  #$FF                     ; self-modified: CMP #$FF (normal) or EOR #$1F (mirrored)
ADC  plot_ship_pixel_column   ; add sub-character offset (0-3)
TAY                           ; save combined value
AND  #$3C                     ; bits 5-2 = character column * 4
ROL  A                        ; * 2 = byte offset (8 bytes per column)
STA  plot_ship_at_y_offset    ; screen byte offset from base
TYA
AND  #PIXEL_COLUMN_MASK       ; bits 1-0 = pixel within byte (0-3)
TAX                           ; index into pixel mask table
```

`CMP #$FF` leaves A unchanged and clears carry (A < `$FF`), so the ADC adds just the pixel column. `EOR #$1F` leaves carry set from the SEC, so mirrored pixels become `(x EOR $1F) + 1 + column`.

The byte offset goes into Y for `EOR (plot_ship_at_ptr),Y`.

### Angles and Mirroring

`plot_ship_sprite_number` holds the ship angle (0-31) or `$FF` for the shield. Angles 0-16 use `ship_sprite_ptr_table` directly. Angles 17-31 use frame `32 - angle` (computed as `(angle EOR $1F) + 1`) with the mirrored decode above. The shield maps to index `SHIELD_SPRITE_INDEX` (`$11`).

### Self-Modifying Code

| Site | What changes | Purpose |
|------|-------------|---------|
| `ship_sprite_addr_1/2/3` | LDA operand address | Select the sprite frame data |
| `ship_pixel_mask_test` | 3-byte instruction | Enable/disable collision detection |
| `plot_ship_write_opcode` / `plot_ship_write_value` | `CMP #$FF` vs `EOR #$1F` | Normal vs mirrored X |
| `ship_load_pixel_mask` | Mask table address | Ship colour (`pixel_masks_3`, colour 1) vs shield colour (`pixel_masks_1`, colour 3) |

Three `LDA sprite_data,X` instructions are patched to the same address: one in the main loop and one after each kind of row advance, so the row-advance code re-reads the current byte and falls straight back into the pixel decode.

### Character Row Boundary Crossing

`plot_ship_row_counter` holds the rows remaining in the current character cell, initialised to `7 - (ptr AND 7)`. Each row advance decrements it and increments the screen pointer by 1. When it goes negative:

```asm
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

`$0239` = `$0240 - 7` steps from the bottom row of one cell to the top row of the cell below.

### Ship Sprite State Variables

| Variable | Address | Purpose |
|---|---|---|
| `plot_ship_at_ptr` | $0072 | Current screen write address (16-bit) |
| `plot_ship_pixel_column` | $0075 | Sub-byte pixel offset (0-3) |
| `plot_ship_sprite_number` | $0076 | Angle (0-31) or `$FF` for shield |
| `plot_ship_index` | $007A | Byte index into the sprite data |
| `plot_ship_row_counter` | $0070 | Rows remaining before char row boundary |
| `plot_ship_at_y_offset` | $0071 | Byte offset for current pixel |
| `plot_ship_collision_detected` | $002A | Set to $FF on collision during erase |
| `old_plot_ship_at_ptr` | $000E | Previous frame screen address |
| `old_plot_ship_pixel_column` | $0010 | Previous frame pixel column |
| `old_plot_ship_sprite_number` | $0011 | Previous frame sprite number |

### Two-Stream Ship Plotter (`_FAST_SPRITES`)

With `_FAST_SPRITES` (currently `(_SWRAM_BUILD AND FALSE)`, so off by default) a second `plot_ship_or_shield` (`thrust.6502:13918`) replaces the one above. It uses pre-baked two-stream data from `tools/output/ship_twostream_data.asm`, generated by `tools/generate_ship_streams.py`: 32 angles x 4 pixel columns plus 4 shield variants, about 12KB, assembled into sideways RAM bank `SPRITE_BANK` (5). Stream A is the object-style offset stream (below); stream B holds `pixel_masks_1`-style bytes. The loop (`plot_ship_ts_loop`) stores each stream B byte to `ship_ts_mask_temp` for the collision test and reduces it to the ship colour with a self-modified `AND #$0F` (`AND #$FF` for the shield). Mirroring and the pixel column are baked into the data. The pod still uses its own plotter; the generator also emits `pod_ts_*` streams but nothing uses them.

---

## Pod Sprite Rendering

The pod uses the same single-stream data format as the ship. `plot_pod_sprite` (`thrust.6502:5664`) is a separate copy of the plotter with its own self-modified sites.

### Pod-Specific Differences

- One frame (`pod_sprite_data`, 28 pixels in 11 rows), no mirroring; the decode uses `CLC` + `pod_temp` instead of `SEC`/`CMP`/`TAY`
- Drawn in colour 3: `draw_pod_and_collision_test` passes X = 3 to `set_plot_pod_sprite_mask_addr`, which selects `pixel_masks_1` from `pixel_mask_ptrs_LO/HI`
- No row counter: a row advance tests `(ptr AND 7) == 7` to detect the character row crossing
- `plot_pod_sprite` computes the screen address inline; the erase pass enters at `L21B6` with the saved address
- The collision flag store is self-modified (`plot_pod_sprite_addr_zp`); `draw_pod_and_collision_test` always points it at `plot_pod_collision_detected` ($002B)
- Position is `midpoint - midpoint_delta` (the pod is on the opposite side of the tether midpoint from the ship, which uses `midpoint + midpoint_delta`)

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

`draw_pod_and_collision_test` (`thrust.6502:5834`) is called after the ship is drawn under normal gravity and before the ship under reversed gravity. It:

1. Points the collision store at `plot_pod_collision_detected`, clears it, and patches `AND pixel_masks_1,X` into the collision test site
2. If `pod_sprite_plotted_flag` is set: clears it, restores the old position and XOR-erases (collision test active)
3. Returns if `pod_lifted_flag` is clear
4. Patches `JMP plot_pod_loop` into the test site and calculates the new position from `midpoint - delta`
5. If `pod_tethered_flag` is set: draws the pod at the new position, sets `pod_sprite_plotted_flag` and saves the position to the `old_*` variables

---

## Static Object Sprite Rendering

Objects use a **two-stream** sprite format and `plot_static_sprite` (`thrust.6502:2449`). Plotted types are the guns, fuel, pod stand, generator and door switches (`$00`-`$08`), plus in SWRAM builds the laser turrets (`$09`-`$0C`) and bobbing mines (`$0E`, `$0F`). The gravity well (`$0D`), teleporter (`$10`) and door (`$11`) skip the sprite code entirely; the first two have stream data in the table but it is never plotted.

In the non-SWRAM build the sprite data comes from `thrust1/obj_sprite_data.asm`; SWRAM builds use `tools/output/object_sprites.asm`, written by `tools/sprite_editor.py`.

### Two-Stream Data Format

Each object sprite is two parallel byte arrays:

**Stream A** (offsets/control):
| Value | Meaning |
|-------|---------|
| `$00`-`$7F` | Y register offset for `(ptr),Y` addressing: selects the screen byte |
| `$80`-`$FE` | Row advance. Low 7 bits = Y offset for the first byte of the new row |
| `$FF` | End of sprite |

**Stream B** (pixel data): each byte is a complete MODE 1 screen byte (4 pixels, both bitplanes) to XOR onto the screen, consumed in step with stream A.

### Static Sprite Plotting Algorithm

```
rows_to_boundary = 8 - (ptr AND 7)
for each byte pair (A[i], B[i]):
    if A[i] == $FF:
        return                        ; end of sprite
    if A[i] bit 7 set:
        ptr += 1                      ; next pixel row
        rows_to_boundary -= 1
        if rows_to_boundary == 0:     ; crossed character row boundary
            ptr += $0238              ; (undo the +1, then add $0239)
            rows_to_boundary = 8
        Y = A[i] AND $7F
    else:
        Y = A[i]
    screen[ptr + Y] ^= B[i]           ; XOR plot
```

`plot_static_sprite` also sets `OBJ_flag_drawn` in `level_obj_flags` for the current object. Writing whole bytes (up to 4 pixels per EOR) makes this much cheaper per pixel than the ship plotter.

### Object Update Loop

`update_and_draw_all_objects` (`thrust.6502:1645`) walks the level's object list until a `$FF` type each frame (see `object-update-loop.md` for the full per-object logic). For drawing:

1. Load the object type (`$00`-`$11`). Gravity wells, teleporters and doors jump to the next object here
2. Pod stand: set `OBJ_flag_alive`, clear it once the pod has been lifted. Generator: toggle `OBJ_flag_alive` on bit 2 of `countdown_timer_ticks` while the planet countdown runs, so it flashes
3. Patch the stream A/B addresses into `plot_static_sprite` from `obj_sprite_data_A_table_LO/HI` and `obj_sprite_data_B_table_LO/HI`
4. If `OBJ_flag_drawn` is set: run `object_visibility_test` for the new screen address. If it equals the cached `level_obj_plot_at_ptr_LO/HI` and the object is still alive, skip both erase and redraw. Otherwise XOR-erase at the cached address and clear `OBJ_flag_drawn`
5. If `OBJ_flag_alive` is clear, go to the next object
6. Run collisions and per-type behaviour, then, unless step 4 skipped it, XOR-draw at the new address (if on screen) and cache the address

### Object Visibility Culling

`object_visibility_test` (`thrust.6502:2286`):

- **Y**: the high byte of `current_obj_ypos - window_ypos` (16-bit) must be zero; then, after subtracting `$38`, the low byte must be in `$11`-`$7D`. These units are two scanlines; `calculate_object_plot_addr` doubles them
- **X**: `current_obj_xpos - window_xpos` (unsigned, so objects to the left wrap to large values) must be below the per-type `object_type_cull_size_table` entry (`$44`-`$47`: the 72-column screen width less the sprite width)

If both pass it falls through to `calculate_object_plot_addr`, which writes `obj_plot_sprite_at_ptr`.

---

## Summary of Sprite System Architecture

| Feature | Ship | Pod | Static objects |
|---------|------|-----|----------------|
| Data format | Single-stream, bit-7 dual-purpose | Single-stream, bit-7 dual-purpose | Two parallel streams (offset + pixel byte) |
| Pixel granularity | Per-pixel (mask table lookup) | Per-pixel (mask table lookup) | Per-byte (up to 4 pixels per write) |
| Colour selection | Self-modified mask table pointer | Self-modified mask table pointer | Baked into stream B |
| Collision detection | XOR residue test during erase | XOR residue test during erase | None in the plotter (bullet hits are bounding-box tests in the update loop) |
| Position memory | `old_plot_ship_*` ZP vars | `old_plot_pod_*` / `old_pod_pixel_column` ZP vars | `level_obj_plot_at_ptr_LO/HI` arrays |
| Frame cycle | Erase old, draw new | Erase old, draw new (when tethered) | Erase and redraw only if moved or died |
| Sprite count | 18 frames (17 rotation + shield), 32 angles via mirroring | 1 frame | 9 types (15 plotted types in SWRAM builds) |
| Self-modifying code | 4 sites (data addr, collision, mirror, colour) | 4 sites (data addr, collision, colour, collision flag address) | 2 sites (stream A addr, stream B addr) |
