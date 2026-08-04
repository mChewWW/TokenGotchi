"""
test_reader_adversarial.py — Adversarial edge-case tests for StatsReader.

These tests probe failure modes, boundary conditions, and defensive handling
of the reader subsystem against the StatsReader interface.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from tokengotchi.reader.stats_reader import (
    BITS_RATIO,
    ECHOES_RATIO,
    SchemaVersionError,
    StatsReader,
    TokenSnapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_stats(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _make_valid_payload(
    output_tokens: int = 0,
    cache_read: int = 0,
    cache_creation: int = 0,
) -> dict:
    return {
        "version": 4,
        "lastComputedDate": "2026-07-24",
        "modelUsage": {
            "claude-sonnet-4-6": {
                "inputTokens": 0,
                "outputTokens": output_tokens,
                "cacheReadInputTokens": cache_read,
                "cacheCreationInputTokens": cache_creation,
                "costUSD": 0,
            }
        },
        "totalSessions": 1,
        "totalMessages": 10,
    }


def _zero_baseline() -> TokenSnapshot:
    """An explicit zero-token baseline so delta is measured from 0."""
    return TokenSnapshot(
        output_tokens=0,
        cache_read_tokens=0,
        cache_creation_tokens=0,
    )


# ---------------------------------------------------------------------------
# Test: version 999
# ---------------------------------------------------------------------------

class TestVersion999:
    """version field is 999 — must raise SchemaVersionError."""

    def test_version_999(self, tmp_path: Path) -> None:
        payload = _make_valid_payload(output_tokens=100)
        payload["version"] = 999
        stats_file = tmp_path / "stats-cache.json"
        _write_stats(stats_file, json.dumps(payload))
        reader = StatsReader(stats_path=stats_file)

        with pytest.raises(SchemaVersionError):
            reader.read_snapshot()


# ---------------------------------------------------------------------------
# Test: version missing
# ---------------------------------------------------------------------------

class TestVersionMissing:
    """No version field at all — treated as unknown, SchemaVersionError raised."""

    def test_version_missing(self, tmp_path: Path) -> None:
        payload = _make_valid_payload(output_tokens=100)
        del payload["version"]
        stats_file = tmp_path / "stats-cache.json"
        _write_stats(stats_file, json.dumps(payload))
        reader = StatsReader(stats_path=stats_file)

        # version=None is not SUPPORTED_VERSION=4 → SchemaVersionError.
        with pytest.raises(SchemaVersionError):
            reader.read_snapshot()


# ---------------------------------------------------------------------------
# Test: modelUsage missing
# ---------------------------------------------------------------------------

class TestModelUsageMissing:
    """Valid JSON but no modelUsage key — returns 0 tokens, no crash."""

    def test_model_usage_missing(self, tmp_path: Path) -> None:
        payload = {
            "version": 4,
            "lastComputedDate": "2026-07-24",
            "totalSessions": 1,
            "totalMessages": 5,
            # modelUsage deliberately absent
        }
        stats_file = tmp_path / "stats-cache.json"
        _write_stats(stats_file, json.dumps(payload))
        reader = StatsReader(stats_path=stats_file)

        snapshot = reader.read_snapshot()

        assert snapshot.output_tokens == 0
        assert snapshot.cache_read_tokens == 0
        assert snapshot.cache_creation_tokens == 0
        assert snapshot.total_cache_tokens == 0


# ---------------------------------------------------------------------------
# Test: negative tokens (defensive handling)
# ---------------------------------------------------------------------------

class TestNegativeTokens:
    """Token counts are negative — currency delta must be clamped to 0."""

    def test_negative_tokens_delta_is_zero(self, tmp_path: Path) -> None:
        """Even with negative token values in snapshot, delta never goes negative."""
        # Put a positive baseline so that current < baseline → clamped to 0.
        baseline = TokenSnapshot(
            output_tokens=500,
            cache_read_tokens=10000,
            cache_creation_tokens=5000,
        )
        payload = _make_valid_payload(output_tokens=100, cache_read=1000, cache_creation=0)
        stats_file = tmp_path / "stats-cache.json"
        _write_stats(stats_file, json.dumps(payload))
        reader = StatsReader(stats_path=stats_file, baseline=baseline)

        snapshot = reader.read_snapshot()
        delta = reader.compute_delta(snapshot)

        assert delta.bits == 0
        assert delta.echoes == 0

    def test_negative_raw_delta_clamped(self) -> None:
        """compute_delta clamps negatives regardless of how snapshot was produced."""
        baseline = TokenSnapshot(output_tokens=1000, cache_read_tokens=50000, cache_creation_tokens=0)
        current = TokenSnapshot(output_tokens=10, cache_read_tokens=100, cache_creation_tokens=0)

        reader = StatsReader(stats_path=Path("/dev/null"), baseline=baseline)
        delta = reader.compute_delta(current)

        assert delta.bits == 0
        assert delta.echoes == 0


# ---------------------------------------------------------------------------
# Test: partial model keys (missing outputTokens)
# ---------------------------------------------------------------------------

class TestPartialModelKeys:
    """A model entry is missing outputTokens — must default to 0, no KeyError."""

    def test_all_keys_missing(self, tmp_path: Path) -> None:
        """Model entry exists but has no recognised keys at all."""
        payload = {
            "version": 4,
            "lastComputedDate": "2026-07-24",
            "modelUsage": {
                "claude-unknown": {}
            },
            "totalSessions": 1,
            "totalMessages": 1,
        }
        stats_file = tmp_path / "stats-cache.json"
        _write_stats(stats_file, json.dumps(payload))
        reader = StatsReader(stats_path=stats_file)

        snapshot = reader.read_snapshot()
        assert snapshot.output_tokens == 0
        assert snapshot.total_cache_tokens == 0


# ---------------------------------------------------------------------------
# Test: zero tokens
# ---------------------------------------------------------------------------

class TestZeroTokens:
    """All token counts are 0 — 0 BITS, 0 ECHOES, no division errors."""

    def test_zero_tokens(self, tmp_path: Path) -> None:
        payload = _make_valid_payload(output_tokens=0, cache_read=0, cache_creation=0)
        stats_file = tmp_path / "stats-cache.json"
        _write_stats(stats_file, json.dumps(payload))
        reader = StatsReader(stats_path=stats_file, baseline=_zero_baseline())

        snapshot = reader.read_snapshot()
        assert snapshot.output_tokens == 0

        delta = reader.compute_delta(snapshot)
        assert delta.bits == 0
        assert delta.echoes == 0

    def test_zero_tokens_with_zero_baseline_no_division_error(self, tmp_path: Path) -> None:
        """Baseline is also zero — no division errors anywhere."""
        baseline = TokenSnapshot(output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0)
        payload = _make_valid_payload()
        stats_file = tmp_path / "stats-cache.json"
        _write_stats(stats_file, json.dumps(payload))
        reader = StatsReader(stats_path=stats_file, baseline=baseline)

        snapshot = reader.read_snapshot()
        delta = reader.compute_delta(snapshot)
        assert delta.bits == 0
        assert delta.echoes == 0


# ---------------------------------------------------------------------------
# Test: v4 fixture round-trip
# ---------------------------------------------------------------------------

class TestV4FixtureRoundTrip:
    """Fixture-driven reader behaviour: schema guard, empty models, first-launch delta.

    The v4 fixtures encode the conversion reference: 500 outputTokens → 10 BITS,
    50000 cache tokens → 10 ECHOES.
    """

    def test_bad_version_fixture_raises(self) -> None:
        """The version=999 fixture must raise SchemaVersionError."""
        fixture_path = (
            Path(__file__).parent / "fixtures" / "stats_cache_bad_version.json"
        )
        reader = StatsReader(stats_path=fixture_path)
        with pytest.raises(SchemaVersionError):
            reader.read_snapshot()

    def test_empty_models_fixture_returns_zeros(self) -> None:
        """The empty-models fixture returns a zero snapshot."""
        fixture_path = (
            Path(__file__).parent / "fixtures" / "stats_cache_empty_models.json"
        )
        reader = StatsReader(stats_path=fixture_path)
        snapshot = reader.read_snapshot()
        assert snapshot.output_tokens == 0
        assert snapshot.total_cache_tokens == 0


    def test_no_baseline_yields_zero_delta(self) -> None:
        """When baseline=None, compute_delta uses snapshot as own baseline → 0 delta.

        This is the defined first-launch behaviour: historical tokens don't
        retroactively grant currency.
        """
        fixture_path = (
            Path(__file__).parent / "fixtures" / "stats_cache_v4_known.json"
        )
        # No baseline provided → first-launch mode.
        reader = StatsReader(stats_path=fixture_path)
        snapshot = reader.read_snapshot()

        delta = reader.compute_delta(snapshot)
        assert delta.bits == 0
        assert delta.echoes == 0


# ---------------------------------------------------------------------------
# SCOPE
#
# This file deliberately holds no token-counting assertions. StatsReader counts
# tokens by scanning ~/.claude/projects/**/*.jsonl; stats-cache.json is not a
# token-count source, so feeding it `stats_cache_*.json` fixtures and asserting
# on totals would only ever assert against zeros.
#
# Bits/echoes conversion, aggregation, floor rounding, and corrupt or missing
# input are all exercised against the real path in tests/test_reader_jsonl.py.
#
# What belongs here: the stats-cache schema guard, which does still read that
# file, and StatsWatcher lifecycle.
# ---------------------------------------------------------------------------
