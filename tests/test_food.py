"""The food menu, and the property that stops it being decoration.

A six-item menu whose items all sit on one efficiency line is not a choice —
whichever is cheapest per point wins every time and the other five are dead
content. These tests pin the shape that makes each one worth picking: the
big-ticket items are the good value, and the cheap ones stay relevant only
because they are precise enough not to waste a big item's overflow.
"""
from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tokengotchi.engine import food  # noqa: E402
from tokengotchi.engine.actions import HUNGER_MAX, feed_item  # noqa: E402
from tokengotchi.engine.creature import (  # noqa: E402
    DORMANCY_TRIGGER_HOURS,
    Creature,
    Stage,
)


def _dormant_time(c):
    from datetime import timedelta
    return c.last_hunger_update + timedelta(hours=DORMANCY_TRIGGER_HOURS + 1)
from tokengotchi.engine.wallet import Wallet  # noqa: E402


def _presses(f):
    return math.ceil(HUNGER_MAX / f.hunger)


_LADDER_IDS = (
    "food_cookie", "food_bread", "food_apple", "food_steak", "food_cake",
)


class TestNothingOnTheMenuIsAMistake:

    def test_efficiency_rises_as_size_rises(self):
        """Big is cheap per point. Paying more up front buys a better rate.

        The Golden Apple sits OUTSIDE this ladder — its case for existing is
        overheal, not value — so it is excluded here and checked on its own
        below.
        """
        ladder = [food.BY_ID[i] for i in _LADDER_IDS]
        eff = [f.per_bit for f in ladder]
        assert eff == sorted(eff), eff

    def test_cake_is_25pct_more_efficient_than_cookie(self):
        cookie = food.BY_ID["food_cookie"]
        cake = food.BY_ID["food_cake"]
        assert cake.per_bit == pytest.approx(cookie.per_bit * 1.25)

    def test_golden_apple_is_the_worst_value_on_the_menu(self):
        """Its payoff is exclusive overheal, not BITS efficiency."""
        gold = food.BY_ID["food_golden_apple"]
        others = [f.per_bit for f in food.FOODS if f.id != gold.id]
        assert gold.per_bit < min(others)

    def test_golden_apple_heals_between_steak_and_cake(self):
        steak = food.BY_ID["food_steak"]
        cake = food.BY_ID["food_cake"]
        gold = food.BY_ID["food_golden_apple"]
        assert steak.hunger < gold.hunger < cake.hunger

    def test_only_the_golden_apple_can_overheal(self):
        for f in food.FOODS:
            if f.id == "food_golden_apple":
                assert f.cap > HUNGER_MAX
            else:
                assert f.cap == HUNGER_MAX

    def test_presses_to_fill_fall_as_size_rises(self):
        ladder = [food.BY_ID[i] for i in _LADDER_IDS]
        p = [_presses(f) for f in ladder]
        assert p == sorted(p, reverse=True), p

    def test_total_cost_to_fill_falls_with_convenience(self):
        """Buying big is strictly the better total price, not just the better
        rate — the counterweight is overflow, not sticker price: a nearly-full
        pet wastes a big item's tail, which is what keeps a Cookie worth
        owning even though it is the worst per-BIT value on the ladder."""
        ladder = [food.BY_ID[i] for i in _LADDER_IDS]
        fills = [_presses(f) * f.cost for f in ladder]
        assert fills == sorted(fills, reverse=True), fills
        assert len(set(fills)) == len(fills), "two foods fill for the same price"

    def test_every_food_has_art(self):
        from tokengotchi.renderer import fooditems
        for f in food.FOODS:
            assert f.id in fooditems.ART, f.id
            rows = fooditems.ART[f.id]
            assert len(rows) == fooditems.GRID
            assert all(len(r) == fooditems.GRID for r in rows), f.id

    def test_art_is_distinguishable_without_colour(self):
        """The screens that quantise destroy the palette, so the SILHOUETTE
        has to carry identity. Compare the on/off masks pairwise."""
        from tokengotchi.renderer import fooditems
        masks = {f.id: "".join("1" if c != "." else "0"
                               for r in fooditems.ART[f.id] for c in r)
                 for f in food.FOODS}
        ids = list(masks)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                same = sum(x == y for x, y in zip(masks[a], masks[b]))
                pct = same / len(masks[a])
                assert pct < 0.92, (
                    f"{a} and {b} are {pct:.0%} identical in silhouette — on a "
                    f"quantising screen they would be the same picture"
                )


class TestFeeding:

    def test_feeding_costs_the_item_and_restores_the_item(self):
        c = Creature(stage=Stage.ADULT, hunger=10.0)
        w = Wallet(bits=100)
        assert feed_item(c, w, "food_bread")
        assert w.bits == 100 - food.BY_ID["food_bread"].cost
        assert c.hunger == pytest.approx(10.0 + food.BY_ID["food_bread"].hunger)

    def test_golden_apple_overheals_past_the_normal_max(self):
        """The Golden Apple alone can push hunger past 100, up to its own
        125 cap — the payoff for being the worst BITS value on the menu.

        Starting hunger is already above the normal 100 max: that is only
        reachable via a prior overheal, which is exactly the state this is
        meant to cap.
        """
        c = Creature(stage=Stage.ADULT, hunger=105.0)
        w = Wallet(bits=200)
        f = food.BY_ID["food_golden_apple"]
        assert feed_item(c, w, "food_golden_apple")
        assert c.hunger == pytest.approx(f.cap)
        assert w.bits == 200 - f.cost

    def test_other_foods_still_clamp_at_the_normal_max(self):
        """Overheal is a Golden Apple exclusive, not a general hunger rule."""
        c = Creature(stage=Stage.ADULT, hunger=90.0)
        w = Wallet(bits=200)
        assert feed_item(c, w, "food_cake")
        assert c.hunger == HUNGER_MAX

    def test_a_smaller_food_never_undoes_an_overheal(self):
        """Feeding a normal-cap food while overhealed must not clamp hunger
        DOWN to 100 and destroy Golden Apple overheal that was already paid
        for. The cap is a ceiling on what THIS food can add, not a ceiling
        that can pull existing hunger backwards."""
        c = Creature(stage=Stage.ADULT, hunger=125.0)
        w = Wallet(bits=200)
        assert feed_item(c, w, "food_cookie")
        assert c.hunger == pytest.approx(125.0)

        c2 = Creature(stage=Stage.ADULT, hunger=110.0)
        assert feed_item(c2, w, "food_apple")
        assert c2.hunger == pytest.approx(110.0)

    def test_waste_is_reported_before_the_click(self):
        """Waste is measured against each food's OWN cap, so the Golden
        Apple's overheal room counts as capacity rather than as waste."""
        f = food.BY_ID["food_golden_apple"]
        assert food.waste(f, 110.0) == pytest.approx(10.0)
        assert food.waste(f, 0.0) == 0.0
        assert food.waste(food.BY_ID["food_cookie"], 0.0) == 0.0

    def test_cannot_afford_is_a_no_op(self):
        c = Creature(stage=Stage.ADULT, hunger=10.0)
        w = Wallet(bits=3)
        assert not feed_item(c, w, "food_cake")
        assert (w.bits, c.hunger) == (3, 10.0)

    def test_eggs_refuse_food(self):
        c = Creature(stage=Stage.EGG, hunger=10.0)
        w = Wallet(bits=500)
        assert not feed_item(c, w, "food_apple")
        assert w.bits == 500

    def test_feeding_wakes_a_dormant_pet(self):
        c = Creature(stage=Stage.ADULT, hunger=0.0)
        c.check_dormancy(_dormant_time(c))
        w = Wallet(bits=200)
        assert feed_item(c, w, "food_steak")
        assert c.stage is not Stage.DORMANT

    def test_unknown_food_is_a_no_op(self):
        c = Creature(stage=Stage.ADULT, hunger=10.0)
        w = Wallet(bits=500)
        assert not feed_item(c, w, "food_nonexistent")
        assert w.bits == 500

class TestEatingAnimation:

    def test_every_food_has_three_consumption_stages(self):
        from tokengotchi.renderer import fooditems
        for f in food.FOODS:
            stages = fooditems.stages(f.id)
            assert stages is not None and len(stages) == 3
            for grid in stages:
                assert len(grid) == fooditems.GRID
                assert all(len(r) == fooditems.GRID for r in grid)

    def test_each_stage_eats_more_than_the_last(self):
        """Half-eaten has less silhouette mass than whole, and almost-gone
        less still — the animation must visibly shrink, not just recolour."""
        from tokengotchi.renderer import fooditems
        for f in food.FOODS:
            whole, half, gone = fooditems.stages(f.id)
            mass = [sum(c != "." for row in g for c in row)
                    for g in (whole, half, gone)]
            assert mass[0] > mass[1] > mass[2], (f.id, mass)

    def test_animation_seeds_from_the_committed_hunger_not_a_guess(self):
        """`start()` is only ever called with the ALREADY-FINAL post-feed
        hunger — engine state commits instantly regardless of animation."""
        from tokengotchi.renderer.eat_animation import EatAnimation
        anim = EatAnimation()
        assert not anim.playing
        assert anim.displayed_hunger(42.0) == 42.0

        anim.start("food_cake", hunger_before=10.0, hunger_after=37.5)
        assert anim.playing
        assert anim.displayed_hunger(37.5) == pytest.approx(10.0)

        anim.update(1000.0)
        assert not anim.playing
        assert anim.displayed_hunger(37.5) == pytest.approx(37.5)

    def test_animation_stage_advances_then_stops(self):
        from tokengotchi.renderer.eat_animation import EatAnimation
        anim = EatAnimation()
        anim.start("food_apple", hunger_before=0.0, hunger_after=12.5)
        seen = set()
        for _ in range(60):
            seen.add(anim.stage())
            anim.update(0.05)
            if not anim.playing:
                break
        assert seen == {0, 1, 2}
        assert not anim.playing

    def test_feeding_logs_the_day_for_progression(self):
        """BABY -> ADULT is gated on distinct feeding days, so the menu must
        not quietly stop counting."""
        c = Creature(stage=Stage.BABY, hunger=10.0)
        w = Wallet(bits=500)
        assert feed_item(c, w, "food_apple")
        assert len(c.daily_feeding_log) == 1
