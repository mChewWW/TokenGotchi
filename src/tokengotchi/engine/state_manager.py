"""State persistence: read/write ~/.tokengotchi/state.json using pydantic."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from tokengotchi.engine.creature import Creature, Stage
from tokengotchi.engine.wallet import Wallet

logger = logging.getLogger(__name__)

# Serialises state writes within this process. The render loop and the
# StatsWatcher thread both persist, and on Windows a rename onto a path
# another thread is renaming onto fails outright.
_WRITE_LOCK = threading.Lock()

# -----------------------------------------------------------------------
# Pydantic schema
#
# SCHEMA_VERSION drives the migration ladder in StateManager._migrate. Note the
# read path is version-TOLERANT by construction: no model sets `extra`, so an
# older build loading a newer file silently drops unknown keys rather than
# failing — which also means downgrading is lossy, not merely safe.
# -----------------------------------------------------------------------

STATE_DIR = Path.home() / ".tokengotchi"
STATE_FILE = STATE_DIR / "state.json"
SCHEMA_VERSION = 4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CreatureState(BaseModel):
    stage: str = "EGG"
    hunger: float = 100.0
    dormancy_start: Optional[datetime] = None
    hat_slot: Optional[str] = None
    daily_feeding_log: list[str] = Field(default_factory=list)
    last_hunger_update: datetime = Field(default_factory=_utcnow)
    pre_dormant_stage: Optional[str] = None


class WalletState(BaseModel):
    bits: int = 0
    echoes: int = 0


class DailyUsage(BaseModel):
    """One UTC day of RAW tokens.

    Raw is load-bearing. If multiplied tokens ever reach these buckets the
    earn multiplier feeds its own input and the whole system diverges — the
    single most dangerous edge in the dynamic-rate design.
    """
    date: str = ""
    output_tokens: int = 0
    cache_tokens: int = 0


class RatePoint(BaseModel):
    at: datetime = Field(default_factory=_utcnow)
    earn: float = 1.0
    drain: float = 1.0


class RateState(BaseModel):
    earn_mult: float = 1.0
    drain_mult: float = 1.0
    prev_earn_mult: float = 1.0
    prev_drain_mult: float = 1.0
    period_start: datetime = Field(default_factory=_utcnow)
    baseline_output_per_day: float = 0.0
    resting: bool = False
    calibrating: bool = True
    last_token_at: Optional[datetime] = None
    history: list[RatePoint] = Field(default_factory=list)


class BaselineTokens(BaseModel):
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


class GameState(BaseModel):
    version: int = SCHEMA_VERSION
    creature: CreatureState = Field(default_factory=CreatureState)
    wallet: WalletState = Field(default_factory=WalletState)
    baseline_tokens: BaselineTokens = Field(default_factory=BaselineTokens)
    # Tokens earned but not yet worth a whole unit. Without these the floor
    # division threw the remainder away on EVERY watcher fire while the
    # baseline advanced past it regardless -- tokens consumed, nothing paid.
    # Kept as raw tokens, always below the conversion ratio.
    pending_output_tokens: int = 0
    pending_cache_tokens: int = 0
    # Trailing daily buckets that drive the pet's appetite. Capped at 8 (the
    # 7-day window plus today) and pruned on write.
    usage_history: list[DailyUsage] = Field(default_factory=list)
    rates: RateState = Field(default_factory=RateState)
    # Item ids the player owns outright. Player-level, not creature-level:
    # a wardrobe outlives any individual creature.
    inventory: list[str] = Field(default_factory=list)
    # Equipped screen skin. Player-level, not creature-level: the device
    # outlives any one pet. None = the default P1 phosphor screen.
    screen_slot: Optional[str] = None
    # Equipped case skin. Same reasoning as screen_slot: the device is the
    # player's, not the creature's.
    shell_slot: Optional[str] = None
    lifetime_bits_earned: int = 0
    first_launch: datetime = Field(default_factory=_utcnow)
    last_launch: datetime = Field(default_factory=_utcnow)

    # ----------------------------------------------------------------
    # Helpers: convert to/from domain objects
    # ----------------------------------------------------------------

    def to_creature(self) -> Creature:
        cs = self.creature
        stage = Stage(cs.stage)
        pre_dormant = Stage(cs.pre_dormant_stage) if cs.pre_dormant_stage else None
        return Creature(
            stage=stage,
            hunger=cs.hunger,
            dormancy_start=cs.dormancy_start,
            hat_slot=cs.hat_slot,
            daily_feeding_log=list(cs.daily_feeding_log),
            last_hunger_update=cs.last_hunger_update,
            pre_dormant_stage=pre_dormant,
        )

    def to_wallet(self) -> Wallet:
        return Wallet(bits=self.wallet.bits, echoes=self.wallet.echoes)

    def apply_creature(self, creature: Creature) -> None:
        self.creature = CreatureState(
            stage=creature.stage.value,
            hunger=creature.hunger,
            dormancy_start=creature.dormancy_start,
            hat_slot=creature.hat_slot,
            daily_feeding_log=list(creature.daily_feeding_log),
            last_hunger_update=creature.last_hunger_update,
            pre_dormant_stage=(
                creature._pre_dormant_stage.value
                if creature._pre_dormant_stage
                else None
            ),
        )

    def apply_wallet(self, wallet: Wallet) -> None:
        self.wallet = WalletState(bits=wallet.bits, echoes=wallet.echoes)


# -----------------------------------------------------------------------
# StateManager
# -----------------------------------------------------------------------


class StateManager:
    """Load/save ~/.tokengotchi/state.json.

    Pass ``state_path`` to override the default location (useful in tests).
    """

    def __init__(self, state_path: Path | None = None) -> None:
        self._state_file: Path = state_path if state_path is not None else STATE_FILE

    def is_first_launch(self) -> bool:
        """Return True if the state file does not yet exist."""
        return not self._state_file.exists()

    def load(self) -> GameState:
        """Load state from disk.

        If the file does not exist, create it with defaults (first launch).
        """
        if self.is_first_launch():
            state = self._create_default()
            self._write(state)
            return state

        raw = self._state_file.read_text(encoding="utf-8")
        data = json.loads(raw)

        stored_version = data.get("version", 1)

        # Update last_launch on every load
        state = GameState.model_validate(data)
        state.last_launch = _utcnow()

        if stored_version < SCHEMA_VERSION:
            state = self._migrate(state, stored_version)
            self._write(state)

        return state

    def _migrate(self, state: GameState, stored_version: int) -> GameState:
        """Bring a state file forward to SCHEMA_VERSION.

        v1 → v2 — currency reset.
            A v1 file was written by a watcher that never advanced its baseline,
            so every fire re-credited the entire lifetime token total instead of
            the increment since the last check. Balances compounded several times
            a minute; one such save held 137,807 BITS against 724 actually earned.

            The inflated balance is unrecoverable — the true figure cannot be
            reconstructed from the file — so the balance is reset and the
            baseline re-anchored on the next read, and earning restarts cleanly
            from zero.

            Progression is deliberately preserved: `stage` is untouched, and
            BABY → ADULT is gated on distinct feeding days rather than on BITS,
            so zeroing lifetime_bits_earned costs the player nothing.
        """
        # v2 -> v3 adds `screen_slot`. No migration branch is needed: no model
        # sets `extra`, so a v2 file loads with the field defaulted to None.
        # The bump is documentary.
        if stored_version < 2:
            logger.warning(
                "Migrating state v%d -> 2: resetting inflated wallet "
                "(bits=%d echoes=%d lifetime=%d).",
                stored_version,
                state.wallet.bits,
                state.wallet.echoes,
                state.lifetime_bits_earned,
            )
            state.wallet.bits = 0
            state.wallet.echoes = 0
            state.lifetime_bits_earned = 0
            # Zeroed baseline forces main.py to re-anchor against the current
            # token snapshot, so pre-existing usage is not credited as new.
            state.baseline_tokens = BaselineTokens()

            # Grandfather the wardrobe. A v1 file carries no ownership record —
            # its hat was charged per equip, not bought once. A player already
            # wearing one has demonstrably paid for it, repeatedly; do not
            # charge again.
            if not state.inventory and state.creature.hat_slot:
                state.inventory = [state.creature.hat_slot]
                logger.info(
                    "Grandfathered worn hat %r into inventory.",
                    state.creature.hat_slot,
                )

        if stored_version < 4:
            # v3 -> v4 adds usage_history and rates. Pydantic defaults cover
            # the load, so the only real work is anchoring the rate period to
            # the current slot instead of to whenever the file was written.
            #
            # usage_history is deliberately NOT back-filled. There is no honest
            # source for it, and inventing one is exactly the class of mistake
            # that produced the 190x inflation. An existing save therefore
            # calibrates for two days at 1.0x, the same as a new install —
            # neither punished nor rewarded by the transition.
            from . import rates as _rates
            state.rates.period_start = _rates.period_start(_utcnow())
            logger.info("Migrating state v%d -> 4: rate window starts empty; "
                        "calibrating for %d days.", stored_version,
                        _rates.CALIBRATION_DAYS)
        state.version = SCHEMA_VERSION
        return state

    def save(self, state: GameState) -> None:
        """Persist state to disk atomically (write-then-rename)."""
        state.last_launch = _utcnow()
        self._write(state)

    # ----------------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------------

    def _create_default(self) -> GameState:
        now = _utcnow()
        return GameState(
            version=SCHEMA_VERSION,
            creature=CreatureState(
                stage="EGG",
                hunger=100.0,
                dormancy_start=None,
                hat_slot=None,
                daily_feeding_log=[],
                last_hunger_update=now,
                pre_dormant_stage=None,
            ),
            wallet=WalletState(bits=0, echoes=0),
            baseline_tokens=BaselineTokens(
                output_tokens=0,
                cache_read_tokens=0,
                cache_creation_tokens=0,
            ),
            lifetime_bits_earned=0,
            first_launch=now,
            last_launch=now,
        )

    def _write(self, state: GameState) -> None:
        """Write state atomically, creating the directory if needed.

        Write-then-rename with a per-call unique temp file. On Windows
        ``Path.replace`` raises ``PermissionError 13`` when the destination is
        held open by anyone else.

        Two defences, because the two races are different:

        - **Same process** (the render loop and the StatsWatcher thread both
          saving) is serialised by ``_WRITE_LOCK``. Retrying through a race you
          can simply prevent is the wrong shape of fix: retry alone fails
          roughly 1 run in 6 under contention, because a ~100ms back-off budget
          is far shorter than the window a competing thread holds the file.
        - **Different processes** (two app instances, an editor, a backup
          agent, antivirus) cannot be locked out, so the retry stays as a
          backstop, with a budget wide enough to outlast them.
        """
        import os as _os
        import tempfile as _tempfile
        import time as _time

        with _WRITE_LOCK:
            self._write_locked(state, _os, _tempfile, _time)

    def _write_locked(self, state: GameState, _os, _tempfile, _time) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = state.model_dump_json(indent=2)

        # Write to a uniquely-named temp file in the same directory so the
        # final rename stays on the same filesystem (required for atomicity).
        fd, tmp_str = _tempfile.mkstemp(
            dir=self._state_file.parent,
            prefix=".state_",
            suffix=".tmp",
        )
        try:
            _os.write(fd, payload.encode("utf-8"))
        finally:
            _os.close(fd)

        tmp = Path(tmp_str)

        # Backstop for cross-process contention, which no in-process lock can
        # prevent. 10 attempts with exponential back-off ≈ 1.2s total, an order
        # of magnitude more patience than a short linear retry buys.
        last_exc: Exception | None = None
        for attempt in range(10):
            try:
                tmp.replace(self._state_file)
                return
            except (PermissionError, OSError) as exc:
                last_exc = exc
                _time.sleep(min(0.25, 0.005 * (2 ** attempt)))

        # Clean up the temp file if rename never succeeded.
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass

        # All retries exhausted — raise so the caller knows about it.
        raise last_exc  # type: ignore[misc]
