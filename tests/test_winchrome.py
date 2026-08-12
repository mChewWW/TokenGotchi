"""Tests for winchrome — the Win32 frameless/rounded/drag helpers.

The OS-touching calls degrade to silent no-ops off-Windows and aren't asserted
here; what IS load-bearing and testable in isolation is:

  * `clamp_to_workarea` — pure arithmetic that is the SOLE safety net keeping a
    frameless, titlebar-less window from being dragged irrecoverably off-screen.
    A NOFRAME window has no WS_SYSMENU Alt+Space->Move fallback, so a bug here
    can brick the app. The multi-monitor case with a NEGATIVE work-area origin
    is the one a naive `max(0, ...)` clamp gets wrong.
"""
from tokengotchi.renderer import winchrome


def test_clamp_keeps_fully_onscreen_window_unchanged():
    # A window comfortably inside the work area is not moved.
    assert winchrome.clamp_to_workarea(
        100, 100, 400, 450, (0, 0, 1920, 1080)) == (100, 100)


def test_clamp_pins_offscreen_right_bottom():
    # Dragged far past the bottom-right: x pinned so the width fits, y pinned so
    # the top handle strip stays above the work-area bottom.
    x, y = winchrome.clamp_to_workarea(
        5000, 5000, 400, 450, (0, 0, 1920, 1080), handle_h=40)
    assert x == 1920 - 400
    assert y == 1080 - 40


def test_clamp_respects_negative_virtual_origin():
    # Left/top monitor with a negative origin (real multi-monitor layout). A
    # window dragged toward the top-left must clamp to the NEGATIVE bounds, not
    # to (0, 0) — the bug a max(0, ...) clamp would introduce.
    bounds = (-318, -1440, 1920, 1080)
    x, y = winchrome.clamp_to_workarea(-5000, -5000, 400, 450, bounds)
    assert x == -318
    assert y == -1440


def test_clamp_top_never_hidden_above_workarea():
    # Even nudged slightly above the top, the origin is clamped down to the
    # work-area top so the control strip is never off the top edge.
    _, y = winchrome.clamp_to_workarea(200, -50, 400, 450, (0, 0, 1920, 1080))
    assert y == 0


def test_clamp_degenerate_width_pins_left_not_beyond():
    # A window wider than the work area can't fit; the origin must pin to the
    # work-area left, never past it (no inverted range that would push controls
    # off the left).
    x, _ = winchrome.clamp_to_workarea(
        500, 50, 4000, 450, (10, 20, 100, 620))
    assert x == 10


def test_clamp_handle_strip_kept_when_it_fits_vertically():
    # The handle strip (40px) fits inside this 100px-tall work area, so the top
    # is clamped down to keep it above the bottom edge, not to the top.
    _, y = winchrome.clamp_to_workarea(
        50, 500, 400, 4000, (10, 20, 100, 120), handle_h=40)
    assert y == 120 - 40


def test_round_radius_matches_case_geometry():
    # The region radius must equal BEZEL(8) + body radius(22) so the OS clip is
    # concentric with the painted case edge.
    assert winchrome.ROUND_RADIUS == 30
