"""DialoguePanel click-to-reveal / click-to-dismiss behavior.

Direction contract v12 ("Dialogue attention") removes the old
hold-duration auto-close timer: `_HELD` now waits indefinitely for a click.
A click while the text is still typewriter-revealing skips straight to the
full line (does not dismiss); a click once fully revealed dismisses into
`_OUT`. A later bug-fix decision supersedes v12's original "outside click is
a no-op" clause: `handle_event()` no longer gates on `_panel_rect` at all, so
a qualifying click ANYWHERE acts on the popup (reveal-skip or dismiss),
never a no-op.
"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from tokengotchi.renderer.dialogue_panel import (
    DialoguePanel, _CLOSED, _HELD, _IN, _OUT,
)


@pytest.fixture(scope="module", autouse=True)
def _pygame_video():
    pygame.init()
    pygame.display.set_mode((10, 10))
    yield
    pygame.quit()


def _make_shown_panel(text="Hello there friend"):
    """Show a panel and advance it into `_HELD` (animation-in complete),
    before the text has fully typewriter-revealed."""
    p = DialoguePanel()
    p.show(text, "healthy", stage="baby", hunger=80.0, hat=None, frame=0)
    # DUR_PANEL_IN is short; a handful of small steps is enough to clear _IN.
    for _ in range(10):
        p.update(0.05)
        if p.phase == _HELD:
            break
    assert p.phase == _HELD
    return p


def _draw(p: DialoguePanel) -> pygame.Surface:
    surf = pygame.Surface((348, 250))
    p.draw(surf)
    return surf


def _click(p: DialoguePanel, pos) -> None:
    p.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def test_click_during_reveal_completes_text_but_stays_open():
    p = _make_shown_panel()
    assert p._elapsed_since_show * p._cps < len(p._text)  # not fully revealed yet
    _draw(p)
    assert p._panel_rect is not None
    _click(p, p._panel_rect.center)
    assert p._elapsed_since_show * p._cps >= len(p._text)  # now fully revealed
    assert p.phase == _HELD  # did not dismiss


def test_click_after_full_reveal_dismisses_to_out():
    p = _make_shown_panel()
    # Advance enough for the typewriter to finish, but not enough for a
    # hold-duration timer to matter (there is none any more).
    for _ in range(200):
        p.update(0.05)
        if p._elapsed_since_show * p._cps >= len(p._text):
            break
    assert p.phase == _HELD
    _draw(p)
    assert p._panel_rect is not None
    _click(p, p._panel_rect.center)
    assert p.phase == _OUT


def test_click_outside_panel_rect_still_dismisses():
    """Superseding v12: a click anywhere acts on the popup, not just one
    landing inside `_panel_rect` — an "outside" click on a fully-revealed
    popup now dismisses it exactly like an "inside" click would."""
    p = _make_shown_panel()
    for _ in range(200):
        p.update(0.05)
        if p._elapsed_since_show * p._cps >= len(p._text):
            break
    assert p.phase == _HELD
    _draw(p)
    assert p._panel_rect is not None
    outside = (p._panel_rect.right + 50, p._panel_rect.bottom + 50)
    _click(p, outside)
    assert p.phase == _OUT


def test_click_during_open_animation_after_already_fully_revealed_dismisses():
    """Regression: a short line's typewriter reveal can finish before the
    ~0.22s open-scale animation does, leaving the panel in `_IN` with
    `fully_revealed` already true. A qualifying click in that exact window
    must still dismiss, not silently no-op — a phase check that only fired
    on `_HELD` would swallow this click and reintroduce the reported "clicking
    the box does nothing" bug for any line short enough to reveal that fast.
    """
    p = DialoguePanel()
    p.show("Hi", "healthy", stage="baby", hunger=80.0, hat=None, frame=0)
    p.update(0.05)
    assert p.phase == _IN, "test setup must catch the panel mid open-animation"
    assert p._elapsed_since_show * p._cps >= len(p._text), \
        "test setup must catch the text already fully revealed"
    _draw(p)
    assert p._panel_rect is not None
    _click(p, p._panel_rect.center)
    assert p.phase == _OUT


def test_panel_never_auto_closes_while_held_no_matter_how_long():
    p = _make_shown_panel()
    # Simulate a full minute of unattended time while _HELD and unclicked.
    elapsed = 0.0
    step = 0.5
    while elapsed < 60.0:
        p.update(step)
        elapsed += step
    assert p.phase != _CLOSED
    assert p.phase == _HELD
