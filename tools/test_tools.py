#!/usr/bin/env python3
"""Headless tests for the level and sprite tools.

Run from the repo root with either of:

    python -m unittest tools.test_tools
    python tools/test_tools.py

No window is opened: level_editor creates its Tk root and pygame display
only in main() / Editor(), so importing it is safe.
"""

import os
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import engine_consts as ec  # noqa: E402
import level_editor as le  # noqa: E402
import sprite_codec as sc  # noqa: E402
import visualise_levels as vl  # noqa: E402

LEVELS_EXPORT = REPO / "tools" / "output" / "thrust_levels_export2.asm"
LEVELS_ORIGINAL = REPO / "thrust1" / "level_data.asm"
SPRITES_SWRAM = REPO / "tools" / "output" / "object_sprites.asm"
SPRITES_ORIGINAL = REPO / "thrust1" / "obj_sprite_data.asm"

# Door-only fields: from_game_data fills them with 1, the importer with 0.
# Both are ignored for anything that isn't a door.
_DOOR_ONLY_KEYS = ("door_width", "door_max_carve")


def _comparable(level):
    d = dict(vars(level))
    objs = []
    for o in d["objects"]:
        o = dict(o)
        if o["type"] != le.OBJECT_DOOR:
            for k in _DOOR_ONLY_KEYS:
                o.pop(k, None)
        objs.append(o)
    d["objects"] = objs
    return d


class LevelRoundTrip(unittest.TestCase):
    def test_export2_round_trips_byte_for_byte(self):
        """Importing the file the SWRAM build INCLUDEs and exporting it
        again gives the same text."""
        original = LEVELS_EXPORT.read_text()
        exported = le.export_beebasm(le.import_beebasm(LEVELS_EXPORT))
        self.assertEqual(original, exported)

    def test_from_game_data_matches_level_data_asm(self):
        """The editor's built-in copy of the original levels equals the
        level data the original build assembles."""
        imported = le.import_beebasm(LEVELS_ORIGINAL)
        self.assertEqual(len(imported), 6)
        builtin = [le.LevelData.from_game_data(i) for i in range(6)]
        for n in range(6):
            with self.subTest(level=n + 1):
                self.assertEqual(_comparable(builtin[n]), _comparable(imported[n]))
        self.assertEqual(le.export_beebasm(builtin), le.export_beebasm(imported))

    def test_levels_within_object_cap(self):
        levels = le.import_beebasm(LEVELS_EXPORT)
        self.assertEqual(le.object_count_problems(levels), [])
        levels[0].objects.extend([dict(levels[0].objects[-1])] * le.LEVEL_OBJECT_CAP)
        self.assertEqual(len(le.object_count_problems(levels)), 1)


class EngineConsts(unittest.TestCase):
    """Hand-copied object tables in the tools agree with thrust.6502."""

    def test_parsed_values(self):
        self.assertEqual(ec.LEVEL_OBJECT_CAP, 32)
        self.assertEqual(ec.OBJECT_TYPES["gun_up_right"], 0x00)
        self.assertEqual(ec.OBJECT_TYPES["door"], 0x11)
        self.assertEqual(sorted(ec.OBJECT_NAMES), list(range(len(ec.OBJECT_NAMES))))

    def test_editor_type_names_cover_engine_types(self):
        self.assertEqual(sorted(vl.OBJECT_TYPE_NAMES), sorted(ec.OBJECT_NAMES))

    def test_sprite_codec_names_match_engine(self):
        # Every type with a sprite, in type order; the door has none.
        expected = [ec.OBJECT_NAMES[t] for t in sorted(ec.OBJECT_NAMES)
                    if t != ec.OBJECT_TYPES["door"]]
        self.assertEqual(sc.OBJECT_NAMES, expected)


class SpriteCodec(unittest.TestCase):
    def test_mode1_byte_codec(self):
        for b in range(256):
            self.assertEqual(sc.encode_mode1_byte(sc.decode_mode1_byte(b)), b)

    def test_swram_sprites_round_trip(self):
        """Decoding and re-encoding object_sprites.asm reproduces the file."""
        text = SPRITES_SWRAM.read_text()
        sprites = sc.load_sprites_from_source(text)
        for name in sc.OBJECT_NAMES:
            with self.subTest(sprite=name):
                spr = sprites[name]
                self.assertTrue(spr.orig_stream_a, "sprite missing from file")
                self.assertEqual(sc.assembled_bytes(spr),
                                 (spr.orig_stream_a, spr.orig_stream_b))
        self.assertEqual(sc.format_object_sprites_asm(sprites), text)

    def test_original_sprites_round_trip(self):
        """The original game's nine sprites decode and re-encode exactly."""
        sprites = sc.load_sprites_from_file(str(SPRITES_ORIGINAL))
        present = [n for n in sc.OBJECT_NAMES if sprites[n].orig_stream_a]
        self.assertEqual(present, sc.OBJECT_NAMES[:9])
        for name in present:
            with self.subTest(sprite=name):
                spr = sprites[name]
                self.assertEqual(sc.assembled_bytes(spr),
                                 (spr.orig_stream_a, spr.orig_stream_b))


if __name__ == "__main__":
    unittest.main()
