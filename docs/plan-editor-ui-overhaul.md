# Plan: Editor UI overhaul — right-pane inspector + sprite palette

**Status:** done (v1). Shipped in `5946c28` (inspector + palette) and `b39f1a8` (section headers, pinch tool, crosshair); later extended for switch wiring (`button` field kind, object refs) and doors. Sections below describe what was built in `tools/level_editor.py`; items not built are marked *deferred* and collected in §8 and in the [Completed](ideas.md#completed) entry in `docs/ideas.md`.

The status bar had become the main parameter readout for the selected item and the only place to see what `[`/`]`/`,`/`.`/`K`/`J`/`\` meant in the current context. Each new feature (band colours, teleporter destination, gravity well radius/strength, mine phase/amplitude, laser endpoint, gun aim/spread) added another key pair to the same row. The right-click placement popup had grown long enough that scanning it was slower than finding the sprite.

The overhaul replaces both with a fixed **right-hand pane**: a schema-driven inspector for the selection, and a palette for placement. Existing keyboard shortcuts keep working, and the status bar is slimmed down.

Tooling only: no engine change, no CRC impact.

## 1. Goals and non-goals

**Goals**

- One place to see and edit every parameter of the selected object / checkpoint / band, or the level when nothing is selected.
- Mouse-first editing (click to step, type values directly) alongside the existing keyboard shortcuts.
- A visual sprite palette for object placement instead of the right-click text list.
- Field schemas declared once per selection type, so adding a field is one entry.
- A status bar reduced to mode, level, file, cursor coordinates and a contextual hint.

**Non-goals (v1)**

- Multi-select / bulk edit.
- Resizable or dockable panes. Width is the constant `INSPECTOR_W`.
- A full level-properties dialog. Level-wide fields appear in the inspector when nothing is selected.
- Batched undo. Each inspector edit calls `undo.save()` once, as before.

## 2. Layout

`INSPECTOR_W = 300`. The toolbar, viewport and status bar are drawn `INSPECTOR_W` narrower; the pane occupies the right-hand strip for the full window height.

```
  ┌────────────────────────────────────────────────┬──────────────┐
  │ Toolbar (level tabs, mode tabs, file, Imp/Exp) │  Inspector   │
  ├────────────────────────────────────────────────┤  fields      │
  │                                                │  (40%)       │
  │             World viewport                     ├──────────────┤
  │                                                │  Palette     │
  │                                                │  (60%)       │
  ├────────────────────────────────────────────────┤              │
  │ Status bar                                     │              │
  └────────────────────────────────────────────────┴──────────────┘
```

On `VIDEORESIZE` the camera viewport becomes `event.w - INSPECTOR_W` wide. Mouse events with `x >= screen_width - INSPECTOR_W` go to `_handle_inspector_mouse_down`.

The pane is split at `inspector_split = 0.40` of the height between toolbar and status bar: fields above, palette below. Each section scrolls independently with the mouse wheel (`inspector_scroll`, `palette_scroll`). The divider is fixed; dragging it is *deferred*.

The toolbar lost the level-colour swatches, gravity ± buttons and Draw/Line buttons (now inspector fields and palette tiles) and gained the current file name with a `*` when dirty.

## 3. Inspector pane

### 3.1 Field schema

`class Field` (`tools/level_editor.py`) has these attributes:

| Attribute | Meaning |
|-----------|---------|
| `id`, `label` | Identifier and display name |
| `kind` | `byte`, `signed_byte`, `word`, `colour`, `enum`, `ref`, `readonly`, `header`, `button` |
| `getter`, `setter` | `getter(target)` / `setter(target, value)` |
| `min`, `max`, `step`, `shift_step` | Numeric range; Shift+click uses `shift_step` |
| `fmt` | Optional format string; otherwise `format_value` shows `$XX (n)`, `$XX (+n)` for signed, `$FFFF (disabled)` for a disabled word, colour names, or enum labels |
| `hotkey`, `hotkey_2` | Documentary only: the key pairs that the legacy handlers map to this field (see §3.4) |
| `allow_none` | Colour fields: adds an "inherit" cell (`None`) |
| `values` | Enum: list of `(label, value)` |
| `target_kind` | Ref: `"checkpoint"` or `"object"` |

There is no `applies_when` predicate. Per-type and per-shape variation is handled in `schema_for_selection` (for example, the door's "Opens" field only appears for `flat_window`, and its side field is relabelled "Wall").

### 3.2 Schemas per selection

`schema_for_selection(editor)` returns `(schema, target, level)`. Every schema starts with a `header` row (`Level N Objects` / `Bands` / `Checkpoints`, or `Level N` for no selection) followed by read-only `Index` and, for objects, `Type` (`name ($xx)`).

| Selection | Schema (after header rows) |
|-----------|----------------------------|
| None (any mode) | `SCHEMA_LEVEL`: Gravity (signed_byte), Land colour, Obj colour, No-wrap Y (word; `$FFFF` = disabled) |
| Band | `SCHEMA_BAND`: Y threshold, Gravity, Land colour, Obj colour (both colours allow inherit) |
| Checkpoint | `SCHEMA_CHECKPOINT`: Spawn X, Spawn Y, Window X, Window Y |
| Gun `$00..$03` | `SCHEMA_GUN`: X, Y, Base angle (enum, steps of 4), Spread (enum, 4 values) |
| Fuel `$04`, pod `$05`, generator `$06` | `SCHEMA_SIMPLE`: X, Y |
| Door switch `$07/$08` | `SCHEMA_DOOR_SWITCH`: X, Y, Side (enum over the type byte), then the switch wiring list: per entry Action / Target (object ref) / action-specific args, a Delete button, and "+ Add wiring" up to the 8-entry table cap |
| Laser turret `$09..$0C` | `SCHEMA_LASER`: X, Y, Phase (enum, ×8 frames), Duty (enum, ×4+4 frames), Beam dx, Beam dy |
| Gravity well `$0D` | `SCHEMA_GRAVITY_WELL`: X, Y, Radius (byte), Strength (signed) |
| Bobbing mine `$0E/$0F` | `SCHEMA_BOBBING_MINE`: X, Y, Amplitude (signed), Phase (byte) |
| Teleporter `$10` | `SCHEMA_TELEPORTER`: X, Y, Destination (ref → checkpoint) |
| Door `$11` | `SCHEMA_DOOR`: X, Y, Shape (enum: slot / notch_v / flat_window), Direction or Wall, Opens (flat_window only), Height, Open depth |

Selecting a wall has no schema; in wall mode the inspector shows level properties.

### 3.3 Field widgets

Each row is `FIELD_H = 26` px: label in the left `FIELD_LABEL_W = 90` px, widget to the right.

- **Spinner** (`byte`, `signed_byte`, `word`): `[-] value [+]`. Click `-`/`+` to step; Shift+click steps by `shift_step`. Values clamp to `min..max`. Clicking the value starts text entry (§3.5).
- **Colour**: inline row of 8 swatches, plus a "—" inherit cell when `allow_none`. Clicking a cell commits and clears the sprite cache so tinted sprites refresh.
- **Enum**: `◄ label ►`. Click an arrow to step through `values` with wrap-around; right-click anywhere on the row steps backwards. There is no popup list.
- **Ref**: current target text (`CP3: 172,1024` or `#5: Gravity well`) and a `Pick` button. Clicking the text cycles (left = forward, right = back); object refs include `$FF` ("(none)") as a stop. `Pick` arms a one-shot canvas click that writes the nearest checkpoint or object (by screen distance) into the field. Self-targeting is allowed.
- **Readonly / header**: text only. **Button**: full-width; click calls the setter (used for wiring Add/Delete).

A slider widget was planned but not built; the spinner covers every numeric range.

### 3.4 Keyboard shortcuts

Clicking a row sets `inspector_active_field`, which highlights the row. The planned schema-driven hotkey dispatcher was **not** built: `_handle_key` still routes `[`/`]`/`,`/`.` to the per-type `_adjust_selected_*` handlers (band gravity, well strength, mine amp/phase, teleporter destination, otherwise gun aim / laser phase-duty), `K`/`J` to `_cycle_band_colour`, and `\` to `_reset_selected_laser_endpoint`. Because those handlers edit the same dict keys the schemas read, the inspector reflects keyboard edits immediately. The `hotkey`/`hotkey_2` attributes record the mapping but nothing reads them. Tab / Shift+Tab focus cycling is *deferred*.

### 3.5 Direct text entry

Clicking a spinner's value sets `input_focus`; while it is set, `_handle_key` only handles Enter / keypad Enter (commit), Escape (cancel), Backspace, and printable characters into `text_entry_buf`, so global shortcuts are suppressed. `_parse_value` accepts decimal (including a leading `-`/`+`), `$XX`, `&XX` and `0xXX`. The result is clamped to the field's range on commit. Clicking another field or the canvas commits. The status hint reads "typing — Enter to commit, Esc to cancel". Tab-to-commit-and-advance and a red flash on out-of-range input are *deferred*.

### 3.6 No selection

With nothing selected the inspector shows `Level N` and the level-wide fields (§3.2). The toolbar copies of these controls were removed rather than kept as duplicates.

## 4. Palette

### 4.1 Object mode: sprite grid

Every type in `OBJECT_TYPE_NAMES` (`$00..$11`, 18 tiles) is drawn as a `PALETTE_TILE_W × PALETTE_TILE_H` (90×74) tile in a `PALETTE_COLS = 3` grid, scrolled by `palette_scroll`. Each tile shows the cached sprite from `SpriteCache.get(obj_type, level)` (tinted with the level colours) scaled to fit, and the type name truncated with `…`. There is no type-number badge. The armed tile is drawn green.

Types with no in-game sprite get a pictogram matching their canvas marker: door (frame and knob), teleporter (ring and centre dot), gravity well (concentric rings and centre dot). Guns and laser turrets keep four separate orientation tiles.

### 4.2 Placement

- **Click to arm**: clicking a tile arms that type (`palette_armed_type`); clicking it again disarms. A left-click on the canvas places one instance via `_place_armed_object` with type-appropriate defaults (well radius/strength, mine amplitude, door width and depth, laser dx/dy) and selects it. The palette then disarms, unless Shift is held, which keeps it armed for repeated placement.
- Right-click or Escape cancels an armed placement.
- Status hint while armed: `Placing: <name> — click to drop (Shift = keep armed), right-click/Esc to cancel`.
- Drag-to-place from a tile is *deferred*.

Right-click on the canvas in object mode no longer opens the popup. It disarms the palette and otherwise does nothing (objects are deleted with `Delete`). The old `show_obj_menu` / `_render_obj_menu` / `_handle_obj_menu_click` code is still present but unreachable.

### 4.3 Other modes

| Mode | Palette contents |
|------|------------------|
| wall | Draw and Line tool tiles; the active tool is highlighted. `L` still toggles. |
| checkpoint | A label tile, "Add checkpoint (right-click)". Not clickable; right-click on the canvas still adds a checkpoint. |
| band | A label tile, "Add band (right-click)". Not clickable; right-click still adds a band. |

Arming checkpoint/band creation from a palette tile was planned but not built.

## 5. Status bar

`_render_status` draws, left to right:

```
[Object]  [Level 3]  [thrust_levels_export2.asm*]  X=84 Y=412  L=40 R=96        <hint>
```

- Mode (wall mode adds the tool, e.g. `Wall (Line)`), level, and file name with `*` when dirty. The file name is not clickable; Ctrl+S quick-saves.
- Cursor world coordinates `X=`/`Y=`, and the actual left/right wall values at the cursor row (`-` when out of range).
- Right-aligned contextual hint: text entry, ref pick ("click a checkpoint on canvas to pick"), armed placement, line tool in progress, pinch drag, bottom/no-wrap handle, or per-mode guidance (wall pinch, right-click to add a checkpoint/band).

The status bar shows nothing specific to the selection.

### Wall-mode additions shipped with the overhaul

- A faint dotted crosshair follows the cursor.
- Shift+left-click on a wall "pinches" that row (`L = R`); dragging extends the same X across every row crossed. This is the authoring tool for rock bands (see [Disconnected caverns](ideas.md#disconnected-caverns)).
- The wall row highlight is a single row, red for the left wall and blue for the right, and follows the pointer during a drag.

## 6. Implementation order (as planned)

Kept for the record. Steps 1-9, 11 and 13 were done; 10 and 12 were not; 14 was partly done (active-field highlight only).

1. Layout reservation (`INSPECTOR_W`, narrower viewport and toolbar).
2. Schema framework and level-properties schema.
3. Spinner widget.
4. Slider widget. *Not built.*
5. Direct text entry with suppressed keymap.
6. Colour widget.
7. Enum widget (built as ◄/► stepper, not a popup).
8. Ref widget and Pick mode.
9. Per-type schemas, checkpoint and band schemas.
10. Active-field hotkey dispatcher replacing `_adjust_selected_*`. *Not built.*
11. Sprite palette grid, click-to-arm.
12. Palette tiles for checkpoint/band creation. *Not built; right-click still creates.*
13. Status bar slimming.
14. Polish: active-field highlight (done); Tab cycling, out-of-range flash (not built).
15. Move the ideas.md entry to Completed (done in `edb4dbf`).

## 7. Risks (as assessed at planning time)

- **Immediate-mode UI sprawl.** The editor is one draw loop with hand-rolled hit tests. Widgets were kept as per-kind render/click methods (`_render_spinner_widget`, `_handle_field_click`, …) rather than a widget class hierarchy. No third-party UI library. In practice the hit-test geometry is duplicated between render, hover and click code, which is the main maintenance cost.
- **Hotkey ambiguity.** Mitigated by leaving the legacy handlers in place rather than routing keys through the active field.
- **Sprite tile cost.** Tiles use `SpriteCache`, which caches the rendered sprite per colour set; scaling still happens every frame.
- **Stale text entry on level switch.** Switching level clears the selection, which resets the inspector to level properties.
- **Global shortcuts during text entry.** Handled by the `input_focus` early return in `_handle_key`.

## 8. Deferred follow-ups

- Slider widget.
- Single schema-driven hotkey dispatcher replacing `_adjust_selected_*`.
- Tab / Shift+Tab focus cycle; Tab commits text entry; red flash on out-of-range commit.
- Drag-to-place from a palette tile; palette tiles that arm checkpoint/band creation.
- Draggable inspector/palette divider; resizable inspector width.
- Remove the dead `obj_menu` code.
- Multi-select and bulk edit.
- Inspector tabs, e.g. an "all checkpoints" list in checkpoint mode.
- Search / filter ("objects of type X", "bands with non-default colour").
- Batched undo for repeated steps or typed edits.
- Level-properties dialog (terrain length, object count, RLE bytes, exporter warnings).
