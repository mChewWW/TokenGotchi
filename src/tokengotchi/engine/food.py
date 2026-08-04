"""The menu. Six foods, each with a cost in BITS and a hunger value.

WHY SIX FOODS ARE NOT SIX COPIES OF ONE FOOD. If every item sits on the same
BITS-per-hunger line, the menu is decoration: whichever is cheapest to click
wins and the other five are dead content. So the line is deliberately NOT flat,
and it bends in a direction that makes the choice about commitment rather than
about arithmetic:

    large foods are EFFICIENT and fast; small foods are WASTEFUL-TO-SKIP but
    precise.

Cookie through Cake form the value ladder: Cookie is the worst value per BIT
on that ladder, Cake is exactly 25% better per BIT than Cookie, and Bread /
Apple / Cooked Steak sit in between, ascending. Bulk-buy the efficient item
when you have the bits and the appetite to use it, or top off precisely with
something cheap and small so a big item's tail doesn't go to waste.

OVERFLOW IS THE OTHER HALF OF IT. Hunger clamps at 100 for most items, so
feeding a big item to a nearly-full pet throws the difference away. That is
what stops the most efficient item being a strict upgrade in every situation,
and it is why the panel shows the balance before you commit.

THE GOLDEN APPLE IS NOT ON THE VALUE LADDER. It heals less than a Cake and
more than a Steak, and it is the single worst BITS-per-hunger value on the
whole menu — worse even than a Cookie. Its entire case for existing is that
it ALONE can push hunger past 100, up to 125 ("overheal"). You are not paying
for hunger points; you are paying for headroom.

Values are a deliberately weaker second pass than the first — the BITS-to-
hunger rate across the whole menu was too generous. The SHAPE is what
matters: efficiency (hunger per BIT) ascending Cookie -> Cake, with the
Golden Apple sitting outside that ladder entirely.
"""
from __future__ import annotations

from dataclasses import dataclass

HUNGER_MAX: float = 100.0


@dataclass(frozen=True)
class Food:
    id: str
    name: str
    cost: int             # BITS
    hunger: float         # points restored, before the clamp
    blurb: str
    cap: float = HUNGER_MAX   # hunger ceiling this food can push the pet to

    @property
    def per_bit(self) -> float:
        """Hunger per BIT. The number that makes the menu a choice."""
        return self.hunger / self.cost


# Ordered cheapest first — the panel lists them in this order, and it is also
# ascending size, so the list reads as a ramp rather than as a grid. Efficiency
# (per_bit) climbs down the Cookie -> Cake ladder: the big-ticket items are the
# good value. The Golden Apple sits outside that ladder — see module docstring.
FOODS: tuple[Food, ...] = (
    Food("food_cookie", "Cookie", 10, 5.5,
         "A biscuit. Barely a meal, and not cheap for what it is."),
    Food("food_bread", "Bread", 18, 10.0,
         "Honest and filling."),
    Food("food_apple", "Apple", 22, 12.5,
         "Crisp. The everyday choice."),
    Food("food_steak", "Cooked Steak", 33, 20.0,
         "A proper dinner, and proper value."),
    Food("food_cake", "Cake", 40, 27.5,
         "Absurd, and it pays for itself."),
    Food("food_golden_apple", "Golden Apple", 50, 25.0,
         "Food of the gods. Can overheal up to 125% hunger.",
         cap=125.0),
)

BY_ID: dict[str, Food] = {f.id: f for f in FOODS}
DEFAULT_ID = "food_apple"


def get(food_id: str | None) -> Food:
    """Resolve a food id, tolerating an unknown value from an older save."""
    return BY_ID.get(food_id or "", BY_ID[DEFAULT_ID])


def waste(food: Food, hunger: float) -> float:
    """Hunger this food would throw away at the pet's current level.

    Surfaced in the panel rather than discovered afterwards: a menu that lets
    you silently burn bits on a few points of hunger is a trap, not a choice.
    Measured against the food's OWN cap, so the Golden Apple's overheal room
    counts as capacity rather than waste.
    """
    return max(0.0, food.hunger - max(0.0, food.cap - hunger))
