"""Ledger correctness: currency inflation and the v1 -> v2 reset migration.

StatsReader.compute_delta() is cumulative-since-baseline, so the watcher must
advance that baseline on every fire. If it does not, the `is None` guard in
_handle_update never fires (main.py always supplies a baseline) and each
watcher fire re-credits the entire lifetime total — roughly 190x inflation on
a long-lived stats file.
"""
from __future__ import annotations

import json

import pytest

from tokengotchi.engine.state_manager import (
    SCHEMA_VERSION,
    GameState,
    StateManager,
)
from tokengotchi.reader.stats_reader import StatsReader, TokenSnapshot
from tokengotchi.reader.watcher import _ProjectsHandler


class _FakeReader:
    """Stands in for StatsReader: fixed snapshot sequence, real baseline logic."""

    def __init__(self, snapshots):
        self._snaps = list(snapshots)
        self._i = 0
        self.baseline: TokenSnapshot | None = None

    def read_snapshot(self) -> TokenSnapshot:
        snap = self._snaps[min(self._i, len(self._snaps) - 1)]
        self._i += 1
        return snap

    def set_baseline(self, snapshot: TokenSnapshot) -> None:
        self.baseline = snapshot

    def compute_delta(self, current: TokenSnapshot):
        return StatsReader.compute_delta(self, current)  # type: ignore[arg-type]

    @property
    def _baseline(self):
        return self.baseline


def _snap(out: int, cache: int) -> TokenSnapshot:
    return TokenSnapshot(
        output_tokens=out, cache_read_tokens=cache, cache_creation_tokens=0
    )


def _fire(handler) -> None:
    handler._handle_update()


class TestBaselineAdvances:
    """The core invariant: repeated fires must not re-credit the same tokens."""

    def test_repeated_fires_on_static_tokens_credit_once(self):
        # 5000 output tokens = 10 BITS at BITS_RATIO=500. Nothing changes after.
        reader = _FakeReader([_snap(5000, 0)] * 6)
        reader.set_baseline(_snap(0, 0))
        credited = []
        h = _ProjectsHandler(reader, lambda d: credited.append(d))  # type: ignore[arg-type]

        for _ in range(6):
            _fire(h)

        total_bits = sum(d.bits for d in credited)
        assert total_bits == 10, (
            f"expected one credit of 10 BITS, got {total_bits} across "
            f"{len(credited)} fires — the baseline is not advancing"
        )

    def test_incremental_growth_credits_each_increment_once(self):
        reader = _FakeReader([_snap(500, 0), _snap(1000, 0), _snap(1500, 0)])
        reader.set_baseline(_snap(0, 0))
        credited = []
        h = _ProjectsHandler(reader, lambda d: credited.append(d))  # type: ignore[arg-type]

        for _ in range(3):
            _fire(h)

        assert [d.bits for d in credited] == [1, 1, 1]
        assert sum(d.bits for d in credited) == 3

    def test_baseline_moves_to_latest_snapshot(self):
        reader = _FakeReader([_snap(9999, 12345)])
        reader.set_baseline(_snap(0, 0))
        h = _ProjectsHandler(reader, lambda d: None)  # type: ignore[arg-type]
        _fire(h)
        assert reader.baseline.output_tokens == 9999
        assert reader.baseline.cache_read_tokens == 12345

    def test_inflation_regression_is_bounded(self):
        """Worst case: 50 fires on a static file must still credit once."""
        reader = _FakeReader([_snap(100_000, 0)] * 50)
        reader.set_baseline(_snap(0, 0))
        total = 0
        h = _ProjectsHandler(reader, lambda d: None)  # type: ignore[arg-type]

        def collect(d):
            nonlocal total
            total += d.bits

        h = _ProjectsHandler(reader, collect)  # type: ignore[arg-type]
        for _ in range(50):
            _fire(h)

        assert total == 200, f"200 BITS earned once; got {total} (={total / 200:.0f}x)"

    def test_callback_raising_does_not_recredit_forever(self):
        """A raising callback drops one increment; it must not re-credit."""
        reader = _FakeReader([_snap(5000, 0)] * 3)
        reader.set_baseline(_snap(0, 0))
        seen = []

        def boom(d):
            seen.append(d.bits)
            raise RuntimeError("callback failed")

        h = _ProjectsHandler(reader, boom)  # type: ignore[arg-type]
        for _ in range(3):
            _fire(h)  # must not propagate

        assert seen == [10, 0, 0], f"expected the delta to be dropped once, got {seen}"


class TestCurrencyResetMigration:
    """v1 -> v2 wipes the inflated balance exactly once, preserving progression."""

    def _write_v1(self, path, **over):
        base = json.loads(GameState().model_dump_json())
        base["version"] = 1
        base["wallet"] = {"bits": 137807, "echoes": 155242}
        base["lifetime_bits_earned"] = 137886
        base["creature"]["stage"] = "BABY"
        base["creature"]["daily_feeding_log"] = ["2026-07-01", "2026-07-02"]
        base["baseline_tokens"] = {
            "output_tokens": 811532,
            "cache_read_tokens": 142390931,
            "cache_creation_tokens": 11646080,
        }
        base.update(over)
        path.write_text(json.dumps(base), encoding="utf-8")

    def test_inflated_wallet_is_zeroed(self, tmp_path):
        p = tmp_path / "state.json"
        self._write_v1(p)
        st = StateManager(state_path=p).load()
        assert st.wallet.bits == 0
        assert st.wallet.echoes == 0
        assert st.lifetime_bits_earned == 0

    def test_baseline_cleared_so_main_reanchors(self, tmp_path):
        p = tmp_path / "state.json"
        self._write_v1(p)
        st = StateManager(state_path=p).load()
        assert st.baseline_tokens.output_tokens == 0
        assert st.baseline_tokens.cache_read_tokens == 0
        assert st.baseline_tokens.cache_creation_tokens == 0

    def test_progression_is_preserved(self, tmp_path):
        """Stage and feeding history must survive — BABY->ADULT is day-gated."""
        p = tmp_path / "state.json"
        self._write_v1(p)
        st = StateManager(state_path=p).load()
        assert st.creature.stage == "BABY"
        assert st.creature.daily_feeding_log == ["2026-07-01", "2026-07-02"]

    def test_migration_is_idempotent(self, tmp_path):
        """Second load must not re-run: earned currency is not wiped again."""
        p = tmp_path / "state.json"
        self._write_v1(p)
        mgr = StateManager(state_path=p)
        mgr.load()

        st = mgr.load()
        st.wallet.bits = 42
        mgr.save(st)

        again = mgr.load()
        assert again.version == SCHEMA_VERSION
        assert again.wallet.bits == 42, "migration re-ran and wiped real currency"

    def test_version_is_stamped_and_persisted(self, tmp_path):
        p = tmp_path / "state.json"
        self._write_v1(p)
        StateManager(state_path=p).load()
        on_disk = json.loads(p.read_text(encoding="utf-8"))
        assert on_disk["version"] == SCHEMA_VERSION
        assert on_disk["wallet"]["bits"] == 0

    def test_already_v2_untouched(self, tmp_path):
        p = tmp_path / "state.json"
        self._write_v1(p, version=SCHEMA_VERSION)
        st = StateManager(state_path=p).load()
        assert st.wallet.bits == 137807, "a v2 file must not be migrated"

    def test_worn_hat_is_grandfathered_into_inventory(self, tmp_path):
        """A hat being worn has already been paid for. Do not charge for it again."""
        p = tmp_path / "state.json"
        self._write_v1(p)
        data = json.loads(p.read_text(encoding="utf-8"))
        data["creature"]["hat_slot"] = "hat_a"
        p.write_text(json.dumps(data), encoding="utf-8")

        st = StateManager(state_path=p).load()
        assert st.inventory == ["hat_a"]
        assert st.creature.hat_slot == "hat_a", "must still be worn"

    def test_no_hat_means_empty_inventory(self, tmp_path):
        p = tmp_path / "state.json"
        self._write_v1(p)
        st = StateManager(state_path=p).load()
        assert st.inventory == []

    def test_grandfathered_hat_is_then_free_to_re_equip(self, tmp_path):
        """End-to-end: the migrated player can wear their hat at zero cost."""
        from tokengotchi.engine.actions import equip, unequip

        p = tmp_path / "state.json"
        self._write_v1(p)
        data = json.loads(p.read_text(encoding="utf-8"))
        data["creature"]["hat_slot"] = "hat_b"
        p.write_text(json.dumps(data), encoding="utf-8")

        st = StateManager(state_path=p).load()
        creature = st.to_creature()
        wallet = st.to_wallet()
        assert wallet.echoes == 0, "reset leaves nothing to spend"

        unequip(creature)
        assert creature.hat_slot is None
        assert equip(creature, st.inventory, "hat_b") is True
        assert creature.hat_slot == "hat_b"
        assert wallet.echoes == 0, "re-equipping must not require currency"
