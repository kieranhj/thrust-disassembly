# Plan: Editor-driven switches and triggers

A per-level **wiring table** lets any switch fire a small set of actions against any object on the level, authored entirely from the editor. Replaces the hardcoded `door_switch_counter_A` write with a generic dispatcher; the original `level_3/4/5_door_logic` routines stay where they are and keep running on a legacy fallback path.

Two-stage rollout:

- **MVP (sections 1–9 of this doc).** Four actions — `set_alive`, `clear_alive`, `toggle_alive`, `destroy` — plus a `none` slot. Two extra switch sprites for floor / ceiling mounting. Levels 3/4/5 keep working unchanged: switches with no wiring entry fall through to the legacy `door_switch_counter_A` write so the existing per-level door routines continue to drive them.
- **Deferred follow-ups (§10).** Door object + `pulse_door` action, parameterised actions (`set_param` / `xor_param` / `cycle_param`), shape generators, migration of original game's three doors away from the legacy path, hostile-bullet activation. Sketched at the end so the wiring format and dispatcher are forward-compatible from day one.

Builds on the sketch in [`docs/ideas.md`](ideas.md#configurable-switches-and-triggers).

SWRAM-only behind a new `_SWITCHES` build flag. Non-SWRAM canonical CRC `6389c446` stays anchored — the entire feature path is gated on the flag.

## 1. MVP scope

**Goals**

- Any switch can target any object on the level. Multiple switches per level, each with independent state.
- Action set covers: shoot-to-enable, shoot-to-disable, shoot-to-toggle, shoot-to-destroy-as-if-player-bullet.
- Switches mountable on left wall, right wall, floor, or ceiling.
- Editor renders wiring as visible lines from switch → target so puzzles are legible while authoring.
- Original three doors keep working with zero migration: switches with no wiring entry fall through to the legacy `door_switch_counter_A` write, and `tick_door_logic` still drives the level-N door routines.

**Non-goals (deferred — see §10)**

- Door object type, `pulse_door` action, shape generators.
- `set_param` / `xor_param` / `cycle_param` actions.
- Re-authoring levels 3/4/5 wiring against the new system.
- Hostile bullets activating switches. Bullet-vs-object inner loop stays player-only in v1; hostile activation drops in cleanly later as a per-wiring-entry flag.
- Predicate combinations across switches ("fire only when all four are set"). Could be layered on later via a separate "logic gate" object type if needed.
- Cross-level wiring or persistence across deaths. State resets on death like everything else.

## 2. Build flag

- `_SWITCHES = (_SWRAM_BUILD AND TRUE)` alongside the other feature flags near `thrust.6502:42`.
- All new arrays, the per-switch state bytes, and the dispatcher are gated on this flag.
- `tick_door_logic` runs unchanged. `handle_door_switch` (`thrust.6502:1947`) gains a gated dispatch *before* the existing `door_switch_counter_A = $FF` write — see §7.1.

## 3. New object types

Two new switch sprites for floor / ceiling mounting. The dispatcher treats all four switch types identically — the type only determines the sprite and the AABB orientation:

| Type   | Name                  | Mount   | Status   |
|--------|-----------------------|---------|----------|
| `$07`  | `door_switch_right`   | wall    | existing |
| `$08`  | `door_switch_left`    | wall    | existing |
| `$12`  | `switch_ceiling`      | ceiling | new      |
| `$13`  | `switch_floor`        | floor   | new      |

The bullet-vs-switch hit predicate (currently filters to `$07`/`$08` in `handle_door_switch`'s caller) extends to accept `$12` / `$13`.

No `door` object type and no other new types in MVP.

## 4. Per-level wiring table

A parallel array per level, one entry per **switch object** (not per object — keeps the table small). The switch's object index is the implicit key. A second small array indexes from object index → wiring entry, so the dispatcher can look up wiring for "switch object X" in O(1).

**Wiring entry layout (4 bytes):**

| Field             | Bytes | Used in MVP? | Meaning                                                  |
|-------------------|-------|--------------|----------------------------------------------------------|
| target_obj_index  | 1     | yes          | object index this switch acts on (`$FF` = no target)     |
| action_code       | 1     | yes          | one of the action codes in §5                            |
| arg_a             | 1     | reserved (0) | for `set_param` / `cycle_param` follow-ups (§10)         |
| arg_b             | 1     | reserved (0) | as above                                                 |

Same 4-byte layout as the full plan, so follow-up actions drop in without a format change. MVP entries always write `arg_a = arg_b = 0`.

**Per-level emission** (added to `thrust_levels_export*.asm`):

```
.level_N_switch_obj_indices              ; one byte per switch object, $FF terminator
        EQUB    <switch obj 0 index>, <switch obj 1 index>, ..., $FF

.level_N_switch_wiring                   ; 4 bytes per switch object, parallel array
        EQUB    target, action, $00, $00   ; entry 0
        EQUB    target, action, $00, $00   ; entry 1
        ...
```

Per-level lookup tables `level_switch_obj_indices_lookup_LO/HI` and `level_switch_wiring_lookup_LO/HI` mirror the existing band/object tables; SMC-patched in `initialise_level_pointers` like the others.

## 5. MVP action codes

Five codes in MVP, plus reserved space for the follow-ups in §10. Dispatched via a 16-bit jump table indexed by `action_code` — the table is sized for 16 entries from day one so adding follow-up actions later is just filling slots.

| Code  | Name              | Effect                                                                                                  |
|-------|-------------------|---------------------------------------------------------------------------------------------------------|
| `$00` | `none`            | No-op. Wiring slot reserved but inactive. Useful for editor stubs / placeholders.                       |
| `$01` | `set_alive`       | Set target's `OBJ_flag_alive` bit (activate).                                                           |
| `$02` | `clear_alive`     | Clear target's `OBJ_flag_alive` bit (deactivate).                                                       |
| `$03` | `toggle_alive`    | XOR target's `OBJ_flag_alive`. Re-shootable.                                                            |
| `$04` | `destroy`         | Run the player-bullet destruction path against the target — explosion particles + score + alive cleared.|
| `$05+`|                   | Reserved for follow-ups: `set_param`, `xor_param`, `cycle_param`, `pulse_door`. See §10.                |

**`destroy` semantics.** Enters via `destroy_object` with `X = target_obj_index`. The bullet-hit path normally reaches `destroy_object` with bullet-state ZP set up by the particle loop; verify what `destroy_object` actually reads beyond `X`, and wrap in a small adapter that zeroes / sets that ZP if needed so the dispatcher can call it cleanly from the switch hit context.

## 6. Per-switch state

One byte per switch object, parallel-indexed to `level_switch_obj_indices`:

- `$00` = idle. Switch is shootable.
- `$01..$07` = refractory countdown. Decrements each frame; switch ignores hits while non-zero.

Stored in `level_switch_state`, cleared on level start in `initialise_level_pointers` like all other per-level state. The refractory window prevents one bullet still inside the switch's AABB from re-firing the action across multiple frames.

No per-switch latch state in MVP — all four actions are purely one-shot.

`door_switch_counter_A` and `door_switch_counter_B` are **not removed** in MVP. They keep driving the legacy door routines for any switch that has no wiring entry.

## 7. Engine changes

### 7.1 Switch hit handler with legacy fallback

In `handle_door_switch` (`thrust.6502:1947`), before the existing `door_switch_counter_A = $FF` write, under `_SWITCHES`:

1. Check the switch's `level_switch_state` byte. If non-zero, return (refractory).
2. Reverse-lookup the switch's wiring entry via `level_switch_obj_indices`.
3. **If no entry exists** for this switch object, or the entry has `action_code = $00 (none)` / `target_obj_index = $FF`: **fall through** to the legacy `door_switch_counter_A = $FF` write. Levels 3/4/5 keep working unchanged because their switches have no wiring entries.
4. **If an entry exists** with a real action: read `target_obj_index` and `action_code`, dispatch into the action jump table, set `level_switch_state` to the refractory value (e.g. `$08`), and return *without* touching `door_switch_counter_A`. The wiring entry has fully consumed the switch hit.

This means a level can mix wired and unwired switches — but in practice each switch is one or the other. Levels 3/4/5 stay 100% on the legacy path; new sandbox / puzzle levels use only wired switches.

### 7.2 No new per-frame work

All five MVP actions complete inline in the dispatcher. There's no `tick_doors` walker, no animation curves to advance — the action runs once and is done. `tick_door_logic` keeps its existing `level_number`-keyed dispatch and the three `level_N_door_logic` routines stay live.

The only new per-frame cost is the `level_switch_state` decrement, which runs once per switch object — bounded by the per-level switch count (≤8). Cheap.

### 7.3 SMC pointer setup at level start

`initialise_level_pointers` already patches per-level SMC slots for objects, bands, etc. Add two more under `_SWITCHES`:

```
LDA  level_switch_obj_indices_lookup_LO,X / HI,X       → switch_indices_addr_*
LDA  level_switch_wiring_lookup_LO,X      / HI,X       → switch_wiring_addr_*
```

Plus zero out `level_switch_state` for the new level.

### 7.4 Memory cost

- Per-level wiring table: ≤8 switches × 4 bytes = 32 bytes
- Per-level switch index list: ≤8 + terminator = 9 bytes
- Switch state: ≤8 bytes
- Action jump table: 16 entries × 2 bytes = 32 bytes (in code; oversized so follow-ups drop in)

Total: ~50 bytes per level + ~32 bytes shared. Comfortably fits in SWRAM.

## 8. Editor changes

### 8.1 New switch sprites

Author 12×8 sprites for `$12` (ceiling-mounted) and `$13` (floor-mounted) via `sprite_editor.py`. Sprite tables grow by two entries; the existing palette grid picks them up automatically once registered in `OBJECT_TYPE_NAMES`.

### 8.2 Per-switch UI

When the selected object is any switch type (`$07` / `$08` / `$12` / `$13`):

- Inspector schema gains two fields:
  - `Action` (enum): `none` / `set_alive` / `clear_alive` / `toggle_alive` / `destroy`.
  - `Target` (ref-pick, `target_kind="object"`): pick any object on the level. `$FF` = no target / disabled.
- A thin wiring line is drawn from the switch sprite to the target object whenever the switch is selected or hovered. Action name floats near the line midpoint.
- Re-uses the existing ref-pick widget (currently used for teleporter destination); only difference is `target_kind` over object indices instead of checkpoint indices.

### 8.3 Wiring data round-trip

`LevelData` gains a `wiring` dict keyed by switch-object index → `{target, action, arg_a, arg_b}`. Import reads `level_N_switch_obj_indices` and `_switch_wiring`; export emits them sorted by switch object index.

Import is forward-compatible with files lacking the new arrays (older exports): `wiring` defaults to `{}`, all switches behave like legacy switches.

### 8.4 Validation pass on export

Editor blocks the export with a status message on:

- Wiring entry whose `target_obj_index` references a non-existent object.
- Wiring entry whose target is the pod (object 0, type `$05`) — single-instance pod state isn't safe to alive-toggle.
- Switch index list referencing a non-switch object (stale entry from a deleted switch is pruned automatically rather than blocked).

Editor warns (does not block) on:

- Switch with `target ≠ $FF` and `action = none` (probably half-wired).
- Switch with `target = $FF` and `action ≠ none` (action will never fire).

## 9. Implementation order (MVP)

Each step ends with the editor still launchable, level 3/4/5 still playable on legacy code, and the non-SWRAM CRC unchanged.

1. **Build flag + scaffolding.** `_SWITCHES` flag; per-level empty `switch_obj_indices` / `switch_wiring` arrays + lookup tables; SMC patches in `initialise_level_pointers`; `level_switch_state` bytes. Exporter emits empty arrays for every level. Game still plays unchanged.
2. **New switch sprites.** Author `$12` ceiling and `$13` floor sprites in `sprite_editor.py`. Register types in `OBJECT_TYPE_NAMES` and the bullet-vs-switch hit predicate. Place a `$12`/`$13` in a sandbox level and shoot it — should drive the same legacy `door_switch_counter_A` behaviour as `$07`/`$08` (which on a non-3/4/5 level is a no-op, fine for now).
3. **Editor wiring UX.** `LevelData.wiring` dict; import/export round-trip; inspector `Action` enum + `Target` ref-pick fields; visible wiring line from switch to target. Round-trip a wired sandbox level through Ctrl+S / `--import` byte-identically.
4. **Action dispatcher + alive actions.** Implement the dispatcher with legacy fallback (§7.1). Code `none`, `set_alive`, `clear_alive`, `toggle_alive`. Sandbox: switch toggles a turret on/off; alive=0 lasers stop drawing their beam.
5. **`destroy` action.** Identify what `destroy_object` reads beyond `X = victim index`; wrap in an adapter that sets up that context from the dispatcher. Sandbox: switch destroys a generator from a safe vantage; explosion particles + score fire as if shot directly.
6. **Acceptance tests.** Multi-switch sandbox level (two switches → two different objects, independent state). Cascade test: switch C clears switch B's alive (no recursion concerns since dispatcher only fires on bullet hit, not on alive transitions). Regression: levels 3/4/5 under both `_SWITCHES = FALSE` and `TRUE` — doors must still open via the legacy fallback.
7. **Editor validation pass.** Dangling-target block, pod-target block, stale-switch-index prune.
8. **Documentation update.** Move the [ideas.md](ideas.md#configurable-switches-and-triggers) "Configurable switches and triggers" entry into Completed; cross-reference this plan; explicitly call out the deferred follow-ups in §10. Hostile-bullet activation stays a separate idea entry for v2.

## 10. Deferred follow-ups

Sketched here so the MVP wiring format and dispatcher are forward-compatible. None of this is in MVP scope.

### 10.1 Door object type + `pulse_door`

A new object type `$11 door` for editor-placed door regions. Owns its own geometry and animation state:

- `obj_data_0` — animation cursor.
- `obj_data_1` — shape descriptor byte.
- `obj_data_2` — door width-in-rows (1..32).
- `obj_pos_X`, `obj_pos_Y` — anchor (top-left) of the door region in the wall.
- `level_obj_flags` bit 1 (`OBJ_flag_alive`) — re-purposed as "door is currently animating".

Sprite registration is a stub (zero-size mask) so the existing sprite-cache path no-ops cleanly. In editor-mode the door is rendered as a custom overlay.

`pulse_door` action (`action_code = $05`, say): writes into target door object's `level_obj_flags` (set `alive`) and `obj_data_0` (start cursor at 0). The door's own per-frame update finishes the work, reading `arg_a` (open hold frames) and `arg_b` (close rate) from the wiring entry.

A new per-frame walker `tick_doors` advances each animating door's cursor and calls the matching shape generator; hooked into the same per-frame slot as `tick_door_logic`. Restoration of original terrain bytes uses a per-door scratch buffer (≤32 bytes per door) cached on first open.

### 10.2 Shape generators

Door geometry varies enough across the original three levels that one parameterised shape doesn't cover all of them well. Carry a small **shape descriptor** byte (`obj_data_1`) that selects a generator routine:

| Code  | Shape         | Geometry                                                                                    |
|-------|---------------|---------------------------------------------------------------------------------------------|
| `$00` | `slot`        | Constant X-offset in the wall for `width` rows. Equivalent to level 3.                     |
| `$01` | `notch_v`     | V-notch — X decreases for `width/2` rows, then increases for `width/2` rows. Level 5.      |
| `$02` | `flat_window` | Constant X-region open for `width` rows, animated by sweeping the open-X back and forth. Level 4. |

Each generator takes Y in screen-space, `width`, and the door's animation cursor, and writes into `terrain_left_wall` or `terrain_right_wall` accordingly. Side (left vs right wall) is a bit in the shape descriptor (`$80`); the generator picks the wall array via SMC pointer.

Window-Y guard: reuse the early-return-if-off-window pattern from `level_3_door_logic`.

### 10.3 Parameter actions

| Code  | Name              | Effect                                                                 | arg_a            | arg_b                |
|-------|-------------------|------------------------------------------------------------------------|------------------|----------------------|
| `$06` | `set_param`       | Write `arg_b` into target's slot indexed by `arg_a`.                   | slot index 0..2  | byte to write        |
| `$07` | `xor_param`       | XOR target's slot byte with `arg_b`. Bit-flip a flag inside `gun_aim`. | slot index 0..2  | XOR mask             |
| `$08` | `cycle_param`     | Step target's slot through the level's cycle-data pool.                | pool offset      | list length          |

`set_param` / `xor_param` cover most laser-puzzle uses (flip orientation, bump phase, swap duty). `cycle_param` covers ordering puzzles where each shot rotates a parameter through a list.

### 10.4 Cycle data pool

Cycle lists used by `cycle_param` live in a single shared per-level **cycle-data pool**:

```
.level_N_cycle_data
        EQUB    <list 0 byte 0>, <list 0 byte 1>, ...
        EQUB    <list 1 byte 0>, ...
```

A wiring entry that uses `cycle_param` stores `arg_a` = offset into the pool, `arg_b` = list length. A second pointer table `level_cycle_data_lookup_LO/HI` is set up at level init.

Editor's export validation pass rebuilds the pool from scratch each export and rewrites all wiring entries' offsets to match — avoids stale offsets after deletes.

### 10.5 Migration of original game's three doors

Re-author each level's door under the new system, then verify via play-test (binary identity is not the goal — the original counter-based animation is being replaced with object-based animation). Per level:

1. Add a `door` object at the world position currently hardcoded in the per-level routine. World Y from the `LDA #$xx / SBC window_ypos_INT` constants (level 3: `$0269`, level 4: `$0343`, level 5: `$0370`); X from the `terrain_left_wall` writes.
2. Pick the matching shape: level 3 → `slot`, level 4 → `flat_window`, level 5 → `notch_v`.
3. Set `width` from the loop count (`$0D`, `$15`, `$0F`).
4. Wire each existing switch on the level (`$07` / `$08`) to the door with action `pulse_door`, tuning `arg_a` (hold frames) and `arg_b` (close rate) to feel similar to the original.
5. Delete the per-level door routine references from the export pipeline.

Acceptance: side-by-side play comparison against the original under SWRAM `_SWITCHES = TRUE`. Frame-count parity unnecessary; original feel is.

### 10.6 Drawn-but-disabled object state (`OBJ_flag_disabled`)

`set_alive` / `clear_alive` / `toggle_alive` semantically mean "exists / is destroyed" — not "active / dormant". The per-object update loop tests `OBJ_flag_alive` at `thrust.6502:1806` and skips both the plot path *and* the per-type behaviour when the bit is clear, so a switch wired to clear a gun's alive bit makes the gun **vanish** rather than just stopping it firing. Confirmed in-emulator with the Phase C level-3 toggle test (2026-05-06).

A second consequence of conflating exists-with-active: a `toggle_alive` switch can **revive a destroyed object**. Player shoots the gun → alive bit clears → switch toggles → alive bit sets → gun is back, with no explosion or animation, just popping into existence. Sometimes a fun puzzle ingredient (a "respawn" switch); usually not what you wanted. Once `OBJ_flag_disabled` lands, this side-effect dissolves: `set_alive` would only ever re-attach an explicitly-deactivated object the *level* started disabled, while `clear_disabled` / `set_disabled` would be the natural pair for "freeze-thaw the gun".

For shoot-to-disable puzzles (a turret freezes in place but is still visible, or a laser stops firing but the emitter sprite stays on the wall), introduce a separate flag bit:

- New `OBJ_flag_disabled = $08` (or similar — first free bit in `level_obj_flags`).
- Per-type update bodies test `OBJ_flag_disabled` *after* the existing `OBJ_flag_alive` gate. When set: skip the type-specific behaviour (gun fire, laser beam draw, mine bobbing, well pull) but still allow the plot / cull / collision-check path to run.
- Three new actions, mirroring the alive trio: `set_disabled` ($05), `clear_disabled` ($06), `toggle_disabled` ($07). Drop into the existing 16-entry jump table.
- Editor cue: dim the sprite or overlay a "disabled" badge in the editor when an object is referenced as a `*_disabled` action target, so the designer can read the puzzle visually.

Cheap to implement once we know which behaviours need gating per type — likely just guns ($00..$03), lasers ($09..$0C), and mines ($0E/$0F). Pod, fuel, generator, teleporter, gravity well don't have ongoing per-frame "behaviour" beyond rendering / collision, so they can ignore the bit.

### 10.7 Single-use switches (per-wiring "destroy after firing" flag)

Some puzzle archetypes want a switch that fires *once* and then is consumed — a one-shot key for an irreversible state change. Right now every switch is freely re-shootable (refractory aside). Add a per-wiring flag that makes the switch destroy *itself* after the action fires.

Implementation:

- Repurpose one of the reserved wiring bytes (`arg_a` or `arg_b`) as a flags byte. Bit 0 (`SWITCH_FLAG_single_use`) means "after the action runs, clear the switch's own alive bit and spawn a debris puff".
- Dispatcher's tail (just before the `CLC; RTS`) tests the flag, and if set: `LDX current_object; clear OBJ_flag_alive; spawn an explosion at the switch's screen position`. Reuses the existing `spawn_hit_debris` path or `create_explosion` directly.
- Editor: a checkbox / toggle on the switch's inspector panel (`Single use`). When set, the wiring line draws as dashed instead of solid, and the action label appends "(once)".
- Validation: a single-use switch with `action = none` is the same as a no-op; warn (don't block) on export.

Composes naturally with `pulse_door` (one-shot door opener: shoot → door pulses open → switch is gone) and with `cycle_param` (interesting puzzle: a single-use switch only consumes one cycle slot before vanishing, locking the cycle in a particular state).

Cheap — one byte of state per wiring entry, ≤16 cycles in the dispatcher tail.

### 10.8 Hostile bullets activate switches

Drop the player-only filter at `thrust.6502:1911-1912` (or relax to also accept particle type `$03`), and walk all 32 particle slots instead of just the four player-bullet slots. Gate via a per-wiring-entry "accepts hostile fire" flag so existing puzzles aren't degenerated by stray turret bullets tripping switches. Combines with [field flips for routing bullets](ideas.md#configurable-switches-and-triggers) and the gravity-well [bullet pull](ideas.md#gravity-well-follow-ups) follow-up to enable turrets-defeat-themselves puzzles.

### 10.9 Authoring helpers for param-write values

`set_param` and `xor_param` take a raw byte as the value / mask. For numeric slots (well radius, mine amplitude, beam dx / dy) that's fine. For *packed* fields it's hostile to author against:

- Gun `gun_aim` packs base angle (bits 2–4, ×4 step) and spread (bits 0–1, lookup-table index).
- Laser `gun_aim` packs phase index (low nibble × 8 frames) and duty index (high nibble × 4 + 4 frames).
- `xor_param` masks are bit patterns — `$80` to flip duty's high bit, `$03` to wipe spread, etc. — and there's no in-editor cue for what each bit *means* on the target type.

The base inspector already has type-aware widgets for these fields (the laser inspector exposes Phase and Duty as separate enums; the gun inspector has Base angle and Spread). The natural fix is to surface the same widgets inside the wiring entry once Slot + Action are picked, replacing the raw Value byte field for known target-type / slot combos.

Concretely, a small registry: given `(target_type, slot)`, return either a list of sub-fields (one per packed sub-component, each backed by a getter/setter that packs into `arg_b`) or `None` to fall back to the raw byte. For `xor_param` the same registry could expose a row of bit checkboxes for the mask, labelled with the sub-field names ("flip duty bit 3?", "flip orientation?").

Cheap once the registry exists; the bulk of the work is enumerating which (type, slot) pairs benefit. Likely worth it before authoring any non-trivial puzzles, since "shoot the switch and the laser changes" only reads well if the designer can predict *how* it changes from the inspector.

## 11. Testing

- **MVP smoke test:** new sandbox level with one switch wired to one turret via `toggle_alive`. Each shot toggles the turret on/off; refractory window prevents double-fire while the bullet is still inside the AABB.
- **Multi-switch level:** two switches wired to two different objects. Independent state; one's refractory doesn't gate the other.
- **Destroy test:** switch wired with `destroy` against a generator. Behaves identically to shooting the generator directly (same explosion particles, same score).
- **Cascade test:** switch C clears switch B's alive. Verifies dispatcher doesn't recurse on alive transitions.
- **Original level 3/4/5 regression:** play levels 3/4/5 under both `_SWITCHES = FALSE` and `_SWITCHES = TRUE`. Doors must still open identically because their switches have no wiring entries and fall through to the legacy path.
- **CRC:** non-SWRAM build remains `6389c446` (whole `_SWITCHES` code path is gated). SWRAM build's CRC will move; that's expected.

## 12. Risks

- **`destroy_object` reentrancy.** The routine normally runs in a bullet-hit context with bullet-state ZP set up by the particle loop. The dispatcher calls it from `handle_door_switch`, which has different ambient state. Mitigation: identify what `destroy_object` actually reads beyond `X = victim index` and wrap in a small adapter that synthesises the missing context. Test against alive=1 lasers, turrets, generators, mines, and gravity wells to make sure each destroys cleanly.
- **Toggling alive on lasers mid-frame.** Lasers XOR-draw their beams each frame; clearing `alive` mid-frame must leave the beam erased rather than stuck on. Verify `tick_lasers` (or the laser draw routine) handles `alive=0` cleanly — the beam should be erased on the frame the toggle fires.
- **Alive bit collisions with single-instance state.** Pod (object 0, type `$05`) has hardcoded single-instance state; alive-toggling it would desync the engine's pod tracking. Editor blocks pod as a wiring target. Generators and other unique single-instance objects are fine because they stay at their canonical index.
- **Self-targeting.** Switch wired to itself with `clear_alive` removes itself after one shot — fine, designer's choice. Editor renders the wiring line as a small loop; dispatcher handles it without recursion concerns since alive transitions don't trigger anything.
- **Refractory window leakage.** If the dispatcher sets `level_switch_state` before the action runs and the action longjmps out (e.g. `destroy` triggers explosion → frame end), the refractory might never decrement. Mitigation: set the state byte *after* the action returns.
- **Save state across deaths.** Switch state and target alive bits both reset on level restart, exactly like other per-level state today. No persistence concerns.
