# Plan: gravity well object

A new object type that, while the ship is inside its radius, applies a per-frame radial pull toward its centre. Stored per-instance so a level designer authors centre, radius, and strength. SWRAM-only — gated by a new `_GRAVITY_WELL` flag so the canonical non-SWRAM CRC `6389c446` is unaffected.

The companion idea **gravity null** (zero gravity inside a radius) is in scope as a sign/flavour of the same object: a signed strength byte means strength=0 effectively cancels a designer-blended pull, and a dedicated negative range can be reserved for "repulsor" later. Keep the on-disc layout identical for both so adding new behaviours is a runtime branch, not a data-format change.

## Decisions confirmed

- **One object type, signed `strength` byte.** Positive = pull (well), negative = push (repulsor), zero = inert. Avoids burning two type slots for what is the same code path.
- **Linear ramp inside radius** — no divide, no `1/r²`. Force magnitude = `strength * (radius − r) / radius` clamped at zero outside. Cheap, monotonic, behaves intuitively at the centre (max pull, no singularity).
- **Manhattan distance** (`|dx| + |dy|`) for the inside-radius test and as the basis of the ramp. Avoids a 16-bit square + sqrt. Visual asymmetry at the diamond edge is acceptable for an authored hazard.
- **Affect ship only in v1.** Bullets and the pod are deferred — see "Things to watch out for". The hook point still leaves room to extend.
- **No interaction with the existing constant gravity.** Pull is *added* to `force_vectory_FRAC/INT` (and `force_vectorx_*`) after the existing `add_gravity_to_force_vector` block. Gravity-null variant (strength sign-bit interpretation TBD) can substitute rather than add later if desired.
- **SWRAM-only.** New flag `_GRAVITY_WELL = _SWRAM_BUILD AND TRUE` near `thrust.6502:39`. Matches the laser pattern; CRC unchanged for the canonical build.

## Object-type slot

Next free type id after the laser block:

```
OBJECT_gravity_well                  = $D       ; SWRAM only, behind _GRAVITY_WELL
```

at `thrust.6502:113` area, inside an `IF _GRAVITY_WELL` block. Bump `obj_type_width` and `obj_type_height` (`thrust.6502:1401`/`1408`) with one entry each — pick a small hitbox (`$04`/`$04`) since the well is non-collidable visually. `obj_type_explosion_particle` and `obj_type_score_value` get `$00,$00` pad entries (not destructible).

## Data model per instance

Two new signed bytes, parallel to `level_N_obj_pos_X` etc. Existing position arrays carry the centre.

| Symbol                            | Type            | Range            | Notes                              |
|-----------------------------------|-----------------|------------------|------------------------------------|
| `level_N_well_radius`             | 8-bit unsigned  | 0..127 BBC px    | 0 = disabled. Manhattan radius.    |
| `level_N_well_strength`           | 8-bit signed    | −127..+127       | Q0.7-ish; positive = pull.         |

Per-level lookup tables (`level_well_radius_lookup_LO/HI`, `level_well_strength_lookup_LO/HI`), mirroring the laser ones at `thrust.6502:10267`. Both tables live in SWRAM alongside `level_laser_dx_lookup_*` (RAM is tight in the SWRAM build — note at `thrust.6502:10264-10266`).

Non-well slots emit `0,0` in their entries; the runtime never indexes these for non-well types, so the cost is purely 2 bytes × 32 slots × 6 levels = 384 bytes total per pair, both pairs = 768 bytes. If RAM bites, see "Things to watch out for".

## Physics integration

The constant gravity is applied at `thrust.6502:4069 .add_gravity_to_force_vector`. That routine runs on the ship-input/thrust path, not every object iteration. The natural hook is **a new function `apply_gravity_wells_to_force` called once per frame from the same place**, immediately after the gravity add and before the thrust force is summed in:

1. `JSR apply_gravity_wells_to_force` after the gravity addition at line ~4076, gated by `IF _GRAVITY_WELL`.
2. The function walks the object type array (terminated by `$FF`) the same way `update_all_laser_beams` does at `thrust.6502:10311-10335`. SMC-patched LDAs, mirror entries in `initialise_level_pointers` at `thrust.6502:6900` (alongside the laser block at `6933-6948`).
3. For each object whose type == `OBJECT_gravity_well`:
   - Load `dx = obj_pos_X − new_ship_xpos_INT` (signed); `dy = obj_pos_Y − new_ship_ypos_INT` (signed). World X wraps; treat `dx` modulo 256 as already signed by virtue of two's complement subtraction. Y high byte is ignored — wells must not span more than ±127 rows from the ship to register; outside that is effectively "not in radius".
   - Compute `r = |dx| + |dy|` (Manhattan).
   - If `r >= radius`, next object.
   - Compute `pull = strength * (radius − r)` — one 8×8 multiply, high byte is the Q0.7 pull magnitude. Use the existing `multiply_*` machinery (zp slots `$88..$8B` are already wired for the laser, but those are reused at draw-line time only — verify no overlap with this earlier-in-frame call).
   - Decompose along axes: `force_x_add = pull * sign(dx) * |dx| / r`, same for Y. To avoid the divide: since `r = |dx| + |dy|`, the per-axis share is just `|dx| / (|dx| + |dy|)` — pre-tabulate a 128-entry "ratio" table keyed on `|dx|` with `|dy|` implicit, OR simply skip the ratio and apply `pull * sign(dx)` and `pull * sign(dy)` independently scaled by 1/2 each. The latter is simpler and preserves diamond-symmetry visually; pick that for v1.
   - `force_vectorx_FRAC/INT += pull_x`; same for Y, signed add with carry/borrow propagation.

Cost estimate: each well = ~50 cycles. With 4 wells per level the total is well under a scanline.

## Math summary

- Inside-radius test: `(|dx| + |dy|) < radius`, all 8-bit unsigned after taking abs.
- Pull magnitude: `(radius − r)` shifted into Q0.7 against `strength`. One 8×8 multiply (`multiply_signed_a_by_b` or whichever the codebase already exposes — see existing uses near `thrust.6502:4106-4120`).
- Direction: `sign(dx)` and `sign(dy)` derived from the original signed differences (preserve before taking abs).
- Centre case (`dx == 0 && dy == 0`): `r = 0`, ramp is at maximum, but the per-axis sign factors are both zero, so the force contribution is zero. No divide-by-zero to handle. The ship just sits there until the constant gravity kicks it back into motion — fine.

## Editor support (`tools/level_editor.py`)

Mirror the laser-endpoint drag handle work (see `level_editor.py:140-141`, `1274-1277`, `1366-1391`):

1. **Sprite:** placeholder — a hollow circle drawn at the well centre with the radius rendered as a faint dotted ring, so the designer sees what they're authoring without needing a baked sprite. Real sprite can come later.
2. **Model fields:** add `well_radius`, `well_strength` keys to each object dict, defaulting to `(40, +60)` for newly placed wells.
3. **Radius drag handle:** a small filled circle at `(centre_x + radius, centre_y)`. Dragging it in screen space updates `well_radius` (clamped 0..127). Same `grab_dx/grab_dy` offset trick as the existing object drag.
4. **Strength keys:** `[`/`]` to nudge `well_strength` ±1 with shift = ±10. Status bar shows `r=40 s=+60`.
5. **Export/import:** emit `level_N_well_radius` and `level_N_well_strength` arrays alongside the laser ones (around `level_editor.py:563-566`). Loader reads them with default 0/0 if absent — back-compat with pre-feature exports.
6. **Visual feedback:** during play-test mode (if any), the editor needn't simulate physics; just showing the radius is enough.

## Suggested implementation order

Each step is independently testable.

1. **Asm: object type slot, padding in width/height/score/explosion tables, build flag.** Build SWRAM and non-SWRAM; CRC stays at `6389c446` for the latter.
2. **Asm: per-level data arrays + lookup tables + `initialise_level_pointers` wiring + SMC sites.** Data is dummy-zeroed; runtime sees no wells. Build still passes.
3. **Asm: `apply_gravity_wells_to_force` walk + ramp math + force add.** Hand-author one well in level 0 data, fly into it, confirm the ship gets pulled.
4. **Editor: model fields + placement + radius drag + status bar.**
5. **Editor: export/import.** Round-trip a level with a well, build, run, confirm in-game pull matches the editor circle.
6. **Polish:** sprite, gravity-null variant (re-purpose negative strength or reserve a flag bit), mark the idea entry in `docs/ideas.md` as implemented.

## Things to watch out for

- **SWRAM RAM budget.** Two new 32-byte arrays per level × 6 levels = 384 bytes; two new lookup-table pairs = ~24 bytes. Recent commits have squeezed RAM headroom hard (per CLAUDE.md). If the build fails to link, candidates to trim: pack `radius` and `strength` into one byte (4 bits radius × 8 = 0..120, 4 bits signed strength); or restrict gravity wells to a subset of slots (e.g. max 4 per level) and use a parallel array indexed by well-id, not by object slot.
- **Existing gravity interaction.** v1 *adds* to the gravity force vector. A well pulling upward against downward gravity will visibly lighten the ship before reversing — that is the intended "gravity field" feel. The `gravity-null` variant in v2 should *replace* `gravity_FRAC/SIGN` for the integration, which means moving the well loop *before* `add_gravity_to_force_vector` and giving it the option to skip the gravity add entirely. Plan now: do the simple add-only version, leave a TODO comment at the call site.
- **Bullets/particles.** Out of scope. The `particles_update_and_draw` per-particle path (line 5799 per the ideas doc) is the natural place to hook in later, but it's a separate cost: 32 particles × N wells × per-frame math is non-trivial. v2 only.
- **Pod.** Same story — pod physics has its own integrator; touching it is its own diff.
- **Centre case:** documented above, no special-case code needed thanks to per-axis sign multiplication.
- **Manhattan vs Euclidean asymmetry.** A well configured as r=40 reaches 40 px along axes but only ~28 px diagonally. Designers will need to know this; mention in the editor status bar tooltip.
- **Sign of strength.** Reserving negatives for repulsors means the first cut should clamp `strength >= 0` in the editor and assert positive in the runtime — keeps v1 honest.
- **`new_ship_xpos_INT` / `new_ship_ypos_INT` (`thrust.6502:303`/`319`)** are the right ship coords to read — they are the freshly integrated values used by the rest of the per-frame physics. Reading post-integration but pre-collision is correct.
