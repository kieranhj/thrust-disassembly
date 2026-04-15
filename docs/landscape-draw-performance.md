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

### 1. Unroll the draw_terrain inner loop — IMPLEMENTED (`_UNROLL_TERRAIN`)

The inner loop spends 27 cycles per column: 11 for the EOR read-modify-write, 6 for Y advancement (TYA; ADC #8; TAY), 5 for DEX/BNE, and 5 for BCC. Unrolling eliminates the loop overhead.

**Implementation:** The `_UNROLL_TERRAIN` flag (enabled when `_SWRAM_BUILD` is true) adds an unrolled path in SWRAM. The classic "jump into unrolled sequence" pattern processes up to 32 columns per batch (matching the 256-byte Y register range), entered via a jump table indexed by column count. Falls back to the original rolled loop for small draws.

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

The unrolled path avoids Y-overflow handling entirely by design: Y is reset to 0 at the batch start and runs exactly 32 iterations (Y: 0→248), so the carry-handling branch (BCC/CLC/INC) is eliminated within the batch.

**Threshold analysis:** The current threshold is `CPX #16` (uses unrolled path for 16+ remaining columns). The unrolled path has ~58 cycles of setup+return overhead. Breakeven vs the rolled loop:

| X (remaining cols) | Rolled (47 + 27*X) | Unrolled (101 + 20*X) | Winner |
|---|---|---|---|
| 8 | 263 | 261 | Unrolled by 2 |
| 9 | 290 | 281 | Unrolled by 9 |
| 16 | 479 | 421 | Unrolled by 58 |

Breakeven is at ~9 remaining columns. The `CPX #16` threshold is conservative but not wildly so — lowering to `CPX #9` would help medium-width draws. However, during typical scrolling most draw calls are 1–8 columns (small wall deltas), so the unrolled path primarily benefits the large-draw case (X-wrap, level init).

**Actual savings:** ~7 cycles per column for draws of 16+ columns. For X-wrap (~111 scanlines × ~36 columns): **~28,000 cycles** (~0.7 frames faster).

### ~~2. Use self-modifying absolute addressing instead of indirect~~ — NOT VIABLE

Replace `EOR (terrain_draw_ptr),Y / STA (terrain_draw_ptr),Y` (5+6 = 11 cycles) with self-modified `EOR addr,Y / STA addr,Y` (4+5 = 9 cycles), saving 2 cycles per column.

**Analysis showed this doesn't combine well with either approach:**

**With unrolling:** All 32 EOR and 32 STA instructions need the same base address patched into their operand bytes. That's 128 STA instructions (64 address pairs × 2 bytes) = **~518 cycles of setup**. Breakeven: 518 / 3 = 173 columns. Maximum draw is 72 columns. **Never pays off.**

**Without unrolling (self-mod loop):** Patches only 2 instructions (22 cycles setup), giving 25 cycles/column vs the rolled loop's 27 cycles/column. However, Y-overflow handling costs more for self-mod (must re-patch both instruction operands: +20 cycles) vs the rolled loop (single ZP pointer INC: +9 cycles). The self-mod loop also re-introduces the loop overhead (DEX/BNE) that unrolling eliminates. Full comparison:

| X (total cols) | Rolled (47 + 27*(X-1)) | Self-mod loop (70 + 25*(X-1)) | Unrolled (101 + 20*(X-1)) |
|---|---|---|---|
| 8 | 236 | 245 | 241 |
| 13 | 371 | 370 | 341 |
| 16 | 452 | 445 | 401 |
| 36 | 992 | 945 | 801 |

The self-mod loop occupies an awkward middle ground — it barely beats rolled (only for X≥13), and the unrolled path beats both from X≈9 onward. Not worth the added complexity.

### ~~3. Combined unrolled + self-modified inner loop~~ — NOT VIABLE

Fully self-modified unrolled (no Y register, `EOR col_N_addr; STA col_N_addr` at 10 cycles/column) requires writing 72 different absolute addresses into the unrolled sequence every call. At ~8 cycles per address pair × 72 = ~576 cycles of setup. Only wins for draws >30 columns, which are rare outside X-wrap events. The setup cost for 32-column batches (518 cycles to patch 64 instruction operands) dwarfs the 2-3 cycle/column saving. **Not recommended.**

### ~~4. Skip fully off-screen scanlines early~~ — MARGINAL, NOT RECOMMENDED

When both walls are clamped to 0 or both to 72 (off-screen), the delta against the draw table is 0. The current code still performs the full clamp-compare-skip logic at ~102 cycles per scanline.

**Analysis showed the detection overhead offsets the savings.** The cheapest safe skip detection requires reading both wall values AND both draw table entries (to confirm the tables already reflect the off-screen state — otherwise old terrain wouldn't be erased):

```
Detection:  LDY + LDA wall + SBC + BCS +
            LDA wall + SBC + BCS +
            LDY + LDA tbl + ORA tbl + BNE  = ~35c
State advance: INC + INC + ADC addr_LO     = ~25c
Total per skipped scanline:                 = ~60c (vs ~102c normal = 42c saved)
```

But the detection cost on VISIBLE scanlines (where the first BCS bails out early) is ~12c of overhead added to every iteration. For a level with 20 off-screen scanlines:

```
Savings:  20 × 42c    = ~840c
Overhead: 91 × 12c    = ~1,092c
Net:                   = -252c (WORSE)
```

Breakeven requires >26 off-screen scanlines out of 111. A contiguous pre-scan from top/bottom avoids the per-visible-scanline overhead but only catches edge regions and saves ~1,000-2,000 cycles in favourable level geometry (<5% of landscape cost). **Not worth the code complexity.**

### ~~5. Amortise the X-wrap redraw~~ — NOT VIABLE AS DESCRIBED

The X-wrap full redraw (~237,000 cycles) is by far the most expensive event.

~~**Option B:** during X-wrap, adjust the draw table entries by the wrap delta ($49 or $B7) instead of resetting to 0/72. This converts the full-screen repaint into a delta update proportional to the actual wall movement at the wrap seam.~~

**Analysis showed Option B is fundamentally flawed.** The wrap delta is `SCREEN_WIDTH_CHARS + 1` = 73 columns. The screen is 72 columns wide. After a wrap, the old and new viewports have **zero overlap** — this is by design, to prevent the player seeing the world seam. Adjusting table entries by ±73 clamps all values (0–72) to the same extreme (0 or SCREEN_WIDTH_CHARS), which is equivalent to a full reset. The delta between adjusted tables and new wall positions is still the entire visible terrain width. **No savings possible.**

**Option A** (spread redraw across 4-6 frames) remains theoretically viable but requires significant restructuring of `landscape_draw` to track partial-redraw state across frames, and introduces visible "painting" artefacts. Given that X-wraps are infrequent (player must traverse the full world width), the 6-frame stall may be acceptable.

### ~~6. Reduce per-scanline overhead with batched wall reads~~ — NOT VIABLE

The second `LDY terrain_draw_wall_index` (line 917) appears redundant but is necessary: Y is overwritten to `terrain_draw_table_index` during left wall processing (line 887) and further clobbered as the start column in draw paths. The reload is required.

Pre-reading both wall values at the top of the loop requires stashing the right wall in a temp variable: `LDA terrain_right_wall,Y` (4c) + `STA temp` (3c) = 7c of extra cost, saving only 4c later (skip LDY 3c + LDA ZP 3c vs LDA abs,Y 4c). **Net: 3 cycles slower.** The original code is already optimal.

### 7. Move draw tables to zero page

The draw tables (`terrain_draw_table_2` at $0300, `terrain_draw_table_4` at $036F) are accessed with absolute indexed addressing (4 cycles for read, 5 for write). Moving them to zero page would save 1 cycle per access. With 4 draw table accesses per scanline (2 reads + 2 writes), that's 4 cycles per scanline = **~444 cycles/frame**.

However, zero page space is tight — the tables are 94 and 145 bytes respectively, far too large. A compromise: keep a small "active window" of draw table entries in zero page and swap them as the scanline advance.

### Summary of potential savings

| Optimisation | Cycles saved (typical frame) | Status |
|---|---|---|
| Unrolled inner loop | ~1,320 (large draws only) | **Implemented** (`_UNROLL_TERRAIN`) |
| Self-modified absolute EOR | — | ~~Not viable~~ (setup cost exceeds savings) |
| Combined unroll + self-mod | — | ~~Not viable~~ (518c setup for 3c/col saving) |
| Fully self-modified (no Y reg) | — | ~~Not viable~~ (576c+ setup per call) |
| Skip off-screen scanlines | — | ~~Not viable~~ (detection overhead exceeds savings) |
| Amortised X-wrap (Option B) | — | ~~Not viable~~ (wrap delta > screen width, no overlap) |
| Amortised X-wrap (Option A) | ~212,000 (event) | Viable but complex, infrequent event |
| Batched wall reads | — | ~~Not viable~~ (pre-read costs more than reload) |
| Draw tables to ZP (partial) | ~444 | Viable, medium complexity |

The unrolled inner loop is implemented and provides the bulk of achievable savings for the `draw_terrain` hot path. The remaining viable optimisations (batched wall reads, ZP draw tables) offer modest per-frame savings (~333-444 cycles each). The landscape draw cost is dominated by the per-scanline overhead in `landscape_draw` itself (~74 cycles per wall × 111 scanlines = ~8,200 cycles even with zero column draws), which is inherent to the delta-tracking architecture.
