# Plan: Editor UI overhaul — right-pane inspector + sprite palette

The status bar at the bottom of the editor has accreted to the point where it's the primary parameter readout for the selected item and the only place to see what `[`/`]`/`,`/`.`/`+`/`-`/`K`/`J`/`H`/`\` etc. are mapped to in the current context. Every new feature (bands with two colours, teleporter dest, gravity well radius/strength, bobbing-mine phase/amplitude, laser endpoint, gun aim/spread, etc.) has piled another bracket-pair onto the same row of overloaded keys. Right-click placement opens a popup list that's now long enough that scanning it is slower than drawing the sprite.

This plan replaces both with a structured **right-hand inspector pane** (parameter editor for whatever is selected) and a **sprite palette grid** (object placement), keeps every existing keyboard shortcut working, and slims the status bar back down to the bits that don't belong on either side.

Pure tooling change — no engine impact, no CRC implications. SWRAM and non-SWRAM builds unchanged.

## 1. Goals and non-goals

**Goals**

- One canonical place to see and edit every parameter of the selected object / checkpoint / band / level. No more reading hex values out of a wrap-prone status string.
- Mouse-first authoring (click to edit, drag sliders, type values directly) without taking the keyboard away from power users — every existing shortcut keeps working in parallel.
- Visual sprite palette for object placement, replacing the right-click text list. Drag-to-place + click-to-arm both supported.
- Field schemas declared once per object type, so the inspector and the export/import code can share the source of truth and adding a new field is one entry instead of three.
- Status bar slimmed to mode + level + file + mouse coords + transient hints.

**Non-goals (this iteration)**

- Multi-select / bulk edit. Selection stays single-item.
- Resizable panes / theming / dockable panels. Right-pane width is fixed (configurable constant); no drag-to-resize.
- Inspector for the level itself as a whole (gravity, no_wrap_y, level colours) is in scope, but a full level-properties dialog with import/export controls is not. The toolbar's level-colour swatches and gravity ± buttons stay where they are.
- Undo for inspector edits is the same per-action `undo.save()` as today; no batching of slider drags into a single undo entry. (Possible follow-up.)

## 2. Layout

Add `INSPECTOR_W = 300` (constant). The viewport, toolbar, and status bar all reduce in width by `INSPECTOR_W`; the inspector occupies the right strip from `screen_width - INSPECTOR_W` to the right edge, full height (top of toolbar to bottom of window).

```
  ┌────────────────────────────────────────────────┬──────────────┐
  │ Toolbar (level tabs, mode tabs, colours, etc.) │              │
  ├────────────────────────────────────────────────┤              │
  │                                                │  Inspector   │
  │             World viewport                     │  pane        │
  │                                                │              │
  │                                                │              │
  ├────────────────────────────────────────────────┤              │
  │ Status bar                                     │              │
  └────────────────────────────────────────────────┴──────────────┘
```

Camera viewport width is `screen_width - INSPECTOR_W`; mouse-pick / world-to-screen conversions clip to that. Resize handler scales the inspector to full height alongside the viewport's height adjustment.

The pane is divided top-to-bottom into two scrollable sections:

1. **Inspector** (top, ~60% height) — schema-driven fields for the current selection.
2. **Palette** (bottom, ~40% height) — sprite grid in object mode; in other modes, a placeholder showing mode-specific tools or simply hidden.

A horizontal divider between them is grab-draggable to retune the split (state persisted in editor state, not in the level file). Each section has its own scroll bar when content overflows.

## 3. Inspector pane

### 3.1 Field-schema declarations

Each editable thing (object type, checkpoint, band, level-properties, no-wrap-y handle) declares a list of fields. A field is:

```python
Field = {
    "id": "well_radius",        # unique within the schema
    "label": "Radius",          # display name
    "kind": "byte" | "signed_byte" | "word" | "bool" | "colour" | "enum" | "ref",
    "min": 0, "max": 127,        # for numeric kinds
    "step": 1, "shift_step": 16, # increment with / without Shift
    "fmt": "{} px"               # format string for display value
        | "${:02X}"
        | "{name}"               # for colour / enum
    "getter": lambda obj: obj["well_radius"],
    "setter": lambda obj, v: obj.__setitem__("well_radius", v),
    "hotkey": ("[", "]"),        # optional keyboard cycle pair, mapped only when this field is "active" (see §3.4)
    "applies_when": lambda obj: obj["type"] == OBJECT_GRAVITY_WELL,  # optional gating predicate
}
```

For colour pickers, `kind="colour"` with `min=0, max=7` and the renderer draws an 8-swatch row instead of a slider. For enums (e.g. door shape descriptor in the future switches feature), `kind="enum"` carries a `values=[("slot", 0), ("notch_v", 1), ...]` list.

For object reference fields (e.g. teleporter destination = checkpoint index, or the future switch target = object index), `kind="ref"` carries a `target_kind="checkpoint"|"object"|"door"` and the inspector renders a "Pick…" button that arms a one-shot click-on-target mode.

### 3.2 Schemas per mode / type

| Selection                       | Schema                                                                                  |
|---------------------------------|-----------------------------------------------------------------------------------------|
| (none)                          | Level properties: gravity, no_wrap_y, landscape_colour, object_colour, level_num readout |
| Wall edge / bottom-handle       | Read-only readout: "Wall mode — Draw / Line tool". No editable fields here, the wall is edited on canvas. |
| Checkpoint                      | spawn_x, spawn_y, window_x, window_y                                                    |
| Band                            | Y, gravity (signed_byte with `[`,`]`,`,`,`.` step), landscape_colour (colour, K), object_colour (colour, J) |
| Object: gun ($00..$03)          | x, y, gun_aim base + spread (two enum dropdowns)                                        |
| Object: fuel ($04)              | x, y                                                                                    |
| Object: pod_stand ($05)         | x, y                                                                                    |
| Object: generator ($06)         | x, y                                                                                    |
| Object: door switch ($07/$08)   | x, y, side (enum: left/right)                                                          |
| Object: laser turret ($09..$0C) | x, y, gun_aim phase (4-bit), gun_aim duty (4-bit), beam dx, beam dy                    |
| Object: gravity well ($0D)      | x, y, radius, strength (signed_byte)                                                   |
| Object: bobbing mine ($0E/$0F)  | x, y, phase, amplitude (signed_byte)                                                   |
| Object: teleporter ($10)        | x, y, destination (ref→checkpoint)                                                     |

Schema entries reuse the existing accessor patterns (the dict keys are already what `LevelData` and the importer/exporter use). A small registry maps `(mode, obj_type or None)` → schema. Switching mode or selection re-renders the inspector body.

### 3.3 Field widgets

Each field renders as a row roughly 28 px tall:

```
┌──────────────────────────────────────────────────┐
│ Label                          [─────●─────] 42  │   ← slider + numeric readout
├──────────────────────────────────────────────────┤
│ Label                          [- 42 +]          │   ← spinner (byte / word / signed)
├──────────────────────────────────────────────────┤
│ Label                          [▾ Yellow]        │   ← colour swatch (click cycles, right-click opens palette popup)
├──────────────────────────────────────────────────┤
│ Label                          [▾ Diamond]       │   ← enum dropdown
├──────────────────────────────────────────────────┤
│ Label                          #3 [Pick…]        │   ← reference (target object index)
└──────────────────────────────────────────────────┘
```

**Slider** (byte / signed_byte / word): horizontal track with a draggable thumb; the numeric readout on the right is also clickable to pop up a small text-entry overlay where the user types a value (`$AF`, `175`, or `-12` all accepted, matching the existing parser). Pressing Enter commits, Escape cancels. Values out of range clamp on commit and flash red briefly.

**Spinner** (compact mode for narrow fields and bytes that don't benefit from a slider — e.g. spawn_x, gun_aim sub-nibbles): `[-] value [+]` tappable buttons + click-to-text-entry on the value. Shift+click on `[+]`/`[-]` applies `shift_step` instead of `step`.

**Colour**: 8-cell palette row directly inline (saves clicks for the most common operation). Selected cell highlighted; clicking a different cell sets and commits. For "inherit" semantics in band colour fields, an extra "—" cell at the end represents `None` (inherit level default). All colour fields use the same widget; field schema declares whether `None` is permitted.

**Enum / dropdown**: click opens a small popup list of `(name, value)` choices; click selects.

**Ref**: shows the current target's kind+index+optional preview ("CP3 (172, 1024)" / "obj#5: gravity well"). "Pick…" arms a one-shot mode where the next click on a valid target on the canvas writes that target's index into the field.

### 3.4 "Active field" and keyboard shortcuts

Fields can declare `hotkey=("[", "]")` (with optional `,` and `.` for ±step). Existing shortcuts wire through here so power users keep them. The dispatch is identical to today's: when the user presses `[` and the current selection's schema has a field claiming that key, that field's setter fires with the matching delta.

Multiple fields can claim the same key pair — in which case there's an implicit "active field" within the schema (the most recently-clicked or focused one); shortcuts apply to the active field. The active field is highlighted with a thin border in the inspector. Tab / Shift+Tab cycle.

This subsumes the current overload at the keyboard level: today `[`/`]` does different things in different modes (and per-object-type within object mode); in the new model the keys still work but they're deterministically tied to the active field, and the user can see which field they're modifying.

Existing single-purpose shortcuts (`K` / `J` for band colours, `H` for the planned hostile flag — now retired in §4) keep working: those shortcuts target their schema's specific field by id rather than relying on active-field state, so they fire regardless of which field is focused.

### 3.5 Direct text entry

Click any numeric value (slider readout, spinner readout) to switch it to text-entry mode. Caret renders, all keypresses except Enter / Escape / Tab buffer into the field. Enter commits with the existing parser (decimal, `$XX` hex, `+N`/`-N` signed). Escape reverts. Tab commits and moves focus to the next field. Click outside commits.

While text-entry is active, the global keyboard shortcut layer is suppressed so the user can type `e` without switching to "object mode" or whatever. A small status hint shows "typing — Enter to commit, Esc to cancel".

### 3.6 No selection

When nothing is selected, the inspector shows level-wide properties: level number (read-only), gravity, no_wrap_y (with a "Disable" checkbox that sets it to `$FFFF`), landscape_colour, object_colour. These mirror the controls currently in the toolbar — the toolbar versions stay as quick-access duplicates.

## 4. Sprite palette

### 4.1 Layout

The bottom section of the right pane, visible in object mode. Displays each placeable object type as a tile in a 3-column grid:

```
┌─────────────────┐
│ ▣ ▣ ▣           │
│ ▣ ▣ ▣           │
│ ▣ ▣ ▣           │
│ ▣ ▣             │
└─────────────────┘
```

Each tile is ~80×64 px and contains:
- The actual sprite art rendered at its in-game pixel scale (or 2× for small sprites), tinted with the *current* level colours (or band colours when in band mode at the cursor's row).
- The type number in a corner (`$0E`).
- Type name beneath the sprite.
- Hover highlight; selected tile (the type currently armed for placement) gets a thicker border.

For type variants that share a sprite slot but differ in orientation only (the four laser turrets `$09..$0C`, the four guns `$00..$03`), tiles can group: a single "Gun" tile that opens a 4-orientation sub-popup, or four separate tiles depending on how cluttered the grid gets. Start with separate tiles and group later if needed.

Sprite types with no real sprite (door switches use plain symbols today; the future `door` object type will have no sprite at all) get a stylised placeholder tile that still reads as that type.

### 4.2 Placement interactions

**Click to arm**: clicking a tile arms that type. Crosshair cursor while armed; clicking on the canvas places one instance at the cursor's world position. Right-click cancels. Esc cancels. Clicking the same tile again or another tile re-arms.

**Drag to place**: alternative — mouse-down on a tile, drag onto the canvas, release. Single-step. Useful for "drop one and immediately move it".

**Status hint while armed**: the status bar shows `Placing: gravity_well — click to drop, Esc to cancel`.

The current right-click-on-empty-canvas popup goes away. Right-click in object mode reverts to its old pre-popup behaviour (object deletion if hitting an existing object; otherwise no-op).

### 4.3 Mode-specific palette content

| Mode       | Palette contents                                                                |
|------------|---------------------------------------------------------------------------------|
| wall       | Wall tools: Draw, Line. Each is a tile with an icon. Selected tile = active tool. |
| object     | Sprite grid as described.                                                       |
| checkpoint | Single "Add checkpoint" tile (places at next click). Also list-of-checkpoints in the inspector. |
| band       | Single "Add band" tile (places at next click's Y).                              |

Replaces today's right-click-to-create flow consistently across modes.

## 5. Status bar slimming

After the inspector takes over selection details, the status bar collapses to:

```
[Mode: Object]  [Level 3]  [thrust_levels_export2.asm*]  [W=84 R=412]  |  Esc to cancel placement
```

- **Mode + level**: persistent left side.
- **File**: current file name, asterisk if dirty. Click to save (Ctrl+S equivalent).
- **Mouse coords**: world (W, R) coords of the cursor.
- **Right-aligned hint**: transient — current armed action, validation error, etc.

No selection-specific text in the status bar. If the user wants the old at-a-glance readout, they can keep their eye on the inspector, which is now the canonical place for it.

## 6. Implementation order

Each step ends with the editor still launchable and round-tripping `tools/output/thrust_levels_export2.asm` byte-identically. UI work shouldn't touch on-disk formats.

1. **Layout reservation.** Define `INSPECTOR_W` constant, reduce viewport width and toolbar width by it, draw a placeholder rectangle in the new right strip. Ship: editor launches, viewport is narrower, no functionality yet.
2. **Schema framework.** Define `Field` and `Schema` data classes. Build the registry: a function `schema_for_selection(editor) → list[Field]`. Wire up minimal level-properties schema (gravity / no_wrap_y / colours) and render it. No editing yet — read-only display.
3. **Numeric widgets — spinner.** Implement the `[- value +]` spinner with click handlers. Wire it through the field's setter. Verify Shift+click uses `shift_step`. Apply to byte / signed_byte / word fields.
4. **Numeric widgets — slider.** Drag-thumb slider, used for ranges where it reads better than a spinner (radius, strength, amplitude, phase). Either-or with the spinner per-field via a schema flag.
5. **Direct text entry.** Click value to switch to text mode; commit on Enter, revert on Esc, clamp on commit. Suppress global keymap while editing.
6. **Colour widget.** Inline 8-cell palette + optional "inherit" cell. Clicking commits.
7. **Enum widget.** Click-to-popup list. Used for: gun_aim base / spread, future door shape descriptor, side (left/right wall).
8. **Ref widget + Pick mode.** Wire up the teleporter destination first since it already exists as a click target. Verify the "Pick…" button arms canvas-click to write the index.
9. **Per-type schemas.** Author one schema per existing object type (gun, fuel, pod_stand, generator, door_switch, laser_turret, gravity_well, bobbing_mine, teleporter). Plus checkpoint and band schemas.
10. **Active-field + hotkey routing.** Replace the existing `_adjust_selected_*` keypress handlers with a single dispatcher that consults the active field's schema entry. Verify every existing shortcut keeps working through the new path. (Includes K/J for band colours, [/] / ,/. variants per field, +/- where applicable.)
11. **Sprite palette grid.** Render the grid in object mode with sprite tiles. Click-to-arm + click-to-place flow. Drag-to-place is a follow-up if click flow feels good.
12. **Wall / checkpoint / band palette tiles.** Replace right-click-to-create everywhere with palette-tile arming.
13. **Status bar slimming.** Remove all selection-specific text. Add the file-name + dirty marker click target. Add the mode-armed hint slot.
14. **Polish.** Highlight active field; tab / shift-tab focus cycle; flash on out-of-range commit; clamped text entry feedback. Resize behaviour: viewport width tracks window resize, inspector stays at `INSPECTOR_W`, palette grid re-flows columns if width ever becomes adjustable in a future iteration.
15. **Documentation update.** Move this entry from `docs/ideas.md` into Completed; cross-reference this plan; note any deferred follow-ups (multi-select, dockable panels, level-properties dialog, batched undo per slider drag).

Each step is independently shippable — the inspector is empty at step 1, has level properties at step 2, gains widgets one at a time through 3-7, becomes universal at 9-10, swallows the popup menu at 11-12.

## 7. Risks

- **Pygame UI cost.** The editor is currently a single immediate-mode draw loop with hand-rolled hit tests. Adding ~10 widget kinds + scrolling regions risks turning that loop into spaghetti. Mitigation: a tiny widget abstraction (`Widget.draw(rect, state)`, `Widget.handle_event(event, rect, state) -> dirty`) keeps each widget self-contained. Don't pull in `pygame_gui` or similar — the audience is one user and the existing visual language is plain rectangles + labels, which the abstraction matches.
- **Active-field hotkey ambiguity.** With many fields claiming `[`/`]`, the user has to know which is active. Mitigation: explicit border highlight on the active field; status hint when a hotkey fires shows "Radius +1" so the user sees what they edited. Keyboard tab cycles focus.
- **Power-user regression.** Existing muscle memory (right-click to insert, single keys for parameter tweaks) gets remapped. Mitigation: keep the hotkeys identical; the right-click *placement* popup is the one workflow change, and arm-then-click is one extra click for an authored sprite menu — net win once the grid is up.
- **Sprite tile rendering cost.** 12 sprite tiles re-rendered each frame is wasteful. Mitigation: render each tile once into a cached surface (already how the in-canvas sprite cache works); blit cached surfaces in the palette draw loop. Invalidate on level-colour change (bands / level swatches) the same way the canvas cache invalidates.
- **Inspector + active-field state vs. editor reload.** Switching levels resets selection to None, which is the level-properties schema. That should be the natural reset point. Test: switching levels mid-edit doesn't carry stale text-entry state across.
- **Direct text entry vs. global shortcuts.** It's easy to write a bug where global shortcuts fire while text entry is active. Mitigation: a single `editor.input_focus` flag short-circuits the global key dispatcher when the inspector or any text widget owns input.

## 8. Optional follow-ups (not v1)

- **Multi-select + bulk edit.** Shift-click adds to a selection set; the inspector shows fields common to all selected items, edits apply to all.
- **Drag-bezel resize for inspector width.** Per-user persisted in editor settings.
- **Inspector tabs.** Per-mode, e.g. an "All checkpoints" list view in checkpoint mode that lets you jump-edit any checkpoint without re-selecting on canvas.
- **Search bar.** "Filter to objects of type X", "show all bands with non-default colour", etc.
- **Batched undo.** Slider drag = one undo entry, not one-per-frame. Same for typed text.
- **Level-properties dialog.** A modal showing the full level metadata (terrain length, object count, RLE bytes used, exporter warnings) on demand.
