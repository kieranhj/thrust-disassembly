"""Rip all sprites from Thrust (BBC Micro) source as PNGs.

Reads sprite data from thrust.6502 and renders each sprite to a transparent PNG.
Also generates a combined sprite sheet.

Sprite types:
  - Ship: 17 rotation frames (single-stream, per-pixel wireframe, colour 3)
  - Shield: 1 frame (single-stream, per-pixel wireframe, colour 1)
  - Pod: 1 frame (single-stream, per-pixel wireframe, colour 3)
  - Objects: 9 types (two-stream, full-byte patterns, multi-colour)

Usage:
    python tools/rip_sprites.py [--scale N] [--out DIR]
"""

import argparse
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

# BBC Micro Mode 1 logical colour palette (default game palette)
# Logical colour -> RGBA
MODE1_PALETTE = {
    0: (0, 0, 0, 0),         # Black (transparent)
    1: (255, 0, 0, 255),     # Red
    2: (255, 255, 0, 255),   # Yellow
    3: (255, 255, 255, 255), # White
}


# ---------------------------------------------------------------------------
# Source parsing
# ---------------------------------------------------------------------------

def parse_source(path):
    """Read thrust.6502 and return full text."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_label_data(source, label):
    """Extract byte data following a .label line until the next label or blank line.

    Returns a list of ints.
    """
    # Find the label definition
    pattern = re.compile(r'^\.' + re.escape(label) + r'\b', re.MULTILINE)
    m = pattern.search(source)
    if not m:
        raise ValueError(f"Label '{label}' not found in source")

    # Collect EQUB lines after the label
    data = []
    pos = m.end()
    for line in source[pos:].split('\n'):
        line = line.strip()
        # Skip the label line itself if we're still on it
        if not line:
            continue
        # Stop at next label or non-EQUB line
        if line.startswith('.') or (not line.startswith('EQUB') and not line.startswith('\\') and data):
            break
        if line.startswith('EQUB'):
            # Parse hex values from EQUB line, strip comments
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
# Ship / Pod / Shield sprite decoding (single-stream format)
# ---------------------------------------------------------------------------

def decode_single_stream_sprite(data):
    """Decode a single-stream sprite (ship, pod, shield).

    Returns list of (x, y) pixel positions.
    """
    pixels = []
    row = 0
    i = 0

    while i < len(data):
        byte = data[i]

        if byte == 0xFF:
            break

        if byte >= 0x80:
            # Row advance marker
            row += 1
            # Re-read the same byte as pixel data (if not $80 = empty row)
            if byte != 0x80:
                x = pixel_x_from_byte(byte)
                pixels.append((x, row))
            i += 1
        else:
            # Pixel data
            x = pixel_x_from_byte(byte)
            pixels.append((x, row))
            i += 1

    return pixels


def pixel_x_from_byte(byte):
    """Convert a sprite data byte to pixel X position.

    bits 5-2 = character column (each char = 4 pixels wide)
    bits 1-0 = pixel within character byte
    bit 7 is ignored (masked out by AND #$3C / AND #$03)
    """
    char_col = (byte & 0x3C) >> 2
    pixel_in_char = byte & 0x03
    return char_col * 4 + pixel_in_char


def render_single_stream(pixels, colour=3):
    """Render single-stream sprite pixels to an Image.

    Returns (image, origin_x, origin_y) where origin is the min pixel coord.
    """
    if not pixels:
        return Image.new('RGBA', (1, 1), (0, 0, 0, 0)), 0, 0

    min_x = min(p[0] for p in pixels)
    max_x = max(p[0] for p in pixels)
    min_y = min(p[1] for p in pixels)
    max_y = max(p[1] for p in pixels)

    w = max_x - min_x + 1
    h = max_y - min_y + 1

    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    rgba = MODE1_PALETTE[colour]
    for x, y in pixels:
        img.putpixel((x - min_x, y - min_y), rgba)

    return img, min_x, min_y


# ---------------------------------------------------------------------------
# Object sprite decoding (two-stream format)
# ---------------------------------------------------------------------------

def decode_mode1_byte(byte):
    """Decode a MODE 1 screen byte into 4 pixels (logical colours 0-3).

    Bit layout per pixel:
      pixel 0: high=bit7, low=bit3
      pixel 1: high=bit6, low=bit2
      pixel 2: high=bit5, low=bit1
      pixel 3: high=bit4, low=bit0
    """
    pixels = []
    for p in range(4):
        high_bit = (byte >> (7 - p)) & 1
        low_bit = (byte >> (3 - p)) & 1
        pixels.append((high_bit << 1) | low_bit)
    return pixels


def decode_two_stream_sprite(stream_a, stream_b):
    """Decode a two-stream object sprite.

    stream_a: offset/control bytes
    stream_b: MODE 1 screen bytes (4 pixels each)

    Returns list of (char_col, pixel_row, screen_byte) tuples,
    where pixel_row is the absolute pixel row from the top.
    """
    entries = []
    pixel_row = -1  # will be incremented on first row advance or start
    row_in_cell = 0
    b_idx = 0
    first = True

    for a_byte in stream_a:
        if a_byte == 0xFF:
            break

        if a_byte & 0x80:
            # Row advance
            pixel_row += 1
            y_offset = a_byte & 0x7F
            char_col = y_offset >> 3
            # pixel_row_in_cell = y_offset & 0x07  # not needed, ptr tracks row
            entries.append((char_col, pixel_row, stream_b[b_idx]))
            b_idx += 1
        else:
            char_col = a_byte >> 3
            entries.append((char_col, pixel_row, stream_b[b_idx]))
            b_idx += 1

    return entries


def render_two_stream(entries):
    """Render two-stream sprite entries to an Image.

    Returns (image, origin_x, origin_y).
    """
    if not entries:
        return Image.new('RGBA', (1, 1), (0, 0, 0, 0)), 0, 0

    # Convert entries to pixels
    pixels = []  # (x, y, colour)
    for char_col, pixel_row, screen_byte in entries:
        pix4 = decode_mode1_byte(screen_byte)
        for p_idx, colour in enumerate(pix4):
            if colour != 0:  # skip black/transparent
                x = char_col * 4 + p_idx
                pixels.append((x, pixel_row, colour))

    if not pixels:
        return Image.new('RGBA', (1, 1), (0, 0, 0, 0)), 0, 0

    min_x = min(p[0] for p in pixels)
    max_x = max(p[0] for p in pixels)
    min_y = min(p[1] for p in pixels)
    max_y = max(p[1] for p in pixels)

    w = max_x - min_x + 1
    h = max_y - min_y + 1

    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    for x, y, colour in pixels:
        img.putpixel((x - min_x, y - min_y), MODE1_PALETTE[colour])

    return img, min_x, min_y


# ---------------------------------------------------------------------------
# Sprite sheet generation
# ---------------------------------------------------------------------------

def create_sprite_sheet(sprites, scale=4, padding=4, bg_colour=(32, 32, 32, 255)):
    """Create a labelled sprite sheet from a list of (name, image) tuples."""
    if not sprites:
        return Image.new('RGBA', (1, 1))

    # Scale all sprites
    scaled = []
    for name, img in sprites:
        sw = img.width * scale
        sh = img.height * scale
        s = img.resize((sw, sh), Image.NEAREST)
        scaled.append((name, s))

    # Layout: fixed columns for ship rotation, then other sprites below
    # Simple approach: arrange in rows with max width
    max_row_width = 800
    rows = []
    current_row = []
    current_width = padding

    for name, img in scaled:
        entry_width = img.width + padding
        if current_width + entry_width > max_row_width and current_row:
            rows.append(current_row)
            current_row = []
            current_width = padding
        current_row.append((name, img))
        current_width += entry_width

    if current_row:
        rows.append(current_row)

    # Calculate sheet dimensions
    label_height = 16
    row_heights = []
    total_width = max_row_width
    total_height = padding

    for row in rows:
        rh = max(img.height for _, img in row) + label_height + padding
        row_heights.append(rh)
        total_height += rh

    sheet = Image.new('RGBA', (total_width, total_height), bg_colour)
    draw = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.truetype("arial.ttf", 11)
    except (OSError, IOError):
        font = ImageFont.load_default()

    y_pos = padding
    for row, rh in zip(rows, row_heights):
        x_pos = padding
        for name, img in row:
            # Draw label
            draw.text((x_pos, y_pos), name, fill=(200, 200, 200, 255), font=font)
            # Paste sprite
            sheet.paste(img, (x_pos, y_pos + label_height), img)
            x_pos += img.width + padding
        y_pos += rh

    return sheet


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Rip sprites from Thrust (BBC Micro)")
    parser.add_argument("--scale", type=int, default=4, help="Scale factor for sprite sheet (default: 4)")
    parser.add_argument("--out", default="tools/sprites", help="Output directory (default: tools/sprites)")
    parser.add_argument("--source", default="thrust.6502", help="Source file (default: thrust.6502)")
    args = parser.parse_args()

    # Resolve paths relative to repo root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    source_path = os.path.join(repo_root, args.source)
    out_dir = os.path.join(repo_root, args.out)

    os.makedirs(out_dir, exist_ok=True)

    print(f"Reading source: {source_path}")
    source = parse_source(source_path)

    all_sprites = []  # (name, image) for sprite sheet

    # --- Ship sprites (17 rotation frames) ---
    print("Decoding ship sprites...")
    for i in range(17):
        label = f"ship_sprite_{i}_data"
        data = extract_label_data(source, label)
        pixels = decode_single_stream_sprite(data)
        img, ox, oy = render_single_stream(pixels, colour=3)
        name = f"ship_{i:02d}"
        img.save(os.path.join(out_dir, f"{name}.png"))
        all_sprites.append((name, img))
        print(f"  {name}: {img.width}x{img.height} ({len(pixels)} pixels)")

    # --- Shield sprite ---
    print("Decoding shield sprite...")
    data = extract_label_data(source, "sheild_sprite_data")
    pixels = decode_single_stream_sprite(data)
    img, ox, oy = render_single_stream(pixels, colour=1)
    img.save(os.path.join(out_dir, "shield.png"))
    all_sprites.append(("shield", img))
    print(f"  shield: {img.width}x{img.height} ({len(pixels)} pixels)")

    # --- Pod sprite ---
    print("Decoding pod sprite...")
    data = extract_label_data(source, "pod_sprite_data")
    pixels = decode_single_stream_sprite(data)
    img, ox, oy = render_single_stream(pixels, colour=3)
    img.save(os.path.join(out_dir, "pod.png"))
    all_sprites.append(("pod", img))
    print(f"  pod: {img.width}x{img.height} ({len(pixels)} pixels)")

    # --- Object sprites (9 types, two-stream) ---
    object_names = [
        "gun_up_right",
        "gun_down_right",
        "gun_up_left",
        "gun_down_left",
        "fuel",
        "pod_stand",
        "generator",
        "door_switch_right",
        "door_switch_left",
    ]

    print("Decoding object sprites...")
    for obj_name in object_names:
        label_a = f"obj_sprite_data_A_{obj_name}"
        label_b = f"obj_sprite_data_B_{obj_name}"
        stream_a = extract_label_data(source, label_a)
        stream_b = extract_label_data(source, label_b)
        entries = decode_two_stream_sprite(stream_a, stream_b)
        img, ox, oy = render_two_stream(entries)
        img.save(os.path.join(out_dir, f"{obj_name}.png"))
        all_sprites.append((obj_name, img))
        print(f"  {obj_name}: {img.width}x{img.height} ({len(entries)} byte-plots)")

    # --- Sprite sheet ---
    print(f"\nGenerating sprite sheet (scale={args.scale})...")
    sheet = create_sprite_sheet(all_sprites, scale=args.scale)
    sheet_path = os.path.join(out_dir, "sprite_sheet.png")
    sheet.save(sheet_path)
    print(f"Sprite sheet saved: {sheet_path} ({sheet.width}x{sheet.height})")

    print(f"\nDone! {len(all_sprites)} sprites saved to {out_dir}/")


if __name__ == "__main__":
    main()
