#!/usr/bin/env python3
"""Interactive level editor for Thrust (BBC Micro) using PyGame.

Allows viewing and editing of terrain wall data and object placements
for all 6 levels. Edited levels can be exported as BeebAsm assembly.

Usage:
    python tools/level_editor.py [--level N] [--import FILE]

Controls:
    1-6         Switch level
    W           Wall editing mode
    O           Object editing mode
    Arrow keys  Pan view
    +/-         Zoom in/out
    Mouse wheel Zoom (centred on cursor)
    Home/End    Jump to top/bottom of level
    G           Toggle grid overlay
    Ctrl+Z      Undo
    Ctrl+Shift+Z Redo
    Ctrl+S      Export to assembly file
    Ctrl+I      Import from assembly file
    Delete      Delete selected object
    Escape      Deselect / cancel

Requires: pygame (pip install pygame)
"""

import copy
import math
import os
import sys
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

import pygame

# Import shared data and decoders from the visualisation tool
sys.path.insert(0, str(Path(__file__).parent))
from visualise_levels import (
    TERRAIN_DATA, OBJECT_DATA, SPRITE_DATA, OBJECT_TYPE_NAMES,
    BBC_COLOURS, LEVEL_LANDSCAPE_COLOUR, LEVEL_OBJECT_COLOUR,
    decode_wall, decode_level, get_objects,
    decode_sprite, decode_mode1_byte,
)

# Gun param data per level (extracted from thrust.6502)
GUN_PARAM_DATA = {
    0: [0x00, 0x00, 0x00, 0x1E],
    1: [0x00, 0x00, 0x00, 0x06, 0x0F],
    2: [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1B, 0x06, 0x0A, 0x16, 0x04],
    3: [0x00, 0x00, 0x00, 0x00, 0x00, 0x06, 0x06, 0x06, 0x12, 0x1F, 0x06, 0x1E],
    4: [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x05, 0x14, 0x1A, 0x02, 0x12, 0x1E, 0x19],
    5: [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1A, 0x06, 0x09, 0x12, 0x06, 0x16, 0x12, 0x1B, 0x12, 0x05, 0x0E],
}

# Per-level gravity (fractional part, extracted from thrust.6502:6625)
LEVEL_GRAVITY_FRAC = [0x05, 0x07, 0x09, 0x0B, 0x0C, 0x0D]

# Level reset / checkpoint data (extracted from thrust.6502:6542-6581)
# Each entry: {"spawn_x", "spawn_y", "window_x", "window_y"}
# spawn_y doubles as the Y threshold for zone matching.
LEVEL_RESET_DATA = {
    0: [{"spawn_x": 0x6C, "spawn_y": 0x0191, "window_x": 0x56, "window_y": 0x0124}],
    1: [{"spawn_x": 0x6C, "spawn_y": 0x0191, "window_x": 0x56, "window_y": 0x0124}],
    2: [{"spawn_x": 0x6C, "spawn_y": 0x0191, "window_x": 0x56, "window_y": 0x0124},
        {"spawn_x": 0x86, "spawn_y": 0x022D, "window_x": 0x6F, "window_y": 0x01AA},
        {"spawn_x": 0x48, "spawn_y": 0x0296, "window_x": 0x32, "window_y": 0x0223}],
    3: [{"spawn_x": 0x6C, "spawn_y": 0x0191, "window_x": 0x56, "window_y": 0x0124},
        {"spawn_x": 0x7B, "spawn_y": 0x01E6, "window_x": 0x57, "window_y": 0x0160},
        {"spawn_x": 0xA1, "spawn_y": 0x024A, "window_x": 0x76, "window_y": 0x01D8}],
    4: [{"spawn_x": 0x6C, "spawn_y": 0x0191, "window_x": 0x56, "window_y": 0x0124},
        {"spawn_x": 0x7B, "spawn_y": 0x0268, "window_x": 0x58, "window_y": 0x01EE},
        {"spawn_x": 0x6B, "spawn_y": 0x02DC, "window_x": 0x43, "window_y": 0x0266},
        {"spawn_x": 0x81, "spawn_y": 0x0315, "window_x": 0x64, "window_y": 0x029F}],
    5: [{"spawn_x": 0x6C, "spawn_y": 0x0191, "window_x": 0x56, "window_y": 0x0124},
        {"spawn_x": 0xA2, "spawn_y": 0x024B, "window_x": 0x8C, "window_y": 0x01D8},
        {"spawn_x": 0x9A, "spawn_y": 0x02D4, "window_x": 0x82, "window_y": 0x025A},
        {"spawn_x": 0x87, "spawn_y": 0x032A, "window_x": 0x6E, "window_y": 0x02B4},
        {"spawn_x": 0xAE, "spawn_y": 0x0398, "window_x": 0x87, "window_y": 0x031B}],
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_W, WINDOW_H = 1280, 800
TOOLBAR_H = 40
STATUS_H = 24
VIEWPORT_Y = TOOLBAR_H
VIEWPORT_H = WINDOW_H - TOOLBAR_H - STATUS_H

FPS = 60
ASPECT = 2.0  # 1 world X unit displays 2x wider than 1 world Y unit

# Colours
COL_BG = (0, 0, 0)
COL_TOOLBAR = (30, 30, 30)
COL_TOOLBAR_ACTIVE = (60, 60, 80)
COL_TOOLBAR_TEXT = (200, 200, 200)
COL_STATUS_BG = (20, 20, 20)
COL_STATUS_TEXT = (180, 180, 180)
COL_GRID = (40, 40, 40)
COL_SELECT = (255, 255, 0)
COL_HOVER = (255, 255, 100, 128)
COL_WALL_HIGHLIGHT = (255, 255, 0)

WALL_HIT_TOLERANCE = 5  # pixels

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hex_to_rgb(hex_colour):
    """Convert '#RRGGBB' to (R, G, B)."""
    return (int(hex_colour[1:3], 16), int(hex_colour[3:5], 16), int(hex_colour[5:7], 16))


def darken(rgb, factor=0.35):
    return (int(rgb[0] * factor), int(rgb[1] * factor), int(rgb[2] * factor))


# ---------------------------------------------------------------------------
# RLE Encoder
# ---------------------------------------------------------------------------

def encode_wall_rle(positions, start_xpos):
    """Re-encode wall position array back to RLE (counts, increments).

    The game uses two interleaved decoder triples per wall:
    - Triple 1 starts at segment 0 with a hardcoded counter of $FF
    - Triple 2 starts at segment 1 with a hardcoded counter of $FF
    Triple 2 overwrites triple 1, so the effective wall comes from triple 2.

    Segment 1 MUST have count=$FF because the game ignores count[1] and
    always uses its hardcoded initial counter of 255. The first 255 rows
    all use the same increment (inc[1]). Remaining data follows as seg2+.

    Segment 0 is filler for triple 1 (count ignored, uses hardcoded $FF).
    """
    if not positions:
        return [0xFF, 0xFF], [0x00, 0x00]

    # Segment 1 must be exactly 255 steps with a single increment.
    # Use the delta of the first position for all 255 steps (game constraint).
    seg1_inc = (positions[0] - start_xpos) & 0xFF if positions else 0x00

    # After 255 steps of seg1_inc, the decoder's X position will be:
    decoded_after_seg1 = (start_xpos + 255 * seg1_inc) & 0xFF

    # Compute remaining deltas relative to where the decoder will actually be,
    # NOT relative to positions[254]. These can differ when the first 255 rows
    # have non-uniform deltas that seg1_inc can't represent.
    remaining = []
    prev = decoded_after_seg1
    for x in positions[255:]:
        d = (x - prev) & 0xFF
        remaining.append(d)
        prev = x

    # RLE compress remaining deltas
    counts = []
    increments = []
    i = 0
    while i < len(remaining):
        current = remaining[i]
        run = 0
        while i < len(remaining) and remaining[i] == current and run < 0xFF:
            run += 1
            i += 1
        counts.append(run)
        increments.append(current)

    # seg0 (triple 1 filler) + seg1 ($FF fixed) + seg2+ (remaining RLE)
    final_counts = [0xFF, 0xFF] + counts
    final_increments = [0x00, seg1_inc] + increments

    # Ensure the data ends with a $FF-count, inc=0 terminator segment.
    # This prevents the decoder from exhausting the last segment and
    # reading past the end of the array. If the last segment already has
    # inc=0, just cap its count; otherwise append a new terminator.
    if final_increments[-1] == 0x00:
        final_counts[-1] = 0xFF
    else:
        final_counts.append(0xFF)
        final_increments.append(0x00)

    return final_counts, final_increments


def format_bytes(data):
    """Format byte list as BeebAsm EQUB data (no spaces, matching original style)."""
    return ",".join(f"${b:02X}" for b in data)


def parse_equb_line(line):
    """Parse an EQUB line and return list of integer values."""
    # Strip comment
    line = line.split("\\")[0].strip()
    if "EQUB" not in line.upper():
        return []
    _, _, rest = line.partition("EQUB")
    rest = rest.strip()
    values = []
    for tok in rest.split(","):
        tok = tok.strip()
        if tok.startswith("$"):
            values.append(int(tok[1:], 16))
        elif tok.startswith("&"):
            values.append(int(tok[1:], 16))
        elif tok.isdigit():
            values.append(int(tok))
    return values


def import_beebasm(path):
    """Import level data from an exported BeebAsm assembly file.

    Returns a list of 6 LevelData objects.
    """
    text = Path(path).read_text()
    lines = text.splitlines()

    # Build a dict mapping label -> list of bytes from the EQUB line(s) that follow
    labels = {}
    current_label = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(".") and not stripped.startswith("\\"):
            current_label = stripped[1:]  # remove leading dot
            labels[current_label] = []
        elif current_label and "EQUB" in line.upper():
            labels[current_label].extend(parse_equb_line(line))
        elif stripped == "" or stripped.startswith("\\"):
            pass  # blank or comment line, keep current_label
        else:
            current_label = None

    levels = []
    for n in range(6):
        # Terrain RLE data
        lc = labels.get(f"terrain_left_wall_count_{n}", [])
        li = labels.get(f"terrain_left_wall_inc_{n}", [])
        rc = labels.get(f"terrain_right_wall_count_{n}", [])
        ri = labels.get(f"terrain_right_wall_inc_{n}", [])
        terrain_rle = {
            "left_count": list(lc), "left_inc": list(li),
            "right_count": list(rc), "right_inc": list(ri),
        }

        # Decode walls from RLE
        left_wall = decode_wall(lc, li, start_xpos=0x00, start_segment=1)
        right_wall = decode_wall(rc, ri, start_xpos=0xFF, start_segment=1)

        # Object data
        obj_x = labels.get(f"level_{n}_obj_pos_X", [])
        obj_y = labels.get(f"level_{n}_obj_pos_Y", [])
        obj_y_ext = labels.get(f"level_{n}_obj_pos_Y_EXT", [])
        obj_type = labels.get(f"level_{n}_obj_type", [])
        gun_param = labels.get(f"level_{n}_gun_param", [])

        # Remove $FF terminator from type list
        types = [t for t in obj_type if t != 0xFF]

        objects = []
        for i in range(len(types)):
            y_world = ((obj_y_ext[i] if i < len(obj_y_ext) else 0) << 8) | \
                      (obj_y[i] if i < len(obj_y) else 0)
            gp = gun_param[i] if i < len(gun_param) else 0x00
            objects.append({
                "x": obj_x[i] if i < len(obj_x) else 0,
                "y": y_world,
                "type": types[i],
                "gun_param": gp,
            })

        # Colours (may not be present in older exports)
        lc_colours = labels.get("level_landscape_colour", [])
        oc_colours = labels.get("level_object_colour", [])
        land_col = lc_colours[n] if n < len(lc_colours) else None
        obj_col = oc_colours[n] if n < len(oc_colours) else None

        # Checkpoints (may not be present in older exports)
        reset_sizes = labels.get("level_reset_data_sizes", [])
        reset_data = labels.get(f"level_{n}_reset_data", [])
        checkpoints = None
        if n < len(reset_sizes) and reset_data:
            s = reset_sizes[n]
            if len(reset_data) >= s * 6:
                checkpoints = []
                for i in range(s):
                    checkpoints.append({
                        "spawn_x":  reset_data[5*s + i],
                        "spawn_y":  (reset_data[0*s + i] << 8) | reset_data[1*s + i],
                        "window_x": reset_data[2*s + i],
                        "window_y": (reset_data[3*s + i] << 8) | reset_data[4*s + i],
                    })

        # Gravity (may not be present in older exports)
        gravity_table = labels.get("level_gravity_FRAC_table", [])
        grav = gravity_table[n] if n < len(gravity_table) else None

        lv = LevelData(n, list(left_wall), list(right_wall), objects,
                        terrain_rle, land_col, obj_col, checkpoints, grav)
        levels.append(lv)

    return levels


def _clamp_converging_walls(left, right):
    """Clamp wall arrays for EOR-safe encoding, returning the truncation point.

    The game draws terrain using EOR (exclusive-or) delta rendering: each
    frame, only the columns that changed are toggled. Two issues arise when
    walls converge:

    1. If left[row] jumps past right[row-1] (or vice versa), the EOR draws
       for both walls overlap on some columns. Those columns get toggled
       twice and remain as black gaps instead of solid rock.

    2. Once walls meet (gap=0), any variation in position creates wall edge
       movement in what should be solid rock, causing further EOR artifacts.

    Fix: limit each wall's per-row movement so it never crosses the other
    wall's previous position. Returns the row index where the walls first
    meet (gap <= 1), or None if they never meet. The caller should only
    encode positions up to (and including) that row.

    Operates on copies — does not truncate the source arrays.
    """
    min_len = min(len(left), len(right))

    # Pass 1: prevent EOR overlap by limiting per-row wall movement.
    # Left can't advance past previous row's right; right can't retreat
    # past previous row's left.
    for row in range(1, min_len):
        if left[row] > right[row - 1]:
            left[row] = right[row - 1]
        if right[row] < left[row - 1]:
            right[row] = left[row - 1]
        if left[row] > right[row]:
            mid = (left[row] + right[row]) // 2
            left[row] = mid
            right[row] = mid

    # Pass 2: find where walls first meet (gap <= 1). Rows beyond this
    # point are solid rock and should not be encoded — the encoder's $FF
    # terminator segment will keep both walls frozen indefinitely.
    for row in range(min_len):
        if right[row] - left[row] <= 1:
            frozen = (left[row] + right[row]) // 2
            left[row] = frozen
            right[row] = frozen
            return row
    return None


def _has_wall_issues(left, right):
    """Check if decoded wall data has wall crossings (left >= right)."""
    for row in range(min(len(left), len(right))):
        if left[row] >= right[row]:
            return True
    return False


def export_beebasm(levels):
    """Generate BeebAsm assembly source for terrain and object data."""
    lines = []
    lines.append("\\ ******************************************************************************")
    lines.append("\\ ******************************************************************************")
    lines.append("\\ * Level data - landscape / terrain, objects")
    lines.append("\\ ******************************************************************************")
    lines.append("\\ ******************************************************************************")
    lines.append("")
    lines.append("\\ ******************************************************************************")
    lines.append("\\ * Terrain data per level - left count & inc same length, right count & inc same length")
    lines.append("\\ * Terrain pointers set to left or right wall count & increment arrays")
    lines.append("\\ ******************************************************************************")
    lines.append("")

    # Terrain data for all levels first, then object data
    for lv in levels:
        n = lv.level_num
        if lv.terrain_dirty:
            # Clamp walls for EOR rendering compatibility. The game's EOR
            # renderer double-toggles pixels when left and right wall edges
            # overlap during scrolling. To prevent artifacts:
            # 1. Left must never exceed right
            # 2. Once walls meet, freeze both at a fixed position so there
            #    is no wall edge movement in the solid rock area
            left = list(lv.left_wall)
            right = list(lv.right_wall)
            freeze_row = _clamp_converging_walls(left, right)
            # Encode only up to the freeze point — the encoder's $FF
            # terminator keeps walls frozen for all rows beyond it
            end = freeze_row + 1 if freeze_row is not None else len(left)
            lc, li = encode_wall_rle(left[:end], 0x00)
            rc, ri = encode_wall_rle(right[:end], 0xFF)
        else:
            # Use original RLE data, but verify no wall crossings exist
            # (could happen if imported from a previous buggy export)
            lc = lv.terrain_rle["left_count"]
            li = lv.terrain_rle["left_inc"]
            rc = lv.terrain_rle["right_count"]
            ri = lv.terrain_rle["right_inc"]
            # Decode and check for crossings
            left_check = decode_wall(lc, li, start_xpos=0x00, start_segment=1)
            right_check = decode_wall(rc, ri, start_xpos=0xFF, start_segment=1)
            if _has_wall_issues(left_check, right_check):
                freeze_row = _clamp_converging_walls(left_check, right_check)
                end = freeze_row + 1 if freeze_row is not None else len(left_check)
                lc, li = encode_wall_rle(left_check[:end], 0x00)
                rc, ri = encode_wall_rle(right_check[:end], 0xFF)

        lines.append(f".terrain_left_wall_count_{n}")
        lines.append(f"        EQUB    {format_bytes(lc)}")
        lines.append(f".terrain_left_wall_inc_{n}")
        lines.append(f"        EQUB    {format_bytes(li)}")
        lines.append(f".terrain_right_wall_count_{n}")
        lines.append(f"        EQUB    {format_bytes(rc)}")
        lines.append(f".terrain_right_wall_inc_{n}")
        lines.append(f"        EQUB    {format_bytes(ri)}")
        if n < 5:
            lines.append("")

    lines.append("")
    lines.append("\\ ******************************************************************************")
    lines.append("\\ * Level object data")
    lines.append("\\ ******************************************************************************")
    lines.append("")

    for lv in levels:
        n = lv.level_num
        # Pod (type $05) must be first object — game hardcodes index 0
        # for tractor beam interaction (level_obj_flags without ,X index)
        obj = sorted(lv.objects, key=lambda o: (0 if o['type'] == 0x05 else 1))
        if obj:
            lines.append(f".level_{n}_obj_pos_X")
            lines.append(f"        EQUB    {format_bytes([o['x'] for o in obj])}")
            lines.append(f".level_{n}_obj_pos_Y")
            lines.append(f"        EQUB    {format_bytes([o['y'] & 0xFF for o in obj])}")
            lines.append(f".level_{n}_obj_pos_Y_EXT")
            lines.append(f"        EQUB    {format_bytes([o['y'] >> 8 for o in obj])}")
            lines.append(f".level_{n}_obj_type")
            lines.append(f"        EQUB    {format_bytes([o['type'] for o in obj] + [0xFF])}")
            lines.append(f".level_{n}_gun_param")
            lines.append(f"        EQUB    {format_bytes([o.get('gun_param', 0x00) for o in obj])}")
            lines.append("")

    # Gravity table
    lines.append("\\ ******************************************************************************")
    lines.append("\\ * Gravity values per level")
    lines.append("\\ ******************************************************************************")
    lines.append("")
    lines.append(".level_gravity_FRAC_table")
    lines.append(f"        EQUB    {format_bytes([lv.gravity for lv in levels])}")
    lines.append("")

    # Colour tables
    lines.append("\\ ******************************************************************************")
    lines.append("\\ * Level colours")
    lines.append("\\ ******************************************************************************")
    lines.append("")
    lines.append(".level_landscape_colour")
    lines.append(f"        EQUB    {format_bytes([lv.landscape_colour for lv in levels])}")
    lines.append(".level_object_colour")
    lines.append(f"        EQUB    {format_bytes([lv.object_colour for lv in levels])}")
    lines.append("")

    # Checkpoint / reset data
    lines.append("\\ ******************************************************************************")
    lines.append("\\ * Level reset data - respawn checkpoints")
    lines.append("\\ * Struct-of-arrays: Y_HI, Y_LO, win_X, win_Y_EXT, win_Y, spawn_X")
    lines.append("\\ ******************************************************************************")
    lines.append("")
    lines.append(".level_reset_data_sizes")
    lines.append(f"        EQUB    {format_bytes([len(lv.checkpoints) for lv in levels])}")
    lines.append("")
    for lv in levels:
        n = lv.level_num
        cps = lv.checkpoints
        s = len(cps)
        # Encode as struct-of-arrays: 6 rows of 's' bytes each
        y_hi =    [cp["spawn_y"] >> 8 for cp in cps]
        y_lo =    [cp["spawn_y"] & 0xFF for cp in cps]
        win_x =   [cp["window_x"] & 0xFF for cp in cps]
        win_y_ext = [cp["window_y"] >> 8 for cp in cps]
        win_y =   [cp["window_y"] & 0xFF for cp in cps]
        spawn_x = [cp["spawn_x"] & 0xFF for cp in cps]
        flat = y_hi + y_lo + win_x + win_y_ext + win_y + spawn_x
        lines.append(f".level_{n}_reset_data")
        # Format as rows of 's' bytes for readability
        for row_start in range(0, len(flat), s):
            lines.append(f"        EQUB    {format_bytes(flat[row_start:row_start+s])}")
        lines.append("")

    # Pointer tables
    lines.append(".level_reset_ptr_table_LO")
    for n in range(6):
        lines.append(f"        EQUB    LO(level_{n}_reset_data)")
    lines.append(".level_reset_ptr_table_HI")
    for n in range(6):
        lines.append(f"        EQUB    HI(level_{n}_reset_data)")
    lines.append("")
    lines.append(".level_reset_ptr2_table_LO")
    for lv in levels:
        s = len(lv.checkpoints)
        lines.append(f"        EQUB    LO(level_{lv.level_num}_reset_data + {s})")
    lines.append(".level_reset_ptr2_table_HI")
    for lv in levels:
        s = len(lv.checkpoints)
        lines.append(f"        EQUB    HI(level_{lv.level_num}_reset_data + {s})")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Level Data Model
# ---------------------------------------------------------------------------

BBC_COLOUR_NAMES = {
    0: "Black", 1: "Red", 2: "Green", 3: "Yellow",
    4: "Blue", 5: "Magenta", 6: "Cyan", 7: "White",
}


class LevelData:
    """Mutable level state: decoded walls + object list."""

    def __init__(self, level_num, left_wall, right_wall, objects,
                 terrain_rle=None, landscape_colour=None, object_colour=None,
                 checkpoints=None, gravity=None):
        self.level_num = level_num
        self.left_wall = left_wall   # list[int] X per Y row
        self.right_wall = right_wall
        self.objects = objects        # list[dict] with x, y, type, gun_param keys
        self.terrain_rle = terrain_rle  # original RLE arrays {"A","B","C","D"}
        self.landscape_colour = landscape_colour if landscape_colour is not None \
            else LEVEL_LANDSCAPE_COLOUR[level_num]  # BBC physical colour 0-7
        self.object_colour = object_colour if object_colour is not None \
            else LEVEL_OBJECT_COLOUR[level_num]      # BBC physical colour 0-7
        self.checkpoints = checkpoints if checkpoints is not None \
            else [dict(cp) for cp in LEVEL_RESET_DATA[level_num]]
        self.gravity = gravity if gravity is not None \
            else LEVEL_GRAVITY_FRAC[level_num]       # Q0.8 fractional gravity
        self.dirty = False
        self.terrain_dirty = False    # True when walls have been edited

    @classmethod
    def from_game_data(cls, level_num):
        left, right = decode_level(level_num)
        # Store original RLE data for byte-identical export
        td = TERRAIN_DATA[level_num]
        terrain_rle = {k: list(v) for k, v in td.items()}
        # Build objects with gun_param
        od = OBJECT_DATA[level_num]
        # Get gun_param from the source data
        gun_params = GUN_PARAM_DATA.get(level_num, [])
        objects = []
        for i in range(len(od["type"])):
            y_world = (od["Y_EXT"][i] << 8) | od["Y"][i]
            gp = gun_params[i] if i < len(gun_params) else 0x00
            objects.append({"x": od["X"][i], "y": y_world,
                            "type": od["type"][i], "gun_param": gp})
        return cls(level_num, list(left), list(right), objects, terrain_rle)

    @property
    def num_rows(self):
        return max(len(self.left_wall), len(self.right_wall))


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

class Camera:
    """Viewport camera with pan and zoom."""

    def __init__(self):
        self.world_x = 0.0    # world X at left edge of viewport
        self.world_y = 0.0    # world Y at top edge of viewport
        self.zoom = 2.0       # pixels per world Y unit (base scale)
        self.viewport_w = WINDOW_W
        self.viewport_h = VIEWPORT_H

    @property
    def x_scale(self):
        """Pixels per world X unit."""
        return self.zoom * ASPECT

    @property
    def y_scale(self):
        """Pixels per world Y unit."""
        return self.zoom

    def world_to_screen(self, wx, wy):
        """Convert world coords to screen pixel coords."""
        sx = (wx - self.world_x) * self.x_scale
        sy = (wy - self.world_y) * self.y_scale + VIEWPORT_Y
        return sx, sy

    def screen_to_world(self, sx, sy):
        """Convert screen pixel coords to world coords."""
        wx = sx / self.x_scale + self.world_x
        wy = (sy - VIEWPORT_Y) / self.y_scale + self.world_y
        return wx, wy

    def visible_y_range(self):
        """Return (y_min, y_max) of visible world Y rows."""
        y_min = max(0, int(self.world_y))
        y_max = int(self.world_y + self.viewport_h / self.y_scale) + 1
        return y_min, y_max

    def visible_x_range(self):
        """Return (x_min, x_max) of visible world X."""
        x_min = max(0, self.world_x)
        x_max = self.world_x + self.viewport_w / self.x_scale
        return x_min, min(256, x_max)

    def zoom_at(self, screen_x, screen_y, factor):
        """Zoom centred on a screen position."""
        wx, wy = self.screen_to_world(screen_x, screen_y)
        self.zoom = max(0.5, min(20.0, self.zoom * factor))
        # Adjust offset so (wx, wy) stays at (screen_x, screen_y)
        self.world_x = wx - screen_x / self.x_scale
        self.world_y = wy - (screen_y - VIEWPORT_Y) / self.y_scale

    def pan(self, dx_world, dy_world):
        self.world_x += dx_world
        self.world_y += dy_world

    def jump_to_y(self, y):
        self.world_y = y


# ---------------------------------------------------------------------------
# Sprite Cache
# ---------------------------------------------------------------------------

# Upright ship sprite (angle 0) decoded from ship_sprite_0_data in thrust.6502.
# The ship uses XOR wireframe plotting in Mode 1; this is the actual pixel data.
# Pixel x range in the decoded sprite is 9-23 (out of a 32-pixel plotting area).
# The offset of 9 Mode 1 pixels = 2.25 world X units from the plotting origin.
_SHIP_PIXEL_OFFSET_X = 9  # leftmost pixel column in the decoded sprite
_SHIP_BITMAP = [
    ".......#.......",
    "......#.#......",
    "......#.#......",
    ".....#...#.....",
    ".....#...#.....",
    "....#.....#....",
    "....#.....#....",
    "...#.......#...",
    "...#.......#...",
    ".##.........##.",
    "#.............#",
    ".#...........#.",
    "..#.........#..",
    "..#...###...#..",
    "...#.#...#.#...",
    "....#.....#....",
]


class SpriteCache:
    """Caches decoded sprites as PyGame surfaces per (obj_type, landscape_col, object_col)."""

    def __init__(self):
        self._cache = {}
        self._ship_surf = None

    def get(self, obj_type, level):
        """Get cached sprite. level is a LevelData instance."""
        key = (obj_type, level.landscape_colour, level.object_colour)
        if key not in self._cache:
            self._cache[key] = self._render(obj_type, level)
        return self._cache[key]

    def get_ship(self):
        """Get the upright ship sprite surface (always yellow)."""
        if self._ship_surf is None:
            w = len(_SHIP_BITMAP[0])
            h = len(_SHIP_BITMAP)
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            for y, row in enumerate(_SHIP_BITMAP):
                for x, ch in enumerate(row):
                    if ch == '#':
                        surf.set_at((x, y), (255, 255, 0, 200))
            self._ship_surf = surf
        return self._ship_surf

    def clear(self):
        self._cache.clear()
        self._ship_surf = None

    def _render(self, obj_type, level):
        if obj_type not in SPRITE_DATA:
            return None
        pixel_array = decode_sprite(obj_type)
        h, w = pixel_array.shape

        palette = {
            0: (0, 0, 0, 0),
            1: (255, 255, 0, 255),
            2: hex_to_rgb(BBC_COLOURS[level.landscape_colour]) + (255,),
            3: hex_to_rgb(BBC_COLOURS[level.object_colour]) + (255,),
        }

        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            for x in range(w):
                surf.set_at((x, y), palette[pixel_array[y, x]])
        return surf


# ---------------------------------------------------------------------------
# Undo System
# ---------------------------------------------------------------------------

class UndoManager:
    """Simple snapshot-based undo/redo."""

    def __init__(self, max_size=100):
        self.stack = []
        self.redo_stack = []
        self.max_size = max_size

    def save(self, level):
        """Save a snapshot before making changes."""
        snapshot = (
            list(level.left_wall),
            list(level.right_wall),
            copy.deepcopy(level.objects),
        )
        self.stack.append((level.level_num, snapshot))
        if len(self.stack) > self.max_size:
            self.stack.pop(0)
        self.redo_stack.clear()

    def undo(self, levels):
        """Restore the most recent snapshot."""
        if not self.stack:
            return False
        lvn, (left, right, objs) = self.stack.pop()
        lv = levels[lvn]
        # Save current state for redo
        self.redo_stack.append((lvn, (list(lv.left_wall), list(lv.right_wall),
                                      copy.deepcopy(lv.objects))))
        lv.left_wall = left
        lv.right_wall = right
        lv.objects = objs
        lv.dirty = True
        return True

    def redo(self, levels):
        if not self.redo_stack:
            return False
        lvn, (left, right, objs) = self.redo_stack.pop()
        lv = levels[lvn]
        self.stack.append((lvn, (list(lv.left_wall), list(lv.right_wall),
                                  copy.deepcopy(lv.objects))))
        lv.left_wall = left
        lv.right_wall = right
        lv.objects = objs
        lv.dirty = True
        return True


# ---------------------------------------------------------------------------
# Editor
# ---------------------------------------------------------------------------

class Editor:
    def __init__(self, start_level=0, import_path=None):
        pygame.init()
        pygame.display.set_caption("Thrust Level Editor")
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 14)
        self.font_small = pygame.font.SysFont("consolas", 12)

        if import_path:
            self.levels = import_beebasm(import_path)
            print(f"Imported level data from {import_path}")
        else:
            self.levels = [LevelData.from_game_data(i) for i in range(6)]
        self.current_level = start_level
        self.camera = Camera()
        self.sprite_cache = SpriteCache()
        self.undo = UndoManager()

        self.mode = "wall"   # "wall", "object", or "checkpoint"
        self.show_grid = False
        self.running = True

        # Editing state
        self.dragging_wall = None     # ("left"|"right", start_row, saved_snapshot)
        self.drag_start_y = None
        self.selected_object = None   # index into objects list
        self.dragging_object = False
        self.hovered_wall = None      # ("left"|"right", row)
        self.hovered_object = None    # index
        self.wall_tool = "draw"       # "draw" (freehand) or "line"
        self.line_start = None        # ("left"|"right", row, x) for line tool
        self.selected_checkpoint = None  # index into checkpoints list
        self.dragging_checkpoint = None  # ("spawn"|"window", index)

        # Panning state
        self.panning = False
        self.pan_start = None

        # Object creation menu
        self.show_obj_menu = False
        self.obj_menu_pos = (0, 0)
        self.obj_menu_world = (0, 0)

        # Centre view on level
        self._centre_on_level()

    @property
    def level(self):
        return self.levels[self.current_level]

    def _centre_on_level(self):
        """Centre camera to show the whole level."""
        lv = self.level
        total_h = lv.num_rows
        # Fit level height into viewport
        self.camera.zoom = max(0.5, self.camera.viewport_h / total_h * 0.9)
        # Centre horizontally
        visible_w = self.camera.viewport_w / self.camera.x_scale
        self.camera.world_x = (256 - visible_w) / 2
        self.camera.world_y = -total_h * 0.05

    def run(self):
        while self.running:
            self._handle_events()
            self._render()
            self.clock.tick(FPS)
        pygame.quit()

    # -------------------------------------------------------------------
    # Event handling
    # -------------------------------------------------------------------

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.VIDEORESIZE:
                self.camera.viewport_w = event.w
                self.camera.viewport_h = event.h - TOOLBAR_H - STATUS_H

            elif event.type == pygame.KEYDOWN:
                self._handle_key(event)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_mouse_down(event)

            elif event.type == pygame.MOUSEBUTTONUP:
                self._handle_mouse_up(event)

            elif event.type == pygame.MOUSEMOTION:
                self._handle_mouse_move(event)

            elif event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                if my > TOOLBAR_H and my < self.screen.get_height() - STATUS_H:
                    factor = 1.15 if event.y > 0 else 1 / 1.15
                    self.camera.zoom_at(mx, my, factor)

        # Continuous keyboard panning
        keys = pygame.key.get_pressed()
        pan_speed = 5.0 / self.camera.zoom
        if keys[pygame.K_LEFT]:
            self.camera.pan(-pan_speed, 0)
        if keys[pygame.K_RIGHT]:
            self.camera.pan(pan_speed, 0)
        if keys[pygame.K_UP]:
            self.camera.pan(0, -pan_speed)
        if keys[pygame.K_DOWN]:
            self.camera.pan(0, pan_speed)

    def _handle_key(self, event):
        mods = pygame.key.get_mods()
        ctrl = mods & pygame.KMOD_CTRL
        shift = mods & pygame.KMOD_SHIFT

        # Level switching: 1-6
        if event.key in (pygame.K_1, pygame.K_2, pygame.K_3,
                         pygame.K_4, pygame.K_5, pygame.K_6):
            self.current_level = event.key - pygame.K_1
            self._centre_on_level()
            self.selected_object = None
            self.dragging_wall = None

        elif event.key == pygame.K_w:
            self.mode = "wall"
            self.selected_object = None
            self.selected_checkpoint = None

        elif event.key == pygame.K_l:
            if self.mode == "wall":
                self.wall_tool = "line" if self.wall_tool != "line" else "draw"
                self.line_start = None

        elif event.key == pygame.K_c:
            self.mode = "checkpoint"
            self.dragging_wall = None
            self.line_start = None
            self.selected_object = None

        elif event.key == pygame.K_o:
            self.mode = "object"
            self.dragging_wall = None
            self.line_start = None
            self.selected_checkpoint = None

        elif event.key == pygame.K_g:
            self.show_grid = not self.show_grid

        elif event.key == pygame.K_HOME:
            self.camera.jump_to_y(0)

        elif event.key == pygame.K_END:
            self.camera.jump_to_y(self.level.num_rows - self.camera.viewport_h / self.camera.y_scale)

        elif event.key == pygame.K_EQUALS or event.key == pygame.K_PLUS:
            cx = self.screen.get_width() / 2
            cy = VIEWPORT_Y + self.camera.viewport_h / 2
            self.camera.zoom_at(cx, cy, 1.25)

        elif event.key == pygame.K_MINUS:
            cx = self.screen.get_width() / 2
            cy = VIEWPORT_Y + self.camera.viewport_h / 2
            self.camera.zoom_at(cx, cy, 1 / 1.25)

        elif event.key == pygame.K_z and ctrl:
            if shift:
                self.undo.redo(self.levels)
            else:
                self.undo.undo(self.levels)

        elif event.key == pygame.K_s and ctrl:
            self._export()

        elif event.key == pygame.K_i and ctrl:
            self._import()

        elif event.key == pygame.K_ESCAPE:
            if self.line_start:
                self.line_start = None

        elif event.key == pygame.K_DELETE:
            if self.selected_object is not None and self.mode == "object":
                self.undo.save(self.level)
                self.level.objects.pop(self.selected_object)
                self.level.dirty = True
                self.selected_object = None
            elif self.selected_checkpoint is not None and self.mode == "checkpoint":
                if len(self.level.checkpoints) > 1:
                    self.undo.save(self.level)
                    self.level.checkpoints.pop(self.selected_checkpoint)
                    self.level.dirty = True
                    self.selected_checkpoint = None

        elif event.key == pygame.K_ESCAPE:
            self.selected_object = None
            self.selected_checkpoint = None
            self.dragging_wall = None
            self.show_obj_menu = False

    def _handle_mouse_down(self, event):
        mx, my = event.pos

        # Toolbar click
        if my < TOOLBAR_H:
            self._handle_toolbar_click(mx, my)
            return

        # Below viewport
        if my > self.screen.get_height() - STATUS_H:
            return

        # Object creation menu
        if self.show_obj_menu:
            self._handle_obj_menu_click(mx, my)
            return

        wx, wy = self.camera.screen_to_world(mx, my)

        # Middle button or right button panning
        if event.button == 2:
            self.panning = True
            self.pan_start = (mx, my)
            return

        if event.button == 3:  # Right click
            if self.mode == "object":
                # Open object creation menu
                self.show_obj_menu = True
                self.obj_menu_pos = (mx, my)
                self.obj_menu_world = (int(wx), int(wy))
            elif self.mode == "checkpoint":
                self._handle_checkpoint_right_click(mx, my)
            return

        # Left click
        if event.button == 1:
            if self.mode == "wall" and self.wall_tool == "line":
                self._handle_line_tool_click(mx, my)
            elif self.mode == "wall":
                hit = self._hit_test_wall(mx, my)
                if hit:
                    side, row = hit
                    self.undo.save(self.level)
                    self.dragging_wall = (side, row)
                    self.drag_start_y = row
                else:
                    # Start panning if clicking in empty space
                    self.panning = True
                    self.pan_start = (mx, my)

            elif self.mode == "checkpoint":
                hit = self._hit_test_checkpoint(mx, my)
                if hit:
                    part, idx = hit
                    self.selected_checkpoint = idx
                    # Store grab offset: mouse world pos minus stored origin
                    cp = self.level.checkpoints[idx]
                    if part == "spawn":
                        ox = cp["spawn_x"]
                        oy = cp["spawn_y"]
                    else:
                        ox = cp["window_x"]
                        oy = cp["window_y"] + 73  # viewport displays at +73
                    grab_dx = wx - ox
                    grab_dy = wy - oy
                    self.dragging_checkpoint = (part, idx, grab_dx, grab_dy)
                    self.undo.save(self.level)
                else:
                    self.selected_checkpoint = None
                    self.panning = True
                    self.pan_start = (mx, my)

            elif self.mode == "object":
                hit = self._hit_test_object(mx, my)
                if hit is not None:
                    self.selected_object = hit
                    self.dragging_object = True
                    self.undo.save(self.level)
                else:
                    self.selected_object = None
                    # Pan
                    self.panning = True
                    self.pan_start = (mx, my)

    def _handle_mouse_up(self, event):
        if event.button in (1, 2):
            self.panning = False
            self.pan_start = None
            if self.dragging_wall:
                self.level.dirty = True
                self.dragging_wall = None
                self.drag_start_y = None
            if self.dragging_object:
                self.level.dirty = True
                self.dragging_object = False
            if self.dragging_checkpoint:
                self.level.dirty = True
                self.dragging_checkpoint = None

    def _handle_mouse_move(self, event):
        mx, my = event.pos

        if self.panning and self.pan_start:
            dx = self.pan_start[0] - mx
            dy = self.pan_start[1] - my
            self.camera.pan(dx / self.camera.x_scale, dy / self.camera.y_scale)
            self.pan_start = (mx, my)
            return

        if self.dragging_wall:
            wx, wy = self.camera.screen_to_world(mx, my)
            side = self.dragging_wall[0]
            wall = self.level.left_wall if side == "left" else self.level.right_wall

            # Determine Y range for multi-row editing
            row = max(0, min(int(wy), len(wall) - 1))
            new_x = max(0, min(255, int(wx)))
            wall[row] = new_x
            self.level.terrain_dirty = True

            # Also set nearby rows when dragging vertically for smooth editing
            if self.drag_start_y is not None:
                start_row = self.drag_start_y
                end_row = row
                if start_row != end_row:
                    step = 1 if end_row > start_row else -1
                    for r in range(start_row, end_row + step, step):
                        if 0 <= r < len(wall):
                            wall[r] = new_x
                self.drag_start_y = row
            return

        if self.dragging_checkpoint:
            wx, wy = self.camera.screen_to_world(mx, my)
            part, idx, grab_dx, grab_dy = self.dragging_checkpoint
            cp = self.level.checkpoints[idx]
            if part == "spawn":
                cp["spawn_x"] = max(0, min(255, int(wx - grab_dx)))
                cp["spawn_y"] = max(0, min(0xFFFF, int(wy - grab_dy)))
            else:  # "window"
                cp["window_x"] = max(0, min(255, int(wx - grab_dx)))
                cp["window_y"] = max(0, min(0xFFFF, int(wy - grab_dy - 73)))
            return

        if self.dragging_object and self.selected_object is not None:
            wx, wy = self.camera.screen_to_world(mx, my)
            obj = self.level.objects[self.selected_object]
            obj["x"] = max(0, min(255, int(wx)))
            obj["y"] = max(0, int(wy))
            return

        # Hover detection
        if my > TOOLBAR_H and my < self.screen.get_height() - STATUS_H:
            if self.mode == "wall":
                self.hovered_wall = self._hit_test_wall(mx, my)
            elif self.mode == "object":
                self.hovered_object = self._hit_test_object(mx, my)

    def _hit_test_wall(self, mx, my):
        """Test if screen position is near a wall edge. Returns (side, row) or None."""
        wx, wy = self.camera.screen_to_world(mx, my)
        row = int(wy)
        lv = self.level

        if row < 0 or row >= lv.num_rows:
            return None

        # Check left wall
        if row < len(lv.left_wall):
            wall_sx, _ = self.camera.world_to_screen(lv.left_wall[row], row)
            if abs(mx - wall_sx) < WALL_HIT_TOLERANCE:
                return ("left", row)

        # Check right wall
        if row < len(lv.right_wall):
            wall_sx, _ = self.camera.world_to_screen(lv.right_wall[row], row)
            if abs(mx - wall_sx) < WALL_HIT_TOLERANCE:
                return ("right", row)

        return None

    def _handle_line_tool_click(self, mx, my):
        """Handle a click in line tool mode."""
        wx, wy = self.camera.screen_to_world(mx, my)
        row = int(wy)
        lv = self.level

        if self.line_start is None:
            # First click: set start point (must be near a wall)
            hit = self._hit_test_wall(mx, my)
            if hit:
                side, r = hit
                wall = lv.left_wall if side == "left" else lv.right_wall
                self.line_start = (side, r, wall[r])
            else:
                # Click in empty space - start panning
                self.panning = True
                self.pan_start = (mx, my)
        else:
            # Second click: apply the line
            side = self.line_start[0]
            wall = lv.left_wall if side == "left" else lv.right_wall
            end_row = max(0, min(int(wy), len(wall) - 1))
            end_x = max(0, min(255, int(wx)))
            self.undo.save(lv)
            self._apply_line(wall, self.line_start[1], self.line_start[2],
                             end_row, end_x)
            lv.terrain_dirty = True
            lv.dirty = True
            self.line_start = None

    def _apply_line(self, wall, r0, x0, r1, x1):
        """Set wall positions along a straight line from (r0, x0) to (r1, x1)."""
        if r0 == r1:
            if 0 <= r0 < len(wall):
                wall[r0] = max(0, min(255, x1))
            return
        dr = r1 - r0
        step = 1 if dr > 0 else -1
        for r in range(r0, r1 + step, step):
            if 0 <= r < len(wall):
                t = (r - r0) / dr
                x = int(round(x0 + t * (x1 - x0)))
                wall[r] = max(0, min(255, x))

    def _hit_test_checkpoint(self, mx, my):
        """Test if screen position hits a checkpoint marker.
        Returns ("spawn"|"window", index) or None."""
        lv = self.level
        cam = self.camera
        ship_surf = self.sprite_cache.get_ship()
        ship_world_w = ship_surf.get_width() / 4
        ship_world_h = ship_surf.get_height() / 2
        ship_offset_x = _SHIP_PIXEL_OFFSET_X / 4
        for i, cp in enumerate(lv.checkpoints):
            # Check spawn marker (ship sprite bounding box)
            sx, sy = cam.world_to_screen(cp["spawn_x"] + ship_offset_x,
                                         cp["spawn_y"])
            ex, ey = cam.world_to_screen(cp["spawn_x"] + ship_offset_x + ship_world_w,
                                         cp["spawn_y"] + ship_world_h)
            if sx <= mx < ex and sy <= my < ey:
                return ("spawn", i)
            # Check viewport rectangle edges (72x111, offset 73 from window_y)
            vp_top = cp["window_y"] + 73
            vp_x0, vp_y0 = cam.world_to_screen(cp["window_x"], vp_top)
            vp_x1, vp_y1 = cam.world_to_screen(cp["window_x"] + 72,
                                                 vp_top + 111)
            near_edge = 8  # pixel tolerance
            in_x = vp_x0 - near_edge <= mx <= vp_x1 + near_edge
            in_y = vp_y0 - near_edge <= my <= vp_y1 + near_edge
            near_left = abs(mx - vp_x0) < near_edge
            near_right = abs(mx - vp_x1) < near_edge
            near_top = abs(my - vp_y0) < near_edge
            near_bottom = abs(my - vp_y1) < near_edge
            if (in_y and (near_left or near_right)) or \
               (in_x and (near_top or near_bottom)):
                return ("window", i)
        return None

    def _handle_checkpoint_right_click(self, mx, my):
        """Right-click in checkpoint mode: add or delete checkpoint."""
        hit = self._hit_test_checkpoint(mx, my)
        if hit:
            # Delete checkpoint (but keep at least one)
            _, idx = hit
            if len(self.level.checkpoints) > 1:
                self.undo.save(self.level)
                self.level.checkpoints.pop(idx)
                self.level.dirty = True
                self.selected_checkpoint = None
        else:
            # Add new checkpoint at click position
            wx, wy = self.camera.screen_to_world(mx, my)
            spawn_x = max(0, min(255, int(wx)))
            spawn_y = max(0, min(0xFFFF, int(wy)))
            # Window position offset: camera centred roughly 110 rows above spawn
            window_y = max(0, spawn_y - 110)
            window_x = max(0, min(255, spawn_x - 22))
            self.undo.save(self.level)
            self.level.checkpoints.append({
                "spawn_x": spawn_x, "spawn_y": spawn_y,
                "window_x": window_x, "window_y": window_y,
            })
            # Sort by spawn_y ascending (game scans top to bottom)
            self.level.checkpoints.sort(key=lambda c: c["spawn_y"])
            self.level.dirty = True
            self.selected_checkpoint = len(self.level.checkpoints) - 1

    def _hit_test_object(self, mx, my):
        """Test if screen position hits an object sprite. Returns index or None."""
        lv = self.level
        for i, obj in enumerate(lv.objects):
            sprite = self.sprite_cache.get(obj["type"], lv)
            if sprite is None:
                continue
            ox, oy = obj["x"], obj["y"]
            # Sprite dimensions in world coords
            sw = sprite.get_width() / 4  # 4 pixels per world X unit
            sh = sprite.get_height() / 2  # 2 pixels per world Y unit

            sx, sy = self.camera.world_to_screen(ox, oy - 1)
            ex, ey = self.camera.world_to_screen(ox + sw, oy - 1 + sh)

            if sx <= mx <= ex and sy <= my <= ey:
                return i
        return None

    def _handle_toolbar_click(self, mx, my):
        """Handle clicks in the toolbar area."""
        # Level tabs: 6 tabs of 60px each starting at x=10
        tab_x = 10
        for i in range(6):
            if tab_x <= mx < tab_x + 55:
                self.current_level = i
                self._centre_on_level()
                self.selected_object = None
                return
            tab_x += 60

        # Mode buttons
        mode_x = 380
        if mode_x <= mx < mode_x + 60:
            self.mode = "wall"
            self.selected_object = None
            self.selected_checkpoint = None
        elif mode_x + 65 <= mx < mode_x + 130:
            self.mode = "object"
            self.dragging_wall = None
            self.line_start = None
            self.selected_checkpoint = None
        elif mode_x + 135 <= mx < mode_x + 195:
            self.mode = "checkpoint"
            self.dragging_wall = None
            self.line_start = None
            self.selected_object = None

        # Wall tool buttons (Draw / Line)
        tool_x = 590
        if self.mode == "wall":
            if tool_x <= mx < tool_x + 50:
                self.wall_tool = "draw"
                self.line_start = None
            elif tool_x + 55 <= mx < tool_x + 105:
                self.wall_tool = "line"
                self.line_start = None

        # Colour swatches - hit test on swatch rectangles
        col_x = 710
        lv = self.level
        for attr in ("landscape_colour", "object_colour"):
            label = "Land" if attr == "landscape_colour" else "Obj"
            label_w = self.font.size(label)[0]
            swatch_x = col_x + label_w + 4
            if swatch_x <= mx < swatch_x + 24:
                cur = getattr(lv, attr)
                # Cycle through 1-7 (skip 0/black)
                new_col = (cur % 7) + 1
                setattr(lv, attr, new_col)
                lv.dirty = True
                self.sprite_cache.clear()
                return
            phys_col = getattr(lv, attr)
            name_w = self.font_small.size(BBC_COLOUR_NAMES[phys_col])[0]
            col_x = swatch_x + 28 + name_w + 12

        # Gravity +/- buttons
        grav_x = col_x
        grav_label_w = self.font.size("Grav")[0]
        val_x = grav_x + grav_label_w + 4
        if val_x <= mx < val_x + 18:  # minus button
            lv.gravity = max(0, lv.gravity - 1)
            lv.dirty = True
            return
        val_txt_w = self.font.size(f"${lv.gravity:02X}")[0]
        plus_x = val_x + 22 + val_txt_w + 4
        if plus_x <= mx < plus_x + 18:  # plus button
            lv.gravity = min(0xFF, lv.gravity + 1)
            lv.dirty = True
            return

        # Import button
        import_x = self.screen.get_width() - 200
        if import_x <= mx < import_x + 90:
            self._import()

        # Export button
        export_x = self.screen.get_width() - 100
        if export_x <= mx < export_x + 90:
            self._export()

    def _handle_obj_menu_click(self, mx, my):
        """Handle clicks on the object creation popup menu."""
        menu_x, menu_y = self.obj_menu_pos
        menu_w, menu_h = 160, len(OBJECT_TYPE_NAMES) * 22 + 4

        if not (menu_x <= mx < menu_x + menu_w and menu_y <= my < menu_y + menu_h):
            self.show_obj_menu = False
            return

        idx = (my - menu_y - 2) // 22
        types = sorted(OBJECT_TYPE_NAMES.keys())
        if 0 <= idx < len(types):
            obj_type = types[idx]
            self.undo.save(self.level)
            wx, wy = self.obj_menu_world
            self.level.objects.append({"x": wx, "y": wy, "type": obj_type, "gun_param": 0x00})
            self.level.dirty = True
            self.selected_object = len(self.level.objects) - 1
        self.show_obj_menu = False

    def _export(self):
        """Export level data to assembly file via file dialog."""
        root = tk.Tk()
        root.withdraw()
        default_path = Path("tools/output/thrust_levels_export.asm").resolve()
        path = filedialog.asksaveasfilename(
            title="Export level data",
            initialdir=str(default_path.parent),
            initialfile=default_path.name,
            defaultextension=".asm",
            filetypes=[("BeebAsm assembly", "*.asm"), ("All files", "*.*")],
        )
        root.destroy()
        if not path:
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        src = export_beebasm(self.levels)
        Path(path).write_text(src)
        print(f"Exported to {path}")

    def _import(self):
        """Import level data from assembly file via file dialog."""
        root = tk.Tk()
        root.withdraw()
        default_path = Path("tools/output/thrust_levels_export.asm").resolve()
        path = filedialog.askopenfilename(
            title="Import level data",
            initialdir=str(default_path.parent),
            defaultextension=".asm",
            filetypes=[("BeebAsm assembly", "*.asm"), ("All files", "*.*")],
        )
        root.destroy()
        if not path:
            return
        self.levels = import_beebasm(path)
        self._centre_on_level()
        self.selected_object = None
        self.dragging_wall = None
        self.undo = UndoManager()
        print(f"Imported from {path}")

    # -------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------

    def _render(self):
        screen = self.screen
        screen.fill(COL_BG)

        self._render_terrain()
        if self.show_grid:
            self._render_grid()
        self._render_objects()
        self._render_checkpoints()
        self._render_wall_highlights()
        self._render_toolbar()
        self._render_status()
        if self.show_obj_menu:
            self._render_obj_menu()

        pygame.display.flip()

    def _render_terrain(self):
        """Draw the terrain (rock fills + wall edges)."""
        lv = self.level
        cam = self.camera
        screen = self.screen
        sw = screen.get_width()

        landscape_rgb = hex_to_rgb(BBC_COLOURS[lv.landscape_colour])
        rock_rgb = darken(landscape_rgb)

        y_min, y_max = cam.visible_y_range()
        y_max = min(y_max, lv.num_rows)

        # Clip to viewport
        clip_rect = pygame.Rect(0, VIEWPORT_Y, sw, cam.viewport_h)
        screen.set_clip(clip_rect)

        for row in range(y_min, y_max):
            _, sy = cam.world_to_screen(0, row)
            _, sy_next = cam.world_to_screen(0, row + 1)
            row_h = max(1, int(sy_next - sy))

            if sy + row_h < VIEWPORT_Y or sy > VIEWPORT_Y + cam.viewport_h:
                continue

            # Rows beyond either wall array are closed (solid rock)
            if row >= len(lv.left_wall) or row >= len(lv.right_wall):
                continue
            left_x = lv.left_wall[row]
            right_x = lv.right_wall[row]

            if right_x - left_x <= 1:
                continue

            # Left rock: world 0 to left_x
            lsx, _ = cam.world_to_screen(0, row)
            lex, _ = cam.world_to_screen(left_x, row)
            x1, x2 = int(lsx), int(lex)
            if x2 > x1 and x2 > 0 and x1 < sw:
                x1 = max(0, x1)
                pygame.draw.rect(screen, rock_rgb,
                                 (x1, int(sy), x2 - x1, row_h))

            # Right rock: right_x to world 256
            rsx, _ = cam.world_to_screen(right_x, row)
            rex, _ = cam.world_to_screen(256, row)
            x1, x2 = int(rsx), int(rex)
            if x2 > x1 and x2 > 0 and x1 < sw:
                x1 = max(0, x1)
                pygame.draw.rect(screen, rock_rgb,
                                 (x1, int(sy), x2 - x1, row_h))

            # Wall edge highlights (thin lines)
            pygame.draw.rect(screen, landscape_rgb,
                             (int(lex) - 1, int(sy), 2, row_h))
            pygame.draw.rect(screen, landscape_rgb,
                             (int(rsx) - 1, int(sy), 2, row_h))

        # Fill solid rock above and below the cave
        # Find first and last cave rows
        first_cave = None
        last_cave = None
        min_len = min(len(lv.left_wall), len(lv.right_wall))
        for row in range(min_len):
            if lv.right_wall[row] - lv.left_wall[row] > 1:
                if first_cave is None:
                    first_cave = row
                last_cave = row

        if first_cave is not None:
            # World X bounds in screen coords
            wx0, _ = cam.world_to_screen(0, 0)
            wx256, _ = cam.world_to_screen(256, 0)
            rock_sx = max(0, int(wx0))
            rock_w = int(wx256) - rock_sx

            # Rock below cave
            _, below_sy = cam.world_to_screen(0, last_cave + 1)
            _, bottom = cam.world_to_screen(0, lv.num_rows)
            if below_sy < VIEWPORT_Y + cam.viewport_h:
                pygame.draw.rect(screen, rock_rgb,
                                 (rock_sx, int(below_sy), rock_w, int(bottom - below_sy) + 1))

            # Sky rows within the cave region that are "all rock"
            for row in range(max(y_min, first_cave), min(y_max, last_cave + 1)):
                if row >= len(lv.left_wall) or row >= len(lv.right_wall):
                    continue
                if lv.right_wall[row] - lv.left_wall[row] <= 1:
                    _, sy = cam.world_to_screen(0, row)
                    _, sy_next = cam.world_to_screen(0, row + 1)
                    row_h = max(1, int(sy_next - sy))
                    pygame.draw.rect(screen, rock_rgb,
                                     (rock_sx, int(sy), rock_w, row_h))

        screen.set_clip(None)

    def _render_grid(self):
        """Draw a grid overlay."""
        cam = self.camera
        screen = self.screen
        sw = screen.get_width()

        clip_rect = pygame.Rect(0, VIEWPORT_Y, sw, cam.viewport_h)
        screen.set_clip(clip_rect)

        # Choose grid spacing based on zoom
        if cam.zoom >= 4:
            spacing = 10
        elif cam.zoom >= 1:
            spacing = 50
        else:
            spacing = 100

        y_min, y_max = cam.visible_y_range()
        x_min, x_max = cam.visible_x_range()

        # Horizontal grid lines
        for y in range(int(y_min // spacing) * spacing, int(y_max) + spacing, spacing):
            _, sy = cam.world_to_screen(0, y)
            if VIEWPORT_Y <= sy <= VIEWPORT_Y + cam.viewport_h:
                pygame.draw.line(screen, COL_GRID, (0, int(sy)), (sw, int(sy)))

        # Vertical grid lines
        for x in range(int(x_min // spacing) * spacing, int(x_max) + spacing, spacing):
            sx, _ = cam.world_to_screen(x, 0)
            if 0 <= sx <= sw:
                pygame.draw.line(screen, COL_GRID,
                                 (int(sx), VIEWPORT_Y),
                                 (int(sx), VIEWPORT_Y + cam.viewport_h))

        screen.set_clip(None)

    def _render_objects(self):
        """Draw object sprites."""
        lv = self.level
        cam = self.camera
        screen = self.screen

        clip_rect = pygame.Rect(0, VIEWPORT_Y, screen.get_width(), cam.viewport_h)
        screen.set_clip(clip_rect)

        for i, obj in enumerate(lv.objects):
            sprite = self.sprite_cache.get(obj["type"], lv)
            if sprite is None:
                continue

            ox, oy = obj["x"], obj["y"]
            # Sprite world dimensions
            sw = sprite.get_width() / 4  # 4 pixels per world X unit
            sh = sprite.get_height() / 2  # 2 pixels per world Y unit

            sx, sy = cam.world_to_screen(ox, oy)
            ex, ey = cam.world_to_screen(ox + sw, oy + sh)
            draw_w = max(1, int(ex - sx))
            draw_h = max(1, int(ey - sy))

            scaled = pygame.transform.scale(sprite, (draw_w, draw_h))
            screen.blit(scaled, (int(sx), int(sy)))

            # Selection highlight
            if i == self.selected_object:
                pygame.draw.rect(screen, COL_SELECT,
                                 (int(sx) - 2, int(sy) - 2, draw_w + 4, draw_h + 4), 2)

            # Hover highlight
            elif i == self.hovered_object and self.mode == "object":
                pygame.draw.rect(screen, (200, 200, 200),
                                 (int(sx) - 1, int(sy) - 1, draw_w + 2, draw_h + 2), 1)

        screen.set_clip(None)

    def _render_checkpoints(self):
        """Draw checkpoint markers as horizontal lines with spawn position dots."""
        lv = self.level
        cam = self.camera
        screen = self.screen
        sw = screen.get_width()

        clip_rect = pygame.Rect(0, VIEWPORT_Y, sw, cam.viewport_h)
        screen.set_clip(clip_rect)

        ship_surf = self.sprite_cache.get_ship()
        # Ship world dimensions (same convention as object sprites)
        ship_world_w = ship_surf.get_width() / 4   # 4 Mode 1 pixels per world X
        ship_world_h = ship_surf.get_height() / 2  # half-res vertical rendering
        ship_offset_x = _SHIP_PIXEL_OFFSET_X / 4   # plotting origin to first pixel

        for i, cp in enumerate(lv.checkpoints):
            # Sprite is plotted at top-left origin + inherent pixel offset
            sx_tl, sy_tl = cam.world_to_screen(
                cp["spawn_x"] + ship_offset_x, cp["spawn_y"])
            sx_win, sy_win = cam.world_to_screen(cp["window_x"], cp["window_y"])

            # Scale ship sprite to match current zoom
            ex, ey = cam.world_to_screen(
                cp["spawn_x"] + ship_offset_x + ship_world_w,
                cp["spawn_y"] + ship_world_h)
            draw_w = max(1, int(ex - sx_tl))
            draw_h = max(1, int(ey - sy_tl))

            if sy_tl + draw_h < VIEWPORT_Y - 20 or sy_tl > VIEWPORT_Y + cam.viewport_h + 20:
                continue

            # Dashed horizontal line at spawn Y
            line_col = (100, 200, 255) if self.mode == "checkpoint" else (60, 120, 160)
            dash_len = 8
            for dx in range(0, sw, dash_len * 2):
                pygame.draw.line(screen, line_col,
                                 (dx, int(sy_tl)), (min(dx + dash_len, sw), int(sy_tl)))

            # Draw ship sprite at top-left
            highlight = (self.mode == "checkpoint" and
                         self.selected_checkpoint == i)
            scaled = pygame.transform.scale(ship_surf, (draw_w, draw_h))
            if highlight:
                bright = scaled.copy()
                bright.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGBA_ADD)
                screen.blit(bright, (int(sx_tl), int(sy_tl)))
            else:
                screen.blit(scaled, (int(sx_tl), int(sy_tl)))

            # Selection outline
            if highlight:
                pygame.draw.rect(screen, (255, 255, 100),
                                 (int(sx_tl) - 1, int(sy_tl) - 1,
                                  draw_w + 2, draw_h + 2), 1)

            # Label
            label = f"CP{i}"
            txt = self.font_small.render(label, True, line_col)
            screen.blit(txt, (4, int(sy_tl) - 14))

            # Game viewport rectangle (72 wide x 111 tall, offset 73 rows from window_y)
            if self.mode == "checkpoint":
                vp_top = cp["window_y"] + 73
                vp_x0, vp_y0 = cam.world_to_screen(cp["window_x"], vp_top)
                vp_x1, vp_y1 = cam.world_to_screen(cp["window_x"] + 72,
                                                     vp_top + 111)
                vp_w = int(vp_x1 - vp_x0)
                vp_h = int(vp_y1 - vp_y0)
                vp_col = (120, 180, 220) if highlight else (60, 100, 140)
                # Dotted rectangle
                dash = 6
                for edge_x in range(int(vp_x0), int(vp_x1), dash * 2):
                    ex = min(edge_x + dash, int(vp_x1))
                    pygame.draw.line(screen, vp_col,
                                     (edge_x, int(vp_y0)), (ex, int(vp_y0)))
                    pygame.draw.line(screen, vp_col,
                                     (edge_x, int(vp_y1)), (ex, int(vp_y1)))
                for edge_y in range(int(vp_y0), int(vp_y1), dash * 2):
                    ey = min(edge_y + dash, int(vp_y1))
                    pygame.draw.line(screen, vp_col,
                                     (int(vp_x0), edge_y), (int(vp_x0), ey))
                    pygame.draw.line(screen, vp_col,
                                     (int(vp_x1), edge_y), (int(vp_x1), ey))

        screen.set_clip(None)

    def _render_wall_highlights(self):
        """Draw highlights on hovered/dragged wall edges."""
        if self.mode != "wall":
            return

        cam = self.camera
        screen = self.screen

        # Line tool: show start marker and preview line
        if self.wall_tool == "line" and self.line_start:
            side, r0, x0 = self.line_start
            # Draw start point marker
            sx0, sy0 = cam.world_to_screen(x0, r0)
            _, sy0_next = cam.world_to_screen(0, r0 + 1)
            h0 = max(1, int(sy0_next - sy0))
            pygame.draw.rect(screen, (0, 255, 128),
                             (int(sx0) - 4, int(sy0), 8, h0))

            # Draw preview line to mouse position
            mx, my = pygame.mouse.get_pos()
            wx, wy = cam.screen_to_world(mx, my)
            wall = self.level.left_wall if side == "left" else self.level.right_wall
            r1 = max(0, min(int(wy), len(wall) - 1))
            x1 = max(0, min(255, int(wx)))
            if r0 != r1:
                dr = r1 - r0
                step = 1 if dr > 0 else -1
                for r in range(r0, r1 + step, step):
                    if 0 <= r < len(wall):
                        t = (r - r0) / dr
                        x = int(round(x0 + t * (x1 - x0)))
                        x = max(0, min(255, x))
                        sx, sy = cam.world_to_screen(x, r)
                        _, sy_next = cam.world_to_screen(0, r + 1)
                        h = max(1, int(sy_next - sy))
                        pygame.draw.rect(screen, (0, 200, 100),
                                         (int(sx) - 2, int(sy), 4, h))
            return

        highlight = self.hovered_wall or (self.dragging_wall[:2] if self.dragging_wall else None)
        if not highlight:
            return

        side, row = highlight
        lv = self.level
        wall = lv.left_wall if side == "left" else lv.right_wall
        if row < 0 or row >= len(wall):
            return

        # Highlight a range of rows around the hovered point
        for r in range(max(0, row - 2), min(len(wall), row + 3)):
            sx, sy = cam.world_to_screen(wall[r], r)
            _, sy_next = cam.world_to_screen(0, r + 1)
            h = max(1, int(sy_next - sy))
            pygame.draw.rect(screen, COL_WALL_HIGHLIGHT,
                             (int(sx) - 3, int(sy), 6, h))

    def _render_toolbar(self):
        """Draw the top toolbar."""
        screen = self.screen
        sw = screen.get_width()
        pygame.draw.rect(screen, COL_TOOLBAR, (0, 0, sw, TOOLBAR_H))
        pygame.draw.line(screen, (60, 60, 60), (0, TOOLBAR_H - 1), (sw, TOOLBAR_H - 1))

        # Level tabs
        tab_x = 10
        for i in range(6):
            col = COL_TOOLBAR_ACTIVE if i == self.current_level else COL_TOOLBAR
            rect = pygame.Rect(tab_x, 5, 55, 30)
            pygame.draw.rect(screen, col, rect, border_radius=4)
            pygame.draw.rect(screen, (80, 80, 80), rect, 1, border_radius=4)

            label = f"Lv {i + 1}"
            if self.levels[i].dirty:
                label += "*"
            txt = self.font.render(label, True, COL_TOOLBAR_TEXT)
            screen.blit(txt, (tab_x + 8, 12))
            tab_x += 60

        # Mode buttons
        mode_x = 380
        for mode_name, offset in [("Wall", 0), ("Object", 65), ("Chkpt", 135)]:
            col = COL_TOOLBAR_ACTIVE if self.mode == mode_name.lower() \
                or (mode_name == "Chkpt" and self.mode == "checkpoint") else COL_TOOLBAR
            rect = pygame.Rect(mode_x + offset, 5, 60, 30)
            pygame.draw.rect(screen, col, rect, border_radius=4)
            pygame.draw.rect(screen, (80, 80, 80), rect, 1, border_radius=4)
            txt = self.font.render(mode_name, True, COL_TOOLBAR_TEXT)
            screen.blit(txt, (mode_x + offset + 8, 12))

        # Wall tool buttons (Draw / Line) - only shown in wall mode
        if self.mode == "wall":
            tool_x = 590
            for tool_name, offset in [("Draw", 0), ("Line", 55)]:
                col = COL_TOOLBAR_ACTIVE if self.wall_tool == tool_name.lower() else COL_TOOLBAR
                rect = pygame.Rect(tool_x + offset, 5, 50, 30)
                pygame.draw.rect(screen, col, rect, border_radius=4)
                pygame.draw.rect(screen, (80, 80, 80), rect, 1, border_radius=4)
                txt = self.font.render(tool_name, True, COL_TOOLBAR_TEXT)
                screen.blit(txt, (tool_x + offset + 6, 12))

        # Colour swatches
        col_x = 710
        lv = self.level
        for label, phys_col in [("Land", lv.landscape_colour),
                                ("Obj", lv.object_colour)]:
            txt = self.font.render(label, True, COL_TOOLBAR_TEXT)
            screen.blit(txt, (col_x, 12))
            swatch_x = col_x + txt.get_width() + 4
            swatch_rgb = hex_to_rgb(BBC_COLOURS[phys_col])
            rect = pygame.Rect(swatch_x, 8, 24, 24)
            pygame.draw.rect(screen, swatch_rgb, rect, border_radius=3)
            pygame.draw.rect(screen, (120, 120, 120), rect, 1, border_radius=3)
            name_txt = self.font_small.render(BBC_COLOUR_NAMES[phys_col], True,
                                              COL_TOOLBAR_TEXT)
            screen.blit(name_txt, (swatch_x + 28, 14))
            col_x = swatch_x + 28 + name_txt.get_width() + 12

        # Gravity control
        grav_x = col_x
        txt = self.font.render("Grav", True, COL_TOOLBAR_TEXT)
        screen.blit(txt, (grav_x, 12))
        val_x = grav_x + txt.get_width() + 4
        # - button
        rect = pygame.Rect(val_x, 8, 18, 24)
        pygame.draw.rect(screen, (50, 50, 50), rect, border_radius=3)
        pygame.draw.rect(screen, (80, 80, 80), rect, 1, border_radius=3)
        txt = self.font.render("-", True, COL_TOOLBAR_TEXT)
        screen.blit(txt, (val_x + 5, 10))
        # value
        val_txt = self.font.render(f"${lv.gravity:02X}", True, COL_TOOLBAR_TEXT)
        screen.blit(val_txt, (val_x + 22, 12))
        # + button
        plus_x = val_x + 22 + val_txt.get_width() + 4
        rect = pygame.Rect(plus_x, 8, 18, 24)
        pygame.draw.rect(screen, (50, 50, 50), rect, border_radius=3)
        pygame.draw.rect(screen, (80, 80, 80), rect, 1, border_radius=3)
        txt = self.font.render("+", True, COL_TOOLBAR_TEXT)
        screen.blit(txt, (plus_x + 4, 10))

        # Import button
        import_x = sw - 200
        rect = pygame.Rect(import_x, 5, 90, 30)
        pygame.draw.rect(screen, (40, 40, 60), rect, border_radius=4)
        pygame.draw.rect(screen, (80, 80, 80), rect, 1, border_radius=4)
        txt = self.font.render("Import", True, (150, 150, 255))
        screen.blit(txt, (import_x + 16, 12))

        # Export button
        export_x = sw - 100
        rect = pygame.Rect(export_x, 5, 90, 30)
        pygame.draw.rect(screen, (40, 60, 40), rect, border_radius=4)
        pygame.draw.rect(screen, (80, 80, 80), rect, 1, border_radius=4)
        txt = self.font.render("Export", True, (150, 255, 150))
        screen.blit(txt, (export_x + 18, 12))

    def _render_status(self):
        """Draw the status bar."""
        screen = self.screen
        sw = screen.get_width()
        sh = screen.get_height()
        pygame.draw.rect(screen, COL_STATUS_BG, (0, sh - STATUS_H, sw, STATUS_H))

        mx, my = pygame.mouse.get_pos()
        wx, wy = self.camera.screen_to_world(mx, my)

        mode_label = self.mode.title()
        if self.mode == "wall":
            mode_label += f" ({self.wall_tool.title()})"
        parts = [f"Mode: {mode_label}"]
        parts.append(f"X={int(wx)}  Y={int(wy)}")

        lv = self.level
        row = int(wy)
        if 0 <= row < lv.num_rows:
            lx = lv.left_wall[row] if row < len(lv.left_wall) else None
            rx = lv.right_wall[row] if row < len(lv.right_wall) else None
            if lx is not None and rx is not None:
                parts.append(f"Left=${lx:02X}  Right=${rx:02X}")

        parts.append(f"Zoom: {self.camera.zoom:.1f}x")

        if self.line_start:
            side, r, x = self.line_start
            parts.append(f"Line: {side} from row {r} x={x} -- click to set end")

        if self.selected_object is not None:
            obj = lv.objects[self.selected_object]
            name = OBJECT_TYPE_NAMES.get(obj["type"], f"?{obj['type']}")
            parts.append(f"Selected: {name} @ ({obj['x']}, {obj['y']})")

        if self.selected_checkpoint is not None and self.selected_checkpoint < len(lv.checkpoints):
            cp = lv.checkpoints[self.selected_checkpoint]
            parts.append(f"CP{self.selected_checkpoint}: spawn=({cp['spawn_x']}, {cp['spawn_y']})  "
                         f"window=({cp['window_x']}, {cp['window_y']})")

        if self.mode == "checkpoint":
            parts.append(f"{len(lv.checkpoints)} checkpoint(s)")

        status = "  |  ".join(parts)
        txt = self.font_small.render(status, True, COL_STATUS_TEXT)
        screen.blit(txt, (10, sh - STATUS_H + 5))

    def _render_obj_menu(self):
        """Draw the object creation popup menu."""
        screen = self.screen
        mx, my = self.obj_menu_pos
        types = sorted(OBJECT_TYPE_NAMES.keys())
        menu_w, menu_h = 160, len(types) * 22 + 4

        # Background
        surf = pygame.Surface((menu_w, menu_h), pygame.SRCALPHA)
        surf.fill((40, 40, 50, 230))
        screen.blit(surf, (mx, my))
        pygame.draw.rect(screen, (100, 100, 120), (mx, my, menu_w, menu_h), 1)

        # Items
        mouse_x, mouse_y = pygame.mouse.get_pos()
        for i, t in enumerate(types):
            iy = my + 2 + i * 22
            # Hover highlight
            if mx <= mouse_x < mx + menu_w and iy <= mouse_y < iy + 22:
                pygame.draw.rect(screen, (60, 60, 80), (mx + 1, iy, menu_w - 2, 22))

            name = OBJECT_TYPE_NAMES[t]
            txt = self.font_small.render(name, True, COL_TOOLBAR_TEXT)
            screen.blit(txt, (mx + 8, iy + 3))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Thrust Level Editor")
    parser.add_argument("--level", type=int, choices=range(1, 7), default=1,
                        help="Starting level (1-6)")
    parser.add_argument("--import", dest="import_path", type=str, default=None,
                        help="Import level data from an exported .asm file")
    args = parser.parse_args()

    editor = Editor(start_level=args.level - 1, import_path=args.import_path)
    editor.run()


if __name__ == "__main__":
    main()
