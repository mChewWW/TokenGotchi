"""GameWindow — Pygame window management and main render loop.

Owns window creation, event routing, frame rendering and clock ticking.
Drawing is delegated to sprites, device, shop_panel and privacy; all chrome is
built from the `theme` tokens through the anti-aliased `uikit` primitives.

Event routing is a LAYER STACK, not a chain of if/elif. Exactly one layer is
topmost, it consumes the event, and nothing falls through. A chain that checks
an overlay's controls unconditionally lets clicks meant for a layer above it
fall straight through and fire underneath.
"""
from __future__ import annotations

import time
from typing import Any

import pygame

from ..config import BITS_RATIO
from ..engine import food as foodmenu
from ..engine.creature import EGG_TO_BABY_BITS
from . import easing, ink, metal, theme, uikit
from . import device
from . import shop_panel as shoppanel
from . import skins as skinmod
from ..shop import catalogue as shopcat
from .background import Starfield
from .eat_animation import EatAnimation
from .privacy import draw_privacy_notice
from .food_panel import FoodPanel
from .rate_panel import RatePanel
from .shop_panel import ShopPanel
from .sprites import draw_creature

WINDOW_W = 400
WINDOW_H = 450

HEADER_H = 32          # retained for back-compat; the shell has no header bar
HUD_H = 80             # retained for back-compat
ACTION_H = 48          # retained for back-compat
CREATURE_AREA_Y = HEADER_H
CREATURE_AREA_H = WINDOW_H - HEADER_H - ACTION_H - HUD_H

# The pet is magnified on the blit. At 1.0 it covers 6.2% of its stage and the
# stage reads as 96% empty; magnified, the creature is the subject and the
# frame around it becomes an object.
PET_SCALE = 1.7

# Vertical room ABOVE the creature for headwear.
#
# draw_creature centres the sprite in its cell, so head_top lands at y=3 (baby)
# / y=7 (adult), while the top hat's crown reaches 39px ABOVE that — i.e.
# y=-36. Without headroom everything above the brim is cut off by the surface
# edge and the hat "doesn't look like a hat"; a taller crown only clips MORE.
HAT_HEADROOM = 42


def _make_font(size: int = 14) -> pygame.font.Font:
    """Compatibility shim for external callers — `uikit.font` is the real
    accessor and nothing in this package calls this."""
    return uikit.font(size)


class GameWindow:
    """Manages the Pygame window and main render loop scaffolding.

    Usage::

        window = GameWindow(always_on_top=False)
        while not window.should_quit():
            actions = window.render_frame(game_state, show_privacy=False)
            window.tick(fps=30)
        window.close()

    ``game_state`` is duck-typed and must expose creature.stage / .hunger /
    .hat_slot / .dormancy_start, wallet.bits / .echoes, and (optionally)
    ``inventory``.

    Action ids returned use a ``verb:arg`` convention: ``feed``, ``buy:<id>``,
    ``equip:<id>``, ``unequip``, ``privacy_ok``, ``quit``.
    """

    def __init__(self, always_on_top: bool = False) -> None:
        import os
        os.environ.setdefault("SDL_VIDEO_CENTERED", "1")

        pygame.init()

        flags = pygame.SHOWN
        if always_on_top:
            flags |= 0x8000  # SDL_WINDOW_ALWAYS_ON_TOP (best-effort, Windows)

        self._surface = pygame.display.set_mode((WINDOW_W, WINDOW_H), flags)
        pygame.display.set_caption("TokenGotchi")
        pygame.display.flip()
        pygame.event.pump()

        self._clock = pygame.time.Clock()
        self._font = uikit.font(theme.FONT_LABEL)
        self._font_large = uikit.font(theme.FONT_TITLE, bold=True)
        self._quit = False

        self._starfield = Starfield(WINDOW_W, WINDOW_H)
        self._last_tick: float = time.monotonic()

        self._anim_frame: int = 0
        self._last_anim_toggle: float = time.monotonic()
        self._ANIM_INTERVAL: float = 1.0

        self._shop = ShopPanel()
        self._rates = RatePanel()
        self._food = FoodPanel()
        self._eat = EatAnimation()
        self._rate_rect = None
        self._tweens = easing.Tweens()

        self._mouse: tuple[int, int] = (0, 0)
        self._hover: str | None = None
        self._pressed: str | None = None

        # Displayed currency, tweened toward the true value so the numbers
        # roll rather than snap. A snapping number is invisible.
        self._peek_hat: str | None = None
        self._clear_hat: bool = False
        self._shown_bits: float | None = None
        self._shown_echoes: float | None = None

        self._feed_rect = pygame.Rect(0, 0, 0, 0)
        self._shop_rect = pygame.Rect(0, 0, 0, 0)
        self._privacy_rect: pygame.Rect | None = None

        # Cached constant overlays. They never change, so rebuilding them from
        # scratch every frame is pure waste.
        self._glow = self._build_glow()
        self._vignette = self._build_vignette()

    # ── Cached decoration ───────────────────────────────────────────────────

    @staticmethod
    def _build_glow() -> pygame.Surface:
        """Ambient light behind the creature.

        Built from concentric ellipses at low alpha and then blurred hard. A
        single ellipse — however transparent — still reads as a discrete oval
        with a visible edge, which looks like a mistake rather than light.
        """
        w, h = 340, 250
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for i in range(9):
            f = i / 8.0
            rw, rh = int(w * (0.30 + 0.70 * f)), int(h * (0.30 + 0.70 * f))
            pygame.draw.ellipse(
                s, (*theme.ACCENT_DIM, 7),
                ((w - rw) // 2, (h - rh) // 2, rw, rh),
            )
        return uikit._blur(s, 0.12)

    @staticmethod
    def _build_vignette() -> pygame.Surface:
        s = pygame.Surface((170, 40), pygame.SRCALPHA)
        for i in range(5):
            f = i / 4.0
            rw, rh = int(170 * (0.45 + 0.55 * f)), int(40 * (0.45 + 0.55 * f))
            pygame.draw.ellipse(
                s, (0, 0, 0, 26), ((170 - rw) // 2, (40 - rh) // 2, rw, rh)
            )
        return uikit._blur(s, 0.25)

    # ── Public API ──────────────────────────────────────────────────────────

    def render_frame(
        self,
        game_state: Any,
        show_privacy: bool = False,
        stats_missing: bool = False,
        schema_error: str | None = None,
    ) -> list[str]:
        """Process events, draw every layer, return this frame's action ids.

        The full keyword set is accepted by every window implementation —
        this one, `_HeadlessWindow` and `renderer/_stub.py` — so the caller can
        pass them unconditionally. Picking kwargs by introspecting this
        signature on every frame is the alternative, and it silently drops any
        argument whose name drifts.

        `stats_missing` / `schema_error` are accepted and currently unused: the
        caller computes and passes them, but no renderer draws them yet.
        """
        triggered: list[str] = []

        inventory = list(getattr(game_state, "inventory", []) or [])
        # A hovered shop item is applied to the real device so the player sees
        # what they are buying, not a 36px thumbnail of it.
        peek = self._shop.preview_item() if self._shop.is_open else None
        # DEFAULT previews the bare device: clear whichever slot this tab owns.
        peek_default = peek == shoppanel.DEFAULT_ID
        peek_item = shopcat.get(peek) if (peek and not peek_default) else None
        from ..shop.catalogue import ItemKind as _IK
        peek_screen = peek if (peek_item and peek_item.kind is _IK.SCREEN) else None
        peek_shell = peek if (peek_item and peek_item.kind is _IK.SHELL) else None
        peek_hat = peek if (peek_item and peek_item.kind is _IK.HAT) else None

        tab_kind = shoppanel.TABS[self._shop._tab][1] if peek_default else None
        clr_screen = peek_default and tab_kind is _IK.SCREEN
        clr_shell = peek_default and tab_kind is _IK.SHELL
        clr_hat = peek_default and tab_kind is _IK.HAT

        skin = skinmod.get(
            None if clr_screen
            else peek_screen or getattr(game_state, "screen_slot", None))
        shell = skinmod.get_shell(
            None if clr_shell
            else peek_shell or getattr(game_state, "shell_slot", None))
        self._peek_hat = peek_hat
        self._clear_hat = clr_hat
        hat_slot = getattr(game_state.creature, "hat_slot", None)
        bits = getattr(game_state.wallet, "bits", 0)
        echoes = getattr(game_state.wallet, "echoes", 0)
        hunger = getattr(game_state.creature, "hunger", 100.0)
        stage = getattr(game_state.creature, "stage", "egg")
        if hasattr(stage, "value"):
            stage = stage.value
        stage = str(stage)

        now = time.monotonic()
        dt = min(0.1, now - self._last_tick)   # clamp: a debugger pause or a
        self._last_tick = now                  # window drag must not teleport
        self._starfield.update(dt)             # every tween to its end state
        self._shop.update(dt)
        self._rates.update(dt)
        self._food.update(dt)
        self._eat.update(dt)
        self._tweens.update(dt)

        if now - self._last_anim_toggle >= self._ANIM_INTERVAL:
            self._anim_frame = 1 - self._anim_frame
            self._last_anim_toggle = now

        # ── Event routing — topmost layer only ─────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._quit = True
                triggered.append("quit")
                continue
            if event.type == pygame.MOUSEMOTION:
                self._mouse = event.pos

            if show_privacy:
                self._route_privacy(event, triggered)
            elif self._food.is_open:
                triggered.extend(self._food.handle_event(event, bits))
            elif self._rates.is_open:
                self._rates.handle_event(event)
            elif self._shop.is_open:
                triggered.extend(
                    self._shop.handle_event(
                        event, inventory, hat_slot, bits, echoes,
                        getattr(game_state, "screen_slot", None),
                        getattr(game_state, "shell_slot", None))
                )
            else:
                self._route_main(event, triggered)

        # `_hover`/`_pressed` are only ever written by `_route_main`, which is
        # skipped for every event above whenever an overlay owns input. Left
        # alone, whichever case button was hovered the instant before FOOD or
        # RATES opens stays lit for that overlay's entire lifetime -- the FOOD
        # button glowing while RATES is open, and vice versa, which reads as
        # the two interfaces fighting each other.
        if self._food.is_open or self._rates.is_open or self._shop.is_open:
            self._hover = None
            self._pressed = None

        # ── Draw ───────────────────────────────────────────────────────────
        # The device, outside in: shell, then the screen's contents rendered
        # offscreen and seated in its recess, then the physical controls.
        surf = self._surface
        device.draw_shell(surf, shell)
        self._draw_silkscreen(surf, stage, shell)

        inner = device.begin_screen(skin)
        # Content on its own layer so a quantising skin (DMG, e-ink) reduces
        # the pet and stars without crushing them into the background.
        content = pygame.Surface(inner.get_size(), pygame.SRCALPHA)
        if skin.stars:
            self._starfield.draw(content)
        self._draw_creature(content, game_state, stage, hunger, skin)
        if skin.palette:
            content = skinmod.quantise_layer(content, skin.palette, skin.dither)
        inner.blit(content, (0, 0))
        if stage.lower() == "egg":
            device.draw_hatch_readout(
                inner, getattr(game_state, "lifetime_bits_earned", 0),
                EGG_TO_BABY_BITS, skin)
        else:
            device.draw_readout(inner, self._eat.displayed_hunger(hunger), skin, now)
        r = getattr(game_state, "rates", None)
        if r is not None:
            hit = device.draw_rate(
                inner,
                max(1, int(round(BITS_RATIO / max(0.01, r.earn_mult)))),
                skin)
            sr = device.screen_rect()
            self._rate_rect = hit.move(sr.x, sr.y)
        # The shop is drawn INSIDE the screen and therefore under the scanlines
        # and glare. A menu floating over the case would read as a card pasted
        # onto an object.
        self._food.draw(inner, bits, hunger, skin,
                        offset=device.screen_rect().topleft)
        self._shop.draw(inner, inventory, hat_slot, bits, echoes, self._preview,
                        stage=stage, hunger=hunger,
                        offset=device.screen_rect().topleft,
                        screen_slot=getattr(game_state, "screen_slot", None),
                        shell_slot=getattr(game_state, "shell_slot", None))
        device.end_screen(surf, inner, skin, shell)

        self._draw_controls(surf, bits, echoes, stage, shell)

        # LAST, over everything, and outside the screen well. Three separate
        # reasons:
        #
        #   * After end_screen, because inside the CRT a scanline every 4px
        #     runs through the digits and closes the counters of 8, 6, 9 and 0
        #     — a seven-figure number reads as "2,40X,XXX".
        #   * Clipped to the screen well, so it reads as being ON the display.
        #     Spilling over the whole case buys space and looks wrong; the
        #     space comes out of the font instead.
        #   * After the controls, or the FEED button paints straight over the
        #     bottom row of the table.
        #
        # The shop panel deliberately stays inside the screen under the CRT
        # treatment: short words and large icons, where the texture is free.
        if self._rates.is_open:
            sr = device.screen_rect()
            self._rates.draw(surf.subsurface(sr), game_state, skin,
                             offset=sr.topleft)

        if show_privacy:
            self._privacy_rect = draw_privacy_notice(
                surf, self._font, self._font_large
            )
        else:
            self._privacy_rect = None

        pygame.display.flip()
        return triggered

    def start_eat_animation(self, food_id: str, hunger_before: float,
                            hunger_after: float) -> None:
        """Play the 3-stage eating animation for a food already committed.

        Called by the caller of `render_frame` AFTER it has applied the
        `eat:<id>` action to the real creature/wallet — `hunger_after` is
        already final. This only seeds what the player SEES; it never
        mutates game state itself.
        """
        self._eat.start(food_id, hunger_before, hunger_after)

    # ── Event layers ────────────────────────────────────────────────────────

    def _route_privacy(self, event, triggered) -> None:
        # The rect is computed during draw, so on the very first frame it is
        # still None. The layer swallows the event either way rather than
        # letting it fall through to the shop buttons underneath.
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._privacy_rect and self._privacy_rect.collidepoint(event.pos):
                triggered.append("privacy_ok")

    def _route_main(self, event, triggered) -> None:
        if event.type == pygame.MOUSEMOTION:
            self._hover = self._hit_main(event.pos)
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_s:
                self._shop.open(self._shop_rect.center)
            elif event.key == pygame.K_f and not self._eat.playing:
                self._food.open(self._feed_rect.center)
            elif event.key == pygame.K_r:
                self._rates.open(self._rate_rect.center
                                 if self._rate_rect else None)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._pressed = self._hit_main(event.pos)
            return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was, self._pressed = self._pressed, None
            hit = self._hit_main(event.pos)
            # Fire only when press and release land on the same target, so a
            # drag off a button cancels it.
            if hit is None or hit != was:
                return
            if hit == "feed" and not self._eat.playing:
                self._food.open(self._feed_rect.center)
            elif hit == "shop":
                self._shop.open(self._shop_rect.center)
            elif hit == "rate":
                self._rates.open(self._rate_rect.center)
            return

    def _hit_main(self, pos) -> str | None:
        if self._feed_rect.collidepoint(pos):
            return "feed"
        if self._shop_rect.collidepoint(pos):
            return "shop"
        if self._rate_rect is not None and self._rate_rect.collidepoint(pos):
            return "rate"
        return None

    # ── Currency roll ───────────────────────────────────────────────────────

    def _roll(self, key: str, target: int) -> int:
        """Ease the *displayed* balance toward the real one."""
        attr = f"_shown_{key}"
        cur = getattr(self, attr)
        if cur is None or theme.ANIM_SCALE <= 0:
            setattr(self, attr, float(target))
            return target
        if abs(cur - target) < 0.5:
            setattr(self, attr, float(target))
            return target
        setattr(self, attr, cur + (target - cur) * 0.22)
        return int(round(getattr(self, attr)))

    # ── Drawing ─────────────────────────────────────────────────────────────

    def _draw_silkscreen(self, surf, stage: str, shell=None) -> None:
        """Lettering printed on the case, above the screen."""
        sh = shell or skinmod.SHELL_DEFAULT
        device.draw_ink_text(surf, (28, 18), "TOKENGOTCHI", sh.text,
                             theme.FONT_CAPTION)
        # The STAGE label goes through ink adaptation for the same reason the
        # currency read-out does: hardcoded gold on the bare case measures
        # 1.03 contrast on Clear and 1.24 on Bone, five of eight shells
        # failing.
        lab = uikit.text(stage.upper(), theme.BITS, theme.FONT_CAPTION, bold=True)
        device.draw_ink_text(surf, (WINDOW_W - 28 - lab.get_width(), 18),
                             stage.upper(), theme.BITS, theme.FONT_CAPTION)

    def _draw_creature(self, inner, game_state, stage: str, hunger: float,
                       skin=None) -> int:
        """Draw the pet onto the SCREEN surface, magnified.

        Unmagnified the pet covers 6.2% of its stage and floats in a 96%-empty
        void. Magnification happens here, on the blit — `sprites.py` owns the
        artwork at its native size and is never touched for layout reasons.
        """
        dormant = getattr(game_state.creature, "dormancy_start", None) is not None
        hat = (None if getattr(self, "_clear_hat", False)
               else getattr(self, "_peek_hat", None)
               or getattr(game_state.creature, "hat_slot", None))
        sw, sh = (100, 110) if stage.lower() == "adult" else (80, 90)

        # Taller cell + drawn lower, so headwear has somewhere to go.
        cell = pygame.Surface((sw, sh + HAT_HEADROOM), pygame.SRCALPHA)
        draw_creature(cell, 0, HAT_HEADROOM, stage=stage, hat=hat,
                      frame=self._anim_frame, dormant=dormant, hunger=hunger)
        scaled = pygame.transform.scale(
            cell, (int(sw * PET_SCALE), int((sh + HAT_HEADROOM) * PET_SCALE))
        )

        cx = inner.get_width() // 2
        cy = int(inner.get_height() * 0.46)
        # Centre the BODY, not the padded cell, or the headroom would push the
        # creature down the screen.
        body_h = int(sh * PET_SCALE)
        pad_h = int(HAT_HEADROOM * PET_SCALE)
        top = cy - body_h // 2 - pad_h
        inner.blit(self._vignette, (cx - 85, cy + body_h // 2 - 18))
        inner.blit(scaled, (cx - scaled.get_width() // 2, top))

        # Eating plays beside the creature, not on top of it — the pet stays
        # fully visible as the food it's holding empties out next to it.
        anchor_x = min(inner.get_width() - 28,
                       cx + scaled.get_width() // 2 + 26)
        self._eat.draw(inner, (anchor_x, cy))

        if dormant:
            # Hardcoded CRT green inside a screen the player chose measures
            # 1.95 on DMG, and paints CRT green onto matte e-ink paper. The
            # skin carries its own phosphor; use it.
            sk = skin or skinmod.DEFAULT
            d = uikit.text("-- DORMANT --", ink.adapt(sk.phosphor, sk.base),
                           theme.FONT_CAPTION, bold=True)
            inner.blit(d, (cx - d.get_width() // 2, 10))
        elif stage.lower() == "egg":
            # A first-time player who sees only an unmoving egg and a hunger
            # bar that nothing they do affects has no way to know the pet
            # hatches from Claude Code usage at all -- this is the only place
            # that says so.
            sk = skin or skinmod.DEFAULT
            hint = uikit.text("USE CLAUDE CODE TO HATCH", sk.phosphor,
                              theme.FONT_CAPTION, bold=True)
            inner.blit(hint, (cx - hint.get_width() // 2, 10))
        return cy

    def _draw_controls(self, surf, bits: int, echoes: int, stage: str,
                       shell=None) -> None:
        """Physical buttons and embossed currency, moulded into the shell.

        FEED is amber because feeding spends BITS; SHOP is phosphor because the
        shop spends ECHOES. Colour carries meaning rather than decorating — a
        primary action sitting only 11 value-points above the background reads
        as an empty container.
        """
        # FOOD, not FEED: the button opens the menu rather than performing the
        # action. Enabled at the price of the CHEAPEST item, because with a
        # per-item cost that is the real affordability floor.
        cheapest = min(f.cost for f in foodmenu.FOODS)
        can_feed = (bits >= cheapest and stage.lower() != "egg"
                   and not self._eat.playing)

        self._feed_rect = pygame.Rect(26, 316, 176, 44)
        device.draw_button(
            surf, self._feed_rect, "FOOD", theme.BITS,
            enabled=can_feed,
            hovered=self._hover == "feed",
            pressed=self._pressed == "feed",
            shell_id=(shell.id if shell else None),
        )

        sw = 128
        self._shop_rect = pygame.Rect(WINDOW_W - 26 - sw, 316, sw, 44)
        device.draw_button(
            surf, self._shop_rect, "SHOP", theme.PHOSPHOR,
            hovered=self._hover == "shop",
            pressed=self._pressed == "shop",
            shell_id=(shell.id if shell else None),
        )

        cy = WINDOW_H - 74
        device.draw_currency(surf, 34, cy, self._roll("bits", bits),
                             "BITS", theme.BITS, shell=shell)
        device.draw_currency(surf, 162, cy, self._roll("echoes", echoes),
                             "ECHOES", theme.ECHOES, shell=shell)
        device.draw_vent(surf, WINDOW_H - 150, cy + 2, shell=shell)

        # LAST, after every piece of lettering -- see draw_sparkle. Suppressed
        # while the pet is mid-event so the chrome never competes with it.
        device.draw_sparkle(surf, shell, time.monotonic(),
                            suppress=self._shop.is_open)

    def _preview(self, dest, x: int, y: int, item_id: str) -> None:
        """Shop-row thumbnail.

        A hat previews as the pet wearing it. A SCREEN cannot: the thumbnail
        would be a picture of a display drawn on that same display, under the
        active skin's own scanlines — and every screen row would show an
        identical pet. So a screen previews as a swatch of ITSELF: its glass
        colour, its pattern, its phosphor.
        """
        from ..shop.catalogue import ItemKind  # local: avoids an import cycle
        item = shopcat.get(item_id)
        if item is not None and item.kind is ItemKind.SHELL:
            sh = skinmod.get_shell(item_id)
            n = shoppanel.ICON
            cell = pygame.Surface((n, n))
            cell.fill(sh.lo)
            face = uikit.round_rect((n - 6, n - 6), 7, sh.body,
                                    gradient_to=sh.hi, border=sh.hi,
                                    top_highlight=70)
            if sh.metal:
                # A metallic previewed as a flat gradient is a mustard square
                # or a grey one -- the player would be paying 90 ECHOES off a
                # thumbnail showing none of what they are buying. The ramp
                # survives compression to 36px and is the thing that sells it;
                # the two frozen glints are the swatch's one lie, and they earn
                # their place because a still cannot show the sweep.
                face = metal.face(sh.metal, (n - 6, n - 6)).convert_alpha()
                mask = uikit.round_rect((n - 6, n - 6), 7, (255, 255, 255),
                                        border=None)
                face = face.copy()
                face.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                atl = metal.atlas(sh.metal)
                for (gx, gy, ai, si) in ((n - 13, 7, 1, 5), (9, n - 15, 0, 3)):
                    g = atl[ai][si]
                    face.blit(g, (gx - g.get_width() // 2,
                                  gy - g.get_height() // 2),
                              special_flags=pygame.BLEND_RGBA_ADD)
            if sh.body_right:
                # Honour the asymmetry — previewing Joy-Con as a plain blue
                # square misrepresents the only thing that makes it Joy-Con.
                rt = uikit.round_rect((n - 6, n - 6), 7, sh.body_right,
                                      gradient_to=sh.hi_right or sh.body_right,
                                      border=sh.hi_right, top_highlight=70)
                face = face.copy()
                half = (n - 6) // 2
                face.blit(rt, (half, 0), pygame.Rect(half, 0, half, n))
            cell.blit(face, (3, 3))
            pygame.draw.rect(cell, sh.lo, (9, 10, n - 18, n - 22),
                             border_radius=3)
            dest.blit(cell, (x, y))
            return
        if item is not None and item.kind is ItemKind.SCREEN:
            sk = skinmod.get(item_id)
            n = shoppanel.ICON
            cell = pygame.Surface((n, n))
            cell.fill(sk.base)
            if sk.pattern != "none":
                cell.blit(device._pattern((n, n), sk.pattern,
                                          sk.period, sk.alpha), (0, 0))
            pygame.draw.rect(cell, sk.phosphor, (4, n - 11, n - 8, 4))
            pygame.draw.rect(cell, sk.edge, (0, 0, n, n), 1)
            dest.blit(cell, (x, y))
            return

        n = shoppanel.ICON
        cell = pygame.Surface((80, 90 + HAT_HEADROOM), pygame.SRCALPHA)
        draw_creature(cell, 0, HAT_HEADROOM, stage="baby", hat=item_id,
                      frame=0, dormant=False, hunger=100.0)
        # Crop to head-and-hat: at 36px a whole body is unreadable, and the hat
        # is the thing being sold.
        crop = cell.subsurface(pygame.Rect(8, HAT_HEADROOM - 40, 64, 64)).copy()
        dest.blit(pygame.transform.smoothscale(crop, (n, n)), (x, y))

    # ── Loop plumbing ───────────────────────────────────────────────────────

    def tick(self, fps: int = 30) -> None:
        self._clock.tick(fps)

    def should_quit(self) -> bool:
        return self._quit

    def close(self) -> None:
        pygame.quit()
