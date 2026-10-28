# Plan

**What is left to do, in order.** Choices are in [docs/decisions.md](docs/decisions.md), defects in [docs/bugs.md](docs/bugs.md), feature ideas in [docs/ideas.md](docs/ideas.md); [docs/review-2026-10.md](docs/review-2026-10.md) is the review this plan started from (section numbers in brackets). When an item lands, delete its line here; the commit says what changed. Keep this file short.

**Every change:** `.\build.ps1 -Smoke` must pass (original CRC `6389c446`, both discs play all six levels, the laser clip check). Engine changes go behind an SWRAM flag; `-Flags` checks each can be turned off.

## Where it stands (2026-10-28, branch `restart/build-fixes`)

- **Build:** `build.ps1` builds both discs from one source and fails on a CRC change; `-Smoke`, `-Flags`, `-Release` (INFO file), `-Run` (b2/beebjit).
- **Tests:** `tools/test_tools.py` (level and sprite round-trips, engine constants); `tools/smoke.mjs` (jsbeeb, both discs, all levels, Model B or Master); `tools/check_laser_clip.mjs`; `tools/frametime.mjs` (frame-length histogram: demo, idle or scripted flight).
- **Fixed since the review:** every bug in review section 2 except 2.6's full workspace (the data restore is done), the underground X clamp, all stale comments, the editor's file/cap/radius issues, broken sprite tools.
- **Memory:** main RAM `&26E` free (was `&1A8`), load headroom `&A44`, bank `&1C84`. The bank is probed, not assumed.
- **Not checked by a person:** nothing on this branch has been played by KC or run on b2/beebjit/real hardware. Everything was checked in jsbeeb.

## 1. Waiting on KC

- [ ] Play `build\thrust.ssd` (`.\build.ps1 -Run`) and the original (`-Run -Orig`) on b2 or real hardware: the fixes touch lasers, doors, bands, teleporters, the underground scroll and the boot (bank probe)
- [ ] Decisions 3 (teleporter during the countdown), 8 (`_FAST_SPRITES`), 9 (copy protection), 10 (frame-gate remainder)
- [ ] Merge `restart/build-fixes` into `wip/experiments` (or replace it)
- [ ] Repo `memory/` duplicates two user-level memory notes: keep or delete

## 2. Frame rate

- [ ] Laser beam redraw: a dedicated plotter (`docs/brief-loader-memory.md` §5). The one measured cause of dropped frames in Thrust Next
- [ ] Decision 10 (frame-gate remainder), played side by side
- [ ] Debris emitter: shifts instead of multiplies, skip off-screen, parity bias [3.3]. No measured cost yet; do it when a level with many wells shows one
- [ ] Mask the MOS vsync event [3.5]

## 3. Loader and memory (`docs/brief-loader-memory.md`)

- [ ] Load the bank as its own file (§1): the load headroom is the binding limit for new content
- [ ] Per-level object workspace (§2)
- [ ] Native-RAM `IF` bodies into the bank (§3)
- [ ] Generated memory map (§4)

## 4. Release

- [ ] Publish a WIP of both discs (`publish-wip` skill) once KC has played the branch

## Later

Replace MOS sound with the kit's `sfx50` [3.6]; relocation proof against the original (kit PORTING §2.1c) [7]; split `level_editor.py`, read sprite sizes from the label dump [6.3-6.5]; `sprite_editor.py` importable headless.
