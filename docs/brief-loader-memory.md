# Brief: loader, memory and the laser beam

**Status:** not started. Costed 2026-10-28 from the build's own reports and jsbeeb measurements. The cheap parts of the original review's section 4 are done (the `&480` scratch is no longer in the file, the bank is probed, level data is restored per level, the legacy door routines are gone from the SWRAM build).

## Where memory stands (read off `.\build.ps1`)

| Space | Free | Limit |
|---|---|---|
| Main RAM (SWRAM build) | `&26E` | `GUARD` in `thrust.6502` |
| Sideways bank | `&1C84` | `&C000`, after the level object snapshot |
| `Thrust` file load headroom | `&A44` | MODE 7 screen at `&7C00`, still up during the load |

The binding limit for new Thrust Next content is the load headroom: the bank payload travels inside the `Thrust` file, which loads at `&1A00`. Levels, sprites and feature code all come out of that `&A44`.

## 1. Load the bank as its own file (frees the load headroom)

`SAVE "Bank"` the payload as a separate file, and have the boot load it into the probed bank before `Thrust` runs. The kit's `lib/loader.6502` (`load_bank`) does this with OSFILE into a buffer and a copy; it needs the BeebAsm conversion in the kit's `docs/toolchain-baron.md`. `!BOOT` then becomes a small loader (`*RUN Loader`), so the disc gets a hand-written `!BOOT` instead of beebasm's `-boot Thrust`.

- Gain: the bank's full `&1C84` becomes usable, and the `Thrust` file shrinks back to main RAM only.
- Cost: M. The probe (decision 5) has to run before the load, so it moves from `copy_up_swram` into the loader. The original disc keeps `-boot Thrust` (its CRC includes the catalogue).
- Check: smoke on both models, and a `*TYPE !BOOT`.

## 2. Per-level object workspace (frees ~800 bytes of main RAM)

`initialise_level_pointers` patches ~45 self-modified sites per level from per-level pointer tables, 969 bytes of main RAM. At level start, copy the current level's seven object columns (32 x 7 = 224 bytes) into one fixed workspace in the bank and point every site at it once at boot. The level object restore (decision 4) then becomes part of the copy.

- Gain: ~800 bytes of main RAM; one place to read object state.
- Cost: M-L. Every SMC site that loads `level_N_obj_*` must be found (grep `**SELF-MODIFIED CODE**` with `level_0_obj`); a missed one reads stale data only on levels 1-5, so the smoke test on all six levels plus a wall/obj-array comparison like the door check in commit `a226fe7` is the gate.

## 3. Move native-RAM `IF` bodies into the bank

The checkpoint block in `level_reset`, the mine contact test and the SWRAM type dispatch in `update_and_draw_all_objects` sit in main RAM. Each can become one `JSR` into the bank. Gain a few hundred bytes; cost S each; check with the smoke test.

## 4. Generated memory map

`build/thrust.labels` has every label. A short script can print the regions (zero page, main RAM by routine, the bank) into `build/memory-map.txt`, and the kit's `beeb-ram-hunt` skill works from it. Cost S.

## 5. Laser beam redraw (the frame-rate item)

Measured with `tools/frametime.mjs --level 0 --fly`: 74 of 422 frames take 4 cs in the SWRAM build against 6 in the original; with `_TIMED_LASER` off, 12. Level 0's turret has a 119-pixel beam, and with software scrolling the whole beam is erased and redrawn through the general Bresenham `draw_line` (~85 cycles a pixel) on every scrolling frame: ~20,000 cycles, a third of the frame.

Options, cheapest first:
- A dedicated plotter for the beam's shape. Most authored beams are near-horizontal or near-vertical; a run-length plotter that writes a byte (4 pixels) at a time along X would cut the near-horizontal case several-fold.
- Erase and redraw only the part that moved: on a vertical scroll the beam moves as a whole, so this only helps if the screen copy can be shifted, which software scrolling doesn't give us.
- Shorter beams in the level design (free, but a design call).

Cost M for the plotter; check with `tools/check_laser_clip.mjs` (beam stays on the playfield) and `frametime.mjs` before and after.
