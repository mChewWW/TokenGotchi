"""Shop modal logic.

The *renderer* is deliberately outside automated coverage: nothing here asserts
pixels. Hit-testing, the modal state machine and input isolation are pure logic,
and they are exactly the class of bug that shipping a modal untested would hide
— click-through, stale hit rects, Esc not closing, disabled controls firing
silently.
"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

pygame.init()
pygame.display.set_mode((1, 1))

from tokengotchi.renderer import theme  # noqa: E402
from tokengotchi.renderer.shop_panel import ItemState, Phase, ShopPanel  # noqa: E402
from tokengotchi.shop import catalogue  # noqa: E402


def _settled() -> ShopPanel:
    """An open panel with its entrance animation finished."""
    p = ShopPanel()
    p.open()
    for _ in range(40):
        p.update(1 / 30)
    return p


def _ev(t, **kw):
    return pygame.event.Event(t, **kw)


def _click(panel, pos, **state):
    """Full press+release at pos. Returns emitted actions."""
    out = []
    out += panel.handle_event(_ev(pygame.MOUSEBUTTONDOWN, pos=pos, button=1), **state)
    out += panel.handle_event(_ev(pygame.MOUSEBUTTONUP, pos=pos, button=1), **state)
    return out


# Derived from the catalogue, not hardcoded: "rich" means "can afford anything
# in the shop". A literal here silently becomes "broke" the moment prices rise,
# and the purchase-flow tests then pass or fail for the wrong reason.
_DEAREST = max(i.cost for i in catalogue.ownable())

BROKE = dict(inventory=[], hat_slot=None, bits=0, echoes=0)
RICH = dict(inventory=[], hat_slot=None, bits=_DEAREST + 1, echoes=_DEAREST + 1)


class TestStateMachine:
    def test_starts_closed(self):
        assert ShopPanel().phase is Phase.CLOSED

    def test_open_then_settle(self):
        p = ShopPanel()
        p.open()
        assert p.phase is Phase.OPENING
        assert p.is_open
        for _ in range(40):
            p.update(1 / 30)
        assert p.phase is Phase.OPEN

    def test_close_is_faster_than_open(self):
        """A slow dismiss reads as lag."""
        assert theme.DUR_PANEL_OUT < theme.DUR_PANEL_IN

    def test_closing_reaches_closed(self):
        p = _settled()
        p.close()
        assert p.phase is Phase.CLOSING
        for _ in range(40):
            p.update(1 / 30)
        assert p.phase is Phase.CLOSED
        assert not p.is_open

    def test_toggle(self):
        p = ShopPanel()
        p.toggle()
        assert p.is_open
        for _ in range(40):
            p.update(1 / 30)
        p.toggle()
        for _ in range(40):
            p.update(1 / 30)
        assert not p.is_open

    def test_double_open_is_a_noop(self):
        p = ShopPanel()
        p.open()
        p.update(0.05)
        t = p._t
        p.open()
        assert p._t == t, "re-opening must not restart the animation"

    def test_anim_scale_zero_opens_instantly(self):
        """The escape hatch, and what makes the end state inspectable."""
        old = theme.ANIM_SCALE
        theme.ANIM_SCALE = 0.0
        try:
            p = ShopPanel()
            p.open()
            p.update(1 / 30)
            assert p.phase is Phase.OPEN
        finally:
            theme.ANIM_SCALE = old


class TestInputIsolation:
    """The modal must swallow input. This is where naive modals leak."""

    def test_closed_panel_emits_nothing(self):
        p = ShopPanel()
        assert p.handle_event(_ev(pygame.MOUSEBUTTONDOWN, pos=(200, 225),
                                  button=1), **RICH) == []

    def test_no_hit_rects_while_animating(self):
        """Stale rects are how a click becomes an accidental purchase."""
        p = ShopPanel()
        p.open()
        p.update(1 / 60)
        assert p._rows == []
        assert not p.accepts_input

    def test_clicks_inert_during_entrance(self):
        p = ShopPanel()
        p.open()
        p.update(1 / 60)
        assert _click(p, (200, 225), **RICH) == []

    def test_escape_closes(self):
        p = _settled()
        p.handle_event(_ev(pygame.KEYDOWN, key=pygame.K_ESCAPE), **RICH)
        assert p.phase is Phase.CLOSING

    def test_escape_does_not_quit(self):
        p = _settled()
        out = p.handle_event(_ev(pygame.KEYDOWN, key=pygame.K_ESCAPE), **RICH)
        assert "quit" not in out

    def test_drag_out_does_not_dismiss(self):
        """Press inside, release outside — must not count as click-outside."""
        p = _settled()
        p._panel_rect = pygame.Rect(20, 100, 356, 250)
        p._rows = [("hat_a", pygame.Rect(30, 140, 330, 58))]
        p.handle_event(_ev(pygame.MOUSEBUTTONDOWN, pos=(100, 160), button=1), **RICH)
        p.handle_event(_ev(pygame.MOUSEBUTTONUP, pos=(5, 5), button=1), **RICH)
        assert p.phase is Phase.OPEN, "dragging out must not close the panel"

    def test_press_outside_release_inside_does_not_dismiss(self):
        p = _settled()
        p._panel_rect = pygame.Rect(20, 100, 356, 250)
        p._rows = []
        p.handle_event(_ev(pygame.MOUSEBUTTONDOWN, pos=(5, 5), button=1), **RICH)
        p.handle_event(_ev(pygame.MOUSEBUTTONUP, pos=(200, 200), button=1), **RICH)
        assert p.phase is Phase.OPEN

    def test_click_fully_outside_dismisses(self):
        p = _settled()
        p._panel_rect = pygame.Rect(20, 100, 356, 250)
        p._rows = []
        p.handle_event(_ev(pygame.MOUSEBUTTONDOWN, pos=(5, 5), button=1), **RICH)
        p.handle_event(_ev(pygame.MOUSEBUTTONUP, pos=(6, 6), button=1), **RICH)
        assert p.phase is Phase.CLOSING


class TestItemStates:
    def _hat(self):
        return catalogue.get("hat_a")

    def test_affordable(self):
        cost = self._hat().cost
        assert ShopPanel.state_of(
            self._hat(), [], None, 0, cost) is ItemState.AFFORDABLE

    def test_unaffordable(self):
        cost = self._hat().cost
        assert ShopPanel.state_of(
            self._hat(), [], None, 0, cost - 1) is ItemState.UNAFFORDABLE

    def test_owned(self):
        assert ShopPanel.state_of(self._hat(), ["hat_a"], None, 0, 0) is ItemState.OWNED

    def test_equipped(self):
        assert ShopPanel.state_of(
            self._hat(), ["hat_a"], "hat_a", 0, 0
        ) is ItemState.EQUIPPED

    def test_owned_beats_affordability(self):
        """Owning it must never render as a purchase, however rich you are."""
        assert ShopPanel.state_of(
            self._hat(), ["hat_a"], None, 999, 999
        ) is ItemState.OWNED


class TestPurchaseFlow:
    def _armed(self, **state):
        p = _settled()
        p._panel_rect = pygame.Rect(20, 100, 356, 250)
        p._rows = [("hat_a", pygame.Rect(30, 140, 330, 58))]
        return p

    def test_affordable_click_buys_and_equips(self):
        p = self._armed()
        out = _click(p, (100, 160), **RICH)
        assert out == ["buy:hat_a", "equip:hat_a"]

    def test_unaffordable_click_is_never_silent(self):
        """A dead click reads as a bug. It must reject visibly instead."""
        p = self._armed()
        out = _click(p, (100, 160), **BROKE)
        assert out == []
        assert "hat_a" in p._reject, "must trigger the rejection shake"

    def test_owned_click_equips_without_buying(self):
        p = self._armed()
        out = _click(p, (100, 160), inventory=["hat_a"], hat_slot=None,
                     bits=99, echoes=99)
        assert out == ["equip:hat_a"]
        assert not any(a.startswith("buy") for a in out)

    def test_equipped_click_removes(self):
        p = self._armed()
        out = _click(p, (100, 160), inventory=["hat_a"], hat_slot="hat_a",
                     bits=99, echoes=99)
        assert out == ["unequip"]

    def test_release_on_different_row_does_not_fire(self):
        p = self._armed()
        p._rows.append(("hat_b", pygame.Rect(30, 210, 330, 58)))
        p.handle_event(_ev(pygame.MOUSEBUTTONDOWN, pos=(100, 160), button=1), **RICH)
        out = p.handle_event(_ev(pygame.MOUSEBUTTONUP, pos=(100, 230), button=1), **RICH)
        assert out == []


class TestCatalogue:
    def test_consumable_is_not_listed_in_shop_rows(self):
        """feed is a verb on the main screen, not merchandise."""
        assert "feed" not in [i.id for i in catalogue.ownable()]

    def test_ownables_cover_every_shop_tab(self):
        """Every tab must have stock, or it opens on an empty list."""
        from tokengotchi.renderer.shop_panel import TABS
        kinds = {i.kind for i in catalogue.ownable()}
        for label, kind in TABS:
            assert kind in kinds, f"tab {label!r} has no items"

    def test_screen_skins_match_the_renderer(self):
        """catalogue.py is engine-side and cannot import pygame, so screen
        metadata is duplicated from renderer/skins.py. This is the guard that
        stops the two drifting — a skin in one and not the other would render
        as a purchasable item that does nothing, or a skin nobody can buy."""
        from tokengotchi.renderer import skins
        from tokengotchi.shop.catalogue import ItemKind
        shop_ids = {i.id for i in catalogue.of_kind(ItemKind.SCREEN)}
        renderer_ids = {s.id for s in skins.purchasable()}
        assert shop_ids == renderer_ids, (
            f"drift — shop-only: {shop_ids - renderer_ids}, "
            f"renderer-only: {renderer_ids - shop_ids}")

    def test_shell_skins_match_the_renderer(self):
        """Same drift guard as screens — catalogue.py cannot import pygame."""
        from tokengotchi.renderer import skins
        from tokengotchi.shop.catalogue import ItemKind
        shop_ids = {i.id for i in catalogue.of_kind(ItemKind.SHELL)}
        renderer_ids = {s.id for s in skins.purchasable_shells()}
        assert shop_ids == renderer_ids, (
            f"drift — shop-only: {shop_ids - renderer_ids}, "
            f"renderer-only: {renderer_ids - shop_ids}")

    def test_shell_prices_match_the_renderer(self):
        from tokengotchi.renderer import skins
        from tokengotchi.shop.catalogue import ItemKind
        for item in catalogue.of_kind(ItemKind.SHELL):
            assert skins.get_shell(item.id).cost == item.cost, item.id

    def test_screen_prices_match_the_renderer(self):
        from tokengotchi.renderer import skins
        from tokengotchi.shop.catalogue import ItemKind
        for item in catalogue.of_kind(ItemKind.SCREEN):
            assert skins.get(item.id).cost == item.cost, item.id

    def test_field_skins_match_the_renderer(self):
        """Same drift guard as screens/shells — catalogue.py cannot import pygame."""
        from tokengotchi.renderer import fields
        from tokengotchi.shop.catalogue import ItemKind
        shop_ids = {i.id for i in catalogue.of_kind(ItemKind.FIELD)}
        renderer_ids = {f.id for f in fields.purchasable_fields()}
        assert shop_ids == renderer_ids, (
            f"drift — shop-only: {shop_ids - renderer_ids}, "
            f"renderer-only: {renderer_ids - shop_ids}")

    def test_field_prices_match_the_renderer(self):
        from tokengotchi.renderer import fields
        from tokengotchi.shop.catalogue import ItemKind
        for item in catalogue.of_kind(ItemKind.FIELD):
            assert fields.get_field(item.id).cost == item.cost, item.id

    def test_field_tab_present_and_equippable(self):
        """Confirms the FIELD tab and the equip round-trip actually work end
        to end, not just that the catalogue/renderer registries match."""
        from tokengotchi.shop.catalogue import ItemKind
        from tokengotchi.engine.actions import equip_field
        from tokengotchi.renderer.shop_panel import TABS
        assert ("FIELD", ItemKind.FIELD) in TABS

        class _FakeState:
            field_slot = None

        state = _FakeState()
        assert equip_field(state, ["field_hearts"], "field_hearts") is True
        assert state.field_slot == "field_hearts"
        assert equip_field(state, ["field_hearts"], None) is True
        assert state.field_slot is None

    def test_hats_have_a_drawing_function(self):
        """Every catalogue hat must actually render.

        Hats are the third place where commercial metadata (catalogue.py) and
        visual definition (sprites.py) are separated. A hat in one and not the
        other sells for real ECHOES and puts nothing on the creature's head.
        """
        import os
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        from tokengotchi.renderer import sprites
        from tokengotchi.shop.catalogue import ItemKind
        for item in catalogue.of_kind(ItemKind.HAT):
            surf = pygame.Surface((120, 140), pygame.SRCALPHA)
            sprites.draw_creature(surf, 10, 46, "baby", item.id, 0, False, 90.0)
            bare = pygame.Surface((120, 140), pygame.SRCALPHA)
            sprites.draw_creature(bare, 10, 46, "baby", None, 0, False, 90.0)
            a = pygame.surfarray.array_alpha(surf).astype(int).sum()
            b = pygame.surfarray.array_alpha(bare).astype(int).sum()
            assert a != b, f"{item.id} renders nothing on the creature"

    def test_every_rarity_tier_is_stocked(self):
        """A tier with no items is a price band the player never sees."""
        from tokengotchi.shop.catalogue import Rarity
        tiers = {i.rarity for i in catalogue.ownable() if i.rarity}
        assert tiers == set(Rarity)

    def test_price_follows_the_tier(self):
        """Rarity owns price. Two epics at different costs would make the
        tier meaningless."""
        for item in catalogue.ownable():
            if item.rarity is not None:
                assert item.cost == item.rarity.price, item.id

    def test_unknown_id(self):
        assert catalogue.get("nope") is None

    def test_hat_kippah_is_epic_and_priced_at_450(self):
        """A specific catalogue entry, not just the generic tier sweep above:
        pins the exact id/rarity/price a designer expects to find."""
        from tokengotchi.shop.catalogue import Rarity
        item = catalogue.get("hat_kippah")
        assert item is not None
        assert item.rarity is Rarity.EPIC
        assert item.cost == 450


class TestHiddenHatWarning:
    """Hats are invisible at egg stage and below 10% hunger.

    sprites.draw_creature returns before the hat layer in both cases, so the
    shop must warn rather than take 15 ECHOES and render nothing.
    """

    def test_egg_cannot_wear_hats(self):
        from tokengotchi.renderer.shop_panel import hat_hidden_reason
        assert hat_hidden_reason("egg", 100.0) is not None
        assert hat_hidden_reason("EGG", 100.0) is not None

    def test_starving_hides_hats(self):
        from tokengotchi.renderer.shop_panel import hat_hidden_reason
        assert hat_hidden_reason("adult", 9.9) is not None

    def test_boundary_matches_the_sprite_code(self):
        """sprites.py suppresses the hat when _hunger_state is 'dying' (<10)."""
        from tokengotchi.renderer.shop_panel import hat_hidden_reason
        assert hat_hidden_reason("adult", 10.0) is None
        assert hat_hidden_reason("adult", 9.99) is not None

    def test_healthy_adult_is_fine(self):
        from tokengotchi.renderer.shop_panel import hat_hidden_reason
        assert hat_hidden_reason("adult", 80.0) is None
        assert hat_hidden_reason("baby", 50.0) is None
