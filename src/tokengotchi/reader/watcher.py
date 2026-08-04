"""
watcher.py — StatsWatcher: watches ~/.claude/projects/ for JSONL modifications.

Claude Code appends to session JSONL files after every assistant response.
We watch the entire projects/ directory recursively for any .jsonl modification,
then trigger a full re-scan and delta computation.

Debouncing: rapid successive writes (e.g. sub-agent activity) are collapsed into
a single re-scan using a 1-second quiet period to avoid hammering the filesystem.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from tokengotchi.reader.stats_reader import CurrencyDelta, StatsReader

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 1.0  # wait for writes to settle before re-scanning


class _ProjectsHandler(FileSystemEventHandler):
    """Watchdog handler that fires on any .jsonl modification under projects/."""

    def __init__(
        self,
        reader: StatsReader,
        on_update: Callable[[CurrencyDelta], None],
    ) -> None:
        super().__init__()
        self._reader = reader
        self._on_update = on_update
        self._debounce_timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        if not str(event.src_path).endswith(".jsonl"):
            return
        self._schedule_update()

    def on_created(self, event) -> None:  # type: ignore[override]
        # New session files appear as created events first.
        if event.is_directory:
            return
        if not str(event.src_path).endswith(".jsonl"):
            return
        self._schedule_update()

    def _schedule_update(self) -> None:
        """Debounce: reset the timer on each event, fire once when quiet."""
        with self._lock:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(
                DEBOUNCE_SECONDS, self._handle_update
            )
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _handle_update(self) -> None:
        try:
            snapshot = self._reader.read_snapshot()
        except Exception as exc:
            logger.warning("StatsWatcher: failed to read snapshot: %s", exc)
            return

        if self._reader.baseline is None:
            self._reader.set_baseline(snapshot)

        delta = self._reader.compute_delta(snapshot)

        # Advance the baseline BEFORE crediting.
        #
        # compute_delta() is cumulative-since-baseline, not incremental, so the
        # baseline MUST move on every fire. Do not rely on the `is None` branch
        # above to do it: main.py always constructs StatsReader with a baseline,
        # so that branch never runs here. A pinned baseline re-credits the
        # entire lifetime total on every fire, compounding several times a
        # minute — measured at 137,807 BITS against 724 actually earned.
        #
        # Advancing first means a raising callback drops one increment rather
        # than re-crediting it forever. Losing a few tokens is the correct
        # failure direction; unbounded inflation is not.
        self._reader.set_baseline(snapshot)

        try:
            self._on_update(delta)
        except Exception:
            logger.exception(
                "StatsWatcher: on_update raised; dropped delta bits=%d echoes=%d",
                delta.bits, delta.echoes,
            )


class StatsWatcher:
    """Watches ~/.claude/projects/ for JSONL modifications and emits currency deltas.

    Fires on_update(delta) whenever Claude Code writes a new assistant response,
    giving the game real-time awareness of token earnings mid-session.
    """

    def __init__(
        self,
        reader: StatsReader,
        on_update: Callable[[CurrencyDelta], None],
    ) -> None:
        self._reader = reader
        self._on_update = on_update
        self._observer: Observer | None = None

    def start(self) -> None:
        """Start watching. Idempotent."""
        if self._observer is not None and self._observer.is_alive():
            return

        watch_dir = str(self._reader.projects_dir)
        if not self._reader.projects_dir.exists():
            logger.warning(
                "StatsWatcher: projects dir %s does not exist yet — "
                "watching parent instead",
                watch_dir,
            )
            watch_dir = str(self._reader.stats_path.parent)

        handler = _ProjectsHandler(self._reader, self._on_update)
        observer = Observer()
        observer.schedule(handler, path=watch_dir, recursive=True)
        observer.start()
        self._observer = observer
        logger.info("StatsWatcher: watching %s (recursive)", watch_dir)

    def stop(self) -> None:
        """Stop watching. Safe when already stopped."""
        if self._observer is None:
            return
        if self._observer.is_alive():
            self._observer.stop()
            self._observer.join()
        self._observer = None

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()
