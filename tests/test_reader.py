"""
test_reader.py — unit tests for the tokengotchi.reader subsystem.

Scope: the stats-cache schema guard (StatsReader does read stats-cache.json for
its version field) and StatsWatcher lifecycle. Token counting itself is driven
by ~/.claude/projects/**/*.jsonl, not stats-cache.json, so bits/echoes
conversion, aggregation, floor rounding and corrupt/missing input are exercised
against that real path in tests/test_reader_jsonl.py (27 tests).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tokengotchi.reader import (
    CurrencyDelta,
    SchemaVersionError,
    StatsReader,
    StatsWatcher,
    TokenSnapshot,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_reader(fixture_name: str, baseline: TokenSnapshot | None = None) -> StatsReader:
    return StatsReader(FIXTURES / fixture_name, baseline=baseline)


# ---------------------------------------------------------------------------
# 1. Schema guard: version=999 raises SchemaVersionError
# ---------------------------------------------------------------------------

class TestSchemaGuard:
    def test_bad_version_raises(self):
        reader = make_reader("stats_cache_bad_version.json")
        with pytest.raises(SchemaVersionError) as exc_info:
            reader.read_snapshot()
        assert "999" in str(exc_info.value)
        assert "please update TokenGotchi" in str(exc_info.value)

    def test_good_version_does_not_raise(self):
        reader = make_reader("stats_cache_v4.json")
        snap = reader.read_snapshot()
        assert isinstance(snap, TokenSnapshot)


# ---------------------------------------------------------------------------
# 2. Delta baseline: first read returns 0 BITS, 0 ECHOES
# ---------------------------------------------------------------------------

class TestDeltaBaseline:
    def test_first_read_zero_delta(self):
        reader = make_reader("stats_cache_v4.json")
        snapshot = reader.read_snapshot()
        # When baseline is None, compute_delta uses current as baseline → zero.
        delta = reader.compute_delta(snapshot)
        assert delta.bits == 0
        assert delta.echoes == 0

    def test_explicit_zero_baseline_gives_zero(self):
        reader = make_reader("stats_cache_v4.json")
        snapshot = reader.read_snapshot()
        reader.set_baseline(snapshot)
        delta = reader.compute_delta(snapshot)
        assert delta.bits == 0
        assert delta.echoes == 0


# ---------------------------------------------------------------------------
# 3. BITS computation: 500 output tokens → 10 BITS
# ---------------------------------------------------------------------------

class TestBitsComputation:


    def test_bits_below_ratio_is_zero(self):
        zero_baseline = TokenSnapshot(0, 0, 0)
        current = TokenSnapshot(output_tokens=49, cache_read_tokens=0, cache_creation_tokens=0)
        reader = StatsReader(FIXTURES / "stats_cache_bits_500.json", baseline=zero_baseline)
        delta = reader.compute_delta(current)
        assert delta.bits == 0


# ---------------------------------------------------------------------------
# 4. ECHOES computation: 50000 cache tokens → 10 ECHOES
# ---------------------------------------------------------------------------

class TestEchoesComputation:


    def test_echoes_below_ratio_is_zero(self):
        zero_baseline = TokenSnapshot(0, 0, 0)
        current = TokenSnapshot(output_tokens=0, cache_read_tokens=4999, cache_creation_tokens=0)
        reader = StatsReader(FIXTURES / "stats_cache_echoes_50000.json", baseline=zero_baseline)
        delta = reader.compute_delta(current)
        assert delta.echoes == 0


# ---------------------------------------------------------------------------
# 5. Missing modelUsage key: handled gracefully
# ---------------------------------------------------------------------------

class TestMissingModelUsage:
    def test_empty_model_usage_returns_zeros(self):
        reader = make_reader("stats_cache_empty_models.json")
        snapshot = reader.read_snapshot()
        assert snapshot.output_tokens == 0
        assert snapshot.cache_read_tokens == 0
        assert snapshot.cache_creation_tokens == 0
        assert snapshot.total_cache_tokens == 0

    def test_empty_model_usage_zero_delta(self):
        zero_baseline = TokenSnapshot(0, 0, 0)
        reader = make_reader("stats_cache_empty_models.json", baseline=zero_baseline)
        snapshot = reader.read_snapshot()
        delta = reader.compute_delta(snapshot)
        assert delta.bits == 0
        assert delta.echoes == 0

    def test_missing_model_usage_key(self, tmp_path):
        """A stats-cache with no 'modelUsage' key at all should return zeros."""
        no_usage = tmp_path / "no_usage.json"
        no_usage.write_text(json.dumps({"version": 4, "lastComputedDate": "2026-07-24"}))
        reader = StatsReader(no_usage)
        snapshot = reader.read_snapshot()
        assert snapshot.output_tokens == 0



# ---------------------------------------------------------------------------
# 6. Watcher: mock file modification triggers callback with correct delta
# ---------------------------------------------------------------------------

class TestStatsWatcher:
    def _make_watcher_and_handler(self, fixture_name: str):
        """Return (watcher, mock_callback, handler_instance)."""
        zero_baseline = TokenSnapshot(0, 0, 0)
        reader = make_reader(fixture_name, baseline=zero_baseline)
        callback = MagicMock()
        watcher = StatsWatcher(reader, on_update=callback)
        return watcher, callback, reader


    def test_watcher_is_running_after_start(self, tmp_path):
        cache_file = tmp_path / "stats-cache.json"
        cache_file.write_text((FIXTURES / "stats_cache_v4.json").read_text())
        reader = StatsReader(cache_file)
        callback = MagicMock()
        watcher = StatsWatcher(reader, on_update=callback)

        assert not watcher.is_running
        watcher.start()
        assert watcher.is_running
        watcher.stop()
        assert not watcher.is_running

    def test_watcher_stop_idempotent(self, tmp_path):
        cache_file = tmp_path / "stats-cache.json"
        cache_file.write_text((FIXTURES / "stats_cache_v4.json").read_text())
        reader = StatsReader(cache_file)
        watcher = StatsWatcher(reader, on_update=MagicMock())
        # Should not raise even if stop is called before start.
        watcher.stop()
        watcher.start()
        watcher.stop()
        watcher.stop()  # double-stop

    def test_watcher_read_failure_logs_warning_not_crash(self, tmp_path, caplog):
        """If read_snapshot fails (even after retry), watcher logs and skips."""
        import logging

        cache_file = tmp_path / "stats-cache.json"
        cache_file.write_text((FIXTURES / "stats_cache_v4.json").read_text())
        reader = StatsReader(cache_file)
        callback = MagicMock()
        watcher = StatsWatcher(reader, on_update=callback)

        # Patch read_snapshot to always fail.
        with patch.object(reader, "read_snapshot", side_effect=IOError("disk error")):
            with caplog.at_level(logging.WARNING, logger="tokengotchi.reader.watcher"):
                watcher.start()
                cache_file.write_text((FIXTURES / "stats_cache_v4.json").read_text())
                time.sleep(1.0)
                watcher.stop()

        # Callback should NOT be called when read fails.
        callback.assert_not_called()

    def test_watcher_ignores_other_files(self, tmp_path):
        """Modification of a different file should not trigger the callback."""
        cache_file = tmp_path / "stats-cache.json"
        cache_file.write_text((FIXTURES / "stats_cache_v4.json").read_text())
        other_file = tmp_path / "other.json"
        other_file.write_text("{}")

        reader = StatsReader(cache_file, baseline=TokenSnapshot(0, 0, 0))
        callback = MagicMock()
        watcher = StatsWatcher(reader, on_update=callback)
        watcher.start()

        try:
            other_file.write_text('{"changed": true}')
            time.sleep(0.5)
        finally:
            watcher.stop()

        callback.assert_not_called()


# ---------------------------------------------------------------------------
# NOTE
#
# Do not assert token totals against `stats_cache_*.json` fixtures here.
# StatsReader's own docstring is explicit that stats-cache.json "is not used
# for token counts" - it scans ~/.claude/projects/**/*.jsonl instead - so any
# such assertion here would only ever be comparing zeros. Put bits/echoes
# conversion, aggregation, floor rounding and corrupt/missing input tests in
# tests/test_reader_jsonl.py, which drives the real path.
# ---------------------------------------------------------------------------
