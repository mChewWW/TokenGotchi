"""The item catalogue — single source of truth for everything purchasable.

Without a catalogue, knowledge of an item is duplicated across the renderer
(labels, prices, affordability), ``engine/actions.py`` (the AVAILABLE_HATS set
and a literal price) and ``main.py`` (an if/elif over literal action ids) —
adding an item then means editing three files and silently doing nothing if
you miss one.

Adding an item means appending one ``Item`` here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Currency(str, Enum):
    BITS = "bits"
    ECHOES = "echoes"


class Rarity(str, Enum):
    """Tiers. Price is a PROPERTY of the tier, not a free field.

    Letting each item carry an arbitrary price is how a catalogue drifts into
    incoherence — two epics at different prices tell the player the tier means
    nothing. `Rarity.price` is the single source, so adding an item means
    choosing a tier, not inventing a number.
    """
    UNCOMMON = "uncommon"
    EPIC = "epic"
    LEGENDARY = "legendary"

    @property
    def price(self) -> int:
        return {"uncommon": 200, "epic": 450, "legendary": 900}[self.value]

    @property
    def order(self) -> int:
        """Cheapest tier first. Used to SORT the shop, not just to label it.

        The shop lists items in catalogue order, so without an explicit sort
        key the ordering is an emergent property of where a row happens to be
        typed in the tables below. That only holds while every item is written
        in tier order, and it breaks the moment one isn't: True Silver is epic
        but sits beside the legendaries in the table, so it would surface
        between them.

        Sorting at construction makes the table's own order irrelevant, which
        is the point — a new item can be added anywhere and still land in the
        right place.
        """
        return {"uncommon": 0, "epic": 1, "legendary": 2}[self.value]

    @property
    def label(self) -> str:
        return self.value.upper()


class ItemKind(str, Enum):
    CONSUMABLE = "consumable"   # bought and spent immediately; never owned
    HAT = "hat"                 # bought once, then owned and equippable
    SCREEN = "screen"           # a display skin for the device itself
    SHELL = "shell"             # a case skin for the device body


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    blurb: str
    kind: ItemKind
    currency: Currency
    cost: int
    rarity: Rarity | None = None

    @property
    def is_ownable(self) -> bool:
        return self.kind is not ItemKind.CONSUMABLE


CATALOGUE: tuple[Item, ...] = (
    Item(
        id="feed",
        name="Ration",
        blurb="Restores a little hunger.",
        kind=ItemKind.CONSUMABLE,
        currency=Currency.BITS,
        cost=3,
    ),
    Item(
        id="hat_a",
        name="Top Hat",
        blurb="Formalwear for a creature of standing.",
        kind=ItemKind.HAT,
        currency=Currency.ECHOES,
        cost=15,
    ),
    Item(
        id="hat_b",
        name="Crown",
        blurb="Heavy is the head.",
        kind=ItemKind.HAT,
        currency=Currency.ECHOES,
        cost=15,
    ),
)

# Cosmetics. Each entry names a TIER, never a price — Rarity owns that, so the
# catalogue cannot drift into two epics costing different amounts.
#
# Visual definitions live in renderer/skins.py (screens, cases) and
# renderer/sprites.py (hats); only commercial metadata is here, because
# catalogue.py is engine-side and must import without pygame (main.py runs
# headless in tests and on the watchdog thread). The drift guards in
# tests/test_shop_panel.py are what keep the two halves honest.
_HATS = (
    ("hat_cap", "Ball Cap", "Worn backwards, obviously.", Rarity.UNCOMMON),
    ("hat_beanie", "Beanie", "For a cold little skull.", Rarity.UNCOMMON),
    ("hat_a", "Top Hat", "Formalwear for a creature of standing.", Rarity.EPIC),
    ("hat_wizard", "Wizard Hat", "Starred, and slightly too large.", Rarity.EPIC),
    ("hat_b", "Crown", "Heavy is the head.", Rarity.LEGENDARY),
    ("hat_halo", "Halo", "Unearned.", Rarity.LEGENDARY),
)

_SCREENS = (
    ("screen_amber", "P3 Amber", "Warm terminal glow.", Rarity.UNCOMMON),
    ("screen_vfd", "Vacuum Fluorescent", "Hi-fi cyan, 1982.", Rarity.UNCOMMON),
    ("screen_grille", "Aperture Grille", "RGB phosphor stripes.", Rarity.EPIC),
    ("screen_dmg", "Dot-Matrix LCD", "Four greens. Nothing else.", Rarity.EPIC),
    ("screen_eink", "E-Ink", "Matte paper. No backlight.", Rarity.LEGENDARY),
    ("screen_scope", "Oscilloscope", "Vector traces on a long-persistence tube.",
     Rarity.LEGENDARY),
    ("screen_true_silver", "True Silver", "Argent. Cold and exact.", Rarity.EPIC),
    ("screen_true_gold", "True Gold", "Every pixel struck in bullion.",
     Rarity.LEGENDARY),
)

_SHELLS = (
    ("shell_graphite", "Graphite", "Matte black, no nonsense.", Rarity.UNCOMMON),
    ("shell_bone", "Bone", "Sun-yellowed since 1989.", Rarity.UNCOMMON),
    ("shell_seafoam", "Seafoam", "Pastel, faintly medical.", Rarity.UNCOMMON),
    ("shell_crimson", "Crimson", "Deep red, gloss finish.", Rarity.EPIC),
    ("shell_joycon", "Joy-Con", "Blue left, red right. Asymmetric on purpose.",
     Rarity.EPIC),
    ("shell_atomic", "Atomic Purple", "Tinted, and you can see through it.",
     Rarity.LEGENDARY),
    ("shell_clear", "Clear", "No tint at all. Every component on show.",
     Rarity.LEGENDARY),
    ("shell_true_silver", "True Silver",
     "Argent. Brushed, and it catches the light.", Rarity.EPIC),
    ("shell_true_gold", "True Gold", "Struck, not painted.", Rarity.LEGENDARY),
)


def _mk(rows, kind):
    """Build a kind's items, ordered by tier and stable within it.

    `sorted` is stable, so items of the same rarity keep the order they were
    written in — the tables stay readable as authored groupings while the shop
    is guaranteed to ascend.
    """
    return tuple(
        Item(id=i, name=n, blurb=b, kind=kind, currency=Currency.ECHOES,
             cost=r.price, rarity=r)
        for i, n, b, r in sorted(rows, key=lambda row: row[3].order)
    )


# hat_a / hat_b already exist as HAT entries above; rebuild the whole ownable
# set from the tables so tier and price are defined in exactly one place.
CATALOGUE = tuple(i for i in CATALOGUE if i.kind is ItemKind.CONSUMABLE)
CATALOGUE = (CATALOGUE + _mk(_HATS, ItemKind.HAT)
             + _mk(_SCREENS, ItemKind.SCREEN)
             + _mk(_SHELLS, ItemKind.SHELL))

_BY_ID: dict[str, Item] = {item.id: item for item in CATALOGUE}


def get(item_id: str) -> Item | None:
    """Return the Item with this id, or None if it is not in the catalogue."""
    return _BY_ID.get(item_id)


def ownable() -> tuple[Item, ...]:
    """Catalogue entries that persist once bought — what the shop lists."""
    return tuple(i for i in CATALOGUE if i.is_ownable)


def of_kind(kind: ItemKind) -> tuple[Item, ...]:
    return tuple(i for i in CATALOGUE if i.kind is kind)


def price_of(item_id: str) -> int | None:
    item = get(item_id)
    return None if item is None else item.cost
