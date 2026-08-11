"""Iconic shop-row emblems for each field, drawn in the game's 8-bit style.

A field is an animated particle backdrop. Scaling the live render down to a
36px shop-row swatch turned its sparse particles into unreadable low-res noise;
a first pass at clean vector icons fixed legibility but read as too smooth and
modern against the pixel-art fields. So each emblem is now a HAND-AUTHORED
PIXEL GLYPH — a small string grid in exactly the idiom `fields.py` already uses
for `_HEART_GLYPH`/`_SKULL_GLYPH` — rendered as scaled-up opaque blocks with no
smoothing, so it sits in the same 8-bit world as the fields it represents.

Each glyph is a tuple of equal-length rows. A `.` is transparent; every other
character indexes that glyph's colour map. `render(id, size)` rasterises the
grid into a `size`x`size` transparent surface by drawing each filled cell as an
integer block of pixels (chunky squares, never anti-aliased).
"""
from __future__ import annotations

import pygame

from . import fields as fieldsmod

# ── Palette (echoing fields.py so an emblem matches its field) ───────────────

_STAR = (219, 226, 245)
_STAR_HI = (255, 255, 255)
_HEART = (255, 120, 150)
_HEART_HI = (255, 175, 195)
_HEART_LO = (230, 80, 110)
_BONE = fieldsmod._BONE
_SOCKET = (45, 45, 48)
_NOSE = fieldsmod._NOSE
_SNOW = (225, 236, 250)
_SNOW_HI = (255, 255, 255)
_FLAME_HOT = fieldsmod._EMBER_HOT
_FLAME_MID = fieldsmod._EMBER_MID
_FLAME_TIP = (255, 214, 110)
_PETAL = (255, 160, 180)
_PETAL_HI = (255, 205, 215)
_PETAL_CORE = (255, 226, 150)
_CLOUD = (150, 164, 190)
_CLOUD_HI = (190, 202, 224)
_BOLT = (255, 236, 120)

# Per-glyph colour maps. Keys are the non-'.' characters in the grid.

# ── Star — 11x11, five-point with a twinkle in the top-right ─────────────────
_STAR_GLYPH = (
    ".....#...o.",
    "....###.ooo",
    "....###...o",
    "...#####...",
    "###########",
    ".#########.",
    "..#######..",
    "..#######..",
    "..###.###..",
    ".###...###.",
    ".##.....##.",
)

# ── Heart — 11x10 ────────────────────────────────────────────────────────────
_HEART_GLYPH = (
    ".###...###.",
    "#####.#####",
    "###########",
    "h##########",
    "h##########",
    ".#########.",
    ".#########.",
    "..#######..",
    "...#####...",
    ".....#.....",
)
_HEART_MAP = {"#": _HEART, "h": _HEART_HI}

# ── Snowflake — 11x11 ────────────────────────────────────────────────────────
_SNOW_GLYPH = (
    "..#..#..#..",
    "...#.#.#...",
    "#..#.#.#..#",
    ".#.#.#.#.#.",
    "..##.#.##..",
    "############",
    "..##.#.##..",
    ".#.#.#.#.#.",
    "#..#.#.#..#",
    "...#.#.#...",
    "..#..#..#..",
)
_SNOW_MAP = {"#": _SNOW}

# ── Flame — 9x11 ─────────────────────────────────────────────────────────────
_FLAME_GLYPH = (
    "....#....",
    "...##....",
    "...###...",
    "..##h#...",
    "..#hh##..",
    ".##hhh#..",
    ".#htttH..",
    ".#htttH..",
    ".##ttt#..",
    "..#####..",
    "...###...",
)
_FLAME_MAP = {"#": _FLAME_HOT, "h": _FLAME_MID, "t": _FLAME_TIP, "H": _FLAME_MID}

# ── Flower / petals — 11x11, five rounded lobes around a golden core ─────────
_PETAL_GLYPH = (
    "...####....",
    "..#hh##....",
    "..######...",
    "##########.",
    "###cccc####",
    "##cccccc###",
    "###cccc####",
    "##########.",
    "..######...",
    "..######...",
    "...####....",
)
_PETAL_MAP = {"#": _PETAL, "h": _PETAL_HI, "c": _PETAL_CORE}

# ── Storm cloud + bolt — 13x12 ───────────────────────────────────────────────
_STORM_GLYPH = (
    "....HHHH.....",
    "..HHHHHHHH...",
    ".HHHHHHHHHH..",
    "#############",
    "#############",
    "#############",
    ".###########.",
    "....bb.......",
    "...bb........",
    "..bbbbb......",
    "....bb.......",
    "...bb........",
)
_STORM_MAP = {"#": _CLOUD, "H": _CLOUD_HI, "b": _BOLT}


def _pad(rows: tuple[str, ...]) -> tuple[str, ...]:
    """Right-pad rows to equal width so a hand-authored grid can be slightly
    ragged without misaligning columns."""
    w = max(len(r) for r in rows)
    return tuple(r.ljust(w, ".") for r in rows)


def _star_map() -> dict:
    return {"#": _STAR, "o": _STAR_HI}


_GLYPHS = {
    "field_stars": (_pad(_STAR_GLYPH), _star_map()),
    "field_hearts": (_pad(_HEART_GLYPH), _HEART_MAP),
    "field_skulls": (fieldsmod._SKULL_GLYPH,
                     {"#": _BONE, "e": _SOCKET, "n": _NOSE}),
    "field_snow": (_pad(_SNOW_GLYPH), _SNOW_MAP),
    "field_embers": (_pad(_FLAME_GLYPH), _FLAME_MAP),
    "field_petals": (_pad(_PETAL_GLYPH), _PETAL_MAP),
    "field_aurora": (_pad(_STORM_GLYPH), _STORM_MAP),
}


def has_emblem(field_id: str) -> bool:
    return field_id in _GLYPHS


def render(field_id: str, size: int) -> pygame.Surface | None:
    """A transparent `size`x`size` pixel-art emblem for `field_id`, or None.

    The glyph grid is centred and each filled cell is drawn as an integer
    block (`cell` px square) with a hard edge — no smoothing — so the result
    is genuinely 8-bit, matching the field particles' own glyphs.
    """
    entry = _GLYPHS.get(field_id)
    if entry is None:
        return None
    grid, cmap = entry
    rows = len(grid)
    cols = len(grid[0])

    # Largest integer cell size that fits the glyph inside `size`, with a small
    # margin so the emblem doesn't touch the swatch border.
    usable = size - 4
    cell = max(1, min(usable // cols, usable // rows))
    gw, gh = cols * cell, rows * cell
    ox = (size - gw) // 2
    oy = (size - gh) // 2

    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    for ry, row in enumerate(grid):
        for rx, ch in enumerate(row):
            if ch == ".":
                continue
            colour = cmap.get(ch)
            if colour is None:
                continue
            pygame.draw.rect(surf, colour,
                             (ox + rx * cell, oy + ry * cell, cell, cell))
    return surf
