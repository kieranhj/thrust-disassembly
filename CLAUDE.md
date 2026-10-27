# CLAUDE.md

Guidance for Claude Code in this repository.

## Project

Annotated disassembly of **Thrust** (BBC Micro, Jeremy C. Smith, 1986), reverse-engineered by Kieran HJ Connell with BeebDis, assembled with **BeebAsm 1.11** (`beebasm.exe` in the repo root). One source tree builds two games:

- **The original**, byte-identical to the released game. `master` holds only this.
- **Thrust Next**, the enhanced sideways RAM build on this branch line: new objects, switches, doors, teleporters and editor-authored levels. Feature work is indexed in `docs/ideas.md`.

Files: `thrust.6502` (~14k lines, everything), `app_init.asm` (boot, relocation, CRTC/ULA, IRQ install), `thrust1/` (level data, object sprites, MODE 7 instructions, status bar), `tools/` (Python level/sprite editors), `docs/` (references, plans, `bugs.md`).

## Build

```
.\build.ps1             both discs into build/; fails unless the original is CRC32 6389c446
.\build.ps1 -Run        ...and launch b2 on the SWRAM disc (-Beebjit, -Orig for the original)
```

`make.bat` / `run.bat` wrap these. Outputs in `build/` (gitignored): `thrust-orig.ssd`, `thrust.ssd`, a log (`*.txt`) and a label dump (`*.labels`) per build. The script prints the build's RAM-free reports.

**The CRC is the regression test for the original game's behaviour.** A build that moves `thrust-orig.ssd` off `6389c446` fails. Every Thrust Next change must sit behind a flag that is false when `_SWRAM_BUILD` is false.

## Build flags (`thrust.6502:30-50`)

All use `=?`, so `-D NAME=0|-1` overrides any of them without editing the source. `_SWRAM_BUILD` selects the game; the others default to `(_SWRAM_BUILD AND TRUE|FALSE)`. Debug: `_DEBUG_RASTERS`, `_DEBUG_FRAME_TIME`. Engine: `_UNROLL_TERRAIN`, `_FAST_SPRITES` (off, unfinished), `_NO_WRAP_UNDERGROUND`, `_THRUST_PARTICLES`, `_FRIENDLY_KEYS`. Features: `_TIMED_LASER`, `_GRAVITY_WELL`, `_Y_BANDS`, `_BOBBING_MINES`, `_TELEPORTER`, `_LAST_USED_CHECKPOINT`, `_SWITCHES`. `_OBJ_DATA_SLOTS` is derived. `_TELEPORTER` requires `_GRAVITY_WELL` and `_LAST_USED_CHECKPOINT` (asserted). Each feature flag can be turned off on its own (the teleporter's two prerequisites only with it) and the build still assembles; keep it that way.

## Conventions

- BeebAsm syntax: `\` comments, `$` or `&` hex, `EQUB`/`EQUW`/`EQUS`.
- Fixed point: mostly Q7.8; Y is Q10.8 (worlds are several screens deep); some X physics Q7.16.
- Suffixes: `_LO`/`_HI` bytes of a 16-bit value; `_FRAC`/`_INT` fixed-point parts; `_FRAC_LO` extra low byte; `_INT_HI` extra high byte.
- Memory: loads at `$1A00`, relocates to `$0A60`. Zero page for variables, `$300-$5FF` terrain, `$600-$7BF` particles, `$7C0+` sound, `$880+` trig tables, screen at `$3C80` (MODE 1 ULA, 72-column CRTC). Thrust Next: sideways RAM bank 4 at `$8000` (code and level data, appended to the `Thrust` file and copied up at boot); bank 5 reserved for `_FAST_SPRITES`. Main RAM is nearly full in both builds.
- Timing: the game frame is at least 3 cs (~33 Hz), gated on the OS clock, not 50 Hz vsync. Scrolling is software: everything on screen is XOR-redrawn each frame.
- Prefer labels to line numbers in docs; line numbers drift.

## Where things are

- `PLAN.md`: what is left to do, in order.
- `docs/bugs.md`: known defects and stale comments.
- `docs/review-2026-10.md`: the October 2026 review against `..\beeb-port-kit`, with evidence for each `PLAN.md` item.
- `docs/plan-*.md`: as-built designs of each feature, with status lines.
