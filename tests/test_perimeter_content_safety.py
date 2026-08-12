"""The 3D perimeter must be perimeter-ONLY — it may never alter displayed content.

Direction contract v19 makes "displayed content unchanged" a hard, testable
gate: the new case-edge relief is confined to the outer band and must not touch
the screen recess (where the pet, readouts, and shop/food panels are composited)
on ANY shell skin. This asserts the `_perimeter` overlay is fully transparent
over `screen_rect()` for every shell — a byte-level guarantee, not an eyeball.
"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from tokengotchi.renderer import device, skins


@pytest.fixture(scope="module", autouse=True)
def _display():
    pygame.init()
    # metal.face() calls .convert(), which needs a real video mode.
    pygame.display.set_mode((device.SCREEN_W + 60, device.SCREEN_H + 200))
    yield
    pygame.quit()


@pytest.mark.parametrize("shell", skins.SHELLS, ids=lambda s: s.id)
def test_perimeter_is_transparent_over_screen_recess(shell):
    size = (400, 450)
    overlay = device._perimeter(size, shell)
    alpha = pygame.surfarray.pixels_alpha(overlay)  # indexed [x, y]
    sr = device.screen_rect()
    inside = alpha[sr.x:sr.x + sr.w, sr.y:sr.y + sr.h]
    assert int(inside.max()) == 0, (
        f"perimeter bevel bled into the screen recess on shell {shell.id}")


def test_perimeter_actually_draws_something_on_the_edge():
    # Guard against the test passing vacuously: the overlay must be non-empty
    # somewhere in the outer band, or "perimeter-only" is trivially satisfied by
    # drawing nothing at all.
    overlay = device._perimeter((400, 450), skins.SHELL_DEFAULT)
    alpha = pygame.surfarray.pixels_alpha(overlay)
    assert int(alpha.max()) > 0


def _luma(px):
    return 0.2126 * px[0] + 0.7152 * px[1] + 0.0722 * px[2]


@pytest.mark.parametrize("shell", skins.SHELLS, ids=lambda s: s.id)
def test_perimeter_edge_reads_three_dimensional(shell):
    # The rim must be a LIT CHAMFER, not a flat frame: sampled on the outer edge
    # band, the top-left must be clearly lighter than the bottom-right, with a
    # meaningful lift on every shell. This is the objective stand-in for "looks
    # 3D" and the regression guard against the flat-bezel look.
    W, H = 400, 450
    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    device.draw_shell(surf, shell)
    arr = pygame.surfarray.array3d(surf)  # [x, y]
    b = 4  # px in from the outer edge, on the straight run past the r=30 corner
    tl = (_luma(arr[45, b]) + _luma(arr[b, 45])) / 2
    br = (_luma(arr[W - 45, H - 1 - b]) + _luma(arr[W - 1 - b, H - 45])) / 2
    assert tl > br, f"{shell.id}: top-left not lighter than bottom-right"
    assert tl - br >= 40, f"{shell.id}: edge lift {tl - br:.1f} < 40 (reads flat)"


# Metal shells replace the plastic face with a plated luminance ramp of their
# own, which brightens the bottom edge and partly cancels the cast shadow — so
# the shadow-side cross-width metric doesn't hold for them even though the rim
# is beveled (they still pass the diagonal TL>BR lift test above). Excluded here.
_METAL_SHELLS = {"shell_true_silver", "shell_true_gold"}


@pytest.mark.parametrize(
    "shell", [s for s in skins.SHELLS if s.id not in _METAL_SHELLS],
    ids=lambda s: s.id)
def test_bevel_ramps_across_the_rim_width(shell):
    # The core of "looks 3D": the bevel's gradient runs ACROSS the rim's width,
    # not flat. The robust, shell-independent signal is the SHADOW side — the
    # bottom rim must darken markedly from the face out to the outer edge on
    # every shell (light shells have little top-edge contrast because their lit
    # side is already near-white, but all plastic shells cast the bottom
    # shadow). The two prior failed attempts were flat across the rim; this
    # guards against regressing to that "picture frame" look.
    W, H = 400, 450
    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    device.draw_shell(surf, shell)
    arr = pygame.surfarray.array3d(surf)
    x = 60  # a straight run of the bottom edge, clear of the rounded corner
    outer = _luma(arr[x, H - 1])
    face = _luma(arr[x, H - 1 - device.BEZEL])
    assert face - outer >= 30, (
        f"{shell.id}: bottom rim not beveled across width "
        f"(face {face:.0f} -> outer edge {outer:.0f}); reads flat")
