"""The shop — a modal panel over the live window.

A stateful object rather than a free draw function, which is a departure from
the rest of the renderer. It has to be: transitions, hover and press are all
time-based state that has to live somewhere between frames, and it must never
live in GameState (that is persisted to disk).

Layout is a list of full-width rows, not a grid. At 400px wide a row has room
for a live preview, a name, a blurb and a price with large hit targets; grid
cells at this width would be cramped and are harder to stagger.
"""
from __future__ import annotations

from enum import Enum

import pygame

from . import easing, theme, uikit
from ..shop import catalogue
from ..shop.catalogue import Currency, ItemKind


class Phase(Enum):
    CLOSED = "closed"
    OPENING = "opening"
    OPEN = "open"
    CLOSING = "closing"


class ItemState(Enum):
    """The states any shop item can be in. Each must be distinguishable in a
    *still* frame — animation communicates transitions, never state."""
    AFFORDABLE = "affordable"
    UNAFFORDABLE = "unaffordable"
    OWNED = "owned"
    EQUIPPED = "equipped"


def _is_screen(item_id: str) -> bool:
    item = catalogue.get(item_id)
    return item is not None and item.kind is ItemKind.SCREEN


def _is_shell(item_id: str) -> bool:
    item = catalogue.get(item_id)
    return item is not None and item.kind is ItemKind.SHELL


def hat_hidden_reason(stage: str, hunger: float) -> str | None:
    """Why a hat would not be drawn right now, or None if it would be.

    `sprites.draw_creature` returns before the hat layer in two cases: eggs
    never wear hats, and a dying creature (hunger < 10) lies on its side with
    no head to hang one on. Without this check the shop takes 15 ECHOES in
    either state and shows nothing for it.
    """
    if (stage or "").lower() == "egg":
        return "eggs can't wear hats"
    if hunger < 10.0:
        return "not while starving"
    return None


# Sized to sit INSIDE the device screen (348x250). A modal floating over the
# CRT reads as a flat card pasted on an object and breaks the illusion outright.
PANEL_W = 316
ROW_H = 58
HEADER_H = 42
FOOTER_H = 32     # taller: carries the pager

# The screen is 250px and body_h = HEADER + n*ROW + FOOTER + 8. Three rows
# overflow by 2px, so the catalogue is PAGED rather than grown. Paging beats
# scrolling here: there is no scrollbar affordance to draw at this size, and a
# page count tells you how much catalogue exists, which a scroll thumb does not.
PAGE_SIZE = 3
ROW_H_PAGED = 46      # sized so three rows fit; leaves no room for a blurb
TAB_H = 22

# Page-turn travel, in pixels. PANEL_W * 0.55 = 173px decayed LINEARLY over
# 0.16s is 36px per frame at 30fps inside a 316px panel — that reads as an
# aggressive shake, not a page turn.
# A page turn should read as a nudge, not a throw.
SLIDE_PX = 22

# Synthetic "Default" row, pinned to the top of every category.
#
# Without it, reverting means finding whichever item is equipped and clicking
# it to un-equip — an action with no visible affordance. Selecting "Default" is
# the same idea expressed as a thing you can point at.
DEFAULT_ID = "__default__"

# Rarity accents. Conventional tiers so the colour is legible without a legend.
RARITY_COLOR = {
    "uncommon": (108, 220, 150),
    "epic": (176, 128, 255),
    "legendary": (255, 176, 66),
}
ICON = 36             # preview cell. At 42x47 in a 42px row it overflows
                      # the row by 8px and sits proud of its own card.

# Categories. The catalogue is filtered before it is paged, so "page 2 of 3"
# means two pages of THIS kind rather than two pages of everything.
TABS: tuple[tuple[str, object], ...] = (
    ("HATS", ItemKind.HAT),
    ("SCREEN", ItemKind.SCREEN),
    ("CASE", ItemKind.SHELL),
)


class ShopPanel:
    def __init__(self) -> None:
        self.phase = Phase.CLOSED
        self._t = 0.0                      # seconds inside the current phase
        self._tweens = easing.Tweens()
        self._hover: str | None = None
        self._pressed: str | None = None
        self._rows: list[tuple[str, pygame.Rect]] = []
        self._close_rect: pygame.Rect | None = None
        self._prev_rect: pygame.Rect | None = None
        self._next_rect: pygame.Rect | None = None
        self._panel_rect = pygame.Rect(0, 0, 0, 0)
        self._origin = (200, 225)          # animate from the trigger button
        self._page = 0
        self._tab = 0
        self._tab_rects: list = []
        self._slide = 0.0      # page-change animation, -1..1
        self._fade_only = False
        self._preview_on = False
        self._peek_rect = None
        self._reject: dict[str, float] = {}   # item_id -> elapsed shake time
        self._flash: dict[str, float] = {}    # item_id -> elapsed flash time

    # ── State ───────────────────────────────────────────────────────────────

    @property
    def is_open(self) -> bool:
        return self.phase is not Phase.CLOSED

    def preview_item(self) -> str | None:
        """The item to show live on the device — only while PREVIEW is armed.

        A thumbnail cannot honestly show a screen skin (it would be a picture
        of a display, drawn on that display, under the active skin's own
        scanlines), so the preview is the real hardware. But applying it on
        mere hover makes the whole device flicker as the cursor crosses rows,
        so it sits behind an explicit toggle, OFF by default.
        """
        if self.phase is not Phase.OPEN or not self._preview_on:
            return None
        h = self._hover
        if h and not h.startswith("__"):
            return h
        if h == DEFAULT_ID:
            return DEFAULT_ID      # previewing "no cosmetic" is meaningful
        return None

    @property
    def accepts_input(self) -> bool:
        """Input is inert while animating.

        If the panel were live while scaling in, the very click that opened it
        could also land on a row underneath the growing panel.
        """
        return self.phase is Phase.OPEN

    def _tab_items(self):
        """Active category, with a Default entry pinned first."""
        return (DEFAULT_ID,) + catalogue.of_kind(TABS[self._tab][1])

    def page_count(self) -> int:
        n = len(self._tab_items())
        return max(1, (n + PAGE_SIZE - 1) // PAGE_SIZE)

    def _page_items(self):
        items = self._tab_items()
        self._page = max(0, min(self._page, self.page_count() - 1))
        return items[self._page * PAGE_SIZE:(self._page + 1) * PAGE_SIZE]

    def _turn(self, delta: int) -> None:
        """Change page, and kick a small slide in that direction."""
        if self.page_count() <= 1:
            return
        self._page = (self._page + delta) % self.page_count()
        self._slide = float(delta)
        self._fade_only = False

    def set_tab(self, i: int) -> None:
        """Switching category CROSS-FADES; it does not slide.

        A tab change is a change of subject, not a move through a sequence, so
        lateral travel is the wrong metaphor — and it is where sliding reads
        worst. `_slide` is negative-tagged here purely to mark "fade only".
        """
        if i != self._tab:
            self._tab = i % len(TABS)
            self._page = 0
            self._slide = 0.999      # sentinel: fade, no travel
            self._fade_only = True

    def open(self, origin: tuple[int, int] | None = None) -> None:
        if self.phase in (Phase.OPEN, Phase.OPENING):
            return
        if origin:
            self._origin = origin
        self.phase = Phase.OPENING
        self._t = 0.0
        self._hover = None
        self._pressed = None

    def close(self) -> None:
        if self.phase in (Phase.CLOSED, Phase.CLOSING):
            return
        self.phase = Phase.CLOSING
        self._t = 0.0
        self._pressed = None

    def toggle(self, origin: tuple[int, int] | None = None) -> None:
        if self.is_open:
            self.close()
        else:
            self.open(origin)

    def update(self, dt: float) -> None:
        scale = theme.ANIM_SCALE
        self._t += dt
        self._tweens.update(dt)
        if self._slide:
            # Pages slide in rather than snapping. Decay toward 0;
            # the sign carries the direction of travel.
            step = dt / max(1e-6, theme.DUR_PANEL_IN * max(theme.ANIM_SCALE, 1e-6))
            self._slide -= step if self._slide > 0 else -step
            if abs(self._slide) < 0.02:
                self._slide = 0.0

        for d in (self._reject, self._flash):
            for k in list(d):
                d[k] += dt
                if d[k] > 0.7:
                    del d[k]

        if self.phase is Phase.OPENING:
            if scale <= 0 or self._t >= theme.DUR_PANEL_IN * scale:
                self.phase = Phase.OPEN
        elif self.phase is Phase.CLOSING:
            if scale <= 0 or self._t >= theme.DUR_PANEL_OUT * scale:
                self.phase = Phase.CLOSED

    # ── Progress helpers ────────────────────────────────────────────────────

    def _progress(self) -> float:
        """0 = fully closed, 1 = fully open."""
        scale = theme.ANIM_SCALE
        if self.phase is Phase.OPEN:
            return 1.0
        if self.phase is Phase.CLOSED:
            return 0.0
        if scale <= 0:
            return 1.0 if self.phase is Phase.OPENING else 0.0
        if self.phase is Phase.OPENING:
            return min(1.0, self._t / (theme.DUR_PANEL_IN * scale))
        return 1.0 - min(1.0, self._t / (theme.DUR_PANEL_OUT * scale))

    # ── Item state ──────────────────────────────────────────────────────────

    @staticmethod
    def state_of(item, inventory, hat_slot, bits, echoes,
                 screen_slot=None, shell_slot=None) -> ItemState:
        """Which of the four states this item is in.

        Two slots, not one: a hat is worn by the creature, a screen is fitted
        to the device. Comparing everything to `hat_slot` would mean a fitted
        screen never showed as equipped and could never be toggled off.
        """
        if item.is_ownable and item.id in inventory:
            worn = (screen_slot if item.kind is ItemKind.SCREEN else
                    shell_slot if item.kind is ItemKind.SHELL else hat_slot)
            return ItemState.EQUIPPED if worn == item.id else ItemState.OWNED
        have = bits if item.currency is Currency.BITS else echoes
        return ItemState.AFFORDABLE if have >= item.cost else ItemState.UNAFFORDABLE

    # ── Input ───────────────────────────────────────────────────────────────

    def handle_event(self, event, inventory, hat_slot, bits, echoes,
                     screen_slot=None, shell_slot=None) -> list[str]:
        """Consume one event. Returns action ids.

        The caller must route events here FIRST and not fall through when the
        panel is open — that is the whole point of a modal.
        """
        out: list[str] = []
        if not self.is_open:
            return out

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_s):
                self.close()
            return out

        if event.type == pygame.MOUSEMOTION:
            self._hover = self._hit(event.pos)
            return out

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.accepts_input:
                return out
            hit = self._hit(event.pos)
            if hit is None and not self._panel_rect.collidepoint(event.pos):
                # Press began outside; remember so a drag that ends inside
                # does not count as a click-outside dismissal.
                self._pressed = "__outside__"
            else:
                self._pressed = hit
            return out

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if not self.accepts_input:
                self._pressed = None
                return out
            hit = self._hit(event.pos)
            was, self._pressed = self._pressed, None

            if was == "__outside__":
                if hit is None and not self._panel_rect.collidepoint(event.pos):
                    self.close()
                return out
            if was is None or hit != was:
                return out

            if was == "__close__":
                self.close()
                return out
            if was == "__prev__":
                self._turn(-1)
                return out
            if was == "__next__":
                self._turn(1)
                return out
            if was == "__peek__":
                self._preview_on = not self._preview_on
                return out
            if was.startswith("__tab"):
                self.set_tab(int(was[5:-2]))
                return out

            if was == DEFAULT_ID:
                kind = TABS[self._tab][1]
                out.append({ItemKind.HAT: "unequip",
                            ItemKind.SCREEN: "screen:",
                            ItemKind.SHELL: "shell:"}[kind])
                return out

            item = catalogue.get(was)
            if item is None:
                return out
            st = self.state_of(item, inventory, hat_slot, bits, echoes,
                               screen_slot, shell_slot)
            if st is ItemState.UNAFFORDABLE:
                # Never a silent dead click: reject visibly and say why.
                self._reject[was] = 0.0
            elif st is ItemState.AFFORDABLE:
                self._flash[was] = 0.0
                out.append(f"buy:{was}")
                out.append(self._equip_action(was))
            elif st is ItemState.OWNED:
                out.append(self._equip_action(was))
            else:  # EQUIPPED -> toggle it back off
                out.append("screen:" if _is_screen(was)
                           else "shell:" if _is_shell(was) else "unequip")
        return out

    @staticmethod
    def _equip_action(item_id: str) -> str:
        if _is_screen(item_id):
            return f"screen:{item_id}"
        if _is_shell(item_id):
            return f"shell:{item_id}"
        return f"equip:{item_id}"

    def _hit(self, pos) -> str | None:
        if self._close_rect and self._close_rect.collidepoint(pos):
            return "__close__"
        for i, r in enumerate(self._tab_rects):
            if r.collidepoint(pos):
                return f"__tab{i}__"
        if self._peek_rect and self._peek_rect.collidepoint(pos):
            return "__peek__"
        if self._prev_rect and self._prev_rect.collidepoint(pos):
            return "__prev__"
        if self._next_rect and self._next_rect.collidepoint(pos):
            return "__next__"
        for item_id, rect in self._rows:
            if rect.collidepoint(pos):
                return item_id
        return None

    # ── Draw ────────────────────────────────────────────────────────────────

    def draw(self, dest, inventory, hat_slot, bits, echoes, draw_preview,
             stage: str = "", hunger: float = 100.0,
             offset: tuple[int, int] = (0, 0),
             screen_slot=None, shell_slot=None) -> None:
        """Render the modal. `draw_preview(surface, x, y, hat)` paints a small
        live creature wearing `hat` — showing the pet in the item beats an
        isolated icon, and costs nothing since sprites are programmatic."""
        if not self.is_open:
            self._rows = []
            self._close_rect = None
            self._prev_rect = self._next_rect = self._peek_rect = None
            self._tab_rects = []
            return

        p = self._progress()
        win_w, win_h = dest.get_size()
        items = self._page_items()

        # Scrim — dims the session without hiding it.
        # Peeking at an item lifts the scrim and fades the panel, so the live
        # device underneath becomes the preview rather than a thumbnail.
        peek = self.preview_item() is not None
        scrim_k = 0.30 if peek else 1.0
        scrim = pygame.Surface((win_w, win_h), pygame.SRCALPHA)
        scrim.fill((2, 8, 5,
                    int(theme.SCRIM_ALPHA * scrim_k * easing.ease_out_cubic(p))))
        dest.blit(scrim, (0, 0))

        # Always PAGE_SIZE rows tall, even on a short final page: a panel
        # that resizes as you page moves the controls under the cursor.
        body_h = HEADER_H + TAB_H + PAGE_SIZE * ROW_H_PAGED + FOOTER_H + theme.SPACE_2
        panel = pygame.Surface((PANEL_W, body_h), pygame.SRCALPHA)
        self._paint_body(panel, items, inventory, hat_slot, bits, echoes,
                         draw_preview, p, stage, hunger, screen_slot, shell_slot)

        # Scale from the trigger, overshooting slightly on the way in.
        if self.phase is Phase.OPENING:
            s = 0.86 + 0.14 * easing.ease_out_back(p)
        elif self.phase is Phase.CLOSING:
            s = 0.86 + 0.14 * easing.ease_in_cubic(p)
        else:
            s = 1.0

        cx, cy = win_w // 2, win_h // 2
        ox, oy = self._origin
        # Drift from the button toward centre as it grows.
        gx = int(ox + (cx - ox) * easing.ease_out_cubic(p))
        gy = int(oy + (cy - oy) * easing.ease_out_cubic(p))

        panel.set_alpha(int(255 * min(1.0, p * 1.6) * (0.42 if peek else 1.0)))
        scaled, topleft = uikit.scaled_about_center(panel, s, (gx, gy))
        dest.blit(scaled, topleft)

        # Hit rects must match what was actually drawn, so recompute them
        # against the final on-screen position.
        self._panel_rect = pygame.Rect(
            (topleft[0] + offset[0], topleft[1] + offset[1]), scaled.get_size())
        self._sync_hitboxes(items, s,
                            (topleft[0] + offset[0], topleft[1] + offset[1]))

    def _sync_hitboxes(self, items, s, topleft) -> None:
        if self.phase is not Phase.OPEN:
            # Stale rects from the last frame's layout are how a click "leaks"
            # into an accidental purchase. While animating, there are none.
            self._rows = []
            self._close_rect = None
            self._prev_rect = self._next_rect = self._peek_rect = None
            self._tab_rects = []
            return
        x0, y0 = topleft
        self._rows = [
            (
                item if isinstance(item, str) else item.id,
                pygame.Rect(
                    x0 + theme.SPACE_3,
                    y0 + HEADER_H + TAB_H + i * ROW_H_PAGED,
                    PANEL_W - theme.SPACE_3 * 2,
                    ROW_H_PAGED - theme.SPACE_1,
                ),
            )
            for i, item in enumerate(items)
        ]
        self._close_rect = pygame.Rect(
            x0 + PANEL_W - 36, y0 + theme.SPACE_2, 26, 26
        )
        h = HEADER_H + TAB_H + PAGE_SIZE * ROW_H_PAGED + FOOTER_H + theme.SPACE_2
        py_ = y0 + h - FOOTER_H + 4
        tw = (PANEL_W - theme.SPACE_3 * 2) // len(TABS)
        self._tab_rects = [
            pygame.Rect(x0 + theme.SPACE_3 + i * tw, y0 + HEADER_H - 4,
                        tw - 4, TAB_H - 4)
            for i in range(len(TABS))
        ]
        self._prev_rect = pygame.Rect(x0 + theme.SPACE_3, py_, 26, 20)
        self._next_rect = pygame.Rect(x0 + PANEL_W - theme.SPACE_3 - 26, py_, 26, 20)
        self._peek_rect = pygame.Rect(x0 + PANEL_W // 2 - 44, py_, 88, 20)

    def _paint_body(self, surf, items, inventory, hat_slot, bits, echoes,
                    draw_preview, p, stage="", hunger=100.0,
                    screen_slot=None, shell_slot=None) -> None:
        w, h = surf.get_size()
        uikit.draw_panel(
            surf, pygame.Rect(0, 0, w, h),
            fill=theme.SCREEN, gradient_to=theme.SCREEN_EDGE,
            border=theme.PHOSPHOR_DIM, radius=theme.RADIUS_MD,
            elevation=None, top_highlight=18,
        )

        # ── Header: title + balances. Currency must stay visible inside the
        # shop; covering the HUD and not restating it is a classic miss.
        surf.blit(uikit.text("SHOP", theme.PHOSPHOR, theme.FONT_TITLE, bold=True),
                  (theme.SPACE_4, theme.SPACE_3))
        self._paint_balance(surf, w - 36 - theme.SPACE_2, bits, echoes)

        pygame.draw.line(surf, theme.BORDER_SUBTLE,
                         (theme.SPACE_3, HEADER_H - 6),
                         (w - theme.SPACE_3, HEADER_H - 6), 1)

        # Close affordance, in addition to Esc and click-outside.
        cr = pygame.Rect(w - 36, theme.SPACE_2, 26, 26)
        hovered = self._hover == "__close__"
        surf.blit(
            uikit.round_rect(
                (cr.w, cr.h), theme.RADIUS_SM,
                theme.SURFACE_HOVER if hovered else theme.SURFACE_RAISED,
                border=theme.BORDER_STRONG if hovered else theme.BORDER_SUBTLE,
            ), cr.topleft)
        uikit.blit_centered(
            surf, uikit.text("X", theme.TEXT if hovered else theme.TEXT_SECONDARY,
                             theme.FONT_BODY, bold=True), cr)

        # ── Category tabs ──────────────────────────────────────────────
        tw = (w - theme.SPACE_3 * 2) // len(TABS)
        for i, (label, _kind) in enumerate(TABS):
            tr = pygame.Rect(theme.SPACE_3 + i * tw, HEADER_H - 4, tw - 4,
                             TAB_H - 4)
            on = i == self._tab
            hov = self._hover == f"__tab{i}__"
            surf.blit(uikit.round_rect(
                (tr.w, tr.h), theme.RADIUS_SM,
                theme.PHOSPHOR_DIM if on else theme.SCREEN_EDGE,
                border=theme.PHOSPHOR if (on or hov) else None,
                top_highlight=40 if on else 0), tr.topleft)
            uikit.blit_centered(surf, uikit.text(
                label, theme.SCREEN if on else theme.PHOSPHOR_DIM,
                theme.FONT_CAPTION, bold=True), tr)

        # Rows slide in from the direction of travel, over a short distance.
        # `_slide` decays 1 -> 0; progress is its complement, eased so the
        # rows decelerate into place instead of snapping.
        mag = min(1.0, abs(self._slide))
        eased_remaining = 1.0 - easing.ease_out_cubic(1.0 - mag)
        dx = 0 if self._fade_only else int(
            (1 if self._slide >= 0 else -1) * SLIDE_PX * eased_remaining)
        fade = 1.0 - eased_remaining

        for i, item in enumerate(items):
            # Staggered reveal — nearly free, and disproportionately effective.
            delay = i * theme.DUR_STAGGER
            local = 1.0
            if theme.ANIM_SCALE > 0 and self.phase is Phase.OPENING:
                span = max(1e-6, theme.DUR_PANEL_IN * theme.ANIM_SCALE - delay)
                local = max(0.0, min(1.0, (self._t - delay) / span))
                local = easing.ease_out_cubic(local)
            row = pygame.Rect(
                theme.SPACE_3 + dx,
                HEADER_H + TAB_H + i * ROW_H_PAGED + int((1.0 - local) * 14),
                w - theme.SPACE_3 * 2,
                ROW_H_PAGED - theme.SPACE_1,
            )
            self._paint_row(surf, row, item, inventory, hat_slot, bits, echoes,
                            draw_preview, local * (0.25 + 0.75 * fade),
                            screen_slot, shell_slot)

        # If a hat would not render right now, say so rather than quietly
        # taking 15 ECHOES for something invisible.
        # Pager. Preferred over a scrollbar: at this size there is no room for
        # a usable thumb, and "2 / 3" tells you how much catalogue exists,
        # which a scroll position does not.
        py_ = h - FOOTER_H + 4
        total = self.page_count()
        for rect, glyph, key in (
            (pygame.Rect(theme.SPACE_3, py_, 26, 20), "<", "__prev__"),
            (pygame.Rect(w - theme.SPACE_3 - 26, py_, 26, 20), ">", "__next__"),
        ):
            live = total > 1
            hov = self._hover == key and live
            surf.blit(uikit.round_rect(
                (rect.w, rect.h), theme.RADIUS_SM,
                theme.SCREEN_EDGE if live else theme.SCREEN,
                border=theme.PHOSPHOR if hov else
                (theme.PHOSPHOR_DIM if live else None)), rect.topleft)
            uikit.blit_centered(surf, uikit.text(
                glyph, theme.PHOSPHOR if live else theme.PHOSPHOR_DIM,
                theme.FONT_CAPTION, bold=True), rect)

        # PREVIEW toggle — off by default. Live-applying on hover makes the
        # device flicker every time the cursor crosses a row.
        pr = pygame.Rect(w // 2 - 44, py_, 88, 20)
        on = self._preview_on
        hov = self._hover == "__peek__"
        surf.blit(uikit.round_rect(
            (pr.w, pr.h), theme.RADIUS_SM,
            theme.PHOSPHOR_DIM if on else theme.SCREEN_EDGE,
            border=theme.PHOSPHOR if (on or hov) else theme.PHOSPHOR_DIM,
            top_highlight=40 if on else 0), pr.topleft)
        # Reads its own state rather than being a mystery toggle.
        uikit.blit_centered(surf, uikit.text(
            "PREVIEW:ON" if on else "PREVIEW:OFF",
            theme.SCREEN if on else theme.PHOSPHOR_DIM,
            theme.FONT_CAPTION, bold=True), pr)

        reason = hat_hidden_reason(stage, hunger)
        if reason:
            mid = uikit.text(f"HIDDEN — {reason}", theme.DANGER,
                             theme.FONT_CAPTION, bold=True)
            surf.blit(mid, ((w - mid.get_width()) // 2, py_ - 13))
        else:
            pg = uikit.text(f"{self._page + 1}/{total}", theme.PHOSPHOR_DIM,
                            theme.FONT_CAPTION, bold=True)
            surf.blit(pg, (w // 2 - pg.get_width() // 2, py_ - 13))

    def _paint_balance(self, surf, right_x, bits, echoes) -> None:
        y = theme.SPACE_3 + 2
        x = right_x
        for label, val, col in (("E", echoes, theme.ECHOES), ("B", bits, theme.BITS)):
            t = uikit.text(f"{val}", col, theme.FONT_BODY, bold=True)
            tag = uikit.text(label, col, theme.FONT_CAPTION)
            x -= t.get_width() + tag.get_width() + 6
            surf.blit(t, (x, y))
            surf.blit(tag, (x + t.get_width() + 3, y + 3))
            x -= theme.SPACE_3

    def _paint_row(self, surf, rect, item, inventory, hat_slot, bits, echoes,
                   draw_preview, reveal, screen_slot=None,
                   shell_slot=None) -> None:
        if item == DEFAULT_ID:
            self._paint_default_row(surf, rect, hat_slot, screen_slot,
                                    shell_slot, reveal)
            return
        st = self.state_of(item, inventory, hat_slot, bits, echoes,
                           screen_slot, shell_slot)
        hovered = self._hover == item.id and self.accepts_input
        pressed = self._pressed == item.id

        dx = int(easing.shake_offset(self._reject.get(item.id, 99.0), 0.28))
        rect = rect.move(dx, 1 if pressed else 0)

        if st is ItemState.EQUIPPED:
            fill, border = theme.SURFACE_RAISED, theme.ACCENT
        elif st is ItemState.OWNED:
            fill = theme.SURFACE_HOVER if hovered else theme.SURFACE_RAISED
            border = theme.BORDER_STRONG if hovered else theme.BORDER_SUBTLE
        elif st is ItemState.UNAFFORDABLE:
            fill, border = theme.SURFACE_SUNKEN, theme.BORDER_SUBTLE
        else:
            fill = theme.SURFACE_HOVER if hovered else theme.SURFACE_RAISED
            border = theme.BORDER_FOCUS if hovered else theme.BORDER
        if item.id in self._flash:
            fill = theme.ACCENT_DIM

        body = uikit.round_rect(
            (rect.w, rect.h), theme.RADIUS_MD, fill,
            border=border, gradient_to=theme.SURFACE if hovered else None,
            top_highlight=22 if st is not ItemState.UNAFFORDABLE else 0,
        )
        if reveal < 1.0:
            body = body.copy()
            body.set_alpha(int(255 * reveal))
        surf.blit(body, rect.topleft)

        # Live preview — the pet actually wearing it.
        pv = pygame.Rect(rect.x + theme.SPACE_2, rect.centery - ICON // 2,
                         ICON, ICON)
        surf.blit(uikit.round_rect((pv.w, pv.h), theme.RADIUS_SM,
                                   theme.SURFACE_SUNKEN), pv.topleft)
        try:
            draw_preview(surf, pv.x, pv.y, item.id)
        except Exception:
            pass

        tx = pv.right + theme.SPACE_3
        dim = st is ItemState.UNAFFORDABLE
        surf.blit(uikit.text(item.name,
                             theme.TEXT_DISABLED if dim else theme.TEXT,
                             theme.FONT_LABEL, bold=True),
                  (tx, rect.centery - 8))
        if item.rarity is not None:
            # A 3px rarity spine on the row's left edge. Cheaper than a badge
            # and it never competes with the price for space.
            rc = RARITY_COLOR[item.rarity.value]
            surf.blit(uikit.round_rect((3, rect.h - 12), 1, rc, border=None),
                      (rect.x + 2, rect.y + 6))
        # No blurb at 46px. The name plus the badge is the whole row.

        self._paint_badge(surf, rect, item, st, bits, echoes)

    def _paint_default_row(self, surf, rect, hat_slot, screen_slot,
                           shell_slot, reveal) -> None:
        """The 'no cosmetic' option, as a selectable thing rather than an
        un-equip gesture hidden inside the equipped item."""
        kind = TABS[self._tab][1]
        current = {ItemKind.HAT: hat_slot, ItemKind.SCREEN: screen_slot,
                   ItemKind.SHELL: shell_slot}[kind]
        active = current in (None, "")
        hovered = self._hover == DEFAULT_ID and self.accepts_input

        fill = (theme.SURFACE_RAISED if active else
                theme.SURFACE_HOVER if hovered else theme.SURFACE_SUNKEN)
        border = (theme.ACCENT if active else
                  theme.BORDER_STRONG if hovered else theme.BORDER_SUBTLE)
        body = uikit.round_rect((rect.w, rect.h), theme.RADIUS_MD, fill,
                                border=border, top_highlight=20)
        if reveal < 1.0:
            body = body.copy()
            body.set_alpha(int(255 * reveal))
        surf.blit(body, rect.topleft)

        pv = pygame.Rect(rect.x + theme.SPACE_2, rect.centery - ICON // 2,
                         ICON, ICON)
        surf.blit(uikit.round_rect((pv.w, pv.h), theme.RADIUS_SM,
                                   theme.SURFACE_SUNKEN,
                                   border=theme.BORDER_SUBTLE), pv.topleft)
        uikit.blit_centered(surf, uikit.text("--", theme.TEXT_MUTED,
                                             theme.FONT_LABEL, bold=True), pv)

        surf.blit(uikit.text("Default", theme.TEXT, theme.FONT_LABEL, bold=True),
                  (pv.right + theme.SPACE_3, rect.centery - 8))

        if active:
            lab, fg, bg = "ACTIVE", theme.TEXT_ON_ACCENT, theme.ACCENT
            tw = uikit.text_w(lab, theme.FONT_CAPTION, bold=True)
            br = pygame.Rect(rect.right - tw - theme.SPACE_3 - theme.SPACE_2,
                             rect.centery - 10, tw + theme.SPACE_3, 20)
            surf.blit(uikit.round_rect((br.w, br.h), theme.RADIUS_SM, bg,
                                       border=None), br.topleft)
            uikit.blit_centered(surf, uikit.text(lab, fg, theme.FONT_CAPTION,
                                                 bold=True), br)

    def _paint_badge(self, surf, rect, item, st, bits, echoes) -> None:
        """Right-hand badge: price, or ownership. Never a bare grey.

        An unaffordable item states the shortfall rather than just dimming —
        a disabled control tells you *that* something is wrong but not *what*.
        """
        col = theme.currency_color(item.currency.value)
        if st is ItemState.EQUIPPED:
            label, fg, bg = "WORN", theme.TEXT_ON_ACCENT, theme.ACCENT
        elif st is ItemState.OWNED:
            label, fg, bg = "OWNED", theme.SUCCESS, theme.SURFACE_SUNKEN
        elif st is ItemState.UNAFFORDABLE:
            have = bits if item.currency is Currency.BITS else echoes
            label, fg, bg = f"NEED {item.cost - have}", theme.DANGER, theme.SURFACE_SUNKEN
        else:
            unit = "B" if item.currency is Currency.BITS else "E"
            label, fg, bg = f"{item.cost} {unit}", col, theme.SURFACE_SUNKEN

        tw = uikit.text_w(label, theme.FONT_CAPTION, bold=True)
        bw = tw + theme.SPACE_3
        br = pygame.Rect(rect.right - bw - theme.SPACE_2,
                         rect.centery - 10, bw, 20)
        surf.blit(uikit.round_rect((br.w, br.h), theme.RADIUS_SM, bg,
                                   border=None), br.topleft)
        uikit.blit_centered(surf, uikit.text(label, fg, theme.FONT_CAPTION,
                                             bold=True), br)
