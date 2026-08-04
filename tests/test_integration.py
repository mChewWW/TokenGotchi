"""Integration tests for TokenGotchi — verifies all 7 MVP success criteria.

These tests exercise the full pipeline with real file I/O (tmp_path).
No pygame is required; the GameWindow is stubbed.

Criteria tested
---------------
1. Real-time token update  — watcher callback credits BITS correctly.
2. Delta baseline          — first-launch historical tokens are NOT credited.
3. Persistence             — stage, hunger, hat_slot survive save → load.
4. Hunger decay            — 7-hour stale last_hunger_update produces correct decay.
5. Dormancy               — creature enters DORMANT after 13 h at 0 hunger;
                             feeding exits dormancy.
6. Cosmetic purchase       — dress() debits 1 ECHO and sets hat_slot; persists.
7. Schema guard            — version=999 raises SchemaVersionError, no crash.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tokengotchi.engine.actions import (
    purchase, equip, unequip, feed, BITS_PER_FEED,
)
from tokengotchi.engine.creature import (
    Creature, Stage, HUNGER_DECAY_PER_6H, HOURS_PER_DECAY_PERIOD,
)
from tokengotchi.engine.state_manager import (
    BaselineTokens,
    CreatureState,
    GameState,
    StateManager,
    WalletState,
)
from tokengotchi.engine.wallet import Wallet
from tokengotchi.reader.stats_reader import (
    BITS_RATIO,
    ECHOES_RATIO,
    SchemaVersionError,
    StatsReader,
    TokenSnapshot,
)
from tokengotchi.reader.watcher import StatsWatcher

# Prices are owned by Rarity (shop/catalogue.py), not by these tests.
from tokengotchi.shop import catalogue as _cat
HAT_A = _cat.get("hat_a")
HAT_B = _cat.get("hat_b")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stats_cache(path: Path, output_tokens: int = 0, cache_read: int = 0,
                      cache_creation: int = 0, version: int = 4) -> None:
    """Set up the token source StatsReader actually reads.

    The name is kept because call sites pass a `stats-cache.json` path, but the
    reader stopped counting tokens from that file: it scans
    `<stats_path>.parent/projects/**/*.jsonl`. This writes BOTH — the
    stats-cache for the schema guard, which still reads it, and a JSONL entry
    carrying the usage that the assertions are about.

    Rewrites (not appends) the JSONL so repeated calls express "the totals are
    now N", which is what every call site means.
    """
    data = {
        "version": version,
        "lastComputedDate": "2026-07-24",
        "modelUsage": {},
        "totalSessions": 1,
        "totalMessages": 1,
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    projects = path.parent / "projects" / "session"
    projects.mkdir(parents=True, exist_ok=True)
    (projects / "a.jsonl").write_text(
        json.dumps({
            "usage": {
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
            }
        }) + chr(10),
        encoding="utf-8",
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utc_hours_ago(hours: float) -> datetime:
    return _utcnow() - timedelta(hours=hours)


# ---------------------------------------------------------------------------
# 1. Real-time token update
#    Create a stats-cache fixture, initialise reader with it as baseline.
#    Modify the fixture to add 100 output tokens.
#    Trigger watcher callback manually (no threading needed).
#    Verify wallet.bits increased by 2 (100 // 50 = 2).
# ---------------------------------------------------------------------------

class TestRealtimeTokenUpdate:
    def test_100_output_tokens_yields_2_bits(self, tmp_path: Path) -> None:
        stats_file = tmp_path / "stats-cache.json"

        # Initial state: 50 output tokens — used as baseline.
        _make_stats_cache(stats_file, output_tokens=BITS_RATIO)
        baseline = TokenSnapshot(output_tokens=BITS_RATIO, cache_read_tokens=0,
                                 cache_creation_tokens=0)
        reader = StatsReader(stats_file, baseline=baseline)

        wallet = Wallet()
        bits_earned: list[int] = []

        def on_update(delta):
            wallet.add_bits(delta.bits)
            wallet.add_echoes(delta.echoes)
            bits_earned.append(delta.bits)

        # Now earn two more BITS worth of output tokens.
        _make_stats_cache(stats_file, output_tokens=BITS_RATIO * 3)

        # Simulate the watcher callback: read snapshot and compute delta.
        snap = reader.read_snapshot()
        delta = reader.compute_delta(snap)
        on_update(delta)

        # Two ratios above the baseline -> exactly 2 BITS.
        assert wallet.bits == 2, f"Expected 2 BITS, got {wallet.bits}"
        assert bits_earned == [2]

    def test_partial_tokens_below_ratio_earns_nothing(self, tmp_path: Path) -> None:
        stats_file = tmp_path / "stats-cache.json"
        _make_stats_cache(stats_file, output_tokens=0)
        baseline = TokenSnapshot(output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0)
        reader = StatsReader(stats_file, baseline=baseline)

        # Add only 49 output tokens — not enough for 1 BITS.
        _make_stats_cache(stats_file, output_tokens=49)
        snap = reader.read_snapshot()
        delta = reader.compute_delta(snap)

        assert delta.bits == 0

    def test_cache_tokens_yield_echoes(self, tmp_path: Path) -> None:
        stats_file = tmp_path / "stats-cache.json"
        _make_stats_cache(stats_file, cache_read=0, cache_creation=0)
        baseline = TokenSnapshot(output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0)
        reader = StatsReader(stats_file, baseline=baseline)

        # Two ratios worth of cache tokens, split across both kinds.
        _make_stats_cache(stats_file, cache_read=ECHOES_RATIO,
                          cache_creation=ECHOES_RATIO)
        snap = reader.read_snapshot()
        delta = reader.compute_delta(snap)

        assert delta.echoes == 2


# ---------------------------------------------------------------------------
# 2. Delta baseline
#    Load state for first time with stats-cache showing 65 815 historical
#    output tokens.  Verify wallet.bits == 0 (baseline set to current).
# ---------------------------------------------------------------------------

class TestDeltaBaseline:
    def test_historical_tokens_not_credited(self, tmp_path: Path) -> None:
        stats_file = tmp_path / "stats-cache.json"
        # 65 815 historical output tokens exist before first launch.
        _make_stats_cache(stats_file, output_tokens=65815)  # arbitrary history

        # On first launch the snapshot becomes the baseline.
        snap = StatsReader(stats_file).read_snapshot()
        assert snap.output_tokens == 65815

        baseline = TokenSnapshot(
            output_tokens=snap.output_tokens,
            cache_read_tokens=snap.cache_read_tokens,
            cache_creation_tokens=snap.cache_creation_tokens,
        )
        reader = StatsReader(stats_file, baseline=baseline)

        # No new tokens added — delta should be zero.
        snap2 = reader.read_snapshot()
        delta = reader.compute_delta(snap2)

        assert delta.bits == 0, "Historical tokens must not be credited on first launch"
        assert delta.echoes == 0

    def test_only_new_tokens_after_baseline_are_credited(self, tmp_path: Path) -> None:
        stats_file = tmp_path / "stats-cache.json"
        _make_stats_cache(stats_file, output_tokens=65815)

        snap = StatsReader(stats_file).read_snapshot()
        baseline = TokenSnapshot(
            output_tokens=snap.output_tokens,
            cache_read_tokens=snap.cache_read_tokens,
            cache_creation_tokens=snap.cache_creation_tokens,
        )
        reader = StatsReader(stats_file, baseline=baseline)

        # Earn exactly two BITS worth after the baseline.
        _make_stats_cache(stats_file, output_tokens=65815 + BITS_RATIO * 2)
        snap2 = reader.read_snapshot()
        delta = reader.compute_delta(snap2)

        assert delta.bits == 2


# ---------------------------------------------------------------------------
# 3. Persistence
#    Create game state, save it.  Load it fresh.
#    Verify stage, hunger, hat_slot all match.
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_state_round_trips(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        manager = StateManager(state_path=state_file)

        # Build a specific game state.
        state = GameState(
            creature=CreatureState(
                stage="BABY",
                hunger=72.5,
                hat_slot="hat_a",
                daily_feeding_log=["2026-07-24"],
            ),
            wallet=WalletState(bits=42, echoes=3),
            lifetime_bits_earned=42,
        )
        manager.save(state)

        # Load fresh.
        manager2 = StateManager(state_path=state_file)
        loaded = manager2.load()

        assert loaded.creature.stage == "BABY"
        assert abs(loaded.creature.hunger - 72.5) < 0.001
        assert loaded.creature.hat_slot == "hat_a"
        assert loaded.wallet.bits == 42
        assert loaded.wallet.echoes == 3
        assert loaded.lifetime_bits_earned == 42

    def test_first_launch_creates_file(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        manager = StateManager(state_path=state_file)
        assert manager.is_first_launch() is True

        state = manager.load()
        assert state_file.exists()
        assert manager.is_first_launch() is False

    def test_fresh_state_defaults(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        manager = StateManager(state_path=state_file)
        state = manager.load()

        assert state.creature.stage == "EGG"
        assert state.creature.hunger == 100.0
        assert state.creature.hat_slot is None
        assert state.wallet.bits == 0
        assert state.wallet.echoes == 0


# ---------------------------------------------------------------------------
# 4. Hunger decay
#    Create state with last_hunger_update = 7 hours ago.
#    Call apply_time_decay(now).
#    Verify hunger ≤ 88.4.
#    (Decay rate: 10 pts / 6 h; 7 h → 10*(7/6) ≈ 11.667 pts decayed)
# ---------------------------------------------------------------------------

class TestHungerDecay:
    def test_one_hour_decay(self) -> None:
        last_update = _utc_hours_ago(1)
        creature = Creature(
            stage=Stage.BABY,
            hunger=100.0,
            last_hunger_update=last_update,
        )
        now = _utcnow()
        creature.apply_time_decay(now)

        expected = 100.0 - (HUNGER_DECAY_PER_6H / HOURS_PER_DECAY_PERIOD)
        assert abs(creature.hunger - expected) < 0.5, (
            f"expected ~{expected:.2f}, got {creature.hunger}")

    def test_exact_1_hour_decay(self) -> None:
        """One hour, not six: a full bar is now three hours of session time."""
        last_update = _utc_hours_ago(1)
        creature = Creature(stage=Stage.ADULT, hunger=100.0, last_hunger_update=last_update)
        creature.apply_time_decay(_utcnow())
        rate = HUNGER_DECAY_PER_6H / 6.0
        assert abs(creature.hunger - (100.0 - rate)) < 0.5

    def test_hunger_floor_is_zero(self) -> None:
        last_update = _utc_hours_ago(200)
        creature = Creature(stage=Stage.BABY, hunger=100.0, last_hunger_update=last_update)
        creature.apply_time_decay(_utcnow())
        assert creature.hunger == 0.0

    def test_dormant_creature_hunger_unchanged(self) -> None:
        last_update = _utc_hours_ago(7)
        creature = Creature(stage=Stage.DORMANT, hunger=0.0, last_hunger_update=last_update)
        creature.apply_time_decay(_utcnow())
        assert creature.hunger == 0.0


# ---------------------------------------------------------------------------
# 5. Dormancy
#    Create state with hunger=0 and dormancy_start = 13 hours ago.
#    Verify creature is DORMANT.
#    Feed it.  Verify exits DORMANT.
# ---------------------------------------------------------------------------

class TestDormancy:
    def test_creature_enters_dormancy_after_12_hours(self) -> None:
        dormancy_start = _utc_hours_ago(13)
        creature = Creature(
            stage=Stage.BABY,
            hunger=0.0,
            dormancy_start=dormancy_start,
        )
        now = _utcnow()
        creature.check_dormancy(now)
        assert creature.stage is Stage.DORMANT

    def test_feeding_exits_dormancy(self) -> None:
        dormancy_start = _utc_hours_ago(13)
        creature = Creature(
            stage=Stage.BABY,
            hunger=0.0,
            dormancy_start=dormancy_start,
        )
        creature.check_dormancy(_utcnow())
        assert creature.stage is Stage.DORMANT

        wallet = Wallet(bits=20)
        result = feed(creature, wallet, bits_to_spend=BITS_PER_FEED)
        assert result is True
        assert creature.stage is not Stage.DORMANT
        assert creature.hunger > 0.0

    def test_hunger_below_zero_threshold_does_not_immediately_trigger_dormancy(self) -> None:
        """Dormancy only triggers after 12 h at zero, not instantly."""
        creature = Creature(stage=Stage.BABY, hunger=0.0, dormancy_start=None)
        # First call: sets dormancy_start to now.
        creature.check_dormancy(_utcnow())
        assert creature.stage is Stage.BABY  # not yet dormant

    def test_pre_dormant_stage_restored_after_feed(self) -> None:
        """The creature reverts to its pre-dormant stage (not hardcoded BABY)."""
        dormancy_start = _utc_hours_ago(13)
        creature = Creature(
            stage=Stage.ADULT,
            hunger=0.0,
            dormancy_start=dormancy_start,
        )
        creature.check_dormancy(_utcnow())
        assert creature.stage is Stage.DORMANT

        wallet = Wallet(bits=20)
        feed(creature, wallet, bits_to_spend=BITS_PER_FEED)
        assert creature.stage is Stage.ADULT


# ---------------------------------------------------------------------------
# 6. Cosmetic purchase
#    Set wallet.echoes=1.  Call dress(creature, wallet, "hat_a").
#    Verify wallet.echoes==0 and creature.hat_slot=="hat_a".
#    Save and reload.  Verify hat_slot persists.
# ---------------------------------------------------------------------------

class TestCosmeticPurchase:
    def test_purchase_deducts_and_equip_sets_hat(self) -> None:
        creature = Creature(stage=Stage.BABY)
        wallet = Wallet(echoes=HAT_A.cost)
        inv: list[str] = []

        assert purchase(wallet, inv, "hat_a") is True
        assert wallet.echoes == 0
        assert equip(creature, inv, "hat_a") is True
        assert creature.hat_slot == "hat_a"

    def test_hat_slot_and_inventory_persist_through_save_load(
        self, tmp_path: Path
    ) -> None:
        state_file = tmp_path / "state.json"
        manager = StateManager(state_path=state_file)

        creature = Creature(stage=Stage.BABY)
        wallet = Wallet(echoes=HAT_A.cost)
        state = GameState()
        purchase(wallet, state.inventory, "hat_a")
        equip(creature, state.inventory, "hat_a")

        state.apply_creature(creature)
        state.apply_wallet(wallet)
        manager.save(state)

        loaded = StateManager(state_path=state_file).load()
        assert loaded.creature.hat_slot == "hat_a"
        assert loaded.inventory == ["hat_a"], "ownership must survive a round-trip"

    def test_purchase_fails_without_echoes(self) -> None:
        creature = Creature(stage=Stage.BABY)
        wallet = Wallet(echoes=0)
        inv: list[str] = []

        assert purchase(wallet, inv, "hat_a") is False
        assert creature.hat_slot is None

    def test_purchase_hat_b_crown(self) -> None:
        creature = Creature(stage=Stage.ADULT)
        wallet = Wallet(echoes=HAT_B.cost + 5)
        inv: list[str] = []

        purchase(wallet, inv, "hat_b")
        equip(creature, inv, "hat_b")
        assert creature.hat_slot == "hat_b"
        assert wallet.echoes == 5

    def test_purchase_invalid_hat_fails(self) -> None:
        wallet = Wallet(echoes=50)
        inv: list[str] = []

        assert purchase(wallet, inv, "hat_z") is False
        assert wallet.echoes == 50  # no charge


# ---------------------------------------------------------------------------
# 7. Schema guard
#    Point StatsReader at a stats-cache with version=999.
#    Verify SchemaVersionError raised.
#    App-level handler ensures no crash.
# ---------------------------------------------------------------------------

class TestSchemaGuard:
    def test_bad_version_raises_schema_version_error(self, tmp_path: Path) -> None:
        stats_file = tmp_path / "stats-cache.json"
        _make_stats_cache(stats_file, output_tokens=100, version=999)

        reader = StatsReader(stats_file)
        with pytest.raises(SchemaVersionError) as exc_info:
            reader.read_snapshot()

        assert "999" in str(exc_info.value)

    def test_app_handles_schema_error_without_crash(self, tmp_path: Path) -> None:
        """The main entry point catches SchemaVersionError and does not raise."""
        from tokengotchi.main import _HeadlessWindow, _handle_first_launch, _AppState
        from tokengotchi.engine.state_manager import GameState, StateManager

        stats_file = tmp_path / "stats-cache.json"
        _make_stats_cache(stats_file, output_tokens=100, version=999)

        state_file = tmp_path / "state.json"
        manager = StateManager(state_path=state_file)
        game_state = GameState()
        app = _AppState(game_state, show_privacy=False)

        # Should not raise — error is captured and returned as a string.
        stats_missing, schema_error = _handle_first_launch(app, manager, stats_file)

        assert schema_error is not None
        assert "999" in schema_error
        assert stats_missing is False

    def test_schema_error_captured_not_propagated_in_main(self, tmp_path: Path) -> None:
        """main() with a bad-version stats-cache must not raise."""
        from tokengotchi.main import main

        stats_file = tmp_path / "stats-cache.json"
        _make_stats_cache(stats_file, output_tokens=100, version=999)
        state_file = tmp_path / "state.json"

        # A window that quits immediately after the first frame.
        class _QuittingWindow:
            _done = False

            def should_quit(self):
                result = self._done
                self._done = True
                return result

            def render_frame(self, *args, **kwargs):
                return []

            def tick(self, fps=30):
                pass

        # Must not raise.
        main(
            state_path=state_file,
            stats_path=stats_file,
            window=_QuittingWindow(),
        )

    def test_true_zero_state_first_run_starts_cleanly(self, tmp_path: Path) -> None:
        """main() with no state file AND no ~/.claude directory at all.

        This is the actual new-user case: TokenGotchi installed and launched
        before Claude Code has ever been used. Neither the state file, the
        stats-cache.json sentinel, nor ~/.claude/projects/ exist. The app must
        start as a fresh EGG, report stats as genuinely missing, and not crash.
        """
        from tokengotchi.main import main, _HeadlessWindow
        from tokengotchi.engine.state_manager import StateManager
        from tokengotchi.engine.creature import Stage

        state_file = tmp_path / "state.json"
        stats_file = tmp_path / "claude_home" / "stats-cache.json"
        # Neither stats_file nor its parent directory exist on disk.
        assert not stats_file.parent.exists()

        captured: dict = {}

        class _QuittingWindow(_HeadlessWindow):
            def __init__(self) -> None:
                super().__init__()
                self._done = False

            def should_quit(self) -> bool:
                result = self._done
                self._done = True
                return result

            def render_frame(self, game_state, **kwargs):
                captured.update(kwargs)
                captured["game_state"] = game_state
                return []

        main(
            state_path=state_file,
            stats_path=stats_file,
            window=_QuittingWindow(),
        )

        assert captured["stats_missing"] is True
        assert captured["schema_error"] is None
        assert captured["game_state"].creature.stage == Stage.EGG.value

        loaded = StateManager(state_path=state_file).load()
        assert loaded.creature.stage == Stage.EGG.value


# ---------------------------------------------------------------------------
# Bonus: full pipeline smoke test (reader → watcher → wallet → state)
# ---------------------------------------------------------------------------

class TestFullPipelineSmoke:
    def test_end_to_end_token_to_wallet_to_persist(self, tmp_path: Path) -> None:
        """Earn 2 BITS from 100 new output tokens, confirm they persist."""
        stats_file = tmp_path / "stats-cache.json"
        state_file = tmp_path / "state.json"

        # Start: 0 tokens (blank baseline).
        _make_stats_cache(stats_file, output_tokens=0)
        baseline = TokenSnapshot(0, 0, 0)
        reader = StatsReader(stats_file, baseline=baseline)

        manager = StateManager(state_path=state_file)
        game_state = manager.load()  # creates fresh state
        wallet = game_state.to_wallet()

        # Simulate two BITS worth of new output tokens arriving.
        _make_stats_cache(stats_file, output_tokens=BITS_RATIO * 2)
        snap = reader.read_snapshot()
        delta = reader.compute_delta(snap)
        wallet.add_bits(delta.bits)
        game_state.apply_wallet(wallet)
        game_state.lifetime_bits_earned += delta.bits
        manager.save(game_state)

        # Reload and verify.
        loaded = StateManager(state_path=state_file).load()
        assert loaded.wallet.bits == 2
        assert loaded.lifetime_bits_earned == 2
