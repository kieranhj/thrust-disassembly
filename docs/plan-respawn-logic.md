# Plan: Last-used-checkpoint respawn

Replace the height-based checkpoint scan in `level_reset` with a "last used checkpoint" model, so that teleporting into a disconnected sub-cavern and dying inside it respawns the player back at the teleporter's destination rather than at the nearest checkpoint above the death Y (which may sit on the wrong side of a divider band).

Preserve the existing pod-carry anti-cheat: when the pod is held, the player is climbing toward the surface and respawn must not jump them upward past where they died.

SWRAM-only behind a new build flag; non-SWRAM canonical CRC `6389c446` stays anchored.

## 1. Build flag and scope

- Add `_LAST_USED_CHECKPOINT = (_SWRAM_BUILD AND TRUE)` alongside the other feature flags near `thrust.6502:42`.
- All new state and the rewritten matching loop are gated on this flag. Original `level_reset` body remains intact for the non-SWRAM build.

## 2. New ZP state

One byte:

- `active_checkpoint_index` — index into the current level's checkpoint table (`level_N_reset_data`). `$FF` = "no active checkpoint, fall back to height-based scan" (used on the very first life of a level before the player has done anything).

Allocate from the existing ZP free-list near the other gameplay-state bytes (around `$22`–`$30`). One byte fits trivially.

## 3. Initialisation

- On level start (`initialise_level_pointers` or wherever existing per-level state is reset), set `active_checkpoint_index = $00`.
- New levels always start at checkpoint 0 — no height-based first-life fallback. The editor sorts checkpoints by ascending Y on export (see §9), so checkpoint 0 is always the topmost spawn point, which matches the historical first-life position for the existing 6 levels.

## 4. Updating on teleport

In `teleporter_perform_warp` (the existing teleport→`level_retry` path):

- Replace the current `midpoint_ypos` pre-nudge that "spoofs" the matching loop with a direct write: `active_checkpoint_index = teleporter_dest_save`.
- The rewritten `level_reset` matching loop (§6) reads the active index directly, so no midpoint nudge is needed and the destination checkpoint is unambiguous.

This also makes teleport destinations robust against future checkpoint reordering — the per-level checkpoint table indexing is already stable across edits.

## 5. Updating during play (advancing through checkpoints)

The current engine has **no concept** of "passing through" a checkpoint — checkpoints are purely respawn anchors, not gameplay markers. Add a per-frame check in the player update path (somewhere near where `midpoint_ypos` is integrated, or in `update_active_band`'s neighbourhood since it already scans Y thresholds):

- Once per frame, compare `midpoint_ypos` against each checkpoint's Y in the current level's table.
- If the player has moved past a checkpoint that is *further along the intended direction of travel* than the active checkpoint, set `active_checkpoint_index` to that checkpoint.
- "Direction of travel" is governed by `pod_lifted_flag` (or `pod_tethered_flag`):
  - **No pod:** intended direction is downward. Adopt a checkpoint when `midpoint_ypos > checkpoint_y` AND the checkpoint is below the current active checkpoint.
  - **Pod held:** intended direction is upward. Adopt a checkpoint when `midpoint_ypos < checkpoint_y` AND the checkpoint is above the current active checkpoint.

Cost is small — checkpoint counts per level are in the single digits — but the per-frame scan can be cheapened if needed by only re-scanning when `midpoint_ypos` crosses a 256-row boundary, or by maintaining a sorted index pointer that only advances.

## 6. Rewriting level_reset's matching loop

Replace the current height-based scan (`level_reset_loop` at `thrust.6502:6894`) with a direct lookup:

```
IF _LAST_USED_CHECKPOINT
    LDY     active_checkpoint_index
    \\ Fall through into the existing position-load block (Y already set).
ENDIF
```

The position-load block (lines 6925–6957) stays unchanged — it just needs Y = active checkpoint index on entry. The old height-based scan and the pod-flag direction flip inside it (`level_reset_loop` and the `level_reset_with_pod_flag` adjustments at 6905–6923) are removed entirely under this flag, because every death now consults `active_checkpoint_index` directly. The pod-carry anti-cheat is preserved through the per-frame advance scan (§5) and the pickup-time snap (§7), not in `level_reset` itself.

## 7. Pod pickup and drop interactions

Pod pickup at a checkpoint mid-cavern:

- When `pod_lifted_flag` transitions from $00 → $FF, the active checkpoint is whichever the player most recently advanced to under no-pod direction-of-travel. That's the right anchor for "where I started carrying the pod from" in most cases.
- Optionally: on pod pickup, force a re-scan and snap `active_checkpoint_index` to the closest checkpoint *below* the pickup Y (the anti-cheat anchor). This guarantees that dying with the pod respawns at or below the pickup point, which is what the original height-based-with-flip logic achieved.

Pod destroyed (player drops it / it explodes):

- `pod_lifted_flag` returns to $00. Direction of travel flips back to "downward". Subsequent §5 advances apply normally. No special handling needed at the moment of drop.

## 8. Demo and `level_retry` interactions

- `level_retry` (called from teleport, level start, and the demo entry path) goes through `level_reset`, which now consults `active_checkpoint_index`. Demo flow: `active_checkpoint_index` is initialised to $00 on level/demo start so the demo's first life lands at checkpoint 0 — the topmost checkpoint, which matches existing demo behaviour for the original 6 levels.
- Stack reset before `JMP level_retry` is unchanged.

## 9. Editor implications

The export pipeline must guarantee that **checkpoint 0 is the topmost spawn point** in every level, since the engine now starts every life at index 0:

- **Sort-on-export:** in `export_beebasm`, sort each level's `checkpoints` list by ascending `spawn_y` before emitting the `level_N_reset_data` table. This is a simple `sorted(cps, key=lambda c: c["spawn_y"])`.
- **Remap teleporter destinations:** any teleporter object whose `obj_data_0` references a checkpoint index must be rewritten under the sort permutation, otherwise the teleporter would warp to the wrong checkpoint after sorting. Build an `old_index → new_index` mapping during the sort and apply it to every type-`$10` object's `obj_data_0` on export.
- **In-editor state stays untouched** during the session (sort applies only at export time). Re-importing the saved file picks up the sorted order and indices stay consistent across save/reload cycles. The sort is deterministic so repeated saves produce byte-identical output.

Verify the existing 6 levels still round-trip byte-identically — they should, since their checkpoints are already authored in ascending-Y order.

Optional follow-up:

- **Validation:** warn if checkpoint 0 ends up inside a disconnected cavern (i.e. below a divider band) — the player would spawn somewhere they can't normally reach, breaking the level.

## 10. Risks

- **Per-frame scan cost.** Single-digit checkpoint counts means the scan is cheap, but if checkpoint counts grow (e.g. with Metroidvania-scale levels) the cost matters. Mitigation: maintain a sorted pointer that only advances in the direction of travel, so the scan is O(1) amortised.
- **Pod pickup snap discontinuity.** If the pickup-time snap to "closest below" (§7) lands on a different checkpoint than the player would expect, the first death after pickup could feel surprising. Worth play-testing before committing to the snap behaviour vs. just leaving the active checkpoint where it was at pickup.
- **Demo recordings.** If any demo data implicitly relies on the height-based fallback firing on every death, the demo will diverge. Initial state (`active_checkpoint_index = $FF` on level start, fallback-then-cache on first death) should preserve original behaviour for the first death of each demo segment, which is likely all that matters.
- **Save state across lives.** `active_checkpoint_index` is intentionally **not** cleared on death — that's the whole point. But it should reset on level transition and on game-over → new game.

## 11. Implementation order

1. Add `_LAST_USED_CHECKPOINT` flag, `active_checkpoint_index` ZP byte, init to $FF on level start. No behavioural change yet.
2. Add the per-frame checkpoint-advance scan (§5), with debug print or temp screen-edge dump to verify it's tracking the right index in play.
3. Replace `level_reset_loop` with the active-index lookup (§6), keeping the height-based scan as fallback when index = $FF. End of fallback path writes back to the index. Test: dying in a normal level should respawn at the same checkpoint as before (height-based path runs, then caches).
4. Add the pod pickup snap (§7) — verify the pod-carry anti-cheat still holds.
5. Wire the teleporter warp to write `active_checkpoint_index` directly (§4) and drop the midpoint nudge.
6. Build a test level with a divider band and a sub-cavern containing one checkpoint; verify dying inside the sub-cavern respawns inside it, and dying in the hub respawns in the hub.
7. Document in `ideas.md` "Completed" once shipped; cross off the disconnected-caverns respawn follow-up.
