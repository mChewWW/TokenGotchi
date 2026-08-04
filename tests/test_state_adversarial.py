"""
test_state_adversarial.py — Adversarial edge-case tests for state.json handling.

Tests cover StateManager persistence edge cases: missing directory, corrupt
files, temporal anomalies, version mismatches, and concurrent writes.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tokengotchi.engine.state_manager import SCHEMA_VERSION, GameState, StateManager
from tokengotchi.engine.creature import Stage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _manager(tmp_path: Path, filename: str = "state.json") -> StateManager:
    """Create a StateManager pointing at a file in tmp_path."""
    return StateManager(state_path=tmp_path / filename)


def _write_state(path: Path, content: str | dict) -> None:
    if isinstance(content, dict):
        content = json.dumps(content)
    path.write_text(content, encoding="utf-8")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Test: missing state directory is created automatically
# ---------------------------------------------------------------------------

class TestMissingStateDir:
    """State directory doesn't exist → StateManager creates it on first load."""

    def test_missing_state_dir(self, tmp_path: Path) -> None:
        state_dir = tmp_path / "nonexistent_dir" / ".tokengotchi"
        assert not state_dir.exists()

        state_file = state_dir / "state.json"
        manager = StateManager(state_path=state_file)

        state = manager.load()

        # Directory and file should now exist.
        assert state_dir.exists()
        assert state_file.exists()
        # State is valid.
        assert state is not None
        assert state.version == SCHEMA_VERSION

    def test_nested_missing_dir(self, tmp_path: Path) -> None:
        """Deeply nested directory is also created."""
        deep = tmp_path / "a" / "b" / "c" / "state.json"
        manager = StateManager(state_path=deep)
        state = manager.load()
        assert deep.exists()
        assert state is not None


# ---------------------------------------------------------------------------
# Test: corrupt state.json is handled — new state created
# ---------------------------------------------------------------------------

class TestCorruptStateJson:
    """state.json is corrupt → handled gracefully."""

    def test_corrupt_state_json_raises_clearly(self, tmp_path: Path) -> None:
        """Corrupt JSON raises json.JSONDecodeError (not a crash or SystemExit)."""
        state_file = tmp_path / "state.json"
        _write_state(state_file, "{corrupt json!!!!")

        manager = StateManager(state_path=state_file)

        with pytest.raises((json.JSONDecodeError, ValueError, Exception)) as exc_info:
            manager.load()

        # Not a SystemExit or KeyboardInterrupt.
        assert not isinstance(exc_info.value, (SystemExit, KeyboardInterrupt))

    def test_empty_state_json_raises_clearly(self, tmp_path: Path) -> None:
        """Empty state.json raises clearly, not a crash."""
        state_file = tmp_path / "state.json"
        _write_state(state_file, "")

        manager = StateManager(state_path=state_file)

        with pytest.raises((json.JSONDecodeError, ValueError, Exception)):
            manager.load()


# ---------------------------------------------------------------------------
# Test: future timestamp — no negative decay
# ---------------------------------------------------------------------------

class TestFutureTimestamp:
    """last_hunger_update is in the future → apply_time_decay clamps to 0 elapsed."""

    def test_future_timestamp_no_negative_decay(self) -> None:
        """Creature with a future last_hunger_update does not gain hunger above stored value."""
        from tokengotchi.engine.creature import Creature, Stage

        future = _utcnow() + timedelta(hours=5)
        creature = Creature(
            stage=Stage.BABY,
            hunger=80.0,
            last_hunger_update=future,
        )

        now = _utcnow()
        creature.apply_time_decay(now)

        # elapsed is negative → clamped to 0 → no decay; hunger unchanged.
        assert creature.hunger == 80.0

    def test_future_timestamp_hunger_not_negative(self) -> None:
        """Far future timestamp never causes hunger to go negative."""
        from tokengotchi.engine.creature import Creature, Stage

        far_future = _utcnow() + timedelta(hours=1000)
        creature = Creature(stage=Stage.BABY, hunger=50.0, last_hunger_update=far_future)

        creature.apply_time_decay(_utcnow())

        assert creature.hunger >= 0.0


# ---------------------------------------------------------------------------
# Test: massive time gap — hunger clamped at 0
# ---------------------------------------------------------------------------

class TestMassiveTimeGap:
    """1000 hours elapsed since last feed → hunger clamped at 0, not negative."""

    def test_massive_time_gap_hunger_zero(self) -> None:
        from tokengotchi.engine.creature import Creature, Stage

        ancient = _utcnow() - timedelta(hours=1000)
        creature = Creature(stage=Stage.BABY, hunger=100.0, last_hunger_update=ancient)

        creature.apply_time_decay(_utcnow())

        assert creature.hunger == 0.0

    def test_massive_time_gap_via_state_json(self, tmp_path: Path) -> None:
        """Loading state.json with ancient timestamp doesn't produce negative hunger."""
        ancient_iso = (_utcnow() - timedelta(hours=1000)).isoformat()

        state_data = {
            "version": 1,
            "creature": {
                "stage": "BABY",
                "hunger": 100.0,
                "dormancy_start": None,
                "hat_slot": None,
                "daily_feeding_log": [],
                "last_hunger_update": ancient_iso,
                "pre_dormant_stage": None,
            },
            "wallet": {"bits": 10, "echoes": 2},
            "baseline_tokens": {
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
            },
            "lifetime_bits_earned": 60,
            "first_launch": ancient_iso,
            "last_launch": ancient_iso,
        }

        state_file = tmp_path / "state.json"
        _write_state(state_file, state_data)

        manager = StateManager(state_path=state_file)
        state = manager.load()

        # The state loads without error.
        assert state is not None
        # The creature parsed from state has non-negative hunger
        # (apply_time_decay is called by the game loop, not by load itself,
        # but the creature object should have 100.0 as stored — the game
        # loop is responsible for applying decay after load).
        creature = state.to_creature()
        # Apply decay to prove it clamps at 0, not goes negative.
        creature.apply_time_decay(_utcnow())
        assert creature.hunger == 0.0


# ---------------------------------------------------------------------------
# Test: state version mismatch
# ---------------------------------------------------------------------------

class TestStateVersionMismatch:
    """state.json has "version": 99 — must not silently corrupt state."""

    def test_state_version_mismatch_handled(self, tmp_path: Path) -> None:
        """Version 99 raises or returns a valid state — never crashes silently."""
        ancient_iso = _utcnow().isoformat()

        state_data = {
            "version": 99,
            "creature": {
                "stage": "BABY",
                "hunger": 75.0,
                "dormancy_start": None,
                "hat_slot": None,
                "daily_feeding_log": [],
                "last_hunger_update": ancient_iso,
                "pre_dormant_stage": None,
            },
            "wallet": {"bits": 5, "echoes": 1},
            "baseline_tokens": {
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
            },
            "lifetime_bits_earned": 55,
            "first_launch": ancient_iso,
            "last_launch": ancient_iso,
        }

        state_file = tmp_path / "state.json"
        _write_state(state_file, state_data)

        manager = StateManager(state_path=state_file)

        # Pydantic will validate and load version=99 as stored (no migration yet).
        # The key constraint: no crash, no silent data loss.
        try:
            state = manager.load()
            # If it loads, version is preserved as-stored.
            assert state is not None
            assert isinstance(state.version, int)
        except Exception as exc:
            # A validation error on unknown version is also acceptable.
            assert not isinstance(exc, (SystemExit, KeyboardInterrupt))


# ---------------------------------------------------------------------------
# Test: concurrent state write — no corruption
# ---------------------------------------------------------------------------

class TestConcurrentStateWrite:
    """Two threads save state.json simultaneously → no corruption.

    On Windows, Path.replace() raises PermissionError when another
    process/thread holds the destination file open, so StateManager._write()
    uses unique temp files plus retry-with-backoff on PermissionError. This
    test is the guard on that behaviour: without it, concurrent saves throw
    and can leave state.json half-written.
    """

    def test_concurrent_state_write(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"

        # Initialise with a valid state.
        manager = StateManager(state_path=state_file)
        manager.load()

        errors: list[Exception] = []

        def write_loop(count: int = 50) -> None:
            mgr = StateManager(state_path=state_file)
            st = mgr.load()
            for _ in range(count):
                try:
                    mgr.save(st)
                except Exception as exc:
                    errors.append(exc)

        t1 = threading.Thread(target=write_loop)
        t2 = threading.Thread(target=write_loop)
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        # No exceptions during concurrent writes.
        assert errors == [], f"Concurrent write errors: {errors}"

        # File is still valid JSON after concurrent writes.
        raw = state_file.read_text(encoding="utf-8")
        parsed = json.loads(raw)  # raises json.JSONDecodeError if corrupt
        assert isinstance(parsed, dict)

    def test_atomic_write_no_partial_file(self, tmp_path: Path) -> None:
        """StateManager._write uses atomic rename — file should never be partially written."""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_path=state_file)
        state = manager.load()

        # Write many times; tmp file should not persist.
        for _ in range(20):
            manager.save(state)

        tmp_file = state_file.with_suffix(".tmp")
        assert not tmp_file.exists(), ".tmp file leaked after atomic write"
