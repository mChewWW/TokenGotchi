# renderer — Pygame drawing layer: sprites, HUD, animations.
"""TokenGotchi renderer package.

Public API:
    GameWindow — manages the Pygame window and the main render loop.

Sub-modules:
    sprites  — programmatic pixel-art creature drawing (no image files).
    device   — the shell + CRT screen; the readout lives inside the
               screen and the currency sits on the case.
    shop_panel — modal shop overlay (rows, ownership, animation).
    theme    — design tokens; uikit — anti-aliased primitives.
    privacy  — first-launch privacy notice overlay.
    window   — GameWindow class (re-exported here for convenience).
    _stub    — StubGameState for renderer integration testing.
"""

from .window import GameWindow

__all__ = ["GameWindow"]
