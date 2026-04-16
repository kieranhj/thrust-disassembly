"""One-off: seed tools/output/object_sprites.asm from thrust.6502 inline data.

Run once when introducing the external sprite file. Afterwards the sprite
editor owns this file.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from sprite_codec import (
    load_sprites_from_file,
    write_object_sprites_asm,
)

REPO = os.path.dirname(HERE)
SRC = os.path.join(REPO, 'thrust.6502')
OUT = os.path.join(REPO, 'tools', 'output', 'object_sprites.asm')


def main():
    sprites = load_sprites_from_file(SRC)
    write_object_sprites_asm(sprites, OUT)
    print(f'Wrote {OUT}')
    for name, spr in sprites.items():
        print(f'  {name}: {spr.width_px}x{spr.height}')


if __name__ == '__main__':
    main()
