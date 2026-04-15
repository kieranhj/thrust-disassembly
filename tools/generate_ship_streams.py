"""Generate pre-baked two-stream ship sprite data for the _FAST_SPRITES build.

Reads original single-stream ship sprite data from thrust.6502 and generates
two-stream format (stream A = screen byte offsets, stream B = pixel masks)
pre-computed for all 32 angles x 4 pixel columns, plus shield and pod.

Output: tools/output/ship_twostream_data.asm

Usage:
    python tools/generate_ship_streams.py [--source thrust.6502]
"""

import argparse
import os
import re
import sys

# BBC Micro Mode 1 pixel mask tables (indexed by pixel column 0-3 within byte)
PIXEL_MASKS_1 = [0x88, 0x44, 0x22, 0x11]  # colour 3 (both bitplanes)
PIXEL_MASKS_2 = [0x80, 0x40, 0x20, 0x10]  # colour 2 (high bitplane only)
PIXEL_MASKS_3 = [0x08, 0x04, 0x02, 0x01]  # colour 1 (low bitplane only)

NUM_ANGLES = 32
NUM_SHIP_SPRITES = 17  # sprite data for angles 0-16
SHIELD_SPRITE_INDEX = 0x11


# ---------------------------------------------------------------------------
# Source parsing (reused from rip_sprites.py)
# ---------------------------------------------------------------------------

def parse_source(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_label_data(source, label):
    pattern = re.compile(r'^\.' + re.escape(label) + r'\b', re.MULTILINE)
    m = pattern.search(source)
    if not m:
        raise ValueError(f"Label '{label}' not found in source")
    data = []
    pos = m.end()
    for line in source[pos:].split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('.') or (not line.startswith('EQUB') and not line.startswith('\\') and data):
            break
        if line.startswith('EQUB'):
            equb_part = line[4:].split('\\')[0].split(';')[0].strip()
            for val in equb_part.split(','):
                val = val.strip()
                if val.startswith('$'):
                    data.append(int(val[1:], 16))
                elif val.startswith('&'):
                    data.append(int(val[1:], 16))
                elif val.isdigit():
                    data.append(int(val))
    return data


# ---------------------------------------------------------------------------
# Single-stream sprite decoding
# ---------------------------------------------------------------------------

def decode_single_stream(data):
    """Decode a single-stream sprite into a list of (row_events).

    Each row_event is a list of pixel bytes for that row.
    Row advances create new rows. The first byte may start an implicit row 0.

    Returns a list of rows, where each row is a list of raw pixel bytes (0-$7F).
    The row list includes empty rows (from $80 markers).
    """
    rows = []
    current_row = []
    i = 0

    while i < len(data):
        byte = data[i]
        if byte == 0xFF:
            break

        if byte >= 0x80:
            # Row advance marker
            rows.append(current_row)
            current_row = []
            # Re-read as pixel data if != $80
            if byte != 0x80:
                current_row.append(byte)  # bit 7 ignored during coord extract
            i += 1
        else:
            current_row.append(byte)
            i += 1

    # Don't forget the last row (before $FF terminator)
    if current_row:
        rows.append(current_row)

    return rows


def generate_two_stream(rows, pixel_column, mirror=False):
    """Convert decoded rows into two-stream (A, B) format.

    Stream B always contains pixel_masks_1 values (both bitplanes: $88,$44,$22,$11)
    so that collision detection works against all screen colours. The plotter applies
    colour reduction at runtime (AND #$0F for ship colour 1, NOP NOP for shield colour 3).

    Args:
        rows: list of rows, each a list of raw pixel bytes
        pixel_column: 0-3, the sub-character pixel offset to bake in
        mirror: if True, apply EOR #$1F to each pixel byte before processing

    Returns:
        (stream_a, stream_b) - lists of ints, terminated by $FF in stream_a
    """
    stream_a = []
    stream_b = []

    for row_idx, row_pixels in enumerate(rows):
        for pix_idx, raw_byte in enumerate(row_pixels):
            # Apply mirror if needed (horizontal flip)
            if mirror:
                effective = (raw_byte ^ 0x1F) & 0x3F
            else:
                effective = raw_byte & 0x3F

            # Add pixel column offset
            shifted = (effective + pixel_column) & 0x3F

            # Compute Y register value (screen byte offset)
            # bits 5-2 = character column, * 2 via ROL = byte offset
            y_offset = (shifted & 0x3C) * 2

            # Always use pixel_masks_1 (both bitplanes) for collision detection.
            # Runtime colour reduction (AND #$0F) selects the drawing colour.
            mask_idx = shifted & 0x03
            mask_byte = PIXEL_MASKS_1[mask_idx]

            # First pixel of each row (except row 0) gets bit 7 set = row advance
            if row_idx > 0 and pix_idx == 0:
                stream_a.append(y_offset | 0x80)
            else:
                stream_a.append(y_offset)

            stream_b.append(mask_byte)

        # Empty row: row with no pixels needs a row-advance + no-op plot
        if not row_pixels and row_idx > 0:
            stream_a.append(0x80)  # row advance, Y offset = 0
            stream_b.append(0x00)  # no-op pixel (EOR with 0)

    # Terminator
    stream_a.append(0xFF)

    return stream_a, stream_b


# ---------------------------------------------------------------------------
# Assembly output
# ---------------------------------------------------------------------------

def format_equb_line(data, per_line=16):
    """Format a list of ints as EQUB lines."""
    lines = []
    for i in range(0, len(data), per_line):
        chunk = data[i:i + per_line]
        vals = ','.join(f'${v:02X}' for v in chunk)
        lines.append(f'        EQUB    {vals}')
    return '\n'.join(lines)


def generate_asm(ship_sprites, shield_data, pod_data, source_path):
    """Generate the complete .asm file content.

    Args:
        ship_sprites: list of 17 single-stream sprite byte lists (angles 0-16)
        shield_data: single-stream byte list for shield
        pod_data: single-stream byte list for pod
        source_path: path to source file (for header comment)
    """
    lines = []
    lines.append('; Auto-generated by generate_ship_streams.py')
    lines.append('; Pre-baked two-stream ship sprite data for _FAST_SPRITES build')
    lines.append(f'; Source: {os.path.basename(source_path)}')
    lines.append(';')
    lines.append('; Format: stream A = screen byte offsets (bit 7 = row advance, $FF = end)')
    lines.append(';         stream B = pixel mask bytes for XOR plotting')
    lines.append('')

    # Track all generated stream labels for pointer tables
    # ship_labels[angle][pixel_col] = (label_a, label_b)
    ship_labels = {}
    shield_labels = {}
    pod_labels = {}

    total_bytes = 0

    # --- Ship sprites: 32 angles x 4 pixel columns ---
    lines.append('; ' + '=' * 70)
    lines.append('; Ship sprite data: 32 angles x 4 pixel columns = 128 variants')
    lines.append('; ' + '=' * 70)

    for angle in range(NUM_ANGLES):
        ship_labels[angle] = {}

        # Determine which sprite data to use and whether to mirror
        if angle < NUM_SHIP_SPRITES:
            # Angles 0-16: use sprite directly, no mirror
            sprite_idx = angle
            mirror = False
        else:
            # Angles 17-31: use sprite (32 - angle) with X mirror
            sprite_idx = NUM_ANGLES - angle  # 32-17=15, 32-18=14, ..., 32-31=1
            mirror = True

        sprite_data = ship_sprites[sprite_idx]
        rows = decode_single_stream(sprite_data)

        for pixel_col in range(4):
            stream_a, stream_b = generate_two_stream(
                rows, pixel_col, mirror=mirror
            )

            label_a = f'ship_ts_A_{angle:02d}_c{pixel_col}'
            label_b = f'ship_ts_B_{angle:02d}_c{pixel_col}'
            ship_labels[angle][pixel_col] = (label_a, label_b)

            lines.append(f'.{label_a}')
            lines.append(format_equb_line(stream_a))
            lines.append(f'.{label_b}')
            lines.append(format_equb_line(stream_b))

            total_bytes += len(stream_a) + len(stream_b)

    # --- Shield sprite: 4 pixel columns ---
    lines.append('')
    lines.append('; ' + '=' * 70)
    lines.append('; Shield sprite data: 4 pixel column variants')
    lines.append('; ' + '=' * 70)

    shield_rows = decode_single_stream(shield_data)
    for pixel_col in range(4):
        stream_a, stream_b = generate_two_stream(
            shield_rows, pixel_col, mirror=False
        )

        label_a = f'shield_ts_A_c{pixel_col}'
        label_b = f'shield_ts_B_c{pixel_col}'
        shield_labels[pixel_col] = (label_a, label_b)

        lines.append(f'.{label_a}')
        lines.append(format_equb_line(stream_a))
        lines.append(f'.{label_b}')
        lines.append(format_equb_line(stream_b))

        total_bytes += len(stream_a) + len(stream_b)

    # --- Pod sprite: 4 pixel columns ---
    lines.append('')
    lines.append('; ' + '=' * 70)
    lines.append('; Pod sprite data: 4 pixel column variants')
    lines.append('; ' + '=' * 70)

    pod_rows = decode_single_stream(pod_data)
    for pixel_col in range(4):
        stream_a, stream_b = generate_two_stream(
            pod_rows, pixel_col, mirror=False
        )

        label_a = f'pod_ts_A_c{pixel_col}'
        label_b = f'pod_ts_B_c{pixel_col}'
        pod_labels[pixel_col] = (label_a, label_b)

        lines.append(f'.{label_a}')
        lines.append(format_equb_line(stream_a))
        lines.append(f'.{label_b}')
        lines.append(format_equb_line(stream_b))

        total_bytes += len(stream_a) + len(stream_b)

    # --- Pointer tables ---
    lines.append('')
    lines.append('; ' + '=' * 70)
    lines.append('; Pointer tables: indexed by angle * 4 + pixel_column')
    lines.append('; ' + '=' * 70)
    lines.append('')

    # Ship stream A pointers (128 entries: 32 angles x 4 pixel cols)
    lines.append('.ship_ts_ptr_A_LO')
    for angle in range(NUM_ANGLES):
        entries = []
        for pc in range(4):
            label_a, _ = ship_labels[angle][pc]
            entries.append(f'LO({label_a})')
        lines.append(f'        EQUB    {",".join(entries)}')
    total_bytes += 128

    lines.append('.ship_ts_ptr_A_HI')
    for angle in range(NUM_ANGLES):
        entries = []
        for pc in range(4):
            label_a, _ = ship_labels[angle][pc]
            entries.append(f'HI({label_a})')
        lines.append(f'        EQUB    {",".join(entries)}')
    total_bytes += 128

    lines.append('.ship_ts_ptr_B_LO')
    for angle in range(NUM_ANGLES):
        entries = []
        for pc in range(4):
            _, label_b = ship_labels[angle][pc]
            entries.append(f'LO({label_b})')
        lines.append(f'        EQUB    {",".join(entries)}')
    total_bytes += 128

    lines.append('.ship_ts_ptr_B_HI')
    for angle in range(NUM_ANGLES):
        entries = []
        for pc in range(4):
            _, label_b = ship_labels[angle][pc]
            entries.append(f'HI({label_b})')
        lines.append(f'        EQUB    {",".join(entries)}')
    total_bytes += 128

    # Shield pointer tables (4 entries each)
    lines.append('')
    lines.append('.shield_ts_ptr_A_LO')
    lines.append('        EQUB    ' + ','.join(f'LO({shield_labels[pc][0]})' for pc in range(4)))
    lines.append('.shield_ts_ptr_A_HI')
    lines.append('        EQUB    ' + ','.join(f'HI({shield_labels[pc][0]})' for pc in range(4)))
    lines.append('.shield_ts_ptr_B_LO')
    lines.append('        EQUB    ' + ','.join(f'LO({shield_labels[pc][1]})' for pc in range(4)))
    lines.append('.shield_ts_ptr_B_HI')
    lines.append('        EQUB    ' + ','.join(f'HI({shield_labels[pc][1]})' for pc in range(4)))
    total_bytes += 16

    # Pod pointer tables (4 entries each)
    lines.append('')
    lines.append('.pod_ts_ptr_A_LO')
    lines.append('        EQUB    ' + ','.join(f'LO({pod_labels[pc][0]})' for pc in range(4)))
    lines.append('.pod_ts_ptr_A_HI')
    lines.append('        EQUB    ' + ','.join(f'HI({pod_labels[pc][0]})' for pc in range(4)))
    lines.append('.pod_ts_ptr_B_LO')
    lines.append('        EQUB    ' + ','.join(f'LO({pod_labels[pc][1]})' for pc in range(4)))
    lines.append('.pod_ts_ptr_B_HI')
    lines.append('        EQUB    ' + ','.join(f'HI({pod_labels[pc][1]})' for pc in range(4)))
    total_bytes += 16

    # Temp variable for collision mask (absolute address, not ZP)
    lines.append('')
    lines.append('.ship_ts_mask_temp')
    lines.append('        EQUB    $00')
    total_bytes += 1

    lines.append('')
    lines.append(f'; Total data size: {total_bytes} bytes (${total_bytes:04X})')

    return '\n'.join(lines), total_bytes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate two-stream ship sprite data")
    parser.add_argument("--source", default="thrust.6502", help="Source file")
    parser.add_argument("--out", default="tools/output/ship_twostream_data.asm", help="Output file")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    source_path = os.path.join(repo_root, args.source)
    out_path = os.path.join(repo_root, args.out)

    print(f"Reading source: {source_path}")
    source = parse_source(source_path)

    # Extract all ship sprite data (17 frames, indices 0-16)
    print("Extracting ship sprites...")
    ship_sprites = []
    for i in range(NUM_SHIP_SPRITES):
        label = f'ship_sprite_{i}_data'
        data = extract_label_data(source, label)
        ship_sprites.append(data)
        print(f'  sprite {i}: {len(data)} bytes')

    # Extract shield sprite
    print("Extracting shield sprite...")
    shield_data = extract_label_data(source, 'sheild_sprite_data')
    print(f'  shield: {len(shield_data)} bytes')

    # Extract pod sprite
    print("Extracting pod sprite...")
    pod_data = extract_label_data(source, 'pod_sprite_data')
    print(f'  pod: {len(pod_data)} bytes')

    # Generate assembly output
    print("Generating two-stream data...")
    asm_content, total_bytes = generate_asm(ship_sprites, shield_data, pod_data, source_path)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        f.write(asm_content)
        f.write('\n')

    print(f"\nOutput: {out_path}")
    print(f"Total data size: {total_bytes} bytes (${total_bytes:04X})")
    print(f"  Ship: 128 variants (32 angles x 4 pixel columns)")
    print(f"  Shield: 4 variants")
    print(f"  Pod: 4 variants")
    print(f"  Pointer tables: {128*4 + 16 + 16} bytes")


if __name__ == "__main__":
    main()
