"""The food panel's icon-vs-slot clearance.

Every food's 16x16 icon is blitted at an integer scale (never anti-aliased —
see fooditems.py's docstring on why) inside a rounded-square "slot" drawn as
its border/background in `food_panel._body()`. If the icon's own canvas is
sized with only a pixel or so of clearance from that slot, the icon's opaque
pixels sit flush against the slot's rounded corners and border stroke.

That was invisible for foods whose OWN art happens to carry a built-in
transparent margin (bread, apple), but visually "cut off" the rounded square
for foods whose silhouette reaches all the way to its own canvas edge
(cookie, cake, steak, and — less obviously, since it's only a single-pixel
glint rather than a solid mass — golden apple). This is a property of the
shared sizing MATH, not of any one food's art, so the tests below check the
geometry itself, for every food on the menu, rather than special-casing the
three IDs the bug was originally reported against.
"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1, 1))

from tokengotchi.engine import food as menu  # noqa: E402
from tokengotchi.renderer import fooditems, food_panel as fp, theme, uikit  # noqa: E402

# Two real pixels, not one — "several pixels, not 0-1" is the whole point of
# the fix. At the sizing that shipped with the bug, slot=49 and icon_px=48
# left a single TOTAL pixel of clearance (well under one pixel per side), so
# this threshold is comfortably above the broken value and comfortably below
# what the fix actually provides (3px+ per side at current geometry).
MIN_MARGIN_PER_SIDE = 2


def _grid_geometry():
    """Re-derive `slot`/`icon_scale`/`icon_px` exactly as `_body()` does.

    Recomputed from the module's real constants rather than duplicated as
    literals, so this test tracks whatever the panel's actual proportions
    are instead of pinning today's PANEL_W/H by hand.
    """
    footer_h = 34
    grid_bottom = fp.PANEL_H - footer_h
    cell_w = (fp.PANEL_W - fp.GRID_MARGIN * 2
              - fp.GRID_GAP * (fp.GRID_COLS - 1)) // fp.GRID_COLS
    cell_h = (grid_bottom - fp.GRID_TOP
              - fp.GRID_GAP * (fp.GRID_ROWS - 1)) // fp.GRID_ROWS
    slot = min(max(30, min(cell_w, cell_h) - fp.SLOT_INSET), fp.MAX_SLOT)
    icon_scale = max(2, (slot - fp.ICON_PAD) // fooditems.GRID)
    icon_px = fooditems.GRID * icon_scale
    return slot, icon_scale, icon_px


def test_icon_canvas_has_visible_clearance_from_its_slot():
    """The canvas-vs-slot fit itself, before any one food's art is considered."""
    slot, icon_scale, icon_px = _grid_geometry()
    margin = slot - icon_px
    assert margin >= MIN_MARGIN_PER_SIDE * 2, (
        f"icon canvas ({icon_px}px) leaves only {margin}px of TOTAL "
        f"clearance inside its {slot}px slot — any food whose own art "
        f"reaches its own canvas edge will visually spill past the slot's "
        f"rounded corners/border"
    )


def test_every_food_icons_opaque_pixels_stay_clear_of_the_slot_edge():
    """For every food on the menu — not just the three reported — no opaque
    pixel of its rendered icon should sit flush against the slot around it.

    This is the check that actually would have caught the original bug:
    `icon_px <= slot` was already true before the fix (the icon never
    literally overflows the square it's centred in), so a bare bounds check
    is not enough. What broke was the MARGIN — this measures the real gap
    between each food's own opaque silhouette and the slot's four edges.
    """
    slot, icon_scale, icon_px = _grid_geometry()
    offset = (slot - icon_px) // 2  # `_body()`'s (slot - icon_px) // 2

    assert set(f.id for f in menu.FOODS) <= set(fooditems.ART)

    failures = []
    for f in menu.FOODS:
        art = fooditems.ART[f.id]
        x0, x1, y0, y1 = fooditems._bbox(art)
        left = offset + x0 * icon_scale
        top = offset + y0 * icon_scale
        right = slot - (offset + (x1 + 1) * icon_scale)
        bottom = slot - (offset + (y1 + 1) * icon_scale)
        for side, gap in (("left", left), ("top", top),
                          ("right", right), ("bottom", bottom)):
            if gap < MIN_MARGIN_PER_SIDE:
                failures.append(f"{f.id}: {side} margin is {gap}px")

    assert not failures, "\n".join(failures)


def test_stat_row_leaves_room_before_the_next_grid_row():
    """Regression: growing `slot` (49 -> 54) to fix the icon-clipping bug
    shrank the vertical gap between each card's name/cost/gain text and the
    NEXT grid row's card top from ~5px to ~0px — the icon fix must not trade
    one clipping bug for a spacing one. `MAX_SLOT` caps the icon's own
    growth and `PANEL_H` grew to fund the freed room instead, so this checks
    the actual resulting gap rather than trusting that combination blindly.
    """
    slot, _icon_scale, _icon_px = _grid_geometry()
    footer_h = 34
    grid_bottom = fp.PANEL_H - footer_h
    cell_h = (grid_bottom - fp.GRID_TOP
              - fp.GRID_GAP * (fp.GRID_ROWS - 1)) // fp.GRID_ROWS
    row_spacing = cell_h + fp.GRID_GAP

    # Mirrors `_body()`'s own text metrics exactly rather than a hardcoded
    # pixel height, so a future font/face change can't silently stale this.
    # `pygame.font.init()` is re-armed defensively: another test module's
    # `pygame.quit()` teardown can tear down the font subsystem this
    # module's own top-level `pygame.init()` brought up earlier, and this is
    # the only test in this file that actually renders text.
    pygame.font.init()
    stat_line = uikit.text("0 B", theme.BITS, theme.FONT_CAPTION, bold=True,
                           face=fp.FACE)
    stat_bottom_rel = 3 + slot + 16 + stat_line.get_height()
    gap = row_spacing - stat_bottom_rel
    assert gap >= 3, (
        f"only {gap}px between the stat row and the next card row "
        f"(row_spacing={row_spacing}, stat_bottom_rel={stat_bottom_rel})"
    )


def test_cookie_cake_and_steak_have_no_margin_of_their_own_to_fall_back_on():
    """Sanity-checks the root cause, not just the fix: these three foods'
    silhouettes touch column 0 and/or column 15 of their own 16x16 canvas, so
    they have zero built-in art margin — unlike bread/apple/golden apple's
    solid bodies, which are all drawn with a transparent gap from at least
    one edge. If this stops being true the diagnosis above needs revisiting.
    """
    def touches_left_or_right(food_id: str) -> bool:
        art = fooditems.ART[food_id]
        cols = {gx for row in art for gx, ch in enumerate(row) if ch != "."}
        return 0 in cols or (fooditems.GRID - 1) in cols

    for fid in ("food_cookie", "food_cake", "food_steak"):
        assert touches_left_or_right(fid), fid
