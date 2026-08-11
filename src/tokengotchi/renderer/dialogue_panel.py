"""DialoguePanel — a small speech popup, Undertale-flavoured.

Modelled on FoodPanel's phase machine (eased scale-in, per-frame rebuild of a
cache-backed body). Unlike FoodPanel, though, its `_panel_rect` (computed in
`draw()`, offset-corrected to real window coordinates the same way
`FoodPanel`'s is) is NOT used to gate `handle_event()`: a click ANYWHERE in
the window while the popup is pinned open acts on it, not just a click
landing inside its own rect. It still is NOT a modal, though: FOOD/SHOP/RATES
remain fully operable while a dialogue is pinned open, and this panel's own
event handling never blocks or consumes an event meant for another layer
(`window.py` routes the same event to both). Text no longer reveals on a
fixed hold-duration timer either — once fully typewriter-revealed, the box
stays open indefinitely awaiting a click. A click while the text is still
revealing skips straight to the full line instead of dismissing (so an
impatient click never closes something half-read); a click once fully
revealed dismisses, playing the existing fade-out. Direction contract v12
("Dialogue attention"), superseding its original "outside click is a no-op"
clause per a later bug-fix decision: a click that does nothing when the
player expects the box to close reads as broken, not attentive.

The portrait is a scaled-to-fit render of the creature's own `draw_creature()`
at the stage/hunger/hat/frame frozen when the popup was triggered — the same
"free 8-bit portrait, zero new art" idea `window.py`'s shop-hat preview uses,
letterboxed instead of centre-cropped so a corpse pose's floor blood-pool
never gets clipped off. State is frozen at `show()` time, not read live on
every `draw()`, because `window.py` keeps updating this panel even while it
is hidden behind FOOD/SHOP/RATES — without freezing, a line written for
"dying" could still be on screen, over a "healthy" portrait, if the player
fed the creature while the box was hidden mid-hold. It duplicates rather
than imports `window.py`'s preview technique because `window.py` imports
this module; importing back would cycle.
"""
from __future__ import annotations

import pygame

from . import easing, theme, uikit
from .sprites import draw_creature

PANEL_W = 296
PANEL_H = 72
PORTRAIT = 52
PAD = 10

# Typewriter reveal speed varies by band to carry tone: brisk when healthy,
# halting when dying.
REVEAL_CPS = {
    "healthy": 42.0,
    "sad": 32.0,
    "distressed": 26.0,
    "horror": 20.0,
    "dying": 14.0,
}
_DEFAULT_CPS = 28.0

_CLOSED, _IN, _HELD, _OUT = 0, 1, 2, 3


def _wrap(s: str, max_w: int, size: int) -> list[str]:
    """Greedy word-wrap using real font metrics, not a character count."""
    words = s.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if not cur or uikit.text_w(trial, size) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


class DialoguePanel:
    def __init__(self) -> None:
        self.phase = _CLOSED
        self._t = 0.0
        self._elapsed_since_show = 0.0
        self._text = ""
        self._cps = _DEFAULT_CPS
        self._stage = "baby"
        self._hunger = 100.0
        self._hat: str | None = None
        self._frame = 0
        self._panel_rect: pygame.Rect | None = None
        self._revealed_this_frame = False

    @property
    def is_open(self) -> bool:
        return self.phase != _CLOSED

    def show(self, text: str, band: str, *, stage: str, hunger: float,
              hat: str | None, frame: int) -> None:
        """Start a popup. A falsy `text` is a silent no-op, never a blank box.

        The creature's pose is snapshotted here, not read live in `draw()` —
        see the module docstring for why (a hidden panel's frozen text must
        never end up rendered over a portrait that has since moved on).
        """
        if not text:
            return
        self._text = text
        self._cps = REVEAL_CPS.get(band, _DEFAULT_CPS)
        self._elapsed_since_show = 0.0
        self._stage, self._hunger, self._hat, self._frame = stage, hunger, hat, frame
        self.phase, self._t = _IN, 0.0

    def update(self, dt: float) -> None:
        if self.phase == _CLOSED:
            return
        self._revealed_this_frame = False
        self._t += dt
        self._elapsed_since_show += dt
        span_in = max(1e-6, theme.DUR_PANEL_IN * max(theme.ANIM_SCALE, 1e-6))
        span_out = max(1e-6, theme.DUR_PANEL_OUT * max(theme.ANIM_SCALE, 1e-6))
        if self.phase == _IN and self._t >= span_in:
            self.phase, self._t = _HELD, 0.0
        elif self.phase == _OUT and self._t >= span_out:
            self.phase, self._t = _CLOSED, 0.0
        # _HELD has no timer-driven exit: it holds indefinitely until a click
        # (see handle_event) dismisses it. Direction contract v12.

    def _progress(self) -> float:
        span_in = max(1e-6, theme.DUR_PANEL_IN * max(theme.ANIM_SCALE, 1e-6))
        span_out = max(1e-6, theme.DUR_PANEL_OUT * max(theme.ANIM_SCALE, 1e-6))
        if self.phase == _IN:
            return min(1.0, self._t / span_in)
        if self.phase == _OUT:
            return max(0.0, 1.0 - self._t / span_out)
        return 1.0 if self.phase == _HELD else 0.0

    def draw(self, inner: pygame.Surface, offset: tuple[int, int] = (0, 0)) -> None:
        if self.phase == _CLOSED:
            self._panel_rect = None
            return

        k = self._progress()
        body = self._body()
        s = easing.ease_out_back(k) if self.phase == _IN else k
        w = max(1, int(PANEL_W * s))
        h = max(1, int(PANEL_H * s))
        x = (inner.get_width() - w) // 2
        # Anchor to the hunger readout's top edge (device.py's
        # `inner.get_height() - 34`), not the screen bottom, so an expanding
        # popup never paints over the stat the whole feature is about.
        bottom = inner.get_height() - 34 - 6
        y = bottom - h
        inner.blit(pygame.transform.smoothscale(body, (w, h)), (x, y))
        self._panel_rect = pygame.Rect(x + offset[0], y + offset[1], w, h)

    # ── input ───────────────────────────────────────────────────────────────
    def handle_event(self, event: pygame.event.Event) -> None:
        """Click-during-reveal skips to full text; click-after-reveal
        dismisses. Acts on a qualifying click ANYWHERE in the window, not
        just one landing inside `_panel_rect` — per a bug-fix decision
        superseding direction v12's original "outside click is a no-op"
        clause, a click that visibly does nothing reads as broken. This
        method still never consumes/blocks the event for other UI: it only
        ever mutates this panel's own state, so `window.py` is free to keep
        routing the same event to FOOD/SHOP/RATES/main afterwards.

        `_revealed_this_frame` guards against pygame handing us two
        MOUSEBUTTONUP events in the same frame's batch (plausible during a
        frame hitch): without it, the first event's reveal-click and the
        second event's dismiss-click could both land before a single
        `draw()` ever shows the user the fully revealed text. It is reset
        once per `update()` call, which `window.py` calls exactly once per
        frame after all of that frame's events are processed."""
        if self.phase == _CLOSED:
            return
        if event.type != pygame.MOUSEBUTTONUP or event.button != 1:
            return
        # No position gate here, deliberately: this fires for a qualifying
        # click ANYWHERE in the window, not just one inside `_panel_rect`.
        # Epsilon tolerance: `len(text) / cps * cps` isn't always >= len(text)
        # in floating point, which would otherwise strand the panel in _HELD
        # forever waiting for a `fully_revealed` that mere re-multiplication
        # can never quite reach.
        fully_revealed = self._elapsed_since_show * self._cps >= len(self._text) - 1e-6
        if not fully_revealed:
            # Bias half a character past the boundary so the stored value
            # reliably satisfies the check above on its own, without relying
            # on a subsequent update(dt) tick to nudge it over.
            self._elapsed_since_show = (len(self._text) + 0.5) / self._cps
            self._revealed_this_frame = True
        elif self.phase in (_IN, _HELD) and not self._revealed_this_frame:
            # `_IN` is included, not just `_HELD`: a short line can finish its
            # typewriter reveal before the ~0.22s open-scale animation does,
            # so restricting this to `_HELD` alone would silently swallow a
            # click during that window — reintroducing the exact "clicking
            # the box does nothing" bug for any text a few characters shorter
            # than today's.
            self.phase, self._t = _OUT, 0.0

    def _body(self) -> pygame.Surface:
        surf = uikit.round_rect(
            (PANEL_W, PANEL_H), theme.RADIUS_MD, theme.SURFACE,
            border=theme.BORDER, gradient_to=theme.SURFACE_SUNKEN,
            top_highlight=26,
        ).copy()

        sw, sh = (100, 110) if self._stage.lower() == "adult" else (80, 90)
        cell = pygame.Surface((sw, sh), pygame.SRCALPHA)
        draw_creature(cell, 0, 0, stage=self._stage, hat=self._hat,
                      frame=self._frame, dormant=False, hunger=self._hunger)
        # Letterbox rather than crop: a hard square crop from (0, 0) clips
        # the "dying" pose's floor blood-pool, which sits below the fold.
        fit = min(PORTRAIT / sw, PORTRAIT / sh)
        fw, fh = max(1, round(sw * fit)), max(1, round(sh * fit))
        scaled = pygame.transform.smoothscale(cell, (fw, fh))
        portrait = pygame.Surface((PORTRAIT, PORTRAIT), pygame.SRCALPHA)
        portrait.blit(scaled, ((PORTRAIT - fw) // 2, (PORTRAIT - fh) // 2))

        px, py = PAD, (PANEL_H - PORTRAIT) // 2
        surf.blit(uikit.round_rect(
            (PORTRAIT + 6, PORTRAIT + 6), theme.RADIUS_SM, theme.SURFACE_SUNKEN,
            border=theme.BORDER_SUBTLE), (px - 3, py - 3))
        surf.blit(portrait, (px, py))

        text_x = px + PORTRAIT + PAD
        text_w = PANEL_W - PAD - text_x
        shown = self._text[:max(0, int(self._elapsed_since_show * self._cps))]
        ty = PAD
        for line in _wrap(shown, text_w, theme.FONT_BODY)[:3]:
            line_surf = uikit.text(line, theme.TEXT, theme.FONT_BODY)
            surf.blit(line_surf, (text_x, ty))
            ty += line_surf.get_height() + 2

        return surf
