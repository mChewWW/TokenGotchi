"""The click-vs-drag threshold on the frameless window's body-drag.

With no titlebar, the case body is the drag handle. The danger is a click that
jitters a pixel or two getting promoted to a drag — relocating the window and
swallowing the button press underneath. The state machine must only commit to a
move once the cursor has travelled past a small threshold; below it, the press
stays a click.

These drive `GameWindow`'s real drag methods against a mocked `winchrome` so no
actual OS window is created — the logic under test is pure state, not Win32.
"""
from __future__ import annotations

from unittest.mock import patch

from tokengotchi.renderer.window import GameWindow


class _DragHarness:
    """A bare object carrying just the drag state the methods read/write, so we
    can exercise the unbound GameWindow drag methods without constructing a real
    window (whose __init__ opens a display and calls into Win32)."""

    def __init__(self):
        self._drag_active = False
        self._drag_candidate = False
        self._drag_grab = None
        self._drag_press_cursor = None

    # Borrow the real implementations verbatim.
    _DRAG_THRESHOLD = GameWindow._DRAG_THRESHOLD
    _begin_drag_candidate = GameWindow._begin_drag_candidate
    _update_drag = GameWindow._update_drag
    _end_drag = GameWindow._end_drag


_MOD = "tokengotchi.renderer.window.winchrome"


def test_press_arms_a_candidate_but_does_not_move():
    h = _DragHarness()
    with patch(f"{_MOD}.global_cursor", return_value=(500, 500)), \
         patch(f"{_MOD}.window_origin", return_value=(450, 460)):
        h._begin_drag_candidate()
    assert h._drag_candidate is True
    assert h._drag_active is False
    assert h._drag_grab == (50, 40)  # cursor - origin


def test_subthreshold_motion_stays_a_click():
    h = _DragHarness()
    with patch(f"{_MOD}.global_cursor", return_value=(500, 500)), \
         patch(f"{_MOD}.window_origin", return_value=(450, 460)):
        h._begin_drag_candidate()
    # Move only 2px total — below the 4px threshold.
    with patch(f"{_MOD}.global_cursor", return_value=(501, 501)), \
         patch(f"{_MOD}.move_window") as mv:
        owns = h._update_drag()
    assert owns is False
    assert h._drag_active is False
    mv.assert_not_called()


def test_beyond_threshold_commits_and_moves_clamped():
    h = _DragHarness()
    with patch(f"{_MOD}.global_cursor", return_value=(500, 500)), \
         patch(f"{_MOD}.window_origin", return_value=(450, 460)):
        h._begin_drag_candidate()
    moved = {}
    with patch(f"{_MOD}.global_cursor", return_value=(520, 530)), \
         patch(f"{_MOD}.clamp_window",
               side_effect=lambda x, y, w, ht, cursor=None: (x, y)), \
         patch(f"{_MOD}.move_window",
               side_effect=lambda x, y: moved.update(x=x, y=y)):
        owns = h._update_drag()
    assert owns is True
    assert h._drag_active is True
    # New origin = cursor - grab_offset = (520-50, 530-40) = (470, 490).
    assert moved == {"x": 470, "y": 490}


def test_clamp_is_applied_to_the_move():
    h = _DragHarness()
    with patch(f"{_MOD}.global_cursor", return_value=(500, 500)), \
         patch(f"{_MOD}.window_origin", return_value=(450, 460)):
        h._begin_drag_candidate()
    seen = {}
    with patch(f"{_MOD}.global_cursor", return_value=(9000, 9000)), \
         patch(f"{_MOD}.clamp_window", return_value=(111, 222)), \
         patch(f"{_MOD}.move_window",
               side_effect=lambda x, y: seen.update(x=x, y=y)):
        h._update_drag()
    # move_window receives the CLAMPED coordinates, not the raw cursor delta.
    assert seen == {"x": 111, "y": 222}


def test_clamp_receives_the_live_cursor():
    # The cross-monitor fix: the clamp must be told the CURSOR position so it can
    # resolve the monitor the cursor is on (always a real monitor), not the one
    # the window started on. Regression guard for the "dragged down, can't drag
    # back up" bug.
    h = _DragHarness()
    with patch(f"{_MOD}.global_cursor", return_value=(500, 500)), \
         patch(f"{_MOD}.window_origin", return_value=(450, 460)):
        h._begin_drag_candidate()
    captured = {}
    with patch(f"{_MOD}.global_cursor", return_value=(700, 800)), \
         patch(f"{_MOD}.clamp_window",
               side_effect=lambda x, y, w, ht, cursor=None: captured.update(
                   cursor=cursor) or (x, y)), \
         patch(f"{_MOD}.move_window"):
        h._update_drag()
    assert captured["cursor"] == (700, 800)


def test_end_drag_resets_state():
    h = _DragHarness()
    h._drag_candidate = True
    h._drag_active = True
    h._drag_grab = (1, 2)
    h._drag_press_cursor = (3, 4)
    h._end_drag()
    assert h._drag_candidate is False
    assert h._drag_active is False
    assert h._drag_grab is None
    assert h._drag_press_cursor is None


def test_update_without_candidate_is_noop():
    h = _DragHarness()
    with patch(f"{_MOD}.global_cursor", return_value=(1, 1)), \
         patch(f"{_MOD}.move_window") as mv:
        assert h._update_drag() is False
    mv.assert_not_called()
