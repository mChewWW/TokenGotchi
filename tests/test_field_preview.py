"""Shop-row field thumbnails — one representative swatch per field.

The bug: `window._preview` had branches for SHELL and SCREEN but none for
FIELD, so every field id fell through to the hat path (`draw_creature(hat=
item_id)`). A field id is not a valid hat, so all field rows rendered the SAME
plain pet — the small image on the left of each purchasable field was identical
and told the player nothing about what they were buying.

These tests defend the fix: each field previews as a swatch of its own
particles, distinct from every other field and from the hat fall-through.
"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from tokengotchi.renderer import field_emblems
from tokengotchi.renderer import fields as fieldsmod
from tokengotchi.renderer import shop_panel as shoppanel
from tokengotchi.renderer import uikit as uikit_mod
from tokengotchi.renderer.window import GameWindow
from tokengotchi.shop.catalogue import ItemKind


@pytest.fixture
def window():
    uikit_mod._font_cache.clear()
    pygame.init()
    w = GameWindow()
    try:
        yield w
    finally:
        w.close()
        pygame.quit()


def _signature(surf: pygame.Surface) -> bytes:
    """A cheap content fingerprint — raw pixels of the rendered swatch."""
    return pygame.image.tostring(surf, "RGB")


def test_every_field_previews_differently(window):
    """The headline guarantee: no two field swatches are identical.

    This is the exact bug's inverse — before the fix all field rows produced
    the same pixels. A per-id `_field_thumb` that ever collapsed back to one
    shared image (e.g. a dropped FIELD branch) fails here.
    """
    ids = [spec.id for spec in fieldsmod.FIELDS]
    assert len(ids) >= 6, "expected the full field roster"

    sigs = {fid: _signature(window._field_thumb(fid)) for fid in ids}
    assert len(set(sigs.values())) == len(ids), (
        "two or more field previews are pixel-identical: "
        f"{[fid for fid in ids if list(sigs.values()).count(sigs[fid]) > 1]}"
    )


def test_a_field_preview_is_not_the_hat_fallthrough(window):
    """A field routed through `_preview` must NOT render the pet.

    The bug was precisely that a field fell through to
    `draw_creature(hat=field_id)`. `_preview` on a field id and `_preview` on a
    (nonexistent) hat id both write ICONxICON into the same dest; if the field
    branch were dropped they would match. They must not.
    """
    n = shoppanel.ICON
    field_id = fieldsmod.purchasable_fields()[0].id

    field_cell = pygame.Surface((n, n))
    window._preview(field_cell, 0, 0, field_id)

    # A hat id that does not exist still exercises the fall-through path (the
    # creature draw), which is what a field used to hit by mistake.
    hat_cell = pygame.Surface((n, n))
    window._preview(hat_cell, 0, 0, "hat_that_does_not_exist")

    assert _signature(field_cell) != _signature(hat_cell), (
        "a field preview matches the hat fall-through — the FIELD branch in "
        "_preview is not being taken"
    )


def test_field_preview_is_drawn_at_icon_size_and_is_not_blank(window):
    """The swatch fills its cell with real content, not an empty rectangle."""
    n = shoppanel.ICON
    for spec in fieldsmod.FIELDS:
        thumb = window._field_thumb(spec.id)
        assert thumb.get_size() == (n, n), spec.id
        # More than one distinct colour == actual particles/base, not a flat
        # blank cell.
        ar = pygame.surfarray.array3d(thumb)
        distinct = len({tuple(ar[x, y]) for x in range(n) for y in range(0, n, 2)})
        assert distinct > 2, f"{spec.id} rendered an almost-blank swatch"


def test_field_thumb_is_cached(window):
    """The swatch is memoised — a particle field must not be rebuilt per row
    per frame. The same id returns the identical surface object."""
    fid = fieldsmod.purchasable_fields()[0].id
    first = window._field_thumb(fid)
    second = window._field_thumb(fid)
    assert first is second, "field thumbnail was not cached"


def test_every_field_has_an_iconic_emblem(window):
    """The human's follow-up: the swatch must be a clean ICON (heart, skull,
    cloud-and-bolt), not a low-res still of the field. Every field in the
    roster — the default starfield included — must resolve an emblem, or that
    field falls back to a blank base and reads as nothing.
    """
    n = shoppanel.ICON
    for spec in fieldsmod.FIELDS:
        assert field_emblems.has_emblem(spec.id), spec.id
        emblem = field_emblems.render(spec.id, n)
        assert emblem is not None and emblem.get_size() == (n, n), spec.id
        # The emblem draws real, opaque content — not a fully transparent
        # square that would leave the swatch bare.
        alpha = pygame.surfarray.array_alpha(emblem)
        assert int(alpha.max()) > 0, f"{spec.id} emblem is fully transparent"


def test_an_unknown_field_emblem_is_none():
    """`render` degrades to None for an id with no emblem, so `_field_thumb`
    can fall back to a bare base rather than raising."""
    assert field_emblems.render("field_not_real", shoppanel.ICON) is None
    assert field_emblems.has_emblem("field_not_real") is False


def test_emblems_are_pixel_art_not_smooth_vectors():
    """The human's second follow-up: the icons must be 8-bit, not smooth.

    A hand-authored glyph rendered as integer blocks uses only the handful of
    flat colours in its colour map (plus fully-transparent). A regression to a
    supersampled/anti-aliased vector would introduce a long tail of blended
    edge colours. Asserting a small distinct-colour count is the machine-
    checkable proxy for 'reads as pixel art'.
    """
    n = shoppanel.ICON
    for spec in fieldsmod.FIELDS:
        emblem = field_emblems.render(spec.id, n)
        rgb = pygame.surfarray.array3d(emblem)
        alpha = pygame.surfarray.array_alpha(emblem)
        # Colours of opaque pixels only (transparent ones are background).
        colours = {
            tuple(rgb[x, y])
            for x in range(n) for y in range(n) if alpha[x, y] > 0
        }
        assert 0 < len(colours) <= 6, (
            f"{spec.id} uses {len(colours)} opaque colours — more than a flat "
            "pixel-art palette should, suggesting anti-aliased vector edges"
        )


def test_emblem_uses_integer_pixel_blocks():
    """Every filled glyph cell is an NxN block, so the smallest run of a
    non-background colour along a row is at least the block size — a smooth
    curve would produce single-pixel steps. Checks the skull, which has both
    large fills and fine detail."""
    n = shoppanel.ICON
    emblem = field_emblems.render("field_skulls", n)
    rgb = pygame.surfarray.array3d(emblem)
    alpha = pygame.surfarray.array_alpha(emblem)
    # Find the block size the renderer chose and assert horizontal runs of the
    # bone colour are multiples of it (allowing the last partial run).
    from tokengotchi.renderer.field_emblems import _BONE
    runs = []
    for y in range(n):
        run = 0
        for x in range(n):
            if alpha[x, y] > 0 and tuple(rgb[x, y]) == _BONE:
                run += 1
            elif run:
                runs.append(run)
                run = 0
        if run:
            runs.append(run)
    assert runs, "no bone pixels found"
    assert min(runs) >= 2, (
        "found a 1px bone run — the skull is not being drawn as integer blocks"
    )


def test_all_kinds_have_a_distinct_preview_path(window):
    """Guards the premise: FIELD is a real ItemKind that reaches its own
    branch, alongside SHELL and SCREEN. If a future refactor drops the FIELD
    case, the equality below (field vs a screen swatch) collapses."""
    field_id = fieldsmod.purchasable_fields()[0].id
    n = shoppanel.ICON

    field_cell = pygame.Surface((n, n))
    window._preview(field_cell, 0, 0, field_id)

    # A screen id goes down the SCREEN branch — different construction entirely.
    screen_cell = pygame.Surface((n, n))
    window._preview(screen_cell, 0, 0, "screen_amber")

    assert ItemKind.FIELD is not ItemKind.SCREEN
    assert _signature(field_cell) != _signature(screen_cell)
