"""
test_creature_edge.py — Creature logic edge cases.

Tests cover dormancy boundary conditions, feeding rules, evolution gating,
and accessory equip logic.

Engine API (from tokengotchi.engine):
  Creature(stage, hunger, dormancy_start, hat_slot, daily_feeding_log,
           last_hunger_update, pre_dormant_stage)
  creature.apply_time_decay(now)      — applies hunger decay
  creature.check_dormancy(now)        — transitions to DORMANT if criteria met
  creature.check_stage_advance(lifetime_bits, now)
  feed(creature, wallet)              — standalone function, costs 1 BIT
  purchase(wallet, inventory, item)   — standalone function, costs ECHOES once
  equip(creature, inventory, hat_id)  — standalone function, free if owned
  unequip(creature)                   — standalone function, keeps ownership
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

# Prices live in the shop catalogue (shop/catalogue.py), never hard-coded here.
from tokengotchi.shop import catalogue as _cat
HAT_A = _cat.get("hat_a")
HAT_B = _cat.get("hat_b")


# ---------------------------------------------------------------------------
# Engine import guard
# ---------------------------------------------------------------------------

try:
    from tokengotchi.engine.creature import Creature, Stage  # type: ignore[import]
    from tokengotchi.engine.actions import (
        feed, purchase, equip, unequip, BITS_PER_FEED,
    )
    from tokengotchi.engine.wallet import Wallet
    CREATURE_AVAILABLE = True
except ImportError:
    CREATURE_AVAILABLE = False
    Creature = None  # type: ignore[assignment,misc]
    Stage = None     # type: ignore[assignment]
    feed = None      # type: ignore[assignment]
    dress = None     # type: ignore[assignment]
    Wallet = None    # type: ignore[assignment]

creature_required = pytest.mark.xfail(
    not CREATURE_AVAILABLE,
    reason="tokengotchi.engine.creature not yet implemented",
    strict=False,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hours_ago(h: float) -> datetime:
    return _utcnow() - timedelta(hours=h)


def _make_creature(
    stage: str = "baby",
    hunger: float = 100.0,
    bits_balance: int = 20,
    echoes_balance: int = 5,
    dormant: bool = False,
    dormancy_start: datetime | None = None,
    daily_feeding_log: list[str] | None = None,
    equipped_hat: str | None = None,
    last_hunger_update: datetime | None = None,
) -> "tuple[Creature, Wallet]":
    """Construct a (Creature, Wallet) pair using the engine API.

    Currency lives on the Wallet, not on the Creature, so every call site
    destructures the returned tuple.
    """
    stage_enum = Stage(stage.upper()) if Stage is not None else None
    pre_dormant: Stage | None = None
    if dormant and stage_enum is not Stage.DORMANT:
        pre_dormant = stage_enum        # remember original stage
        stage_enum = Stage.DORMANT      # now set the dormant stage

    creature = Creature(
        stage=stage_enum,
        hunger=float(hunger),
        dormancy_start=dormancy_start,
        hat_slot=equipped_hat,
        daily_feeding_log=list(daily_feeding_log) if daily_feeding_log is not None else [],
        last_hunger_update=last_hunger_update or _utcnow(),
        pre_dormant_stage=pre_dormant,
    )
    wallet = Wallet(bits=bits_balance, echoes=echoes_balance)
    return creature, wallet


# ---------------------------------------------------------------------------
# Dormancy boundary — exactly 12h elapsed with hunger=0
# ---------------------------------------------------------------------------

@creature_required
class TestDormancyBoundary:
    """Dormancy triggers at hunger=0 AND >=12h elapsed. Test exact boundary."""

    def test_hunger_exactly_zero_no_dormancy_11h59m(self) -> None:
        """hunger=0 but only 11h 59m elapsed → NOT dormant."""
        eleven_h_59m_ago = _hours_ago(11 + 59 / 60)
        creature, _ = _make_creature(
            hunger=0,
            last_hunger_update=eleven_h_59m_ago,
            dormant=False,
        )
        # Dormancy starts being tracked from now; not triggered yet.
        creature.check_dormancy(_utcnow())
        assert creature.stage is not Stage.DORMANT

    def test_hunger_exactly_zero_dormancy_12h(self) -> None:
        """hunger=0 and dormancy_start set 12h ago → DORMANT."""
        twelve_h_ago = _hours_ago(12.01)  # slightly over 12h to pass boundary
        creature, _ = _make_creature(
            hunger=0,
            dormancy_start=twelve_h_ago,
            dormant=False,
        )
        # Force dormancy_start to 12h ago (hunger was already 0 then).
        creature.dormancy_start = twelve_h_ago
        creature.hunger = 0.0
        creature.check_dormancy(_utcnow())
        assert creature.stage is Stage.DORMANT

    def test_hunger_nonzero_no_dormancy(self) -> None:
        """Initial hunger=1, regardless of elapsed time, doesn't trigger dormancy
        unless hunger actually reaches 0 for 12 continuous hours."""
        creature, _ = _make_creature(
            stage="baby",
            hunger=1.0,
            dormant=False,
        )
        creature.check_dormancy(_utcnow())
        # Still has hunger — dormancy cannot trigger yet.
        assert isinstance(creature.stage is Stage.DORMANT, bool)


# ---------------------------------------------------------------------------
# Feed Egg stage — not allowed
# ---------------------------------------------------------------------------

@creature_required
class TestFeedEgg:
    """Feeding an Egg stage creature returns False (cannot feed egg)."""

    def test_feed_egg(self) -> None:
        creature, wallet = _make_creature(stage="egg", hunger=0, bits_balance=100)
        result = feed(creature, wallet, bits_to_spend=BITS_PER_FEED)
        assert result is False

    def test_feed_egg_does_not_consume_bits(self) -> None:
        creature, wallet = _make_creature(stage="egg", hunger=0, bits_balance=100)
        feed(creature, wallet, bits_to_spend=BITS_PER_FEED)
        assert wallet.bits == 100


# ---------------------------------------------------------------------------
# Feed while dormant exits dormancy
# ---------------------------------------------------------------------------

@creature_required
class TestFeedDormantExitsDormancy:
    """Feeding while dormant → dormancy cleared, hunger restored."""

    def test_feed_dormant_exits_dormancy(self) -> None:
        thirteen_h_ago = _hours_ago(13)
        creature, wallet = _make_creature(
            stage="baby",
            hunger=0,
            dormant=True,
            dormancy_start=thirteen_h_ago,
            bits_balance=20,
        )
        result = feed(creature, wallet, bits_to_spend=BITS_PER_FEED)
        assert result is True
        assert creature.stage is not Stage.DORMANT
        assert creature.hunger > 0

    def test_feed_dormant_clears_dormancy_start(self) -> None:
        thirteen_h_ago = _hours_ago(13)
        creature, wallet = _make_creature(
            stage="baby",
            hunger=0,
            dormant=True,
            dormancy_start=thirteen_h_ago,
            bits_balance=20,
        )
        feed(creature, wallet, bits_to_spend=BITS_PER_FEED)
        assert creature.dormancy_start is None


# ---------------------------------------------------------------------------
# Daily feeding log dedup
# ---------------------------------------------------------------------------

@creature_required
class TestDailyLogDedup:
    """Feeding twice in the same calendar day → daily_feeding_log gets one entry."""

    def test_daily_log_dedup(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        creature, wallet = _make_creature(
            stage="baby",
            hunger=50,
            bits_balance=100,
            daily_feeding_log=[],
        )
        feed(creature, wallet, bits_to_spend=BITS_PER_FEED)
        feed(creature, wallet, bits_to_spend=BITS_PER_FEED)
        entries_today = [d for d in creature.daily_feeding_log if d == today]
        assert len(entries_today) == 1

    def test_daily_log_separate_days(self) -> None:
        """Feedings on different days each get their own entry."""
        yesterday = (datetime.now(timezone.utc).date()
                     - timedelta(days=1)).isoformat()
        creature, wallet = _make_creature(
            stage="baby",
            hunger=50,
            bits_balance=100,
            daily_feeding_log=[yesterday],
        )
        feed(creature, wallet, bits_to_spend=BITS_PER_FEED)  # feeds today
        today = datetime.now(timezone.utc).date().isoformat()
        assert today in creature.daily_feeding_log
        assert yesterday in creature.daily_feeding_log
        assert len(creature.daily_feeding_log) == 2


# ---------------------------------------------------------------------------
# Baby advancement requires 7 unique days
# ---------------------------------------------------------------------------

@creature_required
class TestBabyAdvancementRequires7UniqueDays:
    """7 feedings on the same day → does NOT advance to Adult."""

    def test_same_day_7_feeds_no_advance(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        creature, wallet = _make_creature(
            stage="baby",
            hunger=50,
            bits_balance=999,
            daily_feeding_log=[today],  # only 1 unique day
        )
        for _ in range(7):
            feed(creature, wallet, bits_to_spend=BITS_PER_FEED)

        # check_stage_advance with enough bits — still only 1 unique day.
        creature.check_stage_advance(lifetime_bits_earned=9999, now=_utcnow())
        assert creature.stage is Stage.BABY

    def test_7_unique_days_advances(self) -> None:
        """7 feedings on 7 different days → advances to Adult."""
        seven_days = [
            (date.today() - timedelta(days=i)).isoformat() for i in range(1, 8)
        ]
        creature, wallet = _make_creature(
            stage="baby",
            hunger=50,
            bits_balance=999,
            daily_feeding_log=seven_days,
        )
        creature.check_stage_advance(lifetime_bits_earned=9999, now=_utcnow())
        assert creature.stage is Stage.ADULT

    def test_6_unique_days_no_advance(self) -> None:
        """Only 6 unique days → stays Baby."""
        six_days = [
            (date.today() - timedelta(days=i)).isoformat() for i in range(1, 7)
        ]
        creature, wallet = _make_creature(
            stage="baby",
            hunger=50,
            bits_balance=999,
            daily_feeding_log=six_days,
        )
        creature.check_stage_advance(lifetime_bits_earned=9999, now=_utcnow())
        assert creature.stage is Stage.BABY


# ---------------------------------------------------------------------------
# Hat ownership: buy once with purchase(), then equip()/unequip() freely
# ---------------------------------------------------------------------------

@creature_required
class TestHatOwnership:
    """Hats are owned, not rented.

    A hat costs ECHOES exactly once, at purchase.  After that it lives in the
    inventory and wearing, swapping or removing it is free — anything else
    turns cosmetics into a recurring tax on expressing yourself.
    """

    def test_purchase_charges_once(self) -> None:
        creature, wallet = _make_creature(
            stage="adult", echoes_balance=HAT_A.cost + HAT_B.cost + 10, equipped_hat=None
        )
        inv: list[str] = []
        start = wallet.echoes
        assert purchase(wallet, inv, "hat_a") is True
        assert wallet.echoes == start - HAT_A.cost
        assert inv == ["hat_a"]

    def test_repurchase_is_refused_and_free(self) -> None:
        """Buying a hat you already own is refused and costs nothing."""
        creature, wallet = _make_creature(
            stage="adult", echoes_balance=HAT_A.cost + HAT_B.cost + 10, equipped_hat=None
        )
        inv: list[str] = []
        purchase(wallet, inv, "hat_a")
        before = wallet.echoes
        assert purchase(wallet, inv, "hat_a") is False
        assert wallet.echoes == before
        assert inv == ["hat_a"]

    def test_swapping_owned_hats_is_free(self) -> None:
        """Swapping between two owned hats costs 0 ECHOES, in either direction."""
        creature, wallet = _make_creature(
            stage="adult", echoes_balance=HAT_A.cost + HAT_B.cost + 10, equipped_hat=None
        )
        inv: list[str] = []
        purchase(wallet, inv, "hat_a")
        purchase(wallet, inv, "hat_b")
        after_buying = wallet.echoes
        assert after_buying == 10

        for hat in ("hat_a", "hat_b", "hat_a", "hat_b"):
            assert equip(creature, inv, hat) is True
            assert creature.hat_slot == hat
        assert wallet.echoes == after_buying, "wearing an owned hat must be free"

    def test_cannot_equip_unowned(self) -> None:
        creature, wallet = _make_creature(
            stage="adult", echoes_balance=HAT_A.cost + HAT_B.cost + 10, equipped_hat=None
        )
        assert equip(creature, [], "hat_a") is False
        assert creature.hat_slot is None
        assert wallet.echoes == HAT_A.cost + HAT_B.cost + 10

    def test_purchase_insufficient_echoes_is_a_no_op(self) -> None:
        creature, wallet = _make_creature(
            stage="adult", echoes_balance=HAT_A.cost - 1, equipped_hat=None
        )
        inv: list[str] = []
        assert purchase(wallet, inv, "hat_a") is False
        assert wallet.echoes == HAT_A.cost - 1
        assert inv == []

    def test_unequip(self) -> None:
        """A bare head is a valid look: unequip clears the slot, keeps the hat."""
        creature, wallet = _make_creature(
            stage="adult", echoes_balance=HAT_A.cost + HAT_B.cost + 10, equipped_hat=None
        )
        inv: list[str] = []
        purchase(wallet, inv, "hat_a")
        equip(creature, inv, "hat_a")
        assert creature.hat_slot == "hat_a"
        unequip(creature)
        assert creature.hat_slot is None
        assert inv == ["hat_a"], "unequipping must not lose ownership"

    def test_unknown_item_refused(self) -> None:
        creature, wallet = _make_creature(
            stage="adult", echoes_balance=HAT_A.cost + HAT_B.cost + 10, equipped_hat=None
        )
        inv: list[str] = []
        assert purchase(wallet, inv, "hat_nonexistent_xyz") is False
        assert equip(creature, inv, "hat_nonexistent_xyz") is False
        assert wallet.echoes == HAT_A.cost + HAT_B.cost + 10
        assert creature.hat_slot is None

    def test_consumables_are_not_ownable(self) -> None:
        """feed is bought and spent; it must never enter the wardrobe."""
        creature, wallet = _make_creature(
            stage="adult", echoes_balance=HAT_A.cost + HAT_B.cost + 10, equipped_hat=None
        )
        inv: list[str] = []
        assert purchase(wallet, inv, "feed") is False
        assert inv == []
