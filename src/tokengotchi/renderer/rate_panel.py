"""The rate detail view — why the pet is as hungry as it is.

Deliberately a READ-ONLY panel. Everything on it is a value the game already
computed and persisted; there is nothing to click but the close button. That
is what lets it reuse `ShopPanel`'s open/close envelope without inheriting any
of its paging, hover or purchase machinery.

The closing line is the whole feature in one sentence, and it is the actual
transparency requirement: a number you cannot explain is not transparency,
it is decoration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pygame

from ..config import BITS_RATIO, ECHOES_RATIO
from ..engine import rates as raterules
from . import easing, skins as skinmod, theme, uikit

# STAYS INSIDE THE SCREEN. Growing the panel over the whole case buys space
# but loses the thing that makes it feel part of the device. It fits at screen
# size because legibility is fixed at the source — the UI face, not the
# layout. See uikit.font().
PANEL_W = 342        # the screen is 348 wide
PANEL_H = 238        # ...and 250 tall
ROW_H = 24
LABEL_X = 12
VALUE_X = 138
# FONT_CAPTION is 11px and the wrong instrument for a dense read-out: at that
# size, bold, the stems thicken but the sidebearings do not, so the words run
# together. Widening the ROWS does nothing, because the complaint is inside
# the word. One step up to FONT_BODY, plus a pixel of tracking on the labels.
FONT = theme.FONT_BODY       # 13px in Tahoma reads better than 15 in Segoe
FACE = uikit.READOUT_STACK   # this table only — the rest of the UI stays default
TRACK = 1


class RatePanel:
    """Same phase machine as the shop, minus everything the shop needs."""

    def __init__(self) -> None:
        self.phase = 0            # 0 closed, 1 opening, 2 open, 3 closing
        self._t = 0.0
        self._origin = (200, 300)
        self._close_rect: pygame.Rect | None = None
        self._panel_rect = pygame.Rect(0, 0, 0, 0)

    # ── state ───────────────────────────────────────────────────────────────
    @property
    def is_open(self) -> bool:
        return self.phase != 0

    @property
    def accepts_input(self) -> bool:
        return self.phase == 2

    def open(self, origin=None) -> None:
        if self.phase in (1, 2):
            return
        if origin:
            self._origin = origin
        self.phase, self._t = 1, 0.0

    def close(self) -> None:
        if self.phase in (0, 3):
            return
        self.phase, self._t = 3, 0.0

    def toggle(self, origin=None) -> None:
        self.close() if self.is_open else self.open(origin)

    def update(self, dt: float) -> None:
        self._t += dt
        span = max(1e-6, theme.DUR_PANEL_IN * max(theme.ANIM_SCALE, 1e-6))
        if self.phase == 1 and self._t >= span:
            self.phase, self._t = 2, 0.0
        elif self.phase == 3 and self._t >= span:
            self.phase, self._t = 0, 0.0

    def _progress(self) -> float:
        span = max(1e-6, theme.DUR_PANEL_IN * max(theme.ANIM_SCALE, 1e-6))
        if self.phase == 1:
            return min(1.0, self._t / span)
        if self.phase == 3:
            return max(0.0, 1.0 - self._t / span)
        return 1.0 if self.phase == 2 else 0.0

    def handle_event(self, event) -> bool:
        if not self.accepts_input:
            return False
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE,
                                                          pygame.K_r):
            self.close()
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._close_rect and self._close_rect.collidepoint(event.pos):
                self.close()
                return True
            if self._panel_rect and not self._panel_rect.collidepoint(event.pos):
                self.close()
                return True
            return True
        return False

    # ── paint ───────────────────────────────────────────────────────────────
    def draw(self, inner: pygame.Surface, game_state, skin=None,
             offset=(0, 0)) -> None:
        if self.phase == 0:
            return
        sk = skin or skinmod.DEFAULT
        k = self._progress()

        scrim = pygame.Surface(inner.get_size(), pygame.SRCALPHA)
        scrim.fill((0, 0, 0, int(150 * k)))
        inner.blit(scrim, (0, 0))

        body = self._body(game_state, sk)
        s = easing.ease_out_back(k) if self.phase == 1 else k
        w = max(1, int(PANEL_W * s))
        h = max(1, int(PANEL_H * s))
        scaled = pygame.transform.smoothscale(body, (w, h))
        x = (inner.get_width() - w) // 2
        y = (inner.get_height() - h) // 2
        inner.blit(scaled, (x, y))
        self._panel_rect = pygame.Rect(x + offset[0], y + offset[1], w, h)
        if self._close_rect is not None and s > 0.9:
            self._close_rect = pygame.Rect(
                x + offset[0] + PANEL_W - 30, y + offset[1] + 6, 24, 20)

    def _body(self, gs, sk) -> pygame.Surface:
        r = gs.rates
        # See food_panel._body: round_rect() hands back a cached, SHARED
        # Surface, and this function draws dynamic content on top of it, so
        # a bare reference here would leave stale digits burned into the
        # cache for the next hit. Copy it first.
        surf = uikit.round_rect((PANEL_W, PANEL_H), theme.RADIUS_MD, sk.edge,
                                border=sk.phosphor).copy()
        ph, dim = sk.phosphor, sk.meter[1]

        def put(x, y, s, col=None, bold=True, track=0, size=FONT):
            surf.blit(uikit.text(s, col or ph, size, bold=bold, track=track,
                                 face=FACE), (x, y))

        put(LABEL_X, 9, "RATES", track=2, size=theme.FONT_LABEL)
        self._close_rect = pygame.Rect(PANEL_W - 30, 6, 26, 22)
        put(PANEL_W - 26, 9, "X", dim, size=theme.FONT_LABEL)
        pygame.draw.line(surf, sk.phosphor, (12, 32), (PANEL_W - 12, 32))

        now = datetime.now(timezone.utc)
        earn, drain = r.earn_mult, r.drain_mult
        tpb = max(1, int(round(BITS_RATIO / max(0.01, earn))))
        tpe = max(1, int(round(ECHOES_RATIO)))
        pace = raterules.pace(gs.usage_history, now)
        today = next((u.output_tokens for u in gs.usage_history
                      if u.date == raterules.day_key(now)), 0)

        def arrow(cur, prev):
            return "+" if cur > prev + 1e-6 else ("-" if cur < prev - 1e-6 else "=")

        # Units are spelled out and every label says what the number IS, not
        # what the code calls it. Shorthand like "T" or "BASELINE" lets you
        # read the whole panel and still not know what it is telling you,
        # which is the opposite of the transparency this feature exists for.
        rows = [
            ("EARN", f"{tpb:,} Tokens = 1 BIT",
             f"x{earn:.2f} {arrow(earn, r.prev_earn_mult)}"),
            # "fixed" goes in the empty LABEL column, not the right one:
            # right-aligned it collides with the end of the value.
            ("FIXED", f"{tpe:,} Tokens = 1 ECHO", ""),
            ("APPETITE", f"full bar in {raterules.hours_to_empty(100.0, drain):.1f}h",
             f"x{drain:.2f} {arrow(drain, r.prev_drain_mult)}"),
            # The qualifier goes INSIDE the value on these two. With a wider
            # font and a pixel of tracking the labels reach the value column,
            # and a right-aligned third field then collides with the value —
            # two columns fit on a 344px panel, not three.
            ("YOUR AVERAGE",
             f"{int(r.baseline_output_per_day):,} Tokens/day, 7 days", ""),
            ("TODAY", f"{today:,} Tokens"
             + ("" if pace is None else f" = {int(pace * 100)}%"), ""),
        ]
        y = 40
        for label, mid, right in rows:
            if label:
                put(LABEL_X, y, label, dim, track=TRACK)
            put(VALUE_X, y, mid)
            if right:
                w = uikit.text(right, ph, FONT, bold=True, face=FACE)
                surf.blit(w, (PANEL_W - 12 - w.get_width(), y))
            y += ROW_H

        nxt = raterules.period_start(now) + timedelta(
            hours=raterules.PERIOD_HOURS)
        mins = max(0, int((nxt - now).total_seconds() // 60))
        put(LABEL_X, y, "RATES UPDATE", dim, track=TRACK)
        put(VALUE_X, y, f"in {mins // 60}h {mins % 60:02d}m")
        y += ROW_H

        # The label has to name what empties, not just when. It is the hunger
        # bar, it is measured in app-open time, and both of those are
        # load-bearing because the pet is paused while the window is shut.
        hrs = raterules.hours_to_empty(gs.creature.hunger, drain)
        put(LABEL_X, y, "PET STARVES", dim, track=TRACK)
        put(VALUE_X, y, f"after {int(hrs)}h {int((hrs % 1) * 60):02d}m open")
        y += ROW_H + 2

        # No sparkline. It is the least useful thing this panel could carry
        # and it costs 28px of height that the type needs — on a read-out
        # this dense the space buys legible size, not decoration.
        if r.calibrating:
            tail = "Calibrating. Rates hold at 1.00x until there is history."
        elif r.resting:
            tail = "Resting: no tokens for 48h, so the pet is not hungry."
        else:
            tail = "Hunger and earnings only run while this window is open."
        put(LABEL_X, PANEL_H - 22, tail, dim, bold=False,
            size=theme.FONT_CAPTION)
        return surf
