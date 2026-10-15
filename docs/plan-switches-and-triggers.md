# Plan: Editor-driven switches and triggers

**Status:** done, with follow-ups open. The wiring table, dispatcher, refractory, multi-trigger, `destroy`, `set_param` / `xor_param`, the `OBJ_flag_disabled` actions, the generic door object with `pulse_door`, all three door shapes and the migration of the original game's three doors are built. Not built: the floor/ceiling switch types from the original MVP (§3), editor warnings for half-wired entries (§8.4), and the §10 follow-ups marked open. Commits `796aebf` (Phase A) through `f463104`.

A per-level **wiring table** lets any door switch fire one or more actions against any object on the level, authored entirely in the editor. Under `_SWITCHES` the hardcoded `level_3/4/5_door_logic` routines are no longer called: the original doors are now `OBJECT_door` instances wired with `pulse_door`.

Builds on the sketch in [`docs/ideas.md`](ideas.md#switches--triggers-follow-ups).

SWRAM-only behind `_SWITCHES` (`thrust.6502:45`). The non-SWRAM build still assembles and runs the legacy door routines, so the CRC `6389c446` is unaffected.

## 1. Scope

As built:

- Any switch can target any object on the level, with up to 8 wiring entries per level shared across all switches. A switch with several entries fires them all, in slot order, on one hit ("multi-trigger").
- Actions: `destroy`, `pulse_door`, `set_param`, `xor_param`, `set_disabled` / `clear_disabled` / `toggle_disabled`, plus the engine-only `set_alive` / `clear_alive` / `toggle_alive` (§5).
- Switches are the existing wall types `$07` / `$08`.
- The editor draws wiring lines from switch to targets.
- Switch hits from the player's bullets only.

Not in scope (see §10): hostile bullets triggering switches, predicates across switches ("fire only when all four are set"), cross-level wiring.

State is per level, not per life: wiring effects (destroyed or disabled targets, door state) persist across deaths, like destroyed guns in the original game, and reset at level start.

## 2. Build flag

- `_SWITCHES = (_SWRAM_BUILD AND TRUE)`.
- All new arrays, per-switch state, door state and the dispatcher are gated on it.
- `handle_door_switch` (`thrust.6502:1971`) calls the dispatcher before the legacy `door_switch_counter_A = $FF` latch (§7.1).
- `tick_door_logic` (`thrust.6502:3483`) still drains `door_switch_counter_A`, then `JMP tick_doors` instead of dispatching on `level_number` (§7.2).

## 3. Object types

| Type  | Name                | Role |
|-------|---------------------|------|
| `$07` | `door_switch_right` | switch (existing) |
| `$08` | `door_switch_left`  | switch (existing) |
| `$11` | `OBJECT_door`       | door (new, §10.1) |

The original MVP proposed ceiling/floor switches at `$12` / `$13`. They were not built: the bullet hit dispatch still matches only `$07` / `$08`, and the editor's wiring validation only accepts those types as switches.

## 4. Per-level wiring table

Five parallel byte arrays per level, indexed by wiring **slot** (0..7), emitted by the editor into `tools/output/thrust_levels_export2.asm`:

```
.level_N_switch_obj_indices   ; switch object index per slot, $FF terminator
        EQUB    $09,$09,$09,$09,$FF
.level_N_switch_target        ; target object index ($FF = no target)
        EQUB    $05,$02,$06,$04,$FF
.level_N_switch_action        ; action code (§5)
        EQUB    $0A,$04,$0A,$0A,$00
.level_N_switch_arg_a         ; action arg A
        EQUB    $00,$00,$00,$00,$00
.level_N_switch_arg_b         ; action arg B
        EQUB    $00,$00,$00,$00,$00
```

(Level 0's test wiring: switch 9 fires four entries.) The same switch index appears once per entry; entries are grouped by switch, sorted by switch index, and kept in the designer's order within a switch. Each array carries a terminator entry (`$FF` / `$FF` / `$00` / `$00` / `$00`).

Pointer tables `level_switch_{obj_indices,target,action,arg_a,arg_b}_lookup_LO/HI` (`thrust.6502:11053`) are SMC-patched into the dispatcher's `LDA abs,Y` sites in `initialise_level_pointers`.

## 5. Action codes

Dispatched through `action_jump_table` (`thrust.6502:12586`), 16 entries of (LO, HI), indexed by `action × 2`. On entry `X` = target object index and `action_arg_a` / `action_arg_b` are preloaded.

| Code  | Name              | Editor | Effect |
|-------|-------------------|--------|--------|
| `$00` | `none`            | yes | No-op. Entry is skipped. |
| `$01` | `set_alive`       | hidden | Set `OBJ_flag_alive`. |
| `$02` | `clear_alive`     | hidden | Clear `OBJ_flag_alive` (object vanishes). |
| `$03` | `toggle_alive`    | hidden | XOR `OBJ_flag_alive` (can revive a destroyed object). |
| `$04` | `destroy`         | yes | If alive: clear alive, award `obj_type_score_value`, spawn explosion at the target. No-op if already dead. |
| `$05` | `pulse_door`      | yes | Open/hold/close cycle on a door (§10.1). arg_a = hold frames, arg_b = close rate. |
| `$06` | `set_param`       | yes | `obj_data_<arg_a>[X] = arg_b`. |
| `$07` | `xor_param`       | yes | `obj_data_<arg_a>[X] ^= arg_b`. |
| `$08` | `set_disabled`    | yes | Set `OBJ_flag_disabled`. |
| `$09` | `clear_disabled`  | yes | Clear `OBJ_flag_disabled`. |
| `$0A` | `toggle_disabled` | yes | XOR `OBJ_flag_disabled`. |
| `$0B`-`$0F` | reserved    | — | Point at `action_none`. |

`destroy` doesn't go through `destroy_object`. `action_destroy` has its own SMC reads of the target's position and type so it leaves `current_object` and `current_obj_*pos` intact for the bullet loop that called it.

`set_param` / `xor_param` ignore `arg_a >= 3` and set `OBJ_flag_laser_redraw_pending` on the target so a laser's beam is erased at its old endpoint before being redrawn (`d6b79c9`).

The alive trio stays in the engine for compatibility but is hidden in the editor (`215938f`). It overlaps `destroy` and the disabled trio and makes objects vanish rather than go dormant, because `OBJ_flag_alive` gates both drawing and behaviour.

## 6. Per-switch refractory

`level_switch_state` (`thrust.6502:11141`): 8 bytes, one per wiring slot. `0` = idle; non-zero = refractory countdown.

- On a hit, the dispatcher checks the state of the **first** matching slot only. If it is non-zero the whole batch is skipped (the hit is still consumed). This stops a rapid double shot from half-firing a multi-entry switch.
- Each matching slot is set to `$14` (20 frames, about 0.6 s at the ~33 Hz game frame rate) before its action runs.
- `tick_switch_logic` decrements all 8 bytes once per frame. It is called from the main loop right after `tick_door_logic`.
- Cleared at level start in `initialise_level_pointers`, not on death.

The banner comment above the dispatcher still says "8 frames"; the value was raised to 20 in `d6b79c9`.

## 7. Engine changes

### 7.1 Switch hit handler with legacy fallback

The bullet loop (`thrust.6502:1929`) tests player bullet slots 3..0 against each live object. On a hit against a `$07` / `$08`, `handle_door_switch` calls `try_dispatch_switch_action`:

1. Walk `level_N_switch_obj_indices` from slot 0 until `$FF`, looking for `current_object`.
2. On the first match, check refractory (§6).
3. For each match: set refractory, skip the entry if `target = $FF` or `action = $00`, else load arg_a/arg_b and `JSR` through the jump table. The slot index lives in `tdsa_save_y` across the call because `action_destroy` clobbers Y.
4. Return carry clear if any slot matched (hit consumed, legacy latch skipped), carry set if none (fall through to `door_switch_counter_A = $FF`).

`spawn_hit_debris` runs in both cases.

### 7.2 Per-frame work

- `tick_switch_logic`: 8 decrements.
- `tick_doors`: walks the object type list and calls `door_update_one` for each `OBJECT_door`, which advances its state machine (`door_advance_anim`) and writes its carve into `terrain_left_wall` / `terrain_right_wall` every frame, open or closed (§10.1).

Under `_SWITCHES` the legacy `level_3/4/5_door_logic` routines stay assembled but unreachable.

### 7.3 Level-start setup

`initialise_level_pointers`:

- patches the five wiring SMC sites (§4) and the per-type SMC sites used by `action_destroy`, the param actions and the door code;
- zeroes `level_switch_state` and the five door state arrays;
- after the original loop that sets `OBJ_flag_alive` on every object, clears alive on every `OBJECT_door` so doors start idle rather than mid-cycle.

### 7.4 Memory cost

- Wiring: 5 arrays × (entries + 1), at most 45 bytes per level.
- Pointer tables: 5 × 12 bytes = 60 bytes.
- `level_switch_state`: 8 bytes. Action jump table: 32 bytes.
- Door state: 5 arrays × 32 bytes = 160 bytes, plus 14 scratch bytes.

## 8. Editor changes

### 8.1 Switch types

No new switch sprites. `SCHEMA_DOOR_SWITCH` exposes X, Y and a Side enum (`$07` / `$08`).

### 8.2 Per-switch UI

Selecting a switch shows a list of wiring entries in the inspector. Each entry has:

- `Action` (enum from `SWITCH_ACTION_VALUES`: none / destroy / pulse_door / set_param / xor_param / set_disabled / clear_disabled / toggle_disabled);
- `Target` (`ref` field, `target_kind="object"`: click an object on the canvas). Self-targeting is allowed;
- for `set_param` / `xor_param`, Slot and Value/Mask fields, with Slot labels drawn from `SWITCH_SLOT_LABELS` for the target's type (e.g. "Beam dx" for lasers, "Dest checkpoint" for teleporters);
- for `pulse_door`, arg fields labelled "Hold frames" / "Close rate";
- a Delete button. "+ Add wiring" appends an entry until the level has 8 in total.

When a wired switch is selected, orange lines with arrowheads fan out to each target, with the action name near the midpoint.

### 8.3 Wiring data round-trip

`LevelData.wiring` is `{switch_obj_index: [ {target, action, arg_a, arg_b}, ... ]}`. Import reads the five arrays and groups by switch index; files without them load with `wiring = {}`. Export flattens as in §4.

### 8.4 Validation on export (`_check_wiring`)

Blocks export, with a dialog, on:

- a target index that doesn't exist;
- a target that is the pod (object 0, type `$05`);
- `set_param` / `xor_param` with slot > 2;
- `pulse_door` whose target isn't a door;
- more than 8 entries in total on a level.

Entries whose switch has been deleted or is no longer `$07` / `$08` are pruned silently. Placeholder entries (`action = none` or `target = $FF`) are exported and skipped by the engine. The planned warnings for half-wired entries were not built.

## 9. Implementation history

| Commit | Step |
|--------|------|
| `796aebf` | Phase A: flag, empty per-level tables, refractory bytes. |
| `7a96602` | Phase C: dispatcher with legacy fallback; alive trio + `destroy`. |
| `9691185` | Phase B: editor wiring UX, export validation; `destroy` no-op on dead targets. |
| `d6b79c9` | `set_param` / `xor_param`; arg_a/arg_b arrays; refractory 8 → 20 frames; laser redraw fix. |
| `c988040` | Multi-trigger (several entries per switch). |
| `215938f` | `OBJ_flag_disabled` actions; per-mine local tick; alive trio hidden in editor. |
| `6988c13` | Doors D1: `OBJECT_door`, `pulse_door`, slot shape; engine level 3 migrated. |
| `fad2e49` | Doors D2: notch_v; engine level 5 migrated; `pulse_door` re-latch. |
| `d4c34f5`, `99e31f6` | Doors D3: flat_window with open direction; engine level 4 migrated. |
| `1f7de98`, `f463104` | notch_v carves the matching recess in the opposite wall; peak-depth control dropped. |
| `b60d354`, `5dd4f49`, `3a7c284` | Editor: door hit-testing, shape-accurate previews, drag-resize handles. |

Engine `level_number` 3/4/5 are editor levels 4/5/6.

## 10. Follow-ups

| § | Item | Status |
|---|------|--------|
| 10.1 | Door object + `pulse_door` | done |
| 10.2 | Shape generators | done (slot, notch_v, flat_window) |
| 10.3 | Parameter actions | `set_param` / `xor_param` done; `cycle_param` open |
| 10.4 | Cycle data pool | open |
| 10.5 | Migrate the original three doors | done |
| 10.6 | `OBJ_flag_disabled` | done |
| 10.7 | Single-use switches | open |
| 10.8 | Hostile bullets activate switches | open |
| 10.9 | Authoring helpers for packed param values | partly: type-aware Slot labels exist; sub-field widgets for packed bytes do not |
| 10.10 | `toggle_door` | open |

### 10.1 Door object type + `pulse_door` (done)

`OBJECT_door = $11`. No sprite: the main object loop skips doors before the alive test (`thrust.6502:1711`), so they are never plotted or shot. Per-instance data:

| Slot | Meaning |
|------|---------|
| `obj_data_0` | bit 7 = side (0 = left wall, 1 = right wall); bit 6 = flat_window direction (0 = top-down, 1 = bottom-up); bits 0-1 = shape |
| `obj_data_1` | width (rows; editor "Height", 1..32) |
| `obj_data_2` | max carve depth (editor "Open depth", 1..127) |
| `obj_pos_X`, `obj_pos_Y` | anchor: wall X when closed, top row of the door |

`OBJ_flag_alive` means "animating". Runtime state lives in five 32-byte arrays indexed by object, not in obj_data: `door_cursor` (current carve), `door_phase` (0 opening, 1 holding, 2 closing), `door_hold_phase`, `door_close_phase`, `door_close_rate`.

`action_pulse_door` always re-seeds `door_hold_phase = arg_a` and `door_close_rate = arg_b`. Then:

- idle door: set alive, zero cursor/phase/close_phase (start opening);
- opening or holding: nothing more, so the hold window is extended (matches the original `counter_A = $FF` re-latch);
- closing: set phase back to opening from the current cursor.

`door_advance_anim`: opening increments the cursor by one per frame up to its maximum (`max_carve` for slot/notch_v, `width` for flat_window); holding counts `door_hold_phase` down; closing decrements the cursor once every `close_rate + 1` frames and clears alive at 0.

The carve is rewritten into the wall arrays every frame while the door's top row is on screen (same `< $F1` window test as `level_3_door_logic`), whether the door is open or closed. Closed doors keep their rows at the anchor X, so no terrain needs saving and restoring.

### 10.2 Shape generators (done)

| Code | Shape | Geometry |
|------|-------|----------|
| `0` | `slot` | Every row carved to `anchor ∓ cursor`. |
| `1` | `notch_v` | V-protrusion with a fixed ±1 X step per row (peak at width/2), pulled back by the cursor. A second pass carves the matching V-recess into the opposite wall at the anchor, so the cavern seals exactly when closed. |
| `2` | `flat_window` | Rows open one at a time. The cursor counts open rows (0..width); open rows sit at `anchor ∓ max_carve`, the rest at the anchor. Bit 6 picks top-down or bottom-up. |

### 10.3 Parameter actions

`set_param` (`$06`) and `xor_param` (`$07`) are done (§5). `cycle_param`, which steps a target's slot through an authored list, is open. Its earlier proposed code `$08` is now `set_disabled`; it would take one of `$0B`-`$0F`.

### 10.4 Cycle data pool (open)

For `cycle_param`: a per-level `level_N_cycle_data` byte pool with a `level_cycle_data_lookup_LO/HI` pointer table. A wiring entry stores `arg_a` = offset into the pool and `arg_b` = list length. The exporter would rebuild the pool on each export and rewrite offsets.

### 10.5 Migration of the original game's three doors (done)

Each original door is now a door object wired from the level's two original switches with `pulse_door`, `close_rate = 0` (one cursor step per frame):

| Engine level | Editor level | Door(s) | Hold (`arg_a`) |
|--------------|--------------|---------|----------------|
| 3 | 4 | Two notch_v doors (objects `$0E` right wall, `$0F` left wall); each switch pulses both | `$F0` / `$E0` (240 / 224 frames, about 7.3 / 6.8 s) |
| 4 | 5 | One flat_window door (object `$13`, left wall, top-down, width `$15`, depth `$0E`) | `$E0` (about 6.8 s) |
| 5 | 6 | One notch_v door (object `$11`, left wall, width `$16`, depth `$16`) | `$DC` (220 frames, about 6.7 s) |

Engine level 3's door was first migrated as a slot (`6988c13`) and later re-authored as notch_v in the editor (`f463104`). The goal was play-feel parity, not binary identity.

The current export also carries test wiring on engine level 0 (switch 9) and engine level 3 (switches `$0C`, `$0D`).

### 10.6 Drawn-but-disabled object state (done)

`OBJ_flag_disabled = $10` (bit 4 of `level_obj_flags`; bit 3 is `OBJ_flag_laser_redraw_pending`). The sprite still plots and bullets still collide; per-type behaviour stops:

- guns: `try_gun_fire` doesn't fire;
- lasers: `update_one_laser_beam` takes the off-phase path, so a drawn beam is erased;
- bobbing mines: no motion (the per-mine `bobbing_mine_local_tick` freezes, so the bob resumes where it left off) and no ship contact;
- gravity wells: no pull and no debris;
- teleporters: no warp latch (the debris fountain keeps running).

Actions `$08` / `$09` / `$0A` (§5). The editor badge for disabled targets was not built.

### 10.7 Single-use switches (open)

A per-wiring flag (in a free bit of `arg_a` / `arg_b` or a new byte) that makes the switch clear its own alive bit and spawn debris after the action fires. Editor: a "Single use" toggle, dashed wiring line. Note that the alive trio can already do this by wiring a switch to `clear_alive` itself, but the editor hides those actions.

### 10.8 Hostile bullets activate switches (open)

Drop or relax the player-only filter at `thrust.6502:1935-1936` (`LDA particles_type,X : BNE bullet_miss`) and walk all 32 particle slots instead of player slots 3..0. Gate with a per-wiring "accepts hostile fire" flag so existing puzzles aren't tripped by stray turret fire. See [ideas.md](ideas.md#hostile-bullets-activate-switches).

### 10.9 Authoring helpers for param-write values (partly done)

`set_param` / `xor_param` take a raw byte. Packed fields are hard to author:

- gun `gun_aim`: base angle (bits 2-4) and spread (bits 0-1);
- laser slot 0: phase (low nibble) and duty (high nibble);
- `xor_param` masks have no cue for what each bit means.

Done: the Slot dropdown is labelled per target type (`SWITCH_SLOT_LABELS`). Open: a `(target_type, slot)` registry that shows the same sub-field widgets the base inspector uses (Phase/Duty, Base angle/Spread) and packs them into `arg_b`, plus labelled bit checkboxes for `xor_param` masks.

### 10.10 Door toggle trigger (open)

`toggle_door` (next free code in `$0B`-`$0F`): if the door is idle, open it as `pulse_door` does; if opening or holding, jump to closing; if closing, no-op. No hold phase, so `arg_a` is unused and `arg_b` is still the close rate. One jump-table entry plus a `door_phase` check; editor adds it to `SWITCH_ACTION_VALUES`.

## 11. Testing

Recorded in commit messages: one switch toggling a gun on and off in-emulator (Phase C, level 3), and the three door migrations on engine levels 3/4/5. The level 0 test wiring (switch 9: `destroy` plus three `toggle_disabled` entries) exercises multi-trigger and the disabled actions.

Still worth checking after changes:

- two switches wired to different objects keep independent refractory;
- a switch whose action clears another switch's alive bit doesn't recurse (alive changes don't trigger anything);
- non-SWRAM CRC stays `6389c446`; the SWRAM CRC moves with every change.

## 12. Risks

- **Alive bit on single-instance objects.** The pod (object 0) has hardcoded engine state; the editor blocks it as a target. The pod stand and generator also rewrite their own alive bit every frame (pod lifted, planet countdown blink), so alive actions on them won't stick.
- **Alive vs disabled.** The hidden alive actions make objects vanish and `toggle_alive` can revive a destroyed object with no animation. Prefer `destroy` and the disabled trio.
- **Objects handled before the alive gate.** Teleporters, gravity wells, doors (and mine motion) are processed before the per-object `OBJ_flag_alive` test, so alive actions don't switch them off. Use the disabled actions for teleporters, wells and mines; doors use alive to mean "animating".
- **Self-targeting.** Allowed; a switch can disable or destroy itself.
- **Persistence across deaths.** Wiring effects and door state persist across lives within a level (§1). A puzzle that relies on resetting on death would need extra work.
