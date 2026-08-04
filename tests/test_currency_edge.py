"""
test_currency_edge.py — Currency computation edge cases.

Tests cover BITS/ECHOES floor rounding, clamp behaviour, and Wallet spend logic.
"""

from __future__ import annotations

import pytest

from tokengotchi.reader.stats_reader import (
    BITS_RATIO,
    ECHOES_RATIO,
    CurrencyDelta,
    StatsReader,
    TokenSnapshot,
)
from tokengotchi.engine.wallet import Wallet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _delta(
    output: int = 0,
    cache_read: int = 0,
    cache_creation: int = 0,
    baseline_output: int = 0,
    baseline_cache_read: int = 0,
    baseline_cache_creation: int = 0,
) -> CurrencyDelta:
    """Compute currency delta using StatsReader.compute_delta with explicit baselines."""
    baseline = TokenSnapshot(
        output_tokens=baseline_output,
        cache_read_tokens=baseline_cache_read,
        cache_creation_tokens=baseline_cache_creation,
    )
    current = TokenSnapshot(
        output_tokens=output,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
    )
    # StatsReader.compute_delta is a pure computation — we can call it with any
    # stats_path since we're not reading from disk here.
    from pathlib import Path
    reader = StatsReader(stats_path=Path("/dev/null"), baseline=baseline)
    return reader.compute_delta(current)


# ---------------------------------------------------------------------------
# BITS floor rounding
# ---------------------------------------------------------------------------

class TestBitsFloorRounding:
    """Below the ratio → 0 BITS (floor division, not rounding)."""

    def test_bits_floor_rounding(self) -> None:
        result = _delta(output=49)
        assert result.bits == 0

    def test_bits_floor_rounding_at_ratio_minus_one(self) -> None:
        """BITS_RATIO - 1 tokens → still 0 BITS."""
        result = _delta(output=BITS_RATIO - 1)
        assert result.bits == 0

    def test_bits_floor_rounding_large(self) -> None:
        """One token short of 3x the ratio → 2 BITS, never 3."""
        result = _delta(output=BITS_RATIO * 3 - 1)
        assert result.bits == 2

    def test_bits_floor_never_rounds_up(self) -> None:
        """One token short of 2x the ratio → 1 BITS, never 2."""
        result = _delta(output=BITS_RATIO * 2 - 1)
        assert result.bits == 1


# ---------------------------------------------------------------------------
# BITS exact boundary
# ---------------------------------------------------------------------------

class TestBitsExact:
    """Exactly the ratio → exactly 1 BITS."""

    def test_bits_exact(self) -> None:
        result = _delta(output=BITS_RATIO)
        assert result.bits == 1

    def test_bits_exact_multiple(self) -> None:
        """Ten times the ratio → exactly 10 BITS."""
        result = _delta(output=BITS_RATIO * 10)
        assert result.bits == 10

    def test_bits_with_baseline(self) -> None:
        """Only tokens above the baseline count."""
        result = _delta(output=BITS_RATIO * 3, baseline_output=BITS_RATIO * 2)
        assert result.bits == 1

    def test_bits_zero_above_baseline(self) -> None:
        """current == baseline → 0 BITS."""
        result = _delta(output=200, baseline_output=200)
        assert result.bits == 0


# ---------------------------------------------------------------------------
# ECHOES floor rounding
# ---------------------------------------------------------------------------

class TestEchoesFloorRounding:
    """Below the ratio → 0 ECHOES."""

    def test_echoes_floor_rounding(self) -> None:
        result = _delta(cache_read=4999)
        assert result.echoes == 0

    def test_echoes_floor_rounding_at_ratio_minus_one(self) -> None:
        result = _delta(cache_read=ECHOES_RATIO - 1)
        assert result.echoes == 0

    def test_echoes_split_across_read_and_creation(self) -> None:
        """Summed, then floored: one short of the ratio is still 0."""
        result = _delta(cache_read=2500, cache_creation=2499)
        assert result.echoes == 0

    def test_echoes_floor_never_rounds_up(self) -> None:
        """One token short of 2x the ratio → 1 ECHO, never 2."""
        result = _delta(cache_read=ECHOES_RATIO * 2 - 1)
        assert result.echoes == 1


# ---------------------------------------------------------------------------
# ECHOES exact boundary
# ---------------------------------------------------------------------------

class TestEchoesExact:
    """Exactly the ratio → exactly 1 ECHO."""

    def test_echoes_exact_read_only(self) -> None:
        result = _delta(cache_read=ECHOES_RATIO)
        assert result.echoes == 1

    def test_echoes_exact_creation_only(self) -> None:
        result = _delta(cache_creation=ECHOES_RATIO)
        assert result.echoes == 1

    def test_echoes_exact_split(self) -> None:
        """Read and creation are summed before conversion."""
        half = ECHOES_RATIO // 2
        result = _delta(cache_read=half, cache_creation=ECHOES_RATIO - half)
        assert result.echoes == 1

    def test_echoes_exact_multiple(self) -> None:
        """Ten times the ratio → exactly 10 ECHOES."""
        result = _delta(cache_read=ECHOES_RATIO * 10)
        assert result.echoes == 10

    def test_echoes_with_baseline(self) -> None:
        """Only cache tokens above the baseline count."""
        result = _delta(cache_read=ECHOES_RATIO * 3,
                        baseline_cache_read=ECHOES_RATIO * 2)
        assert result.echoes == 1


# ---------------------------------------------------------------------------
# Delta never negative (current < baseline)
# ---------------------------------------------------------------------------

class TestDeltaNeverNegative:
    """If current < baseline (shouldn't happen but test defensive handling) → 0 currency."""

    def test_bits_never_negative(self) -> None:
        result = _delta(output=100, baseline_output=500)
        assert result.bits == 0

    def test_echoes_never_negative(self) -> None:
        result = _delta(cache_read=1000, baseline_cache_read=50000)
        assert result.echoes == 0

    def test_both_never_negative_simultaneously(self) -> None:
        result = _delta(
            output=50,
            cache_read=2000,
            baseline_output=9999,
            baseline_cache_read=99999,
        )
        assert result.bits == 0
        assert result.echoes == 0


# ---------------------------------------------------------------------------
# Wallet: spend BITS to zero
# ---------------------------------------------------------------------------

class TestSpendBitsToZero:
    """Spend all bits → balance is 0, not negative."""

    def test_spend_bits_to_zero(self) -> None:
        wallet = Wallet(bits=10, echoes=5)
        success = wallet.spend_bits(10)
        assert success is True
        assert wallet.bits == 0

    def test_balance_exactly_zero_not_negative(self) -> None:
        wallet = Wallet(bits=1, echoes=0)
        wallet.spend_bits(1)
        assert wallet.bits == 0
        assert wallet.bits >= 0


# ---------------------------------------------------------------------------
# Wallet: spend more BITS than available
# ---------------------------------------------------------------------------

class TestSpendMoreBitsThanHave:
    """Try to spend 10 BITS with balance of 3 → returns False, balance unchanged."""

    def test_spend_more_bits_than_have(self) -> None:
        wallet = Wallet(bits=3, echoes=0)
        success = wallet.spend_bits(10)
        assert success is False
        assert wallet.bits == 3  # balance unchanged

    def test_spend_zero_bits_always_succeeds(self) -> None:
        """Spending 0 BITS always succeeds without changing balance."""
        wallet = Wallet(bits=3, echoes=0)
        success = wallet.spend_bits(0)
        assert success is True
        assert wallet.bits == 3

    def test_spend_bits_exactly_available(self) -> None:
        """Spending exactly the available balance succeeds."""
        wallet = Wallet(bits=5, echoes=0)
        success = wallet.spend_bits(5)
        assert success is True
        assert wallet.bits == 0

    def test_spend_one_more_than_available(self) -> None:
        """Spending balance+1 returns False."""
        wallet = Wallet(bits=5, echoes=0)
        success = wallet.spend_bits(6)
        assert success is False
        assert wallet.bits == 5

    def test_spend_echoes_more_than_have(self) -> None:
        """Same clamp logic for ECHOES."""
        wallet = Wallet(bits=0, echoes=2)
        success = wallet.spend_echoes(10)
        assert success is False
        assert wallet.echoes == 2

    def test_spend_echoes_to_zero(self) -> None:
        wallet = Wallet(bits=0, echoes=5)
        success = wallet.spend_echoes(5)
        assert success is True
        assert wallet.echoes == 0
        assert wallet.echoes >= 0

    def test_wallet_negative_init_clamped(self) -> None:
        """Wallet constructed with negative values is clamped to 0."""
        wallet = Wallet(bits=-100, echoes=-50)
        assert wallet.bits == 0
        assert wallet.echoes == 0

    def test_add_bits_then_spend(self) -> None:
        """add_bits then spend_bits round-trip is consistent."""
        wallet = Wallet(bits=0, echoes=0)
        wallet.add_bits(5)
        assert wallet.bits == 5
        wallet.spend_bits(3)
        assert wallet.bits == 2

    def test_add_negative_bits_raises(self) -> None:
        """add_bits with a negative value raises ValueError."""
        wallet = Wallet(bits=10, echoes=0)
        with pytest.raises(ValueError):
            wallet.add_bits(-1)

    def test_spend_negative_bits_raises(self) -> None:
        """spend_bits with a negative value raises ValueError."""
        wallet = Wallet(bits=10, echoes=0)
        with pytest.raises(ValueError):
            wallet.spend_bits(-1)
