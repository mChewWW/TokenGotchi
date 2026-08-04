"""The dynamic rate rules, and the property the whole design exists to have.

The headline test is `test_the_feature_is_not_a_no_op`. The naive reading of
"scale earning and hunger with usage" is provably invisible — if both key off
the same quantity with exponents a and b, slack goes as usage^(1+a-b) and the
obvious a=0,b=1 gives exactly 1. That version would have been a large amount of
machinery producing a game that plays identically at every speed. These tests
pin the properties that make it not that.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tokengotchi.engine import rates  # noqa: E402
from tokengotchi.engine.creature import Creature, Stage  # noqa: E402
from tokengotchi.engine.state_manager import DailyUsage  # noqa: E402

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def _hist(per_day, days=7, end=NOW):
    return [DailyUsage(date=rates.day_key(end - timedelta(days=i)),
                       output_tokens=int(per_day))
            for i in range(days)]


def _settle(history, n=40, last_token_at=NOW):
    """Run the slew to convergence — one call only ever moves 25%."""
    e = d = 1.0
    for _ in range(n):
        r = rates.compute(history, e, d, last_token_at, NOW)
        e, d = r.earn, r.drain
    return r


class TestTheDesignActuallyDoesSomething:

    def test_the_feature_is_not_a_no_op(self):
        """Slack must genuinely differ across usage levels.

        This is the test that would have caught the naive design. Under
        a=0,b=1 every one of these would be identical.
        """
        slack = {}
        for mult in (0.25, 1.0, 4.0):
            r = _settle(_hist(rates.U_REF * mult))
            income = rates.U_REF * mult / (500 / r.earn)
            upkeep = (rates.DRAIN_BASE_PER_6H * 4 * r.drain) / 1.67
            slack[mult] = income / upkeep
        assert slack[0.25] < slack[1.0] < slack[4.0], slack
        assert slack[4.0] / slack[0.25] > 2.0, (
            f"slack barely moves across a 16x usage range: {slack}"
        )

    def test_earning_and_appetite_key_off_different_quantities(self):
        """The real escape from the trap: different time constants.

        Appetite comes from the trailing average, so a single huge day barely
        moves it — while that same day is earning at full rate immediately.
        """
        quiet = _hist(rates.U_REF, days=7)
        spike = list(quiet)
        spike[0] = DailyUsage(date=rates.day_key(NOW),
                              output_tokens=int(rates.U_REF * 20))
        before = _settle(quiet)
        after = rates.compute(spike, before.earn, before.drain, NOW, NOW)
        assert after.drain <= before.drain * rates.SLEW + 1e-9, (
            "one big day should not spike appetite; the window damps it"
        )
        assert rates.pace(spike, NOW) > 2.0, "the same day should read hot"


class TestTheGuardrails:

    def test_earning_never_falls_below_the_published_rate(self):
        """The advertised 500 T/BIT is the worst it ever gets.

        An early version let a light user's rate fall to 833 T/BIT, which
        nobody asked for and which punished a new player for their first week.
        """
        for per_day in (0, 1, 100, 5_000, rates.U_REF // 2):
            r = _settle(_hist(per_day))
            assert r.earn >= rates.EARN_MIN - 1e-9, (per_day, r.earn)

    def test_multipliers_are_clamped_at_both_ends(self):
        hot = _settle(_hist(rates.U_REF * 10_000))
        assert hot.earn <= rates.EARN_MAX + 1e-9
        assert hot.drain <= rates.DRAIN_MAX + 1e-9
        cold = _settle(_hist(1))
        assert cold.drain >= rates.DRAIN_MIN - 1e-9

    def test_the_bar_is_measured_in_session_hours_and_stays_playable(self):
        """The unit is app-open time, so the bar can be brutal on the clock
        and still survivable: closing the window pauses the pet entirely.

        DRAIN_MAX is set by the shortest bar that is still playable — under
        an hour of actual work per feed would be a chore, not a pet.
        """
        assert rates.hours_to_empty(100.0, 1.0) == pytest.approx(3.0, abs=0.05)
        assert rates.hours_to_empty(100.0, rates.DRAIN_MAX) >= 1.25
        assert rates.hours_to_empty(100.0, rates.DRAIN_MIN) <= 10.0

    def test_one_period_cannot_move_a_rate_more_than_the_slew(self):
        r = rates.compute(_hist(rates.U_REF * 500), 1.0, 1.0, NOW, NOW)
        assert r.earn <= 1.0 * rates.SLEW + 1e-9
        assert r.drain <= 1.0 * rates.SLEW + 1e-9

    def test_calibrates_before_it_judges(self):
        """An empty history must not hand a new player floor rates."""
        r = rates.compute([], 1.0, 1.0, None, NOW)
        assert (r.earn, r.drain, r.calibrating) == (1.0, 1.0, True)


class TestRestIsRepresentable:

    def test_two_days_of_silence_drops_appetite_immediately(self):
        """No slew on the mercy path: a rule that takes a day to arrive is
        not mercy."""
        r = rates.compute(_hist(rates.U_REF * 8), 3.0, 3.0,
                          NOW - timedelta(hours=rates.REST_HOURS + 1), NOW)
        assert r.resting is True
        assert r.drain == rates.DRAIN_MIN

    def test_resting_does_not_freeze_the_earn_multiplier(self):
        """Freezing it is a clean exploit: rest a fortnight, come back with a
        2.5x rate against a zero baseline."""
        r = rates.compute(_hist(rates.U_REF * 8), 3.0, 3.0,
                          NOW - timedelta(days=5), NOW)
        assert r.earn < 3.0

    def test_a_normal_weekend_is_not_rest(self):
        r = rates.compute(_hist(rates.U_REF), 1.0, 1.0,
                          NOW - timedelta(hours=40), NOW)
        assert r.resting is False


class TestDecayIsNotRepricedRetroactively:

    def test_appetite_multiplies_the_burn(self):
        c = Creature(stage=Stage.ADULT, hunger=100.0, last_hunger_update=NOW)
        c.apply_time_decay(NOW + timedelta(minutes=30), 1.0)
        one = 100.0 - c.hunger
        c2 = Creature(stage=Stage.ADULT, hunger=100.0, last_hunger_update=NOW)
        c2.apply_time_decay(NOW + timedelta(minutes=30), 2.0)
        assert (100.0 - c2.hunger) == pytest.approx(one * 2, rel=1e-6)

    def test_flushing_at_the_boundary_preserves_the_old_rate(self):
        """Two half-periods at different appetites must cost the sum of both,
        not the whole span at whichever rate happened to be installed last."""
        boundary = NOW + timedelta(minutes=20)
        end = NOW + timedelta(minutes=40)

        flushed = Creature(stage=Stage.ADULT, hunger=100.0,
                           last_hunger_update=NOW)
        flushed.apply_time_decay(boundary, 1.0)      # old rate, then swap
        flushed.apply_time_decay(end, 3.0)

        naive = Creature(stage=Stage.ADULT, hunger=100.0,
                         last_hunger_update=NOW)
        naive.apply_time_decay(end, 3.0)             # swap first: retroactive

        assert flushed.hunger > naive.hunger, (
            "not flushing at the boundary re-prices hunger already burned"
        )


class TestPaceIsHonest:

    def test_pace_is_today_over_the_trailing_average(self):
        h = _hist(1000)
        h[0] = DailyUsage(date=rates.day_key(NOW), output_tokens=2000)
        got = rates.pace(h, NOW)
        assert got == pytest.approx(2000 / ((1000 * 6 + 2000) / 7), rel=1e-6)

    def test_pace_is_unavailable_during_calibration(self):
        assert rates.pace([], NOW) is None

    def test_a_missing_day_counts_as_a_real_zero(self):
        """Someone who works two days a week has a genuinely cheap pet."""
        two = [DailyUsage(date=rates.day_key(NOW - timedelta(days=i)),
                          output_tokens=70_000) for i in (0, 1)]
        base, _ = rates.baseline_tokens_per_day(two, NOW)
        assert base == pytest.approx(140_000 / 7)


class TestPeriodBoundaries:

    def test_slots_are_fixed_not_relative(self):
        a = rates.period_start(NOW)
        b = rates.period_start(NOW + timedelta(minutes=59))
        assert a == b, "two launches in one slot must agree"

    def test_the_next_slot_differs(self):
        a = rates.period_start(NOW)
        b = rates.period_start(NOW + timedelta(hours=rates.PERIOD_HOURS))
        assert b > a
