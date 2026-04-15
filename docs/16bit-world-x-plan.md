# Plan: 16-Bit World X Coordinates

## Context

The world X coordinate system is currently 8-bit (0–255), wrapping at ~$B8–$DC. The visible viewport is 72 character columns, so the playable world is only ~184 columns wide — roughly 2.5 screens. Extending to 16-bit would allow worlds up to 65,535 columns wide, enabling the Metroidvania-style interconnected maps described in ideas.md.

This is a **deep structural change** touching nearly every system in the game. This document catalogues what must change, quantifies the costs, and identifies the riskiest areas.

---

## Scope of Change

### Systems Affected

| System | Severity | Files | Notes |
|--------|----------|-------|-------|
| Zero page variables | Medium | thrust.6502 | ~10 new ZP bytes needed |
| World X wrap logic | **Major rewrite** | thrust.6502:2894–2965 | 16-bit comparisons + additions for all entities |
| Terrain wall arrays | **Major rewrite** | thrust.6502:$0400/$0500 | Must become 16-bit (512 bytes → 1024 bytes, or rearchitect) |
| Terrain RLE decoder | **Major rewrite** | thrust.6502:1085–1259 | Accumulator and increments become 16-bit |
| landscape_draw | **Major rewrite** | thrust.6502:843–993 | World-to-screen subtraction, clamping, self-mod all become 16-bit |
| draw_terrain (unrolled) | Medium | thrust.6502:10871–10987 | Already screen-relative; no change to inner loop |
| Object visibility/rendering | Major | thrust.6502:1921–2056 | 16-bit world X subtract, level data format change |
| Object collision detection | Major | thrust.6502:1597–1633 | 16-bit subtractions |
| Particle system | Major | thrust.6502:$0600+ | xpos_INT needs _INT_HI companion (32 extra bytes) |
| Particle-terrain collision | Major | thrust.6502:5977–5982 | Terrain wall arrays indexed differently |
| Ship position calc | Medium | thrust.6502:4263–4296 | midpoint→ship already 16-bit-ish via fractional; needs _INT_HI carry |
| Pod position calc | Medium | thrust.6502:5344–5364, 9054–9086 | Same pattern as ship |
| Midpoint force integration | Medium | thrust.6502:5534–5543 | 3-byte add becomes 4-byte add |
| Player position calc | Medium | thrust.6502:5595–5676 | velocity calc, old_pos storage need _INT_HI |
| Distance calculations | Medium | thrust.6502:7100–7170 | ship-to-pod distance, BVS overflow check breaks |
| Tether line drawing | Low | thrust.6502:7710–7738 | Uses screen-relative coords; unaffected |
| Level data format | Major | level_data.6502, level_editor.py | New `obj_pos_X_EXT` arrays (following Y pattern) |
| Gun firing | Low | thrust.6502:1829–1839 | Object X → particle X init, adds _INT_HI |
| Player gun firing | Low | thrust.6502:6929–6939 | player_xpos → particle, adds _INT_HI |

---

## Detailed Analysis by System

### 1. Zero Page: ~10 New Bytes Required

New `_INT_HI` / `_EXT` variables needed (following existing Y-coordinate pattern):

| New Variable | Purpose | ZP Addr |
|-------------|---------|---------|
| `window_xpos_EXT` | Viewport world X high byte | Need to allocate |
| `midpoint_xpos_INT_HI` | Midpoint world X high byte | Need to allocate |
| `player_xpos_INT_HI` | Ship world X high byte | Need to allocate |
| `old_player_xpos_INT_HI` | Previous ship X high byte | Need to allocate |
| `pod_xpos_INT_HI` | Pod world X high byte | Need to allocate |
| `nearest_obj_xpos_INT_HI` | Object X high byte | Need to allocate |
| `force_vectorx_INT_HI` | X force sign extension | Need to allocate |
| `player_velocityx_INT_HI` | X velocity high byte | Need to allocate |
| `window_deltax_INT_HI` | Wrap delta high byte (temp) | Can use $0080+ range |
| `current_obj_xpos_EXT` | Current object X high byte (temp) | Can use $0080+ range |

**ZP availability:** $00A8–$00FB = 84 bytes free. Plenty of room. The persistent variables ($0000–$00A7) can absorb ~8 new bytes; the rest go in the temp range ($0080+).

### 2. Terrain Wall Arrays — The Hardest Problem

**Current:** `terrain_left_wall` at $0400 (256 bytes), `terrain_right_wall` at $0500 (256 bytes). Each entry is an 8-bit world X. Indexed by Y position (circular buffer).

**Problem:** With 16-bit world X, each entry needs 2 bytes. Options:

#### Option A: Split LO/HI arrays (recommended)
- `terrain_left_wall_LO` at $0400 (256 bytes) — low byte, as now
- `terrain_left_wall_HI` at $0500 (256 bytes) — new high byte
- `terrain_right_wall_LO` at $0300 (256 bytes) — move from $0500
- `terrain_right_wall_HI` at another 256-byte page

This needs **512 extra bytes** of page-aligned RAM. The existing memory map has:
- $0300–$03FF: terrain draw tables 1–4 (currently holds screen-space delta data, 4×18 bytes = 72 bytes used, rest free)
- $0600–$07BF: particle system (448 bytes, densely packed)

The draw tables at $0300 are only 72 bytes — but they're at the bottom of the page. The right wall arrays could potentially share $0300 if draw tables move.

**This is the main memory pressure point.** Needs careful layout planning.

#### Option B: Keep 8-bit wall arrays, store viewport-relative X
Instead of storing world X in the wall arrays, store **screen-relative X** (0–72). The RLE decoder would subtract `window_xpos` during accumulation rather than at draw time.

**Pros:** Wall arrays stay 8-bit, landscape_draw inner loop unchanged.
**Cons:** Every scroll event must update ALL 256 entries in both arrays (subtract scroll delta). That's 512 LDA/SBC/STA operations = ~5,120 cycles per scroll frame. X-wrap must recompute everything. Much worse than current architecture.

#### Option C: Keep wall arrays as world X, widen to 16-bit with interleaved storage
Store `terrain_left_wall` as 512 bytes (2 per entry, LO then HI). Indexing becomes `Y*2`.

**Cons:** All terrain indexing doubles. Y register can only reach 128 entries before overflow. Breaks the elegant single-byte-index circular buffer design.

**Recommendation: Option A** — split LO/HI arrays. This preserves the existing indexing pattern and only costs memory, not cycles in the inner loop.

### 3. Landscape Draw — Significant Rewrite (`thrust.6502:843–993`)

**Current flow per scanline:**
```
LDA terrain_left_wall,Y    ; 4c — load 8-bit world X
SBC #window_xpos_INT       ; 2c — self-modified immediate (screen X = world X - window)
BCC clamp_zero             ; 2c
CMP #72                    ; 2c
BCC ok                     ; 2c
```

**New flow per scanline (16-bit subtract):**
```
SEC                        ; 2c
LDA terrain_left_wall_LO,Y ; 4c
SBC window_xpos_INT        ; 3c (ZP)
STA temp                   ; 3c
LDA terrain_left_wall_HI,Y ; 4c
SBC window_xpos_EXT        ; 3c (ZP)
BNE offscreen_or_clamp     ; 2c/3c — if high byte != 0, wall is far offscreen
LDA temp                   ; 3c
CMP #72                    ; 2c
BCC ok                     ; 2c
```

**Cycle cost increase per scanline:** Currently ~10c per wall (2 walls x 111 scanlines = ~2,220c). New: ~28c per wall = ~6,216c. **Extra ~4,000c per frame** (~10% of frame budget).

This is the most performance-critical change. The self-modifying immediate operand trick no longer works because we need a 16-bit subtraction. Could self-modify two immediate bytes, but that's still more instructions.

**Mitigation:** The high byte check (`BNE offscreen`) will short-circuit most scanlines when the wall is far offscreen (high byte difference != 0). In practice, only walls within 256 columns of the viewport need the full comparison.

### 4. Terrain RLE Decoder — Medium Rewrite (`thrust.6502:1085–1259`)

The RLE accumulator (`terrain_*_wall_*_xpos`) becomes 16-bit. The increment values in level data can stay 8-bit (signed, -128 to +127 per row) but must be sign-extended for 16-bit addition.

**Current (line 1226–1241):**
```
ADC (terrain_data_x_increment_ptr),Y  ; 8-bit add
```

**New:**
```
ADC (terrain_data_x_increment_ptr),Y  ; add low byte
STA terrain_wall_xpos_LO
LDA terrain_wall_xpos_HI
ADC #$00                              ; or ADC #$FF if increment was negative
STA terrain_wall_xpos_HI
```

The sign extension of the increment is the tricky part — need to check bit 7 of the increment byte to determine whether to add #$00 or #$FF to the high byte. This adds ~8 cycles per terrain row decoded (2 rows per scroll frame = negligible).

**The four terrain triples** each need a `_xpos_HI` companion variable (4 extra bytes, can go in the terrain variable block near line 1156).

### 5. World X Wrap Logic — Rewrite (`thrust.6502:2894–2965`)

**Current:** Single-byte comparisons and additions for wrap detection/application.

**New:** All comparisons become 16-bit. The wrap constants become 16-bit. All entity X position adjustments (`window_xpos`, `midpoint_xpos`, `player_xpos`, `old_player_xpos`, all 32 particles) need 16-bit addition.

**Wrap constant changes:**
- `WORLD_X_WRAP_THRESHOLD` — becomes 16-bit, configurable per level
- `WORLD_X_WRAP_FORWARD` / `BACKWARD` — 16-bit deltas
- The world width itself becomes a level parameter

**Particle loop (lines 2928–2936):** Currently 32 iterations of 8-bit add. Becomes 32 iterations of 16-bit add. Extra cost: 32 x ~6c = ~192c (only during wrap frames, which are rare).

**Draw table edge-case handling (lines 2938–2965):** The 0/72 swap logic for terrain draw tables still works conceptually but the conditions change for wider worlds.

### 6. Object System — Major Change

**Level data format** (`level_data.6502`): Add `level_N_obj_pos_X_EXT` arrays (high byte), following the existing pattern of `level_N_obj_pos_Y` / `level_N_obj_pos_Y_EXT`.

**Self-modifying load code** (`thrust.6502:1921–1935`): Add a third self-modified `LDA level_0_obj_pos_X_EXT,X` instruction. The initialise_level_pointers function needs new lookup table entries.

**Object visibility test** (`thrust.6502:1960–1972`): Currently:
```
LDA current_obj_xpos_INT
SBC window_xpos_INT
```
Becomes 16-bit subtraction. If high byte of result is non-zero, object is offscreen (fast reject).

**Object-to-bullet collision** (`thrust.6502:1597–1633`): 16-bit X delta. Fast reject on high byte.

### 7. Particle System — Straightforward Extension

Add `particles_xpos_INT_HI` array (32 bytes) at a new page-aligned address. All particle spawn code adds high byte init. Movement code (`thrust.6502:6204–6212`) becomes 4-byte add (add carry from INT to INT_HI).

**Particle-terrain collision** (`thrust.6502:5977–5982`): Currently compares `particles_xpos_INT` directly against `terrain_left/right_wall`. With 16-bit walls, this becomes a 16-bit comparison.

### 8. Ship/Pod/Midpoint Position — Medium Changes

**Midpoint force integration** (`thrust.6502:5534–5543`): Currently 3-byte chain (FRAC_LO -> FRAC -> INT). Becomes 4-byte (-> INT_HI). The force vector X already has Q7.16 precision; the high byte is just sign extension.

**Ship position from midpoint** (`thrust.6502:4263–4288`, 5595–5676): Add INT_HI carry propagation. Midpoint_deltax is a small signed offset (ship-to-midpoint distance / 2), so its INT_HI is always 0 or $FF — sign extend.

### 9. Distance Calculations — Subtle Rewrite

**Ship-to-pod distance** (`thrust.6502:7100–7170`): The BVS overflow check at line 7119 detects 8-bit signed overflow. With 16-bit X, the subtraction result can exceed 8 bits. Need 16-bit delta with overflow on the full 16-bit result instead.

---

## Performance Impact Summary

| System | Extra cycles/frame | Frequency | Net impact |
|--------|-------------------|-----------|------------|
| landscape_draw (2 walls x 111 scanlines) | ~4,000c | Every frame | **~10% frame budget** |
| Terrain RLE decode | ~16c | Per scroll frame | Negligible |
| X-wrap entity adjustment | ~250c | Rare (wrap frames) | Negligible |
| Object visibility (per object) | ~6c | Per object per frame | ~60c for 10 objects |
| Particle movement (32 particles) | ~64c | Every frame | <0.2% |
| Midpoint/ship/pod position calc | ~30c | Every frame | <0.1% |
| **Total typical frame** | **~4,150c** | | **~10.4%** |

**The dominant cost is landscape_draw.** The 16-bit world-to-screen subtraction on every scanline is unavoidable. Mitigation strategies:

1. **Self-modify both bytes** of an immediate 16-bit subtract (saves the ZP loads each scanline)
2. **Cache the high byte comparison**: if `terrain_wall_HI == window_xpos_EXT`, only then do the low byte subtract. Most walls in view will have matching high bytes. Branch prediction helps.
3. **Pre-subtract window_xpos from wall arrays** at scroll time (Option B above) — trades per-scanline cost for per-scroll cost. Only viable if scrolling is infrequent.

---

## Memory Impact

| Item | Bytes | Location |
|------|-------|----------|
| New ZP variables | ~10 | $00A8+ |
| terrain_left_wall_HI array | 256 | Need page-aligned RAM |
| terrain_right_wall_HI array | 256 | Need page-aligned RAM |
| particles_xpos_INT_HI array | 32 | Within particle pages |
| Level data X_EXT arrays | ~6–19 per level | ROM (level_data.6502) |
| Terrain triple xpos_HI vars | 4 | Near line 1156 |
| Code size increase | ~200–300 | Various |
| **Total RAM** | **~560** | |

The main challenge is finding 512 bytes of page-aligned RAM for the wall high-byte arrays. Current memory map is tight:
- $0300–$05FF is terrain tables + wall arrays
- $0600–$07BF is particles
- Below $0300 is OS workspace / ZP / stack

Options:
- Relocate terrain draw tables (72 bytes) to make room
- Use SWRAM ($C000+) for the high-byte arrays (slower access from main RAM code)
- Shrink particle pool from 32 to 24 entries, freeing a page

---

## Level Data & Tooling Changes

### level_data.6502
- Add `.level_N_obj_pos_X_EXT` arrays (one byte per object, high byte of X)
- Terrain RLE increment data can stay 8-bit (signed per-row delta)
- Need new initial X position high bytes for terrain wall triples

### tools/level_editor.py
- Object X coordinates become 16-bit in the editor's internal model
- Export adds `obj_pos_X_EXT` arrays
- Canvas/viewport needs to support wider worlds
- The editor already handles 16-bit Y via `obj_pos_Y_EXT`; follow same pattern

### thrust.6502 initialise_level_pointers
- Add lookup tables for `level_obj_pos_X_EXT_lookup_LO/HI`
- Add self-mod patching for the new `LDA level_0_obj_pos_X_EXT,X` instruction

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| landscape_draw performance regression (~10%) | **High** | Profile before/after; self-mod optimization; consider SWRAM fast path |
| Memory layout — finding 512 bytes for wall HI arrays | **High** | Map out exact page usage; may need to reorganise $0300–$07BF |
| Subtle 8-bit assumption in untouched code | **Medium** | Comprehensive grep for all X variables; test at world edges |
| Terrain RLE sign extension bugs | **Medium** | Unit test the decoder with known level data |
| Wrap logic correctness at 16-bit boundaries | **Medium** | Test with world width just over 256 |
| Level editor canvas scaling for wide worlds | **Low** | Pygame viewport already scrolls |

---

## Suggested Implementation Order

1. **Zero page & variable declarations** — allocate all new `_INT_HI` / `_EXT` variables
2. **Memory layout** — decide where wall HI arrays go; relocate if needed
3. **Terrain wall arrays & RLE decoder** — 16-bit accumulation, split LO/HI storage
4. **landscape_draw** — 16-bit world-to-screen conversion
5. **World X wrap logic** — 16-bit comparisons and adjustments
6. **Object system** — level data format, visibility, collision
7. **Particle system** — xpos_INT_HI, movement, terrain collision
8. **Ship/pod/midpoint position** — force integration, position calc
9. **Level editor & data export** — 16-bit X support
10. **Testing** — build with world width = 300 (just over 256) to exercise 16-bit paths

---

## Verification

- Build with `_WIDE_WORLD = TRUE` and `FALSE` — both must compile
- With `FALSE`: CRC32 must match original ($6389C446)
- With `TRUE`: test level with world width > 256
- Verify terrain renders correctly at X positions > 255
- Verify X-wrap works at 16-bit boundaries
- Verify all object types visible and interactable at high X
- Verify particles spawn/move/collide correctly at high X
- Verify ship-to-terrain collision at high X
- Profile landscape_draw to measure actual cycle cost increase
