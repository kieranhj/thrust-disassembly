# Known issues

Open defects in Thrust Next. Feature work lives in [ideas.md](ideas.md); the plan in [../PLAN.md](../PLAN.md). Fixed items are removed; their commits say what changed.

## Possible bugs

### `_FAST_SPRITES` mirrored angles may be one pixel left

The original decode (`plot_ship_write_opcode`) does `SEC`, then `EOR #$1F`, then `ADC plot_ship_pixel_column`, so mirrored angles (17-31) get +1. `tools/generate_ship_streams.py` computes `(raw ^ 0x1F) + pixel_column` with no +1. With `_FAST_SPRITES` on, mirrored frames would be drawn one pixel left of the original. Not checked in an emulator. Moot if `_FAST_SPRITES` is deleted (PLAN.md, decisions).

## Minor

- `generate_ship_streams.py` also generates pod streams that nothing uses.
- `sprite_editor.py` still creates `Tk()` at import time, so it can't be imported headless.
