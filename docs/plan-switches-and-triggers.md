# Plan: Editor-driven switches and triggers

Replace the hardcoded `level_3/4/5_door_logic` routines and the single global `door_switch_counter_A` with a generic per-level **wiring table** authored entirely from the editor. Switches become a meta-mechanic: any switch can target any object (or a region of terrain) and fire one of a small set of actions (toggle / set parameter / pulse-open a door / activate / deactivate / cycle). The original game's three doors are re-expressed as wiring entries against a generic door object, so the per-level door routines and the global counter both disappear.

Builds on the sketch in [`docs/ideas.md`](ideas.md#configurable-switches-and-triggers); this document picks concrete byte layouts, state owners, action semantics, and an implementation order.

SWRAM-only behind a new build flag; non-SWRAM canonical CRC `6389c446` stays anchored. The original three doors stay byte-identical in non-SWRAM (kept entirely under the legacy code path).

## 1. Goals and non-goals

**Goals**

- Any switch can target any object on the level. Multiple switches per level, each with independent state.
- A small but expressive action set: toggle alive, set parameter byte, cycle parameter byte through a list, pulse a door open/closed.
- Doors are placeable like any other object; their geometry, side (left/right wall), shape, and animation are authored, not hardcoded per level.
- Levels 3/4/5 of the original game are reproduced as wirings against the generic door object; their per-level routines are deleted under the new flag.
- Editor renders wiring as visible lines from switch → target so puzzles are legible while authoring.

**Non-goals (this iteration)**

- Predicate combinations ("fire only when all four switches are set"). The wiring table is one switch → one action; multi-switch combinatorics are layered on later via a separate "logic gate" object type if needed.
- Cross-level wiring or persistence across deaths. State resets on death like everything else.
- Re-using existing object types for switches with arbitrary other meaning. New, distinct object types where helpful.
- Hostile bullets activating switches. Tracked separately as [Hostile bullets activate switches](ideas.md#hostile-bullets-activate-switches) — bullet-vs-object inner loop stays player-only in v1, hostile activation drops in cleanly later as a per-switch flag.

## 2. Build flag and scope

- New flag `_SWITCHES = (_SWRAM_BUILD AND TRUE)` alongside the other feature flags near `thrust.6502:42`.
- All new types, the wiring table, the per-switch state bytes, and the generic dispatcher are gated on this flag.
- Original `tick_door_logic` and the three `level_N_door_logic` routines remain intact and dispatched from `tick_door_logic` only when `_SWITCHES = FALSE`. Under `_SWITCHES = TRUE`, `tick_door_logic` becomes a thin shim that calls `tick_switch_logic` and the three `level_N` routines are bypassed (still assembled if non-SWRAM is the build target — they sit in main RAM either way).

## 3. New object types

| Type    | Name              | Purpose                                                   |
|---------|-------------------|-----------------------------------------------------------|
| `$11`   | `door`            | Editor-placed door region. Owns its own geometry & state. |

`$07`/`$08` (`door_switch_right` / `door_switch_left`) keep their meaning — sprite + AABB collision + "I am a switch". The wiring table is what changes about them.

A door object stores in its existing object slots:

- `obj_data_0` — wiring action target reference (so a door can be the *target* of an action; no special-casing in the dispatcher beyond it).
- `obj_data_1` — door **shape descriptor** byte (see §7).
- `obj_data_2` — door **width-in-rows** (1..32).
- `obj_pos_X`, `obj_pos_Y`, `obj_pos_Y_EXT` — anchor (top-left) of the door region in the wall.
- `level_obj_flags` bit 1 (`OBJ_flag_alive`) — used here as "door is currently being drawn". Cleared = door fully closed (terrain unmodified). Set = door is open/animating (terrain currently carved).

The door object does not need a sprite cache slot — it never plots anything on top of terrain. The sprite registration is a stub (zero-size mask) so the existing sprite-cache path no-ops cleanly. In editor-mode the door is rendered with a custom overlay (§9).

The pod / generator / fuel / gun / laser slots stay where they are; new types take indices ≥ existing ones.

## 4. Per-level wiring table

A parallel array per level, one entry per **switch object** (not per object — keeps the table small). The switch's object index is the implicit key. A second small array indexes from object index → wiring entry, so the dispatcher can lookup wiring for "switch object X" in O(1).

**Wiring entry layout (4 bytes):**

| Field            | Bytes | Meaning                                                                    |
|------------------|-------|----------------------------------------------------------------------------|
| target_obj_index | 1     | object index this switch acts on (`$FF` = no target / disabled)            |
| action_code      | 1     | one of the action codes in §5                                              |
| arg_a            | 1     | action argument 1 (e.g. parameter mask, pulse duration, cycle list index)  |
| arg_b            | 1     | action argument 2 (e.g. parameter value, cycle list length)                |

Action-specific use of `arg_a` / `arg_b` is documented inline in §5.

**Per-level emission** (added to `thrust_levels_export*.asm`):

```
.level_N_switch_obj_indices              ; one byte per switch object, $FF terminator
        EQUB    <switch obj 0 index>, <switch obj 1 index>, ..., $FF

.level_N_switch_wiring                   ; 4 bytes per switch object, parallel array
        EQUB    target, action, arg_a, arg_b   ; entry 0
        EQUB    target, action, arg_a, arg_b   ; entry 1
        ...
```

Per-level lookup tables `level_switch_obj_indices_lookup_LO/HI` and `level_switch_wiring_lookup_LO/HI` mirror the existing band/object tables; SMC patched in `initialise_level_pointers` like the others.

Cycle lists (used by `cycle_param`, §5) live in a single shared **cycle-data pool** per level:

```
.level_N_cycle_data
        EQUB    <list 0 byte 0>, <list 0 byte 1>, ...
        EQUB    <list 1 byte 0>, ...
```

A wiring entry that uses `cycle_param` stores `arg_a` = offset into `level_N_cycle_data`, `arg_b` = list length. A second pointer table `level_cycle_data_lookup_LO/HI` is set up at level init.

## 5. Action codes

Eight action codes is plenty for the original game plus the puzzle archetypes already discussed. Dispatched via a 16-bit jump table indexed by action_code.

| Code  | Name              | Effect                                                                 | arg_a            | arg_b                |
|-------|-------------------|------------------------------------------------------------------------|------------------|----------------------|
| `$00` | `none`            | No-op. Wiring slot is reserved but inactive. Useful for editor stubs.  | —                | —                    |
| `$01` | `set_alive`       | Set target's `OBJ_flag_alive` bit (activate).                          | —                | —                    |
| `$02` | `clear_alive`     | Clear target's `OBJ_flag_alive` bit (deactivate).                      | —                | —                    |
| `$03` | `toggle_alive`    | XOR target's `OBJ_flag_alive`. Re-shootable.                           | —                | —                    |
| `$04` | `set_param`       | Write `arg_b` into target's slot indexed by `arg_a`.                   | slot index 0..2  | byte to write        |
| `$05` | `xor_param`       | XOR target's slot byte with `arg_b`. Bit-flip a flag inside `gun_aim`. | slot index 0..2  | XOR mask             |
| `$06` | `cycle_param`     | Step target's slot through the level's cycle-data pool.                | pool offset      | list length          |
| `$07` | `pulse_door`      | Open the target door for a duration; door's own state machine animates the close. | open hold frames | close-rate (frames per row) |

`set_param` / `xor_param` give you most of what laser puzzles need (flip orientation, bump phase, swap duty). `cycle_param` covers ordering puzzles where each shot rotates a parameter through a list. `pulse_door` is the only action that knows about doors specifically and only because doors have an animation curve.

## 6. Per-switch state

Each switch object gets one byte of "I have been triggered, action is firing or in flight" state. The byte is an **animation cursor**:

- `$00` = idle. Switch is shootable.
- `$01..$FE` = action in flight (cursor counts down, action's per-frame tick interprets the value).
- `$FF` = latched and waiting for a re-arm condition. (Used by toggleable switches that should not re-fire on the same shot.)

Stored in a parallel array `level_switch_state` (one byte per switch object, indexed identically to `level_N_switch_obj_indices`). Cleared on level start in `initialise_level_pointers`, like all other per-level state.

Most actions are *one-shot*: they fire on the leading edge of "cursor went from 0 to non-zero", apply their effect (which may write to the target's parameter / `OBJ_flag_alive`), then return to idle. `pulse_door` and `cycle_param` are the exceptions — they need ongoing per-frame logic (animation curve, advance pointer with refractory delay).

A small refractory window (e.g. 8 frames) is enforced regardless of action so the switch can't be re-triggered by a particle still inside its AABB.

`door_switch_counter_B` is removed entirely. Per-door animation phase lives on the **door object** (§7), not on a global counter.

## 7. Door action implementation

Door geometry varies enough across the original three levels that one parameterised shape doesn't cover all of them well. Carry a small **shape descriptor** byte (`obj_data_1`) that selects a generator routine:

| Code  | Shape                | Geometry                                                                |
|-------|----------------------|-------------------------------------------------------------------------|
| `$00` | `slot`               | Constant X-offset in the wall for `width` rows. Equivalent to level 3 (writes a flat slot of decreasing-X over `width` rows). |
| `$01` | `notch_v`            | V-notch — X decreases for `width/2` rows, then increases for `width/2` rows. Equivalent to level 5. |
| `$02` | `flat_window`        | A constant X-region open for `width` rows, animated by sweeping the open-X back and forth (level 4 effectively). |

Each shape generator is a small subroutine that takes:

- Y in screen-space (computed from world Y via the same `window_ypos_INT/EXT` subtraction used by the existing routines)
- `width` in rows (`obj_data_2`)
- the door's animation cursor (per-frame state byte, see below)

…and writes into `terrain_left_wall` or `terrain_right_wall` accordingly. **Side** (left vs right wall) is a single bit in the shape descriptor (`$80`); the generator picks the wall array via SMC pointer.

**Per-door state.** Carried on the door object's own slot, not on a global counter:

- `level_obj_flags` bit 1 (`alive`) — currently animating? Cleared = door fully shut, dispatcher leaves terrain alone. Set = door is open or in transition.
- `obj_data_0` (re-purposed when alive) — animation cursor: counts up from `0` while opening, sits at `width` while held open, counts back to `0` while closing. The `pulse_door` action reads `arg_a` (open hold frames) and `arg_b` (close rate) from the wiring entry to drive the cursor.

The door object's per-frame update (during `update_and_draw_all_objects`'s usual walk) advances the cursor and calls the shape generator. When the cursor returns to zero, the generator restores the original wall bytes (cached on first open) and the `alive` bit is cleared so subsequent frames skip the work entirely.

**Window-Y guard.** Reuse the existing pattern from `level_3_door_logic` — early-return if the door's screen Y is off-window. The generator only runs when the door is on-screen *and* in transition, so animations advance even while off-screen but no terrain writes happen.

**Caching the original terrain.** The first time a door opens, copy the affected `terrain_left/right_wall` bytes into a small per-door scratch buffer (max `width` bytes, ≤32 bytes per door). On close, write them back. Avoids needing to recompute the original terrain shape from RLE.

## 8. Engine changes

### 8.1 Switch hit handler

Where `handle_door_switch` (`thrust.6502:1947`) currently sets `door_switch_counter_A = $FF`:

Under `_SWITCHES`:
- Look up the switch's wiring entry via the `level_switch_obj_indices` reverse map.
- Read `target_obj_index`, `action_code`, `arg_a`, `arg_b`.
- Dispatch into the action jump table.

Most actions complete inline (the one-shots set/clear/xor a byte and return). `pulse_door` writes into the target door object's `level_obj_flags` (set `alive`) and `obj_data_0` (start cursor at 0); the door's own per-frame update finishes the work.

The bullet-test loop (`thrust.6502:1907`) keeps its existing player-bullet filter at `:1911` unchanged in v1; only the post-hit dispatch is rewired. Hostile-bullet activation is a deliberate v2 follow-up — see [Hostile bullets activate switches](ideas.md#hostile-bullets-activate-switches) — and slots in cleanly later as a per-wiring-entry flag without disturbing the v1 dispatcher.

### 8.2 Per-frame door tick

Add `tick_doors`: walks each level object that is a door type (`$11`) and has `OBJ_flag_alive` set, advances its animation cursor according to the wiring entry that owns it, calls the shape generator. Hooked into the same per-frame slot as the existing `tick_door_logic` (after gameplay update, before render).

Under `_SWITCHES`, `tick_door_logic` becomes:

```
.tick_door_logic
        JSR     tick_doors
        RTS
```

The `level_number`-keyed dispatch and the three `level_N_door_logic` routines are bypassed — they remain in source but are dead code under the flag. Under `_SWITCHES = FALSE` the original routines are still called and produce byte-identical output.

### 8.3 SMC pointer setup at level start

`initialise_level_pointers` already patches per-level SMC slots for objects, bands, etc. Add four more under `_SWITCHES`:

```
LDA  level_switch_obj_indices_lookup_LO,X / HI,X       → switch_indices_addr_*
LDA  level_switch_wiring_lookup_LO,X      / HI,X       → switch_wiring_addr_*
LDA  level_cycle_data_lookup_LO,X         / HI,X       → switch_cycle_addr_*
```

…plus zero out `level_switch_state` for the new level.

### 8.4 Memory cost

- Per-level wiring table: ≤8 switches × 4 bytes = 32 bytes
- Per-level switch index list: ≤8 + terminator = 9 bytes
- Per-level cycle data pool: typical ≤16 bytes (most actions don't use it)
- Switch state: ≤8 bytes
- Door scratch buffers: ≤2 doors × 32 bytes = 64 bytes
- Action jump table: 8 entries × 2 bytes = 16 bytes (in code)

Total: ~130 bytes per level + ~32 bytes shared. Comfortably fits in SWRAM.

## 9. Editor changes

### 9.1 New object types

Register `$11` (`door`) in `OBJECT_TYPE_NAMES` and the object-creation menu. Sprite is a small placeholder (12×8 hollow box) that renders only in the editor — at export time the sprite isn't placed in the in-game sprite tables (`door` is invisible in-game; what's visible is the hole it carves into terrain).

### 9.2 Per-object UI in editor

When the selected object is a `door`:

- Status bar shows `door: shape=<name>  side=<L|R>  width=<rows>  wired_from=#<switch_obj_index or "none">`.
- `[`/`]` cycles `obj_data_1` shape descriptor through `slot` / `notch_v` / `flat_window`.
- `,`/`.` cycles the wall side (left/right bit in shape descriptor).
- `+`/`-` adjusts width (`obj_data_2`).

When the selected object is a switch (`$07`/`$08`):

- Status bar shows `switch: target=#N  action=<name>  arg_a=$XX arg_b=$XX`.
- `[`/`]` cycles `action_code`.
- `,`/`.` and `+`/`-` adjust `arg_a` / `arg_b`.
- **Right-click on a target object while a switch is selected** = "rewire to this object". Most direct authoring move; no menu.
- A thin wiring line is drawn from switch sprite to target object whenever the switch is selected or hovered. Action name floats next to the line midpoint.

### 9.3 Wiring data round-trip

`LevelData` gains a `wiring` dict keyed by switch-object index → `{target, action, arg_a, arg_b}`. Import reads `level_N_switch_obj_indices` and `_switch_wiring`; export emits them sorted by switch object index. Cycle data goes into a shared `cycle_data` list per level, with each wiring entry that uses it referencing an offset.

Import is forward-compatible with files lacking the new arrays (older exports): `wiring` defaults to `{}`, no switches act on anything.

### 9.4 Validation pass on export

The editor checks before writing the file:

- Every switch object index in `level_N_switch_obj_indices` must reference an existing `$07` / `$08` object. Stale entries from deleted switches are pruned automatically.
- Every wiring `target_obj_index` must reference an existing object on the level (or `$FF` = "no target"). Dangling references are flagged and the export is blocked with a status message.
- `pulse_door` action targets must be `door` objects. Mismatch is flagged.
- Cycle-data offsets and lengths must stay within the per-level pool.

Validation pass also warns (but does not block) if a switch has `target=$FF` and `action ≠ none` — almost certainly a half-wired switch.

## 10. Migration of existing levels 3, 4, 5

Re-author each level's door under the new system, then verify via play-test (binary identity is not the goal here — the original counter-based animation is being replaced with object-based animation). Steps per level:

1. Add a `door` object at the world position currently hardcoded in the per-level routine. World Y comes from the `LDA #$xx / SBC window_ypos_INT` constants (level 3: `$0269`, level 4: `$0343`, level 5: `$0370`), X from the `terrain_left_wall` writes the routine performs.
2. Pick the matching shape: level 3 → `slot`, level 4 → `flat_window`, level 5 → `notch_v`.
3. Set `width` from the loop count (`$0D`, `$15`, `$0F`).
4. Wire each existing switch on the level (`$07` / `$08`) to the door with action `pulse_door`. Use `arg_a` (hold frames) and `arg_b` (close rate) values that produce a similar feel to the original animation curve.
5. Delete the per-level door routine references from the export pipeline. Levels 3/4/5 no longer special-case anything.

Acceptance: side-by-side play comparison against the original game (under the SWRAM build with `_SWITCHES = TRUE`). Look for: door opens at the same window-Y, takes a similar number of frames to fully open, holds open for a similar duration, closes at a similar rate. Exact frame-count parity is unnecessary; original feel is.

Under `_SWITCHES = FALSE` the original code path remains, so the canonical CRC `6389c446` is unaffected.

## 11. Testing

- **Smoke test:** new sandbox level with one switch wired to one door. Door opens, holds, closes. Switch is shootable from both player bullets and (when flag set) hostile bullets.
- **Multi-switch level:** two switches wired to two different doors. Each door animates independently.
- **Toggle test:** switch wired with `toggle_alive` against a laser turret. Each shot toggles the laser on/off. Laser correctly stops drawing its beam when alive=0.
- **Cycle test:** switch wired with `cycle_param` against a laser's `gun_aim`. Each shot steps through a 4-entry cycle list (e.g. four orientations). Wraps at the end.
- **Original level 3/4/5 regression:** play levels 3/4/5 under `_SWITCHES = FALSE` (original code) and `_SWITCHES = TRUE` (re-authored). Animation timing should feel near-identical.
- **CRC:** non-SWRAM build remains `6389c446` (whole `_SWITCHES` code path is gated). SWRAM build's CRC will move; that's expected.

## 12. Risks

- **Animation feel.** The original three doors have hand-tuned animation curves baked into their per-level routines. The generic shape generators must reproduce the curves closely enough that levels 3/4/5 still feel right. Mitigation: parameterise the curve (open-rate, hold, close-rate) through `arg_a`/`arg_b` so the migration step in §10 has knobs to turn rather than needing new shape codes.
- **Terrain restoration ordering.** If the door is closing while the player happens to be inside the carved region, restoring the original wall could clip through or kill the player. The original game avoids this by closing slowly enough that this is rarely possible, but it's still a consideration. Mitigation: door close routine inspects the player's screen-space bounding box against the rows it's about to restore each frame, and stalls the close cursor for one frame if the player overlaps. (Cheap; runs only while the door is animating closed.)
- **Sprite registration for door object.** The existing sprite system assumes every object type has a sprite cache slot. Door is the first object type to render purely as a terrain modification with no sprite. Mitigation: register a zero-size mask for type `$11` so the existing path no-ops cleanly without special-casing.
- **Cycle-data layout fragility.** Inline cycle lists in the wiring entry are simpler but limit list length to 1 byte. The pooled approach (offset + length) is more flexible; risk is wiring entries pointing into stale offsets after editor deletes. Mitigation: editor's export validation pass (§9.4) rebuilds the pool from scratch each export, and rewrites all wiring entries' offsets to match the freshly emitted pool.
- **Save state across deaths.** Door state and switch state both reset on level restart, exactly like other per-level state today. No persistence concerns.

## 13. Implementation order

1. **Build flag and stubs.** `_SWITCHES` flag, dead `tick_switch_logic` stub, dead `tick_doors` stub. SWRAM build still produces a working game (new code path runs but does nothing).
2. **Data plumbing.** Add per-level `level_N_switch_obj_indices`, `_switch_wiring`, `_cycle_data` arrays + four lookup tables. Editor exporter emits empty tables for every level. SMC pointers patched in `initialise_level_pointers`. Verify level 3/4/5 still play (original code path still in charge).
3. **Door object type `$11`.** Register in editor, add status-bar UI, add export. Place a door in a sandbox level. Verify sprite-cache no-op path doesn't crash. Door does nothing in-game yet (no per-frame tick).
4. **Switch wiring UX in editor.** Click-to-select switch, right-click-target-to-rewire, status bar action editor. Round-trip a wired sandbox level through import/export.
5. **Action dispatcher + simple actions.** Implement `set_alive` / `clear_alive` / `toggle_alive` first. Wire a sandbox switch to a turret's alive bit. Verify bullets disable the turret.
6. **`set_param` / `xor_param`.** Wire a switch to a laser's `gun_aim`. Verify orientation flips on shoot.
7. **`pulse_door` + door tick.** Implement the `slot` shape generator first. Wire a sandbox switch to a sandbox door. Verify open/hold/close cycle.
8. **`notch_v` and `flat_window` shape generators.** Add status-bar shape cycler. Verify each shape draws correctly.
9. **`cycle_param` and the cycle-data pool.** Wire an ordering puzzle in a sandbox level: four switches stepping a laser's `gun_aim` through four orientations. Verify wrap and reset on level restart.
10. **Migrate level 3.** Re-author its door + wiring entry. Tune the `pulse_door` arguments until animation feels right.
11. **Migrate level 4.**
12. **Migrate level 5.**
13. **Editor validation pass.** Wire-dangling check, switch-target type check, cycle-offset check.
14. **Documentation update.** Move the [ideas.md](ideas.md#configurable-switches-and-triggers) "Configurable switches and triggers" entry into Completed; cross-reference this plan and the migration notes. Hostile-bullet activation stays a separate idea entry for v2.

Each step ends with a play-test in BeebJit / b2 / jsbeeb (per project preference), and a CRC check on the non-SWRAM build to confirm the canonical `6389c446` is still preserved.
