"""Creature state machine: Egg → Baby → Adult, hunger decay, dormancy."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum


class Stage(Enum):
    EGG = "EGG"
    BABY = "BABY"
    ADULT = "ADULT"
    DORMANT = "DORMANT"  # overlay state — dormant creature remembers its previous stage


# Hunger constants
HUNGER_MAX: float = 100.0
# Base appetite, before the dynamic multiplier. Hunger accrues only while the
# window is OPEN (main.py re-anchors last_hunger_update on launch), so this is
# session time, not wall-clock time. See engine/rates.py.
HUNGER_DECAY_PER_6H: float = 200.0  # ~3h of SESSION time at 1.0x
HOURS_PER_DECAY_PERIOD: float = 6.0
DORMANCY_TRIGGER_HOURS: float = 6.0  # 6 hours at 0 hunger → DORMANT

# Stage-advance constants
# Kept low deliberately: at BITS_RATIO=500 tokens/bit, this is one short
# Claude Code exchange. A new player should see their egg hatch within
# their first few minutes of real usage, not their first week, or they
# quit before the game ever pays off.
EGG_TO_BABY_BITS: int = 5            # lifetime_bits_earned threshold
BABY_TO_ADULT_DAYS: int = 7         # days with at least one feeding

# The five-stage emotional ladder, poorest to richest. Both sprite rendering
# (renderer/sprites.py) and dialogue-line selection (dialogue/scheduler.py)
# read the bands from `hunger_state()` below so the two can never drift apart.
HUNGER_BANDS: tuple[str, ...] = ("dying", "horror", "distressed", "sad", "healthy")


def hunger_state(hunger: float) -> str:
    """Return the hunger band name for a 0-100 hunger value."""
    if hunger >= 75:
        return "healthy"
    if hunger >= 50:
        return "sad"
    if hunger >= 25:
        return "distressed"
    if hunger >= 10:
        return "horror"
    return "dying"


class Creature:
    """
    Represents the virtual pet creature.

    Stages:
      EGG   → BABY  when lifetime_bits_earned >= EGG_TO_BABY_BITS (5)
      BABY  → ADULT when 7 distinct calendar days have a feeding entry

    DORMANT is an overlay: the creature enters dormancy but can be recovered
    via a successful feed.  The previous stage (EGG/BABY/ADULT) is preserved
    in _pre_dormant_stage so recovery can restore it correctly.
    """

    def __init__(
        self,
        stage: Stage = Stage.EGG,
        hunger: float = HUNGER_MAX,
        dormancy_start: datetime | None = None,
        hat_slot: str | None = None,
        daily_feeding_log: list[str] | None = None,
        last_hunger_update: datetime | None = None,
        pre_dormant_stage: Stage | None = None,
    ) -> None:
        self.stage = stage
        self.hunger = float(hunger)
        self.dormancy_start = dormancy_start
        self.hat_slot = hat_slot
        self.daily_feeding_log: list[str] = daily_feeding_log if daily_feeding_log is not None else []
        self.last_hunger_update: datetime = last_hunger_update or datetime.now(timezone.utc)
        # Tracks which stage the creature was in before going dormant
        self._pre_dormant_stage: Stage | None = pre_dormant_stage

    # ------------------------------------------------------------------
    # Time-driven updates
    # ------------------------------------------------------------------

    def apply_time_decay(self, now: datetime, drain_mult: float = 1.0) -> None:
        """Apply hunger decay proportional to elapsed time since last update.

        `drain_mult` is the pet's current appetite, driven by the trailing
        7-day token average (see engine/rates.py).

        THE CALLER MUST FLUSH BEFORE CHANGING IT. This integrates from
        `last_hunger_update` to `now` at a single rate, so if the multiplier
        changes at a period boundary the decay *before* that boundary has to be
        applied at the OLD rate first. Swapping the multiplier and then
        integrating retroactively re-prices hunger that was already burned —
        the same shape as the baseline bug that once inflated currency 190x.
        """
        if self.stage is Stage.DORMANT:
            # While dormant, hunger is locked at 0; just update timestamp
            self.last_hunger_update = now
            return

        elapsed_seconds = (now - self.last_hunger_update).total_seconds()
        if elapsed_seconds <= 0:
            return

        elapsed_hours = elapsed_seconds / 3600.0
        decay = ((HUNGER_DECAY_PER_6H / HOURS_PER_DECAY_PERIOD)
                 * elapsed_hours * max(0.0, drain_mult))
        self.hunger = max(0.0, self.hunger - decay)
        self.last_hunger_update = now

    def check_dormancy(self, now: datetime) -> None:
        """Enter dormancy if hunger stays at 0 for DORMANCY_TRIGGER_HOURS (6).

        Must be called *after* apply_time_decay so hunger is current.
        """
        if self.stage is Stage.DORMANT:
            return  # already dormant

        if self.hunger <= 0.0:
            if self.dormancy_start is None:
                # First moment hunger hit 0 — record it using last_hunger_update
                # (which was just set by apply_time_decay to `now` when hunger
                # first bottomed out, or was already 0 from a previous tick)
                self.dormancy_start = now
            else:
                elapsed = (now - self.dormancy_start).total_seconds() / 3600.0
                if elapsed >= DORMANCY_TRIGGER_HOURS:
                    self._pre_dormant_stage = self.stage
                    self.stage = Stage.DORMANT
                    self.hunger = 0.0
        else:
            # Hunger recovered without a feed (shouldn't happen normally, but
            # reset the dormancy clock to be safe)
            self.dormancy_start = None

    def check_stage_advance(self, lifetime_bits_earned: int, now: datetime) -> None:
        """Advance EGG → BABY or BABY → ADULT if conditions are met.

        Does not act while the creature is DORMANT (stage advance is paused).
        """
        if self.stage is Stage.DORMANT:
            return

        if self.stage is Stage.EGG:
            if lifetime_bits_earned >= EGG_TO_BABY_BITS:
                self.stage = Stage.BABY

        elif self.stage is Stage.BABY:
            unique_days = len(set(self.daily_feeding_log))
            if unique_days >= BABY_TO_ADULT_DAYS:
                self.stage = Stage.ADULT

    # ------------------------------------------------------------------
    # Feeding helpers (called from actions.py)
    # ------------------------------------------------------------------

    def record_feeding(self, now: datetime) -> None:
        """Log today's date (UTC ISO date string) for the BABY → ADULT check."""
        date_str = now.date().isoformat()
        if date_str not in self.daily_feeding_log:
            self.daily_feeding_log.append(date_str)

    def exit_dormancy(self, new_hunger: float) -> None:
        """Exit dormancy after a successful feed.

        Restores the pre-dormant stage, sets hunger, clears dormancy clock.
        """
        if self.stage is Stage.DORMANT:
            self.stage = self._pre_dormant_stage or Stage.BABY
            self._pre_dormant_stage = None
        self.hunger = new_hunger
        self.dormancy_start = None
