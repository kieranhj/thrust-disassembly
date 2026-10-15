# Landscape Draw Performance Analysis

## Overview

`landscape_draw` (`thrust.6502:933`) runs once per game frame. It walks every visible terrain scanline, compares each wall's screen X with last frame's, and EOR-draws only the changed columns. This document counts 6502 cycles through each path to estimate best-case, typical and worst-case cost. The algorithm itself is described in `landscape-drawing.md`.

**Platform and budget:** BBC Micro Model B, 2 MHz 6502. Vsync is 50 Hz (40,000 cycles; 39,936 exact). The main loop waits in `draw_player_timed_to_vsync` until the centisecond clock reaches 3, so a game frame is at least 3 cs = **60,000 cycles** (~33 frames/s). Percentages below are of that 60,000-cycle game frame.

**Screen:** MODE 1 ULA setting (2bpp, 4 pixels per byte), CRTC reprogrammed to 72 character columns; screen memory $3C80-$7FFF.

Instruction timings assume no page-crossing penalty unless stated. The wall arrays ($0400, $0500) are page-aligned and the draw tables ($0300-$03DD) never cross a page with indices 0-110, so `abs,Y` accesses in `landscape_draw` don't incur it. `EOR (terrain_draw_ptr),Y` in `draw_terrain` does take +1 when pointer + Y crosses a page, which depends on alignment and averages roughly half the columns; the figures below leave this out and are therefore about 0.5 cycles per column optimistic.

---

## Scanline Count

The loop draws every other pixel row, starting at pixel row 2 of the first playfield character row, and stops when the screen address reaches $8000 (`BMI` at `thrust.6502:1089`).

- Screen memory $3C80-$7FFF = 17,280 bytes = 30 character rows of 576 ($0240) bytes
- Status bar: 2 rows; playfield: 28 rows
- 4 scanlines per character row, except the first, which starts at pixel row 2 and has 3

**111 scanlines per frame** (28 x 4 - 1). The `$49` (73) constant at `thrust.6502:940` is the offset from `terrain_window_y_index` to the first visible row in the wall arrays, not the scanline count.

---

## Code Structure

Per scanline:

1. **Left wall** (`thrust.6502:958-1011`): read, convert to screen X, clamp, delta against `terrain_draw_table_2`, `draw_terrain` if non-zero.
2. **Right wall** (`thrust.6502:1014-1065`): the same against `terrain_draw_table_4`.
3. **Advance** (`thrust.6502:1068-1091`): bump the indices and screen address, handle the character row crossing.

`draw_terrain` is called 0, 1 or 2 times per scanline.

---

## Setup (once per frame)

```
landscape_draw:
    LDA #$00                    ; 2
    STA terrain_draw_table_index ; 3 (ZP)
    LDA #$49                    ; 2
    CLC                         ; 2
    ADC terrain_window_y_index  ; 4 (absolute: variable lives in the code area)
    STA terrain_draw_wall_index ; 3
    LDA #$02                    ; 2
    STA terrain_draw_addr_LO    ; 3
    LDA #HI(SCREEN_START_ADDR)  ; 2
    STA terrain_draw_addr_HI    ; 3
    LDX window_xpos_INT         ; 3 (ZP $00)
    DEX                         ; 2
    STX window_xpos_2           ; 4 (absolute, self-mod)
    STX window_xpos_1           ; 4 (absolute, self-mod)
    CLC                         ; 2
                                ; ----
                                ; 41 cycles (+12 JSR/RTS)
```

`window_xpos_INT - 1` becomes the SBC immediate operand. With carry clear, `SBC` computes `wall - (window_xpos - 1) - 1 = wall - window_xpos`, saving a `SEC` per wall per scanline.

---

## Per-Scanline: Left Wall

### Path A: no change (delta = 0)

```
    LDY terrain_draw_wall_index ; 3
    LDA terrain_left_wall,Y     ; 4
    SBC #imm                    ; 2 (self-modified)
    BCS (taken)                 ; 3
    CMP #SCREEN_WIDTH_CHARS     ; 2
    BCC (taken)                 ; 3
    STA terrain_xpos_1_clipped  ; 3
    LDY terrain_draw_table_index; 3
    SEC                         ; 2
    SBC terrain_draw_table_2,Y  ; 4
    BCS (taken)                 ; 3
    CLC                         ; 2
    BEQ (taken)                 ; 3
                                ; ----
                                ; 37 cycles
```

### Path B: moved right (new > old)

```
    ...as path A up to CLC...   ; 34
    BEQ (not taken)             ; 2
    TAX                         ; 2
    LDA terrain_draw_table_2,Y  ; 4
    STA terrain_draw_start_x    ; 3
    LDA terrain_xpos_1_clipped  ; 3
    STA terrain_draw_table_2,Y  ; 5
    LDY terrain_draw_start_x    ; 3
    JSR draw_terrain            ; (counted in draw_terrain cost)
                                ; ----
                                ; 56 + draw_terrain
```

### Path C: moved left (new < old)

```
    ...read/clamp/LDY/SEC...    ; 25
    SBC terrain_draw_table_2,Y  ; 4
    BCS (not taken)             ; 2
    EOR #$FF                    ; 2
    TAX                         ; 2
    INX                         ; 2
    LDA terrain_xpos_1_clipped  ; 3
    STA terrain_draw_table_2,Y  ; 5
    TAY                         ; 2
    JMP draw_terrain_xpos_1     ; 3
    JSR draw_terrain            ; (counted in draw_terrain cost)
                                ; ----
                                ; 50 + draw_terrain
```

### Clamping

- Clamped to 0 (wall left of the window): `BCS` not taken (2) + `LDA #0` (2) + `JMP` (3) = 7, against 8 for the unclamped `BCS`/`CMP`/`BCC`. **1 cycle faster.**
- Clamped to 72: `BCC` not taken (2) + `LDA #SCREEN_WIDTH_CHARS` (2). **1 cycle slower.**

The right wall is structurally identical: 37 / 56 / 50 cycles.

---

## Per-Scanline: Advance

### Within a character cell

```
    INC terrain_draw_wall_index ; 5
    INC terrain_draw_table_index; 5
    LDA terrain_draw_addr_LO    ; 3
    ADC #$02                    ; 2
    STA terrain_draw_addr_LO    ; 3
    AND #$07                    ; 2
    BEQ (not taken)             ; 2
    JMP landscape_draw_loop     ; 3
                                ; ----
                                ; 25 cycles
```

### Character row crossing

```
    ...INC/INC/ADC/STA/AND...   ; 20
    BEQ (taken)                 ; 3
    LDA terrain_draw_addr_LO    ; 3
    ADC #LO(SCREEN_CHAR_ROW_BYTES-8) ; 2
    STA terrain_draw_addr_LO    ; 3
    LDA terrain_draw_addr_HI    ; 3
    ADC #HI(SCREEN_CHAR_ROW_BYTES-8) ; 2
    STA terrain_draw_addr_HI    ; 3
    BMI (not taken)             ; 2
    JMP landscape_draw_loop     ; 3
                                ; ----
                                ; 44 cycles
```

83 normal advances + 27 crossings + the final crossing (BMI taken, RTS: 48) = 2,075 + 1,188 + 48 = **3,311 cycles per frame**, ~29.8 per scanline.

---

## draw_terrain

Called with Y = start column, X = column count, C = 0.

### First column (always executed)

```
    LDA mult_by_8_LO,Y          ; 4
    STA terrain_draw_ptr        ; 3
    LDA mult_by_8_HI,Y          ; 4
    ADC terrain_draw_addr_HI    ; 3
    STA terrain_draw_ptr+1      ; 3
    LDY terrain_draw_addr_LO    ; 3
    LDA #LANDSCAPE_COLOUR_BYTE  ; 2
    EOR (terrain_draw_ptr),Y    ; 5
    STA (terrain_draw_ptr),Y    ; 6
    DEX                         ; 2
    BEQ draw_terrain_return     ; 2 (3 if X was 1)
                                ; ----
                                ; 37 cycles
```

### Each further column (rolled loop)

```
    TYA                         ; 2
    ADC #$08                    ; 2
    TAY                         ; 2
    BCC (taken)                 ; 3
    LDA #LANDSCAPE_COLOUR_BYTE  ; 2
    EOR (terrain_draw_ptr),Y    ; 5
    STA (terrain_draw_ptr),Y    ; 6
    DEX                         ; 2
    BNE (taken)                 ; 3 (2 on the last column)
                                ; ----
                                ; 27 cycles
```

When Y overflows (every 32 columns, as Y steps by 8) the `BCC` falls through to `CLC; INC terrain_draw_ptr+1`: **+6 cycles**.

### Total, including JSR (6) and RTS (6)

```
cost(1) = 6 + 38 + 6                       = 50
cost(N) = 6 + 37 + 27*(N-1) - 1 + 6        = 21 + 27*N     (N >= 2)
```

plus 6 per Y overflow. In the SWRAM build the `CPX #9; BCS` test for the unrolled path adds 4 cycles to every rolled draw of 2-9 columns: `25 + 27*N`.

---

## Scenario Analysis

Original (non-SWRAM) `draw_terrain`. Per-scanline costs below exclude the advance, which is added as the 3,311 frame total; setup + JSR/RTS adds 53.

### Best case: static view

Both walls take path A on every scanline.

```
111 * (37 + 37)  =  8,214
advance          =  3,311
setup            =     53
Total            ≈ 11,580 cycles (19% of game frame)
```

### Typical: slow scrolling

Model: half the scanlines draw nothing; the other half move both walls by 3 columns (path B).

```
no draw:        74 cycles
draw both (3):  56 + cost(3) + 56 + cost(3) = 56 + 102 + 56 + 102 = 316

111 * (0.5*74 + 0.5*316) = 21,645
+ advance + setup        =  3,364
Total                    ≈ 25,000 cycles (42% of game frame)
```

### Fast scrolling

Same model with 8-column deltas: `56 + cost(8) + 56 + cost(8) = 586` per drawing scanline.

```
111 * (0.5*74 + 0.5*586) + 3,364 ≈ 40,000 cycles (67% of game frame)
```

### Full redraw: level start and respawn

`clear_screen_and_init` resets the caches to left = 0, right = 72, so the first `landscape_draw` must draw every solid column. With both walls mid-screen each draws ~36 columns (left via path B, right via path C):

```
56 + cost(36) + 6 + 50 + cost(36) + 6 = 56 + 999 + 50 + 999 = 2,104 per scanline
111 * 2,104 + 3,364 ≈ 237,000 cycles
```

About 4 game frames (~5.9 vsyncs). This draw happens in the level-start / respawn sequence (`thrust.6502:9328-9330`, `9603-9606`) before `reset_system_clock`, outside the tick loop, so it doesn't cause a gameplay frame drop.

An X wrap does **not** normally cause a full redraw: the wrap fix-up flips cached rows pinned at one edge so they draw nothing (see `landscape-drawing.md`, "X world wrapping"). The fix-up loop itself costs 25-32 cycles per entry, ~3,000 cycles. Only rows whose wall was on screen in the frame before the wrap redraw at near full width.

### Theoretical maximum

Both walls swing the full width (0 to 72 and 72 to 0) on every scanline:

```
56 + cost(72) + 12 + 50 + cost(72) + 12 = 4,060 per scanline
111 * 4,060 + 3,364 ≈ 454,000 cycles (~7.6 game frames)
```

This never happens in practice.

---

## Cost Summary

| Scenario | Original | `_UNROLL_TERRAIN` | % of 60,000 (original) |
|----------|----------|-------------------|------------------------|
| Static (no scroll) | ~11,600 | ~11,600 | 19% |
| Slow scroll (typical model) | ~25,000 | ~25,450 | 42% |
| Fast scroll (8-col model) | ~40,000 | ~40,450 | 67% |
| Full redraw (level start/respawn) | ~237,000 | ~195,000 | ~400% (outside tick loop) |
| Theoretical max | ~454,000 | ~355,000 | ~760% |

Even with no movement, the per-scanline bookkeeping costs ~11,500 cycles (74 per scanline for the two path-A walls plus ~30 advance). During scrolling the landscape is the largest single cost in the frame.

---

## Optimisation Opportunities

### 1. Unroll the draw_terrain inner loop: IMPLEMENTED (`_UNROLL_TERRAIN`)

`_UNROLL_TERRAIN = (_SWRAM_BUILD AND TRUE)` (`thrust.6502:34`) replaces the rolled `draw_terrain` with a version in the SWRAM block (`thrust.6502:13729`). The rolled loop spends 27 cycles per column: 13 on the EOR read-modify-write, 6 on `TYA; ADC #8; TAY`, 5 on `DEX; BNE`, 3 on `BCC`.

After the first column, if 9 or more columns remain (`CPX #9; BCS`, so draws of N >= 10 columns), `draw_terrain_unrolled`:

1. Folds `terrain_draw_addr_LO + 8` into `terrain_draw_ptr` and sets Y = 0, so Y runs 0-248 within a batch and the per-column carry check disappears.
2. Looks up the entry point in `width_to_plot_LO/HI` (73 entries, indexed by remaining columns) and patches a `JMP` into `terrain_unrolled_plot_one_page`, a 32-column unrolled block (`UNROLLED_PLOT_SIZE` = 10 bytes per column). Entering *k* columns from the end draws *k* columns.
3. After the block, subtracts 32 from X; if columns remain, increments the pointer high byte and runs another batch.

Per column:
```
    LDA #LANDSCAPE_COLOUR_BYTE  ; 2
    EOR (terrain_draw_ptr),Y    ; 5
    STA (terrain_draw_ptr),Y    ; 6
    TYA                         ; 2
    ADC #$08                    ; 2
    TAY                         ; 2
                                ; ----
                                ; 19 cycles (8 fewer than rolled)
```

Fixed cost for an N-column draw (one batch, N <= 32), including JSR/RTS: 6 + 37 (first column) + 5 (`CPX`/`BCS` taken) + 20 (pointer rebase) + 16 (table lookup and patch) + 3 + 3 (`JMP`s) + 10 (`SEC`..`BCS`) + 6 (RTS) = **106 + 19*(N-1)**. Each further batch adds 38. The pointer rebase costs 6 more when `ptr + addr_LO + 8` carries into the high byte, which depends on alignment (roughly half the time).

| N (total cols) | Rolled, original (21 + 27N) | Rolled, SWRAM (25 + 27N) | Unrolled (106 + 19(N-1)) |
|---|---|---|---|
| 8 | 237 | 241 | 239 |
| 9 | 264 | 268 | 258 |
| 10 | 291 | 295 | 277 |
| 16 | 453 | 457 | 391 |
| 36 | 993 (+6) | — | 809 |

Breakeven is about N = 8-9 once the rebase carry is averaged in, so the N >= 10 threshold is about right. Typical scrolling draws are 1-8 columns and take the rolled path, where the SWRAM build is 4 cycles per draw slower (~450 cycles per frame in the typical model). The gain is on wide draws: ~190 cycles per 36-column wall draw, ~42,000 cycles on a full redraw.

### 2. Self-modified absolute addressing instead of indirect: NOT VIABLE

Replacing `EOR (ptr),Y / STA (ptr),Y` (5 + 6) with self-modified `EOR abs,Y / STA abs,Y` (4 + 5) saves 2 cycles per column.

**With unrolling:** all 32 EOR and 32 STA operands need the base address patched, 128 operand-byte stores, ~518 cycles of setup. Breakeven would be ~260 columns against a 72-column maximum.

**As a rolled loop:** only 2 instructions to patch (~22 cycles), giving 25 cycles per column. Y overflow then needs both operands re-patched (+20, against +6 for the ZP pointer), and the `DEX`/`BNE` overhead stays.

| N (total cols) | Rolled (48 + 27(N-1)) | Self-mod loop (~70 + 25(N-1)) | Unrolled (106 + 19(N-1)) |
|---|---|---|---|
| 8 | 237 | 245 | 239 |
| 13 | 372 | 370 | 334 |
| 16 | 453 | 445 | 391 |
| 36 | 993 | 945 | 809 |

The self-mod loop only beats rolled from N = 13 and the unrolled path beats both from N ≈ 9.

### 3. Fully self-modified unrolled sequence: NOT VIABLE

`EOR col_N_addr / STA col_N_addr` with no Y register is 10 cycles per column but needs up to 72 absolute addresses patched per call (~8 cycles each, ~576 cycles). It would only win on draws over ~30 columns, which happen only on full redraws.

### 4. Skip fully off-screen scanlines early: NOT WORTHWHILE

When both walls are clamped to the same edge and the cache already agrees, the delta is 0 but the scanline still costs ~104 cycles. A safe skip test must read both walls and both cache entries:

```
Detection:      LDY + LDA wall + SBC + BCS +
                LDA wall + SBC + BCS +
                LDY + LDA tbl + ORA tbl + BNE  = ~35c
State advance:  INC + INC + ADC addr_LO        = ~25c
Per skipped scanline                           = ~60c (saves ~44c)
```

On visible scanlines the test adds ~12 cycles before bailing out. With 20 skippable scanlines: 20 x 44 = 880 saved, 91 x 12 = 1,092 added, net loss. Breakeven needs ~24 skippable scanlines out of 111. Scanning contiguous runs from the top and bottom avoids the per-line overhead but saves only ~1,000-2,000 cycles in favourable geometry.

### 5. Amortise the full redraw: NOT NEEDED

The only full redraw is at level start and respawn, outside the tick loop, so spreading it across frames would gain nothing in play. For the X wrap, adjusting the cache by the wrap delta is what the existing fix-up already does where it helps (rows pinned at one edge). The 73-column wrap delta is wider than the 72-column screen, so the views before and after don't overlap and rows with a visible wall can't be preserved.

### 6. Batch the wall reads: NOT VIABLE

The second `LDY terrain_draw_wall_index` (`thrust.6502:1015`) is needed: Y is reloaded with `terrain_draw_table_index` at `thrust.6502:982` and used as the start column on the draw paths. Pre-reading the right wall at the top of the loop costs `LDA terrain_right_wall,Y` + `STA temp` (7) and saves `LDY` (3) plus 1 cycle on the later load: 3 cycles slower.

### 7. Move the draw tables to zero page: NOT WORTHWHILE

Tables 2 and 4 are 111 bytes each, too large for zero page. There is also little to gain: `SBC`/`LDA` have no `zp,Y` mode, and `zp,X` reads take 4 cycles, the same as the current `abs,Y` reads. Only the store (`STA zp,X` 4 vs `STA abs,Y` 5) saves a cycle, once per wall draw, and X is already used for the column count.

### Summary

| Optimisation | Effect | Status |
|---|---|---|
| Unrolled inner loop | ~42,000 on a full redraw; ~-450/frame typical (threshold test) | **Implemented** (`_UNROLL_TERRAIN`) |
| Self-modified absolute EOR | setup exceeds savings | Not viable |
| Fully self-modified, no Y | ~576c setup per call | Not viable |
| Skip off-screen scanlines | detection overhead exceeds savings | Not worthwhile |
| Amortise full redraw | redraw is outside the tick loop | Not needed |
| Batched wall reads | 3c slower | Not viable |
| Draw tables in ZP | ~1c per wall draw | Not worthwhile |

The remaining cost is dominated by the per-scanline bookkeeping in `landscape_draw` (~11,500 cycles with nothing to draw), which is inherent to the delta-tracking design.
