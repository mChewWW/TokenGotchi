"""Food icons, authored as 16x16 pixel grids and blitted magnified.

Same discipline as `sprites.py`: every mark is a whole sprite-pixel drawn as a
rectangle, then the whole thing is upscaled by an integer. Nothing is
anti-aliased and nothing is a gradient.

AUTHORED AS TEXT, DELIBERATELY. The first version built each item from a stack
of horizontal runs with an outline drawn per run — which meant every interior
row got outlined too, and each row's outline overwrote its neighbour's fill.
All six came out as flat horizontal bands and were indistinguishable. A literal
grid cannot have that bug: what is written is what is drawn.

SILHOUETTE CARRIES THESE, NOT COLOUR, and that is a requirement rather than a
preference. They are drawn INSIDE the screen, and several skins run everything
through `skins.quantise_layer` — the Dot-Matrix LCD reduces the world to four
greens, E-Ink to four greys. On those the palettes below are destroyed. So each
of the six is shaped to survive with all colour removed:

    Cookie        a wide disc with holes punched through it
    Bread         a tall domed loaf with three slashes cut across the crown
    Apple         a round fruit with a BITE out of the right side
    Cooked Steak  a lopsided slab with a pale bone nub on one end
    Cake          a wide two-tier block with three candles breaking the top
    Golden Apple  the apple silhouette, unbitten, inside a glint burst

The bite and the burst exist purely to break a tie: without them the two apples
are one shape in two colours, and on the LCD that is one shape twice.
"""
from __future__ import annotations

import pygame

GRID = 16

_O = (26, 18, 12)          # outline, darker than anything it touches
_LEAF_D, _LEAF_L = (32, 92, 38), (58, 138, 56)
_BONE_D, _BONE_L = (198, 192, 172), (238, 234, 218)
_GLINT = (255, 246, 196)
_STEM = (74, 48, 26)

# s = shadow, b = base, h = highlight, o = outline, . = transparent
_PAL = {
    "food_cookie": {"s": (104, 62, 28), "b": (150, 96, 44), "h": (188, 132, 70)},
    "food_bread": {"s": (132, 82, 34), "b": (178, 122, 58), "h": (222, 172, 104)},
    "food_apple": {"s": (150, 26, 32), "b": (204, 44, 48), "h": (244, 104, 100)},
    "food_steak": {"s": (92, 38, 32), "b": (146, 64, 50), "h": (190, 106, 80)},
    "food_cake": {"s": (176, 168, 158), "b": (238, 232, 222), "h": (255, 253, 248),
                  "t": (208, 54, 58), "u": (150, 32, 40), "v": (250, 112, 108)},
    "food_golden_apple": {"s": (176, 126, 20), "b": (232, 182, 46),
                          "h": (255, 230, 128)},
}
_EXTRA = {"o": _O, "g": _LEAF_L, "G": _LEAF_D, "n": _BONE_L, "N": _BONE_D,
          "*": _GLINT, "|": _STEM}

ART: dict[str, tuple[str, ...]] = {
    # A wide flat disc. The holes are the whole identity in monochrome.
    "food_cookie": (
        "................",
        "................",
        "................",
        "................",
        "....oooooooo....",
        "..oohhhhhhhhoo..",
        ".ohhbbooobbbbbho",
        "obbbbooobbbbbbbo",
        "obbbbbbbbboobbbo",
        "obooobbbbboobbso",
        ".oooobbbbbbbsso.",
        "..oosssssssssoo.",
        "....oooooooo....",
        "................",
        "................",
        "................",
    ),
    # Tall and domed, with slashes. The only item taller than it is wide.
    "food_bread": (
        "................",
        ".....oooooo.....",
        "...oohhhhhhoo...",
        "..ohhbbbbbbbho..",
        "..ohbohbohbobho.",
        "..obsobsobsobbo.",
        "..obbbbbbbbbbbo.",
        "..obbbbbbbbbbbo.",
        "..obbbbbbbbbbbo.",
        "..obbbbbbbbbbbo.",
        "..obbbbbbbbbbbo.",
        "..obbbbbbbbbbbo.",
        "..osbbbbbbbbbso.",
        "..oosssssssssoo.",
        "....oooooooo....",
        "................",
    ),
    # Round, with a bite carved out of the right shoulder.
    "food_apple": (
        "................",
        "........|.......",
        "........|.gGg...",
        "....oooo|gggG...",
        "...ohhhbbbo.....",
        "..ohhbbbbbboo...",
        "..obbbbbbbbo....",
        ".obbbbbbbbo.....",
        ".obbbbbbbbo.....",
        ".obbbbbbbbboo...",
        ".obbbbbbbbbbbo..",
        "..obbbbbbbbbbo..",
        "..osbbbbbbbbso..",
        "...ossbbbbsso...",
        "....oossssoo....",
        "......oooo......",
    ),
    # Lopsided slab plus a bone nub. Irregular on purpose: a neat rectangle
    # reads as a brick, not as meat.
    "food_steak": (
        "................",
        "................",
        "................",
        "....oooooo......",
        "..oohhhbbboo.NN.",
        ".ohhbbbbbbbbonn.",
        "obbbbbbbbbbbbonn",
        "obbbbbbbbbbbbbon",
        "obbbbbbbbbbbbbo.",
        ".obbbbsbbbbbbo..",
        ".obsssssbbbbo...",
        "..ossssssssoo...",
        "...oooooooo.....",
        "................",
        "................",
        "................",
    ),
    # Wide, two-tier, candles breaking the top edge. The only WIDE silhouette.
    "food_cake": (
        "................",
        "...*....*....*..",
        "...v....v....v..",
        "...v....v....v..",
        "....oooooooo....",
        "..oovvvvvvvvoo..",
        ".ovvvvvvvvvvvvo.",
        ".ouuuuuuuuuuuuo.",
        "ohhhhhhhhhhhhhho",
        "obbbbbbbbbbbbbbo",
        "obbbbbbbbbbbbbbo",
        "obbbbbbbbbbbbbbo",
        "osssssssssssssso",
        ".oooooooooooooo.",
        "................",
        "................",
    ),
    # The apple shape, unbitten, inside a burst.
    "food_golden_apple": (
        "................",
        "...*....|...*...",
        "........|.gGg...",
        "....oooo|gggG...",
        "*..ohhhbbbbo..*.",
        "..ohhbbbbbbbo...",
        ".obbbbbbbbbbbo..",
        ".obbbbbbbbbbbo..",
        "*obbbbbbbbbbbo*.",
        ".obbbbbbbbbbbo..",
        ".obbbbbbbbbbbo..",
        "..obbbbbbbbbo...",
        "*.osbbbbbbbso.*.",
        "...ossbbbbsso...",
        "....oossssoo....",
        "..*...oooo...*..",
    ),
}


def _colour(food_id: str, ch: str):
    if ch == ".":
        return None
    pal = _PAL.get(food_id, {})
    return pal.get(ch) or _EXTRA.get(ch)


# ── Eating animation — 2 derived stages per food ─────────────────────────────
# Not 12 separately hand-drawn grids: each stage is ERODED from that food's own
# ART, keeping only that food's own outline/palette characters. A generic
# "shrink toward a blob" would lose identity mid-bite; eroding the real grid
# from the right, capped with that food's own 'o' outline, keeps the silhouette
# recognisably itself at every stage instead of converging on a generic shape.
STAGE_KEEP = (1.0, 0.62, 0.30)   # fraction of the silhouette's width kept
CRUMBS = 3                       # leftover flecks scattered in the final stage


def _bbox(art: tuple[str, ...]) -> tuple[int, int, int, int]:
    cols = [gx for row in art for gx, ch in enumerate(row) if ch != "."]
    rows = [gy for gy, row in enumerate(art) for ch in row if ch != "."]
    return min(cols), max(cols), min(rows), max(rows)


def _eaten(food_id: str, keep: float, crumbs: int = 0) -> tuple[str, ...]:
    art = ART[food_id]
    x0, x1, y0, y1 = _bbox(art)
    width = x1 - x0 + 1
    cutoff = x0 + max(1, int(round(width * keep)))
    rows: list[str] = []
    for row in art:
        chars = list(row)
        bitten = any(c != "." for c in row[cutoff:])
        for gx in range(cutoff, len(chars)):
            chars[gx] = "."
        if bitten and cutoff - 1 >= 0 and chars[cutoff - 1] != ".":
            chars[cutoff - 1] = "o"
        rows.append("".join(chars))
    if crumbs and cutoff <= x1:
        base = next((c for c in "sbh" if c in "".join(art)), "b")
        span = max(1, x1 - cutoff)
        for i in range(crumbs):
            cx = min(len(rows[0]) - 1, cutoff + 1 + (i * span) // crumbs)
            cy = max(y0, min(y1, y1 - (i % 2)))
            r = list(rows[cy])
            r[cx] = base
            rows[cy] = "".join(r)
    return tuple(rows)


EATEN: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    fid: (_eaten(fid, STAGE_KEEP[1]), _eaten(fid, STAGE_KEEP[2], crumbs=CRUMBS))
    for fid in ART
}


def stages(food_id: str) -> tuple[tuple[str, ...], ...] | None:
    """The 3 consumption-stage grids for a food: whole, half-eaten, near-gone."""
    if food_id not in ART:
        return None
    half, gone = EATEN[food_id]
    return ART[food_id], half, gone


def draw(surf: pygame.Surface, food_id: str, x: int, y: int,
         scale: int = 2, stage: int = 0) -> None:
    """Blit one food icon with its top-left at (x, y), magnified `scale`x.

    `stage` selects which of the 3 consumption-stage grids to draw (0 = whole,
    2 = nearly gone); defaults to the whole item so every existing call site
    (the menu grid, which never eats) is unaffected.
    """
    all_stages = stages(food_id)
    if all_stages is None:
        return
    art = all_stages[max(0, min(2, stage))]
    for gy, row in enumerate(art):
        for gx, ch in enumerate(row):
            col = _colour(food_id, ch)
            if col is not None:
                pygame.draw.rect(surf, col,
                                 (x + gx * scale, y + gy * scale, scale, scale))


def surface(food_id: str, scale: int = 2, stage: int = 0) -> pygame.Surface:
    s = pygame.Surface((GRID * scale, GRID * scale), pygame.SRCALPHA)
    draw(s, food_id, 0, 0, scale, stage)
    return s
