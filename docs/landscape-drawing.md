# Landscape Drawing Technical Reference

## Overview

Each level's cave walls are stored as **run-length encoded (RLE) deltas**. For every world-Y row the game knows the X position of the **left wall** and the **right wall**; the open cave is the space between them and everything outside is solid. Only the change since the previous frame is drawn, using EOR plotting, so the routine toggles just the columns whose solid/open state changed.

Screen geometry used throughout: MODE 1 ULA setting (2bpp, 4 pixels per byte), CRTC reprogrammed to 72 character columns (`SCREEN_WIDTH_CHARS`), 30 character rows of which the top 2 are the status bar. One world-Y row is drawn as one pixel row on every other scanline, so the 28 playfield character rows show 111 terrain rows. Cycle costs are in `landscape-draw-performance.md`.

---

## Terrain Data Format

Each level defines four parallel byte arrays:

| Array | Data label | Contents |
|-------|------------|----------|
| A | `terrain_data_level_N_A` | Left wall run lengths |
| B | `terrain_data_level_N_B` | Left wall signed X increment per row |
| C | `terrain_data_level_N_C` | Right wall run lengths |
| D | `terrain_data_level_N_D` | Right wall signed X increment per row |

Entry `i` is a **segment**: for `A[i]` rows the wall X changes by `B[i]` each row. C and D do the same for the right wall.

### Example: Level 0 Left Wall

```
A (count):     $FF, $FF, $AB, $01, $0F, $01, $0C, $01, $FF
B (increment): $00, $00, $00, $55, $01, $15, $01, $19, $00
```

| Segment | Count | Increment | Meaning |
|---------|-------|-----------|---------|
| 0 | $FF (255) | $00 | 255 rows, wall X unchanged (vertical) |
| 1 | $FF (255) | $00 | another 255 vertical rows |
| 2 | $AB (171) | $00 | 171 more vertical rows |
| 3 | $01 (1) | $55 | 1 row, X jumps by +$55 (horizontal step) |
| 4 | $0F (15) | $01 | 15 rows, wall slopes right by 1 per row |
| 5 | $01 (1) | $15 | 1 row, X jumps by +$15 |
| ... | | | |

Negative increments (`$FF` = -1, `$F1` = -15) slope the wall left. The leading segments are sky: the left wall starts at X=0 and the right wall at X=$FF, so the whole width is open. Every level starts with two `$FF,$00` segments on both walls; the decoder initialisation relies on this (see below).

### Level Data Location

The terrain data for all six levels is inline in `thrust.6502` (`terrain_data_level_0_A` .. `terrain_data_level_5_D`, from line 6492).

`initialise_level_pointers` (`thrust.6502:7293`) copies the four per-level pointers from `terrain_left_wall_counter_ptrs_LO` etc. into `terrain_left_wall_counter_LO/HI`, `terrain_left_wall_increment_LO/HI`, `terrain_right_wall_counter_LO/HI` and `terrain_right_wall_increment_LO/HI`, indexed by `level_number`.

---

## Runtime Wall Arrays

Two 256-byte circular buffers hold the decoded wall positions:

| Array | Address | Contents |
|-------|---------|----------|
| `terrain_left_wall` | $0400 | Left wall world X for each row |
| `terrain_right_wall` | $0500 | Right wall world X for each row |

Each byte is a **world** X in character columns (0-255), not a screen column. The arrays are indexed modulo 256, so 8-bit index overflow wraps naturally.

### `terrain_window_y_index`

`terrain_window_y_index` marks the **top** edge of the decoded window: the buffer holds 256 consecutive rows from index `terrain_window_y_index` (oldest/highest row) to `terrain_window_y_index - 1` (lowest row). It increments when the view scrolls down and decrements when it scrolls up. `landscape_draw` reads from `terrain_window_y_index + $49` onwards, so there are 73 decoded rows above the visible area and 72 below it.

Door logic (`tick_door_logic` and the per-level door routines) also writes directly into `terrain_left_wall` to open and close doors.

---

## RLE Decoder

There are four decoder states (**triples**), two per wall:

| Triple | Variables | Writes to |
|--------|-----------|-----------|
| Left wall 1 | `terrain_left_wall_1_xpos`, `_counter`, `_index` | `terrain_left_wall[terrain_window_y_index]` (top edge) |
| Left wall 2 | `terrain_left_wall_2_xpos`, `_counter`, `_index` | `terrain_left_wall[terrain_window_y_index - 1]` (bottom edge) |
| Right wall 1 | `terrain_right_wall_1_xpos`, `_counter`, `_index` | `terrain_right_wall[terrain_window_y_index]` (top edge) |
| Right wall 2 | `terrain_right_wall_2_xpos`, `_counter`, `_index` | `terrain_right_wall[terrain_window_y_index - 1]` (bottom edge) |

Each triple is passed to the step function in registers: **A** = accumulated xpos, **X** = remaining count in the current segment, **Y** = segment index.

Two triples per wall are needed because the data is deltas: decoding a new row requires the decoder state for the neighbouring row. Scrolling down adds a row at the bottom edge and scrolling up adds one at the top edge, so each edge keeps its own state. Triple 2 runs 255 rows ahead of triple 1 (it starts at segment 1 rather than segment 0; with the two leading 255-row zero-increment segments that is exactly 255 rows), and because it writes at `index - 1` = `index + 255` both triples store row *r* at array index *r* mod 256.

### Forward step (scroll down)

`terrain_accumulate_xpos_fn` (`thrust.6502:1155`):

```
if counter == 0:
    index++                                    ; next segment
    counter = count[index]                     ; load its run length
xpos += x_increment[index]
counter--
```

### Reverse step (scroll up)

`terrain_subtract_xpos_fn` (`thrust.6502:1172`):

```
counter++                                      ; undo the decrement
xpos -= x_increment[index]                     ; undo the delta
if counter == count[index]:                    ; back at segment start?
    index--                                    ; previous segment
    counter = 0
```

---

## Terrain Expansion

### Initialisation

`initialise_landscape` (`thrust.6502:929`) runs at level start and on respawn:

1. Sets `terrain_window_y_index` to 0.
2. Resets the triples: left xpos = 0, right xpos = $FF, all counters = $FF, triple 1 index = 0, triple 2 index = 1.
3. Calls `terrain_process_accumulate_xpos` `window_ypos + 256` times (16-bit count from `window_ypos_EXT`/`window_ypos_INT`), fast-forwarding the decoder to the current scroll position and filling both arrays. Afterwards `terrain_window_y_index` equals `window_ypos_INT`.

### Per-frame scrolling

`update_window_and_terrain_tables` (`thrust.6502:2895`) runs once per game frame:

1. Adds `window_scroll_x` to `window_xpos_INT`. Horizontal scroll needs no decoding because the arrays hold world X.
2. If `window_scroll_y > 0`: adds it to `window_ypos` and calls `terrain_process_accumulate_xpos` that many times. Each call increments `terrain_window_y_index` and decodes one new row at each edge.
3. If `window_scroll_y < 0`: calls `terrain_process_subtract_xpos` |N| times, each decrementing `terrain_window_y_index` first.

### `terrain_process` internals

`terrain_process_accumulate_xpos` / `terrain_process_subtract_xpos` patch the target of `terrain_call_process_fn` (a self-modified `JMP`) to the forward or reverse step, adjust `terrain_window_y_index`, then run `terrain_process` (`thrust.6502:1001`):

1. Points `terrain_data_count_ptr` / `terrain_data_x_increment_ptr` (ZP $9F / $9D) at the left wall arrays.
2. Steps left triple 1 and stores the result at `terrain_left_wall[terrain_window_y_index]`.
3. Steps left triple 2 and stores at `terrain_left_wall[terrain_window_y_index - 1]`.
4. Switches the pointers to the right wall arrays.
5. Steps right triple 1 and stores at `terrain_right_wall[terrain_window_y_index]`.
6. Steps right triple 2 and stores at `terrain_right_wall[terrain_window_y_index - 1]`.

---

## Camera Scroll System

`update_window_and_terrain_tables` also computes next frame's scroll speeds, a damped follow of the ship's midpoint.

### Vertical

`midpoint_window_ypos_INT = midpoint_ypos_INT - window_ypos_INT - $38` (`SCREEN_ADDR_HI_OFFSET`; larger = lower on screen).

- Moving down (`velocity_vectory_INT` >= 0): if ydist >= $5D, `window_scroll_y = velocity_vectory_INT + 1`. Otherwise, if the window is already scrolling down faster than `force + 1`, decelerate by 1 (never landing on 0).
- Moving up: if ydist < $2F, `window_scroll_y = velocity_vectory_INT - 1`. Otherwise decelerate an upward scroll that is outrunning the ship by 1.
- Overshoot clamp: scrolling down with ydist < $3C, or scrolling up with ydist >= $50, sets `window_scroll_y = 0`.

### Horizontal

`midpoint_window_xpos_INT = midpoint_xpos_INT - window_xpos_INT`.

- xdist < $10: `window_scroll_x = xdist - $10` (scroll left). xdist > $30: `window_scroll_x = xdist - $30` (scroll right).
- Scrolling right: xdist < $1D stops the scroll; $1D <= xdist < $30 decelerates by 1.
- Scrolling left: xdist >= $23 stops the scroll; $10 <= xdist < $23 decelerates by 1.

### X world wrapping

After the scroll update, `window_xpos_INT` is kept in $01-$B7 (`thrust.6502:3198`):

- `window_xpos_INT >= WORLD_X_WRAP_THRESHOLD` ($B8): add `WORLD_X_WRAP_FORWARD` ($49 = 73).
- `window_xpos_INT == 0` or >= $DC (scrolled left past 0): add `WORLD_X_WRAP_BACKWARD` ($B7 = -73).

The same delta is added to `window_xpos_INT`, `midpoint_xpos_INT`, `player_xpos_INT`, `old_player_xpos_INT` and all 32 particle X positions. The world is therefore 183 columns around as far as the window is concerned.

A 73-column jump is wider than the screen, so the views before and after a wrap don't overlap. The wrap then walks every cached scanline (loop at `thrust.6502:3271`, X = $11-$7F through `terrain_draw_table_1`/`_3`, i.e. entries 0-110 of tables 2 and 4) and, for rows where both walls are pinned to the same screen edge (both 0 or both 72), flips both to the opposite edge. Such rows are fully solid either way, so the flip keeps the cache consistent with the new clamped positions and nothing is redrawn. In all six levels the window only reaches the wrap thresholds on the surface, where every row is either open sky (walls clamped to 0 and 72) or solid ground (both walls pinned to one edge), so a wrap normally costs no redraw. A row whose wall was still on screen in the previous frame does get a near full-width EOR.

---

## Landscape Rendering

### Draw tables

The cache of last frame's screen X per scanline:

| Table | Address | Contents |
|-------|---------|----------|
| `terrain_draw_table_2` | $0300-$036E | Left wall screen X per scanline (111 entries) |
| `terrain_draw_table_4` | $036F-$03DD | Right wall screen X per scanline (111 entries) |
| `terrain_draw_table_1` | $02EF | Alias: `terrain_draw_table_2 - $11` |
| `terrain_draw_table_3` | $035E | Alias: `terrain_draw_table_4 - $11` |

Tables 1 and 3 are not separate data. They let the loops in `clear_screen_and_init` and the X-wrap fix-up index both caches with X running $11-$7F (`INX`/`BPL` terminates at $80), which covers entries 0-110. (The source comments give tables 1/3 as "11 bytes"; that is $11 = 17. The "94 bytes" and "145 bytes" comments on tables 2 and 4 are also wrong: each holds 111 entries.)

`clear_screen_and_init` (`thrust.6502:10054`) clears the screen and sets table 2 to 0 and table 4 to 72: "nothing drawn", left wall at the left edge, right wall at the right edge.

### `landscape_draw` algorithm

`landscape_draw` (`thrust.6502:772`).

**Setup:**
```
terrain_draw_table_index = 0
terrain_draw_wall_index  = terrain_window_y_index + $49   ; first visible row
terrain_draw_addr        = HI(SCREEN_START_ADDR):$02      ; $4102: playfield row 0, pixel row 2
SBC operands (window_xpos_1/_2) = window_xpos_INT - 1     ; self-modified
CLC
```

`SCREEN_START_ADDR` is `$3C80 + 2 * $240` = $4100. With carry clear, `SBC #(window_xpos_INT - 1)` computes `wall - window_xpos_INT`, saving a `SEC` per wall per scanline. The second SBC relies on every path through the left-wall code leaving C=0.

**Per scanline, left wall:**

1. `A = terrain_left_wall[terrain_draw_wall_index] - window_xpos_INT`.
2. Clamp: borrow → 0; >= 72 → 72. Store in `terrain_xpos_1_clipped`.
3. `delta = new - terrain_draw_table_2[terrain_draw_table_index]`.
   - delta = 0: nothing to draw.
   - delta > 0 (moved right): EOR `delta` columns starting at the **old** X.
   - delta < 0 (moved left): EOR `|delta|` columns starting at the **new** X.
4. Store the new X in the table and call `draw_terrain` (Y = start column, X = count).

The right wall repeats this with `terrain_right_wall`, `terrain_xpos_2_clipped` and `terrain_draw_table_4`.

5. Increment `terrain_draw_wall_index` and `terrain_draw_table_index`; add 2 to the screen address.

### Character row crossing

The screen address advances 2 bytes (2 pixel rows) per scanline. When `terrain_draw_addr_LO AND 7` becomes 0 the address has run off the bottom of a character cell, so `SCREEN_CHAR_ROW_BYTES - 8` ($0238) is added to move to the top of the next character row. The first playfield character row starts at pixel row 2, so it contributes 3 scanlines and the other 27 contribute 4 each: **111 scanlines**. The loop ends when the add carries the address to $8000 (`BMI`).

The `$49` setup offset is the gap between `terrain_window_y_index` and the first visible row, not the scanline count.

### `draw_terrain`

`draw_terrain` (`thrust.6502:1197`; Y = start column, X = column count, C = 0 on entry):

1. `terrain_draw_ptr = mult_by_8[Y] + (terrain_draw_addr_HI << 8)`, then `Y = terrain_draw_addr_LO`.
2. For each column:
   ```
   LDA #LANDSCAPE_COLOUR_BYTE     ; $F0
   EOR (terrain_draw_ptr),Y
   STA (terrain_draw_ptr),Y
   Y += 8                         ; next character column; INC ptr+1 on overflow
   ```

`$F0` sets the high bit of all four 2bpp pixels in the byte, giving logical colour 2 (the landscape colour). Because only the delta is drawn, EOR adds newly solid columns and removes ones that became open. Cycle costs and a proposed unrolled version are in `landscape-draw-performance.md`.

---

## Coordinate Summary

- **World Y**: 16-bit `(window_ypos_EXT, window_ypos_INT)`, increasing downward. One world row = one drawn scanline = 2 pixel rows.
- **World X**: 8-bit, in character columns. `window_xpos_INT` stays in $01-$B7; the viewport is 72 columns.
- **Screen Y**: scanline *t* (0-110) reads wall index `terrain_window_y_index + $49 + t`.
- **Screen X**: `wall - window_xpos_INT`, clamped to [0, 72].

Drawing every other pixel row halves the cost and gives the terrain its striped look.

---

## Data Flow

```
Level RLE data (count + increment arrays, per wall)
    |
    v
initialise_landscape: replay window_ypos + 256 rows
    |
    v
terrain_left_wall[$0400], terrain_right_wall[$0500]   (256-row circular buffers, world X)
    ^
    |
update_window_and_terrain_tables: decode new rows at top/bottom edge as Y scrolls;
                                  X wrap + cache fix-up
    |
    v
landscape_draw: 111 scanlines
    +---> wall world X - window_xpos_INT, clamp to [0, 72]
    +---> delta against terrain_draw_table_2 / _4 (last frame)
    +---> draw_terrain: EOR only the changed columns
    +---> store new X in the table
```
