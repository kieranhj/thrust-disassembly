# Plan: Teleporter object (one-way, checkpoint destination)

A new placeable object that warps the player to an existing level **checkpoint** when the ship overlaps the pad. One-way only: the destination is a checkpoint index, not another teleporter. Reuses the level-respawn machinery for the actual position write, the existing teleport-out/in animation for the visual, and the gravity-well debris emitter for an in-world location indicator.

SWRAM-only behind a new build flag; non-SWRAM canonical CRC `6389c446` stays anchored.

## 1. Build flag and object type

- Add `_TELEPORTER = (_SWRAM_BUILD AND TRUE)` alongside the other feature flags near `thrust.6502:42`.
- Allocate `OBJECT_teleporter = $10` (next free slot after the bobbing-mine pair `$0E`/`$0F`).
- Add `IF _TELEPORTER`-gated entries in the per-type parallel tables (same locations as bobbing mines):
  - `obj_type_width` / `obj_type_height` — sized to the visual footprint (see §6).
  - `obj_type_explosion_particle` — irrelevant (teleporters are non-destructible) but keep table aligned with a placeholder.
  - `obj_type_score_value` — `$00`.
  - `object_type_cull_size_table` — sized so a slightly off-screen pad still ticks its debris emitter.
  - `obj_sprite_data_A_table_LO/HI` and `_B_*` — point at the placeholder sprite (see §6).

The teleporter is **not** in the bullet-destructible whitelist and **not** in the ship-pixel-collision lethal set: shooting it does nothing, and brushing it triggers the warp instead of killing the player.

## 2. Per-instance data layout

Reuses the existing generic obj_data slot mechanism — no new export arrays.

| Slot | Field |
|------|-------|
| `obj_data_0` | Destination checkpoint index (0-based; into the level's `level_N_reset_data` table) |
| `obj_data_1` | Reserved (`$00`) — leaves room for cooldown frames / one-shot flag later |
| `obj_data_2` | Reserved (`$00`) — leaves room for a "with-pod" flag or visual variant later |

Slot 0 is small (a level has at most a handful of checkpoints) — single byte is plenty. Slots 1/2 are deliberately left unused so we have headroom for the variants in §10 without another data layout migration.

## 3. Trigger: ship overlaps pad

Hook in **`check_planet_explode_trigger`**, alongside the existing bobbing-mine ship-contact AABB. Order in that routine:

1. Bobbing-mine AABB (existing) — kills both.
2. Teleporter AABB (new) — fires warp.
3. Existing planet-explode test (default fall-through).

The AABB uses the same shape as the mine test — `|dx|` in chars vs object width sum, `|dy|` in pixels vs object height sum, with X char-granularity acknowledged. A pad sized 3×8 against ship ~2×10 gives `|dx| < 5` chars / `|dy| < 9` px as a starting point; tune by feel like the mine thresholds were.

When the AABB fires:

- Set a one-shot **`teleporter_pending_index`** zp scratch byte = `obj_data_0[X] + 1` (`+1` so `0 = idle`, `1+ = pending checkpoint N-1`).
- Do **not** call the warp routine inline — the trigger runs deep inside `update_and_draw_all_objects` and the warp wants a clean per-frame state. Defer to the end of the main tick.
- Clear `pod_lifted_flag` / `pod_tethered_flag` before the warp **only if** we adopt the v1 simplification of dropping the pod (see §5).

A second flag, **`teleporter_just_warped`**, suppresses re-trigger while the ship is still overlapping the destination pad (if a checkpoint happens to sit near another pad). Cleared once the AABB stops firing for one frame.

## 4. Warp execution: reuse `player_teleport` + checkpoint write

The actual warp runs once, at the end of the current frame's update loop (after `update_and_draw_all_objects` returns, before `draw_player_timed_to_vsync`).

```
IF _TELEPORTER
        LDA     teleporter_pending_index
        BEQ     no_teleport_pending
        SEC
        SBC     #$01                       ; convert back to 0-based checkpoint idx
        JSR     teleporter_warp_to_checkpoint
        LDA     #$00
        STA     teleporter_pending_index
        LDA     #$FF
        STA     teleporter_just_warped
.no_teleport_pending
ENDIF
```

`teleporter_warp_to_checkpoint` does, in order:

1. **Teleport-out animation at the current position.** Reuse `player_teleport` with `teleport_appear_or_disappear = $FF` (disappear). The existing routine snapshots and restores `pod_line_exists_flag` / `plot_ship_collision_detected` / `pod_tethered_flag` itself, so the world stays intact.
2. **Write checkpoint position into ship/window state.** Mirror lines 6896-6922 of `level_reset_loop` exactly — the same six writes (`midpoint_ypos_INT_HI`, `midpoint_ypos_INT`, `window_xpos_INT`, `window_ypos_EXT`, `window_ypos_INT`, `midpoint_xpos_INT`), reading from `(level_reset_ptr),Y` with `Y` derived from the destination index and `level_reset_size`. Refactor the byte-grab block out of `level_reset_loop` into a shared helper `write_checkpoint_position_in_Y`; both call sites use it.
3. **Re-run band gravity scan** (`IF _Y_BANDS`) — same as the post-respawn block at 6927-6939 — so warping into a band-overridden region updates `gravity_FRAC` / `gravity_SIGN` cleanly.
4. **Teleport-in animation at the new position.** Call `player_teleport` again with `teleport_appear_or_disappear = $00` (appear).
5. Clear ship velocity (`vel_x = vel_y = 0`) so the player doesn't carry pre-warp momentum into the destination — keeps the warp deterministic.

Things deliberately **not** reset: object positions, particles, pod state (subject to §5), score, fuel. Level state continues from where it was.

### Pod handling (v1)

Simplest first cut: **the pad refuses to fire while the ship is carrying or tethered to the pod.** AABB hit + (`pod_lifted_flag != 0` OR `pod_tethered_flag != 0`) → ignore. This dodges all the questions about teleporting the tether, re-establishing it on the far side, or what happens to the pod's screen-space position. Level designers route around it. Revisit later if it feels too restrictive.

## 5. Visual indicator: gravity-well debris emitter, repulsor mode

Reuse `well_emit_debris_particle` directly. Hook the emit inside `update_and_draw_all_objects` for `OBJECT_teleporter`, after the per-type early-exit dispatch:

```
IF _TELEPORTER
        LDA     object_type
        CMP     #OBJECT_teleporter
        BNE     not_teleporter
        \\ Per-pad emit gate, jittered by current_object so multiple
        \\ pads don't all emit on the same frame.
        LDA     level_tick_counter
        EOR     current_object
        AND     #TELEPORTER_DEBRIS_SPAWN_MASK
        BNE     teleporter_emit_skip
        \\ Force "repulsor" mode — particles fly outward from centre.
        \\ well_emit_debris_particle reads strength sign; we set up
        \\ scratch bytes so it sees a synthetic well at the pad's
        \\ position with a small fixed radius and negative strength.
        JSR     teleporter_emit_debris
.teleporter_emit_skip
        JMP     next_object                  ; pads have no other update
.not_teleporter
ENDIF
```

`teleporter_emit_debris` is a thin wrapper that:

- Stores the pad's `current_obj_xpos_INT` / `current_obj_ypos_INT(_EXT)` into the well centre scratch slots that `well_emit_debris_particle` reads.
- Loads a fixed `TELEPORTER_RADIUS` (e.g. `$08` chars) into the well-radius scratch slot.
- Loads a fixed negative `TELEPORTER_STRENGTH` (any value with bit 7 set) so the existing repulsor branch fires — particles spawn at the centre and fly outward.
- Calls `well_emit_debris_particle`.

Why repulsor mode rather than pull-in: an outward debris fountain reads as "this is an active warp gate" without implying "this object pulls the ship." Pulls would be visually confusable with a gravity well.

If sharing scratch slots with the gravity well emitter turns out awkward (timing or interleaving), the alternative is to copy the relevant ~30 lines of `well_emit_debris_particle` into a dedicated `teleporter_emit` and inline the centre/radius/strength constants. Cheap either way.

## 6. Sprite

The debris emitter does most of the visual work. The pad still needs *something* drawable so it has a footprint for the AABB and so the editor can hit-test it.

- Small "ring" sprite: 12×8 (3 chars × 8 rows), drawn in colour 3. Two horizontal bars top and bottom plus a centre dot — reads as a pad/gate. Same sprite shared by all pads.
- Built via `tools/sprite_codec.py` / `tools/sprite_editor.py` exactly like the bobbing-mine sprite was. Add `OBJECT_teleporter` to `OBJECT_NAMES` and `OBJECT_WIDTH_CHARS` in the codec; regenerate `tools/output/object_sprites.asm`.
- Ship-vs-pixel collision against the pad pixels does **not** kill — the AABB in §3 fires first and ends the frame with the ship at the new position. To be safe, also skip the lethal pixel test for teleporter pads in `check_planet_explode_trigger` (same shape as the existing gravity-well skip).

## 7. Editor support (`tools/level_editor.py`)

The editor already has a checkpoint mode and renders the level's checkpoints with handles. Teleporter wiring leans on that.

- Register `OBJECT_TELEPORTER = 0x10` in the type tables (`OBJECT_TYPE_NAMES`, `BOBBING_MINE_TYPES`-style sets if needed for special cases, `OBJECT_WIDTH_CHARS`).
- `tools/visualise_levels.py`: add `0x10` "Teleporter" with a distinct marker (e.g. `"o"`, `"cyan"`).
- Per-pad object dict field: `teleport_dest_index` (int, 0..len(checkpoints)-1). Packed into obj_data slot 0 on export; slots 1/2 export as `0`. Imported back from slot 0.
- Place teleporter pads in normal object mode like any other object type.
- **Wiring UI:** when a teleporter pad is selected, draw a thin coloured line from the pad's screen position to the destination checkpoint's spawn position (same UX pattern proposed for switch wiring in `ideas.md`). The destination checkpoint is also highlighted while the pad is selected.
- Key bindings on a selected teleporter:
  - `[` / `]` — cycle `teleport_dest_index` through the level's checkpoints (wraps).
  - `Enter` (or another single key) — "go to destination": camera-pans to the destination checkpoint without changing selection, so the designer can sanity-check the target without losing the pad.
- Status bar shows `dest=#N` (and the checkpoint's world `(x, y)` if room).
- **Validation on export:** if a pad's `teleport_dest_index` is out of range for the level's current checkpoint count (e.g. designer deleted a checkpoint), clamp to `0` and emit a warning to stdout. Don't silently break.

No new editor mode — pads live in the existing object mode.

## 8. Asm scratch / RAM

- `teleporter_pending_index` — 1 byte zp (or low-RAM if zp is tight).
- `teleporter_just_warped` — 1 byte; cleared once the AABB stops firing.
- Both gated by `IF _TELEPORTER`.

No new export arrays. The synthetic-well scratch slots used by `teleporter_emit_debris` are the same slots the real well emitter uses; safe because the well walker has fully returned by the time `update_and_draw_all_objects` reaches a teleporter (different per-object dispatch branches, no interleaving).

## 9. Risks / open questions

- **Pod constraint feels restrictive.** v1 ignores AABB hits while carrying/tethered. If playtest suggests "I want to teleport with the pod," need a follow-up that either teleports the pod alongside or drops it cleanly. Out of scope for v1.
- **AABB threshold tuning.** Same playtest cycle as bobbing mines — initial `|dx| < 5` chars / `|dy| < 9` px is a starting point.
- **`level_reset_loop` refactor.** Extracting the position-write block to a shared helper touches a routine that's well outside the SWRAM-gated regions. Implementation must keep the helper itself gated (or the non-SWRAM build inlines the original block unchanged) so the canonical CRC stays anchored. Probably easiest: keep the original code path verbatim in `level_reset_loop` and have `teleporter_warp_to_checkpoint` use its **own** copy of the six-byte read sequence — duplication is ~25 bytes, not worth a refactor that risks the CRC.
- **Re-trigger after warp.** `teleporter_just_warped` covers the "destination checkpoint sits inside another pad" case; verify by placing two pads close together and warping between them.
- **Velocity zero on warp.** Decided to zero ship velocity to keep the warp clean. If that feels wrong (e.g. designer wants momentum-preserving "slingshots") it's a single-line change.
- **Off-screen pads.** The pad still emits debris when off-screen (the emitter doesn't gate on visibility). Cheap and harmless — particles spawned off-screen are clipped at draw time. Matches gravity-well behaviour.
- **Multiple pads pointing at the same checkpoint.** Fully supported; checkpoint index is just a number.
- **No checkpoints on the level.** Editor must prevent placing a teleporter on a level with zero checkpoints (or auto-create the implicit level-start checkpoint as index 0). Validate at place-time.

## 10. Possible follow-ups (not v1)

- **Two-way pads** = two one-way pads, each pointing at the other's checkpoint. Already expressible; just a designer convention.
- **Pad pairs that omit the explicit checkpoint** — pad A's destination is pad B's position rather than a checkpoint. Saves an editor step. Slot 0 becomes "destination object index" with a flag bit.
- **Cooldown frames** in slot 1, so a pad self-disables for N frames after firing. Useful for scripted single-use warps.
- **Switch-gated pads** — pad only fires when a particular switch (see [Configurable switches and triggers](ideas.md#configurable-switches-and-triggers)) is in a given state. Drops out for free once the switch system lands.
- **Pod-aware warp** — teleport the pod with the ship and re-establish the tether at the destination. Needs design work on what happens to the tether's geometry.

## Suggested implementation order

1. **Editor first:** add `OBJECT_TELEPORTER`, the dest-index field, key bindings, and the wiring line. Round-trip a placed pad through export/import. Visualises in `visualise_levels.py`. (No game-side behaviour yet — pad just sits there as a sprite.)
2. **Sprite + cull table entries:** wire up via `sprite_codec.py`; verify pad renders in-game.
3. **Debris emitter:** hook the per-frame emit using the gravity-well repulsor path. Verify particles fountain out of the pad in-game; tune `TELEPORTER_DEBRIS_SPAWN_MASK` if too sparse / dense.
4. **AABB trigger + deferred warp scaffolding:** AABB sets `teleporter_pending_index`; warp routine logs (e.g. flashes border colour) but doesn't move the ship yet. Verify the trigger fires once per overlap and not while still inside the pad.
5. **Checkpoint write + animations:** wire the actual position write and the two `player_teleport` calls. Verify both animations fire and the ship lands at the correct checkpoint.
6. **Pod guard:** ignore AABB hits while carrying/tethered.
7. **Tuning pass:** AABB thresholds, debris density, decide if velocity zeroing feels right.
8. **Mark done in `ideas.md` Completed section** with a note about pod-carry restriction and threshold tunability — same pattern as the bobbing-mine entry.
