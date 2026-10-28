# Decisions

Every deviation from the original game, and every choice that shapes Thrust Next, gets a number here. **Status:** *agreed* (KC said so), *built* (in the code, awaiting KC's word), *proposed* (not built), *rejected* (tried or costed, not taken). Newest last. Feature designs are in the `plan-*.md` files; this is the index of choices.

Started 2026-10-28; earlier choices are recorded in the plan docs and not back-filled here except where they constrain new work.

| # | Decision | Status | Evidence |
|---|---|---|---|
| 1 | One source, two games. `_SWRAM_BUILD =? TRUE`; `build.ps1` builds both. The original (`-D _SWRAM_BUILD=0`) must stay byte-identical, CRC32 `6389c446`; every Thrust Next change sits behind a flag that is false there. | agreed | `CLAUDE.md`, `build.ps1` |
| 2 | Every build flag uses `=?` and each feature can be turned off on its own (the teleporter needs the gravity well and last-used checkpoint, asserted). Per-type tables carry every Thrust Next type under `_SWRAM_BUILD` so their indices never shift. | built | `build.ps1 -Flags`; commits `79dbc39`, `5f38b04` |
| 3 | The teleporter refuses to warp while the ship is dying or the reactor countdown runs. The alternative for the countdown is to carry it through the warp (`level_reset` currently resets it). | built, KC to confirm | commit `11e1928`; `plan-teleporter.md` |
| 4 | Level object arrays are restored from a boot-time snapshot at every new level; deaths keep the changes (wiring effects persist across lives, as `plan-switches-and-triggers.md` §1 intends). | built | commit `ff498b5` |
| 5 | Sideways RAM: probe banks 4-15 then 0-3, skip banks the MOS registered a ROM in, take the first that holds two complementary values; no bank, print why and stop. One bank is enough (`_FAST_SPRITES` keeps fixed banks 4/5). | built | commit `5e7c3bf` |
| 6 | Leave the MOS keyboard scan on during play. Disabling it (System VIA CA2 off; zeroing `&0242` alone does nothing on MOS 1.20, the next keypress sets it again) gained ~0.1 fps on the worst measured level. | rejected | `tools/frametime.mjs --level 0 --fly`: 74 -> 60 frames of 4 cs out of 422, mean 31.9 -> 32.0 fps |
| 7 | `RELEASE` builds assert both debug flags off and the game's own start level/checkpoint, and carry an `INFO` file (commit and flags). | built | commit `c666f0b` |
| 8 | `_FAST_SPRITES`: finish it (needs the bank loader, a sprite-scratch skip in bank 5 and the mirrored-frame +1) or delete it with `generate_ship_streams.py` and `ship_twostream_data.asm`. Its measured gain would be ~2,000 cycles a frame. | open | `docs/bugs.md`; `sprite-draw-performance.md` |
| 9 | Copy protection (`BYTEV+1` check, `app_init.asm`) in the SWRAM build: remove it, since it scrambles the unencrypted image if a RAM utility hooks OSBYTE. | open | `docs/review-2026-10.md` §5 |
| 10 | Frame gate: carry the remainder past 3 cs instead of zeroing the clock, so a frame of 3.01 cs doesn't cost 4. Changes the game's pace when it overruns, so it is a taste call to play side by side. | open | `docs/review-2026-10.md` §3.1; worst case measured is level 0 flying, 18% of frames at 4 cs |
