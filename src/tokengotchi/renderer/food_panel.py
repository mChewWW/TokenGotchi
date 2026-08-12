"""The food menu — six items, one click, closes on choose.

Modelled on the shop's envelope rather than the shop itself: this has no
paging, no ownership, no preview and no tabs, because food is spent rather than
owned. What it does share is the phase machine and the scale-from-origin
opening, so it feels like the same object as the shop.

A GRID OF CARDS, NOT A LIST OF ROWS. Six items read as a menu of things to
look at rather than a ledger of numbers to compare, so each food gets its own
square slot for its icon plus its name, cost and hunger value underneath —
closer to a vending machine than a spreadsheet.
"""
from __future__ import annotations

import pygame

from ..engine import food as menu
from . import easing, fooditems, skins as skinmod, theme, uikit

PANEL_W = 342
PANEL_H = 238        # matches RATES so the three overlays share one box size
GRID_COLS = 3
GRID_ROWS = 2
# GRID_TOP was 38 at the old PANEL_H=248. Dropping the box to 238 (to match
# RATES) removed 10px from the grid; the icon slot is capped at MAX_SLOT so it
# can't absorb the loss, so the grid start moves up to keep the same ~3px gap
# between a card's stat row and the next row (see test_food_panel).
GRID_TOP = 32
GRID_MARGIN = 10
GRID_GAP = 8
FACE = uikit.READOUT_STACK

# The icon's own 16x16 art canvas is blitted at an integer scale inside the
# slot square (see fooditems.py's docstring on why: anything non-integer
# blurs the pixel art). Foods like bread and apple happen to carry a built-in
# transparent margin in their own art, so a too-tight canvas-vs-slot fit was
# invisible for them; foods without that margin (cookie, cake, steak) had
# their opaque pixels sit flush against the slot's rounded border/corners and
# visually spilled past it. SLOT_INSET and ICON_PAD both exist so every food
# gets real, visible clearance from its slot regardless of its own art.
SLOT_INSET = 25  # shrink applied to the smaller cell dimension to get `slot`
ICON_PAD = 6     # reserved clearance between the icon canvas and `slot`
# `slot` also feeds the per-card name/cost/gain text block *below* it
# (`sy + slot + ...`), so growing PANEL_H to give that text more breathing
# room from the next grid row would, without a cap, just keep re-growing
# `slot` too and eat the very room it was meant to free up. 54 is the exact
# value needed for icon_scale 3 at ICON_PAD 6 (see the fix above) — capping
# there lets extra PANEL_H flow to the text gap instead of the icon.
MAX_SLOT = 54


def _wrap(s: str, max_w: int, size: int, face=None) -> list[str]:
    """Greedy word-wrap using the real font metrics, not a character count."""
    words = s.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if not cur or uikit.text_w(trial, size, face=face) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


class FoodPanel:
    def __init__(self) -> None:
        self.phase = 0            # 0 closed, 1 opening, 2 open, 3 closing
        self._t = 0.0
        self._origin = (100, 338)
        self._rows: list[tuple[str, pygame.Rect]] = []
        self._close_rect: pygame.Rect | None = None
        self._panel_rect = pygame.Rect(0, 0, 0, 0)
        self._hover: str | None = None
        self._reject: dict[str, float] = {}

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
        self.phase, self._t, self._hover = 1, 0.0, None

    def close(self) -> None:
        if self.phase in (0, 3):
            return
        self.phase, self._t = 3, 0.0

    def toggle(self, origin=None) -> None:
        self.close() if self.is_open else self.open(origin)

    def update(self, dt: float) -> None:
        self._t += dt
        for k in list(self._reject):
            self._reject[k] += dt
            if self._reject[k] > theme.DUR_HOVER * 3:
                del self._reject[k]
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

    # ── input ───────────────────────────────────────────────────────────────
    def handle_event(self, event, bits: int) -> list[str]:
        """Returns actions for the main loop. Choosing a food closes the menu."""
        if not self.accepts_input:
            return []
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE,
                                                          pygame.K_f):
            self.close()
            return []
        if event.type == pygame.MOUSEMOTION:
            self._hover = next((fid for fid, r in self._rows
                                if r.collidepoint(event.pos)), None)
            return []
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._close_rect and self._close_rect.collidepoint(event.pos):
                self.close()
                return []
            for fid, r in self._rows:
                if r.collidepoint(event.pos):
                    if menu.BY_ID[fid].cost > bits:
                        # Never a silent dead click: reject visibly.
                        self._reject[fid] = 0.0
                        return []
                    self.close()
                    return [f"eat:{fid}"]
            if self._panel_rect and not self._panel_rect.collidepoint(event.pos):
                self.close()
        return []

    # ── paint ───────────────────────────────────────────────────────────────
    def draw(self, inner: pygame.Surface, bits: int, hunger: float,
             skin=None, offset=(0, 0)) -> None:
        if self.phase == 0:
            self._rows = []
            return
        sk = skin or skinmod.DEFAULT
        k = self._progress()

        scrim = pygame.Surface(inner.get_size(), pygame.SRCALPHA)
        scrim.fill((0, 0, 0, int(150 * k)))
        inner.blit(scrim, (0, 0))

        body, rows = self._body(bits, hunger, sk)
        s = easing.ease_out_back(k) if self.phase == 1 else k
        w = max(1, int(PANEL_W * s))
        h = max(1, int(PANEL_H * s))
        x = (inner.get_width() - w) // 2
        y = (inner.get_height() - h) // 2
        inner.blit(pygame.transform.smoothscale(body, (w, h)), (x, y))
        self._panel_rect = pygame.Rect(x + offset[0], y + offset[1], w, h)

        if s > 0.98:
            ox, oy = x + offset[0], y + offset[1]
            self._rows = [(fid, r.move(ox, oy)) for fid, r in rows]
            self._close_rect = pygame.Rect(ox + PANEL_W - 30, oy + 6, 26, 22)
        else:
            self._rows = []

    def _body(self, bits: int, hunger: float, sk):
        # round_rect() is cache-backed and hands back a SHARED Surface — every
        # blit below (the bits balance, hover states, ...) draws dynamic
        # content, so mutating that shared surface in place leaves it dirty
        # for the next cache hit and the old bits figure shows through the
        # new one. Copy it first so this call owns a private canvas.
        surf = uikit.round_rect((PANEL_W, PANEL_H), theme.RADIUS_MD, sk.edge,
                                border=sk.phosphor).copy()
        ph, dim = sk.phosphor, sk.meter[1]

        def put(x, y, s, col=None, size=theme.FONT_BODY, bold=True, track=0):
            surf.blit(uikit.text(s, col or ph, size, bold=bold, track=track,
                                 face=FACE), (x, y))

        put(12, 9, "FOOD", size=theme.FONT_LABEL, track=2)
        bal = uikit.text(f"{bits} B", theme.BITS, theme.FONT_LABEL, bold=True,
                         face=FACE)
        surf.blit(bal, (PANEL_W - 38 - bal.get_width(), 9))
        put(PANEL_W - 26, 9, "X", dim, size=theme.FONT_LABEL)
        pygame.draw.line(surf, sk.phosphor, (12, 28), (PANEL_W - 12, 28))

        footer_h = 34
        grid_bottom = PANEL_H - footer_h
        cell_w = (PANEL_W - GRID_MARGIN * 2 - GRID_GAP * (GRID_COLS - 1)) \
            // GRID_COLS
        cell_h = (grid_bottom - GRID_TOP - GRID_GAP * (GRID_ROWS - 1)) \
            // GRID_ROWS
        slot = min(max(30, min(cell_w, cell_h) - SLOT_INSET), MAX_SLOT)
        icon_scale = max(2, (slot - ICON_PAD) // fooditems.GRID)
        icon_px = fooditems.GRID * icon_scale

        rows = []
        for i, f in enumerate(menu.FOODS):
            col, row = i % GRID_COLS, i // GRID_COLS
            cell = pygame.Rect(
                GRID_MARGIN + col * (cell_w + GRID_GAP),
                GRID_TOP + row * (cell_h + GRID_GAP),
                cell_w, cell_h,
            )
            afford = bits >= f.cost
            hot = self._hover == f.id and afford
            shake = int(easing.shake_offset(self._reject[f.id], theme.DUR_HOVER * 3) * 6) \
                if f.id in self._reject else 0
            r = cell.move(shake, 0)

            surf.blit(uikit.round_rect(
                (r.w, r.h), theme.RADIUS_SM,
                sk.base if not hot else sk.edge,
                border=ph if hot else None), r.topleft)

            sx = r.x + (r.w - slot) // 2
            sy = r.y + 3
            surf.blit(uikit.round_rect((slot, slot), theme.RADIUS_SM,
                                       sk.edge, border=ph), (sx, sy))
            fooditems.draw(surf, f.id, sx + (slot - icon_px) // 2,
                           sy + (slot - icon_px) // 2, icon_scale)

            name_col = ph if afford else dim
            name = uikit.text(f.name, name_col, theme.FONT_CAPTION, bold=True,
                              face=FACE)
            surf.blit(name, (r.x + (r.w - name.get_width()) // 2, sy + slot + 3))

            stat_y = sy + slot + 16
            cost = uikit.text(f"{f.cost} B", theme.BITS if afford else dim,
                              theme.FONT_CAPTION, bold=True, face=FACE)
            surf.blit(cost, (r.x + 4, stat_y))
            gain = uikit.text(f"+{f.hunger:.0f}", name_col,
                              theme.FONT_CAPTION, bold=True, face=FACE)
            surf.blit(gain, (r.right - 4 - gain.get_width(), stat_y))

            rows.append((f.id, cell))

        hovered = menu.BY_ID.get(self._hover) if self._hover else None
        if hovered is not None:
            self._draw_caption(surf, hovered, grid_bottom, sk)

        return surf, rows

    def _draw_caption(self, surf: pygame.Surface, f, grid_bottom: int, sk) -> None:
        """The hovered food's blurb, in the footer strip below the grid.

        Not shown by default: this is detail you go looking for by hovering,
        not noise on screen at all times. An overlay covering the whole grid
        would block picking any OTHER food while reading about one — a menu
        you can't compare against itself while hovering isn't a menu. The
        footer strip is reserved space below the cards, so a caption there
        never covers a card.
        """
        pad = 10
        # +6, not +4: at PANEL_H=238 the bottom row's stat text reaches a few
        # px into this footer strip, so the caption starts just below it.
        y = grid_bottom + 6
        for line in _wrap(f.blurb, PANEL_W - pad * 2, theme.FONT_CAPTION,
                          face=FACE)[:2]:
            surf.blit(uikit.text(line, sk.meter[1], theme.FONT_CAPTION,
                                 bold=False, face=FACE), (pad, y))
            y += theme.FONT_CAPTION + 2
