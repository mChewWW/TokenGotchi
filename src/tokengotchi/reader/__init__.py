"""
tokengotchi.reader — token-reading subsystem for TokenGotchi.

Public surface:
    StatsReader     — reads live JSONL session data, computes currency deltas
    StatsWatcher    — watchdog-based file watcher
    TokenSnapshot   — immutable snapshot of raw token totals
    CurrencyDelta   — computed BITS / ECHOES earned since baseline
    SchemaVersionError — raised when schema version is not supported
"""

from tokengotchi.reader.stats_reader import (
    CurrencyDelta,
    SchemaVersionError,
    StatsReader,
    TokenSnapshot,
)
from tokengotchi.reader.watcher import StatsWatcher

__all__ = [
    "StatsReader",
    "StatsWatcher",
    "TokenSnapshot",
    "CurrencyDelta",
    "SchemaVersionError",
]
