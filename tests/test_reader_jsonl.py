"""StatsReader against its ACTUAL data source: the JSONL transcript logs.

`StatsReader` scans `~/.claude/projects/**/*.jsonl`; stats-cache.json is not a
source of token counts, so any test that feeds the reader a stats-cache fixture
and asserts on tokens is measuring nothing.

This file tests the path that actually earns currency: JSONL discovery,
recursive walk, usage extraction from either nesting, requestId de-duplication,
and resilience to the malformed lines a live log will contain.

Ratios are asserted against the specified values (BITS_RATIO=500,
ECHOES_RATIO=100000), not against whatever the code currently returns.
"""
from __future__ import annotations

import json

import pytest

from tokengotchi.reader.stats_reader import (
    BITS_RATIO,
    ECHOES_RATIO,
    StatsReader,
    TokenSnapshot,
)


def _entry(out=0, read=0, creation=0, rid=None, nested=False):
    usage = {
        "output_tokens": out,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": creation,
    }
    obj: dict = {"message": {"usage": usage}} if nested else {"usage": usage}
    if rid:
        obj["requestId"] = rid
    return json.dumps(obj)


@pytest.fixture
def claude_dir(tmp_path):
    """A ~/.claude lookalike. The reader derives projects/ from stats_path."""
    root = tmp_path / ".claude"
    (root / "projects").mkdir(parents=True)
    return root


def _reader(claude_dir, baseline=None):
    return StatsReader(claude_dir / "stats-cache.json", baseline=baseline)


def _write(claude_dir, relpath: str, *lines: str) -> None:
    p = claude_dir / "projects" / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestDiscovery:
    def test_no_projects_dir_is_zero_not_a_crash(self, tmp_path):
        r = StatsReader(tmp_path / "stats-cache.json")
        snap = r.read_snapshot()
        assert snap.output_tokens == 0
        assert snap.total_cache_tokens == 0

    def test_empty_projects_dir(self, claude_dir):
        assert _reader(claude_dir).read_snapshot().output_tokens == 0

    def test_single_file(self, claude_dir):
        _write(claude_dir, "proj/a.jsonl", _entry(out=500))
        assert _reader(claude_dir).read_snapshot().output_tokens == 500

    def test_walks_recursively(self, claude_dir):
        _write(claude_dir, "one/a.jsonl", _entry(out=100))
        _write(claude_dir, "two/deep/b.jsonl", _entry(out=250))
        _write(claude_dir, "three/c.jsonl", _entry(out=150))
        assert _reader(claude_dir).read_snapshot().output_tokens == 500

    def test_ignores_non_jsonl(self, claude_dir):
        _write(claude_dir, "p/a.jsonl", _entry(out=300))
        (claude_dir / "projects" / "p" / "notes.txt").write_text(
            _entry(out=99999), encoding="utf-8"
        )
        (claude_dir / "projects" / "p" / "x.json").write_text(
            _entry(out=99999), encoding="utf-8"
        )
        assert _reader(claude_dir).read_snapshot().output_tokens == 300


class TestUsageExtraction:
    def test_top_level_usage(self, claude_dir):
        _write(claude_dir, "p/a.jsonl", _entry(out=10, read=20, creation=30))
        s = _reader(claude_dir).read_snapshot()
        assert s.output_tokens == 10
        assert s.total_cache_tokens == 50

    def test_nested_under_message(self, claude_dir):
        _write(claude_dir, "p/a.jsonl", _entry(out=10, read=20, creation=30,
                                               nested=True))
        s = _reader(claude_dir).read_snapshot()
        assert s.output_tokens == 10
        assert s.total_cache_tokens == 50

    def test_cache_total_is_read_plus_creation(self, claude_dir):
        _write(claude_dir, "p/a.jsonl", _entry(read=30000, creation=20000))
        assert _reader(claude_dir).read_snapshot().total_cache_tokens == 50000

    def test_missing_keys_default_to_zero(self, claude_dir):
        _write(claude_dir, "p/a.jsonl", json.dumps({"usage": {}}))
        s = _reader(claude_dir).read_snapshot()
        assert (s.output_tokens, s.total_cache_tokens) == (0, 0)


class TestDeduplication:
    """Sub-agent sessions repeat entries; double-counting would inflate earnings."""

    def test_same_request_id_counted_once(self, claude_dir):
        _write(claude_dir, "p/a.jsonl",
               _entry(out=100, rid="req-1"),
               _entry(out=100, rid="req-1"))
        assert _reader(claude_dir).read_snapshot().output_tokens == 100

    def test_dedup_spans_files(self, claude_dir):
        _write(claude_dir, "p/a.jsonl", _entry(out=100, rid="req-1"))
        _write(claude_dir, "q/b.jsonl", _entry(out=100, rid="req-1"))
        assert _reader(claude_dir).read_snapshot().output_tokens == 100

    def test_distinct_ids_both_count(self, claude_dir):
        _write(claude_dir, "p/a.jsonl",
               _entry(out=100, rid="req-1"),
               _entry(out=100, rid="req-2"))
        assert _reader(claude_dir).read_snapshot().output_tokens == 200

    def test_entries_without_ids_are_not_deduped(self, claude_dir):
        _write(claude_dir, "p/a.jsonl", _entry(out=100), _entry(out=100))
        assert _reader(claude_dir).read_snapshot().output_tokens == 200


class TestMalformedInput:
    """A live log is appended to while being read; it will contain junk."""

    def test_bad_json_line_is_skipped(self, claude_dir):
        _write(claude_dir, "p/a.jsonl",
               _entry(out=100), "{not json at all", _entry(out=50))
        assert _reader(claude_dir).read_snapshot().output_tokens == 150

    def test_truncated_final_line(self, claude_dir):
        p = claude_dir / "projects" / "p"
        p.mkdir(parents=True)
        (p / "a.jsonl").write_text(
            _entry(out=100) + '\n{"usage": {"output_to', encoding="utf-8"
        )
        assert _reader(claude_dir).read_snapshot().output_tokens == 100

    def test_blank_lines(self, claude_dir):
        _write(claude_dir, "p/a.jsonl", _entry(out=100), "", "   ", _entry(out=50))
        assert _reader(claude_dir).read_snapshot().output_tokens == 150

    def test_entries_without_usage(self, claude_dir):
        _write(claude_dir, "p/a.jsonl",
               json.dumps({"type": "user", "text": "hello"}),
               _entry(out=100))
        assert _reader(claude_dir).read_snapshot().output_tokens == 100

    def test_usage_not_a_dict(self, claude_dir):
        _write(claude_dir, "p/a.jsonl",
               json.dumps({"usage": "nonsense"}), _entry(out=100))
        assert _reader(claude_dir).read_snapshot().output_tokens == 100

    def test_unreadable_file_does_not_sink_the_scan(self, claude_dir):
        _write(claude_dir, "p/good.jsonl", _entry(out=100))
        (claude_dir / "projects" / "p" / "bad.jsonl").write_bytes(
            b"\xff\xfe\x00binary\x00garbage"
        )
        assert _reader(claude_dir).read_snapshot().output_tokens == 100


class TestCurrencyConversion:
    """Ratios: 500 output tokens = 1 BITS, 100000 cache tokens = 1 ECHO."""

    ZERO = TokenSnapshot(0, 0, 0)

    def test_ratios_are_what_the_ledger_says(self):
        assert BITS_RATIO == 500
        assert ECHOES_RATIO == 100000

    def test_one_bit(self, claude_dir):
        _write(claude_dir, "p/a.jsonl", _entry(out=BITS_RATIO))
        r = _reader(claude_dir, baseline=self.ZERO)
        assert r.compute_delta(r.read_snapshot()).bits == 1

    def test_ten_bits(self, claude_dir):
        _write(claude_dir, "p/a.jsonl", _entry(out=BITS_RATIO * 10))
        r = _reader(claude_dir, baseline=self.ZERO)
        assert r.compute_delta(r.read_snapshot()).bits == 10

    def test_one_echo(self, claude_dir):
        _write(claude_dir, "p/a.jsonl", _entry(read=ECHOES_RATIO))
        r = _reader(claude_dir, baseline=self.ZERO)
        assert r.compute_delta(r.read_snapshot()).echoes == 1

    def test_floor_never_rounds_up(self, claude_dir):
        """Currency rounding is always floored: partial units never credit."""
        _write(claude_dir, "p/a.jsonl", _entry(out=BITS_RATIO - 1,
                                               read=ECHOES_RATIO - 1))
        r = _reader(claude_dir, baseline=self.ZERO)
        d = r.compute_delta(r.read_snapshot())
        assert d.bits == 0
        assert d.echoes == 0

    def test_partial_progress_is_not_lost_only_uncredited(self, claude_dir):
        _write(claude_dir, "p/a.jsonl", _entry(out=BITS_RATIO * 2 + 499))
        r = _reader(claude_dir, baseline=self.ZERO)
        assert r.compute_delta(r.read_snapshot()).bits == 2

    def test_delta_is_relative_to_baseline(self, claude_dir):
        _write(claude_dir, "p/a.jsonl", _entry(out=BITS_RATIO * 5))
        r = _reader(claude_dir,
                    baseline=TokenSnapshot(BITS_RATIO * 3, 0, 0))
        assert r.compute_delta(r.read_snapshot()).bits == 2

    def test_negative_delta_clamps_to_zero(self, claude_dir):
        """A baseline ahead of current (log rotation) must never refund."""
        _write(claude_dir, "p/a.jsonl", _entry(out=100))
        r = _reader(claude_dir, baseline=TokenSnapshot(999999, 999999, 0))
        d = r.compute_delta(r.read_snapshot())
        assert d.bits == 0
        assert d.echoes == 0
