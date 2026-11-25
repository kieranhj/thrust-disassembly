# thrust: start here

Thrust (Jeremy C. Smith, Superior Software 1986) for the BBC Micro: Kieran's 2016 reverse-engineered,
annotated source that rebuilds the original byte for byte, now also "Thrust Next", an enhanced build
using a sideways RAM bank (new level features, faster terrain and sprites). A disassembly plus a game
remaster, in beebasm.

| | |
|---|---|
| GitHub | https://github.com/kieranhj/thrust-disassembly (public) |
| Upstream | the original game (`$.THRUST3`, decrypted and relocated; readme.md) |
| Local path | D:\beeb\mine\thrust (moved from OneDrive\BEEB\Repos\thrust on 2026-11-22) |
| Branch | `restart/build-fixes` (158 commits past `master`); other branches: `master`, `wip/experiments`, `wip/fully-unrolled-terrain-draw`, `wip/new-comments` |
| Last commit | 2026-10-28: Docs: PLAN.md rewritten for where the branch stands; decisions log; loader brief |

## What's in here
- `thrust.6502` - the whole game; `-D _SWRAM_BUILD=0` is the original, `-1` Thrust Next. `app_init.asm`, `thrust1/` (level data, MODE 7 instructions).
- `build.ps1` - the build (both discs, CRC check, `-Smoke`, `-Flags`, `-Release`, `-Run`); `make.bat` / `run.bat` call it.
- `beebasm.exe` - pinned beebasm 1.11 in the repo root.
- `tools/` - level and sprite editors (Python), jsbeeb smoke tests (`smoke.mjs`, `check_laser_clip.mjs`, `frametime.mjs`), `test_tools.py`.
- `docs/` - `decisions.md`, `bugs.md`, `ideas.md`, `review-2026-10.md`, feature plans, engine write-ups.
- `memory/` - two copied memory notes (PLAN.md asks whether to keep them).

## Build and run
- `make`: runs `build.ps1`: `build\thrust-orig.ssd` (must be CRC32 `6389c446`) and `build\thrust.ssd` (SWRAM).
  Other targets: `make release`, `make flags`, `make smoke` (node + jsbeeb, headless), `make run` /
  `make run-orig` (launch b2), `make help`.
- Tools: `beebasm.exe` in the repo (or `$env:BEEBASM`); node for the smoke tests; Python 3 for `tools\`.
- Run: `make run` opens b2 (`$env:B2`, else `D:\tools\beeb\b2\b2\b2.exe`); `build.ps1 -Run -Beebjit` uses beebjit.
  The SWRAM build needs sideways RAM (the bank is probed).

## Local changes
- No uncommitted work before the 2026-11 tidy.
- 2026-11-22: `build.ps1`'s fallback emulator paths updated from `OneDrive\Retro\BEEB\...` to `D:\tools\beeb\...` (uncommitted).
- New, uncommitted: `Makefile`, `START_HERE.md`.
- `wip/experiments`, `wip/fully-unrolled-terrain-draw`, `wip/new-comments` are older work branches (April and
  October 2026), already on origin; PLAN.md says to merge `restart/build-fixes` into `wip/experiments` or replace it.

## Status and next steps
- Everything on `restart/build-fixes` is checked in jsbeeb only; KC has not played it on b2 or hardware.
- PLAN.md order: KC's play test and decisions 3, 8, 9, 10; frame rate (laser beam plotter); loader and
  memory (load the bank as its own file); then publish a WIP.

## See also
- `readme.md`, `CLAUDE.md`, `PLAN.md`, `docs/decisions.md`, `docs/bugs.md`, `docs/ideas.md`.
