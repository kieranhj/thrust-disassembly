"""Object sprite codec for Thrust (BBC Micro).

Parses the 9 object sprites (two-stream format) from thrust.6502 or from a
standalone export file. Decodes to a 2D pixel grid (Mode 1 logical colours
0-3). Encodes back to stream A + stream B bytes.

Stream format (per rip_sprites.py):
  Stream A: one byte per non-empty char column in the sprite
    bit 7 set  = "advance to next pixel row first", char_col in bits 6-3
    bit 7 clear = same row, char_col in bits 6-3
    $FF         = terminator
  Stream B: raw Mode 1 screen bytes (4 pixels per byte)
    pixel i colour bits: high = bit (7-i), low = bit (3-i)

Width (char cols) and height (pixel rows) are external metadata from
obj_type_width / obj_type_height tables. The codec carries them alongside
each sprite so encode can emit a pixel-perfect round-trip.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# In order matching obj_sprite_data_A_table_LO. Index = OBJECT_* type byte.
OBJECT_NAMES = [
    "gun_up_right",
    "gun_down_right",
    "gun_up_left",
    "gun_down_left",
    "fuel",
    "pod_stand",
    "generator",
    "door_switch_right",
    "door_switch_left",
    "laser_turret_up_right",
    "laser_turret_down_right",
    "laser_turret_up_left",
    "laser_turret_down_left",
    "gravity_well",                     # $0D: invisible field, sprite never plots (early-exit in update)
    "bobbing_mine",                     # $0E: vertical sine-wave hazard
    "bobbing_mine_horizontal",          # $0F: horizontal sine-wave hazard
]

# Char-column widths from obj_type_width.
OBJECT_WIDTH_CHARS = {
    "gun_up_right":            5,
    "gun_down_right":          5,
    "gun_up_left":             5,
    "gun_down_left":           5,
    "fuel":                    4,
    "pod_stand":               5,
    "generator":               5,
    "door_switch_right":       2,
    "door_switch_left":        2,
    "laser_turret_up_right":   5,
    "laser_turret_down_right": 5,
    "laser_turret_up_left":    5,
    "laser_turret_down_left":  5,
    "gravity_well":            1,
    "bobbing_mine":            3,
    "bobbing_mine_horizontal": 3,
}

# BBC Micro Mode 1 physical palette (8 physical colours, index 0-7).
BBC_COLOURS = {
    0: (0, 0, 0),         # Black
    1: (255, 0, 0),       # Red
    2: (0, 255, 0),       # Green
    3: (255, 255, 0),     # Yellow
    4: (0, 0, 255),       # Blue
    5: (255, 0, 255),     # Magenta
    6: (0, 255, 255),     # Cyan
    7: (255, 255, 255),   # White
}

BBC_COLOUR_NAMES = {
    0: "Black", 1: "Red", 2: "Green", 3: "Yellow",
    4: "Blue",  5: "Magenta", 6: "Cyan", 7: "White",
}

# Per-level defaults for landscape (logical 2) and object (logical 3)
# colours. Extracted from thrust.6502:6866/6869. Index = level number.
# Logical 0 is always black; logical 1 is always yellow (ship).
LEVEL_LANDSCAPE_COLOUR = [0x01, 0x02, 0x06, 0x02, 0x01, 0x05]
LEVEL_OBJECT_COLOUR    = [0x02, 0x01, 0x02, 0x05, 0x05, 0x06]

# Fixed logical colours.
LOGICAL_SHIP_PHYSICAL = 0x03  # colour 1 = yellow (ship, always)


def make_logical_palette(landscape_phys: int,
                         object_phys: int) -> Dict[int, tuple]:
    """Build {logical_colour: (R,G,B,A)} for the 4 Mode 1 logical colours.

    Colour 0 is transparent, colour 1 is always yellow (ship, fixed),
    colours 2 and 3 are configurable as landscape / object physical colours.
    """
    return {
        0: (0, 0, 0, 0),
        1: BBC_COLOURS[LOGICAL_SHIP_PHYSICAL] + (255,),
        2: BBC_COLOURS[landscape_phys & 7] + (255,),
        3: BBC_COLOURS[object_phys & 7] + (255,),
    }


# Static fallback palette (landscape=red, object=green — level 0 defaults).
# Used by code that doesn't know the editor's current palette state.
MODE1_PALETTE = make_logical_palette(LEVEL_LANDSCAPE_COLOUR[0],
                                     LEVEL_OBJECT_COLOUR[0])


# ---------------------------------------------------------------------------
# Mode 1 byte <-> 4 pixel colours
# ---------------------------------------------------------------------------

def decode_mode1_byte(byte: int) -> List[int]:
    """Split a Mode 1 screen byte into 4 logical colours (left-to-right)."""
    out = []
    for p in range(4):
        hi = (byte >> (7 - p)) & 1
        lo = (byte >> (3 - p)) & 1
        out.append((hi << 1) | lo)
    return out


def encode_mode1_byte(pixels: List[int]) -> int:
    """Pack 4 logical colours (left-to-right) back into a Mode 1 screen byte."""
    assert len(pixels) == 4
    out = 0
    for p, col in enumerate(pixels):
        hi = (col >> 1) & 1
        lo = col & 1
        out |= hi << (7 - p)
        out |= lo << (3 - p)
    return out


# ---------------------------------------------------------------------------
# Sprite data model
# ---------------------------------------------------------------------------

@dataclass
class Sprite:
    name: str
    width_chars: int                  # char-columns (4 pixels each)
    height: int                       # pixel rows
    pixels: List[List[int]]           # [row][col_px], values 0..3
    # Some original sprites author the first stream-A byte WITHOUT the
    # row-advance bit 7. rip_sprites.py tolerates this via min_y normalisation.
    # We preserve the flag so round-trip emits identical bytes.
    first_byte_has_advance: bool = True
    # Raw original bytes so we can preserve any trailing padding on round-trip.
    orig_stream_a: List[int] = field(default_factory=list)
    orig_stream_b: List[int] = field(default_factory=list)

    @property
    def width_px(self) -> int:
        return self.width_chars * 4

    def clone(self) -> "Sprite":
        return Sprite(
            name=self.name,
            width_chars=self.width_chars,
            height=self.height,
            pixels=[row[:] for row in self.pixels],
            first_byte_has_advance=self.first_byte_has_advance,
            orig_stream_a=self.orig_stream_a[:],
            orig_stream_b=self.orig_stream_b[:],
        )


# ---------------------------------------------------------------------------
# Source parsing (extract EQUB bytes from a .label block)
# ---------------------------------------------------------------------------

_HEX_VAL_RE = re.compile(r'[\$&]([0-9A-Fa-f]+)')


def _parse_equb_line(line: str) -> List[int]:
    """Parse an EQUB ... line, stripping comments. Returns hex byte ints."""
    # Strip comments (BeebAsm uses \ or ;).
    for marker in ('\\', ';'):
        if marker in line:
            line = line.split(marker, 1)[0]
    line = line.strip()
    if not line.upper().startswith('EQUB'):
        return []
    body = line[4:]
    out = []
    for tok in body.split(','):
        tok = tok.strip()
        if not tok:
            continue
        m = _HEX_VAL_RE.search(tok)
        if m:
            out.append(int(m.group(1), 16))
        elif tok.isdigit():
            out.append(int(tok))
        else:
            raise ValueError(f"Could not parse EQUB token: {tok!r}")
    return out


def extract_label_bytes(source: str, label: str) -> List[int]:
    """Extract EQUB bytes following .<label> until the next label."""
    # Match ".label" at line start (possibly indented).
    pattern = re.compile(r'^[ \t]*\.' + re.escape(label) + r'\b.*$',
                         re.MULTILINE)
    m = pattern.search(source)
    if not m:
        raise ValueError(f"Label '{label}' not found")
    data = []
    # Start after the label line.
    lines = source[m.end():].split('\n')
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('\\') or stripped.startswith(';'):
            continue
        if stripped.startswith('.'):
            break
        # Stop on directives that aren't EQUB (IF/ENDIF/INCLUDE/etc.)
        upper = stripped.upper()
        if not upper.startswith('EQUB'):
            break
        data.extend(_parse_equb_line(line))
    return data


# ---------------------------------------------------------------------------
# Decode: two-stream bytes -> pixel grid
# ---------------------------------------------------------------------------

def decode_streams(stream_a: List[int],
                   stream_b: List[int],
                   width_chars: int
                   ) -> Tuple[List[List[int]], int, int, bool]:
    """Decode stream A/B into a pixel grid.

    Returns (pixels, height_rows, n_consumed_b, first_byte_has_advance).
    pixels is indexed as pixels[row][col], colour values 0..3.

    If the first non-$FF byte in stream A does not have bit 7 set, that byte
    contributes to row 0 (a "pre-row" that rip_sprites.py normalises via
    min_y). We lift everything so the grid starts at row 0 either way, and
    return the original first-byte style so the encoder can reproduce it.
    """
    width_px = width_chars * 4
    pixel_row = -1
    b_idx = 0
    entries = []  # (char_col, row, mode1_byte)
    first_byte_has_advance = True
    first_byte = True
    for a in stream_a:
        if a == 0xFF:
            break
        if a & 0x80:
            pixel_row += 1
            char_col = (a & 0x7F) >> 3
        else:
            char_col = a >> 3
        if first_byte:
            first_byte_has_advance = bool(a & 0x80)
            first_byte = False
            if not first_byte_has_advance:
                # Treat this byte as belonging to row 0 like the real renderer.
                pixel_row = 0
        entries.append((char_col, pixel_row, stream_b[b_idx]))
        b_idx += 1

    height = pixel_row + 1 if pixel_row >= 0 else 0
    pixels = [[0] * width_px for _ in range(height)]
    for char_col, row, mode_byte in entries:
        colours = decode_mode1_byte(mode_byte)
        base_x = char_col * 4
        for i, c in enumerate(colours):
            x = base_x + i
            if 0 <= x < width_px and 0 <= row < height:
                pixels[row][x] = c
    return pixels, height, b_idx, first_byte_has_advance


# ---------------------------------------------------------------------------
# Encode: pixel grid -> two-stream bytes
# ---------------------------------------------------------------------------

def encode_streams(pixels: List[List[int]],
                   width_chars: int,
                   first_byte_has_advance: bool = True
                   ) -> Tuple[List[int], List[int]]:
    """Encode a pixel grid into stream A + stream B.

    Emits one (stream_a_byte, stream_b_byte) pair per non-empty char column
    per row. The first entry of each row after the starting row has bit 7
    set in stream A (row advance). Empty interior rows emit a dummy advance
    with a $00 B-byte. Trailing empty rows are omitted. Stream A is
    terminated with $FF. Stream B is not terminated here (callers pad).

    If first_byte_has_advance is False, the very first emitted stream A byte
    has bit 7 cleared (to match some original sprites whose data starts
    without a leading row-advance marker).
    """
    stream_a: List[int] = []
    stream_b: List[int] = []

    # Find last non-empty row so we can trim trailing empty rows.
    last_nonempty = -1
    for r, row in enumerate(pixels):
        if any(p != 0 for p in row):
            last_nonempty = r

    if last_nonempty < 0:
        stream_a.append(0xFF)
        return stream_a, stream_b

    for r in range(last_nonempty + 1):
        row = pixels[r]
        # Collect non-empty char columns in this row.
        non_empty_cols = []
        for cc in range(width_chars):
            base_x = cc * 4
            quad = row[base_x:base_x + 4]
            # Pad if row is shorter than expected (shouldn't happen).
            while len(quad) < 4:
                quad.append(0)
            if any(p != 0 for p in quad):
                non_empty_cols.append((cc, encode_mode1_byte(quad)))

        if not non_empty_cols:
            # Empty interior row: emit a dummy advance at char_col 0.
            stream_a.append(0x80)
            stream_b.append(0x00)
            continue

        first = True
        for cc, mode_byte in non_empty_cols:
            byte_a = (cc << 3) & 0x7F
            if first:
                byte_a |= 0x80
                first = False
            stream_a.append(byte_a)
            stream_b.append(mode_byte)

    # If the original omitted bit 7 on the very first byte, reproduce that.
    if not first_byte_has_advance and stream_a:
        stream_a[0] &= 0x7F

    stream_a.append(0xFF)
    return stream_a, stream_b


# ---------------------------------------------------------------------------
# High-level: load all 9 sprites from a source
# ---------------------------------------------------------------------------

def load_sprites_from_source(source: str) -> Dict[str, Sprite]:
    """Load all object sprites from a thrust.6502 (or export) source string.

    If a sprite's label is missing, or decodes to zero height (placeholder
    $FF-only entry for a newly added OBJECT_NAMES entry that hasn't been
    drawn yet), returns a blank sprite of the configured width at default
    height so the editor can still launch and the user can paint it.
    """
    out = {}
    default_h = 8
    for name in OBJECT_NAMES:
        width = OBJECT_WIDTH_CHARS[name]
        try:
            sa = extract_label_bytes(source, f"obj_sprite_data_A_{name}")
            sb = extract_label_bytes(source, f"obj_sprite_data_B_{name}")
            pixels, height, _, first_adv = decode_streams(sa, sb, width)
        except ValueError:
            pixels, height, first_adv, sa, sb = [], 0, True, [], []
        if height == 0 or not pixels:
            out[name] = Sprite(
                name=name,
                width_chars=width,
                height=default_h,
                pixels=[[0] * (width * 4) for _ in range(default_h)],
            )
        else:
            out[name] = Sprite(
                name=name,
                width_chars=width,
                height=height,
                pixels=pixels,
                first_byte_has_advance=first_adv,
                orig_stream_a=sa[:],
                orig_stream_b=sb[:],
            )
    return out


def load_sprites_from_file(path: str) -> Dict[str, Sprite]:
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return load_sprites_from_source(f.read())


# ---------------------------------------------------------------------------
# Export: write object_sprites.asm
# ---------------------------------------------------------------------------

_HEADER = """\\ ******************************************************************************
\\ * Object sprite data (two-stream format)                                     *
\\ *                                                                            *
\\ * AUTO-GENERATED by tools/sprite_editor.py -- do not hand-edit.              *
\\ * Original data lives in thrust.6502 inside IF _SWRAM_BUILD=FALSE. This file *
\\ * is INCLUDEd in the SWRAM build so edits here take effect without touching  *
\\ * the main source.                                                           *
\\ ******************************************************************************

"""


def _format_equb_block(data: List[int], bytes_per_line: int = 8) -> List[str]:
    """Format a byte list as indented EQUB lines."""
    lines = []
    for i in range(0, len(data), bytes_per_line):
        chunk = data[i:i + bytes_per_line]
        vals = ','.join(f'${b:02X}' for b in chunk)
        lines.append(f'        EQUB    {vals}')
    return lines


def _pad_stream_b(new_b: List[int], orig_b: List[int]) -> List[int]:
    """If original had trailing $FF padding, preserve that length."""
    if len(new_b) < len(orig_b):
        pad_count = len(orig_b) - len(new_b)
        # Use whatever the original used as trailing bytes.
        tail = orig_b[-pad_count:]
        return new_b + tail
    return new_b


def format_object_sprites_asm(sprites: Dict[str, Sprite]) -> str:
    """Produce the full text for tools/output/object_sprites.asm."""
    out_lines = [_HEADER.rstrip('\n')]

    # Sprite data.
    for name in OBJECT_NAMES:
        spr = sprites[name]
        sa, sb = encode_streams(spr.pixels, spr.width_chars,
                                spr.first_byte_has_advance)
        sb = _pad_stream_b(sb, spr.orig_stream_b)

        out_lines.append('')
        out_lines.append(f'.obj_sprite_data_A_{name}')
        out_lines.extend(_format_equb_block(sa))
        out_lines.append(f'.obj_sprite_data_B_{name}')
        out_lines.extend(_format_equb_block(sb))

    # Pointer tables.
    out_lines.append('')
    out_lines.append('.obj_sprite_data_A_table_LO')
    for name in OBJECT_NAMES:
        out_lines.append(f'        EQUB    LO(obj_sprite_data_A_{name})')
    out_lines.append('')
    out_lines.append('.obj_sprite_data_A_table_HI')
    for name in OBJECT_NAMES:
        out_lines.append(f'        EQUB    HI(obj_sprite_data_A_{name})')
    out_lines.append('')
    out_lines.append('.obj_sprite_data_B_table_LO')
    for name in OBJECT_NAMES:
        out_lines.append(f'        EQUB    LO(obj_sprite_data_B_{name})')
    out_lines.append('')
    out_lines.append('.obj_sprite_data_B_table_HI')
    for name in OBJECT_NAMES:
        out_lines.append(f'        EQUB    HI(obj_sprite_data_B_{name})')
    out_lines.append('')
    return '\n'.join(out_lines)


def write_object_sprites_asm(sprites: Dict[str, Sprite], path: str) -> None:
    """Write the export file atomically (tmp + rename)."""
    text = format_object_sprites_asm(sprites)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Assembled-bytes helpers (for round-trip tests that must be byte-identical)
# ---------------------------------------------------------------------------

def assembled_bytes(sprite: Sprite) -> Tuple[List[int], List[int]]:
    """Return the stream A / B bytes this sprite would contribute to the asm."""
    sa, sb = encode_streams(sprite.pixels, sprite.width_chars,
                            sprite.first_byte_has_advance)
    sb = _pad_stream_b(sb, sprite.orig_stream_b)
    return sa, sb


# ---------------------------------------------------------------------------
# Self-test: round-trip all 9 sprites from the current thrust.6502
# ---------------------------------------------------------------------------

def _self_test(source_path: str) -> int:
    """Parse, decode, re-encode, compare. Return 0 if byte-identical."""
    print(f"Loading sprites from {source_path}")
    with open(source_path, 'r', encoding='utf-8', errors='replace') as f:
        source = f.read()
    sprites = load_sprites_from_source(source)

    # Mode 1 byte codec round-trip: all 256 values.
    for b in range(256):
        if encode_mode1_byte(decode_mode1_byte(b)) != b:
            print(f"FAIL: mode1 byte codec broken at ${b:02X}")
            return 1
    print("OK   mode1 byte codec round-trips for all 256 values")

    # Per-sprite round-trip.
    bad = 0
    for name in OBJECT_NAMES:
        spr = sprites[name]
        sa_new, sb_new = assembled_bytes(spr)
        if sa_new != spr.orig_stream_a:
            bad += 1
            print(f"FAIL: {name} stream A differs")
            print(f"  orig: {' '.join(f'{b:02X}' for b in spr.orig_stream_a)}")
            print(f"  new:  {' '.join(f'{b:02X}' for b in sa_new)}")
            continue
        if sb_new != spr.orig_stream_b:
            bad += 1
            print(f"FAIL: {name} stream B differs")
            print(f"  orig: {' '.join(f'{b:02X}' for b in spr.orig_stream_b)}")
            print(f"  new:  {' '.join(f'{b:02X}' for b in sb_new)}")
            continue
        print(f"OK   {name}: {spr.width_chars*4}x{spr.height} "
              f"({len(sa_new)}A + {len(sb_new)}B bytes)")
    return 1 if bad else 0


if __name__ == '__main__':
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    # Try each in order: export file, extracted inline, then full source.
    candidates = [
        os.path.join(repo, 'tools', 'output', 'object_sprites.asm'),
        os.path.join(repo, 'obj_sprite_data.6502'),
        os.path.join(repo, 'thrust.6502'),
    ]
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = next((c for c in candidates if os.path.exists(c)), candidates[-1])
    sys.exit(_self_test(path))
