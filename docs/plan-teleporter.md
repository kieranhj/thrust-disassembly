# Plan: Teleporter object (one-way, checkpoint destination)

**Status:** done (commit `aa602ec`, updated by `9038a8e` for last-used-checkpoint respawn and `215938f` for `OBJ_flag_disabled`). This doc describes the as-built design; §10 lists what is still open.

A placeable pad that warps the player to one of the level's **checkpoints** when the ship overlaps it. One-way: the destination is a checkpoint index, not another pad. The warp reuses the death-respawn path (`level_retry`) for the position write, screen rebuild and teleport-in animation, and the gravity-well debris emitter for the in-world indicator.

SWRAM-only behind `_TELEPORTER` (`thrust.6502:43`); the non-SWRAM CRC `6389c446` is unaffected. Requires `_GRAVITY_WELL` (the debris emitter lives in that block) and works with `_LAST_USED_CHECKPOINT` (see [plan-respawn-logic.md](plan-respawn-logic.md)).

## 1. Build flag and object type

- `_TELEPORTER = (_SWRAM_BUILD AND TRUE)`.
- `OBJECT_teleporter = $10`, the slot after the bobbing-mine pair `$0E`/`$0F`. (`$11` is `OBJECT_door`, see [plan-switches-and-triggers.md](plan-switches-and-triggers.md).)
- `IF _TELEPORTER` entries in the per-type tables: `obj_type_width` `$03`, `obj_type_height` `$08` (both placeholders), `obj_type_explosion_particle` `$00`, `obj_type_score_value` `$00`, `object_type_cull_size_table` `$44`.

The pad is handled in `update_and_draw_all_objects` *before* the `OBJ_flag_alive` test, sprite selection and bullet collision, then jumps to `next_object`. Consequences:

- It is never sprite-plotted (a sprite would trip the ship's pixel collision), never shootable, and never lethal.
- `set_alive` / `clear_alive` have no effect on a pad. Use the `OBJ_flag_disabled` actions to switch it off (§9).

## 2. Per-instance data layout

Uses the generic obj_data slots; no new export arrays.

| Slot | Field |
|------|-------|
| `obj_data_0` | Destination checkpoint index (0-based, into the level's `level_N_reset_data` table, which the editor exports sorted by ascending Y) |
| `obj_data_1` | Unused (`$00`) |
| `obj_data_2` | Unused (`$00`) |

## 3. Trigger: ship overlaps pad

In the per-object loop (`thrust.6502:1698`):

```
        LDY     object_type
        CPY     #OBJECT_teleporter
        BNE     not_teleporter
        JSR     teleporter_emit_debris
        JSR     teleporter_check_ship_contact
        JMP     next_object
```

`teleporter_emit_debris` always loads the pad's world position (via SMC on `level_N_obj_pos_X/Y/Y_EXT`, patched in `initialise_level_pointers`) into `well_obj_x_save` / `well_obj_y_lo_save` / `well_obj_y_hi_save`, offset by `TELEPORTER_CENTRE_X_OFFSET = $02` chars and `TELEPORTER_CENTRE_Y_OFFSET = $04` rows so the trigger and fountain sit over the visible ship rather than the sprite top-left. `teleporter_check_ship_contact` reads the same slots.

`teleporter_check_ship_contact` bails if any of these hold:

- the pad has `OBJ_flag_disabled` set;
- `pod_tethered_flag` or `pod_lifted_flag` is non-zero (pod guard, §5);
- `|pad_y - player_ypos| >= 8` pixels (16-bit compare);
- `|pad_x - player_xpos_INT| >= 5` chars.

On geometric overlap it sets `teleporter_overlap_this_frame = $FF`. If `teleporter_just_warped` and `teleporter_pending_index` are both zero, it latches `teleporter_pending_index = obj_data_0 + 1` (0 = idle).

Re-trigger suppression: `teleporter_dispatch_pending` copies `teleporter_overlap_this_frame` into `teleporter_just_warped` at the end of each frame, then clears it. A ship sitting on a pad therefore latches once and won't re-arm until it has left the box for a frame.

## 4. Warp execution

`end_of_objects_function` calls `teleporter_dispatch_pending` after `update_all_laser_beams`. If a warp is pending it calls `teleporter_perform_warp` with A = destination index. That routine:

1. Saves the index in `teleporter_dest_save`; clears `teleporter_pending_index` and `teleporter_overlap_this_frame`; sets `teleporter_just_warped = $FF`. This must happen up front because the routine never returns.
2. Loads `level_reset_data_sizes,X` into `level_reset_size`; returns without warping if the level has no checkpoints.
3. Clamps an out-of-range destination to `0`, then writes it to **both** `active_checkpoint_index` and `deepest_checkpoint_visited` (§6).
4. Clears `level_reset_with_pod_flag`.
5. Plays `enter_orbit_sound`, then `player_teleport` with `teleport_appear_or_disappear = $FF` (disappear animation at the source).
6. Resets the stack (`LDX #$FF : TXS`) because it is several JSRs deep, then `JMP level_retry`.

`level_retry` runs `level_reset` and falls through into `level_start_demo_entry`, exactly as after a death: screen clear, ZP game vars `$01-$9A` cleared (velocity, pod flags, etc.), respawn at `active_checkpoint_index`, `update_active_band` re-run at the spawn point (under `_Y_BANDS`), teleport-in animation. The warp skips the death path, so no life is lost.

Not reset: object state (`level_obj_flags`, positions, door/switch state), score, fuel.

## 5. Pod handling

The pad refuses to fire while the pod is tethered or lifted. This avoids teleporting the tether. `level_reset_with_pod_flag` is cleared anyway so the respawn can't re-attach a pod.

## 6. Interaction with last-used-checkpoint respawn

The original commit nudged `midpoint_ypos` so the height-based scan in `level_reset` landed on the destination. Under `_LAST_USED_CHECKPOINT` the warp writes the destination straight into `active_checkpoint_index`, and `level_reset` loads that index directly. It also resets the `deepest_checkpoint_visited` watermark to the destination. The player has only just arrived in the new segment, so the respawn-with-pod bump can never point at a checkpoint they haven't reached on foot. A later death inside a sealed sub-cavern therefore respawns at the pad's destination (or a checkpoint passed since), not at the nearest checkpoint above the death Y.

## 7. Visual indicator: debris fountain

`teleporter_emit_debris` emits on `(level_tick_counter EOR current_object) AND TELEPORTER_DEBRIS_SPAWN_MASK == 0` (`$03`: one particle every 4 ticks per pad, jittered per pad). It sets `well_radius_save = TELEPORTER_DEBRIS_RADIUS ($08)` and `well_strength_save = TELEPORTER_DEBRIS_STRENGTH ($80)`. The negative strength selects the repulsor branch, so particles spawn at the centre and fly outward. It then tail-calls `well_emit_debris_particle`.

An outward fountain reads as "active gate" without suggesting a pull, which would be confused with a gravity well. Pads emit when off-screen too (no visibility gate), as gravity wells do.

The emitter runs even when the pad is disabled; only the trigger is suppressed.

## 8. Sprite

The pad has no in-game sprite; the debris fountain is its only visual. `tools/sprite_codec.py` registers `teleporter` (3 chars wide) to keep the sprite table aligned, but the engine never plots it.

## 9. Editor support (`tools/level_editor.py`)

- `OBJECT_TELEPORTER = 0x10`, placed in normal object mode. The palette tile shows a pictogram (`51ede73`); the canvas draws a cyan ring + centre dot.
- Per-object field `teleport_dest` (inspector `SCHEMA_TELEPORTER`: a `ref` field with `target_kind="checkpoint"`, so it can be picked on the canvas). Exported to `obj_data_0`; slots 1/2 export as `0`. Imported from slot 0.
- `[` / `]` cycle `teleport_dest` through the level's checkpoints (wraps; no-op if the level has none).
- When a pad is selected, a cyan line with an arrowhead runs from the pad to the destination checkpoint's spawn point, which is circled.
- On export, checkpoints are sorted by ascending `spawn_y`, and every pad's `teleport_dest` is remapped through the sort permutation (`remap_teleport_dest`). An out-of-range index is wrapped modulo the checkpoint count; there is no warning.
- `tools/visualise_levels.py`: `0x10` "Teleporter", marker `("o", "cyan")`.
- Switch wiring can target a pad with `set_disabled` / `clear_disabled` / `toggle_disabled` ($08-$0A), which gives switch-gated pads with no extra work.

## 10. Risks and open items

- **Pod constraint.** Pads ignore the ship while the pod is tethered or carried. A pod-aware warp would need the tether re-established at the destination.
- **AABB thresholds** (`|dx| < 5` chars, `|dy| < 8` px, centre offset `+2`/`+4`) were tuned by feel and may need revisiting.
- **No checkpoints on the level.** The editor doesn't stop you placing a pad; the engine just doesn't warp.
- **Out-of-range destinations** wrap silently in the exporter and clamp to 0 in the engine. A warning on export would be better.
- **Editor "go to destination"** (pan the camera to the destination on `Enter`) was planned but not built. [ideas.md](ideas.md#disconnected-caverns) still refers to it.

Possible follow-ups:

- **Two-way pads.** Already expressible as two one-way pads pointing at each other's checkpoints.
- **Pad-to-pad destinations.** Destination is another pad's position rather than a checkpoint; slot 0 becomes an object index with a flag bit.
- **Cooldown / single-use** in slot 1.
- **Pod-aware warp** (above).
