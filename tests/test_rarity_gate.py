"""The legendary gate, wired to the catalogue instead of trusted to a flag.

`rarity_locked` is a hand-set boolean on the skin with NO structural link to
`catalogue.Rarity`, so nothing stops a legendary item leaving it `False` and
skipping the assertion it guards entirely. A gate nothing reaches is not a
gate, it is a comment — and the rule exists because a legendary that is "just
purple and nothing unique" is not legendary. These tests are what make the
flag mean something.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pygame  # noqa: E402

pygame.init()
pygame.display.set_mode((1, 1), pygame.HIDDEN)

from tokengotchi.renderer import skins  # noqa: E402
from tokengotchi.shop import catalogue  # noqa: E402
from tokengotchi.shop.catalogue import ItemKind, Rarity  # noqa: E402


def _legendary(kind):
    return {i.id for i in catalogue.of_kind(kind)
            if i.rarity is Rarity.LEGENDARY}


class TestLegendaryIsStructural:

    def test_every_legendary_shell_declares_rarity_locked(self):
        for sid in _legendary(ItemKind.SHELL):
            sh = skins.get_shell(sid)
            assert sh.rarity_locked, (
                f"{sid} is LEGENDARY in the catalogue but does not set "
                f"rarity_locked, so the structural gate never runs on it"
            )

    def test_every_legendary_screen_declares_rarity_locked(self):
        for sid in _legendary(ItemKind.SCREEN):
            sk = skins.get(sid)
            assert sk.rarity_locked, (
                f"{sid} is LEGENDARY in the catalogue but does not set "
                f"rarity_locked, so the structural gate never runs on it"
            )

    def test_a_legendary_shell_must_be_more_than_a_colour(self):
        """The gate must actually refuse. Proved, not assumed."""
        with pytest.raises(ValueError, match="more than"):
            skins.ShellSkin(
                id="shell_bad", name="Bad", blurb="just a colour",
                body=(120, 60, 60), hi=(180, 90, 90), lo=(40, 20, 20),
                text=(240, 200, 200), rarity_locked=True,
            )

    def test_metal_satisfies_the_structural_requirement(self):
        """A finish counts, and the reason is not that it was convenient.

        Metal is a luminance pattern rather than a colour — flat gold reads as
        mustard, and it is the ramp and the specular that make it read as gold.
        That is a change in how the surface is rendered, the same kind of claim
        `translucent` makes.
        """
        sh = skins.ShellSkin(
            id="shell_ok", name="OK", blurb="plated",
            body=(101, 61, 19), hi=(255, 247, 216), lo=(70, 40, 13),
            text=(255, 236, 186), metal="gold", rarity_locked=True,
        )
        assert sh.metal == "gold"


class TestPriceComesFromTheTier:

    @pytest.mark.parametrize("item_id,rarity", [
        ("shell_true_gold", Rarity.LEGENDARY),
        ("shell_true_silver", Rarity.EPIC),
        ("screen_true_gold", Rarity.LEGENDARY),
        ("screen_true_silver", Rarity.EPIC),
    ])
    def test_metal_items_priced_by_tier(self, item_id, rarity):
        item = catalogue.get(item_id)
        assert item is not None, f"{item_id} missing from the catalogue"
        assert item.rarity is rarity
        assert item.cost == rarity.price

    def test_skin_cost_matches_catalogue_cost(self):
        """Two sources for one price is how a catalogue drifts."""
        for i in catalogue.of_kind(ItemKind.SHELL):
            assert skins.get_shell(i.id).cost == i.cost, i.id
        for i in catalogue.of_kind(ItemKind.SCREEN):
            assert skins.get(i.id).cost == i.cost, i.id


class TestShopIsSortedByRarity:
    """The shop lists in catalogue order, so catalogue order IS the shop.

    Nothing in the code enforces that order — it holds only because the items
    are typed into the tables in tier order by hand. Append an epic after the
    legendaries and it lands between them, silently. An ordering that holds by
    accident is one nobody notices breaking.
    """

    @pytest.mark.parametrize("kind", [ItemKind.HAT, ItemKind.SCREEN,
                                      ItemKind.SHELL])
    def test_tiers_never_descend(self, kind):
        items = catalogue.of_kind(kind)
        orders = [i.rarity.order for i in items]
        assert orders == sorted(orders), (
            f"{kind.value} shop order jumps back down a tier: "
            + ", ".join(f"{i.name}={i.rarity.label}" for i in items)
        )

    @pytest.mark.parametrize("kind", [ItemKind.HAT, ItemKind.SCREEN,
                                      ItemKind.SHELL])
    def test_price_never_descends_either(self, kind):
        """Price follows tier, so a descending price means a mis-sorted tier."""
        costs = [i.cost for i in catalogue.of_kind(kind)]
        assert costs == sorted(costs), costs

    def test_order_is_total_and_matches_price(self):
        tiers = sorted(Rarity, key=lambda r: r.order)
        assert [t.price for t in tiers] == sorted(t.price for t in tiers), (
            "Rarity.order and Rarity.price disagree — a cheaper tier is "
            "sorted after a dearer one"
        )
