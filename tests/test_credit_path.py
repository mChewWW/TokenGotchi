"""Two leaks that between them eat ~60% of everything the player earns.

Neither is visible: the balance still goes up, just far less than it should,
and nothing in the app claims a figure you could check it against. They stay
invisible until the earn rate is DISPLAYED, and a displayed rate has to be
true.

Both are pinned here with the real-world shapes that cause them.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tokengotchi.config import BITS_RATIO, ECHOES_RATIO  # noqa: E402
from tokengotchi.reader.stats_reader import (  # noqa: E402
    StatsReader,
    TokenSnapshot,
)


def _write(tmp_path, name, rows):
    # StatsReader derives projects_dir as stats_path.parent/"projects", so the
    # layout matters and the reader takes no directory argument.
    d = tmp_path / "projects" / "p"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("\n".join(json.dumps(r) for r in rows),
                          encoding="utf-8")
    return d


def _usage(rid, out, read=0, creation=0):
    return {"requestId": rid,
            "message": {"usage": {"output_tokens": out,
                                  "cache_read_input_tokens": read,
                                  "cache_creation_input_tokens": creation}}}


class TestStreamingPartialsAreNotUndercounted:
    """Claude Code logs one requestId many times as the response streams.

    `output_tokens` GROWS across those lines. Keeping the first and skipping
    the rest banks 3 tokens for a 2,130-token reply. Measured on a real
    corpus: 1,692,852 of 3,598,945 output tokens, 47%, go uncounted that way.
    """

    def test_largest_usage_per_request_id_wins(self, tmp_path):
        _write(tmp_path, "a.jsonl", [
            _usage("req_1", 3),
            _usage("req_1", 3),
            _usage("req_1", 2130),      # the real answer, arriving last
        ])
        snap = StatsReader(tmp_path / "stats.json").read_snapshot()
        assert snap.output_tokens == 2130, (
            "first-wins dedup — streamed replies are being banked at their "
            "opening partial"
        )

    def test_partials_may_span_files(self, tmp_path):
        """A resumed session continues in a new JSONL, so the running maximum
        cannot be per-file."""
        _write(tmp_path, "a.jsonl", [_usage("req_1", 5)])
        _write(tmp_path, "b.jsonl", [_usage("req_1", 900)])
        snap = StatsReader(tmp_path / "stats.json").read_snapshot()
        assert snap.output_tokens == 900

    def test_distinct_ids_still_sum(self, tmp_path):
        """The dedup must not become a max over everything."""
        _write(tmp_path, "a.jsonl", [_usage("r1", 100), _usage("r2", 250)])
        snap = StatsReader(tmp_path / "stats.json").read_snapshot()
        assert snap.output_tokens == 350

    def test_max_is_per_field(self, tmp_path):
        """A partial can carry final cache figures with a truncated output."""
        _write(tmp_path, "a.jsonl", [
            _usage("r1", 10, read=9000, creation=400),
            _usage("r1", 2000, read=0, creation=0),
        ])
        snap = StatsReader(tmp_path / "stats.json").read_snapshot()
        assert snap.output_tokens == 2000
        assert snap.cache_read_tokens == 9000
        assert snap.cache_creation_tokens == 400

    def test_records_without_an_id_are_not_collapsed(self, tmp_path):
        _write(tmp_path, "a.jsonl", [
            {"message": {"usage": {"output_tokens": 7}}},
            {"message": {"usage": {"output_tokens": 7}}},
        ])
        snap = StatsReader(tmp_path / "stats.json").read_snapshot()
        assert snap.output_tokens == 14


class TestTheRemainderIsNotThrownAway:
    """The delta must expose raw tokens, or the caller cannot bank the change.

    The watcher advances the baseline on every fire, so a remainder that is
    floored away is not credited later — it is gone. On real event timings
    flooring per fire credits zero BITS on 70.9% of fires and evaporates
    27.6% of all BITS.
    """

    def test_delta_reports_raw_tokens(self):
        r = StatsReader(Path("stats.json"))
        r.set_baseline(TokenSnapshot(output_tokens=0, cache_read_tokens=0,
                                     cache_creation_tokens=0))
        d = r.compute_delta(TokenSnapshot(
            output_tokens=BITS_RATIO + 499,
            cache_read_tokens=ECHOES_RATIO + 7, cache_creation_tokens=0))
        assert d.bits == 1
        assert d.raw_output == BITS_RATIO + 499, "the 499 must survive"
        assert d.echoes == 1
        assert d.raw_cache == ECHOES_RATIO + 7

    def test_many_sub_ratio_fires_eventually_pay(self):
        """The shape that loses tokens: lots of small deltas.

        Each is worth zero whole BITS on its own. Floored per fire they pay
        nothing at all; accumulated they are worth exactly what was earned.
        """
        r = StatsReader(Path("stats.json"))
        total = 0
        pending = 0
        credited = 0
        for _ in range(50):
            r.set_baseline(TokenSnapshot(output_tokens=total,
                                         cache_read_tokens=0,
                                         cache_creation_tokens=0))
            total += 100                      # a fifth of a BIT each time
            d = r.compute_delta(TokenSnapshot(output_tokens=total,
                                              cache_read_tokens=0,
                                              cache_creation_tokens=0))
            assert d.bits == 0                # nothing whole, every time
            pending += d.raw_output
            whole = pending // BITS_RATIO
            pending -= whole * BITS_RATIO
            credited += whole
        assert credited == 50 * 100 // BITS_RATIO == 10, (
            "50 fires of 100 tokens is 10 BITS; flooring per fire pays 0"
        )
        assert 0 <= pending < BITS_RATIO

    def test_no_tokens_credits_nothing(self):
        r = StatsReader(Path("stats.json"))
        snap = TokenSnapshot(output_tokens=9999, cache_read_tokens=0,
                             cache_creation_tokens=0)
        r.set_baseline(snap)
        for _ in range(100):
            d = r.compute_delta(snap)
            assert (d.bits, d.echoes, d.raw_output, d.raw_cache) == (0, 0, 0, 0)

    def test_a_shrinking_corpus_credits_nothing(self):
        """Pruned JSONL files make the cumulative counter go DOWN."""
        r = StatsReader(Path("stats.json"))
        r.set_baseline(TokenSnapshot(output_tokens=10_000,
                                     cache_read_tokens=0,
                                     cache_creation_tokens=0))
        d = r.compute_delta(TokenSnapshot(output_tokens=10,
                                          cache_read_tokens=0,
                                          cache_creation_tokens=0))
        assert (d.bits, d.raw_output) == (0, 0)
