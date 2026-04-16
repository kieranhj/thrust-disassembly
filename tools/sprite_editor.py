#!/usr/bin/env python3
"""Object sprite editor for Thrust (BBC Micro).

Edits the 9 object sprites (gun, fuel, generator, door switches, pod stand)
stored in the two-stream format. Reads and writes
tools/output/object_sprites.asm, which is included in _SWRAM_BUILD only.

Usage:
    python tools/sprite_editor.py

Palette (Mode 1 logical colours):
    0               Transparent (background, fixed black)
    1               Ship (always yellow, fixed)
    2               Landscape (configurable — cycle BBC physical colour)
    3               Object (configurable — cycle BBC physical colour)

Controls:
    Left-click      Paint with current colour (click sidebar to pick sprite,
                    click swatch to select, click Land/Obj to cycle colour)
    Right-click     Erase (colour 0)
    0-3             Select palette colour
    F               Flood fill
    C               Clear current sprite
    Ctrl+Z          Undo
    Ctrl+Shift+Z    Redo
    Ctrl+S          Export to .asm (via save-as dialog) + regenerate PNGs
    Ctrl+I          Import from .asm (via open dialog)
    Tab / Shift+Tab Next / previous sprite
    Escape          Quit

Requires: pygame (pip install pygame), PIL (pip install pillow)
"""
import copy
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import pygame

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from sprite_codec import (
    OBJECT_NAMES,
    OBJECT_WIDTH_CHARS,
    BBC_COLOURS,
    BBC_COLOUR_NAMES,
    LEVEL_LANDSCAPE_COLOUR,
    LEVEL_OBJECT_COLOUR,
    Sprite,
    load_sprites_from_file,
    make_logical_palette,
    write_object_sprites_asm,
)


REPO = HERE.parent
THRUST_SRC = REPO / 'thrust.6502'
DEFAULT_EXPORT_FILE = REPO / 'tools' / 'output' / 'object_sprites.asm'
OBJ_SPRITE_DATA_FILE = REPO / 'obj_sprite_data.6502'  # non-SWRAM inline copy
SPRITES_DIR = REPO / 'tools' / 'sprites'

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

WINDOW_W, WINDOW_H = 1280, 800
TOOLBAR_H = 40
STATUS_H = 28
SIDEBAR_W = 220

CANVAS_X = SIDEBAR_W
CANVAS_Y = TOOLBAR_H
CANVAS_W = WINDOW_W - SIDEBAR_W
CANVAS_H = WINDOW_H - TOOLBAR_H - STATUS_H

FPS = 60

# Colours (editor chrome)
COL_BG = (16, 16, 20)
COL_TOOLBAR = (32, 32, 40)
COL_SIDEBAR = (24, 24, 32)
COL_STATUS = (32, 32, 40)
COL_TEXT = (220, 220, 220)
COL_TEXT_DIM = (140, 140, 150)
COL_SEL = (70, 100, 160)
COL_GRID = (60, 60, 70)
COL_CHAR_GRID = (90, 90, 110)
COL_TRANSPARENT_DARK = (30, 30, 34)  # canvas background
COL_TRANSPARENT_LIGHT = (40, 40, 44)  # checkerboard


# ---------------------------------------------------------------------------
# Editor state
# ---------------------------------------------------------------------------

class Editor:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Thrust sprite editor")
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 14)
        self.font_small = pygame.font.SysFont("consolas", 12)
        self.font_big = pygame.font.SysFont("consolas", 18, bold=True)

        # Prefer the external export file if it exists; otherwise try the
        # extracted inline file, then fall back to thrust.6502 itself.
        candidates = [DEFAULT_EXPORT_FILE, OBJ_SPRITE_DATA_FILE, THRUST_SRC]
        source_path = next((p for p in candidates if p.exists()), candidates[0])
        self.sprites = load_sprites_from_file(str(source_path))
        # Remember the export destination — but never let it default to
        # thrust.6502 (don't want Ctrl+S to overwrite it). If we bootstrapped
        # from thrust.6502, the save dialog defaults to DEFAULT_EXPORT_FILE.
        if source_path == THRUST_SRC:
            self.last_file_path = str(DEFAULT_EXPORT_FILE)
        else:
            self.last_file_path = str(source_path)
        self.source_label = f"loaded: {source_path.relative_to(REPO)}"

        self.selected = OBJECT_NAMES[0]
        self.palette_idx = 3  # start on "object" colour
        # Preview palette — logical colours 0 and 1 are fixed; 2/3 cycle
        # through BBC physical colours 1-7 (black excluded).
        self.landscape_phys = LEVEL_LANDSCAPE_COLOUR[0]
        self.object_phys = LEVEL_OBJECT_COLOUR[0]
        self.painting_colour = None  # not None while mouse button held
        self.status_msg = self.source_label
        self.dirty = False

        # Hit-regions that toolbar event handling needs to consult. Recomputed
        # each frame.
        self._swatch_rects = []   # list of (rect, palette_idx)
        self._land_rect = None    # rect around Land swatch
        self._obj_rect = None     # rect around Obj swatch
        self._import_rect = None  # rect around Import button
        self._export_rect = None  # rect around Export button

        # Undo stack: list of (sprite_name, snapshot_of_pixels)
        self.undo_stack = []
        self.redo_stack = []

        self._recompute_canvas()

    # ------------------------------------------------------------------
    # Palette
    # ------------------------------------------------------------------

    def palette_rgb(self):
        """Current logical palette as {idx: (R,G,B)} (colour 0 is special)."""
        rgba = make_logical_palette(self.landscape_phys, self.object_phys)
        return {k: v[:3] for k, v in rgba.items()}

    def palette_rgba(self):
        return make_logical_palette(self.landscape_phys, self.object_phys)

    def cycle_landscape(self, step=1):
        # Cycle 1-7 (skip black), matching level editor behaviour.
        self.landscape_phys = ((self.landscape_phys - 1 + step) % 7) + 1

    def cycle_object(self, step=1):
        self.object_phys = ((self.object_phys - 1 + step) % 7) + 1

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _recompute_canvas(self):
        spr = self.sprites[self.selected]
        # Pick a zoom that fits the canvas area with margin.
        margin = 40
        avail_w = CANVAS_W - margin
        avail_h = CANVAS_H - margin
        # We want square pixels on screen for clarity.
        zoom_w = avail_w // max(spr.width_px, 1)
        zoom_h = avail_h // max(spr.height, 1)
        self.zoom = max(4, min(32, min(zoom_w, zoom_h)))
        grid_w = spr.width_px * self.zoom
        grid_h = spr.height * self.zoom
        self.grid_rect = pygame.Rect(
            CANVAS_X + (CANVAS_W - grid_w) // 2,
            CANVAS_Y + (CANVAS_H - grid_h) // 2,
            grid_w, grid_h,
        )

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------

    def _snapshot(self):
        spr = self.sprites[self.selected]
        return (self.selected, copy.deepcopy(spr.pixels))

    def push_undo(self):
        self.undo_stack.append(self._snapshot())
        # Cap depth so memory doesn't balloon.
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self._snapshot())
        name, pixels = self.undo_stack.pop()
        self.selected = name
        self.sprites[name].pixels = pixels
        self.dirty = True
        self._recompute_canvas()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self._snapshot())
        name, pixels = self.redo_stack.pop()
        self.selected = name
        self.sprites[name].pixels = pixels
        self.dirty = True
        self._recompute_canvas()

    # ------------------------------------------------------------------
    # Edit operations
    # ------------------------------------------------------------------

    def pixel_at(self, x: int, y: int):
        spr = self.sprites[self.selected]
        if 0 <= x < spr.width_px and 0 <= y < spr.height:
            return spr.pixels[y][x]
        return None

    def paint_pixel(self, x: int, y: int, colour: int):
        spr = self.sprites[self.selected]
        if 0 <= x < spr.width_px and 0 <= y < spr.height:
            if spr.pixels[y][x] != colour:
                spr.pixels[y][x] = colour
                self.dirty = True

    def flood_fill(self, x: int, y: int, colour: int):
        spr = self.sprites[self.selected]
        if not (0 <= x < spr.width_px and 0 <= y < spr.height):
            return
        target = spr.pixels[y][x]
        if target == colour:
            return
        self.push_undo()
        stack = [(x, y)]
        seen = set()
        while stack:
            px, py = stack.pop()
            if (px, py) in seen:
                continue
            seen.add((px, py))
            if not (0 <= px < spr.width_px and 0 <= py < spr.height):
                continue
            if spr.pixels[py][px] != target:
                continue
            spr.pixels[py][px] = colour
            stack.extend([(px + 1, py), (px - 1, py),
                          (px, py + 1), (px, py - 1)])
        self.dirty = True

    def clear_sprite(self):
        self.push_undo()
        spr = self.sprites[self.selected]
        for row in spr.pixels:
            for i in range(len(row)):
                row[i] = 0
        self.dirty = True

    # ------------------------------------------------------------------
    # Import / export (file dialogs, match level_editor.py pattern)
    # ------------------------------------------------------------------

    def _drain_input_events(self):
        """Clear buffered pygame input events after a modal tk dialog so that
        clicks/keys the user mashed while the dialog was up don't re-trigger
        the button we just returned from (stacking dialogs).
        """
        pygame.event.clear(pygame.MOUSEBUTTONDOWN)
        pygame.event.clear(pygame.MOUSEBUTTONUP)
        pygame.event.clear(pygame.KEYDOWN)

    def _save_to_file(self, path):
        """Write sprite + PNG data to the given path. No dialog, no prompts."""
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            write_object_sprites_asm(self.sprites, path)
            self._export_pngs()
            self.last_file_path = str(Path(path).resolve())
            self.dirty = False
            rel = self._relpath(path)
            self.status_msg = f"Saved to {rel} + PNGs"
        except Exception as exc:
            self.status_msg = f"Save FAILED: {exc}"

    def _quick_save(self):
        """Ctrl+S: save over the current file without a dialog. Falls back
        to _export() if no file has been loaded/saved yet.
        """
        if self.last_file_path:
            self._save_to_file(self.last_file_path)
        else:
            self._export()

    def _confirm_exit(self):
        """Prompt the user if there are unsaved sprite changes.
        Returns True if exit should proceed, False to cancel.
        """
        if not self.dirty:
            return True
        root = tk.Tk()
        root.withdraw()
        result = messagebox.askyesnocancel(
            "Unsaved changes",
            "Sprite data has unsaved changes.\n\n"
            "Yes = save and exit\n"
            "No = exit without saving\n"
            "Cancel = stay in editor",
        )
        root.destroy(); self._drain_input_events()
        if result is None:
            return False
        if result:
            self._quick_save()
            if self.dirty:
                return False
        return True

    def _export(self):
        """Export via file dialog (OS will prompt on overwrite)."""
        default_path = Path(self.last_file_path) if self.last_file_path \
            else DEFAULT_EXPORT_FILE
        root = tk.Tk()
        root.withdraw()
        path = filedialog.asksaveasfilename(
            title="Export object sprite data",
            initialdir=str(default_path.parent),
            initialfile=default_path.name,
            defaultextension=".asm",
            filetypes=[("BeebAsm assembly", "*.asm *.6502"),
                       ("All files", "*.*")],
        )
        root.destroy(); self._drain_input_events()
        if not path:
            return
        self._save_to_file(path)

    def _import(self):
        default_path = Path(self.last_file_path) if self.last_file_path \
            else DEFAULT_EXPORT_FILE
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="Import object sprite data",
            initialdir=str(default_path.parent),
            defaultextension=".asm",
            filetypes=[("BeebAsm assembly", "*.asm *.6502"),
                       ("All files", "*.*")],
        )
        root.destroy(); self._drain_input_events()
        if not path:
            return
        try:
            self.sprites = load_sprites_from_file(path)
            self.last_file_path = str(Path(path).resolve())
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.dirty = False
            self._recompute_canvas()
            rel = self._relpath(path)
            self.status_msg = f"Imported from {rel}"
        except Exception as exc:
            self.status_msg = f"Import FAILED: {exc}"

    def _relpath(self, path):
        try:
            return str(Path(path).resolve().relative_to(REPO))
        except ValueError:
            return path

    def _export_pngs(self):
        # Lazy import — only needed on save.
        from PIL import Image
        SPRITES_DIR.mkdir(parents=True, exist_ok=True)
        palette = self.palette_rgba()
        for name, spr in self.sprites.items():
            if spr.height == 0 or spr.width_px == 0:
                continue
            img = Image.new('RGBA', (spr.width_px, spr.height), (0, 0, 0, 0))
            for y, row in enumerate(spr.pixels):
                for x, col in enumerate(row):
                    if col != 0:
                        img.putpixel((x, y), palette[col])
            img.save(str(SPRITES_DIR / f"{name}.png"))

    # ------------------------------------------------------------------
    # Coordinate conversion
    # ------------------------------------------------------------------

    def screen_to_pixel(self, mx: int, my: int):
        if not self.grid_rect.collidepoint(mx, my):
            return None
        px = (mx - self.grid_rect.x) // self.zoom
        py = (my - self.grid_rect.y) // self.zoom
        return int(px), int(py)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def draw(self):
        self.screen.fill(COL_BG)
        self._draw_sidebar()
        self._draw_toolbar()
        self._draw_canvas()
        self._draw_status()
        pygame.display.flip()

    def _draw_sidebar(self):
        pygame.draw.rect(self.screen, COL_SIDEBAR,
                         (0, 0, SIDEBAR_W, WINDOW_H))
        title = self.font_big.render("Objects", True, COL_TEXT)
        self.screen.blit(title, (12, 8))

        palette = self.palette_rgb()
        y = 40
        for name in OBJECT_NAMES:
            spr = self.sprites[name]
            row_h = 52
            row_rect = pygame.Rect(4, y, SIDEBAR_W - 8, row_h)
            if name == self.selected:
                pygame.draw.rect(self.screen, COL_SEL, row_rect, border_radius=3)
            # Thumbnail at fixed scale
            thumb_zoom = 2
            tw = spr.width_px * thumb_zoom
            th = spr.height * thumb_zoom
            thumb_x = row_rect.x + 8
            thumb_y = row_rect.y + (row_h - th) // 2
            pygame.draw.rect(self.screen, COL_TRANSPARENT_DARK,
                             (thumb_x, thumb_y, tw, th))
            for py, pixrow in enumerate(spr.pixels):
                for px, col in enumerate(pixrow):
                    if col != 0:
                        pygame.draw.rect(self.screen, palette[col],
                                         (thumb_x + px * thumb_zoom,
                                          thumb_y + py * thumb_zoom,
                                          thumb_zoom, thumb_zoom))
            label = self.font.render(name, True, COL_TEXT)
            self.screen.blit(label, (thumb_x + tw + 10,
                                     row_rect.y + 4))
            dim = self.font_small.render(
                f"{spr.width_px}x{spr.height}", True, COL_TEXT_DIM)
            self.screen.blit(dim, (thumb_x + tw + 10,
                                   row_rect.y + row_h - 16))
            y += row_h + 2

    def _draw_toolbar(self):
        pygame.draw.rect(self.screen, COL_TOOLBAR,
                         (SIDEBAR_W, 0, WINDOW_W - SIDEBAR_W, TOOLBAR_H))
        spr = self.sprites[self.selected]
        title = self.font_big.render(
            f"{self.selected}  {spr.width_px}x{spr.height}  "
            f"({spr.width_chars} char cols)",
            True, COL_TEXT)
        self.screen.blit(title, (SIDEBAR_W + 12, 10))

        palette = self.palette_rgb()
        sw = 28
        pad = 4

        # ---- Import / Export buttons (far right) -----------------------
        btn_w, btn_h = 90, 30
        btn_gap = 10
        export_x = WINDOW_W - btn_w - 8
        import_x = export_x - btn_w - btn_gap
        self._import_rect = pygame.Rect(import_x, 5, btn_w, btn_h)
        self._export_rect = pygame.Rect(export_x, 5, btn_w, btn_h)
        pygame.draw.rect(self.screen, (40, 40, 60), self._import_rect,
                         border_radius=4)
        pygame.draw.rect(self.screen, (80, 80, 80), self._import_rect, 1,
                         border_radius=4)
        itxt = self.font.render("Import", True, (150, 150, 255))
        self.screen.blit(itxt, (self._import_rect.x + 16,
                                self._import_rect.y + 7))
        pygame.draw.rect(self.screen, (40, 60, 40), self._export_rect,
                         border_radius=4)
        pygame.draw.rect(self.screen, (80, 80, 80), self._export_rect, 1,
                         border_radius=4)
        etxt = self.font.render("Export", True, (150, 255, 150))
        self.screen.blit(etxt, (self._export_rect.x + 18,
                                self._export_rect.y + 7))

        # ---- Palette swatches (left of Import button) ------------------
        self._swatch_rects = []
        swatches_w = 4 * (sw + pad) - pad
        swatches_x = import_x - swatches_w - 16
        for idx in range(4):
            r = pygame.Rect(swatches_x + idx * (sw + pad), 6, sw, sw)
            self._swatch_rects.append((r, idx))
            colour = palette[idx]
            if idx == 0:
                pygame.draw.rect(self.screen, COL_TRANSPARENT_DARK, r)
                half = sw // 2
                pygame.draw.rect(self.screen, COL_TRANSPARENT_LIGHT,
                                 (r.x, r.y, half, half))
                pygame.draw.rect(self.screen, COL_TRANSPARENT_LIGHT,
                                 (r.x + half, r.y + half, half, half))
            else:
                pygame.draw.rect(self.screen, colour, r)
            # Lock icon on colour 1 (fixed yellow) to hint it is not a
            # configurable physical colour.
            if idx == 1:
                lock = self.font_small.render("[YELLOW]", True, (0, 0, 0))
                self.screen.blit(lock, (r.x + 1, r.y + sw + 2))
            else:
                num = self.font_small.render(str(idx), True, COL_TEXT_DIM)
                self.screen.blit(num, (r.x + 2, r.y + sw + 2))
            if idx == self.palette_idx:
                pygame.draw.rect(self.screen, (255, 255, 255), r, 2)

        # ---- Landscape / Object colour cyclers (middle of toolbar) ------
        # Reserve the widest possible name width so positions don't shift
        # as the user cycles through colours.
        name_w = max(self.font.size(n)[0] for n in BBC_COLOUR_NAMES.values())
        label_w = max(self.font.size(s)[0] for s in ("Land:", "Obj:"))
        sw_small = 20
        gap = 6
        ctrl_w = label_w + gap + sw_small + gap + name_w
        group_gap = 16
        group_w = 2 * ctrl_w + group_gap
        gx = swatches_x - 16 - group_w

        def draw_colour_ctrl(x, label, phys_col):
            label_surf = self.font.render(label, True, COL_TEXT_DIM)
            self.screen.blit(label_surf, (x, 12))
            sx = x + label_w + gap
            srect = pygame.Rect(sx, 10, sw_small, sw_small)
            pygame.draw.rect(self.screen, BBC_COLOURS[phys_col], srect)
            pygame.draw.rect(self.screen, COL_TEXT, srect, 1)
            nx = sx + sw_small + gap
            nsurf = self.font.render(BBC_COLOUR_NAMES[phys_col], True, COL_TEXT)
            self.screen.blit(nsurf, (nx, 12))
            return srect

        self._land_rect = draw_colour_ctrl(gx, "Land:", self.landscape_phys)
        self._obj_rect = draw_colour_ctrl(gx + ctrl_w + group_gap, "Obj:",
                                          self.object_phys)

    def _draw_canvas(self):
        spr = self.sprites[self.selected]
        # Checkerboard background to show transparency.
        tile = 8
        for ty in range(0, self.grid_rect.h, tile):
            for tx in range(0, self.grid_rect.w, tile):
                col = COL_TRANSPARENT_LIGHT if ((tx // tile + ty // tile) & 1) \
                    else COL_TRANSPARENT_DARK
                pygame.draw.rect(self.screen, col,
                                 (self.grid_rect.x + tx,
                                  self.grid_rect.y + ty,
                                  min(tile, self.grid_rect.w - tx),
                                  min(tile, self.grid_rect.h - ty)))

        # Pixels.
        palette = self.palette_rgb()
        for y, row in enumerate(spr.pixels):
            for x, col in enumerate(row):
                if col == 0:
                    continue
                pygame.draw.rect(
                    self.screen, palette[col],
                    (self.grid_rect.x + x * self.zoom,
                     self.grid_rect.y + y * self.zoom,
                     self.zoom, self.zoom))

        # Pixel grid.
        if self.zoom >= 8:
            for x in range(spr.width_px + 1):
                xs = self.grid_rect.x + x * self.zoom
                pygame.draw.line(self.screen, COL_GRID,
                                 (xs, self.grid_rect.y),
                                 (xs, self.grid_rect.bottom))
            for y in range(spr.height + 1):
                ys = self.grid_rect.y + y * self.zoom
                pygame.draw.line(self.screen, COL_GRID,
                                 (self.grid_rect.x, ys),
                                 (self.grid_rect.right, ys))

        # Char-column divides (every 4 pixels).
        for cc in range(spr.width_chars + 1):
            xs = self.grid_rect.x + cc * 4 * self.zoom
            pygame.draw.line(self.screen, COL_CHAR_GRID,
                             (xs, self.grid_rect.y),
                             (xs, self.grid_rect.bottom), 2)

        # Outer border.
        pygame.draw.rect(self.screen, COL_CHAR_GRID, self.grid_rect, 2)

    def _draw_status(self):
        pygame.draw.rect(self.screen, COL_STATUS,
                         (0, WINDOW_H - STATUS_H, WINDOW_W, STATUS_H))
        spr = self.sprites[self.selected]
        # Compute current byte usage vs original.
        from sprite_codec import assembled_bytes
        sa, sb = assembled_bytes(spr)
        orig_a = len(spr.orig_stream_a)
        orig_b = len(spr.orig_stream_b)
        delta_a = len(sa) - orig_a
        delta_b = len(sb) - orig_b

        def sign(n):
            return f"+{n}" if n > 0 else str(n)

        # Draw the mouse coord on the far right first so we can reserve a
        # gap and keep the main status text from running into it.
        coord_w = 140
        mx, my = pygame.mouse.get_pos()
        pixel = self.screen_to_pixel(mx, my)
        if pixel:
            px, py = pixel
            coord = self.font.render(
                f"pixel ({px},{py})", True, COL_TEXT_DIM)
            self.screen.blit(coord, (WINDOW_W - coord_w,
                                     WINDOW_H - STATUS_H + 6))

        status = (f"{self.status_msg}  |  "
                  f"streams: A={len(sa)}({sign(delta_a)}) "
                  f"B={len(sb)}({sign(delta_b)})  |  "
                  f"Ctrl+S export, Ctrl+I import, Z undo, F fill, C clear, "
                  f"Tab next, 0-3 colour")
        if self.dirty:
            status = "* " + status
        # Trim if it would overlap the coord area.
        max_status_w = WINDOW_W - coord_w - 16
        while self.font.size(status)[0] > max_status_w and len(status) > 4:
            status = status[:-4] + "..."
        text = self.font.render(status, True, COL_TEXT)
        self.screen.blit(text, (8, WINDOW_H - STATUS_H + 6))

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return not self._confirm_exit()
        if event.type == pygame.KEYDOWN:
            mods = pygame.key.get_mods()
            ctrl = mods & pygame.KMOD_CTRL
            shift = mods & pygame.KMOD_SHIFT
            if event.key == pygame.K_ESCAPE:
                return not self._confirm_exit()
            if ctrl and event.key == pygame.K_s:
                self._quick_save()
                return True
            if ctrl and event.key == pygame.K_i:
                self._import()
                return True
            if ctrl and event.key == pygame.K_z:
                if shift:
                    self.redo()
                else:
                    self.undo()
                return True
            if event.key in (pygame.K_0, pygame.K_1, pygame.K_2, pygame.K_3):
                self.palette_idx = event.key - pygame.K_0
                return True
            if event.key == pygame.K_TAB:
                idx = OBJECT_NAMES.index(self.selected)
                step = -1 if shift else 1
                idx = (idx + step) % len(OBJECT_NAMES)
                self.selected = OBJECT_NAMES[idx]
                self._recompute_canvas()
                return True
            if event.key == pygame.K_f:
                mx, my = pygame.mouse.get_pos()
                p = self.screen_to_pixel(mx, my)
                if p:
                    self.flood_fill(p[0], p[1], self.palette_idx)
                return True
            if event.key == pygame.K_c:
                self.clear_sprite()
                return True

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                mx, my = event.pos
                # Toolbar — Import / Export buttons.
                if self._import_rect and self._import_rect.collidepoint(mx, my):
                    self._import()
                    return True
                if self._export_rect and self._export_rect.collidepoint(mx, my):
                    self._export()
                    return True
                # Toolbar — palette swatches.
                for r, idx in self._swatch_rects:
                    if r.collidepoint(mx, my):
                        self.palette_idx = idx
                        return True
                # Toolbar — landscape / object colour cyclers.
                if self._land_rect and self._land_rect.collidepoint(mx, my):
                    self.cycle_landscape()
                    return True
                if self._obj_rect and self._obj_rect.collidepoint(mx, my):
                    self.cycle_object()
                    return True
                # Sidebar click — switch sprite.
                if mx < SIDEBAR_W and my >= 40:
                    rel_y = my - 40
                    idx = rel_y // 54
                    if 0 <= idx < len(OBJECT_NAMES):
                        self.selected = OBJECT_NAMES[idx]
                        self._recompute_canvas()
                        return True
                p = self.screen_to_pixel(mx, my)
                if p:
                    self.push_undo()
                    self.painting_colour = self.palette_idx
                    self.paint_pixel(p[0], p[1], self.painting_colour)
            elif event.button == 3:
                p = self.screen_to_pixel(*event.pos)
                if p:
                    self.push_undo()
                    self.painting_colour = 0
                    self.paint_pixel(p[0], p[1], 0)
        elif event.type == pygame.MOUSEBUTTONUP:
            self.painting_colour = None
        elif event.type == pygame.MOUSEMOTION and self.painting_colour is not None:
            p = self.screen_to_pixel(*event.pos)
            if p:
                self.paint_pixel(p[0], p[1], self.painting_colour)

        return True

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if not self.handle_event(event):
                    running = False
                    break
            self.draw()
            self.clock.tick(FPS)
        pygame.quit()


def main():
    Editor().run()


if __name__ == '__main__':
    main()
