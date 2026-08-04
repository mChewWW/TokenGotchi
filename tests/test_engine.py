"""Engine unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tokengotchi.engine.creature import (
    Creature,
    Stage,
    HUNGER_MAX,
    HUNGER_DECAY_PER_6H,
    HOURS_PER_DECAY_PERIOD,
    EGG_TO_BABY_BITS,
    DORMANCY_TRIGGER_HOURS,
)
from tokengotchi.engine.wallet import Wallet
from tokengotchi.engine.actions import (
    feed, purchase, equip, unequip, BITS_PER_FEED, HUNGER_PER_BIT,
)
from tokengotchi.engine.state_manager import SCHEMA_VERSION, StateManager, GameState

# Prices live in shop/catalogue.py; read them here so a price change does not
# require touching these tests.
from tokengotchi.shop import catalogue as _cat
HAT_A = _cat.get("hat_a")
HAT_B = _cat.get("hat_b")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc(*args, **kwargs) -> datetime:
    """Shorthand for a UTC datetime."""
    return datetime(*args, **kwargs, tzinfo=timezone.utc)


def creature_at(hunger: float = 100.0, stage: Stage = Stage.BABY) -> Creature:
    """Return a Creature with given hunger/stage and last_hunger_update = epoch."""
    now = utc(2026, 1, 1, 0, 0, 0)
    return Creature(stage=stage, hunger=hunger, last_hunger_update=now)


# ---------------------------------------------------------------------------
# 1. Hunger decay — decay scales with elapsed session time (float tolerance)
# ---------------------------------------------------------------------------

def test_hunger_decay_is_proportional_to_elapsed_time():
    """Decay is proportional to elapsed SESSION time at HUNGER_DECAY_PER_6H.

    The span must be 1h: at this rate a full bar is three hours of app-open
    time, so anything past 3h clamps at zero and asserts nothing about the
    rate. Hunger runs on session time, not the wall clock — the pet pauses
    while the window is shut.
    """
    t0 = utc(2026, 1, 1, 0, 0, 0)
    c = Creature(stage=Stage.BABY, hunger=100.0, last_hunger_update=t0)
    c.apply_time_decay(t0 + timedelta(hours=1))
    expected = 100.0 - (HUNGER_DECAY_PER_6H / HOURS_PER_DECAY_PERIOD)
    assert c.hunger == pytest.approx(expected)


def test_hunger_decay_zero_floor():
    """Hunger never goes below 0."""
    t0 = utc(2026, 1, 1, 0, 0, 0)
    c = Creature(stage=Stage.BABY, hunger=5.0, last_hunger_update=t0)
    t1 = t0 + timedelta(hours=48)
    c.apply_time_decay(t1)
    assert c.hunger == 0.0


def test_hunger_decay_updates_timestamp():
    """last_hunger_update is advanced to `now` after decay."""
    t0 = utc(2026, 1, 1, 0, 0, 0)
    c = Creature(stage=Stage.BABY, hunger=100.0, last_hunger_update=t0)
    t1 = t0 + timedelta(hours=3)
    c.apply_time_decay(t1)
    assert c.last_hunger_update == t1


# ---------------------------------------------------------------------------
# 2. Dormancy trigger — hunger=0, 13 hours elapsed → stage is DORMANT
# ---------------------------------------------------------------------------

def test_dormancy_trigger():
    """Hunger at 0 for 13 hours → creature enters DORMANT."""
    t0 = utc(2026, 1, 1, 0, 0, 0)
    c = Creature(stage=Stage.BABY, hunger=0.0, last_hunger_update=t0)
    # First tick: hunger is already 0, record dormancy_start
    c.apply_time_decay(t0)
    c.check_dormancy(t0)
    assert c.dormancy_start is not None

    # 13 hours later
    t13 = t0 + timedelta(hours=13)
    c.apply_time_decay(t13)
    c.check_dormancy(t13)
    assert c.stage is Stage.DORMANT


def test_dormancy_not_triggered_before_threshold():
    """Starving for just under DORMANCY_TRIGGER_HOURS must NOT go dormant."""
    t0 = utc(2026, 1, 1, 0, 0, 0)
    c = Creature(stage=Stage.BABY, hunger=0.0, last_hunger_update=t0)
    c.check_dormancy(t0)
    t_before = t0 + timedelta(hours=DORMANCY_TRIGGER_HOURS - 1)
    c.apply_time_decay(t_before)
    c.check_dormancy(t_before)
    assert c.stage is Stage.BABY


# ---------------------------------------------------------------------------
# 3. Dormancy recovery — feed while dormant → exits dormancy, hunger restored
# ---------------------------------------------------------------------------

def test_dormancy_recovery_feed():
    """Feeding a dormant creature revives it and restores hunger."""
    t0 = utc(2026, 1, 1, 0, 0, 0)
    c = Creature(stage=Stage.DORMANT, hunger=0.0, last_hunger_update=t0)
    c._pre_dormant_stage = Stage.BABY
    w = Wallet(bits=5, echoes=0)
    result = feed(c, w, bits_to_spend=BITS_PER_FEED)
    assert result is True
    assert c.stage is Stage.BABY
    assert c.hunger == pytest.approx(BITS_PER_FEED * HUNGER_PER_BIT)
    assert c.dormancy_start is None


def test_dormancy_recovery_hunger_capped_at_100():
    """Hunger never exceeds 100, however many BITS are spent."""
    t0 = utc(2026, 1, 1, 0, 0, 0)
    c = Creature(stage=Stage.DORMANT, hunger=0.0, last_hunger_update=t0)
    c._pre_dormant_stage = Stage.ADULT
    w = Wallet(bits=500, echoes=0)
    enough = int(HUNGER_MAX / HUNGER_PER_BIT) + 1
    feed(c, w, bits_to_spend=enough)
    assert c.hunger == pytest.approx(100.0)
    assert c.stage is Stage.ADULT


# ---------------------------------------------------------------------------
# 4. BABY → ADULT: 7 days of feeding log entries → advances stage
# ---------------------------------------------------------------------------

def test_baby_to_adult_advance():
    """7 unique feeding dates → BABY advances to ADULT."""
    c = Creature(stage=Stage.BABY, hunger=80.0)
    dates = [f"2026-01-{d:02d}" for d in range(1, 8)]  # 7 distinct days
    c.daily_feeding_log = dates
    t_now = utc(2026, 1, 8, 12, 0, 0)
    c.check_stage_advance(lifetime_bits_earned=100, now=t_now)
    assert c.stage is Stage.ADULT


def test_baby_to_adult_insufficient_days():
    """Only 6 unique feeding dates → stays BABY."""
    c = Creature(stage=Stage.BABY, hunger=80.0)
    c.daily_feeding_log = [f"2026-01-{d:02d}" for d in range(1, 7)]
    c.check_stage_advance(lifetime_bits_earned=100, now=utc(2026, 1, 7, 12, 0, 0))
    assert c.stage is Stage.BABY


def test_baby_to_adult_deduplicates_same_day():
    """Feeding multiple times on the same day counts as 1 day."""
    c = Creature(stage=Stage.BABY, hunger=80.0)
    # 6 real days + 2 duplicate entries for day 1
    c.daily_feeding_log = ["2026-01-01", "2026-01-01"] + [
        f"2026-01-{d:02d}" for d in range(2, 7)
    ]
    c.check_stage_advance(lifetime_bits_earned=100, now=utc(2026, 1, 7, 12, 0, 0))
    assert c.stage is Stage.BABY  # Only 6 unique days


# ---------------------------------------------------------------------------
# 5. EGG → BABY: lifetime_bits_earned >= 50 → stage advances
# ---------------------------------------------------------------------------

def test_egg_to_baby_advance():
    """lifetime_bits_earned >= 50 → EGG advances to BABY."""
    c = Creature(stage=Stage.EGG, hunger=100.0)
    c.check_stage_advance(lifetime_bits_earned=50, now=utc(2026, 1, 1))
    assert c.stage is Stage.BABY


def test_egg_to_baby_not_advance_below_threshold():
    """Below EGG_TO_BABY_BITS → stays EGG."""
    c = Creature(stage=Stage.EGG, hunger=100.0)
    c.check_stage_advance(lifetime_bits_earned=EGG_TO_BABY_BITS - 1,
                          now=utc(2026, 1, 1))
    assert c.stage is Stage.EGG


# ---------------------------------------------------------------------------
# 6. Feed: insufficient BITS → returns False, hunger unchanged
# ---------------------------------------------------------------------------

def test_feed_insufficient_bits():
    """feed() returns False and leaves hunger unchanged if BITS balance is 0."""
    c = creature_at(hunger=50.0, stage=Stage.BABY)
    w = Wallet(bits=0, echoes=5)
    result = feed(c, w, bits_to_spend=1)
    assert result is False
    assert c.hunger == pytest.approx(50.0)
    assert w.bits == 0


def test_feed_cannot_feed_egg():
    """Cannot feed an EGG regardless of BITS balance."""
    c = Creature(stage=Stage.EGG, hunger=100.0)
    w = Wallet(bits=10, echoes=0)
    result = feed(c, w, bits_to_spend=1)
    assert result is False
    assert w.bits == 10  # unchanged


def test_feed_success_deducts_bits():
    """Successful feed deducts BITS and updates hunger."""
    c = creature_at(hunger=50.0, stage=Stage.BABY)
    w = Wallet(bits=3, echoes=0)
    result = feed(c, w, bits_to_spend=BITS_PER_FEED)
    assert result is True
    assert w.bits == 0
    assert c.hunger == pytest.approx(
        min(HUNGER_MAX, 50.0 + BITS_PER_FEED * HUNGER_PER_BIT))


def test_feed_hunger_capped_at_100():
    """Feed cannot push hunger above 100."""
    c = creature_at(hunger=90.0, stage=Stage.BABY)
    w = Wallet(bits=500, echoes=0)
    feed(c, w, bits_to_spend=int(HUNGER_MAX / HUNGER_PER_BIT) + 1)
    assert c.hunger == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# 7. Dress: equips hat, deducts echo
# ---------------------------------------------------------------------------

def test_purchase_then_equip():
    """Buying charges the catalogue price; wearing it afterwards is free."""
    c = Creature(stage=Stage.BABY, hunger=80.0)
    w = Wallet(bits=0, echoes=HAT_A.cost + 5)
    inv: list[str] = []
    assert purchase(w, inv, "hat_a") is True
    assert w.echoes == 5
    assert equip(c, inv, "hat_a") is True
    assert c.hat_slot == "hat_a"
    assert w.echoes == 5


def test_purchase_hat_b():
    c = Creature(stage=Stage.ADULT, hunger=80.0)
    w = Wallet(bits=0, echoes=HAT_B.cost)
    inv: list[str] = []
    assert purchase(w, inv, "hat_b") is True
    assert equip(c, inv, "hat_b") is True
    assert c.hat_slot == "hat_b"
    assert w.echoes == 0


def test_purchase_insufficient_echoes():
    """Refused with no side effect when short."""
    c = Creature(stage=Stage.BABY, hunger=80.0)
    w = Wallet(bits=10, echoes=0)
    inv: list[str] = []
    assert purchase(w, inv, "hat_a") is False
    assert inv == []
    assert c.hat_slot is None


def test_purchase_invalid_item():
    c = Creature(stage=Stage.BABY, hunger=80.0)
    w = Wallet(bits=0, echoes=50)
    inv: list[str] = []
    assert purchase(w, inv, "hat_z") is False
    assert w.echoes == 50  # unchanged
    assert inv == []


# ---------------------------------------------------------------------------
# 8. State round-trip: save and reload state.json, values match
# ---------------------------------------------------------------------------

def test_state_round_trip(tmp_path: Path):
    """Save a GameState and reload it — all values must survive serialisation."""
    state_file = tmp_path / "state.json"
    mgr = StateManager(state_path=state_file)

    # Build a non-trivial state
    state = mgr.load()  # first launch creates defaults
    state.lifetime_bits_earned = 75
    state.wallet.bits = 42
    state.wallet.echoes = 7
    state.creature.stage = "BABY"
    state.creature.hunger = 66.5
    state.creature.hat_slot = "hat_b"
    state.creature.daily_feeding_log = ["2026-01-01", "2026-01-02"]

    mgr.save(state)

    # Reload
    mgr2 = StateManager(state_path=state_file)
    loaded = mgr2.load()

    assert loaded.lifetime_bits_earned == 75
    assert loaded.wallet.bits == 42
    assert loaded.wallet.echoes == 7
    assert loaded.creature.stage == "BABY"
    assert loaded.creature.hunger == pytest.approx(66.5)
    assert loaded.creature.hat_slot == "hat_b"
    assert loaded.creature.daily_feeding_log == ["2026-01-01", "2026-01-02"]


# ---------------------------------------------------------------------------
# 9. First-launch: state.json created with correct defaults
# ---------------------------------------------------------------------------

def test_first_launch_creates_defaults(tmp_path: Path):
    """On first launch, state.json is created with expected default values."""
    state_file = tmp_path / "state.json"
    assert not state_file.exists()

    mgr = StateManager(state_path=state_file)
    assert mgr.is_first_launch() is True

    state = mgr.load()

    assert state_file.exists()
    assert state.version == SCHEMA_VERSION
    assert state.creature.stage == "EGG"
    assert state.creature.hunger == pytest.approx(100.0)
    assert state.creature.hat_slot is None
    assert state.creature.dormancy_start is None
    assert state.creature.daily_feeding_log == []
    assert state.wallet.bits == 0
    assert state.wallet.echoes == 0
    assert state.lifetime_bits_earned == 0
    assert mgr.is_first_launch() is False  # file now exists


def test_first_launch_creates_directory(tmp_path: Path):
    """StateManager creates the parent directory if it does not exist."""
    state_file = tmp_path / "nested" / "dir" / "state.json"
    mgr = StateManager(state_path=state_file)
    mgr.load()
    assert state_file.exists()


# ---------------------------------------------------------------------------
# 10. Wallet: bits/echoes never go negative
# ---------------------------------------------------------------------------

def test_wallet_bits_never_negative():
    """Spending more BITS than available returns False; balance stays >= 0."""
    w = Wallet(bits=3, echoes=0)
    result = w.spend_bits(5)
    assert result is False
    assert w.bits == 3  # unchanged


def test_wallet_echoes_never_negative():
    """Spending more ECHOES than available returns False; balance stays >= 0."""
    w = Wallet(bits=0, echoes=2)
    result = w.spend_echoes(3)
    assert result is False
    assert w.echoes == 2


def test_wallet_add_bits():
    """add_bits credits correctly."""
    w = Wallet(bits=10, echoes=0)
    w.add_bits(5)
    assert w.bits == 15


def test_wallet_add_echoes():
    """add_echoes credits correctly."""
    w = Wallet(bits=0, echoes=1)
    w.add_echoes(9)
    assert w.echoes == 10


def test_wallet_zero_balance_init():
    """Wallet initialised with negative values is clamped to 0."""
    w = Wallet(bits=-5, echoes=-3)
    assert w.bits == 0
    assert w.echoes == 0


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------

def test_hunger_decay_dormant_no_change():
    """Dormant creatures do not lose additional hunger during time decay."""
    t0 = utc(2026, 1, 1, 0, 0, 0)
    c = Creature(stage=Stage.DORMANT, hunger=0.0, last_hunger_update=t0)
    t24 = t0 + timedelta(hours=24)
    c.apply_time_decay(t24)
    assert c.hunger == 0.0
    assert c.last_hunger_update == t24


def test_feeding_logs_date():
    """Successful feed logs today's ISO date in daily_feeding_log."""
    now = utc(2026, 3, 15, 10, 0, 0)
    c = creature_at(hunger=50.0, stage=Stage.BABY)
    w = Wallet(bits=5, echoes=0)
    feed(c, w, bits_to_spend=BITS_PER_FEED, now=now)
    assert "2026-03-15" in c.daily_feeding_log


def test_feeding_deduplicates_same_day():
    """Feeding twice on the same day does not duplicate the date log entry."""
    now = utc(2026, 3, 15, 10, 0, 0)
    c = creature_at(hunger=10.0, stage=Stage.BABY)
    w = Wallet(bits=50, echoes=0)
    feed(c, w, bits_to_spend=BITS_PER_FEED, now=now)
    feed(c, w, bits_to_spend=BITS_PER_FEED, now=now)
    assert c.daily_feeding_log.count("2026-03-15") == 1


def test_stage_dormant_pauses_advance():
    """DORMANT creature does not advance stages."""
    c = Creature(stage=Stage.DORMANT, hunger=0.0)
    c._pre_dormant_stage = Stage.EGG
    c.check_stage_advance(lifetime_bits_earned=100, now=utc(2026, 1, 1))
    assert c.stage is Stage.DORMANT


def test_state_manager_to_creature_and_back(tmp_path: Path):
    """GameState ↔ Creature domain object conversion is lossless."""
    state_file = tmp_path / "state.json"
    mgr = StateManager(state_path=state_file)
    state = mgr.load()

    # Mutate via domain objects
    creature = state.to_creature()
    wallet = state.to_wallet()
    creature.stage = Stage.BABY
    creature.hunger = 77.7
    creature.hat_slot = "hat_a"
    wallet.add_bits(20)

    state.apply_creature(creature)
    state.apply_wallet(wallet)
    mgr.save(state)

    loaded = StateManager(state_path=state_file).load()
    assert loaded.creature.stage == "BABY"
    assert loaded.creature.hunger == pytest.approx(77.7)
    assert loaded.creature.hat_slot == "hat_a"
    assert loaded.wallet.bits == 20
