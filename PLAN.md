# Plan

**What is left to do, in order.** Evidence for each item is in [docs/review-2026-10.md](docs/review-2026-10.md) (section numbers in brackets); defects are in [docs/bugs.md](docs/bugs.md); feature ideas in [docs/ideas.md](docs/ideas.md). When an item lands, tick it here with the commit; when a phase is done, collapse it to one line. Keep this file short.

**Rule for every phase:** `.\build.ps1` must pass (original CRC `6389c446`). Engine changes go behind an SWRAM flag.

## Where it stands (2026-10-27, branch `restart/build-fixes` from `wip/experiments`)

Thrust Next plays with all features on. Nothing has been checked in an emulator since the review; there are no automated tests. Main RAM has `&1A8` bytes free in the SWRAM build, and the SWRAM payload's real headroom is ~`&A02`.

## 1. A build that checks itself

- [x] `build.ps1` builds both discs from one source (`_SWRAM_BUILD =? TRUE`, `-D`), stops on beebasm errors, and fails unless the original is `6389c446`; it writes label dumps and prints the RAM reports [1.1]
- [x] Every build flag uses `=?`, so any can be overridden with `-D` [1.1]
- [x] `_DEBUG_FRAME_TIME` store gated on its own flag [1.2]
- [x] Feature flags independent: obj_data lookups under derived `_OBJ_DATA_SLOTS`, door state and `level_switch_state` moved out of the mine and laser blocks, teleporter prerequisites asserted. SWRAM binary unchanged (`84a9e5f1`) [1.3]
- [x] `thrust.ssd` and `crc32dos.exe` untracked, `build/` ignored, `make.bat`/`run.bat` wrap `build.ps1`, `run.bat` uses b2, VS Code build task, `CLAUDE.md` and `readme.md` rewritten [1.4]
- [ ] Repo `memory/` duplicates two user-level memory notes: KC to decide whether to keep it [1.4]

## 2. Tests

- [ ] `tools/test_tools.py`: level round-trip, `from_game_data` vs `level_data.asm`, sprite codec round-trip; move `Tk()` out of import time first [6.1]
- [ ] Smoke test with jsbeeb (node, kit `template/tools/harness.mjs`): boot both discs, reach the main loop on all six levels. Convert the label dump to `<disc>.symbols.json`. Add `.mcp.json` (kit template) for interactive use [7]
- [ ] Optional check in `build.ps1`: build with each feature flag off in turn [1.3]

## 3. Small bugs (SWRAM only, one commit each)

- [ ] Thrust particle `ROR particles_dy_FRAC` missing `,X` [2.1]
- [ ] Fuel tractor counters cleared for 12 slots, not 32 [2.2]
- [ ] Teleporter: refuse while dying or during the reactor countdown [2.3]
- [ ] Clip up-facing laser beams to the playfield [2.4]
- [ ] Per-type tables missing door ($11) entries; `ASSERT` table lengths; editor blocks invalid destroy targets [2.7]
- [ ] Door on-screen test, zero width, `open_compare` [2.8]
- [ ] Bands vs invisible landscape [2.9]
- [ ] Unpause needs CAPS LOCK with `_FRIENDLY_KEYS` [2.10]
- [ ] Editor: cap objects at `LEVEL_MAX_OBJECTS`; default to `export2.asm`, delete the stale export [2.11, 2.12]
- [ ] Stale comments and dead code listed in `docs/bugs.md`

## 4. Frame rate (measure before and after with kit `beeb-frame-drops`, against the 3 cs gate)

- [ ] Carry the frame-gate remainder instead of zeroing the clock [3.1]
- [ ] MOS keyboard scan off during play (OSBYTE `&B2`) [3.2]
- [ ] Debris emitter: shifts instead of multiplies; skip off-screen; fix parity bias [3.3]
- [ ] Per-type object index lists [3.4]
- [ ] Mask the MOS vsync event [3.5]

## 5. Loader and memory (one brief: `docs/brief-loader-memory.md`, to write)

- [ ] Probe for sideways RAM instead of hard-coding banks 4/5 (kit `lib/swram_probe.6502`) [2.5]
- [ ] Load the bank as its own file (kit `lib/loader.6502`) [4.2]; stop copying the `skip &480` [4.3]
- [ ] Per-level object workspace in SWRAM; restores level data each game [4.1, 2.6]
- [ ] Move native-RAM `IF` bodies into SWRAM; `IF NOT _SWITCHES` round the legacy doors [4.4]
- [ ] Generated memory map from the label dump [4.5]

## 6. Release

- [ ] `RELEASE` flag: asserts debug flags off and `INITIAL_LEVEL`/`INITIAL_CHECKPOINT` at defaults; `INFO` build stamp (kit `lib/boot_stamp.6502`) [7]
- [ ] Publish a WIP of both discs (`publish-wip`) [7]

## Decisions for KC

- [ ] `_FAST_SPRITES`: finish it with phase 5's bank loader, or delete it and `generate_ship_streams.py` [5]
- [ ] Remove the copy protection check from the SWRAM build [5]
- [ ] Start `docs/decisions.md` (numbered log of each deviation from the original) [7]

## Later

Replace MOS sound with kit `sfx50` [3.6]; relocation proof against the original (PORTING §2.1c) [7]; split `level_editor.py`, one source for engine constants, drop hard-coded level copies [6.3-6.5].
