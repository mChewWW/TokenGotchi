"""
stats_reader.py — reads token usage from Claude Code's local JSONL session files.

Claude Code writes stats-cache.json only at session end, making it useless for
real-time updates. The session JSONL files under ~/.claude/projects/ are written
after every assistant response and are the authoritative live source.

This module sums usage blocks across all JSONL files, deduplicating by requestId
to avoid double-counting sub-agent sessions.

stats-cache.json is retained as a fallback schema-version sentinel only.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_STATS_CACHE_VERSION = 4

BITS_RATIO = 500       # 1 BITS per 500 output tokens
ECHOES_RATIO = 100000  # 1 ECHO per 100000 (cache_read + cache_creation) tokens


class SchemaVersionError(Exception):
    """Raised when stats-cache.json has an unrecognised schema version."""


@dataclass(frozen=True)
class TokenSnapshot:
    """Immutable snapshot of raw token totals summed across all JSONL sessions."""

    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int

    @property
    def total_cache_tokens(self) -> int:
        return self.cache_read_tokens + self.cache_creation_tokens


@dataclass(frozen=True)
class CurrencyDelta:
    """Computed currency earned since baseline.

    Carries the RAW token delta alongside the whole-unit counts. Flooring
    here and discarding the remainder is the second of two leaks that were
    costing most of the player's earnings: the watcher advances the baseline
    past those tokens on every fire, so anything under one whole unit was
    consumed and paid nothing. Measured on real event timings, 70.9% of fires
    credited zero BITS and 27.6% of all earned BITS evaporated.

    The remainder is now banked by the caller, which is the only place that
    has somewhere durable to put it.
    """

    bits: int
    echoes: int
    raw_output: int = 0
    raw_cache: int = 0


class StatsReader:
    """Reads token usage from ~/.claude/projects/**/*.jsonl and computes currency deltas.

    The projects_dir is watched for JSONL modifications. On each read, all JSONL
    files are scanned and usage blocks summed (deduplicated by requestId).

    stats-cache.json is checked only for schema version compatibility on first
    launch; it is not used for token counts.
    """

    def __init__(
        self,
        stats_path: Path,
        baseline: Optional[TokenSnapshot] = None,
    ) -> None:
        # stats_path is kept for schema-guard compatibility with existing code.
        self._stats_path = stats_path
        self._projects_dir = stats_path.parent / "projects"
        self._baseline = baseline

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read_snapshot(self) -> TokenSnapshot:
        """Scan all JSONL session files and return a live TokenSnapshot.

        Also validates stats-cache.json schema version if the file exists.
        Retries once after 200ms on IOError.
        """
        # Schema guard on stats-cache.json (version check only, not token source)
        if self._stats_path.exists():
            self._check_schema_version()

        try:
            return self._sum_jsonl_tokens()
        except IOError:
            time.sleep(0.2)
            return self._sum_jsonl_tokens()

    def compute_delta(self, current: TokenSnapshot) -> CurrencyDelta:
        """Compute earned currency since baseline (zero delta on first launch)."""
        baseline = self._baseline if self._baseline is not None else current

        raw_bits = current.output_tokens - baseline.output_tokens
        raw_cache = current.total_cache_tokens - baseline.total_cache_tokens

        raw_bits = max(0, raw_bits)
        raw_cache = max(0, raw_cache)
        return CurrencyDelta(
            bits=raw_bits // BITS_RATIO,
            echoes=raw_cache // ECHOES_RATIO,
            raw_output=raw_bits,
            raw_cache=raw_cache,
        )

    @property
    def stats_path(self) -> Path:
        return self._stats_path

    @property
    def projects_dir(self) -> Path:
        return self._projects_dir

    def set_baseline(self, snapshot: TokenSnapshot) -> None:
        self._baseline = snapshot

    @property
    def baseline(self) -> Optional[TokenSnapshot]:
        return self._baseline

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_schema_version(self) -> None:
        """Raise SchemaVersionError if stats-cache.json has an unknown version."""
        try:
            with open(self._stats_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            version = data.get("version")
            if version != SUPPORTED_STATS_CACHE_VERSION:
                raise SchemaVersionError(
                    f"Unrecognised stats-cache version {version} — please update TokenGotchi"
                )
        except SchemaVersionError:
            raise
        except Exception as exc:
            # If we can't read the file, don't block — JSONL is the real source.
            logger.warning("Could not read stats-cache.json for version check: %s", exc)

    def _sum_jsonl_tokens(self) -> TokenSnapshot:
        """Walk all JSONL files under projects_dir and sum usage blocks."""
        if not self._projects_dir.exists():
            return TokenSnapshot(0, 0, 0)

        output_tokens = 0
        cache_read_tokens = 0
        cache_creation_tokens = 0
        # requestId -> the largest usage tuple seen for it, across ALL files.
        # Must be shared across files, not per-file: a resumed session can
        # continue in a new JSONL.
        best: dict[str, tuple[int, int, int]] = {}

        for jsonl_file in self._projects_dir.rglob("*.jsonl"):
            try:
                out, read, creation = self._parse_jsonl(jsonl_file, best)
                output_tokens += out
                cache_read_tokens += read
                cache_creation_tokens += creation
            except Exception as exc:
                logger.debug("Skipping %s: %s", jsonl_file.name, exc)

        for o, r, c in best.values():
            output_tokens += o
            cache_read_tokens += r
            cache_creation_tokens += c

        return TokenSnapshot(
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
        )

    def _parse_jsonl(
        self,
        path: Path,
        best: dict[str, tuple[int, int, int]],
    ) -> tuple[int, int, int]:
        """Parse one JSONL file.

        Returns the totals for records that carry NO request id, and folds the
        rest into `best` as a running per-id maximum. The caller adds `best` in
        once every file has been read.
        """
        out = 0
        read = 0
        creation = 0

        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Deduplicate by requestId to avoid double-counting sub-agent
                # sessions. FIRST-WINS IS WRONG AND WAS COSTING 47% OF EVERY
                # BIT EARNED. Claude Code appends a line for the same requestId
                # repeatedly as a response streams, and `output_tokens` GROWS
                # across them:
                #
                #   req_011CdRz...  out=3      <- first, and all we kept
                #   req_011CdRz...  out=2130   <- the actual answer, discarded
                #
                # Measured on this machine's real corpus: 1,692,852 of
                # 3,598,945 output tokens never counted. Cache figures repeat
                # unchanged across partials, so the loss fell on BITS alone and
                # silently skewed the whole BITS:ECHOES balance.
                #
                # Keep the LARGEST usage seen per id: cumulative counters only
                # grow, so max is the completed figure whichever order the
                # lines arrive in.

                msg = obj.get("message")
                rid = (obj.get("requestId") or obj.get("messageId")
                       or (msg.get("id") if isinstance(msg, dict) else None))

                # usage block can be at top level or under 'message'
                usage = obj.get("usage")
                if not usage and isinstance(msg, dict):
                    usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue

                o = usage.get("output_tokens", 0) or 0
                r = usage.get("cache_read_input_tokens", 0) or 0
                c = usage.get("cache_creation_input_tokens", 0) or 0

                if rid:
                    prev = best.get(rid)
                    if prev is None:
                        best[rid] = (o, r, c)
                    else:
                        # Per field, not per record: a partial can carry the
                        # final cache figures with a truncated output count.
                        best[rid] = (max(prev[0], o), max(prev[1], r),
                                     max(prev[2], c))
                    continue

                out += o
                read += r
                creation += c

        return out, read, creation
