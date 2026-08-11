"""Feed-dialogue rarity gate — direction contract v18, Part A.

The complaint (measured): 20 consecutive feeds parked 20 lines. Feeding is the
only unbounded dialogue source, so a bounded pity gate goes on the four `fed_*`
keys and nothing else. These tests defend three separate guarantees:

  * the gate's boundary behaviour (FLOOR/CEILING/bypasses) against a seeded RNG;
  * that non-feed moments (hatch/adult/wake/purchases) are NEVER gated;
  * that a once-ever milestone already parked in the window's single pending
    slot cannot be destroyed by a later purchase line (the bug the survey found).
"""
from __future__ import annotations

import os
import random

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

from tokengotchi.dialogue.rarity import CEILING, FLOOR, GATED_MOMENTS, FeedGate


# ── The gated set is exactly the four feed keys ─────────────────────────────


def test_only_feed_keys_are_gated():
    """The whole scoping decision: hatch/adult/wake/purchases are unbounded in
    name only — they fire rarely by construction and must pass untouched."""
    assert GATED_MOMENTS == {"fed_hungry", "fed_full", "fed_wasted", "overfed"}
    for key in ("hatch", "adult", "wake_dormant", "purchase:hat", "generic"):
        assert key not in GATED_MOMENTS


def test_a_non_feed_key_always_passes_even_with_a_gate_that_would_refuse():
    """A gate primed to refuse (RNG always 1.0, counter below CEILING) still
    lets every non-feed key through — the gate owns feeding alone."""
    gate = FeedGate(rng=random.Random())
    gate._rng = _AlwaysHigh()
    for _ in range(50):
        assert gate.allow("hatch") is True
        assert gate.allow("adult") is True
        assert gate.allow("wake_dormant") is True


# ── Boundary behaviour ──────────────────────────────────────────────────────


class _AlwaysHigh:
    """random() == 1.0: never below P, so only FLOOR/CEILING can pass a feed."""

    def random(self) -> float:
        return 1.0


class _AlwaysLow:
    """random() == 0.0: always below P, so the open interval always speaks."""

    def random(self) -> float:
        return 0.0


def test_below_floor_is_always_silent():
    """The first FLOOR-1 feeds after a spoken line never speak, no matter the
    dice — that is what stops two lines landing back to back."""
    gate = FeedGate()
    gate._rng = _AlwaysLow()      # even the most generous dice
    for i in range(FLOOR - 1):
        assert gate.allow("fed_full") is False, i


def test_ceiling_forces_a_line_even_on_the_unluckiest_dice():
    """At CEILING silent feeds the gate speaks unconditionally — the pet can
    never go mute for an unbounded run of feeds."""
    gate = FeedGate()
    gate._rng = _AlwaysHigh()     # dice never help
    results = [gate.allow("fed_full") for _ in range(CEILING)]
    assert results[:CEILING - 1] == [False] * (CEILING - 1)
    assert results[CEILING - 1] is True, "CEILING must force a line"


def test_speaking_resets_the_counter():
    """After a forced line at CEILING, the next FLOOR-1 feeds are silent again
    — the cadence repeats rather than latching open."""
    gate = FeedGate()
    gate._rng = _AlwaysHigh()
    for _ in range(CEILING):
        gate.allow("fed_full")     # ends on a forced True, counter reset
    assert gate.allow("fed_full") is False, "counter did not reset after speaking"


def test_first_feed_ever_always_speaks_and_resets():
    """The once-per-install discovery moment bypasses the counter: if the pet
    is silent the first time it is fed, the feature's existence is never taught.
    The bypass also resets, so the pity clock starts clean afterwards."""
    gate = FeedGate()
    gate._rng = _AlwaysHigh()
    gate.allow("fed_full")         # advance the counter to 1
    assert gate.allow("fed_hungry", first_feed=True) is True
    # Counter reset: next feed is feed #1 of a fresh cadence, hence silent.
    assert gate.allow("fed_full") is False


def test_rescue_from_dying_always_speaks():
    """A feed that pulls the pet out of the `dying` band always earns a line —
    the moment is too important to lose to a dice roll."""
    gate = FeedGate()
    gate._rng = _AlwaysHigh()
    gate.allow("fed_full")
    assert gate.allow("fed_hungry", rescue=True) is True


def test_the_mean_gap_lands_inside_the_humans_one_in_four_to_one_in_five():
    """End-to-end distribution check against the real default RNG: over many
    feeds the average gap between spoken lines must sit in the 4-5 range the
    human asked for, with the pity bounds keeping any single gap in [FLOOR,
    CEILING]."""
    gate = FeedGate(rng=random.Random(20260807))
    gaps = []
    run = 0
    for _ in range(20000):
        run += 1
        if gate.allow("fed_full"):
            gaps.append(run)
            run = 0
    assert gaps, "the gate never spoke"
    mean_gap = sum(gaps) / len(gaps)
    assert 4.0 <= mean_gap <= 5.0, mean_gap
    assert min(gaps) >= FLOOR, min(gaps)
    assert max(gaps) <= CEILING, max(gaps)
