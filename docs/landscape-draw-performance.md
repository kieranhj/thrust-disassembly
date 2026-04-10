# Landscape Draw Performance Analysis

## Overview

`landscape_draw` (line 808) is the most cycle-intensive routine called every frame. It iterates over all visible half-resolution scanlines, computing the delta between the current and previous frame's wall positions, and EOR-drawing only the changed columns. This analysis counts 6502 cycles through every code path to estimate best-case, typical, and worst-case frame costs.

**Target platform:** BBC Micro Model B, 2 MHz 6502A. At 50 Hz, one frame = 40,000 cycles (39,936 exact). The game uses MODE 5 (160x256, 4 colours, 20KB screen memory).

---

## Scanline Count

The loop draws at half vertical resolution (every other pixel row), starting at pixel row 2 of the first gameplay character row. It terminates when the screen address high byte goes negative (`BMI` at line 952), i.e. the address reaches $8000 (end of screen memory).

- Screen memory: `$3C80` to `$7FFF` = 17,280 bytes
- Character row size: 72 columns x 8 bytes = 576 ($0240) bytes
- Total character rows: 17,280 / 576 = 30
- Status bar: 2 character rows
- Gameplay character rows: 28
- Half-res scanlines per character row: 4
- First character row starts at pixel row 2 (loses 1 scanline)

**Total: 111 half-resolution scanlines per frame** (28 x 4 - 1).

The `$49` (73) constant at line 813 is the wall array index offset — it determines where in the circular buffer the renderer starts reading wall data. It is not the scanline count.

---

## Code Structure

The routine has three phases per scanline:

1. **Left wall processing** (lines 831-879): read wall position, convert to screen X, clamp, compute delta against draw table, call `draw_terrain` if delta is non-zero
2. **Right wall processing** (lines 881-930): identical logic for the right wall
3. **Index advancement** (lines 932-954): increment wall/table indices, advance screen address, handle character row boundary crossing

The inner drawing is done by `draw_terrain` (line 1233), called 0, 1, or 2 times per scanline.

---

## Setup (one-time per frame)

```
landscape_draw:
    LDA #$00                    ; 2 cycles
    STA terrain_draw_table_index ; 3 cycles (zero page)
    LDA #$49                    ; 2
    CLC                         ; 2
    ADC terrain_window_y_index  ; 3
    STA terrain_draw_wall_index ; 3
    LDA #$02                    ; 2
    STA terrain_draw_addr_LO    ; 3
    LDA #HI(SCREEN_START_ADDR)  ; 2
    STA terrain_draw_addr_HI    ; 3
    LDX window_xpos_INT         ; 3
    DEX                         ; 2
    STX window_xpos_2           ; 4 (absolute, self-mod)
    STX window_xpos_1           ; 4 (absolute, self-mod)
    CLC                         ; 2
                                ; ----
                                ; 40 cycles total
```

The `DEX` / `STX` stores `window_xpos - 1` as the SBC immediate operand. Combined with the initial `CLC` (carry=0), the SBC in the loop computes `wall_pos - (window_xpos - 1) - 1 = wall_pos - window_xpos`, giving the correct world-to-screen conversion.

---

## Per-Scanline: Left Wall Processing

### Path A: No change (delta = 0)

The fastest path — the wall hasn't moved since last frame.

```
    LDY terrain_draw_wall_index ; 3
    LDA terrain_left_wall,Y     ; 4 (absolute indexed)
    SBC #imm                    ; 2 (self-modified)
    BCS (taken)                 ; 3
    CMP #SCREEN_WIDTH_CHARS     ; 2
    BCC (taken)                 ; 3
    STA terrain_xpos_1_clipped  ; 3 (zero page)
    LDY terrain_draw_table_index; 3
    SEC                         ; 2
    SBC terrain_draw_table_2,Y  ; 4 (absolute indexed)
    BCS (taken)                 ; 3
    CLC                         ; 2
    BEQ (taken)                 ; 3 (delta=0, skip draw)
                                ; ----
                                ; 37 cycles
```

### Path B: Wall moved right (new > old), draw required

```
    LDY terrain_draw_wall_index ; 3
    LDA terrain_left_wall,Y     ; 4
    SBC #imm                    ; 2
    BCS (taken)                 ; 3
    CMP #SCREEN_WIDTH_CHARS     ; 2
    BCC (taken)                 ; 3
    STA terrain_xpos_1_clipped  ; 3
    LDY terrain_draw_table_index; 3
    SEC                         ; 2
    SBC terrain_draw_table_2,Y  ; 4
    BCS (taken)                 ; 3
    CLC                         ; 2
    BEQ (not taken)             ; 2
    TAX                         ; 2
    LDA terrain_draw_table_2,Y  ; 4
    STA terrain_draw_start_x    ; 3
    LDA terrain_xpos_1_clipped  ; 3
    STA terrain_draw_table_2,Y  ; 5
    LDY terrain_draw_start_x    ; 3
    JSR draw_terrain            ; 6 + draw_terrain cycles
                                ; ----
                                ; 59 + draw_terrain
```

### Path C: Wall moved left (new < old), draw required

```
    ...same read/clamp...       ; 24
    SBC terrain_draw_table_2,Y  ; 4
    BCS (not taken)             ; 2
    EOR #$FF                    ; 2
    TAX                         ; 2
    INX                         ; 2
    LDA terrain_xpos_1_clipped  ; 3
    STA terrain_draw_table_2,Y  ; 5
    TAY                         ; 2
    JMP draw_terrain_xpos_1     ; 3
    JSR draw_terrain            ; 6 + draw_terrain cycles
                                ; ----
                                ; 55 + draw_terrain
```

### Path D: Clamped to 0 (wall off-screen left)

Add 5 cycles for the `LDA #$00; JMP` clamp path vs the normal BCS/BCC path.

### Path E: Clamped to 72 (wall off-screen right)

Add 2 cycles for the `LDA #SCREEN_WIDTH_CHARS` load.

Right wall processing is structurally identical — same cycle counts.

---

## Per-Scanline: Index Advancement

### Normal case (within character cell)

```
    INC terrain_draw_wall_index ; 5 (zero page)
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

### Character row crossing (every 4th scanline)

When `terrain_draw_addr_LO AND 7 == 0`, the screen address crosses into the next character row. This happens every 4 iterations (pixel rows advance by 2, character cells are 8 bytes).

```
    ...same INC/ADC...          ; 20
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

**Weighted average:** 3 normal (25) + 1 crossing (44) per 4 scanlines = (75 + 44) / 4 = **29.75 cycles**

---

## draw_terrain Inner Loop

Called with Y = start column, X = column count.

### First column (always executed)

```
    LDA mult_by_8_LO,Y         ; 4 (absolute indexed)
    STA terrain_draw_ptr        ; 3
    LDA mult_by_8_HI,Y         ; 4
    ADC terrain_draw_addr_HI    ; 3 (zero page)
    STA terrain_draw_ptr+1      ; 3
    LDY terrain_draw_addr_LO    ; 3
    LDA #$F0                    ; 2
    EOR (terrain_draw_ptr),Y    ; 5 (indirect indexed)
    STA (terrain_draw_ptr),Y    ; 6
    DEX                         ; 2
    BEQ draw_terrain_return     ; 2/3
                                ; ----
                                ; 37 cycles (if X=1, +1 for taken branch, +6 RTS = 44 total)
```

### Each additional column

```
    TYA                         ; 2
    ADC #$08                    ; 2
    TAY                         ; 2
    BCC (taken, usually)        ; 3 (or 2+2+2 if page cross)
    LDA #$F0                    ; 2
    EOR (terrain_draw_ptr),Y    ; 5
    STA (terrain_draw_ptr),Y    ; 6
    DEX                         ; 2
    BNE (taken)                 ; 3
                                ; ----
                                ; 27 cycles per column (no page cross)
                                ; 31 cycles per column (page cross)
```

Page crosses occur when Y + 8 overflows a page boundary. Since Y starts at `column * 8` and the screen is 72 columns (576 bytes = 2.25 pages), a page cross happens roughly every 32 columns.

### JSR/RTS overhead

```
    JSR draw_terrain            ; 6
    ...body...
    RTS                         ; 6
                                ; ----
                                ; 12 cycles overhead
```

### Total draw_terrain cost for N columns

```
cost(N) = 12 (JSR/RTS) + 37 (first column) + 27 * (N-1) (remaining)
        = 49 + 27 * (N-1)
        = 22 + 27 * N
```

Plus ~4 extra cycles per page crossing (~1 per 32 columns drawn).

---

## Scenario Analysis

### Best case: static view (no scrolling, no wall movement)

Every scanline takes the "no change" path for both walls.

```
Per scanline: 37 (left, no draw) + 37 (right, no draw) + 30 (advance, weighted avg)
            = 104 cycles

111 scanlines: 111 * 104 = 11,544 cycles
Setup: 40 cycles
Total: ~11,580 cycles (29% of frame)
```

### Typical case: slow scrolling

When scrolling, each scanline has one new row entering and one old row leaving. On average, each wall moves by 0-2 columns per scanline. Assume ~50% of scanlines need drawing, average 3 columns per draw call.

```
Per scanline (no draw): 37 + 37 + 30 = 104 cycles
Per scanline (draw both walls, 3 cols each):
    59 + cost(3) + 59 + cost(3) + 30
    = 59 + 103 + 59 + 103 + 30
    = 354 cycles

50% no draw, 50% draw:
    111 * (0.5 * 104 + 0.5 * 354) = 111 * 229 = 25,419 cycles

Total: ~25,460 cycles (64% of frame)
```

### Worst case: level initialisation or X-wrap

After level start or an X-wrap, the draw tables are reset (left=0, right=72). Every scanline must draw the full delta from the initial state to the actual wall positions. In the worst case (walls near the middle of the screen), each wall draws ~36 columns.

```
Per scanline (draw both walls, 36 cols each):
    59 + cost(36) + 59 + cost(36) + 30
    = 59 + 994 + 59 + 994 + 30
    = 2,136 cycles

111 scanlines: 111 * 2,136 = 237,096 cycles
```

This is **~5.9 frames** at 2 MHz — the landscape redraw after an X-wrap or level start will visibly take several frames to complete. However, this only happens once per wrap event; subsequent frames return to the delta-only cost.

### Absolute worst case: every column every scanline

If both walls move from column 0 to column 72 (or vice versa) simultaneously on every scanline:

```
Per scanline: 59 + cost(72) + 59 + cost(72) + 30
            = 59 + 1966 + 59 + 1966 + 30
            = 4,080 cycles

111 scanlines: 111 * 4,080 = 452,880 cycles (~11.3 frames)
```

This is a theoretical maximum that never occurs in practice.

---

## Cost Summary

| Scenario | Cycles | % of frame (40,000) | Frames |
|----------|--------|---------------------|--------|
| Static (no scroll) | ~11,580 | 29% | 0.29 |
| Slow scroll (typical) | ~25,460 | 64% | 0.64 |
| Fast scroll (8+ cols delta) | ~42,000 | 105% | 1.05 |
| X-wrap / init (full redraw) | ~237,000 | 593% | 5.9 |
| Theoretical max (all cols) | ~453,000 | 1133% | 11.3 |

The landscape draw alone consumes roughly **two thirds of the frame** during typical scrolling. This is the primary bottleneck in the rendering pipeline and the most impactful target for optimisation.

---

## Optimisation Opportunities

### 1. Unroll the draw_terrain inner loop

The inner loop spends 27 cycles per column: 11 for the EOR read-modify-write, 6 for Y advancement (TYA; ADC #8; TAY), 5 for DEX/BNE, and 5 for BCC. Unrolling eliminates the loop overhead.

**Fully unrolled (self-modified column count):** replace the loop with a straight-line sequence of `LDA #$F0; EOR addr,Y; STA addr,Y; INY8` blocks, jumping into the sequence at the right offset for the column count. This is the classic "unrolled loop entered via jump table" pattern.

Per column (unrolled, indirect addressing):
```
    LDA #$F0                    ; 2
    EOR (terrain_draw_ptr),Y    ; 5
    STA (terrain_draw_ptr),Y    ; 6
    TYA                         ; 2
    ADC #$08                    ; 2
    TAY                         ; 2
                                ; ----
                                ; 19 cycles (down from 27, saves 8 per column)
```

**Savings:** 8 cycles per column. For typical scrolling (~55 scanlines drawing ~3 columns each = 165 columns): **~1,320 cycles/frame**.

For the X-wrap case (~111 scanlines x ~36 columns = 3,996 columns): **~32,000 cycles** — nearly a full frame faster.

### 2. Use self-modifying absolute addressing instead of indirect

Replace `EOR (terrain_draw_ptr),Y / STA (terrain_draw_ptr),Y` (5+6 = 11 cycles) with self-modified `EOR addr,Y / STA addr,Y` (4+5 = 9 cycles). The terrain_draw_ptr setup already computes the address — just write it into the instruction operands instead.

```
    LDA #$F0                    ; 2
    EOR addr,Y                  ; 4 (self-modified absolute)
    STA addr,Y                  ; 5
                                ; ----
                                ; 11 cycles (down from 13 for the EOR/STA pair)
```

**Savings:** 2 cycles per column drawn. Combinable with unrolling.

### 3. Combined unrolled + self-modified inner loop

With both optimisations, the per-column cost becomes:

```
    LDA #$F0                    ; 2
    EOR addr,Y                  ; 4
    STA addr,Y                  ; 5
    ; Y advancement inlined     ; 6 (TYA; ADC #8; TAY)
                                ; ----
                                ; 17 cycles (down from 27, saves 10 per column)
```

Can also eliminate Y advancement by precomputing the screen offset per column and using a fixed Y=0 with self-modified absolute addresses per column. This requires more self-modifying code but removes the Y register manipulation entirely:

```
    LDA #$F0                    ; 2
    EOR col_N_addr              ; 4 (self-modified)
    STA col_N_addr              ; 4
                                ; ----
                                ; 10 cycles per column (down from 27, saves 17)
```

**Savings (vs current):** 17 cycles per column. For typical frame: **~2,800 cycles**. For X-wrap: **~68,000 cycles** (1.7 frames faster).

The downside is significant code size: 72 x ~10 bytes = ~720 bytes for the fully unrolled sequence, plus setup code to write the screen addresses. But this would bring the X-wrap case from ~5.9 frames down to ~4.2 frames.

### 4. Skip fully off-screen scanlines early

When both walls are clamped to 0 or both to 72 (entire scanline off-screen), the delta against the draw table will always be 0. The current code still performs the full clamp-compare-skip logic (37 cycles per wall).

An early-out: before entering the main loop, precompute the range of visible scanlines (those where at least one wall is on-screen). Skip directly from the last off-screen scanline to the first visible one by advancing the address and indices in bulk.

**Savings:** up to ~74 cycles per off-screen scanline (both walls). In levels with a large sky region or deep underground, this could save thousands of cycles.

### 5. Amortise the X-wrap redraw across frames

The X-wrap full redraw (~237,000 cycles) is by far the most expensive event. Instead of redrawing the entire screen in one frame:

- **Option A:** spread the redraw across 4-6 frames, redrawing ~20-28 scanlines per frame. The player would see the terrain "painting" downward, but each frame stays within budget.

- **Option B:** during X-wrap, adjust the draw table entries by the wrap delta ($49 or $B7) instead of resetting to 0/72. This converts the full-screen repaint into a delta update proportional to the actual wall movement at the wrap seam, which is typically just a few columns.

Option B is the more elegant solution and could reduce the X-wrap cost from ~237,000 cycles to the typical scrolling cost (~25,000 cycles).

### 6. Reduce per-scanline overhead with batched wall reads

The current code reads `terrain_left_wall,Y` and `terrain_right_wall,Y` separately with full clamp logic for each. Since both arrays are in pages $04 and $05, they could be read with a single Y index load. A restructured loop could:

1. Load Y = wall index once
2. Read both wall values (LDA $0400,Y / LDA $0500,Y)
3. Process both walls before advancing

This saves the second `LDY terrain_draw_wall_index` (3 cycles per scanline). Small but it's free.

### 7. Move draw tables to zero page

The draw tables (`terrain_draw_table_2` at $0300, `terrain_draw_table_4` at $036F) are accessed with absolute indexed addressing (4 cycles for read, 5 for write). Moving them to zero page would save 1 cycle per access. With 4 draw table accesses per scanline (2 reads + 2 writes), that's 4 cycles per scanline = **~444 cycles/frame**.

However, zero page space is tight — the tables are 94 and 145 bytes respectively, far too large. A compromise: keep a small "active window" of draw table entries in zero page and swap them as the scanline advances.

### Summary of potential savings

| Optimisation | Cycles saved (typical frame) | Complexity |
|---|---|---|
| Unrolled inner loop | ~1,320 | Medium |
| Self-modified absolute EOR | ~660 | Low |
| Combined unroll + self-mod | ~2,800 | High |
| Fully self-modified (no Y reg) | ~4,600+ | High |
| Skip off-screen scanlines | ~1,000-5,000 | Low |
| Amortised X-wrap | ~212,000 (event) | Medium |
| Batched wall reads | ~333 | Low |
| Draw tables to ZP (partial) | ~444 | Medium |

The highest-impact change is amortising the X-wrap. For steady-state performance, the combined unroll + self-modified inner loop offers the best return, potentially bringing typical scrolling from 64% to ~50% of the frame budget.
