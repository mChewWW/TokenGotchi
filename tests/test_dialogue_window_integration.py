"""GameWindow-level integration tests for direction contract v12.

These exercise `window.py`'s REAL composed gate expressions rather than a
hand-rolled stand-in — `tests/test_dialogue.py::
test_scheduler_paused_while_dialogue_pinned_open` simulates the shape of
`dialogue_ok = self._dialogue_visible(...) and not self._dialogue.is_open`
with a bare `_Pinned` class, which proves the scheduler behaves correctly
given that boolean but proves nothing about whether `window.py` actually
computes it that way. This file constructs a real `GameWindow` and drives
`render_frame()` so a regression in the gate's wiring (not just its logic)
would fail a test.

No prior test in this project instantiates `GameWindow` directly (grepped:
zero hits) — `window.py` sits at ~15% coverage. These two tests close the
specific gaps direction contract v12 calls out by name: "scheduler
suppression while `panel.is_open`" and "pinned-popup survival across a
hide/reshow cycle from an intervening FOOD/SHOP/RATES open+close."
"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from tokengotchi.dialogue import scheduler as sched_mod
from tokengotchi.engine.state_manager import CreatureState, GameState
from tokengotchi.renderer import device as device_mod
from tokengotchi.renderer import dialogue_panel as dp_mod
from tokengotchi.renderer import uikit as uikit_mod
from tokengotchi.renderer.window import GameWindow


@pytest.fixture(autouse=True)
def _pygame_video():
    # `uikit._font_cache` is a process-wide dict keyed on (size, bold) that
    # is never invalidated across a pygame.quit()/init() cycle. Other test
    # modules' own init/quit fixtures leave it holding Font objects tied to
    # an already-destroyed font subsystem; reusing one of those handles here
    # (this is the first test file to drive a real GameWindow through many
    # real text-drawing render_frame() calls) segfaults the interpreter
    # rather than raising — hence clearing it fresh for this module only.
    uikit_mod._font_cache.clear()
    pygame.init()
    yield
    pygame.quit()


def _game_state(hunger: float = 100.0) -> GameState:
    """A hatched, non-dormant creature — the only state dialogue speaks in."""
    return GameState(creature=CreatureState(stage="BABY", hunger=hunger))


def test_scheduler_suppressed_via_real_window_gate_while_dialogue_pinned(monkeypatch):
    """Contract v12 point 3, proven against `window.py`'s actual gate.

    A zero-length interval means the scheduler is always "ready to fire" the
    instant `allow_trigger` is True — so if `render_frame`'s real
    `dialogue_ok = self._dialogue_visible(...) and not self._dialogue.is_open`
    expression is wired correctly, exactly one `show()` call happens (the
    first frame) and every subsequent frame is suppressed by `is_open`
    staying True (nothing ever dismisses it). A broken gate — e.g. one that
    forgot the `is_open` half — would call `show()` again on frame 2.
    """
    monkeypatch.setattr(sched_mod.random, "uniform", lambda a, b: 0.0)

    window = GameWindow()
    try:
        state = _game_state()

        calls: list[str] = []
        real_show = window._dialogue.show

        def spy_show(text, *a, **kw):
            calls.append(text)
            real_show(text, *a, **kw)

        window._dialogue.show = spy_show

        window.render_frame(state)
        assert window._dialogue.is_open, "first frame must fire — interval is zero"
        assert len(calls) == 1

        # Many more frames: `is_open` stays True the whole time (nothing
        # clicks it away), so the real gate must keep suppressing new fires
        # even though the scheduler's own interval is always satisfied.
        for _ in range(25):
            window.render_frame(state)
        assert len(calls) == 1, (
            "a pinned-open dialogue must suppress further scheduler fires "
            "via window.py's real dialogue_ok gate, not just in isolation"
        )
        assert window._dialogue.is_open

        # Once dismissed, the real gate must allow firing again — this is
        # "pause, don't queue": no backlog dumped, but not permanently wedged.
        window._dialogue.phase = dp_mod._CLOSED
        assert not window._dialogue.is_open
        window.render_frame(state)
        assert len(calls) == 2
    finally:
        window.close()


def test_pinned_dialogue_survives_food_panel_hide_and_reshow(monkeypatch):
    """Contract v12 point 4: FOOD/SHOP/RATES hide the popup, never dismiss it.

    Pins a known line/portrait directly, opens FOOD (which must hide it via
    `_dialogue_visible` going False, not by touching the panel itself), runs
    a frame while FOOD covers it, then closes FOOD and confirms the exact
    same frozen text/pose reappears — proving decision 027's frozen-state
    fix still holds under the new indefinite-pin lifetime v12 introduces.
    """
    monkeypatch.setattr(sched_mod.random, "uniform", lambda a, b: 999999.0)

    window = GameWindow()
    try:
        state = _game_state(hunger=42.0)
        # One frame first so `_feed_rect` etc. are sized; the scheduler's
        # interval is pinned far in the future so it can't fire on its own
        # and interfere with the line this test pins directly.
        window.render_frame(state)

        window._dialogue.show(
            "A pinned test line.", "healthy",
            stage="baby", hunger=42.0, hat=None, frame=0,
        )
        assert window._dialogue.is_open
        pinned_text = window._dialogue._text

        window._food.open(window._feed_rect.center)
        assert window._food.is_open

        # A frame while FOOD covers the popup: `_dialogue_visible` is False,
        # so `window.py` must neither update nor redraw it, nor touch its
        # frozen snapshot — only `show()` (not called here) may change it.
        window.render_frame(state)
        assert window._dialogue.is_open, "hiding must not dismiss the pin"
        assert window._dialogue._text == pinned_text
        assert window._dialogue._stage == "baby"
        assert window._dialogue._hunger == 42.0

        # Close FOOD outright (bypass its own closing animation — that is
        # FoodPanel's own concern, not what this test is checking) and
        # confirm the same pinned popup reappears untouched.
        window._food.phase = 0
        assert not window._food.is_open

        window.render_frame(state)
        assert window._dialogue.is_open
        assert window._dialogue._text == pinned_text
        assert window._dialogue._stage == "baby"
        assert window._dialogue._hunger == 42.0
    finally:
        window.close()


def _pin_fully_revealed_held(window: GameWindow, state) -> None:
    """Show a line, then force it past reveal and into `_HELD`.

    `window.render_frame` is called twice: once so `_dialogue.show()` has a
    frame to animate `_IN` from, and once more (after forcing phase/reveal
    state directly) so `window.py`'s own `draw()` call site runs at least
    once with the popup fully open — this is what populates
    `window._dialogue._panel_rect` with REAL, offset-corrected window
    coordinates via the exact code path `render_frame` uses in production,
    not a hand-rolled bypass.
    """
    window.render_frame(state)
    window._dialogue.show(
        "Click anywhere to close me.", "healthy",
        stage="baby", hunger=80.0, hat=None, frame=0,
    )
    window._dialogue.phase = dp_mod._HELD
    window._dialogue._elapsed_since_show = 9999.0
    window.render_frame(state)


def test_real_onscreen_click_dismisses_pinned_dialogue_via_render_frame(monkeypatch):
    """Bug-fix regression: a real MOUSEBUTTONUP at the popup's actual
    on-screen location, dispatched through `pygame.event.post` and consumed
    by `render_frame`'s own `pygame.event.get()` loop (the SAME dispatch path
    `window.py` uses in production, not `_dialogue.handle_event()` called
    directly as a bypass), must dismiss a fully-revealed, pinned-open popup.

    Before the coordinate-offset fix, `_panel_rect` was left in `inner`-local
    coordinates while `event.pos` arrives in real window coordinates, so a
    click at the popup's true on-screen centre would fail `collidepoint` and
    silently do nothing — the reported bug.
    """
    monkeypatch.setattr(sched_mod.random, "uniform", lambda a, b: 999999.0)

    window = GameWindow()
    try:
        state = _game_state()
        _pin_fully_revealed_held(window, state)
        assert window._dialogue.phase == dp_mod._HELD

        real_rect = window._dialogue._panel_rect
        assert real_rect is not None
        # Direct proof of the offset fix, decoupled from click-anywhere: a
        # fully-open popup is exactly PANEL_W x PANEL_H, anchored the same
        # way `draw()` computes it internally, so the expected real topleft
        # is independently derivable from the same public constants `draw()`
        # uses. `real_rect.x >= sr.x` alone (the old sanity check here) would
        # pass even with the offset never applied, since the inner-local x
        # for this panel size happens to equal SCREEN_X — this checks the
        # actual coordinates, not just a bound that offset-application would
        # trivially satisfy either way.
        sr = device_mod.screen_rect()
        expected_inner_x = (device_mod.SCREEN_W - dp_mod.PANEL_W) // 2
        expected_inner_y = (
            device_mod.SCREEN_H - 34 - 6 - dp_mod.PANEL_H
        )
        assert real_rect.topleft == (
            expected_inner_x + sr.x, expected_inner_y + sr.y,
        ), "offset must be added to the inner-local rect, not just bounded by it"

        real_pos = real_rect.center
        pygame.event.post(
            pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=real_pos)
        )
        window.render_frame(state)

        assert window._dialogue.phase == dp_mod._OUT, (
            "a real on-screen click at the popup's true composited location "
            "must dismiss it via window.py's real event-dispatch path"
        )
    finally:
        window.close()


def test_click_at_old_buggy_inner_local_position_also_dismisses(monkeypatch):
    """A point that would ONLY have registered as "inside" under the old,
    forgotten-offset math (i.e. `_panel_rect` computed with no offset at
    all) is a genuinely different, off-target real on-screen point — it does
    NOT land inside the correctly offset-corrected `_panel_rect`. Yet the new
    "click anywhere" behavior dismisses the popup anyway, since position no
    longer gates `handle_event()` at all.
    """
    monkeypatch.setattr(sched_mod.random, "uniform", lambda a, b: 999999.0)

    window = GameWindow()
    try:
        state = _game_state()
        _pin_fully_revealed_held(window, state)
        assert window._dialogue.phase == dp_mod._HELD

        real_rect = window._dialogue._panel_rect
        assert real_rect is not None
        sr = device_mod.screen_rect()

        # The rect a pre-fix `draw()` would have produced: same size, but
        # anchored at the inner surface's own (0, 0) origin rather than the
        # real screen recess's offset.
        buggy_local_rect = real_rect.move(-sr.x, -sr.y)
        assert buggy_local_rect != real_rect, (
            "test is only meaningful if the offset actually shifts the rect"
        )
        old_buggy_inside_pos = buggy_local_rect.center
        # That old-buggy "inside" point is a different real point than the
        # popup's true location, and must NOT be inside the corrected rect —
        # proving the offset fix, not just the "anywhere" relaxation, is
        # doing real work.
        assert not real_rect.collidepoint(old_buggy_inside_pos)

        pygame.event.post(
            pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=old_buggy_inside_pos
            )
        )
        window.render_frame(state)

        assert window._dialogue.phase == dp_mod._OUT, (
            "a click anywhere — including a point that is only 'inside' "
            "under the old buggy inner-local math — must dismiss the popup"
        )
    finally:
        window.close()
