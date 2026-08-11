"""Player actions: feeding and dressing the creature."""

from __future__ import annotations

from datetime import datetime, timezone

from tokengotchi.engine import food as foodmenu
from tokengotchi.engine.creature import Creature, Stage
from tokengotchi.engine.wallet import Wallet
from tokengotchi.shop import catalogue
from tokengotchi.shop.catalogue import Currency, ItemKind

# Feeding constants
BITS_PER_FEED: int = 3               # minimum cost per feed call
# One press restores a quarter of the bar. At a 3 BITS -> 5.01 hunger
# granularity that would be ~32 presses a day at 1.0x drain and ~96 at 3.0x --
# the drain multiplier multiplying the CLICK COUNT, which is RSI rather than
# tension. Coarse granularity fixes that; the BITS-per-hunger economy is
# untouched by it (25 / 1.67 = 15).
FEED_HUNGER: float = 25.0
FEED_COST: int = 15
HUNGER_PER_BIT: float = 1.67        # 1 BITS restores 1.67 hunger points (3 BITS = ~5%)
HUNGER_MAX: float = 100.0

# Available hats — derived from the catalogue so there is one source of truth.
AVAILABLE_HATS: frozenset[str] = frozenset(
    i.id for i in catalogue.CATALOGUE if i.kind is ItemKind.HAT
)


def feed(
    creature: Creature,
    wallet: Wallet,
    bits_to_spend: int = 1,
    now: datetime | None = None,
) -> bool:
    """Feed the creature.

    Args:
        creature: The creature to feed.
        wallet:   The player's wallet.
        bits_to_spend: Number of BITS to spend (minimum 1).
                  Each BITS restores HUNGER_PER_BIT (1.67) hunger points,
                  capped at 100.
        now: Current time (defaults to datetime.now(timezone.utc)).

    Returns True on success, False if:
      - The creature is an EGG (cannot feed eggs)
      - BITS balance is insufficient
      - bits_to_spend < 1

    On success the creature's hunger is refilled proportionally and the
    feeding date is logged for the BABY → ADULT stage check.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if bits_to_spend < BITS_PER_FEED:
        return False

    # Cannot feed an Egg
    if creature.stage is Stage.EGG:
        return False

    # Try to spend the bits (no-op on failure)
    if not wallet.spend_bits(bits_to_spend):
        return False

    # Compute new hunger. Clamped to HUNGER_MAX as a CEILING on the gain, not
    # a ceiling on the result — a pet already overhealed past 100 (only
    # reachable via the Golden Apple) must never be pulled back down to 100
    # by a smaller food.
    hunger_gain = bits_to_spend * HUNGER_PER_BIT
    new_hunger = max(creature.hunger, min(HUNGER_MAX, creature.hunger + hunger_gain))

    if creature.stage is Stage.DORMANT:
        creature.exit_dormancy(new_hunger)
    else:
        creature.hunger = new_hunger

    # Log today's feeding date (for BABY → ADULT progression)
    creature.record_feeding(now)

    return True


def feed_item(
    creature: Creature,
    wallet: Wallet,
    food_id: str,
    now: datetime | None = None,
) -> bool:
    """Feed one item off the menu.

    Kept separate from `feed()` rather than folded into it. `feed()` takes a
    number of BITS and derives hunger from HUNGER_PER_BIT, which is exactly the
    flat line the menu exists to break: a menu whose items all sit on one
    efficiency curve is decoration. Here cost and hunger are independent
    properties of the item, so a Cookie can be the best value in the game and a
    Golden Apple the worst-but-fastest.

    Overflow is CLAMPED, not refused. Refusing a big food on a nearly-full pet
    would be a modal error message for a mistake the player can already see
    coming — the panel shows the balance on each row before the click. Letting
    them spend it anyway is the honest version.

    The clamp is PER-ITEM, not the flat HUNGER_MAX: most food caps at 100 like
    `feed()` does, but the Golden Apple's `cap` is 125, which is the whole
    point of its overheal.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    item = foodmenu.BY_ID.get(food_id)
    if item is None:
        return False
    if creature.stage is Stage.EGG:
        return False
    if not wallet.spend_bits(item.cost):
        return False

    # cap is a CEILING ON THE GAIN, not on the result: a pet already sitting
    # above THIS item's cap (e.g. overhealed to 125 by a Golden Apple, then
    # fed a normal food whose cap is 100) must not be dragged back down —
    # that food's hunger value is simply wasted, exactly as `food.waste()`
    # already reports before the click.
    new_hunger = max(creature.hunger, min(item.cap, creature.hunger + item.hunger))
    if creature.stage is Stage.DORMANT:
        creature.exit_dormancy(new_hunger)
    else:
        creature.hunger = new_hunger
    creature.record_feeding(now)
    return True


def purchase(wallet: Wallet, inventory: list[str], item_id: str) -> bool:
    """Buy an ownable item. Charges exactly once, ever.

    Ownership is permanent, so equipping is free: switching between two owned
    hats costs nothing either way, and re-equipping the hat you are already
    wearing costs nothing. Only the first purchase is charged.

    Args:
        wallet:    The player's wallet.
        inventory: The player's owned item ids. Mutated in place on success.
        item_id:   Catalogue id to buy.

    Returns True on success, False (with no side effect whatsoever) if:
      - item_id is not in the catalogue
      - the item is a consumable and so cannot be owned
      - it is already owned
      - the balance is insufficient
    """
    item = catalogue.get(item_id)
    if item is None or not item.is_ownable:
        return False

    if item_id in inventory:
        return False

    if item.currency is Currency.ECHOES:
        ok = wallet.spend_echoes(item.cost)
    else:
        ok = wallet.spend_bits(item.cost)
    if not ok:
        return False

    inventory.append(item_id)
    return True


def equip(creature: Creature, inventory: list[str], item_id: str) -> bool:
    """Wear an already-owned item. Always free.

    Returns False if the item is unknown, not a hat, or not owned.
    """
    item = catalogue.get(item_id)
    if item is None or item.kind is not ItemKind.HAT:
        return False
    if item_id not in inventory:
        return False

    creature.hat_slot = item_id
    return True


def equip_screen(game_state, inventory: list[str], item_id: str | None) -> bool:
    """Fit an owned screen skin to the device, or clear back to the default.

    Free and reversible: once bought, a skin is enabled and disabled on demand.
    Screens are a PLAYER property, not a creature one — the device outlives any
    pet — so this writes GameState, not Creature.

    `item_id=None` reverts to the stock screen.
    """
    if item_id is None:
        game_state.screen_slot = None
        return True

    item = catalogue.get(item_id)
    if item is None or item.kind is not ItemKind.SCREEN:
        return False
    if item_id not in inventory:
        return False

    game_state.screen_slot = item_id
    return True


def equip_shell(game_state, inventory: list[str], item_id: str | None) -> bool:
    """Fit an owned case skin, or clear back to the default. Free either way."""
    if item_id is None:
        game_state.shell_slot = None
        return True
    item = catalogue.get(item_id)
    if item is None or item.kind is not ItemKind.SHELL:
        return False
    if item_id not in inventory:
        return False
    game_state.shell_slot = item_id
    return True


def equip_field(game_state, inventory: list[str], item_id: str | None) -> bool:
    """Fit an owned background field, or clear back to the default (stars). Free either way."""
    if item_id is None:
        game_state.field_slot = None
        return True
    item = catalogue.get(item_id)
    if item is None or item.kind is not ItemKind.FIELD:
        return False
    if item_id not in inventory:
        return False
    game_state.field_slot = item_id
    return True


def unequip(creature: Creature) -> None:
    """Take off whatever is being worn. Always free.

    The counterpart to ``equip()``: ``hat_slot`` must be clearable, not just
    settable.
    """
    creature.hat_slot = None
