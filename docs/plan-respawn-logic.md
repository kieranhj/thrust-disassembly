# Plan: Last-used-checkpoint respawn

**Status:** done (commit `9038a8e`, `_LAST_USED_CHECKPOINT`). This doc describes the as-built design. The pod-direction scan and pickup-time snap in earlier drafts were not built (see §7).

The height-based checkpoint scan in `level_reset` is replaced by a "last used checkpoint" model. The motivating case: teleport into a disconnected sub-cavern, die there, and respawn back in the sub-cavern rather than at the nearest checkpoint above the death Y, which may be on the far side of a sealing band. See [plan-teleporter.md](plan-teleporter.md).

The original pod-carry anti-cheat is kept: with the pod attached, dying must not move the player closer to the surface than where they died.

SWRAM-only; the non-SWRAM CRC `6389c446` is unaffected.

## 1. Build flag and scope

- `_LAST_USED_CHECKPOINT = (_SWRAM_BUILD AND TRUE)` (`thrust.6502:44`).
- All new state, the per-frame tracker and the respawn changes are gated on it. The original `level_reset_loop` code is still assembled; under the flag it is bypassed by a `JMP`.

## 2. State

Two ZP bytes (`thrust.6502:509-510`), both above the `$01-$9A` range that `level_reset` clears, so they survive death:

| Address | Name | Meaning |
|---------|------|---------|
| `$AA` | `active_checkpoint_index` | Index into the level's checkpoint table (`level_N_reset_data`). Respawn position. |
| `$AB` | `deepest_checkpoint_visited` | High-watermark of `active_checkpoint_index` within the current segment. Caps the respawn-with-pod bump. |

There is no `$FF` "fall back to height scan" value; the index is always valid.

## 3. Initialisation

`initialise_level_pointers` sets both bytes to `INITIAL_CHECKPOINT` (`thrust.6502:54`, normally `$00`; raise it for test builds that spawn deeper). Every level, including demo levels, starts at checkpoint 0. The editor exports checkpoints sorted by ascending Y (§8), so checkpoint 0 is the topmost spawn point, matching the original first-life position.

## 4. Updating on teleport

`teleporter_perform_warp` writes the destination index to both `active_checkpoint_index` and `deepest_checkpoint_visited`, then `JMP level_retry`. Resetting the watermark matters: the player has only just arrived in the new segment, so the pod bump (§6) must not reach checkpoints beyond the destination.

## 5. Per-frame tracking: `update_active_checkpoint`

Called once per frame from the main tick loop, straight after `update_active_band` (`thrust.6502:9662`). Bidirectional and direction-agnostic: the pod state plays no part. It compares `midpoint_ypos_INT_HI/INT` with checkpoint Y (Y increases downward):

- **Retreat** while `midpoint_y < cp[active-1].y` (player above the previous checkpoint): `DEC active_checkpoint_index`.
- **Advance** while `midpoint_y > cp[active+1].y` (player below the next checkpoint): `INC active_checkpoint_index`, and raise `deepest_checkpoint_visited` if `active` now exceeds it.

Comparisons are strict, so standing exactly on a checkpoint's Y doesn't move `active`. The routine reloads `level_reset_size` and `level_reset_ptr` itself. Checkpoint counts are single digits and usually zero or one step fires, so the cost is small.

## 6. `level_reset` changes

At the start of the old matching loop (`thrust.6502:6964`):

```
IF _LAST_USED_CHECKPOINT
        LDY     active_checkpoint_index
        JMP     active_checkpoint_loaded
ENDIF
    .level_reset_loop
        ...                                   ; original height scan + pod flip, now bypassed
    .active_checkpoint_loaded
```

Between `active_checkpoint_loaded` and the unchanged position-load block, a gated respawn-with-pod rule runs when `level_reset_with_pod_flag` is set (`attach_pod_to_ship` sets it). `midpoint_ypos` at this point is the death Y, saved and restored around the ZP clear:

1. **Bump.** If `cp[active].y` is above the death Y (respawning there would let the player gain height by dying), set `Y = min(active + 1, deepest_checkpoint_visited)`. Otherwise keep `Y = active`.
2. **Drop.** If the final `Y == deepest_checkpoint_visited`, clear `level_reset_with_pod_flag`: the pod is lost and stays at its stand.

Phase 2 is the original game's "respawn at the bottom checkpoint drops the pod" rule, applied to the segment's watermark rather than `cp[size-1]`. `active_checkpoint_index` is not changed by the bump.

The position-load block (from `CLC` after `active_cp_pod_done`) then writes `midpoint_ypos_INT_HI`, `midpoint_ypos_INT`, `window_xpos_INT`, `window_ypos_EXT`, `window_ypos_INT` and `midpoint_xpos_INT` from the checkpoint table, unchanged from the original.

## 7. Design notes (differences from earlier drafts)

- **No pod-direction scan.** Drafts made the per-frame advance depend on the pod flags (downward without pod, upward with). Bidirectional tracking plus the respawn-time rule covers both cases.
- **No pod-pickup snap.** Not needed; `active` is never changed at pickup.
- **Watermark, not an unconditional bump.** An unconditional `active+1` bump breaks across teleporters, because `cp[active+1]` may sit in a cavern the player has never visited. Capping at `deepest_checkpoint_visited`, which resets on teleport, prevents that.
- **Drop rule applies whether or not the bump fired.**

## 8. Editor implications

- `export_beebasm` sorts each level's checkpoints by ascending `spawn_y` before emitting `level_N_reset_data`, so checkpoint 0 is the topmost spawn point. Commit `ac68192`.
- Teleporter destinations (`obj_data_0` of type `$10` objects) are remapped through the same permutation (`remap_teleport_dest`).
- In-editor order is not changed; the sort applies only to the exported bytes and is deterministic, so repeated saves are byte-identical. The original six levels were already in ascending-Y order.

Open: warn on export if checkpoint 0 sits inside a disconnected cavern (the first life would spawn somewhere unreachable).

## 9. Demo and `level_retry`

`level_retry` (death, teleport) calls `level_reset`, which now reads `active_checkpoint_index`. The demo starts each level at checkpoint 0, as before. The stack reset before `JMP level_retry` in the teleporter is unchanged.

## 10. Risks

- **Per-frame scan cost.** The tracker only steps from the current index, so it stays cheap as checkpoint counts grow; the worst case is a long retreat/advance after a big Y jump.
- **Demo divergence.** A demo whose deaths relied on the height-based scan could respawn somewhere different.
- **Lifetime of the state.** The two bytes survive death by design and are reset at every level start (`initialise_level_pointers`), which also covers game-over and new game.
