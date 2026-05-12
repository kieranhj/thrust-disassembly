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
from tkinter import Tk, filedialog, messagebox
from pathlib import Path

import numpy as np
import pygame

root = Tk()

# Import shared data and decoders from the visualisation tool
sys.path.insert(0, str(Path(__file__).parent))
from visualise_levels import (
    TERRAIN_DATA, OBJECT_DATA, SPRITE_DATA, OBJECT_TYPE_NAMES,
    BBC_COLOURS, LEVEL_LANDSCAPE_COLOUR, LEVEL_OBJECT_COLOUR,
    decode_wall, decode_level, get_objects,
    decode_sprite, decode_mode1_byte,
)

# Gun param data per level (extracted from thrust.6502)
GUN_AIM_DATA = {
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
BOTTOM_HIT_TOLERANCE = 6  # pixels for bottom boundary handle
COL_BOTTOM_HANDLE = (100, 180, 255)

# Inspector / palette pane (right strip)
INSPECTOR_W     = 300   # right-hand strip width (pixels)
INSPECTOR_PAD   = 6     # inner padding
FIELD_H         = 26    # height of one inspector field row
FIELD_LABEL_W   = 90    # label column width within a field
PALETTE_TILE_W  = 90    # sprite palette tile width
PALETTE_TILE_H  = 74    # sprite palette tile height
PALETTE_COLS    = 3
PALETTE_PAD     = 4
COL_INSP_BG      = (22, 22, 28)
COL_INSP_BORDER  = (55, 55, 68)
COL_INSP_HEADER  = (32, 34, 44)
COL_FIELD_BG     = (28, 28, 38)
COL_FIELD_ACTIVE = (38, 42, 60)
COL_FIELD_LABEL  = (125, 128, 155)
COL_FIELD_VALUE  = (200, 205, 220)
COL_FIELD_TEXT   = (255, 255, 140)
COL_BTN          = (46, 48, 62)
COL_BTN_HOVER    = (66, 70, 90)
COL_PALETTE_BG   = (18, 18, 26)
COL_PALETTE_SEL  = (40, 90, 50)
COL_PALETTE_ARMED = (55, 140, 65)

# Object types whose gun_aim byte actually drives firing behaviour.
# thrust.6502 gates firing at try_gun_fire: types < OBJECT_fuel (0-3) for
# regular guns, plus OBJECT_laser_turret_* ($09..$0C). Lasers reuse the
# byte for period/duty/phase decoding rather than aim/spread (TBD), but
# the editor exposes it the same way for now.
OBJECT_FIRING_TYPES = frozenset({0x00, 0x01, 0x02, 0x03, 0x09, 0x0A, 0x0B, 0x0C})

# Spread mask index (gun_aim bits 0-1) -> actual mask from
# thrust.6502 gun_spread_mask_table.
GUN_SPREAD_MASKS = (0x01, 0x03, 0x07, 0x0F)

# Visual scale for the aim indicator drawn over selected firing objects.
GUN_AIM_ARROW_LEN = 18   # world X units (will be scaled by camera zoom)
COL_GUN_AIM = (255, 180, 80)
COL_GUN_SPREAD = (255, 180, 80, 90)

# Laser turret types use the gun_aim byte differently (period/duty/phase
# instead of base angle / spread). Beam direction is fixed per orientation,
# mirroring laser_beam_dx/dy_table in thrust.6502.
OBJECT_LASER_TYPES = frozenset({0x09, 0x0A, 0x0B, 0x0C})
# Per-orientation defaults for laser dx/dy (signed BBC pixels / rows). New
# lasers and old exports without dx/dy arrays fall back to these.
LASER_BEAM_DX_PIXELS = {0x09: +60, 0x0A: +60, 0x0B: -60, 0x0C: -60}
LASER_BEAM_DY_ROWS   = {0x09: -30, 0x0A: +30, 0x0B: -30, 0x0C: +30}
LASER_BARREL_X_CHARS = {0x09:   4, 0x0A:   4, 0x0B:   1, 0x0C:   1}
LASER_BARREL_Y_ROWS  = {0x09:   0, 0x0A:   8, 0x0B:   0, 0x0C:   8}
LASER_ENDPOINT_HANDLE_RADIUS = 8   # screen-px radius of draggable endpoint dot
LASER_ENDPOINT_HIT_PADDING   = 6   # extra screen-px tolerance around the dot for click hit-test
COL_LASER_BEAM       = (255, 110, 50)

# Gravity well object ($0D, SWRAM-only). Per-instance (radius, strength)
# stored as world-coord-unit Manhattan radius and signed Q0.7-ish strength.
# See docs/plan-gravity-well.md.
OBJECT_GRAVITY_WELL  = 0x0D
GRAVITY_WELL_DEFAULT_RADIUS   = 40   # world-coord units; 0 = inactive
GRAVITY_WELL_DEFAULT_STRENGTH = 60   # signed (-127..127)
GRAVITY_WELL_CENTRE_RADIUS    = 6    # screen-px radius of centre dot (also click area)
GRAVITY_WELL_CENTRE_HIT_PADDING = 4
GRAVITY_WELL_HANDLE_RADIUS    = 6    # screen-px radius of radius drag handle dot
GRAVITY_WELL_HANDLE_HIT_PADDING = 6
COL_GRAVITY_WELL     = (140, 160, 255)
COL_GRAVITY_WELL_RING = (140, 160, 255, 110)  # diamond outline (translucent)

# Bobbing mine objects ($0E vertical, $0F horizontal — both SWRAM-only).
# Position bobs along a sine curve with per-instance phase (slot 0) and
# signed amplitude (slot 1). Slot 2 is the runtime previous-offset; always
# 0 in level data.
OBJECT_BOBBING_MINE             = 0x0E
OBJECT_BOBBING_MINE_HORIZONTAL  = 0x0F
BOBBING_MINE_TYPES = frozenset({OBJECT_BOBBING_MINE,
                                OBJECT_BOBBING_MINE_HORIZONTAL})
BOBBING_MINE_DEFAULT_PHASE = 0
BOBBING_MINE_DEFAULT_AMP   = 32   # signed pixels
COL_BOBBING_MINE     = (255, 220, 80)
COL_BOBBING_MINE_RANGE = (255, 220, 80, 110)  # amplitude indicator (translucent)

# Teleporter pads ($10, SWRAM-only). One-way warp to a level checkpoint.
# Slot 0 = destination checkpoint index (0-based). Slots 1/2 reserved.
OBJECT_TELEPORTER       = 0x10
TELEPORTER_DEFAULT_DEST = 0
COL_TELEPORTER          = (120, 220, 255)
COL_TELEPORTER_WIRE     = (120, 220, 255, 180)  # selected->dest line
COL_SWITCH_WIRE         = (255, 200, 100, 180)  # switch->target wiring line (orange)

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
    # Strip comment — BeebAsm accepts both `\` (project convention) and `;`.
    line = line.split("\\")[0].split(";")[0].strip()
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
        # Per-object data slots (current schema). Fall back to the legacy
        # named arrays if obj_data_* aren't present so we can still load
        # exports made before the consolidation. When the new schema is
        # active, slots 1/2 carry the laser-or-well field for that slot —
        # the per-type interpretation happens in the loop below using
        # obj_type[i] to pick which field the byte belongs to.
        data_0 = labels.get(f"level_{n}_obj_data_0", [])
        data_1 = labels.get(f"level_{n}_obj_data_1", [])
        data_2 = labels.get(f"level_{n}_obj_data_2", [])
        new_schema = bool(data_0 or data_1 or data_2)
        gun_aim = data_0 if new_schema else labels.get(f"level_{n}_gun_aim", [])
        legacy_laser_dx = labels.get(f"level_{n}_laser_dx_pixels", [])
        legacy_laser_dy = labels.get(f"level_{n}_laser_dy_rows", [])
        legacy_well_radius = labels.get(f"level_{n}_well_radius", [])
        legacy_well_strength = labels.get(f"level_{n}_well_strength", [])

        # Remove $FF terminator from type list
        types = [t for t in obj_type if t != 0xFF]

        objects = []
        for i in range(len(types)):
            y_world = ((obj_y_ext[i] if i < len(obj_y_ext) else 0) << 8) | \
                      (obj_y[i] if i < len(obj_y) else 0)
            gp = gun_aim[i] if i < len(gun_aim) else 0x00
            t = types[i]
            # Per-orientation default for lasers (matches what the asm shipped
            # with before per-instance dx/dy was added). Non-laser slots get 0.
            default_dx = LASER_BEAM_DX_PIXELS.get(t, 0)
            default_dy = LASER_BEAM_DY_ROWS.get(t, 0)
            if new_schema:
                # Slots 1/2 are shared. Pick interpretation by object type:
                # lasers -> dx/dy bytes; wells -> radius/strength; others 0.
                slot_1 = data_1[i] if i < len(data_1) else 0
                slot_2 = data_2[i] if i < len(data_2) else 0
                if t in LASER_BEAM_DX_PIXELS:
                    dx_byte, dy_byte = slot_1, slot_2
                    wr, ws = 0, 0
                    mine_phase, mine_amp = 0, 0
                elif t == OBJECT_GRAVITY_WELL:
                    dx_byte, dy_byte = default_dx & 0xFF, default_dy & 0xFF
                    wr, ws = slot_1, slot_2
                    mine_phase, mine_amp = 0, 0
                elif t in BOBBING_MINE_TYPES:
                    dx_byte, dy_byte = default_dx & 0xFF, default_dy & 0xFF
                    wr, ws = 0, 0
                    mine_phase, mine_amp = gp, slot_1
                elif t == OBJECT_TELEPORTER:
                    # Slot 0 (loaded into gp above) holds destination
                    # checkpoint index; slots 1/2 reserved.
                    dx_byte, dy_byte = default_dx & 0xFF, default_dy & 0xFF
                    wr, ws = 0, 0
                    mine_phase, mine_amp = 0, 0
                else:
                    dx_byte, dy_byte = default_dx & 0xFF, default_dy & 0xFF
                    wr, ws = 0, 0
                    mine_phase, mine_amp = 0, 0
            else:
                dx_byte = legacy_laser_dx[i] if i < len(legacy_laser_dx) else (default_dx & 0xFF)
                dy_byte = legacy_laser_dy[i] if i < len(legacy_laser_dy) else (default_dy & 0xFF)
                wr = legacy_well_radius[i] if i < len(legacy_well_radius) else 0
                ws = legacy_well_strength[i] if i < len(legacy_well_strength) else 0
                mine_phase, mine_amp = 0, 0
            # Convert from unsigned byte to signed int (-128..127).
            dx_s = dx_byte - 256 if dx_byte >= 128 else dx_byte
            dy_s = dy_byte - 256 if dy_byte >= 128 else dy_byte
            ws_s = ws - 256 if ws >= 128 else ws
            mine_amp_s = mine_amp - 256 if mine_amp >= 128 else mine_amp
            objects.append({
                "x": obj_x[i] if i < len(obj_x) else 0,
                "y": y_world,
                "type": t,
                "gun_aim": gp,
                "laser_dx": dx_s,
                "laser_dy": dy_s,
                "well_radius": wr,
                "well_strength": ws_s,
                "mine_phase": mine_phase & 0xFF,
                "mine_amp": mine_amp_s,
                "teleport_dest": (gp & 0xFF) if t == OBJECT_TELEPORTER else 0,
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

        # No-wrap Y threshold (may not be present in older exports)
        nw_lo = labels.get("level_no_wrap_y_table_LO", [])
        nw_hi = labels.get("level_no_wrap_y_table_HI", [])
        if n < len(nw_lo) and n < len(nw_hi):
            no_wrap_y = (nw_hi[n] << 8) | nw_lo[n]
        else:
            no_wrap_y = None

        # Y-banded parameter overrides (may not be present in older exports).
        # Parallel arrays terminated by $FF in y_HI. Optional landscape/object
        # colour overrides use $FF as a sentinel meaning "inherit level default".
        bands = []
        b_hi = labels.get(f"level_{n}_band_y_HI", [])
        b_lo = labels.get(f"level_{n}_band_y_LO", [])
        b_g  = labels.get(f"level_{n}_band_gravity", [])
        b_lc = labels.get(f"level_{n}_band_landscape_colour", [])
        b_oc = labels.get(f"level_{n}_band_object_colour", [])
        for i in range(min(len(b_hi), len(b_lo), len(b_g))):
            if b_hi[i] == 0xFF:
                break
            lc = b_lc[i] if i < len(b_lc) else 0xFF
            oc = b_oc[i] if i < len(b_oc) else 0xFF
            bands.append({
                "y": (b_hi[i] << 8) | b_lo[i],
                "gravity": b_g[i],
                "landscape_colour": None if lc == 0xFF else lc,
                "object_colour": None if oc == 0xFF else oc,
            })

        # Switch wiring tables (may not be present in older exports).
        # Up to five parallel arrays terminated by $FF in switch_obj_indices;
        # arg_a/arg_b default to 0 when missing (older format compatibility).
        # The same switch_obj_indices value may appear in multiple slots —
        # each is one wiring entry on that switch (multi-trigger).
        wiring = {}
        sw_idx = labels.get(f"level_{n}_switch_obj_indices", [])
        sw_tgt = labels.get(f"level_{n}_switch_target", [])
        sw_act = labels.get(f"level_{n}_switch_action", [])
        sw_aa  = labels.get(f"level_{n}_switch_arg_a", [])
        sw_ab  = labels.get(f"level_{n}_switch_arg_b", [])
        for i in range(min(len(sw_idx), len(sw_tgt), len(sw_act))):
            if sw_idx[i] == 0xFF:
                break
            entry = {
                "target": sw_tgt[i],
                "action": sw_act[i],
                "arg_a":  sw_aa[i] if i < len(sw_aa) else 0,
                "arg_b":  sw_ab[i] if i < len(sw_ab) else 0,
            }
            wiring.setdefault(sw_idx[i], []).append(entry)

        lv = LevelData(n, list(left_wall), list(right_wall), objects,
                        terrain_rle, land_col, obj_col, checkpoints, grav,
                        no_wrap_y, bands, wiring)
        levels.append(lv)

    return levels


def _clamp_converging_walls(left, right):
    """Clamp wall arrays for EOR-safe encoding, returning the last row to encode.

    The game draws terrain using EOR (exclusive-or) delta rendering: each
    frame, only the columns that changed are toggled. Two issues arise when
    walls move:

    1. If left[row] jumps past right[row-1] (or vice versa), the EOR draws
       for both walls overlap on some columns. Those columns get toggled
       twice and remain as black gaps instead of solid rock.

    2. Inside a "rock band" (a stretch of rows where left == right at a
       constant X) any wobble in that X creates wall edge movement in what
       should be solid rock, causing further EOR artifacts.

    Rock bands are preserved as a level-design primitive — the cavern can
    converge to solid rock for N rows then re-open into a disconnected
    sub-cavern. The encoder emits zero-delta RLE segments through the band,
    and the renderer paints the row as solid because left==right.

    Band detection is sticky: a row painted with `gap <= 1` (walls touching
    or crossed) enters a band at the midpoint X. Subsequent rows whose
    painted gap is also <= 1 get snapped to that same X — so a hand-painted
    band where each row's X drifts slightly (easy to do with the line tool)
    still encodes as a clean solid strip, not as alternating pinned / gap=2
    rows that would render with EOR wobble. The band ends at the first row
    where the painted gap is > 1 (the cavern re-opens).

    Pass 2 finds the last open row (gap > 1) and returns the row index
    one past it, so the encoder's terminator freezes the decoder on a
    closed-bottom row rather than mid-cavern. Returns None for a fully
    solid level (no open rows at all).

    Operates on copies — does not truncate the source arrays.
    """
    min_len = min(len(left), len(right))
    if min_len == 0:
        return None

    # Pass 1: walk rows, switching between "open" and "in band" state.
    # Sticky band: once we enter a band, painted rows with gap <= 1 stay
    # pinned to the entry X regardless of any drift in painted X.
    band_x = None
    for row in range(min_len):
        painted_gap = right[row] - left[row]

        if band_x is not None:
            if painted_gap <= 1:
                # Still in the band. Snap to band X (ignore painted drift).
                left[row] = band_x
                right[row] = band_x
                continue
            # Cavern re-opens — exit the band and fall through to open
            # handling. Previous row was at band_x, so EOR clamps below
            # use that as the "previous row" reference.
            band_x = None

        # Open-row processing.
        if row > 0:
            # Per-row movement clamp: left can't advance past prev row's
            # right; right can't retreat past prev row's left.
            if left[row] > right[row - 1]:
                left[row] = right[row - 1]
            if right[row] < left[row - 1]:
                right[row] = left[row - 1]

        # If walls touched after clamping, enter a rock band at midpoint.
        if right[row] - left[row] <= 1:
            mid = (left[row] + right[row]) // 2
            left[row] = mid
            right[row] = mid
            band_x = mid

    # Pass 2: find the last open row. Encoding through last_open + 1
    # ensures the terminator freezes the decoder on a closed-bottom row
    # (or the natural array end), not mid-cavern.
    last_open = None
    for row in range(min_len):
        if right[row] - left[row] > 1:
            last_open = row

    if last_open is None:
        return None
    return min(last_open + 1, min_len - 1)


def _has_wall_issues(left, right):
    """Check if decoded wall data has wall crossings (left > right).

    `left == right` is allowed — that's a rock-band row, a legitimate
    level-design primitive (zero-width corridor reads as solid rock).
    Only strict crossings indicate corruption that warrants re-encoding.
    """
    for row in range(min(len(left), len(right))):
        if left[row] > right[row]:
            return True
    return False


def _is_bottom_open(left, right):
    """Check if the landscape bottom is open (walls don't converge).

    Returns True if the effective last row has a gap > 1 between
    left and right walls, meaning the cave isn't sealed at the bottom.
    When arrays differ in length, the shorter wall is frozen at its
    last value for the remaining rows.
    """
    if not left or not right:
        return False
    max_len = max(len(left), len(right))
    last_left = left[-1] if len(left) >= max_len else left[-1]
    last_right = right[-1] if len(right) >= max_len else right[-1]
    return last_right - last_left > 1


def _close_bottom(left, right):
    """Close an open landscape bottom by converging the walls.

    Equalises array lengths first, then appends rows that linearly bring
    the left and right walls together to a midpoint.
    """
    if not left or not right:
        return

    # Equalise lengths — extend the shorter array with its last value
    max_len = max(len(left), len(right))
    while len(left) < max_len:
        left.append(left[-1])
    while len(right) < max_len:
        right.append(right[-1])

    last_left = left[-1]
    last_right = right[-1]
    gap = last_right - last_left
    if gap <= 1:
        return  # already closed

    # Converge over 'gap // 2' rows (roughly one column per row from each side)
    mid = (last_left + last_right) // 2
    steps = max(gap // 2, 1)
    for i in range(1, steps + 1):
        t = i / steps
        lx = int(round(last_left + t * (mid - last_left)))
        rx = int(round(last_right + t * (mid - last_right)))
        # Ensure they don't cross
        if lx > rx:
            lx = rx = mid
        left.append(lx)
        right.append(rx)

    # Freeze at midpoint for a final row
    left.append(mid)
    right.append(mid)


def export_beebasm(levels):
    """Generate BeebAsm assembly source for terrain and object data."""
    # Per-level checkpoint sort permutation. The engine starts every life at
    # checkpoint 0, so checkpoint 0 must be the topmost spawn point in the
    # exported table. Sort each level's checkpoints by ascending spawn_y on
    # export, and remap any teleporter's destination index through the sort
    # permutation so warps still land on the same checkpoint after the sort.
    # In-editor state is NOT mutated — the sort applies only to the emitted
    # bytes, and the sort is deterministic so repeated saves are byte-stable.
    sorted_checkpoints = {}
    checkpoint_remap = {}
    for lv in levels:
        cps = lv.checkpoints or []
        order = sorted(range(len(cps)), key=lambda i: cps[i]["spawn_y"])
        sorted_checkpoints[lv.level_num] = [cps[i] for i in order]
        old_to_new = [0] * len(cps)
        for new_i, old_i in enumerate(order):
            old_to_new[old_i] = new_i
        checkpoint_remap[lv.level_num] = old_to_new

    def remap_teleport_dest(level_num, dest):
        """Apply the sort permutation to a teleporter's checkpoint index."""
        perm = checkpoint_remap.get(level_num, [])
        if not perm:
            return 0
        return perm[dest % len(perm)]

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
            # Generic per-object data slots. Each object type interprets each
            # slot in its own way (see thrust.6502 OBJ_DATA_* offsets):
            #   slot 0: gun_aim (guns/lasers) / mine_phase (mines)
            #   slot 1: laser_dx_pixels (lasers) / well_radius (wells) / mine_amp (mines)
            #   slot 2: laser_dy_rows (lasers) / well_strength (wells) / 0 (mines: runtime state)
            data_0 = []
            data_1 = []
            data_2 = []
            for o in obj:
                t = o['type']
                if t in BOBBING_MINE_TYPES:
                    data_0.append(o.get('mine_phase', 0) & 0xFF)
                    data_1.append(o.get('mine_amp', 0) & 0xFF)
                    data_2.append(0)
                elif t == OBJECT_TELEPORTER:
                    data_0.append(remap_teleport_dest(n, o.get('teleport_dest', 0)) & 0xFF)
                    data_1.append(0)
                    data_2.append(0)
                else:
                    data_0.append(o.get('gun_aim', 0x00) & 0xFF)
                    data_1.append(
                        (o.get('laser_dx', 0) & 0xFF) | (o.get('well_radius', 0) & 0xFF)
                    )
                    data_2.append(
                        (o.get('laser_dy', 0) & 0xFF) | (o.get('well_strength', 0) & 0xFF)
                    )
            lines.append(f".level_{n}_obj_data_0")
            lines.append(f"        EQUB    {format_bytes(data_0)}")
            lines.append(f".level_{n}_obj_data_1")
            lines.append(f"        EQUB    {format_bytes(data_1)}")
            lines.append(f".level_{n}_obj_data_2")
            lines.append(f"        EQUB    {format_bytes(data_2)}")
            lines.append("")

    # Gravity table
    lines.append("\\ ******************************************************************************")
    lines.append("\\ * Gravity values per level")
    lines.append("\\ ******************************************************************************")
    lines.append("")
    lines.append(".level_gravity_FRAC_table")
    lines.append(f"        EQUB    {format_bytes([lv.gravity for lv in levels])}")
    lines.append("")

    # Y-banded gravity overrides per level
    lines.append("\\ ******************************************************************************")
    lines.append("\\ * Y-banded parameter overrides per level")
    lines.append("\\ * Three parallel arrays: band_y_HI, band_y_LO, band_gravity (gravity_FRAC).")
    lines.append("\\ * Bands sorted ascending by Y. Sentinel: $FF in band_y_HI terminates list.")
    lines.append("\\ ******************************************************************************")
    lines.append("")
    for lv in levels:
        n = lv.level_num
        bands = sorted(lv.bands, key=lambda b: b["y"])
        y_hi = [(b["y"] >> 8) & 0xFF for b in bands] + [0xFF]
        y_lo = [b["y"] & 0xFF for b in bands] + [0x00]
        grav = [b["gravity"] & 0xFF for b in bands] + [0x00]
        lc   = [(b.get("landscape_colour") if b.get("landscape_colour") is not None else 0xFF) & 0xFF
                for b in bands] + [0xFF]
        oc   = [(b.get("object_colour") if b.get("object_colour") is not None else 0xFF) & 0xFF
                for b in bands] + [0xFF]
        lines.append(f".level_{n}_band_y_HI")
        lines.append(f"        EQUB    {format_bytes(y_hi)}")
        lines.append(f".level_{n}_band_y_LO")
        lines.append(f"        EQUB    {format_bytes(y_lo)}")
        lines.append(f".level_{n}_band_gravity")
        lines.append(f"        EQUB    {format_bytes(grav)}")
        lines.append(f".level_{n}_band_landscape_colour")
        lines.append(f"        EQUB    {format_bytes(lc)}")
        lines.append(f".level_{n}_band_object_colour")
        lines.append(f"        EQUB    {format_bytes(oc)}")
        lines.append("")

    # Switch wiring tables per level
    lines.append("\\ ******************************************************************************")
    lines.append("\\ * Switch wiring tables per level")
    lines.append("\\ * Five parallel arrays per level, indexed by switch slot:")
    lines.append("\\ *   level_N_switch_obj_indices: object index of each switch ($FF terminator)")
    lines.append("\\ *   level_N_switch_target:     target object index ($FF = no target / disabled)")
    lines.append("\\ *   level_N_switch_action:     action code (see thrust.6502)")
    lines.append("\\ *   level_N_switch_arg_a:      action arg A (e.g. obj_data slot 0..2 for set_param/xor_param)")
    lines.append("\\ *   level_N_switch_arg_b:      action arg B (e.g. value or XOR mask)")
    lines.append("\\ ******************************************************************************")
    lines.append("")
    for lv in levels:
        n = lv.level_num
        wiring = getattr(lv, "wiring", {}) or {}
        # Flatten {sw_idx: [entry, ...]} to slot-indexed parallel arrays.
        # Sort outer by switch index for deterministic export; preserve list
        # order within each switch (designer chose firing order).
        indices, targets, actions, arg_as, arg_bs = [], [], [], [], []
        for sw_idx in sorted(wiring.keys()):
            entries = wiring[sw_idx]
            # Defensive: an older single-entry dict slipped through means
            # exactly one entry on that switch.
            if isinstance(entries, dict):
                entries = [entries]
            for e in entries:
                indices.append(sw_idx & 0xFF)
                targets.append(e.get("target", 0xFF) & 0xFF)
                actions.append(e.get("action", 0x00) & 0xFF)
                arg_as.append(e.get("arg_a", 0x00) & 0xFF)
                arg_bs.append(e.get("arg_b", 0x00) & 0xFF)
        # Parallel terminators.
        indices.append(0xFF)
        targets.append(0xFF)
        actions.append(0x00)
        arg_as.append(0x00)
        arg_bs.append(0x00)
        lines.append(f".level_{n}_switch_obj_indices")
        lines.append(f"        EQUB    {format_bytes(indices)}")
        lines.append(f".level_{n}_switch_target")
        lines.append(f"        EQUB    {format_bytes(targets)}")
        lines.append(f".level_{n}_switch_action")
        lines.append(f"        EQUB    {format_bytes(actions)}")
        lines.append(f".level_{n}_switch_arg_a")
        lines.append(f"        EQUB    {format_bytes(arg_as)}")
        lines.append(f".level_{n}_switch_arg_b")
        lines.append(f"        EQUB    {format_bytes(arg_bs)}")
        lines.append("")

    # No-wrap Y threshold table
    lines.append("\\ ******************************************************************************")
    lines.append("\\ * No-wrap Y threshold per level")
    lines.append("\\ * X wrap disabled when player Y >= this value ($FFFF = always wrap)")
    lines.append("\\ ******************************************************************************")
    lines.append("")
    lines.append(".level_no_wrap_y_table_LO")
    lines.append(f"        EQUB    {format_bytes([lv.no_wrap_y & 0xFF for lv in levels])}")
    lines.append(".level_no_wrap_y_table_HI")
    lines.append(f"        EQUB    {format_bytes([lv.no_wrap_y >> 8 for lv in levels])}")
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
        # Use sort-by-Y order so checkpoint 0 is always the topmost spawn.
        cps = sorted_checkpoints[n]
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


# ---------------------------------------------------------------------------
# Inspector field schemas
# ---------------------------------------------------------------------------

class Field:
    """One editable parameter shown in the inspector pane."""
    __slots__ = ('id', 'label', 'kind', 'getter', 'setter',
                 'min', 'max', 'step', 'shift_step', 'fmt',
                 'hotkey', 'hotkey_2', 'allow_none', 'values', 'target_kind')

    def __init__(self, id, label, kind, getter, setter, *,
                 min=0, max=255, step=1, shift_step=16, fmt=None,
                 hotkey=None, hotkey_2=None, allow_none=False,
                 values=None, target_kind=None):
        self.id = id; self.label = label; self.kind = kind
        self.getter = getter; self.setter = setter
        self.min = min; self.max = max; self.step = step
        self.shift_step = shift_step; self.fmt = fmt
        self.hotkey = hotkey; self.hotkey_2 = hotkey_2
        self.allow_none = allow_none; self.values = values
        self.target_kind = target_kind

    def get(self, t):
        return self.getter(t)

    def set(self, t, v):
        self.setter(t, v)

    def clamp(self, v):
        if v is None:
            return v
        return max(self.min, min(self.max, v))

    def format_value(self, v):
        if v is None:
            return "inherit"
        if self.fmt:
            try:
                return self.fmt.format(v)
            except Exception:
                pass
        if self.kind == 'signed_byte':
            s = v - 256 if v >= 128 else v
            return f"${v:02X} ({s:+d})"
        if self.kind == 'byte':
            return f"${v:02X} ({v})"
        if self.kind == 'word':
            if v == 0xFFFF:
                return "$FFFF (disabled)"
            return f"${v:04X} ({v})"
        if self.kind == 'colour':
            return BBC_COLOUR_NAMES.get(v, str(v))
        if self.kind == 'enum' and self.values:
            for lbl, val in self.values:
                if val == v:
                    return lbl
        return str(v)


def _g(key):
    return lambda t: t[key]

def _s(key):
    return lambda t, v: t.__setitem__(key, v)


_GUN_BASE_ANGLES  = [(f"{a}", a) for a in range(0, 32, 4)]
_GUN_SPREAD_VALS  = [("Tight (1px)", 0), ("Narrow (3px)", 1),
                     ("Medium (7px)", 2), ("Wide (15px)", 3)]
_LASER_PHASE_VALS = [(f"{i*8}f", i) for i in range(16)]
_LASER_DUTY_VALS  = [(f"{i*4+4}f", i) for i in range(16)]


def _gun_base_get(t):  return t.get("gun_aim", 0) & 0x1C
def _gun_spread_get(t): return t.get("gun_aim", 0) & 0x03
def _gun_base_set(t, v): t["gun_aim"] = (v & 0x1C) | (t.get("gun_aim", 0) & 0x03)
def _gun_spread_set(t, v): t["gun_aim"] = (t.get("gun_aim", 0) & 0x1C) | (v & 0x03)
def _laser_phase_get(t): return t.get("gun_aim", 0) & 0x0F
def _laser_duty_get(t):  return (t.get("gun_aim", 0) >> 4) & 0x0F
def _laser_phase_set(t, v): t["gun_aim"] = (t.get("gun_aim", 0) & 0xF0) | (v & 0x0F)
def _laser_duty_set(t, v):  t["gun_aim"] = (t.get("gun_aim", 0) & 0x0F) | ((v & 0x0F) << 4)


SCHEMA_LEVEL = [
    Field("level_num", "Level", "readonly",
          getter=lambda t: t.level_num + 1, setter=lambda t, v: None),
    Field("gravity", "Gravity", "signed_byte",
          getter=lambda t: t.gravity,
          setter=lambda t, v: setattr(t, 'gravity', v & 0xFF),
          min=0, max=255, step=1, shift_step=16, hotkey=("[", "]")),
    Field("landscape_colour", "Land colour", "colour",
          getter=lambda t: t.landscape_colour,
          setter=lambda t, v: setattr(t, 'landscape_colour', v),
          min=0, max=7, allow_none=False),
    Field("object_colour", "Obj colour", "colour",
          getter=lambda t: t.object_colour,
          setter=lambda t, v: setattr(t, 'object_colour', v),
          min=0, max=7, allow_none=False),
    Field("no_wrap_y", "No-wrap Y", "word",
          getter=lambda t: t.no_wrap_y,
          setter=lambda t, v: setattr(t, 'no_wrap_y', v),
          min=0, max=0xFFFF, step=1, shift_step=256),
]

SCHEMA_BAND = [
    Field("y", "Y threshold", "word",
          getter=_g("y"), setter=_s("y"),
          min=0, max=0xFFFE, step=1, shift_step=256),
    Field("gravity", "Gravity", "signed_byte",
          getter=_g("gravity"), setter=_s("gravity"),
          min=0, max=255, step=1, shift_step=16,
          hotkey=("[", "]"), hotkey_2=(",", ".")),
    Field("landscape_colour", "Land colour", "colour",
          getter=_g("landscape_colour"), setter=_s("landscape_colour"),
          min=0, max=7, allow_none=True, hotkey=("k", "k")),
    Field("object_colour", "Obj colour", "colour",
          getter=_g("object_colour"), setter=_s("object_colour"),
          min=0, max=7, allow_none=True, hotkey=("j", "j")),
]

SCHEMA_CHECKPOINT = [
    Field("spawn_x", "Spawn X", "byte",
          getter=_g("spawn_x"), setter=_s("spawn_x"),
          min=0, max=255, step=1, shift_step=8),
    Field("spawn_y", "Spawn Y", "word",
          getter=_g("spawn_y"), setter=_s("spawn_y"),
          min=0, max=0xFFFF, step=1, shift_step=32),
    Field("window_x", "Window X", "byte",
          getter=_g("window_x"), setter=_s("window_x"),
          min=0, max=255, step=1, shift_step=8),
    Field("window_y", "Window Y", "word",
          getter=_g("window_y"), setter=_s("window_y"),
          min=0, max=0xFFFF, step=1, shift_step=32),
]

SCHEMA_GUN = [
    Field("x", "X", "byte", getter=_g("x"), setter=_s("x"),
          min=0, max=255, step=1, shift_step=8),
    Field("y", "Y", "word", getter=_g("y"), setter=_s("y"),
          min=0, max=0xFFFF, step=1, shift_step=32),
    Field("gun_aim_base", "Base angle", "enum",
          getter=_gun_base_get, setter=_gun_base_set,
          min=0, max=28, step=4, values=_GUN_BASE_ANGLES,
          hotkey=("[", "]")),
    Field("gun_aim_spread", "Spread", "enum",
          getter=_gun_spread_get, setter=_gun_spread_set,
          min=0, max=3, step=1, values=_GUN_SPREAD_VALS,
          hotkey=(",", ".")),
]

SCHEMA_LASER = [
    Field("x", "X", "byte", getter=_g("x"), setter=_s("x"),
          min=0, max=255, step=1, shift_step=8),
    Field("y", "Y", "word", getter=_g("y"), setter=_s("y"),
          min=0, max=0xFFFF, step=1, shift_step=32),
    Field("laser_phase", "Phase", "enum",
          getter=_laser_phase_get, setter=_laser_phase_set,
          min=0, max=15, step=1, values=_LASER_PHASE_VALS,
          hotkey=("[", "]")),
    Field("laser_duty", "Duty", "enum",
          getter=_laser_duty_get, setter=_laser_duty_set,
          min=0, max=15, step=1, values=_LASER_DUTY_VALS,
          hotkey=(",", ".")),
    Field("laser_dx", "Beam dx", "signed_byte",
          getter=_g("laser_dx"), setter=_s("laser_dx"),
          min=-127, max=127, step=1, shift_step=8),
    Field("laser_dy", "Beam dy", "signed_byte",
          getter=_g("laser_dy"), setter=_s("laser_dy"),
          min=-127, max=127, step=1, shift_step=8),
]

SCHEMA_GRAVITY_WELL = [
    Field("x", "X", "byte", getter=_g("x"), setter=_s("x"),
          min=0, max=255, step=1, shift_step=8),
    Field("y", "Y", "word", getter=_g("y"), setter=_s("y"),
          min=0, max=0xFFFF, step=1, shift_step=32),
    Field("well_radius", "Radius", "byte",
          getter=_g("well_radius"), setter=_s("well_radius"),
          min=0, max=255, step=1, shift_step=10),
    Field("well_strength", "Strength", "signed_byte",
          getter=_g("well_strength"), setter=_s("well_strength"),
          min=-127, max=127, step=1, shift_step=10,
          hotkey=("[", "]")),
]

SCHEMA_BOBBING_MINE = [
    Field("x", "X", "byte", getter=_g("x"), setter=_s("x"),
          min=0, max=255, step=1, shift_step=8),
    Field("y", "Y", "word", getter=_g("y"), setter=_s("y"),
          min=0, max=0xFFFF, step=1, shift_step=32),
    Field("mine_amp", "Amplitude", "signed_byte",
          getter=_g("mine_amp"), setter=_s("mine_amp"),
          min=-127, max=127, step=1, shift_step=10,
          hotkey=("[", "]")),
    Field("mine_phase", "Phase", "byte",
          getter=_g("mine_phase"), setter=_s("mine_phase"),
          min=0, max=255, step=1, shift_step=8,
          hotkey=(",", ".")),
]

SCHEMA_TELEPORTER = [
    Field("x", "X", "byte", getter=_g("x"), setter=_s("x"),
          min=0, max=255, step=1, shift_step=8),
    Field("y", "Y", "word", getter=_g("y"), setter=_s("y"),
          min=0, max=0xFFFF, step=1, shift_step=32),
    Field("teleport_dest", "Destination", "ref",
          getter=_g("teleport_dest"), setter=_s("teleport_dest"),
          min=0, max=255, step=1, target_kind="checkpoint",
          hotkey=("[", "]")),
]

SCHEMA_DOOR_SWITCH = [
    Field("x", "X", "byte", getter=_g("x"), setter=_s("x"),
          min=0, max=255, step=1, shift_step=8),
    Field("y", "Y", "word", getter=_g("y"), setter=_s("y"),
          min=0, max=0xFFFF, step=1, shift_step=32),
    Field("type", "Side", "enum",
          getter=_g("type"), setter=_s("type"),
          min=7, max=8, step=1,
          values=[("Left wall ($07)", 7), ("Right wall ($08)", 8)]),
]

# Switch wiring action codes — must match thrust.6502 action_jump_table.
SWITCH_ACTION_VALUES = [
    ("none",          0),
    ("set_alive",     1),
    ("clear_alive",   2),
    ("toggle_alive",  3),
    ("destroy",       4),
    ("set_param",     6),
    ("xor_param",     7),
]

# Action codes that need the Slot + Value (Mask) inspector fields.
SWITCH_PARAM_ACTIONS = {6, 7}

# Per-target-type meaning of the three obj_data slots, for the editor's
# Slot dropdown. Indexed by object type. Slots that the engine doesn't
# read are labelled "(unused)"; engine-managed scratch is flagged so
# designers don't accidentally write to it.
SWITCH_SLOT_LABELS = {
    0x00: ("gun_aim",         "(unused)",  "(unused)"),
    0x01: ("gun_aim",         "(unused)",  "(unused)"),
    0x02: ("gun_aim",         "(unused)",  "(unused)"),
    0x03: ("gun_aim",         "(unused)",  "(unused)"),
    0x04: ("(unused)",        "(unused)",  "(unused)"),  # fuel
    0x05: ("(unused)",        "(unused)",  "(unused)"),  # pod (blocked anyway)
    0x06: ("(unused)",        "(unused)",  "(unused)"),  # generator
    0x07: ("(unused)",        "(unused)",  "(unused)"),  # door switch L
    0x08: ("(unused)",        "(unused)",  "(unused)"),  # door switch R
    0x09: ("phase/duty",      "Beam dx",   "Beam dy"),
    0x0A: ("phase/duty",      "Beam dx",   "Beam dy"),
    0x0B: ("phase/duty",      "Beam dx",   "Beam dy"),
    0x0C: ("phase/duty",      "Beam dx",   "Beam dy"),
    0x0D: ("(unused)",        "Radius",    "Strength (signed)"),
    0x0E: ("Phase",           "Amplitude", "(engine scratch)"),
    0x0F: ("Phase",           "Amplitude", "(engine scratch)"),
    0x10: ("Dest checkpoint", "(unused)",  "(unused)"),
}


def slot_labels_for_target(lv, wiring_entry):
    """Return (slot0, slot1, slot2) labels for the wiring's current target.
    Falls back to generic labels when the target is unset or out of range.
    """
    if not wiring_entry:
        return ("Slot 0", "Slot 1", "Slot 2")
    tgt = wiring_entry.get("target", 0xFF)
    if not (0 <= tgt < len(lv.objects)):
        return ("Slot 0", "Slot 1", "Slot 2")
    obj_type = lv.objects[tgt]["type"]
    return SWITCH_SLOT_LABELS.get(obj_type, ("Slot 0", "Slot 1", "Slot 2"))


SWITCH_SLOT_CAP = 8  # parallel arrays in thrust.6502 are 8 entries deep


def _build_wiring_entry_fields(lv, sw_idx, entry_i):
    """Build the field list for one wiring entry on switch sw_idx at slot entry_i.
    Closures rebuild the path each call so deletions/insertions in the list
    can't leave field setters pointing at the wrong entry.
    """
    def _entry():
        lst = lv.wiring.get(sw_idx, [])
        if 0 <= entry_i < len(lst):
            return lst[entry_i]
        return {}

    def _ensure_entry():
        lst = lv.wiring.setdefault(sw_idx, [])
        while len(lst) <= entry_i:
            lst.append({"target": 0xFF, "action": 0, "arg_a": 0, "arg_b": 0})
        return lst[entry_i]

    def _g(key, default):
        return lambda _t: _entry().get(key, default)

    def _s(key):
        def setter(_t, v):
            e = _ensure_entry()
            e[key] = int(v) & 0xFF
        return setter

    fields = [
        Field(f"sw_action_{entry_i}", "Action", "enum",
              getter=_g("action", 0), setter=_s("action"),
              min=0, max=7, step=1, values=SWITCH_ACTION_VALUES,
              hotkey=("[", "]")),
        Field(f"sw_target_{entry_i}", "Target", "ref",
              getter=_g("target", 0xFF), setter=_s("target"),
              min=0, max=255, step=1, target_kind="object"),
    ]

    # Slot + Value (or Mask) are only meaningful for the param-write actions.
    entry = _entry()
    action = entry.get("action", 0)
    if action in SWITCH_PARAM_ACTIONS:
        slot0, slot1, slot2 = slot_labels_for_target(lv, entry)
        slot_values = [
            (f"Slot 0: {slot0}", 0),
            (f"Slot 1: {slot1}", 1),
            (f"Slot 2: {slot2}", 2),
        ]
        value_label = "Mask" if action == 7 else "Value"
        fields.append(
            Field(f"sw_slot_{entry_i}", "Slot", "enum",
                  getter=_g("arg_a", 0), setter=_s("arg_a"),
                  min=0, max=2, step=1, values=slot_values,
                  hotkey=(",", ".")))
        fields.append(
            Field(f"sw_value_{entry_i}", value_label, "byte",
                  getter=_g("arg_b", 0), setter=_s("arg_b"),
                  min=0, max=255, step=1, shift_step=16))

    return fields


def _switch_wiring_fields(lv, obj):
    """Build the wiring list editor for a switch object.

    Each wiring entry renders as a numbered sub-section (header + fields +
    Delete button). A "+ Add wiring" button at the end appends a new empty
    entry, unless the per-level 8-slot table cap has been reached.
    """
    try:
        sw_idx = lv.objects.index(obj)
    except ValueError:
        return []

    entries = lv.wiring.get(sw_idx, [])

    def _delete_entry(i):
        def _click(_t, _v=None):
            lst = lv.wiring.get(sw_idx)
            if lst is None or not (0 <= i < len(lst)):
                return
            lst.pop(i)
            if not lst:
                lv.wiring.pop(sw_idx, None)
        return _click

    def _append_entry(_t, _v=None):
        # Respect the per-level total cap so the export never exceeds 8 slots.
        total = sum(len(v) for v in lv.wiring.values())
        if total >= SWITCH_SLOT_CAP:
            return
        lv.wiring.setdefault(sw_idx, []).append(
            {"target": 0xFF, "action": 0, "arg_a": 0, "arg_b": 0})

    fields = []
    if not entries:
        fields.append(_section_header("Wiring (none)"))
    for entry_i in range(len(entries)):
        fields.append(_section_header(f"Wiring #{entry_i + 1}"))
        fields.extend(_build_wiring_entry_fields(lv, sw_idx, entry_i))
        fields.append(
            Field(f"sw_delete_{entry_i}", "✕ Delete entry", "button",
                  getter=lambda _t: 0,
                  setter=_delete_entry(entry_i)))

    # Total entries across all switches (cap shared by the export's parallel arrays).
    total_entries = sum(len(v) for v in lv.wiring.values())
    if total_entries < SWITCH_SLOT_CAP:
        fields.append(
            Field("sw_add", "+ Add wiring", "button",
                  getter=lambda _t: 0, setter=_append_entry))
    else:
        fields.append(_readonly("(max 8 wiring entries per level)", ""))
    return fields

SCHEMA_SIMPLE = [
    Field("x", "X", "byte", getter=_g("x"), setter=_s("x"),
          min=0, max=255, step=1, shift_step=8),
    Field("y", "Y", "word", getter=_g("y"), setter=_s("y"),
          min=0, max=0xFFFF, step=1, shift_step=32),
]


def _readonly(label, value):
    """Build a readonly field that displays a fixed value."""
    return Field(label.lower().replace(" ", "_") + "_ro", label, "readonly",
                 getter=lambda t, _v=value: _v, setter=lambda t, v: None)


def _section_header(title):
    """Build a title-bar field that spans the full inspector width."""
    return Field("section_header", title, "header",
                 getter=lambda t, _v=title: _v, setter=lambda t, v: None)


def schema_for_selection(editor):
    """Return (schema, target, level) for the current editor selection."""
    lv = editor.level
    mode = editor.mode
    ln = lv.level_num + 1
    if mode == "band" and editor.selected_band is not None:
        bi = editor.selected_band
        if 0 <= bi < len(lv.bands):
            prefix = [_section_header(f"Level {ln} Bands"),
                      _readonly("Index", str(bi))]
            return prefix + SCHEMA_BAND, lv.bands[bi], lv
    if mode == "checkpoint" and editor.selected_checkpoint is not None:
        ci = editor.selected_checkpoint
        if 0 <= ci < len(lv.checkpoints):
            prefix = [_section_header(f"Level {ln} Checkpoints"),
                      _readonly("Index", str(ci))]
            return prefix + SCHEMA_CHECKPOINT, lv.checkpoints[ci], lv
    if mode == "object" and editor.selected_object is not None:
        oi = editor.selected_object
        if 0 <= oi < len(lv.objects):
            obj = lv.objects[oi]
            t = obj["type"]
            type_name = OBJECT_TYPE_NAMES.get(t, f"${t:02X}")
            prefix = [_section_header(f"Level {ln} Objects"),
                      _readonly("Index", str(oi)),
                      _readonly("Type", f"{type_name} (${t:02X})")]
            if t in OBJECT_LASER_TYPES:
                return prefix + SCHEMA_LASER, obj, lv
            if t == OBJECT_GRAVITY_WELL:
                return prefix + SCHEMA_GRAVITY_WELL, obj, lv
            if t in BOBBING_MINE_TYPES:
                return prefix + SCHEMA_BOBBING_MINE, obj, lv
            if t == OBJECT_TELEPORTER:
                return prefix + SCHEMA_TELEPORTER, obj, lv
            if t in OBJECT_FIRING_TYPES:
                return prefix + SCHEMA_GUN, obj, lv
            if t in (0x07, 0x08):
                return prefix + SCHEMA_DOOR_SWITCH + _switch_wiring_fields(lv, obj), obj, lv
            return prefix + SCHEMA_SIMPLE, obj, lv
    return [_section_header(f"Level {ln}")] + SCHEMA_LEVEL[1:], lv, lv


class LevelData:
    """Mutable level state: decoded walls + object list."""

    def __init__(self, level_num, left_wall, right_wall, objects,
                 terrain_rle=None, landscape_colour=None, object_colour=None,
                 checkpoints=None, gravity=None, no_wrap_y=None, bands=None,
                 wiring=None):
        self.level_num = level_num
        self.left_wall = left_wall   # list[int] X per Y row
        self.right_wall = right_wall
        self.objects = objects        # list[dict] with x, y, type, gun_aim keys
        self.terrain_rle = terrain_rle  # original RLE arrays {"A","B","C","D"}
        self.landscape_colour = landscape_colour if landscape_colour is not None \
            else LEVEL_LANDSCAPE_COLOUR[level_num]  # BBC physical colour 0-7
        self.object_colour = object_colour if object_colour is not None \
            else LEVEL_OBJECT_COLOUR[level_num]      # BBC physical colour 0-7
        self.checkpoints = checkpoints if checkpoints is not None \
            else [dict(cp) for cp in LEVEL_RESET_DATA[level_num]]
        self.gravity = gravity if gravity is not None \
            else LEVEL_GRAVITY_FRAC[level_num]       # Q0.8 fractional gravity
        self.no_wrap_y = no_wrap_y if no_wrap_y is not None else 0xFFFF  # Y threshold for disabling X wrap
        # Y-banded gravity overrides. Each band: {"y": int (0..0xFFFE), "gravity": int (0..0xFF)}.
        # Sorted ascending by y; band is active when player_y >= band["y"].
        self.bands = bands if bands is not None else []
        # Switch wiring: dict mapping switch object index -> list of entries.
        # Each entry: {"target": int, "action": int, "arg_a": int, "arg_b": int}.
        # A switch can have multiple entries (multi-trigger) — they all fire
        # in list order on each switch hit, sharing one refractory window.
        self.wiring = wiring if wiring is not None else {}
        self.dirty = False
        self.terrain_dirty = False    # True when walls have been edited

    @classmethod
    def from_game_data(cls, level_num):
        left, right = decode_level(level_num)
        # Store original RLE data for byte-identical export
        td = TERRAIN_DATA[level_num]
        terrain_rle = {k: list(v) for k, v in td.items()}
        # Build objects with gun_aim
        od = OBJECT_DATA[level_num]
        # Get gun_aim from the source data
        gun_aims = GUN_AIM_DATA.get(level_num, [])
        objects = []
        for i in range(len(od["type"])):
            y_world = (od["Y_EXT"][i] << 8) | od["Y"][i]
            gp = gun_aims[i] if i < len(gun_aims) else 0x00
            t = od["type"][i]
            objects.append({"x": od["X"][i], "y": y_world,
                            "type": t, "gun_aim": gp,
                            "laser_dx": LASER_BEAM_DX_PIXELS.get(t, 0),
                            "laser_dy": LASER_BEAM_DY_ROWS.get(t, 0),
                            "well_radius": 0, "well_strength": 0,
                            "mine_phase": 0, "mine_amp": 0,
                            "teleport_dest": 0})
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
        self.viewport_w = WINDOW_W - INSPECTOR_W
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

# Vertical offset between the spawn_y stored in the level reset table
# (which becomes midpoint_ypos at reset) and the ship's actual plot Y in
# the game. Derived from calculate_attached_pod_vector at level start:
# angle_ship_to_pod = 1, top_nibble_index = $0E, so midpoint_deltay ≈
# -2.5 * cos(11.25°) * (14+2) / 4 ≈ -9.8 world Y units. Round to 10.
_SPAWN_MIDPOINT_TO_SHIP_DY = 10
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
    """Caches decoded sprites as PyGame surfaces per (obj_type, landscape_col, object_col).

    Supports a "live" sprite source: if load_live_sprites() has been called
    successfully, _render uses the loaded pixel data in preference to the
    static SPRITE_DATA fallback, so the editor's visuals match whatever is
    currently in tools/output/object_sprites.asm.
    """

    def __init__(self):
        self._cache = {}
        self._ship_surf = None
        self._live_pixels = {}   # {obj_type: np.ndarray} overrides SPRITE_DATA
        self.live_path = None    # path currently supplying live sprites, or None

    def load_live_sprites(self, path):
        """Parse sprites from an assembly file (typically object_sprites.asm)
        and use them as the rendering source. Raises on I/O / parse failure;
        callers can ignore the exception for silent best-effort loads.
        Returns the list of object type IDs that were replaced.

        sprite_codec.decode_streams strips the first stream-A byte's advance
        bit when normalising to a row-0 grid. The asm renderer does NOT skip
        that advance — it lifts the plot pointer one row before the first
        pixel — so sprites with first_byte_has_advance=True (pod_stand,
        guns, laser turrets) appear one row lower in-game than in the
        editor unless we re-add the blank top row here. visualise_levels'
        static decoder already includes this row for the SPRITE_DATA
        fallback; mirror it for the live path so live and static agree.
        """
        import sprite_codec
        sprites = sprite_codec.load_sprites_from_file(str(path))
        new_pixels = {}
        for type_id, name in enumerate(sprite_codec.OBJECT_NAMES):
            if name not in sprites:
                continue
            spr = sprites[name]
            pixels = spr.pixels
            if spr.first_byte_has_advance and pixels:
                blank = [0] * len(pixels[0])
                pixels = [blank] + pixels
            new_pixels[type_id] = np.array(pixels, dtype=int)
        self._live_pixels = new_pixels
        self.live_path = str(path)
        self._cache.clear()      # force re-render at next get()
        return list(new_pixels.keys())

    def get(self, obj_type, level, landscape_colour=None, object_colour=None):
        """Get cached sprite. level is a LevelData instance.
        landscape_colour / object_colour optionally override the level's
        defaults (used in band mode to render objects in their band-resolved
        colours)."""
        lc = level.landscape_colour if landscape_colour is None else landscape_colour
        oc = level.object_colour if object_colour is None else object_colour
        key = (obj_type, lc, oc)
        if key not in self._cache:
            self._cache[key] = self._render(obj_type, level, lc, oc)
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

    def _render(self, obj_type, level, landscape_colour=None, object_colour=None):
        pixel_array = self._live_pixels.get(obj_type)
        if pixel_array is None:
            if obj_type not in SPRITE_DATA:
                return None
            pixel_array = decode_sprite(obj_type)
        if pixel_array.ndim != 2 or pixel_array.size == 0:
            return None                           # unpainted sprite, skip render
        h, w = pixel_array.shape

        lc = level.landscape_colour if landscape_colour is None else landscape_colour
        oc = level.object_colour if object_colour is None else object_colour
        palette = {
            0: (0, 0, 0, 0),
            1: (255, 255, 0, 255),
            2: hex_to_rgb(BBC_COLOURS[lc]) + (255,),
            3: hex_to_rgb(BBC_COLOURS[oc]) + (255,),
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

    @staticmethod
    def _snapshot(level):
        return (
            list(level.left_wall),
            list(level.right_wall),
            copy.deepcopy(level.objects),
            copy.deepcopy(level.checkpoints),
            copy.deepcopy(level.bands),
            level.gravity,
            level.no_wrap_y,
            level.landscape_colour,
            level.object_colour,
        )

    @staticmethod
    def _restore(level, snap):
        (level.left_wall, level.right_wall, level.objects,
         level.checkpoints, level.bands, level.gravity,
         level.no_wrap_y, level.landscape_colour,
         level.object_colour) = snap
        level.dirty = True

    def save(self, level):
        """Save a snapshot before making changes."""
        self.stack.append((level.level_num, self._snapshot(level)))
        if len(self.stack) > self.max_size:
            self.stack.pop(0)
        self.redo_stack.clear()

    def undo(self, levels):
        """Restore the most recent snapshot."""
        if not self.stack:
            return False
        lvn, snap = self.stack.pop()
        lv = levels[lvn]
        self.redo_stack.append((lvn, self._snapshot(lv)))
        self._restore(lv, snap)
        return True

    def redo(self, levels):
        if not self.redo_stack:
            return False
        lvn, snap = self.redo_stack.pop()
        lv = levels[lvn]
        self.stack.append((lvn, self._snapshot(lv)))
        self._restore(lv, snap)
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

        self.last_file_path = None  # last imported/exported file path
        if import_path:
            self.levels = import_beebasm(import_path)
            self.last_file_path = str(Path(import_path).resolve())
            print(f"Imported level data from {import_path}")
        else:
            self.levels = [LevelData.from_game_data(i) for i in range(6)]
        self.current_level = start_level
        self.camera = Camera()
        self.sprite_cache = SpriteCache()
        self.undo = UndoManager()

        # Best-effort: load live sprite data from the SWRAM include so the
        # editor shows whatever is currently painted in sprite_editor.py.
        # Silent on failure; static SPRITE_DATA remains as fallback.
        default_sprites = Path(__file__).parent / "output" / "object_sprites.asm"
        if default_sprites.exists():
            try:
                self.sprite_cache.load_live_sprites(default_sprites)
            except Exception as e:
                print(f"Could not load live sprites from {default_sprites}: {e}")

        self.mode = "wall"   # "wall", "object", or "checkpoint"
        self.show_grid = False
        self.running = True

        # Editing state
        self.dragging_wall = None     # ("left"|"right", start_row, saved_snapshot)
        self.dragging_pinch = None    # (anchor_x, last_row) — Shift+drag L=R
        self.drag_start_y = None
        self.selected_object = None   # index into objects list
        self.dragging_object = None    # None or (grab_dx, grab_dy) world-coord offset
        self.dragging_laser_endpoint = False  # True while dragging the selected laser's beam tip
        self.hovered_laser_endpoint = False   # True when mouse is over the endpoint handle
        self.dragging_well_radius = False     # True while dragging the selected gravity well's radius handle
        self.hovered_well_radius = False      # True when mouse is over the radius drag handle
        self.hovered_wall = None      # ("left"|"right", row)
        self.hovered_object = None    # index
        self.wall_tool = "draw"       # "draw" (freehand) or "line"
        self.line_start = None        # ("left"|"right", row, x) for line tool
        self.selected_checkpoint = None  # index into checkpoints list
        self.dragging_checkpoint = None  # ("spawn"|"window", index)
        self.dragging_bottom = False    # dragging the landscape bottom limit
        self.hovered_bottom = False     # hovering over the bottom limit handle
        self.dragging_no_wrap = False   # dragging the no-wrap Y threshold line
        self.hovered_no_wrap = False    # hovering over the no-wrap Y threshold line
        self.selected_band = None       # index into level.bands
        self.dragging_band = None       # (band_index, grab_dy) while dragging
        self.hovered_band = None        # band index under cursor

        # Panning state
        self.panning = False
        self.pan_start = None

        # Inspector pane state
        self.inspector_scroll = 0          # field section y-scroll offset (px)
        self.palette_scroll = 0            # palette section y-scroll offset (px)
        self.inspector_active_field = None # field id with keyboard focus
        self.input_focus = False           # True when a text widget owns the keyboard
        self.text_entry_field = None       # field id being text-edited
        self.text_entry_buf = ""
        self.text_entry_orig = None
        self.inspector_split = 0.40        # fraction of inspector height for fields (palette gets the rest)
        self.hovered_btn = None            # (field_id, "dec"|"inc"|"val") or None
        self.palette_armed_type = None     # object type armed for click-to-place
        self.ref_pick_field = None         # field id expecting a canvas pick
        self.ref_pick_target = None
        self.ref_pick_level = None
        # Legacy obj_menu state (kept briefly for compatibility)
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
        self.camera.viewport_w = self.screen.get_width() - INSPECTOR_W
        lv = self.level
        total_h = lv.num_rows
        self.camera.zoom = max(0.5, self.camera.viewport_h / total_h * 0.9)
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
                if self._confirm_exit():
                    self.running = False

            elif event.type == pygame.VIDEORESIZE:
                self.camera.viewport_w = event.w - INSPECTOR_W
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
                insp_x = self.screen.get_width() - INSPECTOR_W
                if mx >= insp_x:
                    # Scroll inspector pane sections
                    if my < self._inspector_split_y():
                        self.inspector_scroll = max(0, self.inspector_scroll - event.y * 20)
                    else:
                        self.palette_scroll = max(0, self.palette_scroll - event.y * 20)
                elif my > TOOLBAR_H and my < self.screen.get_height() - STATUS_H:
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

        # Text entry mode: only Enter/Escape/Tab/Backspace pass through
        if self.input_focus:
            if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                self._commit_text_entry()
            elif event.key == pygame.K_ESCAPE:
                self._cancel_text_entry()
            elif event.key == pygame.K_BACKSPACE:
                self.text_entry_buf = self.text_entry_buf[:-1]
            elif event.unicode and event.unicode.isprintable():
                self.text_entry_buf += event.unicode
            return

        # Cancel armed placement or ref-pick on Escape (early return so they
        # take priority over the mode-specific Escape in the elif chain below)
        if event.key == pygame.K_ESCAPE and self.palette_armed_type is not None:
            self.palette_armed_type = None
            return
        if event.key == pygame.K_ESCAPE and self.ref_pick_field is not None:
            self.ref_pick_field = None
            return

        # Level switching: 1-6
        if event.key in (pygame.K_1, pygame.K_2, pygame.K_3,
                         pygame.K_4, pygame.K_5, pygame.K_6):
            self.current_level = event.key - pygame.K_1
            self._centre_on_level()
            self.selected_object = None
            self.dragging_wall = None
            self.dragging_bottom = False
            self.dragging_no_wrap = False

        elif event.key == pygame.K_w:
            self.mode = "wall"
            self.selected_object = None
            self.selected_checkpoint = None
            self.palette_armed_type = None

        elif event.key == pygame.K_l:
            if self.mode == "wall":
                self.wall_tool = "line" if self.wall_tool != "line" else "draw"
                self.line_start = None

        elif event.key == pygame.K_c:
            self.mode = "checkpoint"
            self.dragging_wall = None
            self.dragging_bottom = False
            self.dragging_no_wrap = False
            self.line_start = None
            self.selected_object = None
            self.palette_armed_type = None

        elif event.key == pygame.K_o:
            self.mode = "object"
            self.dragging_wall = None
            self.dragging_bottom = False
            self.dragging_no_wrap = False
            self.line_start = None
            self.selected_checkpoint = None

        elif event.key == pygame.K_b:
            self.mode = "band"
            self.dragging_wall = None
            self.dragging_bottom = False
            self.dragging_no_wrap = False
            self.line_start = None
            self.selected_object = None
            self.selected_checkpoint = None
            self.palette_armed_type = None

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
            self._quick_save()

        elif event.key == pygame.K_i and ctrl:
            self._import()

        elif event.key == pygame.K_ESCAPE:
            if self.line_start:
                self.line_start = None
            self.palette_armed_type = None
            self.ref_pick_field = None

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
            elif self.selected_band is not None and self.mode == "band":
                self.undo.save(self.level)
                self.level.bands.pop(self.selected_band)
                self.level.dirty = True
                self.selected_band = None

        elif event.key in (pygame.K_k, pygame.K_j) \
                and self.mode == "band" and self.selected_band is not None:
            attr = "landscape_colour" if event.key == pygame.K_k else "object_colour"
            self._cycle_band_colour(attr)

        elif event.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET,
                           pygame.K_COMMA, pygame.K_PERIOD):
            if self.mode == "band" and self.selected_band is not None:
                self._adjust_selected_band_gravity(event.key, shift)
            elif (self.selected_object is not None
                    and self.level.objects[self.selected_object]["type"] == OBJECT_GRAVITY_WELL):
                self._adjust_selected_well_strength(event.key, shift)
            elif (self.selected_object is not None
                    and self.level.objects[self.selected_object]["type"] in BOBBING_MINE_TYPES):
                self._adjust_selected_mine_param(event.key, shift)
            elif (self.selected_object is not None
                    and self.level.objects[self.selected_object]["type"] == OBJECT_TELEPORTER):
                self._adjust_selected_teleporter_dest(event.key)
            else:
                self._adjust_selected_gun_aim(event.key)

        elif event.key == pygame.K_BACKSLASH:
            self._reset_selected_laser_endpoint()

        elif event.key == pygame.K_F5:
            self._reload_live_sprites()

    def _reload_live_sprites(self):
        """Reload object sprites from the current live path, or prompt for
        one if none is set. Useful after painting in sprite_editor while the
        level editor is still open.
        """
        path = self.sprite_cache.live_path
        if path is None or not Path(path).exists():
            root = tk.Tk(); root.withdraw()
            picked = filedialog.askopenfilename(
                title="Import object sprites",
                initialdir=str(Path(__file__).parent / "output"),
                filetypes=[("BeebAsm assembly", "*.asm *.6502"),
                           ("All files", "*.*")])
            root.destroy(); self._drain_input_events()
            if not picked:
                return
            path = picked
        try:
            loaded = self.sprite_cache.load_live_sprites(path)
            print(f"Loaded {len(loaded)} live sprites from {path}")
        except Exception as e:
            print(f"Failed to load sprites from {path}: {e}")

    def _adjust_selected_gun_aim(self, key):
        """Edit the gun_aim byte for the selected firing object.

        Guns:
            [ / ]  rotate base angle by -4 / +4 in the 32-angle system
            , / .  decrement / increment spread mask index (0..3)
        Lasers (gun_aim repurposed for period/duty/phase, see thrust.6502
        update_one_laser_beam):
            [ / ]  decrement / increment phase index (low nibble, 0..15)
            , / .  decrement / increment duty  index (high nibble, 0..15)
        No-op if the selected object doesn't fire. (- / = are taken by zoom.)
        """
        if self.selected_object is None or self.mode != "object":
            return
        obj = self.level.objects[self.selected_object]
        if obj["type"] not in OBJECT_FIRING_TYPES:
            return

        aim = obj.get("gun_aim", 0x00)

        if obj["type"] in OBJECT_LASER_TYPES:
            phase_idx = aim & 0x0F
            duty_idx = (aim & 0xF0) >> 4
            if key == pygame.K_LEFTBRACKET:
                phase_idx = (phase_idx - 1) & 0x0F
            elif key == pygame.K_RIGHTBRACKET:
                phase_idx = (phase_idx + 1) & 0x0F
            elif key == pygame.K_COMMA:
                duty_idx = (duty_idx - 1) & 0x0F
            elif key == pygame.K_PERIOD:
                duty_idx = (duty_idx + 1) & 0x0F
            new_aim = (duty_idx << 4) | phase_idx
        else:
            base = aim & 0x1C                      # bits 4-2: base angle (step 4)
            spread_idx = aim & 0x03                # bits 1-0: spread mask index
            if key == pygame.K_LEFTBRACKET:
                base = (base - 4) & 0x1C
            elif key == pygame.K_RIGHTBRACKET:
                base = (base + 4) & 0x1C
            elif key == pygame.K_COMMA:
                spread_idx = (spread_idx - 1) & 0x03
            elif key == pygame.K_PERIOD:
                spread_idx = (spread_idx + 1) & 0x03
            new_aim = base | spread_idx

        if new_aim != aim:
            self.undo.save(self.level)
            obj["gun_aim"] = new_aim
            self.level.dirty = True

    def _adjust_selected_well_strength(self, key, shift):
        """[ / ]  nudge well_strength by -1 / +1 (or -10 / +10 with shift)."""
        if self.selected_object is None:
            return
        obj = self.level.objects[self.selected_object]
        if obj["type"] != OBJECT_GRAVITY_WELL:
            return
        step = 10 if shift else 1
        cur = obj.get("well_strength", 0)
        if key == pygame.K_LEFTBRACKET:
            new = cur - step
        elif key == pygame.K_RIGHTBRACKET:
            new = cur + step
        else:
            return
        new = max(-127, min(127, new))
        if new != cur:
            self.undo.save(self.level)
            obj["well_strength"] = new
            self.level.dirty = True

    def _adjust_selected_mine_param(self, key, shift):
        """[ / ]  nudge mine_amp by -1 / +1 (or -10 / +10 with shift).
        , / .    nudge mine_phase by -1 / +1 (or -8 / +8 with shift)."""
        if self.selected_object is None:
            return
        obj = self.level.objects[self.selected_object]
        if obj["type"] not in BOBBING_MINE_TYPES:
            return
        if key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
            step = 10 if shift else 1
            cur = obj.get("mine_amp", 0)
            new = cur + (step if key == pygame.K_RIGHTBRACKET else -step)
            new = max(-127, min(127, new))
            if new != cur:
                self.undo.save(self.level)
                obj["mine_amp"] = new
                self.level.dirty = True
        elif key in (pygame.K_COMMA, pygame.K_PERIOD):
            step = 8 if shift else 1
            cur = obj.get("mine_phase", 0)
            new = (cur + (step if key == pygame.K_PERIOD else -step)) & 0xFF
            if new != cur:
                self.undo.save(self.level)
                obj["mine_phase"] = new
                self.level.dirty = True

    def _adjust_selected_teleporter_dest(self, key):
        """[ / ] cycle the selected teleporter's destination checkpoint index."""
        if self.selected_object is None:
            return
        obj = self.level.objects[self.selected_object]
        if obj["type"] != OBJECT_TELEPORTER:
            return
        n = len(self.level.checkpoints)
        if n <= 0:
            return
        cur = obj.get("teleport_dest", 0) % n
        if key == pygame.K_LEFTBRACKET:
            new = (cur - 1) % n
        elif key == pygame.K_RIGHTBRACKET:
            new = (cur + 1) % n
        else:
            return
        if new != obj.get("teleport_dest", 0):
            self.undo.save(self.level)
            obj["teleport_dest"] = new
            self.level.dirty = True

    def _reset_selected_laser_endpoint(self):
        """Restore the selected laser's dx/dy to its orientation default."""
        if self.selected_object is None:
            return
        obj = self.level.objects[self.selected_object]
        t = obj["type"]
        if t not in OBJECT_LASER_TYPES:
            return
        new_dx = LASER_BEAM_DX_PIXELS[t]
        new_dy = LASER_BEAM_DY_ROWS[t]
        if obj.get("laser_dx") != new_dx or obj.get("laser_dy") != new_dy:
            self.undo.save(self.level)
            obj["laser_dx"] = new_dx
            obj["laser_dy"] = new_dy
            self.level.dirty = True

    def _handle_mouse_down(self, event):
        mx, my = event.pos

        # Toolbar click
        if my < TOOLBAR_H:
            self._handle_toolbar_click(mx, my)
            return

        # Below viewport
        if my > self.screen.get_height() - STATUS_H:
            return

        # Inspector pane click (right strip)
        if mx >= self.screen.get_width() - INSPECTOR_W:
            self._handle_inspector_mouse_down(mx, my, event.button)
            return

        # Commit any open text entry when clicking outside inspector
        if self.input_focus:
            self._commit_text_entry()

        wx, wy = self.camera.screen_to_world(mx, my)

        # Ref-pick mode: route left-clicks on canvas to the picker
        if self.ref_pick_field is not None and event.button == 1:
            self._handle_ref_pick_click(mx, my)
            return

        # Armed placement: left-click drops; SHIFT keeps it armed for rapid placement,
        # otherwise the palette disarms after a single drop. Right-click cancels.
        if self.palette_armed_type is not None and event.button == 1:
            self._place_armed_object(int(wx), int(wy))
            if not (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                self.palette_armed_type = None
            return
        if self.palette_armed_type is not None and event.button == 3:
            self.palette_armed_type = None
            return

        # Middle button or right button panning
        if event.button == 2:
            self.panning = True
            self.pan_start = (mx, my)
            return

        if event.button == 3:  # Right click
            if self.mode == "wall":
                # Toggle no-wrap Y threshold line
                lv = self.level
                if lv.no_wrap_y < 0xFFFF and self._hit_test_no_wrap(mx, my):
                    # Remove the line
                    self.undo.save(lv)
                    lv.no_wrap_y = 0xFFFF
                    lv.dirty = True
                else:
                    # Place the line at cursor Y
                    self.undo.save(lv)
                    lv.no_wrap_y = max(0, min(0xFFFE, int(wy)))
                    lv.dirty = True
            elif self.mode == "object":
                # Right-click: disarm palette if armed; otherwise no-op
                # (Object placement is done via the palette grid on the right)
                self.palette_armed_type = None
            elif self.mode == "checkpoint":
                self._handle_checkpoint_right_click(mx, my)
            elif self.mode == "band":
                self._handle_band_right_click(mx, my)
            return

        # Left click
        if event.button == 1:
            if self.mode == "wall" and self.wall_tool == "line":
                self._handle_line_tool_click(mx, my)
            elif self.mode == "wall":
                # Check no-wrap line, then bottom handle, then wall edges
                if self._hit_test_no_wrap(mx, my):
                    self.undo.save(self.level)
                    self.dragging_no_wrap = True
                    return
                if self._hit_test_bottom(mx, my):
                    self.undo.save(self.level)
                    self.dragging_bottom = True
                    return
                hit = self._hit_test_wall(mx, my)
                if hit:
                    side, row = hit
                    self.undo.save(self.level)
                    if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                        # Snap the opposite wall to match (L=R pinch point).
                        # Drag continues to apply the same anchor value to
                        # subsequent rows the cursor passes through.
                        lv = self.level
                        anchor_x = lv.left_wall[row] if side == "left" else lv.right_wall[row]
                        lv.left_wall[row] = anchor_x
                        lv.right_wall[row] = anchor_x
                        lv.terrain_dirty = True
                        self.hovered_wall = (side, row)
                        self.dragging_pinch = (anchor_x, row)
                    else:
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

            elif self.mode == "band":
                hit = self._hit_test_band(mx, my)
                if hit is not None:
                    self.selected_band = hit
                    band = self.level.bands[hit]
                    grab_dy = wy - band["y"]
                    self.dragging_band = (hit, grab_dy)
                    self.undo.save(self.level)
                else:
                    self.selected_band = None
                    self.panning = True
                    self.pan_start = (mx, my)

            elif self.mode == "object":
                # Endpoint handle on selected laser takes priority over the
                # object hit-test so the handle stays grabbable even when it
                # overlaps another sprite.
                if self._hit_test_laser_endpoint(mx, my):
                    self.undo.save(self.level)
                    self.dragging_laser_endpoint = True
                    self._set_laser_endpoint_from_screen(mx, my)
                    return
                if self._hit_test_well_radius(mx, my):
                    self.undo.save(self.level)
                    self.dragging_well_radius = True
                    self._set_well_radius_from_screen(mx)
                    return
                # Wells have no sprite, so _hit_test_object skips them; check
                # well centres separately first. Mines now render via the
                # standard sprite path so _hit_test_object handles them.
                well_hit = self._hit_test_well(mx, my)
                if well_hit is not None:
                    self.selected_object = well_hit
                    obj = self.level.objects[well_hit]
                    wx, wy = self.camera.screen_to_world(mx, my)
                    grab_dx = wx - obj["x"]
                    grab_dy = wy - obj["y"]
                    self.dragging_object = (grab_dx, grab_dy)
                    self.undo.save(self.level)
                    return
                hit = self._hit_test_object(mx, my)
                if hit is not None:
                    self.selected_object = hit
                    obj = self.level.objects[hit]
                    wx, wy = self.camera.screen_to_world(mx, my)
                    grab_dx = wx - obj["x"]
                    grab_dy = wy - obj["y"]
                    self.dragging_object = (grab_dx, grab_dy)
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
            if self.dragging_pinch:
                self.level.dirty = True
                self.dragging_pinch = None
            if self.dragging_bottom:
                self.level.dirty = True
                self.dragging_bottom = False
            if self.dragging_no_wrap:
                self.level.dirty = True
                self.dragging_no_wrap = False
            if self.dragging_object:
                self.level.dirty = True
                self.dragging_object = None
            if self.dragging_laser_endpoint:
                self.level.dirty = True
                self.dragging_laser_endpoint = False
            if self.dragging_well_radius:
                self.level.dirty = True
                self.dragging_well_radius = False
            if self.dragging_checkpoint:
                self.level.dirty = True
                self.dragging_checkpoint = None
            if self.dragging_band:
                # Re-sort and remap selected_band index after drag.
                idx, _ = self.dragging_band
                target = self.level.bands[idx]
                self.level.bands.sort(key=lambda b: b["y"])
                self.selected_band = self.level.bands.index(target)
                self.level.dirty = True
                self.dragging_band = None

    def _handle_mouse_move(self, event):
        mx, my = event.pos

        if self.panning and self.pan_start:
            dx = self.pan_start[0] - mx
            dy = self.pan_start[1] - my
            self.camera.pan(dx / self.camera.x_scale, dy / self.camera.y_scale)
            self.pan_start = (mx, my)
            return

        if self.dragging_no_wrap:
            wx, wy = self.camera.screen_to_world(mx, my)
            self.level.no_wrap_y = max(0, min(0xFFFE, int(wy)))
            return

        if self.dragging_bottom:
            wx, wy = self.camera.screen_to_world(mx, my)
            lv = self.level
            new_rows = max(256, int(wy))  # minimum 256 (first 255 rows are fixed)
            old_rows = lv.num_rows
            if new_rows > old_rows:
                # Extend walls by repeating last value
                last_left = lv.left_wall[-1] if lv.left_wall else 0
                last_right = lv.right_wall[-1] if lv.right_wall else 0xFF
                lv.left_wall.extend([last_left] * (new_rows - len(lv.left_wall)))
                lv.right_wall.extend([last_right] * (new_rows - len(lv.right_wall)))
            elif new_rows < old_rows:
                # Truncate walls
                lv.left_wall = lv.left_wall[:new_rows]
                lv.right_wall = lv.right_wall[:new_rows]
            lv.terrain_dirty = True
            return

        if self.dragging_pinch:
            _, wy = self.camera.screen_to_world(mx, my)
            anchor_x, last_row = self.dragging_pinch
            lv = self.level
            row = max(0, min(int(wy), len(lv.left_wall) - 1, len(lv.right_wall) - 1))
            step = 1 if row >= last_row else -1
            for r in range(last_row, row + step, step):
                if 0 <= r < len(lv.left_wall) and r < len(lv.right_wall):
                    lv.left_wall[r] = anchor_x
                    lv.right_wall[r] = anchor_x
            lv.terrain_dirty = True
            self.hovered_wall = ("left", row)
            self.dragging_pinch = (anchor_x, row)
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
            self.hovered_wall = (side, row)

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

        if self.dragging_band:
            _, wy = self.camera.screen_to_world(mx, my)
            idx, grab_dy = self.dragging_band
            self.level.bands[idx]["y"] = max(0, min(0xFFFE, int(wy - grab_dy)))
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

        if self.dragging_laser_endpoint and self.selected_object is not None:
            self._set_laser_endpoint_from_screen(mx, my)
            return

        if self.dragging_well_radius and self.selected_object is not None:
            self._set_well_radius_from_screen(mx)
            return

        if self.dragging_object and self.selected_object is not None:
            grab_dx, grab_dy = self.dragging_object
            wx, wy = self.camera.screen_to_world(mx, my)
            obj = self.level.objects[self.selected_object]
            obj["x"] = max(0, min(255, int(wx - grab_dx)))
            obj["y"] = max(0, int(wy - grab_dy))
            return

        # Hover detection — update inspector button hover and viewport hover
        insp_x = self.screen.get_width() - INSPECTOR_W
        if mx >= insp_x:
            self._update_inspector_hover(mx, my)
            return
        self.hovered_btn = None
        if my > TOOLBAR_H and my < self.screen.get_height() - STATUS_H:
            if self.mode == "wall":
                self.hovered_no_wrap = self._hit_test_no_wrap(mx, my)
                self.hovered_bottom = self._hit_test_bottom(mx, my)
                self.hovered_wall = self._hit_test_wall(mx, my)
            elif self.mode == "object":
                self.hovered_object = self._hit_test_object(mx, my)
                if self.hovered_object is None:
                    self.hovered_object = self._hit_test_well(mx, my)
                self.hovered_laser_endpoint = self._hit_test_laser_endpoint(mx, my)
                self.hovered_well_radius = self._hit_test_well_radius(mx, my)
            elif self.mode == "band":
                self.hovered_band = self._hit_test_band(mx, my)
        else:
            self.hovered_laser_endpoint = False
            self.hovered_well_radius = False

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

    def _hit_test_bottom(self, mx, my):
        """Test if screen position is near the landscape bottom boundary."""
        lv = self.level
        _, bottom_sy = self.camera.world_to_screen(0, lv.num_rows)
        # Check the full horizontal extent of the world
        wx0, _ = self.camera.world_to_screen(0, 0)
        wx256, _ = self.camera.world_to_screen(256, 0)
        if mx >= wx0 and mx <= wx256 and abs(my - bottom_sy) < BOTTOM_HIT_TOLERANCE:
            return True
        return False

    def _hit_test_band(self, mx, my):
        """Test if screen position is near a band Y line. Returns band index or None.
        Bands span the full editor width (like checkpoint threshold lines)."""
        for i, band in enumerate(self.level.bands):
            _, line_sy = self.camera.world_to_screen(0, band["y"])
            if abs(my - line_sy) < BOTTOM_HIT_TOLERANCE:
                return i
        return None

    def _handle_band_right_click(self, mx, my):
        """Right-click in band mode: add a band at cursor Y, or delete one if hit."""
        hit = self._hit_test_band(mx, my)
        if hit is not None:
            self.undo.save(self.level)
            self.level.bands.pop(hit)
            self.level.dirty = True
            self.selected_band = None
            return
        _, wy = self.camera.screen_to_world(mx, my)
        new_y = max(0, min(0xFFFE, int(wy)))
        self.undo.save(self.level)
        # Default new band gravity = level base, so it has no effect until edited.
        # Colour overrides default to None (inherit level default).
        self.level.bands.append({"y": new_y, "gravity": self.level.gravity,
                                  "landscape_colour": None, "object_colour": None})
        self.level.bands.sort(key=lambda b: b["y"])
        self.level.dirty = True
        self.selected_band = next(
            (i for i, b in enumerate(self.level.bands) if b["y"] == new_y), None)

    def _cycle_band_colour(self, attr):
        """Cycle a band's landscape/object colour override.
        None (inherit) -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> None.
        Skips 0 (black) to match the level swatch behaviour."""
        band = self.level.bands[self.selected_band]
        cur = band.get(attr)
        if cur is None:
            new = 1
        elif cur >= 7:
            new = None
        else:
            new = cur + 1
        self.undo.save(self.level)
        band[attr] = new
        self.level.dirty = True
        self.sprite_cache.clear()

    def _adjust_selected_band_gravity(self, key, shift):
        """[/]/,/. tweak the selected band's gravity_FRAC; shift = ±$10."""
        band = self.level.bands[self.selected_band]
        delta = 0
        if key in (pygame.K_LEFTBRACKET, pygame.K_COMMA):
            delta = -1
        elif key in (pygame.K_RIGHTBRACKET, pygame.K_PERIOD):
            delta = +1
        if shift:
            delta *= 16
        self.undo.save(self.level)
        band["gravity"] = (band["gravity"] + delta) & 0xFF
        self.level.dirty = True

    def _hit_test_no_wrap(self, mx, my):
        """Test if screen position is near the no-wrap Y threshold line."""
        lv = self.level
        if lv.no_wrap_y >= 0xFFFF:
            return False
        _, line_sy = self.camera.world_to_screen(0, lv.no_wrap_y)
        wx0, _ = self.camera.world_to_screen(0, 0)
        wx256, _ = self.camera.world_to_screen(256, 0)
        if mx >= wx0 and mx <= wx256 and abs(my - line_sy) < BOTTOM_HIT_TOLERANCE:
            return True
        return False

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
            # Check spawn marker (ship sprite bounding box).
            # spawn_y is the midpoint Y the game writes into midpoint_ypos at
            # reset; the ship plots above that by midpoint_deltay at the
            # default tether angle (≈ _SPAWN_MIDPOINT_TO_SHIP_DY world Y).
            ship_top_y = cp["spawn_y"] - _SPAWN_MIDPOINT_TO_SHIP_DY
            sx, sy = cam.world_to_screen(cp["spawn_x"] + ship_offset_x,
                                         ship_top_y)
            ex, ey = cam.world_to_screen(cp["spawn_x"] + ship_offset_x + ship_world_w,
                                         ship_top_y + ship_world_h)
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
            # Add new checkpoint at click position. The click marks where the
            # ship sprite top should appear; spawn_y stored in the reset table
            # is the midpoint Y, _SPAWN_MIDPOINT_TO_SHIP_DY world units below.
            wx, wy = self.camera.screen_to_world(mx, my)
            spawn_x = max(0, min(255, int(wx)))
            spawn_y = max(0, min(0xFFFF, int(wy + _SPAWN_MIDPOINT_TO_SHIP_DY)))
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
            if obj["type"] == OBJECT_TELEPORTER:
                # Pad has no sprite (yet); hit-test a small circle at obj pos.
                cx, cy = self.camera.world_to_screen(obj["x"], obj["y"])
                r = 10
                if (mx - cx) ** 2 + (my - cy) ** 2 <= r * r:
                    return i
                continue
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

    def _hit_test_laser_endpoint(self, mx, my):
        """If the selected object is a laser and (mx, my) is within the
        endpoint drag handle, return True. Else False."""
        if self.selected_object is None:
            return False
        obj = self.level.objects[self.selected_object]
        if obj["type"] not in OBJECT_LASER_TYPES:
            return False
        sprite = self.sprite_cache.get(obj["type"], self.level)
        if sprite is None:
            return False
        # Recompute beam screen coords using the same draw_w/draw_h as the
        # renderer (sprite dimensions in screen px). Must match the renderer's
        # ox/oy of obj["x"], obj["y"] — no -1 offset.
        sx, sy = self.camera.world_to_screen(obj["x"], obj["y"])
        ex, ey = self.camera.world_to_screen(
            obj["x"] + sprite.get_width() / 4,
            obj["y"] + sprite.get_height() / 2)
        draw_w = ex - sx
        draw_h = ey - sy
        _, _, end_sx, end_sy = self._laser_beam_screen_coords(obj, sx, sy, draw_w, draw_h)
        # Generous click radius so the handle's easy to grab.
        r = LASER_ENDPOINT_HANDLE_RADIUS + LASER_ENDPOINT_HIT_PADDING
        return (mx - end_sx) ** 2 + (my - end_sy) ** 2 <= r * r

    def _set_laser_endpoint_from_screen(self, mx, my):
        """Convert (mx, my) into per-instance laser_dx / laser_dy for the
        selected laser. Inverse of _laser_beam_screen_coords."""
        obj = self.level.objects[self.selected_object]
        sprite = self.sprite_cache.get(obj["type"], self.level)
        if sprite is None:
            return
        sx, sy = self.camera.world_to_screen(obj["x"], obj["y"])
        ex, ey = self.camera.world_to_screen(
            obj["x"] + sprite.get_width() / 4,
            obj["y"] + sprite.get_height() / 2)
        draw_w = ex - sx
        draw_h = ey - sy
        char_w_px = draw_w / 5.0
        row_h_px  = draw_h / 8.0
        barrel_sx = sx + LASER_BARREL_X_CHARS[obj["type"]] * char_w_px
        barrel_sy = sy + LASER_BARREL_Y_ROWS[obj["type"]]  * row_h_px
        # Must match _laser_beam_screen_coords scale.
        scale = char_w_px / 4.0
        if scale <= 0:
            return
        dx = round((mx - barrel_sx) / scale)
        dy = round((my - barrel_sy) / scale)
        # Clamp to signed 8-bit range so the asm export round-trips cleanly.
        obj["laser_dx"] = max(-128, min(127, dx))
        obj["laser_dy"] = max(-128, min(127, dy))
        self.level.dirty = True

    def _well_screen_geometry(self, obj):
        """Return (cx, cy, rx_screen, ry_screen) for a gravity well in screen
        pixels: centre and per-axis screen-pixel projection of the radius.
        The game's pull region is a pixel-square diamond — 2*|dx_world| +
        |dy_world| < radius — so X reach is r/2 world units and Y reach is r
        world units. The camera then applies its own world→screen aspect
        on top, so rx_screen ≈ ry_screen for a true visual diamond."""
        cx_w, cy_w = obj["x"], obj["y"]
        cx, cy = self.camera.world_to_screen(cx_w, cy_w)
        r = obj.get("well_radius", 0)
        rx_end, _ = self.camera.world_to_screen(cx_w + r / 2.0, cy_w)
        _, ry_end = self.camera.world_to_screen(cx_w, cy_w + r)
        return cx, cy, rx_end - cx, ry_end - cy

    def _hit_test_well(self, mx, my):
        """Return object index if (mx, my) is over a gravity well's centre dot."""
        for i, obj in enumerate(self.level.objects):
            if obj["type"] != OBJECT_GRAVITY_WELL:
                continue
            cx, cy, _, _ = self._well_screen_geometry(obj)
            r = GRAVITY_WELL_CENTRE_RADIUS + GRAVITY_WELL_CENTRE_HIT_PADDING
            if (mx - cx) ** 2 + (my - cy) ** 2 <= r * r:
                return i
        return None

    def _hit_test_well_radius(self, mx, my):
        """If the selected object is a gravity well and (mx, my) is over the
        radius drag handle (right vertex of the diamond), return True."""
        if self.selected_object is None:
            return False
        obj = self.level.objects[self.selected_object]
        if obj["type"] != OBJECT_GRAVITY_WELL:
            return False
        if obj.get("well_radius", 0) <= 0:
            return False
        cx, cy, rx_screen, _ = self._well_screen_geometry(obj)
        hx, hy = cx + rx_screen, cy
        r = GRAVITY_WELL_HANDLE_RADIUS + GRAVITY_WELL_HANDLE_HIT_PADDING
        return (mx - hx) ** 2 + (my - hy) ** 2 <= r * r

    def _set_well_radius_from_screen(self, mx):
        """Inverse of _well_screen_geometry's X axis: convert mouse X into
        world-coord radius for the selected well, clamped 0..127. The X
        vertex sits at cx_w + r/2 (pixel-square diamond), so radius is twice
        the world-X distance from the centre."""
        obj = self.level.objects[self.selected_object]
        cx_w = obj["x"]
        cx, _ = self.camera.world_to_screen(cx_w, 0)
        unit_x, _ = self.camera.world_to_screen(cx_w + 1, 0)
        scale = unit_x - cx
        if scale <= 0:
            return
        r = round(2 * (mx - cx) / scale)
        obj["well_radius"] = max(0, min(127, r))
        self.level.dirty = True

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
            self.selected_band = None
            self.palette_armed_type = None
        elif mode_x + 70 <= mx < mode_x + 130:
            self.mode = "object"
            self.dragging_wall = None
            self.dragging_bottom = False
            self.dragging_no_wrap = False
            self.line_start = None
            self.selected_checkpoint = None
            self.selected_band = None
        elif mode_x + 140 <= mx < mode_x + 200:
            self.mode = "checkpoint"
            self.dragging_wall = None
            self.dragging_bottom = False
            self.dragging_no_wrap = False
            self.line_start = None
            self.selected_object = None
            self.selected_band = None
            self.palette_armed_type = None
        elif mode_x + 210 <= mx < mode_x + 270:
            self.mode = "band"
            self.dragging_wall = None
            self.dragging_bottom = False
            self.dragging_no_wrap = False
            self.line_start = None
            self.selected_object = None
            self.selected_checkpoint = None
            self.palette_armed_type = None

        # Import button
        vw = self.screen.get_width() - INSPECTOR_W
        import_x = vw - 200
        if import_x <= mx < import_x + 90:
            self._import()

        # Export button
        export_x = vw - 100
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
            is_well = obj_type == OBJECT_GRAVITY_WELL
            is_mine = obj_type in BOBBING_MINE_TYPES
            is_teleporter = obj_type == OBJECT_TELEPORTER
            self.level.objects.append({"x": wx, "y": wy, "type": obj_type,
                                        "gun_aim": 0x00,
                                        "laser_dx": LASER_BEAM_DX_PIXELS.get(obj_type, 0),
                                        "laser_dy": LASER_BEAM_DY_ROWS.get(obj_type, 0),
                                        "well_radius": GRAVITY_WELL_DEFAULT_RADIUS if is_well else 0,
                                        "well_strength": GRAVITY_WELL_DEFAULT_STRENGTH if is_well else 0,
                                        "mine_phase": BOBBING_MINE_DEFAULT_PHASE if is_mine else 0,
                                        "mine_amp": BOBBING_MINE_DEFAULT_AMP if is_mine else 0,
                                        "teleport_dest": TELEPORTER_DEFAULT_DEST if is_teleporter else 0})
            self.level.dirty = True
            self.selected_object = len(self.level.objects) - 1
        self.show_obj_menu = False

    def _drain_input_events(self):
        """Clear buffered pygame input events after a modal tk dialog so that
        clicks/keys the user mashed while the dialog was up don't re-trigger
        the button we just returned from (stacking dialogs).
        """
        pygame.event.clear(pygame.MOUSEBUTTONDOWN)
        pygame.event.clear(pygame.MOUSEBUTTONUP)
        pygame.event.clear(pygame.KEYDOWN)

    def _check_landscape_bottoms(self):
        """Run the open-bottoms integrity check. Returns True to proceed
        with export, False to abort. Auto-closes if the user chose Yes.
        """
        open_levels = [lv.level_num for lv in self.levels
                       if _is_bottom_open(lv.left_wall, lv.right_wall)]
        if not open_levels:
            return True

        names = ", ".join(str(n + 1) for n in open_levels)
        root = tk.Tk()
        root.withdraw()
        result = messagebox.askyesnocancel(
            "Open landscape bottom",
            f"Level(s) {names} have open bottoms — the left and right "
            f"walls don't converge at the bottom of the landscape.\n\n"
            f"This will cause rendering artifacts in-game.\n\n"
            f"Yes = auto-close and export\n"
            f"No = export anyway\n"
            f"Cancel = abort export",
        )
        root.destroy(); self._drain_input_events()
        if result is None:
            return False
        if result:
            for n in open_levels:
                lv = self.levels[n]
                _close_bottom(lv.left_wall, lv.right_wall)
                lv.terrain_dirty = True
                lv.dirty = True
            print(f"Auto-closed landscape bottom on level(s) {names}")
        return True

    def _check_wiring(self):
        """Validate every level's switch wiring before export.

        Auto-prunes wiring entries whose switch object has been deleted or
        is no longer a switch type. Blocks the export with a dialog if any
        remaining entry has a dangling target_obj_index, or wires to the
        pod (object 0, type $05) — the pod uses single-instance engine
        state that isn't safe to alive-toggle or destroy.

        Returns True to proceed, False to abort.
        """
        problems = []
        for lv in self.levels:
            if not lv.wiring:
                continue
            stale = []
            total_entries = 0
            for sw_idx, entries in lv.wiring.items():
                # Switch must still exist and still be a switch type.
                if not (0 <= sw_idx < len(lv.objects)) or lv.objects[sw_idx]["type"] not in (0x07, 0x08):
                    stale.append(sw_idx)
                    continue
                # Defensive: tolerate a stray single-entry dict.
                if isinstance(entries, dict):
                    entries = [entries]
                    lv.wiring[sw_idx] = entries
                for entry_i, entry in enumerate(entries):
                    total_entries += 1
                    action = entry.get("action", 0)
                    target = entry.get("target", 0xFF)
                    label = f"L{lv.level_num + 1} switch #{sw_idx} entry #{entry_i + 1}"
                    if action == 0 or target == 0xFF:
                        continue  # placeholder — exporter handles as no-op
                    if not (0 <= target < len(lv.objects)):
                        problems.append(f"{label}: target #{target} doesn't exist")
                        continue
                    if target == 0 and lv.objects[0]["type"] == 0x05:
                        problems.append(f"{label}: targets pod (object 0)")
                    if action in SWITCH_PARAM_ACTIONS:
                        arg_a = entry.get("arg_a", 0)
                        if arg_a > 2:
                            problems.append(f"{label}: slot {arg_a} out of range (must be 0..2)")
            if total_entries > 8:
                problems.append(
                    f"L{lv.level_num + 1}: {total_entries} wiring entries across all switches "
                    f"exceeds the 8-slot table cap")
            for sw_idx in stale:
                lv.wiring.pop(sw_idx, None)
                lv.dirty = True

        if problems:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Wiring validation failed",
                "Cannot export — fix these wiring problems first:\n\n  " +
                "\n  ".join(problems),
            )
            root.destroy(); self._drain_input_events()
            return False
        return True

    def _save_to_file(self, path):
        """Write level data to the given path. No dialog, no prompts."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        src = export_beebasm(self.levels)
        Path(path).write_text(src)
        self.last_file_path = str(Path(path).resolve())
        # Clear per-level dirty flags so the exit check reflects true state.
        for lv in self.levels:
            lv.dirty = False
            lv.terrain_dirty = False
        print(f"Exported to {path}")

    def _has_unsaved_changes(self):
        return any(lv.dirty for lv in self.levels)

    def _confirm_exit(self):
        """Prompt the user if there are unsaved changes.
        Returns True if exit should proceed, False to cancel.
        """
        if not self._has_unsaved_changes():
            return True
        dirty = ", ".join(str(lv.level_num + 1) for lv in self.levels if lv.dirty)
        root = tk.Tk()
        root.withdraw()
        result = messagebox.askyesnocancel(
            "Unsaved changes",
            f"Level(s) {dirty} have unsaved changes.\n\n"
            f"Yes = save and exit\n"
            f"No = exit without saving\n"
            f"Cancel = stay in editor",
        )
        root.destroy(); self._drain_input_events()
        if result is None:
            return False
        if result:
            self._quick_save()
            # If save was cancelled (e.g. open-bottom prompt cancelled),
            # don't exit -- user is still in an unsaved state.
            if self._has_unsaved_changes():
                return False
        return True

    def _quick_save(self):
        """Ctrl+S: save over the current file without a dialog. Falls back
        to _export() if no file has been loaded/saved yet.
        """
        if not self._check_landscape_bottoms():
            return
        if not self._check_wiring():
            return
        if self.last_file_path:
            self._save_to_file(self.last_file_path)
        else:
            self._export()

    def _export(self):
        """Export via file dialog (OS will prompt on overwrite)."""
        if not self._check_landscape_bottoms():
            return
        if not self._check_wiring():
            return

        if self.last_file_path:
            default_path = Path(self.last_file_path)
        else:
            default_path = Path("tools/output/thrust_levels_export.asm").resolve()
        root = tk.Tk()
        root.withdraw()
        path = filedialog.asksaveasfilename(
            title="Export level data",
            initialdir=str(default_path.parent),
            initialfile=default_path.name,
            defaultextension=".asm",
            filetypes=[("BeebAsm assembly", "*.asm"), ("All files", "*.*")],
        )
        root.destroy(); self._drain_input_events()
        if not path:
            return
        self._save_to_file(path)

    def _import(self):
        """Import level data from assembly file via file dialog."""
        if self.last_file_path:
            default_path = Path(self.last_file_path)
        else:
            default_path = Path("tools/output/thrust_levels_export.asm").resolve()
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="Import level data",
            initialdir=str(default_path.parent),
            defaultextension=".asm",
            filetypes=[("BeebAsm assembly", "*.asm"), ("All files", "*.*")],
        )
        root.destroy(); self._drain_input_events()
        if not path:
            return
        self.levels = import_beebasm(path)
        self.last_file_path = str(Path(path).resolve())
        self._centre_on_level()
        self.selected_object = None
        self.dragging_wall = None
        self.dragging_bottom = False
        self.dragging_no_wrap = False
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
        self._render_bands()
        self._render_wall_highlights()
        self._render_toolbar()
        self._render_status()
        self._render_inspector_pane()

        pygame.display.flip()

    def _resolve_band_colours(self, world_y):
        """Walk the level's bands (sorted ascending by y) and return
        (landscape_colour, object_colour) resolved at world_y. Each band's
        non-None colour overrides the previous; deepest active band wins.
        Mirrors the engine's update_active_band scan."""
        lv = self.level
        lc = lv.landscape_colour
        oc = lv.object_colour
        for b in sorted(lv.bands, key=lambda b: b["y"]):
            if world_y < b["y"]:
                break
            if b.get("landscape_colour") is not None:
                lc = b["landscape_colour"]
            if b.get("object_colour") is not None:
                oc = b["object_colour"]
        return lc, oc

    def _render_terrain(self):
        """Draw the terrain (rock fills + wall edges)."""
        lv = self.level
        cam = self.camera
        screen = self.screen
        sw = screen.get_width() - INSPECTOR_W

        default_landscape_rgb = hex_to_rgb(BBC_COLOURS[lv.landscape_colour])
        default_rock_rgb = darken(default_landscape_rgb)
        band_mode = self.mode == "band" and bool(lv.bands)

        y_min, y_max = cam.visible_y_range()
        y_max = min(y_max, lv.num_rows)

        # Clip to viewport (exclude inspector strip)
        clip_rect = pygame.Rect(0, VIEWPORT_Y, sw, cam.viewport_h)
        screen.set_clip(clip_rect)

        for row in range(y_min, y_max):
            _, sy = cam.world_to_screen(0, row)
            _, sy_next = cam.world_to_screen(0, row + 1)
            row_h = max(1, int(sy_next - sy))
            # Mimic BBC half-resolution rendering: each world row maps to
            # 2 BBC scanlines but only the first is drawn — the second
            # stays as background. Reflect that in the editor by filling
            # the top half of the row's editor-pixel band only.
            half_h = max(1, row_h // 2)

            if sy + row_h < VIEWPORT_Y or sy > VIEWPORT_Y + cam.viewport_h:
                continue

            # Rows beyond either wall array are closed (solid rock)
            if row >= len(lv.left_wall) or row >= len(lv.right_wall):
                continue
            left_x = lv.left_wall[row]
            right_x = lv.right_wall[row]

            if right_x - left_x <= 1:
                continue

            if band_mode:
                lc_row, _ = self._resolve_band_colours(row)
                landscape_rgb = hex_to_rgb(BBC_COLOURS[lc_row])
                rock_rgb = darken(landscape_rgb)
            else:
                landscape_rgb = default_landscape_rgb
                rock_rgb = default_rock_rgb

            # Left rock: world 0 to left_x
            lsx, _ = cam.world_to_screen(0, row)
            lex, _ = cam.world_to_screen(left_x, row)
            x1, x2 = int(lsx), int(lex)
            if x2 > x1 and x2 > 0 and x1 < sw:
                x1 = max(0, x1)
                pygame.draw.rect(screen, rock_rgb,
                                 (x1, int(sy), x2 - x1, half_h))

            # Right rock: right_x to world 256
            rsx, _ = cam.world_to_screen(right_x, row)
            rex, _ = cam.world_to_screen(256, row)
            x1, x2 = int(rsx), int(rex)
            if x2 > x1 and x2 > 0 and x1 < sw:
                x1 = max(0, x1)
                pygame.draw.rect(screen, rock_rgb,
                                 (x1, int(sy), x2 - x1, half_h))

            # Wall edge highlights (thin lines)
            pygame.draw.rect(screen, landscape_rgb,
                             (int(lex) - 1, int(sy), 2, half_h))
            pygame.draw.rect(screen, landscape_rgb,
                             (int(rsx) - 1, int(sy), 2, half_h))

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

            # Rock below cave — per-row loop so half-res striping is
            # consistent with the cave walls.
            below_start = max(y_min, last_cave + 1)
            below_end = min(y_max, lv.num_rows)
            for row in range(below_start, below_end):
                _, sy = cam.world_to_screen(0, row)
                _, sy_next = cam.world_to_screen(0, row + 1)
                row_h = max(1, int(sy_next - sy))
                if sy + row_h < VIEWPORT_Y or sy > VIEWPORT_Y + cam.viewport_h:
                    continue
                if band_mode:
                    lc_row, _ = self._resolve_band_colours(row)
                    rr = darken(hex_to_rgb(BBC_COLOURS[lc_row]))
                else:
                    rr = default_rock_rgb
                pygame.draw.rect(screen, rr,
                                 (rock_sx, int(sy), rock_w, max(1, row_h // 2)))

            # Sky rows within the cave region that are "all rock"
            for row in range(max(y_min, first_cave), min(y_max, last_cave + 1)):
                if row >= len(lv.left_wall) or row >= len(lv.right_wall):
                    continue
                if lv.right_wall[row] - lv.left_wall[row] <= 1:
                    _, sy = cam.world_to_screen(0, row)
                    _, sy_next = cam.world_to_screen(0, row + 1)
                    row_h = max(1, int(sy_next - sy))
                    if band_mode:
                        lc_row, _ = self._resolve_band_colours(row)
                        rr = darken(hex_to_rgb(BBC_COLOURS[lc_row]))
                    else:
                        rr = default_rock_rgb
                    pygame.draw.rect(screen, rr,
                                     (rock_sx, int(sy), rock_w, max(1, row_h // 2)))

        # In wall mode, draw wall edge markers for converged rows (gap <= 1)
        # on top of the rock fill so they're visible and editable
        if self.mode == "wall":
            edge_col = (landscape_rgb[0] // 2, landscape_rgb[1] // 2,
                        landscape_rgb[2] // 2)
            for row in range(y_min, y_max):
                if row >= len(lv.left_wall) or row >= len(lv.right_wall):
                    continue
                if lv.right_wall[row] - lv.left_wall[row] > 1:
                    continue
                _, sy = cam.world_to_screen(0, row)
                _, sy_next = cam.world_to_screen(0, row + 1)
                row_h = max(1, int(sy_next - sy))
                if sy + row_h < VIEWPORT_Y or sy > VIEWPORT_Y + cam.viewport_h:
                    continue
                lex, _ = cam.world_to_screen(lv.left_wall[row], row)
                pygame.draw.rect(screen, edge_col,
                                 (int(lex) - 1, int(sy), 2, row_h))
                if lv.right_wall[row] != lv.left_wall[row]:
                    rex, _ = cam.world_to_screen(lv.right_wall[row], row)
                    pygame.draw.rect(screen, edge_col,
                                     (int(rex) - 1, int(sy), 2, row_h))

        screen.set_clip(None)

    def _render_grid(self):
        """Draw a grid overlay."""
        cam = self.camera
        screen = self.screen
        sw = screen.get_width() - INSPECTOR_W

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
        band_mode = self.mode == "band" and bool(lv.bands)

        clip_rect = pygame.Rect(0, VIEWPORT_Y, screen.get_width() - INSPECTOR_W, cam.viewport_h)
        screen.set_clip(clip_rect)

        for i, obj in enumerate(lv.objects):
            if obj["type"] == OBJECT_GRAVITY_WELL:
                self._render_gravity_well(obj, i)
                continue
            if obj["type"] == OBJECT_TELEPORTER:
                self._render_teleporter(obj, i)
                continue
            if band_mode:
                lc_obj, oc_obj = self._resolve_band_colours(obj["y"])
                sprite = self.sprite_cache.get(obj["type"], lv,
                                               landscape_colour=lc_obj,
                                               object_colour=oc_obj)
            else:
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

            # Aim / beam-direction indicator for firing types, only in object mode
            if self.mode == "object":
                if obj["type"] in OBJECT_LASER_TYPES:
                    self._render_laser_beam(obj, sx, sy, draw_w, draw_h)
                elif obj["type"] in OBJECT_FIRING_TYPES:
                    self._render_gun_aim(obj, sx, sy, draw_w, draw_h)
                elif obj["type"] in BOBBING_MINE_TYPES:
                    self._render_bobbing_mine_amp_bar(obj, sx, sy, draw_w, draw_h)
                elif obj["type"] in (0x07, 0x08) and i == self.selected_object:
                    self._render_switch_wiring(obj, i, sx, sy, draw_w, draw_h)

        screen.set_clip(None)

    def _render_gun_aim(self, obj, sx, sy, draw_w, draw_h):
        """Draw an arrow along the centre of the gun's firing cone, plus a
        translucent wedge showing the spread.

        thrust.6502 firing logic (see try_gun_fire): shot_angle = base + rnd(spread_mask)
        + rnd(3), so bullets fly in a one-sided cone from `base` to
        `base + spread_mask + 3`. The arrow therefore points along the cone
        midpoint, not along `base`, which is how the gun actually "aims".

        Game angle convention (see angle_to_x/y lookup tables in app_init.asm):
        angle 0 = up, CW, 32 steps. dx = +1.25*sin(a*2pi/32), dy = -2.5*cos(...).
        """
        aim = obj.get("gun_aim", 0x00)
        base = aim & 0x1C
        spread_idx = aim & 0x03
        spread_mask = GUN_SPREAD_MASKS[spread_idx]
        # Total additive spread on top of base.
        max_spread = spread_mask + 3
        # Centre of the firing cone (where the arrow points).
        centre = base + max_spread / 2.0
        half = max_spread / 2.0

        cx = sx + draw_w / 2
        cy = sy + draw_h / 2
        arrow_len = GUN_AIM_ARROW_LEN * self.camera.zoom / 4

        def angle_to_xy(angle, length):
            rad = (angle / 32.0) * 2 * math.pi
            return math.sin(rad) * length, -math.cos(rad) * length

        # Spread wedge as a pie slice (apex + arc sampled every 1 angle unit).
        # A straight-edged triangle looks wrong for wide spreads ($0F mask is
        # ~202 degrees total) because the far chord cuts across the "circle".
        pts = [(cx, cy)]
        steps = max(2, int(max_spread))
        for i in range(steps + 1):
            a = (centre - half) + max_spread * i / steps
            dx, dy = angle_to_xy(a, arrow_len)
            pts.append((cx + dx, cy + dy))
        cone = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(cone, COL_GUN_SPREAD, pts)
        self.screen.blit(cone, (0, 0))

        # Centre-angle arrow.
        dx_c, dy_c = angle_to_xy(centre, arrow_len)
        tip = (cx + dx_c, cy + dy_c)
        pygame.draw.line(self.screen, COL_GUN_AIM, (cx, cy), tip, 2)
        perp_dx, perp_dy = angle_to_xy(centre + 8, 3)  # +90 deg CW from centre
        pygame.draw.polygon(self.screen, COL_GUN_AIM, [
            tip,
            (tip[0] - dx_c * 0.3 + perp_dx, tip[1] - dy_c * 0.3 + perp_dy),
            (tip[0] - dx_c * 0.3 - perp_dx, tip[1] - dy_c * 0.3 - perp_dy),
        ])

    def _render_laser_beam(self, obj, sx, sy, draw_w, draw_h):
        """Draw a static line from the laser turret barrel along its firing
        direction. Length and direction mirror laser_beam_dx/dy_table and the
        gun_bullet_x/y_offset reuse in thrust.6502 — the rendered beam should
        match where the in-game beam will actually plot.

        Note on aspect: the editor compresses horizontals (ASPECT = 2) so 1
        char draws as 2 row-heights, but on the BBC display 1 char displays
        as ~4 row-heights (4:3 CRT, 320×256, 4 BBC pixels per char). Scaling
        beam X by row_h_px keeps the in-game angle (60 BBC px × 30 rows ≈
        2:1 → ~27°), but the editor's halved char width means dropping a
        further factor of 2 keeps the beam's on-screen length proportional
        to the sprite the same way it is in-game (beam ≈ 3× sprite width).
        """
        barrel_sx, barrel_sy, end_sx, end_sy = \
            self._laser_beam_screen_coords(obj, sx, sy, draw_w, draw_h)
        pygame.draw.line(self.screen, COL_LASER_BEAM,
                         (int(barrel_sx), int(barrel_sy)),
                         (int(end_sx), int(end_sy)), 2)
        # Endpoint drag handle: filled circle at the beam tip when this laser
        # is the selected object. Hit-tested in _hit_test_laser_endpoint.
        if (self.selected_object is not None
                and self.level.objects[self.selected_object] is obj):
            cx, cy = int(end_sx), int(end_sy)
            highlight = (self.dragging_laser_endpoint
                         or self.hovered_laser_endpoint)
            r = LASER_ENDPOINT_HANDLE_RADIUS
            blob = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(blob, (*COL_LASER_BEAM, 130), (r + 1, r + 1), r)
            self.screen.blit(blob, (cx - r - 1, cy - r - 1))
            ring_col = (255, 255, 255) if highlight else (180, 180, 180)
            pygame.draw.circle(self.screen, ring_col, (cx, cy), r + 1, 1)

    def _render_gravity_well(self, obj, i):
        """Draw a gravity well placeholder: centre dot + diamond outline at
        the Manhattan-radius boundary, plus a draggable handle on the
        right vertex when selected. Strength sign tints the diamond
        (blue = pull, red-ish = push) so designers can see direction."""
        cx, cy, rx_screen, ry_screen = self._well_screen_geometry(obj)
        cxi, cyi = int(cx), int(cy)

        s = obj.get("well_strength", 0)
        ring_col = (255, 140, 140, 110) if s < 0 else COL_GRAVITY_WELL_RING
        if obj.get("well_radius", 0) > 0 and rx_screen > 0 and ry_screen > 0:
            pts = [(cxi + rx_screen, cyi),
                   (cxi, cyi + ry_screen),
                   (cxi - rx_screen, cyi),
                   (cxi, cyi - ry_screen)]
            ring_surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            pygame.draw.polygon(ring_surf, ring_col, pts, 1)
            self.screen.blit(ring_surf, (0, 0))

        pygame.draw.circle(self.screen, COL_GRAVITY_WELL,
                           (cxi, cyi), GRAVITY_WELL_CENTRE_RADIUS)
        if i == self.selected_object:
            pygame.draw.circle(self.screen, COL_SELECT, (cxi, cyi),
                               GRAVITY_WELL_CENTRE_RADIUS + 2, 2)
        elif i == self.hovered_object and self.mode == "object":
            pygame.draw.circle(self.screen, (200, 200, 200), (cxi, cyi),
                               GRAVITY_WELL_CENTRE_RADIUS + 1, 1)

        if i == self.selected_object and obj.get("well_radius", 0) > 0:
            hx, hy = cxi + rx_screen, cyi
            highlight = (self.dragging_well_radius or self.hovered_well_radius)
            pygame.draw.circle(self.screen, COL_GRAVITY_WELL,
                               (hx, hy), GRAVITY_WELL_HANDLE_RADIUS)
            ring_col_handle = (255, 255, 255) if highlight else (180, 180, 180)
            pygame.draw.circle(self.screen, ring_col_handle, (hx, hy),
                               GRAVITY_WELL_HANDLE_RADIUS + 1, 1)

    def _render_teleporter(self, obj, i):
        """Draw a teleporter pad placeholder (ring + centre dot) and, when
        selected, a thin wiring line to the destination checkpoint's spawn
        position so the designer can see where the warp lands."""
        cam = self.camera
        screen = self.screen
        cx, cy = cam.world_to_screen(obj["x"], obj["y"])
        cxi, cyi = int(cx), int(cy)

        # Placeholder marker (will overlay any future sprite — cheap and
        # informative either way).
        pygame.draw.circle(screen, COL_TELEPORTER, (cxi, cyi), 7, 2)
        pygame.draw.circle(screen, COL_TELEPORTER, (cxi, cyi), 2)

        if i == self.selected_object:
            pygame.draw.circle(screen, COL_SELECT, (cxi, cyi), 9, 2)
        elif i == self.hovered_object and self.mode == "object":
            pygame.draw.circle(screen, (200, 200, 200), (cxi, cyi), 8, 1)

        # Wiring line from selected pad to its destination checkpoint.
        if i == self.selected_object:
            cps = self.level.checkpoints
            dest = obj.get("teleport_dest", 0)
            if cps and 0 <= dest < len(cps):
                cp = cps[dest]
                tx, ty = cam.world_to_screen(cp["spawn_x"], cp["spawn_y"])
                wire = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
                pygame.draw.line(wire, COL_TELEPORTER_WIRE,
                                 (cxi, cyi), (int(tx), int(ty)), 2)
                # Arrowhead at destination.
                ang = math.atan2(ty - cy, tx - cx)
                ah = 8
                for da in (math.pi - 0.4, math.pi + 0.4):
                    ax = tx + math.cos(ang + da) * ah
                    ay = ty + math.sin(ang + da) * ah
                    pygame.draw.line(wire, COL_TELEPORTER_WIRE,
                                     (int(tx), int(ty)), (int(ax), int(ay)), 2)
                screen.blit(wire, (0, 0))
                # Highlight target spawn.
                pygame.draw.circle(screen, COL_TELEPORTER,
                                   (int(tx), int(ty)), 5, 1)

    def _render_switch_wiring(self, obj, i, sx, sy, draw_w, draw_h):
        """When a wired switch is selected, draw one line + arrow + action
        label per wiring entry, fanning out to each target.
        """
        entries = self.level.wiring.get(i)
        if not entries:
            return

        cam = self.camera
        screen = self.screen
        cx = sx + draw_w / 2
        cy = sy + draw_h / 2
        cxi, cyi = int(cx), int(cy)

        wire = pygame.Surface(screen.get_size(), pygame.SRCALPHA)

        for entry in entries:
            action = entry.get("action", 0)
            if action == 0:
                continue
            target_idx = entry.get("target", 0xFF)
            if target_idx == 0xFF or target_idx >= len(self.level.objects):
                continue

            target = self.level.objects[target_idx]
            tx, ty = cam.world_to_screen(target["x"], target["y"])
            sprite = self.sprite_cache.get(target["type"], self.level)
            if sprite is not None:
                tx += sprite.get_width() / 8
                ty += sprite.get_height() / 4
            txi, tyi = int(tx), int(ty)

            pygame.draw.line(wire, COL_SWITCH_WIRE, (cxi, cyi), (txi, tyi), 2)
            ang = math.atan2(ty - cy, tx - cx)
            ah = 8
            for da in (math.pi - 0.4, math.pi + 0.4):
                ax = tx + math.cos(ang + da) * ah
                ay = ty + math.sin(ang + da) * ah
                pygame.draw.line(wire, COL_SWITCH_WIRE,
                                 (txi, tyi), (int(ax), int(ay)), 2)

            pygame.draw.rect(screen, (255, 200, 100),
                             (txi - 6, tyi - 6, 13, 13), 1)

            action_name = next((n for n, v in SWITCH_ACTION_VALUES if v == action),
                               f"act${action:02X}")
            label = self.font_small.render(action_name, True, (255, 220, 160))
            mx = int((cx + tx) / 2) - label.get_width() // 2
            my = int((cy + ty) / 2) - label.get_height() // 2
            pad = 2
            plate = pygame.Surface((label.get_width() + pad * 2,
                                    label.get_height() + pad * 2), pygame.SRCALPHA)
            plate.fill((0, 0, 0, 140))
            screen.blit(plate, (mx - pad, my - pad))
            screen.blit(label, (mx, my))

        screen.blit(wire, (0, 0))

    def _render_bobbing_mine_amp_bar(self, obj, sx, sy, draw_w, draw_h):
        """Overlay a bar showing the mine's bob-amplitude extent at the
        sprite centre. Vertical mines get a vertical bar; horizontal mines
        get a horizontal one. The sprite itself is drawn by the standard
        path; this is just the editor-only bob-range indicator."""
        amp = obj.get("mine_amp", 0)
        if amp == 0:
            return
        cam = self.camera
        cxi = int(sx + draw_w / 2)
        cyi = int(sy + draw_h / 2)
        bar_surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        if obj["type"] == OBJECT_BOBBING_MINE_HORIZONTAL:
            # World X displays at 2x scale (ASPECT) compared to world Y; use
            # the camera's x_scale so the bar matches the sprite's width.
            extent = abs(amp) * cam.x_scale
            if extent < 1:
                return
            left_x = cxi - int(extent)
            right_x = cxi + int(extent)
            pygame.draw.line(bar_surf, COL_BOBBING_MINE_RANGE,
                             (left_x, cyi), (right_x, cyi), 2)
            pygame.draw.line(bar_surf, COL_BOBBING_MINE_RANGE,
                             (left_x, cyi - 4), (left_x, cyi + 4), 1)
            pygame.draw.line(bar_surf, COL_BOBBING_MINE_RANGE,
                             (right_x, cyi - 4), (right_x, cyi + 4), 1)
        else:
            extent = abs(amp) * cam.zoom
            if extent < 1:
                return
            top_y = cyi - int(extent)
            bot_y = cyi + int(extent)
            pygame.draw.line(bar_surf, COL_BOBBING_MINE_RANGE,
                             (cxi, top_y), (cxi, bot_y), 2)
            pygame.draw.line(bar_surf, COL_BOBBING_MINE_RANGE,
                             (cxi - 4, top_y), (cxi + 4, top_y), 1)
            pygame.draw.line(bar_surf, COL_BOBBING_MINE_RANGE,
                             (cxi - 4, bot_y), (cxi + 4, bot_y), 1)
        self.screen.blit(bar_surf, (0, 0))

    def _laser_beam_screen_coords(self, obj, sx, sy, draw_w, draw_h):
        """Return (barrel_sx, barrel_sy, end_sx, end_sy) screen positions for
        the laser beam from this turret. Shared by _render_laser_beam (drawing)
        and _hit_test_laser_endpoint (drag handle hit test).

        Scaling: the game's draw_line uses 1 X-unit per BBC pixel (chars in
        this game's encoding are 4 BBC pixels wide; the asm's ASL ASL turns
        chars*4 into X-units = BBC pixels). 1 row is also 1 BBC pixel
        vertically. The angle therefore matches between editor and game when
        scale_x == scale_y. Using char_w_px / 4 on both axes maps each BBC
        pixel of beam travel to the same proportion of sprite-width that the
        game's beam covers (e.g. dx=60 X-units = 60 BBC px = 3 sprite-widths
        in both editor and game). Sprite vertical proportion differs from
        game (the source PNG is taller per row than the in-game 1-px row)
        but the *beam's* angle matches what you'd see in BeebEm.
        """
        obj_type = obj["type"]
        # Sprite cells are 5 chars wide × 8 rows tall for laser turrets.
        char_w_px = draw_w / 5.0
        row_h_px  = draw_h / 8.0
        barrel_sx = sx + LASER_BARREL_X_CHARS[obj_type] * char_w_px
        barrel_sy = sy + LASER_BARREL_Y_ROWS[obj_type]  * row_h_px
        scale = char_w_px / 4.0
        end_sx = barrel_sx + obj["laser_dx"] * scale
        end_sy = barrel_sy + obj["laser_dy"] * scale
        return barrel_sx, barrel_sy, end_sx, end_sy

    def _render_checkpoints(self):
        """Draw checkpoint markers as horizontal lines with spawn position dots."""
        lv = self.level
        cam = self.camera
        screen = self.screen
        sw = screen.get_width() - INSPECTOR_W

        clip_rect = pygame.Rect(0, VIEWPORT_Y, sw, cam.viewport_h)
        screen.set_clip(clip_rect)

        ship_surf = self.sprite_cache.get_ship()
        # Ship world dimensions (same convention as object sprites)
        ship_world_w = ship_surf.get_width() / 4   # 4 Mode 1 pixels per world X
        ship_world_h = ship_surf.get_height() / 2  # half-res vertical rendering
        ship_offset_x = _SHIP_PIXEL_OFFSET_X / 4   # plotting origin to first pixel

        for i, cp in enumerate(lv.checkpoints):
            # spawn_y is the midpoint Y stored in the reset table. The game's
            # plotted ship lands midpoint_deltay above that — at level start
            # ≈ _SPAWN_MIDPOINT_TO_SHIP_DY world Y units upward. Render the
            # sprite at that offset so the editor matches the in-game position.
            ship_top_y = cp["spawn_y"] - _SPAWN_MIDPOINT_TO_SHIP_DY
            sx_tl, sy_tl = cam.world_to_screen(
                cp["spawn_x"] + ship_offset_x, ship_top_y)
            sx_win, sy_win = cam.world_to_screen(cp["window_x"], cp["window_y"])

            # Scale ship sprite to match current zoom
            ex, ey = cam.world_to_screen(
                cp["spawn_x"] + ship_offset_x + ship_world_w,
                ship_top_y + ship_world_h)
            draw_w = max(1, int(ex - sx_tl))
            draw_h = max(1, int(ey - sy_tl))

            if sy_tl + draw_h < VIEWPORT_Y - 20 or sy_tl > VIEWPORT_Y + cam.viewport_h + 20:
                continue

            if self.mode == "checkpoint":
                # Dashed horizontal line at the raw spawn_y — this is the
                # threshold the game uses for zone matching, independent of
                # the rendered sprite's vertical offset.
                _, sy_thresh = cam.world_to_screen(0, cp["spawn_y"])
                line_col = (100, 200, 255)
                dash_len = 8
                for dx in range(0, sw, dash_len * 2):
                    pygame.draw.line(screen, line_col,
                                     (dx, int(sy_thresh)), (min(dx + dash_len, sw), int(sy_thresh)))
                label = f"CP{i} Y={cp['spawn_y']}"
                txt = self.font_small.render(label, True, line_col)
                screen.blit(txt, (4, int(sy_thresh) - 14))

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

    def _render_bands(self):
        """Draw Y-band threshold lines (cyan dashed) with gravity label.
        Only visible in band mode, similar to other mode-specific overlays."""
        if self.mode != "band":
            return
        lv = self.level
        if not lv.bands:
            return
        cam = self.camera
        screen = self.screen
        sw = screen.get_width() - INSPECTOR_W
        for i, band in enumerate(lv.bands):
            _, sy = cam.world_to_screen(0, band["y"])
            y = int(sy)
            if not (VIEWPORT_Y <= y <= VIEWPORT_Y + cam.viewport_h):
                continue
            active = (i == self.selected_band or i == self.hovered_band)
            col = (140, 240, 255) if active else (70, 170, 200)
            dash = 8
            for dx in range(0, sw, dash * 2):
                pygame.draw.line(screen, col, (dx, y),
                                 (min(dx + dash, sw), y), 2)
            g = band["gravity"]
            g_signed = g - 256 if g >= 128 else g
            label = f"Band Y={band['y']}  g=${g:02X} ({g_signed:+d})"
            txt = self.font_small.render(label, True, col)
            screen.blit(txt, (4, y - 14))

    def _render_wall_highlights(self):
        """Draw highlights on hovered/dragged wall edges and bottom handle."""
        if self.mode != "wall":
            return

        cam = self.camera
        screen = self.screen
        sw = screen.get_width() - INSPECTOR_W

        # Faint crosshair guidelines extending from the cursor to the viewport edges
        mx, my = pygame.mouse.get_pos()
        sh_full = screen.get_height()
        if 0 <= mx < sw and TOOLBAR_H <= my < sh_full - STATUS_H:
            guide_col = (90, 95, 110)
            prev_clip = screen.get_clip()
            screen.set_clip(pygame.Rect(0, TOOLBAR_H, sw, sh_full - STATUS_H - TOOLBAR_H))
            # Vertical guide
            for y in range(TOOLBAR_H, sh_full - STATUS_H, 4):
                screen.set_at((mx, y), guide_col)
            # Horizontal guide
            for x in range(0, sw, 4):
                screen.set_at((x, my), guide_col)
            screen.set_clip(prev_clip)

        # Bottom boundary handle — always visible in wall mode
        lv = self.level
        wx0, _ = cam.world_to_screen(0, lv.num_rows)
        wx256, _ = cam.world_to_screen(256, lv.num_rows)
        _, bottom_sy = cam.world_to_screen(0, lv.num_rows)
        x1 = max(0, int(wx0))
        x2 = min(sw, int(wx256))
        by = int(bottom_sy)
        if VIEWPORT_Y <= by <= VIEWPORT_Y + cam.viewport_h and x2 > x1:
            col = (150, 220, 255) if (self.hovered_bottom or self.dragging_bottom) \
                else COL_BOTTOM_HANDLE
            # Draw dashed line with small handle triangles
            dash = 8
            for dx in range(x1, x2, dash * 2):
                ex = min(dx + dash, x2)
                pygame.draw.line(screen, col, (dx, by), (ex, by), 2)
            # Draw grab triangles at the edges
            for tx in [x1 + 10, x2 - 10]:
                pygame.draw.polygon(screen, col,
                                    [(tx - 5, by - 4), (tx + 5, by - 4), (tx, by + 4)])

        # No-wrap Y threshold line
        if lv.no_wrap_y < 0xFFFF:
            wx0_nw, _ = cam.world_to_screen(0, lv.no_wrap_y)
            wx256_nw, _ = cam.world_to_screen(256, lv.no_wrap_y)
            _, nw_sy = cam.world_to_screen(0, lv.no_wrap_y)
            nx1 = max(0, int(wx0_nw))
            nx2 = min(sw, int(wx256_nw))
            ny = int(nw_sy)
            if VIEWPORT_Y <= ny <= VIEWPORT_Y + cam.viewport_h and nx2 > nx1:
                col = (255, 200, 80) if (self.hovered_no_wrap or self.dragging_no_wrap) \
                    else (200, 150, 50)
                dash = 8
                for dx in range(nx1, nx2, dash * 2):
                    ex = min(dx + dash, nx2)
                    pygame.draw.line(screen, col, (dx, ny), (ex, ny), 2)
                # Label
                label = f"No-wrap Y={lv.no_wrap_y}"
                txt = self.font_small.render(label, True, col)
                screen.blit(txt, (nx1 + 4, ny - 14))

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

        # Highlight just the selected row; colour-code left vs right wall
        col = (255, 120, 120) if side == "left" else (120, 200, 255)
        sx, sy = cam.world_to_screen(wall[row], row)
        _, sy_next = cam.world_to_screen(0, row + 1)
        h = max(1, int(sy_next - sy))
        pygame.draw.rect(screen, col, (int(sx) - 3, int(sy), 6, h))

    def _render_toolbar(self):
        """Draw the top toolbar."""
        screen = self.screen
        sw = screen.get_width()
        vw = sw - INSPECTOR_W  # usable viewport width (excludes inspector strip)
        pygame.draw.rect(screen, COL_TOOLBAR, (0, 0, vw, TOOLBAR_H))
        pygame.draw.line(screen, (60, 60, 60), (0, TOOLBAR_H - 1), (vw, TOOLBAR_H - 1))

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
        for mode_name, offset in [("Wall", 0), ("Object", 70), ("Chkpt", 140), ("Band", 210)]:
            col = COL_TOOLBAR_ACTIVE if self.mode == mode_name.lower() \
                or (mode_name == "Chkpt" and self.mode == "checkpoint") else COL_TOOLBAR
            rect = pygame.Rect(mode_x + offset, 5, 60, 30)
            pygame.draw.rect(screen, col, rect, border_radius=4)
            pygame.draw.rect(screen, (80, 80, 80), rect, 1, border_radius=4)
            txt = self.font.render(mode_name, True, COL_TOOLBAR_TEXT)
            screen.blit(txt, (mode_x + offset + 8, 12))

        # Current filename (centred between mode buttons and Import/Export)
        fname = Path(self.last_file_path).name if self.last_file_path else "(unsaved)"
        if self._has_unsaved_changes():
            fname += "*"
        fname_txt = self.font.render(fname, True, (220, 220, 160))
        fname_x = (vw - 200 + 720) // 2 - fname_txt.get_width() // 2
        screen.blit(fname_txt, (fname_x, 12))

        # Import button
        import_x = vw - 200
        rect = pygame.Rect(import_x, 5, 90, 30)
        pygame.draw.rect(screen, (40, 40, 60), rect, border_radius=4)
        pygame.draw.rect(screen, (80, 80, 80), rect, 1, border_radius=4)
        txt = self.font.render("Import", True, (150, 150, 255))
        screen.blit(txt, (import_x + 16, 12))

        # Export button
        export_x = vw - 100
        rect = pygame.Rect(export_x, 5, 90, 30)
        pygame.draw.rect(screen, (40, 60, 40), rect, border_radius=4)
        pygame.draw.rect(screen, (80, 80, 80), rect, 1, border_radius=4)
        txt = self.font.render("Export", True, (150, 255, 150))
        screen.blit(txt, (export_x + 18, 12))

    def _render_status(self):
        """Draw the slimmed status bar: mode, level, file, coords, transient hint."""
        screen = self.screen
        vw = screen.get_width() - INSPECTOR_W
        sh = screen.get_height()
        pygame.draw.rect(screen, COL_STATUS_BG, (0, sh - STATUS_H, vw, STATUS_H))

        mx, my = pygame.mouse.get_pos()
        wx, wy = self.camera.screen_to_world(mx, my)

        lv = self.level
        mode_label = self.mode.title()
        if self.mode == "wall":
            mode_label += f" ({self.wall_tool.title()})"

        fname = Path(self.last_file_path).name if self.last_file_path else "(unsaved)"
        if self._has_unsaved_changes():
            fname += "*"

        row = int(wy)
        l_val = lv.left_wall[row] if 0 <= row < len(lv.left_wall) else None
        r_val = lv.right_wall[row] if 0 <= row < len(lv.right_wall) else None
        walls_str = f"L={'-' if l_val is None else l_val} R={'-' if r_val is None else r_val}"

        parts = [
            f"[{mode_label}]",
            f"[Level {lv.level_num + 1}]",
            f"[{fname}]",
            f"X={int(wx)} Y={int(wy)}",
            walls_str,
        ]

        # Transient hint (rightmost)
        hint = ""
        if self.input_focus:
            hint = "typing — Enter to commit, Esc to cancel"
        elif self.ref_pick_field is not None:
            kind = "object"  # default; refine from the armed field's target_kind if available
            schema, _, _ = schema_for_selection(self)
            for f in schema:
                if f.id == self.ref_pick_field and f.target_kind:
                    kind = f.target_kind
                    break
            hint = f"click a {kind} on canvas to pick"
        elif self.palette_armed_type is not None:
            name = OBJECT_TYPE_NAMES.get(self.palette_armed_type,
                                         f"${self.palette_armed_type:02X}")
            hint = f"Placing: {name} — click to drop (Shift = keep armed), right-click/Esc to cancel"
        elif self.line_start:
            side, r, x = self.line_start
            hint = f"Line: {side} from row {r} x={x} — click to set end"
        elif self.dragging_pinch:
            hint = "Pinch drag — both walls set to L=R; release to stop"
        elif self.dragging_bottom or self.hovered_bottom:
            hint = "Drag to resize landscape"
        elif self.dragging_no_wrap or self.hovered_no_wrap:
            hint = "Drag no-wrap line (right-click to remove)"
        elif self.mode == "wall" and self.hovered_wall:
            hint = "Drag to edit wall  •  Shift+drag = pinch (L=R)"
        elif self.mode == "wall" and lv.no_wrap_y >= 0xFFFF:
            hint = "Right-click to place no-wrap line  •  Shift+click wall = pinch (L=R)"
        elif self.mode == "wall":
            hint = "Shift+click a wall = pinch row (L=R); drag to extend"
        elif self.mode == "checkpoint":
            hint = "Right-click to add a checkpoint at the cursor"
        elif self.mode == "band":
            hint = "Right-click to add a Y-band at the cursor"

        status_left = "  ".join(parts)
        txt_left = self.font_small.render(status_left, True, COL_STATUS_TEXT)
        screen.blit(txt_left, (10, sh - STATUS_H + 5))

        if hint:
            txt_hint = self.font_small.render(hint, True, (200, 200, 100))
            screen.blit(txt_hint, (vw - txt_hint.get_width() - 10, sh - STATUS_H + 5))

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

    # -------------------------------------------------------------------
    # Inspector pane
    # -------------------------------------------------------------------

    def _inspector_split_y(self):
        sh = self.screen.get_height()
        return int(TOOLBAR_H + (sh - TOOLBAR_H - STATUS_H) * self.inspector_split)

    def _render_inspector_pane(self):
        screen = self.screen
        sw = screen.get_width()
        sh = screen.get_height()
        insp_x = sw - INSPECTOR_W
        split_y = self._inspector_split_y()

        # Background + border
        pygame.draw.rect(screen, COL_INSP_BG, (insp_x, 0, INSPECTOR_W, sh))
        pygame.draw.line(screen, COL_INSP_BORDER, (insp_x, 0), (insp_x, sh))

        schema, target, level = schema_for_selection(self)

        field_top = self._inspector_field_top()
        insp_h = split_y - field_top

        # Clip to fields section
        clip = pygame.Rect(insp_x, field_top, INSPECTOR_W, insp_h)
        screen.set_clip(clip)

        y = field_top - self.inspector_scroll
        max_scroll = max(0, len(schema) * FIELD_H - insp_h)
        self.inspector_scroll = min(self.inspector_scroll, max_scroll)

        for field in schema:
            if y + FIELD_H > field_top and y < split_y:
                rect = pygame.Rect(insp_x + 2, y, INSPECTOR_W - 4, FIELD_H)
                self._render_inspector_field(rect, field, target, level)
            y += FIELD_H

        screen.set_clip(None)

        # Divider
        pygame.draw.line(screen, COL_INSP_BORDER, (insp_x, split_y), (sw, split_y))

        # Palette / mode tools section
        self._render_palette_section(insp_x, split_y + 1, sh - STATUS_H)

    def _inspector_field_top(self):
        return TOOLBAR_H + 1

    def _render_inspector_field(self, rect, field, target, level):
        screen = self.screen
        is_active = (field.id == self.inspector_active_field)
        is_text = (field.id == self.text_entry_field)

        # Section header — full-width title strip, no value widget.
        if field.kind == "header":
            pygame.draw.rect(screen, COL_INSP_HEADER, rect)
            pygame.draw.line(screen, COL_INSP_BORDER,
                             (rect.x, rect.bottom - 1), (rect.right, rect.bottom - 1))
            t = self.font.render(field.label, True, (210, 215, 235))
            screen.blit(t, (rect.x + (rect.width - t.get_width()) // 2,
                            rect.y + (rect.height - t.get_height()) // 2))
            return

        # Button — full-width clickable rect, no value widget. Setter is
        # invoked as a side-effect on click (see _handle_field_click).
        if field.kind == "button":
            inset = pygame.Rect(rect.x + 6, rect.y + 2, rect.width - 12, rect.height - 4)
            pygame.draw.rect(screen, COL_BTN, inset, border_radius=3)
            pygame.draw.rect(screen, COL_INSP_BORDER, inset, 1, border_radius=3)
            t = self.font_small.render(field.label, True, COL_FIELD_VALUE)
            screen.blit(t, (inset.x + (inset.width - t.get_width()) // 2,
                            inset.y + (inset.height - t.get_height()) // 2))
            return

        bg = COL_FIELD_ACTIVE if is_active else COL_FIELD_BG
        pygame.draw.rect(screen, bg, rect)
        # Subtle bottom border
        pygame.draw.line(screen, COL_INSP_BORDER,
                         (rect.x, rect.bottom - 1), (rect.right, rect.bottom - 1))

        # Label
        lbl = self.font_small.render(field.label, True, COL_FIELD_LABEL)
        screen.blit(lbl, (rect.x + 4, rect.y + (FIELD_H - lbl.get_height()) // 2))

        # Widget
        wx = rect.x + FIELD_LABEL_W
        ww = rect.right - wx - 4
        widget_rect = pygame.Rect(wx, rect.y + 2, ww, FIELD_H - 4)

        try:
            val = field.get(target)
        except Exception:
            val = 0

        if field.kind == "colour":
            self._render_colour_widget(widget_rect, field, val)
        elif field.kind in ("enum", "ref"):
            self._render_cycle_widget(widget_rect, field, val, target, level)
        elif field.kind == "readonly":
            txt = self.font_small.render(str(val), True, COL_FIELD_VALUE)
            screen.blit(txt, (widget_rect.x + 2, widget_rect.y + 3))
        else:
            self._render_spinner_widget(widget_rect, field, val, is_text)

    def _render_spinner_widget(self, rect, field, val, is_text):
        screen = self.screen
        btn_w = 16
        dec_rect = pygame.Rect(rect.x, rect.y, btn_w, rect.height)
        inc_rect = pygame.Rect(rect.right - btn_w, rect.y, btn_w, rect.height)
        val_rect = pygame.Rect(dec_rect.right + 1, rect.y,
                               inc_rect.x - dec_rect.right - 2, rect.height)

        hover_dec = (self.hovered_btn == (field.id, "dec"))
        hover_inc = (self.hovered_btn == (field.id, "inc"))
        hover_val = (self.hovered_btn == (field.id, "val"))

        pygame.draw.rect(screen, COL_BTN_HOVER if hover_dec else COL_BTN,
                         dec_rect, border_radius=2)
        pygame.draw.rect(screen, COL_BTN_HOVER if hover_inc else COL_BTN,
                         inc_rect, border_radius=2)
        pygame.draw.rect(screen, (40, 44, 58) if hover_val else (32, 35, 48),
                         val_rect, border_radius=2)

        m = self.font_small.render("-", True, COL_FIELD_VALUE)
        screen.blit(m, (dec_rect.x + (btn_w - m.get_width()) // 2,
                        dec_rect.y + (dec_rect.height - m.get_height()) // 2))
        p = self.font_small.render("+", True, COL_FIELD_VALUE)
        screen.blit(p, (inc_rect.x + (btn_w - p.get_width()) // 2,
                        inc_rect.y + (inc_rect.height - p.get_height()) // 2))

        if is_text:
            text = self.text_entry_buf + "|"
            col = COL_FIELD_TEXT
        else:
            text = field.format_value(val)
            col = COL_FIELD_VALUE

        screen.set_clip(val_rect)
        txt = self.font_small.render(text, True, col)
        screen.blit(txt, (val_rect.x + 3, val_rect.y + (val_rect.height - txt.get_height()) // 2))
        screen.set_clip(None)

    def _render_colour_widget(self, rect, field, val):
        screen = self.screen
        cell_count = 9 if field.allow_none else 8
        cell_w = max(4, rect.width // cell_count)
        for ci in range(cell_count):
            cx = rect.x + ci * cell_w
            cr = pygame.Rect(cx, rect.y, max(1, cell_w - 1), rect.height)
            if field.allow_none and ci == 8:
                pygame.draw.rect(screen, (35, 35, 48), cr, border_radius=2)
                d = self.font_small.render("—", True, (110, 110, 140))
                screen.blit(d, (cr.x + (cr.width - d.get_width()) // 2,
                                cr.y + (cr.height - d.get_height()) // 2))
                if val is None:
                    pygame.draw.rect(screen, (220, 220, 220), cr, 2, border_radius=2)
            else:
                col = hex_to_rgb(BBC_COLOURS[ci])
                pygame.draw.rect(screen, col, cr, border_radius=2)
                if ci == 0:
                    pygame.draw.rect(screen, (60, 60, 72), cr, 1, border_radius=2)
                if val == ci:
                    pygame.draw.rect(screen, (255, 255, 255), cr, 2, border_radius=2)

    def _render_cycle_widget(self, rect, field, val, target, level):
        screen = self.screen
        if field.kind == "ref":
            btn_w = 38
            pick_rect = pygame.Rect(rect.right - btn_w, rect.y, btn_w, rect.height)
            val_rect = pygame.Rect(rect.x, rect.y, rect.width - btn_w - 2, rect.height)
            if field.target_kind == "checkpoint" and level.checkpoints:
                n = len(level.checkpoints)
                dest = val if isinstance(val, int) else 0
                dest = dest % n if n else 0
                cp = level.checkpoints[dest]
                val_text = f"CP{dest}: {cp['spawn_x']},{cp['spawn_y']}"
            elif field.target_kind == "object":
                if isinstance(val, int) and val == 0xFF:
                    val_text = "(none)"
                elif isinstance(val, int) and 0 <= val < len(level.objects):
                    obj = level.objects[val]
                    name = OBJECT_TYPE_NAMES.get(obj["type"], f"${obj['type']:02X}")
                    val_text = f"#{val}: {name}"
                else:
                    val_text = f"#{val}"
            else:
                val_text = str(val)
            screen.set_clip(val_rect)
            txt = self.font_small.render(val_text, True, COL_FIELD_VALUE)
            screen.blit(txt, (val_rect.x + 2, val_rect.y + (val_rect.height - txt.get_height()) // 2))
            screen.set_clip(None)
            armed = (self.ref_pick_field == field.id)
            btn_col = COL_PALETTE_ARMED if armed else COL_BTN
            pygame.draw.rect(screen, btn_col, pick_rect, border_radius=2)
            p = self.font_small.render("Pick", True, COL_FIELD_VALUE)
            screen.blit(p, (pick_rect.x + (pick_rect.width - p.get_width()) // 2,
                            pick_rect.y + (pick_rect.height - p.get_height()) // 2))
        else:
            btn_w = 16
            dec = pygame.Rect(rect.x, rect.y, btn_w, rect.height)
            inc = pygame.Rect(rect.right - btn_w, rect.y, btn_w, rect.height)
            mid = pygame.Rect(dec.right + 1, rect.y, inc.x - dec.right - 2, rect.height)
            pygame.draw.rect(screen, COL_BTN, dec, border_radius=2)
            pygame.draw.rect(screen, COL_BTN, inc, border_radius=2)
            pygame.draw.rect(screen, COL_FIELD_BG, mid, border_radius=2)
            l = self.font_small.render("◄", True, COL_FIELD_VALUE)
            r = self.font_small.render("►", True, COL_FIELD_VALUE)
            screen.blit(l, (dec.x + (dec.width - l.get_width()) // 2,
                            dec.y + (dec.height - l.get_height()) // 2))
            screen.blit(r, (inc.x + (inc.width - r.get_width()) // 2,
                            inc.y + (inc.height - r.get_height()) // 2))
            val_text = field.format_value(val)
            screen.set_clip(mid)
            t = self.font_small.render(val_text, True, COL_FIELD_VALUE)
            screen.blit(t, (mid.x + (mid.width - t.get_width()) // 2,
                            mid.y + (mid.height - t.get_height()) // 2))
            screen.set_clip(None)

    # -------------------------------------------------------------------
    # Palette section
    # -------------------------------------------------------------------

    def _render_palette_section(self, insp_x, y_start, y_end):
        screen = self.screen
        pane_w = INSPECTOR_W
        pane_h = y_end - y_start

        pygame.draw.rect(screen, COL_PALETTE_BG,
                         (insp_x, y_start, pane_w, pane_h))

        if self.mode == "object":
            self._render_sprite_palette(insp_x, y_start, y_end)
        elif self.mode == "band":
            self._render_palette_add_tile(insp_x, y_start, "Add band  (right-click)", "band")
        elif self.mode == "checkpoint":
            self._render_palette_add_tile(insp_x, y_start, "Add checkpoint  (right-click)", "checkpoint")
        else:
            # Wall tools
            self._render_wall_tool_palette(insp_x, y_start, y_end)

    def _render_palette_add_tile(self, insp_x, y_start, label, kind):
        screen = self.screen
        tile_rect = pygame.Rect(insp_x + PALETTE_PAD, y_start + PALETTE_PAD,
                                INSPECTOR_W - PALETTE_PAD * 2, 36)
        pygame.draw.rect(screen, COL_BTN, tile_rect, border_radius=4)
        pygame.draw.rect(screen, COL_INSP_BORDER, tile_rect, 1, border_radius=4)
        txt = self.font_small.render(label, True, COL_FIELD_VALUE)
        screen.blit(txt, (tile_rect.x + (tile_rect.width - txt.get_width()) // 2,
                          tile_rect.y + (tile_rect.height - txt.get_height()) // 2))

    def _render_wall_tool_palette(self, insp_x, y_start, y_end):
        screen = self.screen
        tools = [("Draw", "draw"), ("Line", "line")]
        tile_w = (INSPECTOR_W - PALETTE_PAD * (len(tools) + 1)) // len(tools)
        for i, (label, tool_id) in enumerate(tools):
            tx = insp_x + PALETTE_PAD + i * (tile_w + PALETTE_PAD)
            tile_rect = pygame.Rect(tx, y_start + PALETTE_PAD, tile_w, 36)
            active = (self.wall_tool == tool_id)
            bg = COL_PALETTE_SEL if active else COL_BTN
            pygame.draw.rect(screen, bg, tile_rect, border_radius=4)
            pygame.draw.rect(screen, COL_INSP_BORDER, tile_rect, 1, border_radius=4)
            txt = self.font_small.render(label, True, COL_FIELD_VALUE)
            screen.blit(txt, (tile_rect.x + (tile_rect.width - txt.get_width()) // 2,
                              tile_rect.y + (tile_rect.height - txt.get_height()) // 2))

    def _render_sprite_palette(self, insp_x, y_start, y_end):
        screen = self.screen
        lv = self.level
        types = sorted(OBJECT_TYPE_NAMES.keys())
        tw = PALETTE_TILE_W
        th = PALETTE_TILE_H
        cols = PALETTE_COLS
        pad = PALETTE_PAD

        clip = pygame.Rect(insp_x, y_start, INSPECTOR_W, y_end - y_start)
        screen.set_clip(clip)

        max_scroll = max(0, math.ceil(len(types) / cols) * (th + pad) - (y_end - y_start))
        self.palette_scroll = min(self.palette_scroll, max_scroll)

        for idx, obj_type in enumerate(types):
            row = idx // cols
            col = idx % cols
            tx = insp_x + pad + col * (tw + pad)
            ty = y_start + pad + row * (th + pad) - self.palette_scroll

            if ty + th < y_start or ty > y_end:
                continue

            tile_rect = pygame.Rect(tx, ty, tw, th)
            armed = (self.palette_armed_type == obj_type)
            bg = COL_PALETTE_ARMED if armed else (35, 38, 52)
            pygame.draw.rect(screen, bg, tile_rect, border_radius=4)
            pygame.draw.rect(screen, COL_INSP_BORDER if not armed else (100, 180, 100),
                             tile_rect, 1, border_radius=4)

            label_h = 16
            sprite_area = pygame.Rect(tile_rect.x + 2, tile_rect.y + 2,
                                      tile_rect.width - 4,
                                      tile_rect.height - label_h - 2)
            label_area = pygame.Rect(tile_rect.x + 2, sprite_area.bottom,
                                     tile_rect.width - 4, label_h)

            # Sprite — fitted entirely within sprite_area, centred
            sprite = self.sprite_cache.get(obj_type, lv)
            if sprite is not None:
                sw_sp = sprite.get_width()
                sh_sp = sprite.get_height()
                scale = min(sprite_area.width / max(1, sw_sp),
                            sprite_area.height / max(1, sh_sp))
                if scale <= 0:
                    scale = 1.0
                dw = max(1, int(sw_sp * scale))
                dh = max(1, int(sh_sp * scale))
                scaled = pygame.transform.scale(sprite, (dw, dh))
                sx = sprite_area.x + (sprite_area.width - dw) // 2
                sy = sprite_area.y + (sprite_area.height - dh) // 2
                prev_clip = screen.get_clip()
                screen.set_clip(sprite_area)
                screen.blit(scaled, (sx, sy))
                screen.set_clip(prev_clip)

            # Object name (truncated to fit label_area)
            name = OBJECT_TYPE_NAMES.get(obj_type, f"${obj_type:02X}")
            txt_col = (200, 255, 200) if armed else (160, 165, 185)
            txt = self.font_small.render(name, True, txt_col)
            while txt.get_width() > label_area.width and len(name) > 1:
                name = name[:-1]
                txt = self.font_small.render(name + "…", True, txt_col)
            prev_clip = screen.get_clip()
            screen.set_clip(label_area)
            screen.blit(txt, (label_area.x + (label_area.width - txt.get_width()) // 2,
                              label_area.y + (label_area.height - txt.get_height()) // 2))
            screen.set_clip(prev_clip)

        screen.set_clip(None)

    # -------------------------------------------------------------------
    # Inspector event handling
    # -------------------------------------------------------------------

    def _update_inspector_hover(self, mx, my):
        """Update hovered_btn while mouse is in the inspector pane."""
        sw = self.screen.get_width()
        insp_x = sw - INSPECTOR_W
        split_y = self._inspector_split_y()
        if my >= split_y:
            self.hovered_btn = None
            return

        schema, target, level = schema_for_selection(self)
        field_top = self._inspector_field_top()
        y = field_top - self.inspector_scroll
        for field in schema:
            if field.kind not in ("byte", "signed_byte", "word"):
                y += FIELD_H
                continue
            rect = pygame.Rect(insp_x + 2, y, INSPECTOR_W - 4, FIELD_H)
            if rect.collidepoint(mx, my):
                wx = rect.x + FIELD_LABEL_W
                ww = rect.right - wx - 4
                w_rect = pygame.Rect(wx, rect.y + 2, ww, FIELD_H - 4)
                btn_w = 16
                dec = pygame.Rect(w_rect.x, w_rect.y, btn_w, w_rect.height)
                inc = pygame.Rect(w_rect.right - btn_w, w_rect.y, btn_w, w_rect.height)
                val_r = pygame.Rect(dec.right + 1, w_rect.y, inc.x - dec.right - 2, w_rect.height)
                if dec.collidepoint(mx, my):
                    self.hovered_btn = (field.id, "dec")
                elif inc.collidepoint(mx, my):
                    self.hovered_btn = (field.id, "inc")
                elif val_r.collidepoint(mx, my):
                    self.hovered_btn = (field.id, "val")
                else:
                    self.hovered_btn = None
                return
            y += FIELD_H
        self.hovered_btn = None

    def _handle_inspector_mouse_down(self, mx, my, button):
        sw = self.screen.get_width()
        insp_x = sw - INSPECTOR_W
        split_y = self._inspector_split_y()
        field_top = self._inspector_field_top()

        if button == 4 or button == 5:
            return  # handled by MOUSEWHEEL

        if my >= split_y:
            self._handle_palette_click(mx, my, button, insp_x, split_y)
            return

        if my < field_top:
            return

        # Field area click
        schema, target, level = schema_for_selection(self)
        y = field_top - self.inspector_scroll
        for field in schema:
            rect = pygame.Rect(insp_x + 2, y, INSPECTOR_W - 4, FIELD_H)
            if rect.collidepoint(mx, my):
                self.inspector_active_field = field.id
                if self.text_entry_field and self.text_entry_field != field.id:
                    self._commit_text_entry()
                self._handle_field_click(rect, field, target, level, mx, my, button)
                return
            y += FIELD_H

        # Click on empty field area: commit text entry
        if self.input_focus:
            self._commit_text_entry()

    def _handle_field_click(self, rect, field, target, level, mx, my, button):
        if field.kind in ("readonly", "header"):
            return

        # Button: invoke setter as side-effect on left-click. Undo + dirty
        # are handled here so individual button setters stay simple.
        if field.kind == "button":
            if button == 1:
                self.undo.save(level)
                field.set(target, None)
                level.dirty = True
            return

        wx = rect.x + FIELD_LABEL_W
        ww = rect.right - wx - 4
        w_rect = pygame.Rect(wx, rect.y + 2, ww, FIELD_H - 4)

        mods = pygame.key.get_mods()
        shift = bool(mods & pygame.KMOD_SHIFT)

        if field.kind == "colour":
            cell_count = 9 if field.allow_none else 8
            cell_w = max(1, w_rect.width // cell_count)
            if cell_w > 0 and w_rect.collidepoint(mx, my):
                ci = (mx - w_rect.x) // cell_w
                if 0 <= ci < cell_count:
                    new_val = None if (field.allow_none and ci == 8) else ci
                    old_val = field.get(target)
                    if new_val != old_val:
                        self.undo.save(level)
                        field.set(target, new_val)
                        level.dirty = True
                        self.sprite_cache.clear()
            return

        if field.kind in ("byte", "signed_byte", "word"):
            btn_w = 16
            dec = pygame.Rect(w_rect.x, w_rect.y, btn_w, w_rect.height)
            inc = pygame.Rect(w_rect.right - btn_w, w_rect.y, btn_w, w_rect.height)
            val_r = pygame.Rect(dec.right + 1, w_rect.y, inc.x - dec.right - 2, w_rect.height)
            step = field.shift_step if shift else field.step
            cur = field.get(target)
            if dec.collidepoint(mx, my):
                new_val = field.clamp(cur - step)
                if new_val != cur:
                    self.undo.save(level)
                    field.set(target, new_val)
                    level.dirty = True
            elif inc.collidepoint(mx, my):
                new_val = field.clamp(cur + step)
                if new_val != cur:
                    self.undo.save(level)
                    field.set(target, new_val)
                    level.dirty = True
            elif val_r.collidepoint(mx, my):
                self.text_entry_field = field.id
                self.text_entry_buf = ""
                self.text_entry_orig = cur
                self.input_focus = True
            return

        if field.kind == "enum":
            if field.values:
                vals = [v for _, v in field.values]
                cur = field.get(target)
                try:
                    ci = vals.index(cur)
                except ValueError:
                    ci = -1
                btn_w = 16
                dec = pygame.Rect(w_rect.x, w_rect.y, btn_w, w_rect.height)
                inc = pygame.Rect(w_rect.right - btn_w, w_rect.y, btn_w, w_rect.height)
                if button == 3 or dec.collidepoint(mx, my):
                    direction = -1
                elif inc.collidepoint(mx, my):
                    direction = 1
                else:
                    return
                new_val = vals[(ci + direction) % len(vals)]
                if new_val != cur:
                    self.undo.save(level)
                    field.set(target, new_val)
                    level.dirty = True
            return

        if field.kind == "ref":
            btn_w = 38
            pick_rect = pygame.Rect(w_rect.right - btn_w, w_rect.y, btn_w, w_rect.height)
            cur = field.get(target)
            if pick_rect.collidepoint(mx, my):
                # Arm pick mode
                if self.ref_pick_field == field.id:
                    self.ref_pick_field = None  # toggle off
                else:
                    self.ref_pick_field = field.id
                    self.ref_pick_target = target
                    self.ref_pick_level = level
            else:
                # Cycle. Object refs include $FF as a "none" stop in the
                # cycle so users can clear a wiring without text-entry.
                direction = 1 if button == 1 else -1
                if field.target_kind == "checkpoint":
                    n = len(level.checkpoints)
                    if n > 0:
                        new_val = (cur + direction) % n
                    else:
                        new_val = cur
                else:  # "object"
                    n = len(level.objects)
                    if n == 0:
                        new_val = 0xFF
                    elif cur == 0xFF:
                        new_val = 0 if direction == 1 else n - 1
                    else:
                        nxt = cur + direction
                        if nxt < 0 or nxt >= n:
                            new_val = 0xFF
                        else:
                            new_val = nxt
                if new_val != cur:
                    self.undo.save(level)
                    field.set(target, new_val)
                    level.dirty = True
            return

    def _handle_palette_click(self, mx, my, button, insp_x, split_y):
        if self.mode == "object":
            types = sorted(OBJECT_TYPE_NAMES.keys())
            tw, th = PALETTE_TILE_W, PALETTE_TILE_H
            pad = PALETTE_PAD
            for idx, obj_type in enumerate(types):
                row = idx // PALETTE_COLS
                col = idx % PALETTE_COLS
                tx = insp_x + pad + col * (tw + pad)
                ty = split_y + 1 + pad + row * (th + pad) - self.palette_scroll
                tile_rect = pygame.Rect(tx, ty, tw, th)
                if tile_rect.collidepoint(mx, my):
                    if self.palette_armed_type == obj_type:
                        self.palette_armed_type = None  # disarm
                    else:
                        self.palette_armed_type = obj_type
                    return
        elif self.mode == "wall":
            # Wall tool tiles
            tools = [("draw", 0), ("line", 1)]
            tile_w = (INSPECTOR_W - PALETTE_PAD * 3) // 2
            for tool_id, i in tools:
                tx = insp_x + PALETTE_PAD + i * (tile_w + PALETTE_PAD)
                tile_rect = pygame.Rect(tx, split_y + 1 + PALETTE_PAD, tile_w, 36)
                if tile_rect.collidepoint(mx, my):
                    self.wall_tool = tool_id
                    self.line_start = None
                    return

    def _place_armed_object(self, wx, wy):
        """Place an instance of palette_armed_type at world position (wx, wy)."""
        obj_type = self.palette_armed_type
        if obj_type is None:
            return
        is_well = obj_type == OBJECT_GRAVITY_WELL
        is_mine = obj_type in BOBBING_MINE_TYPES
        is_tp = obj_type == OBJECT_TELEPORTER
        self.undo.save(self.level)
        self.level.objects.append({
            "x": max(0, min(255, wx)), "y": max(0, wy), "type": obj_type,
            "gun_aim": 0x00,
            "laser_dx": LASER_BEAM_DX_PIXELS.get(obj_type, 0),
            "laser_dy": LASER_BEAM_DY_ROWS.get(obj_type, 0),
            "well_radius": GRAVITY_WELL_DEFAULT_RADIUS if is_well else 0,
            "well_strength": GRAVITY_WELL_DEFAULT_STRENGTH if is_well else 0,
            "mine_phase": BOBBING_MINE_DEFAULT_PHASE if is_mine else 0,
            "mine_amp": BOBBING_MINE_DEFAULT_AMP if is_mine else 0,
            "teleport_dest": TELEPORTER_DEFAULT_DEST if is_tp else 0,
        })
        self.level.dirty = True
        self.selected_object = len(self.level.objects) - 1
        # Disarm after placing (keep armed for repeated placement)

    def _handle_ref_pick_click(self, mx, my):
        """Canvas click during ref-pick mode: set the field to the nearest target."""
        if self.ref_pick_field is None:
            return
        lv = self.level
        field_id = self.ref_pick_field
        target = self.ref_pick_target
        level = self.ref_pick_level
        # Find matching field
        schema, _, _ = schema_for_selection(self)
        for field in schema:
            if field.id != field_id:
                continue
            if field.target_kind == "checkpoint" and lv.checkpoints:
                # Pick nearest checkpoint by distance on screen
                best_i, best_d = 0, float('inf')
                for i, cp in enumerate(lv.checkpoints):
                    sx, sy = self.camera.world_to_screen(cp["spawn_x"], cp["spawn_y"])
                    d = (sx - mx) ** 2 + (sy - my) ** 2
                    if d < best_d:
                        best_d, best_i = d, i
                old_val = field.get(target)
                if best_i != old_val:
                    self.undo.save(level)
                    field.set(target, best_i)
                    level.dirty = True
            elif field.target_kind == "object" and lv.objects:
                # Pick nearest object by screen distance. Self-targeting
                # is allowed — a switch can validly wire to itself (e.g.
                # destroy-self, or any future "consume on activation"
                # semantics).
                best_i, best_d = None, float('inf')
                for i, obj in enumerate(lv.objects):
                    sx, sy = self.camera.world_to_screen(obj["x"], obj["y"])
                    d = (sx - mx) ** 2 + (sy - my) ** 2
                    if d < best_d:
                        best_d, best_i = d, i
                if best_i is not None:
                    old_val = field.get(target)
                    if best_i != old_val:
                        self.undo.save(level)
                        field.set(target, best_i)
                        level.dirty = True
            break
        self.ref_pick_field = None

    # -------------------------------------------------------------------
    # Text entry
    # -------------------------------------------------------------------

    def _commit_text_entry(self):
        if not self.text_entry_field:
            self.input_focus = False
            return
        schema, target, level = schema_for_selection(self)
        for field in schema:
            if field.id != self.text_entry_field:
                continue
            parsed = self._parse_value(self.text_entry_buf, field)
            if parsed is not None:
                clamped = field.clamp(parsed)
                old_val = field.get(target)
                if clamped != old_val:
                    self.undo.save(level)
                    field.set(target, clamped)
                    level.dirty = True
                    if field.kind == "colour":
                        self.sprite_cache.clear()
            break
        self.text_entry_field = None
        self.text_entry_buf = ""
        self.text_entry_orig = None
        self.input_focus = False

    def _cancel_text_entry(self):
        self.text_entry_field = None
        self.text_entry_buf = ""
        self.text_entry_orig = None
        self.input_focus = False

    def _parse_value(self, text, field):
        """Parse a typed value string: decimal, $hex, +N/-N."""
        text = text.strip()
        if not text:
            return None
        try:
            if text.startswith("$") or text.startswith("&"):
                return int(text[1:], 16)
            if text.startswith("0x") or text.startswith("0X"):
                return int(text, 16)
            return int(text)
        except ValueError:
            return None


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
