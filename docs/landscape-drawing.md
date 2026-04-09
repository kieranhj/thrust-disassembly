# Landscape Drawing Technical Reference

## Overview

The terrain system defines the cave walls of each level using **run-length encoded (RLE) delta-compression**. For every Y scanline in the world, the system tracks the **X position of the left wall** and **X position of the right wall**. The cave opening is the space between them. Only the wall edges are drawn, using XOR (EOR) plotting, which allows incremental updates -- only the pixels that changed since the previous frame are toggled.

---

## Terrain Data Format

Each level defines four parallel byte arrays:

| Array | Pointer Variable | Contents |
|-------|-----------------|----------|
| A | `terrain_left_wall_counter_*` | Left wall run-length counts |
| B | `terrain_left_wall_increment_*` | Left wall signed X-increment per step |
| C | `terrain_right_wall_counter_*` | Right wall run-length counts |
| D | `terrain_right_wall_increment_*` | Right wall signed X-increment per step |

Each entry at index Y defines a terrain **segment**: `A[Y]` scanlines where the wall's X position changes by `B[Y]` each step. The same applies to the right wall with C and D.

### Example: Level 0 Left Wall

```
A (count):     $FF, $FF, $AB, $01, $0F, $01, $0C, $01, $FF
B (increment): $00, $00, $00, $55, $01, $15, $01, $19, $00
```

Reading this sequentially:

| Segment | Count | Increment | Meaning |
|---------|-------|-----------|---------|
| 0 | $FF (255) | $00 | 255 rows, wall stays at same X (vertical) |
| 1 | $FF (255) | $00 | Another 255 vertical rows |
| 2 | $AB (171) | $00 | 171 more vertical rows |
| 3 | $01 (1) | $55 | 1 row, X jumps by +$55 (sharp horizontal step) |
| 4 | $0F (15) | $01 | 15 rows, wall slopes right by 1 per row |
| 5 | $01 (1) | $15 | 1 row, X jumps by +$15 |
| ... | | | |

Negative increments (e.g. `$FF` = -1, `$F1` = -15 signed) slope the wall leftward. The first entries typically represent the sky above the cave (wall at X=0 / X=72 means fully open).

### Level Data Location

Terrain data for all 6 levels is stored in `level_data.6502` (`terrain_left_wall_count_0` through `terrain_right_wall_inc_5`). `initialise_level_pointers` (line 6274) loads the appropriate four pointers into working variables indexed by `level_number`.

---

## Runtime Wall Arrays

Two 256-byte circular buffers store the decoded wall positions:

| Array | Address | Contents |
|-------|---------|----------|
| `terrain_left_wall` | $0400 | Left wall X position at each world-Y scanline |
| `terrain_right_wall` | $0500 | Right wall X position at each world-Y scanline |

Each byte stores a character column index (0-72). The arrays are indexed by world Y position modulo 256, making them circular -- 8-bit index overflow wraps naturally.

### Write Cursor: `terrain_window_y_index`

`terrain_window_y_index` tracks the **bottom edge** of the currently expanded terrain data. It advances when the view scrolls down and retreats when scrolling up.

---

## RLE Decoder

The decoder maintains four independent **triples**, one for each wall track:

| Triple | Variables | Wall |
|--------|-----------|------|
| Left wall 1 | `terrain_left_wall_1_xpos`, `_counter`, `_index` | Left, even scanlines |
| Left wall 2 | `terrain_left_wall_2_xpos`, `_counter`, `_index` | Left, odd scanlines |
| Right wall 1 | `terrain_right_wall_1_xpos`, `_counter`, `_index` | Right, even scanlines |
| Right wall 2 | `terrain_right_wall_2_xpos`, `_counter`, `_index` | Right, odd scanlines |

Each triple tracks:
- **xpos** (A register): The accumulated X position
- **counter** (X register): Remaining count in the current RLE segment
- **index** (Y register): Current position in the data arrays

Two triples per wall exist because the terrain is rendered at half vertical resolution (every other scanline). The two triples populate alternating entries in the wall arrays, offset by one Y index.

### Forward Decoding (Scroll Down)

`terrain_accumulate_xpos_fn` advances one step through the RLE data:

```
if counter == 0:
    index++                                    ; move to next segment
    counter = terrain_data_count[index]        ; load new run length
xpos += terrain_data_x_increment[index]        ; accumulate X delta
counter--
```

### Reverse Decoding (Scroll Up)

`terrain_subtract_xpos_fn` reverses one step:

```
counter++                                      ; undo decrement
xpos -= terrain_data_x_increment[index]        ; reverse X delta
if counter == terrain_data_count[index]:        ; back to segment start?
    index--                                    ; go to previous segment
    counter = 0
```

This bidirectional decoding allows the terrain to be expanded or contracted at the leading edge as the viewport scrolls in either direction.

---

## Terrain Expansion

### Initialisation

`initialise_landscape` (line 909) runs at level start:

1. Resets `terrain_window_y_index` to 0
2. Resets all four triples to their starting state (xpos=0, counter=$FF, index=0 or 1)
3. Replays the decoder forward from Y=0 to `window_ypos`, calling `terrain_process_accumulate_xpos` once per Y step. This "fast-forwards" through the RLE data to populate the wall arrays for the current scroll position.

### Per-Frame Scrolling

`update_window_and_terrain_tables` (line 2598) runs each frame:

1. Applies `window_scroll_x` to `window_xpos_INT` (horizontal scroll needs no terrain recalculation since wall arrays store world-X)
2. If `window_scroll_y > 0` (scrolling down): calls `terrain_process_accumulate_xpos` N times, where N = scroll speed. Each call increments `terrain_window_y_index` and writes new wall entries at the bottom edge.
3. If `window_scroll_y < 0` (scrolling up): calls `terrain_process_subtract_xpos` |N| times, decrementing `terrain_window_y_index` and retracting the bottom edge.

### `terrain_process` Internals

Each call to `terrain_process` (line 984):

1. Sets up zero-page pointers (`terrain_data_count_ptr`, `terrain_data_x_increment_ptr`) to the left wall data arrays
2. Processes left wall triple 1 -- writes result to `terrain_left_wall[terrain_window_y_index]`
3. Processes left wall triple 2 -- writes result to `terrain_left_wall[terrain_window_y_index - 1]`
4. Switches pointers to right wall data arrays
5. Processes right wall triple 1 -- writes to `terrain_right_wall[terrain_window_y_index]`
6. Processes right wall triple 2 -- writes to `terrain_right_wall[terrain_window_y_index - 1]`

---

## Camera Scroll System

`update_window_and_terrain_tables` also manages scroll speed using a damped follow system:

### Vertical Scrolling

- If the ship is near the **bottom** of the viewport (midpoint_window_ypos >= $5D): scroll speed tracks the ship's downward velocity
- If the ship is near the **top** (midpoint_window_ypos < $2F): scroll speed tracks the ship's upward velocity
- A **dead zone** between $3C and $50 where scrolling decelerates to zero
- Gradual deceleration (DEC/INC scroll_y) prevents jarring camera movement

### Horizontal Scrolling

- Similar dead-zone logic based on `midpoint_window_xpos_INT`
- Scroll triggers when the ship is within $10 columns of the left edge or past $30 columns from the left
- Dead zone between $1D and $23

### X World Wrapping

The world X coordinate wraps at approximately $B8-$DC. When `window_xpos_INT` crosses the wrap boundary:

1. A delta ($49 or $B7) is added to all X positions: window, midpoint, player, old player, and all 32 particle X positions
2. The draw tables (1 and 3) are reset by swapping $00/$48 entries, forcing a terrain redraw at the wrap seam

---

## Landscape Rendering

### Draw Tables

Four draw tables track the **previous frame's rendered wall positions** for incremental updates:

| Table | Address | Size | Contents |
|-------|---------|------|----------|
| `terrain_draw_table_1` | $02EF | 17 bytes | Left wall coarse state (X-wrap handling) |
| `terrain_draw_table_2` | $0300 | 94 bytes | Left wall screen-X per scanline (previous frame) |
| `terrain_draw_table_3` | $035E | 17 bytes | Right wall coarse state (X-wrap handling) |
| `terrain_draw_table_4` | $036F | 145 bytes | Right wall screen-X per scanline (previous frame) |

At level start, table 1 is zeroed (left wall was at X=0) and table 3 is set to $48/72 (right wall at screen right edge). This represents "no visible terrain drawn yet".

### `landscape_draw` Algorithm

The main rendering function (line 755) iterates over all visible scanlines:

**Setup:**
```
terrain_draw_table_index = 0
terrain_draw_wall_index = terrain_window_y_index + $49   ; top of visible screen
terrain_draw_addr = SCREEN_START_ADDR + 2                ; start at pixel row 2
```

The offset $49 (73 decimal) is the number of half-resolution scanlines visible on screen. Since `terrain_window_y_index` points to the bottom of the expanded data, adding 73 reads back up to the top of the visible window.

**Per-scanline loop:**

For each scanline (every other pixel row):

1. **Read left wall position**: `terrain_left_wall[terrain_draw_wall_index]`
2. **Convert to screen X**: Subtract `window_xpos_INT` (world-to-screen conversion)
3. **Clamp** to [0, 72] (screen column range)
4. **Compute delta**: Compare clamped X with `terrain_draw_table_2[terrain_draw_table_index]` (previous frame)
   - If new X < old X: wall moved left -- EOR from new X to old X
   - If new X > old X: wall moved right -- EOR from old X to new X
   - If equal: nothing to draw
5. **Update draw table**: Store new X into `terrain_draw_table_2[terrain_draw_table_index]`
6. **Call `draw_terrain`**: EOR the delta columns

Steps 1-6 are repeated for the right wall using `terrain_right_wall` and `terrain_draw_table_4`.

7. **Advance**: Increment wall index, draw table index, and screen address by 2 pixel rows

### Character Row Boundary Crossing

The screen address advances by 2 each iteration (half-resolution). When `terrain_draw_addr_LO AND 7 == 0`, the address has crossed from one character cell into the next. An offset of `$0238` (= `$0240 - 8` = `SCREEN_CHAR_ROW_BYTES - 8`) is added to jump to the start of the next character row.

The loop terminates when the screen address high byte goes negative (past the bottom of screen memory).

### `draw_terrain` Line Drawing

`draw_terrain` (line 1180) draws a horizontal run of columns at a given scanline:

```
Parameters: Y = starting column, X = number of columns
```

1. Compute screen address: `mult_by_8[Y] + terrain_draw_addr_HI` (column * 8 + row base)
2. For each column:
   ```
   LDA #$F0                       ; landscape colour pixel pattern
   EOR (terrain_draw_ptr),Y       ; XOR with screen contents
   STA (terrain_draw_ptr),Y       ; write back
   Y += 8                         ; next column (8 bytes per char column)
   ```

The byte `$F0` in MODE 1 sets the high bitplane for all 4 pixels in the byte, producing colour 2 (the landscape colour). EOR toggles pixels: drawing where there was nothing, erasing where there was terrain. Since only the **delta** columns are drawn each frame, EOR correctly adds new wall segments and removes old ones.

---

## Coordinate System Summary

### World Coordinates

- **Y axis**: 16-bit value `(window_ypos_EXT, window_ypos_INT)`. Increases downward. Each level can be several screens deep.
- **X axis**: 8-bit `window_xpos_INT`. Wraps at ~$B8-$DC (world is 184 columns wide). The visible viewport is 72 columns.

### Screen Mapping

- **Y**: The visible window starts at `terrain_window_y_index + $49` in the wall arrays and reads downward for 73 half-resolution scanlines (146 pixel rows)
- **X**: `screen_X = wall_array[Y] - window_xpos_INT`, clamped to [0, 72]

### Half-Resolution Rendering

Terrain is drawn on every other pixel row (the screen address increments by 2 each iteration). This gives the terrain its characteristic striped appearance and halves the rendering cost. The two wall triples per side populate alternating Y entries in the wall arrays to match this scheme.

---

## Data Flow Summary

```
Level terrain data (RLE: count + delta arrays)
    |
    v
initialise_landscape: replay from Y=0 to window_ypos
    |
    v
Wall arrays: terrain_left_wall[$0400], terrain_right_wall[$0500]
    ^                                    (256-byte circular buffers)
    |
update_window_and_terrain_tables: expand/contract at leading edge
    |
    v
landscape_draw: for each visible scanline
    |
    +---> Read wall X from array
    +---> Convert world X to screen X (subtract window_xpos)
    +---> Clamp to [0, 72]
    +---> Delta against draw_table (previous frame)
    +---> EOR draw only the changed columns
    +---> Update draw_table with new position
```
