"""TokenGotchi main entry point.

Wires the full pipeline:
    StateManager → GameState
    StatsReader  → StatsWatcher (token delta → wallet credits)
    GameWindow   (pygame renderer — imported lazily so tests can stub it)
    main loop    (30 fps, action dispatch, time decay, persistence)

First-launch flow
-----------------
1. StateManager.is_first_launch() returns True.
2. Read live JSONL session data under ~/.claude/projects/ (via StatsReader) →
   set state.baseline_tokens to current snapshot.
3. Set state.show_privacy = True.
4. Set state.first_launch = now.
5. Save state.
6. Show privacy notice until user clicks "Got it!".

Error handling
--------------
- No Claude Code session data found yet → `stats_missing` is set and the
  watcher is not started; the creature stays as an egg, no currency earned
  until real usage appears. Checked against the live JSONL source under
  ~/.claude/projects/, not stats-cache.json alone — that file is only
  written at session end, so gating on it reports a false "not found"
  state for a user's entire first Claude Code session. NOTE: `stats_missing`
  and `schema_error` are computed and passed to the window, but no renderer
  currently draws them — surfacing either in the UI is unbuilt.
- SchemaVersionError             → captured, does not crash; see note above.
- State file corrupt on load     → log warning, create a fresh state, continue.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from tokengotchi.config import (
    ALWAYS_ON_TOP,
    BITS_RATIO,
    ECHOES_RATIO,
    FPS,
    STATE_PATH,
    STATS_CACHE_PATH,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from tokengotchi.engine import rates as raterules
from tokengotchi.engine.actions import (
    feed_item,
    BITS_PER_FEED,
    FEED_COST,
    equip,
    equip_screen,
    equip_shell,
    feed,
    purchase,
    unequip,
)
from tokengotchi.engine.creature import Creature
from tokengotchi.engine.state_manager import (
    DailyUsage,
    RatePoint,
    BaselineTokens,
    GameState,
    StateManager,
)
from tokengotchi.engine.wallet import Wallet
from tokengotchi.reader.stats_reader import (
    SchemaVersionError,
    StatsReader,
    TokenSnapshot,
)
from tokengotchi.reader.watcher import StatsWatcher

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Privacy / show_privacy — added as an optional field on GameState at runtime
# ---------------------------------------------------------------------------

_MISSING_STATS_MSG = (
    "No Claude Code session data found yet — "
    "your tokens will be counted once you start using Claude Code."
)

# ---------------------------------------------------------------------------
# App state (runtime additions not persisted in schema yet)
# ---------------------------------------------------------------------------


# Persistence cadence. The loop runs at 30fps; saving on every frame costs four
# times as much as rendering. A change is flushed within SAVE_DEBOUNCE, and an
# idle session still checkpoints every SAVE_HEARTBEAT.
SAVE_DEBOUNCE = 1.0    # seconds after a real change before writing
SAVE_HEARTBEAT = 60.0  # seconds between writes when nothing has changed


class _AppState:
    """Thin wrapper around GameState adding runtime-only flags."""

    def __init__(self, game_state: GameState, show_privacy: bool = False) -> None:
        self.game_state = game_state
        self.show_privacy = show_privacy
        self._dirty = True          # first frame always persists
        self._last_save = 0.0

    # ── Persistence bookkeeping ─────────────────────────────────────────
    # A dirty flag rather than comparing state: StateManager.save() mutates
    # last_launch on every call, so any equality check against the previous
    # snapshot reports a change every time and never settles.

    def mark_dirty(self) -> None:
        self._dirty = True

    def mark_saved(self, when: float) -> None:
        self._dirty = False
        self._last_save = when

    def should_save(self, when: float) -> bool:
        since = when - self._last_save
        if self._dirty:
            return since >= SAVE_DEBOUNCE
        return since >= SAVE_HEARTBEAT

    # Convenience passthrough properties
    @property
    def baseline_tokens(self) -> BaselineTokens:
        return self.game_state.baseline_tokens

    @baseline_tokens.setter
    def baseline_tokens(self, value: BaselineTokens) -> None:
        self.game_state.baseline_tokens = value

    @property
    def lifetime_bits_earned(self) -> int:
        return self.game_state.lifetime_bits_earned

    @lifetime_bits_earned.setter
    def lifetime_bits_earned(self, value: int) -> None:
        self.game_state.lifetime_bits_earned = value


# ---------------------------------------------------------------------------
# Minimal GameWindow stub (used when pygame is unavailable or in tests)
# ---------------------------------------------------------------------------


class _HeadlessWindow:
    """No-display fallback — used when pygame is absent or in CI.

    render_frame() returns an empty action list; tick() is a no-op.
    """

    def __init__(self) -> None:
        self._quit = False

    def should_quit(self) -> bool:
        return self._quit

    def render_frame(
        self,
        game_state: GameState,
        show_privacy: bool = False,
        stats_missing: bool = False,
        schema_error: str | None = None,
    ) -> list[str]:
        return []

    def tick(self, fps: int = 30) -> None:
        pass

    def quit(self) -> None:
        self._quit = True


# ---------------------------------------------------------------------------
# GameWindow (pygame implementation) — imported lazily
# ---------------------------------------------------------------------------


def _build_game_window() -> object:
    """Return the real GameWindow if pygame is available, else the headless stub."""
    try:
        # GameWindow lives in tokengotchi.renderer, which pulls in pygame.
        from tokengotchi.renderer import GameWindow  # type: ignore[import]
        return GameWindow(always_on_top=ALWAYS_ON_TOP)
    except ImportError:
        logger.warning("tokengotchi.renderer not available; running headless.")
        return _HeadlessWindow()
    except Exception as exc:
        logger.error("Failed to create GameWindow: %s", exc)
        return _HeadlessWindow()


# ---------------------------------------------------------------------------
# Currency update callback (thread-safe via threading.Lock)
# ---------------------------------------------------------------------------


def _make_on_update(
    wallet: Wallet,
    app_state: _AppState,
    lock: threading.Lock,
    state_manager: StateManager,
    reader: StatsReader,
) -> object:
    """Return a callback suitable for StatsWatcher.

    The callback credits BITS and ECHOES to *wallet*, then persists state.
    It runs on the watchdog thread, so all mutations are guarded by *lock*.
    """

    def on_update(delta):  # type: ignore[no-untyped-def]
        with lock:
            # Convert from the RAW delta plus whatever was left over last
            # time, rather than from the pre-floored counts. The watcher
            # advances the baseline on every fire, so a remainder that is not
            # banked here is not "credited later" -- it is gone.
            gs = app_state.game_state
            now = datetime.now(timezone.utc)

            # RAW tokens into the daily bucket, ALWAYS. If multiplied tokens
            # ever reach the history the earn multiplier feeds its own input
            # and the system diverges. This is the single most dangerous edge
            # in the design and it is one line.
            if delta.raw_output or delta.raw_cache:
                key = raterules.day_key(now)
                row = next((r for r in gs.usage_history if r.date == key), None)
                if row is None:
                    row = DailyUsage(date=key)
                    gs.usage_history.append(row)
                row.output_tokens += delta.raw_output
                row.cache_tokens += delta.raw_cache
                gs.usage_history.sort(key=lambda r: r.date)
                del gs.usage_history[:-8]
                gs.rates.last_token_at = now

            # The multiplier is applied ONCE, here, to a delta — never to a
            # balance and never to a stored remainder. `pending_*` is already
            # in effective tokens, so a remainder banked at 1.0x stays worth
            # 1.0x when the rate later moves.
            earn = gs.rates.earn_mult
            pend_o = gs.pending_output_tokens + int(delta.raw_output * earn)
            pend_c = gs.pending_cache_tokens + delta.raw_cache
            bits = pend_o // BITS_RATIO
            echoes = pend_c // ECHOES_RATIO
            gs.pending_output_tokens = pend_o - bits * BITS_RATIO
            gs.pending_cache_tokens = pend_c - echoes * ECHOES_RATIO
            if bits > 0:
                wallet.add_bits(bits)
                app_state.lifetime_bits_earned += bits
            if echoes > 0:
                wallet.add_echoes(echoes)
            # Persist the advanced baseline alongside the credit. The watcher
            # moves it forward on every fire; if it is not written back here,
            # the next launch reloads the stale one from disk and re-credits
            # everything earned since it.
            live = reader.baseline
            if live is not None:
                app_state.baseline_tokens = BaselineTokens(
                    output_tokens=live.output_tokens,
                    cache_read_tokens=live.cache_read_tokens,
                    cache_creation_tokens=live.cache_creation_tokens,
                )
            # Sync back to GameState and persist
            app_state.game_state.apply_wallet(wallet)
            app_state.game_state.lifetime_bits_earned = app_state.lifetime_bits_earned
            state_manager.save(app_state.game_state)

    return on_update


# ---------------------------------------------------------------------------
# First-launch setup
# ---------------------------------------------------------------------------


def _has_claude_data(stats_path: Path) -> bool:
    """True if Claude Code has produced anything TokenGotchi can read.

    The live token source is JSONL session files under ~/.claude/projects/
    (see stats_reader.py) — Claude Code writes those after every assistant
    response. stats-cache.json only appears at session end, so checking it
    alone reports "missing" for a user's entire first Claude Code session
    even while real usage is already accruing. Either source counts.
    """
    projects_dir = StatsReader(stats_path).projects_dir
    if projects_dir.exists() and any(projects_dir.rglob("*.jsonl")):
        return True
    return stats_path.exists()


def _handle_first_launch(
    app_state: _AppState,
    state_manager: StateManager,
    stats_path: Path,
) -> tuple[bool, str | None]:
    """Perform first-launch initialisation.

    Returns (stats_missing, schema_error_msg).
    """
    now = datetime.now(timezone.utc)
    app_state.game_state.first_launch = now
    app_state.show_privacy = True

    schema_error: str | None = None
    stats_missing: bool = False

    if not _has_claude_data(stats_path):
        stats_missing = True
        logger.info("No Claude Code session data found for %s", stats_path)
    else:
        try:
            reader = StatsReader(stats_path)
            snap = reader.read_snapshot()
            app_state.baseline_tokens = BaselineTokens(
                output_tokens=snap.output_tokens,
                cache_read_tokens=snap.cache_read_tokens,
                cache_creation_tokens=snap.cache_creation_tokens,
            )
        except SchemaVersionError as exc:
            schema_error = str(exc)
            logger.error("SchemaVersionError on first launch: %s", exc)
        except Exception as exc:
            logger.warning("Could not read Claude Code session data on first launch: %s", exc)
            stats_missing = True

    state_manager.save(app_state.game_state)
    return stats_missing, schema_error


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(
    *,
    state_path: Path | None = None,
    stats_path: Path | None = None,
    window: object | None = None,
) -> None:
    """Launch TokenGotchi.

    Keyword arguments allow tests to inject overrides without touching the
    module-level constants.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _state_path: Path = state_path if state_path is not None else STATE_PATH
    _stats_path: Path = stats_path if stats_path is not None else STATS_CACHE_PATH

    # -----------------------------------------------------------------------
    # 1. Load (or create) game state
    # -----------------------------------------------------------------------
    manager = StateManager(state_path=_state_path)
    is_first = manager.is_first_launch()

    try:
        game_state = manager.load()
    except Exception as exc:
        logger.warning("State load failed (%s); starting fresh.", exc)
        game_state = GameState()
        try:
            manager.save(game_state)
        except Exception as save_exc:
            logger.error("Could not save fresh state: %s", save_exc)

    app = _AppState(game_state, show_privacy=False)

    # -----------------------------------------------------------------------
    # 2. First-launch flow
    # -----------------------------------------------------------------------
    stats_missing: bool = False
    schema_error: str | None = None

    if is_first:
        stats_missing, schema_error = _handle_first_launch(app, manager, _stats_path)
    else:
        if not _has_claude_data(_stats_path):
            stats_missing = True

    # -----------------------------------------------------------------------
    # 3. Reconstruct live domain objects from persisted state
    # -----------------------------------------------------------------------
    creature = game_state.to_creature()
    wallet = game_state.to_wallet()
    lock: threading.Lock = threading.Lock()

    # -----------------------------------------------------------------------
    # 4. Wire up the stats reader + watcher
    # -----------------------------------------------------------------------
    baseline_snap = TokenSnapshot(
        output_tokens=game_state.baseline_tokens.output_tokens,
        cache_read_tokens=game_state.baseline_tokens.cache_read_tokens,
        cache_creation_tokens=game_state.baseline_tokens.cache_creation_tokens,
    )
    # THE PET LIVES ONLY WHILE THE WINDOW IS OPEN. Two re-anchors, and they
    # are the same idea applied to the two clocks:
    #
    #   * The baseline is moved to the CURRENT snapshot on every launch, so
    #     tokens spent while TokenGotchi was closed are not credited. You earn
    #     while the pet is watching, and not otherwise.
    #   * The creature's decay clock is moved to now, so hunger does not accrue
    #     while the app is shut. This is what makes an aggressive 3h bar
    #     survivable at all — without it, closing the laptop overnight would
    #     guarantee a dormant pet every single morning.
    #
    # The pair has to move together. Crediting offline tokens while not
    # charging offline hunger would be free money; charging offline hunger
    # without offline earning would be unpayable rent.
    if not is_first:
        try:
            _anchor = StatsReader(_stats_path).read_snapshot()
            baseline_snap = _anchor
            game_state.baseline_tokens = BaselineTokens(
                output_tokens=_anchor.output_tokens,
                cache_read_tokens=_anchor.cache_read_tokens,
                cache_creation_tokens=_anchor.cache_creation_tokens,
            )
            logger.info("Session anchor: offline tokens not credited.")
        except Exception as exc:
            logger.warning("Could not re-anchor baseline on launch: %s", exc)
    creature.last_hunger_update = datetime.now(timezone.utc)
    game_state.rates.period_start = raterules.period_start(
        datetime.now(timezone.utc))

    # A zeroed baseline on a non-first launch means the v1→v2 currency-reset
    # migration just cleared it. Re-anchor against the current snapshot before
    # the watcher starts, or the player's entire pre-existing token history is
    # credited as freshly earned and the reset undoes itself on the first fire.
    if not is_first and baseline_snap.total_cache_tokens == 0 and baseline_snap.output_tokens == 0:
        try:
            _probe = StatsReader(_stats_path)
            _now_snap = _probe.read_snapshot()
            baseline_snap = _now_snap
            game_state.baseline_tokens = BaselineTokens(
                output_tokens=_now_snap.output_tokens,
                cache_read_tokens=_now_snap.cache_read_tokens,
                cache_creation_tokens=_now_snap.cache_creation_tokens,
            )
            manager.save(game_state)
            logger.info("Currency reset: baseline re-anchored to current token snapshot.")
        except Exception as exc:
            logger.warning("Could not re-anchor baseline after reset: %s", exc)

    reader = StatsReader(_stats_path, baseline=baseline_snap)
    on_update = _make_on_update(wallet, app, lock, manager, reader)
    watcher = StatsWatcher(reader, on_update=on_update)  # type: ignore[arg-type]

    watcher_started = False
    if not stats_missing and schema_error is None:
        try:
            watcher.start()
            watcher_started = True
        except Exception as exc:
            logger.warning("Could not start StatsWatcher: %s", exc)

    # -----------------------------------------------------------------------
    # 5. Build window
    # -----------------------------------------------------------------------
    if window is None:
        window = _build_game_window()

    # -----------------------------------------------------------------------
    # 6. Main loop — 30 fps
    # -----------------------------------------------------------------------
    try:
        while not window.should_quit():  # type: ignore[union-attr]
            now = datetime.now(timezone.utc)

            with lock:
                # Sync latest domain state onto game_state before render
                game_state.apply_creature(creature)
                game_state.apply_wallet(wallet)

            # Every window implementation accepts the same keywords, so they
            # are passed directly. Do NOT filter them through
            # inspect.signature(): that is reflection in the hot loop, and a
            # silent-failure surface — rename a parameter and the argument is
            # quietly dropped with no error.
            actions: list[str] = window.render_frame(  # type: ignore[union-attr]
                game_state,
                show_privacy=app.show_privacy,
                stats_missing=stats_missing,
                schema_error=schema_error,
            )

            with lock:
                prev_stage = creature.stage
                for action in actions:
                    verb, _, arg = action.partition(":")
                    if action == "feed":
                        # Spend a full portion when affordable, otherwise
                        # everything down to the 3-BIT floor. Without the
                        # fallback a new player holding 3-14 BITS could not
                        # feed at all.
                        spend = FEED_COST if wallet.bits >= FEED_COST else wallet.bits
                        if spend >= BITS_PER_FEED:
                            feed(creature, wallet, bits_to_spend=spend)
                        app.mark_dirty()
                    elif verb == "buy":
                        purchase(wallet, game_state.inventory, arg)
                        app.mark_dirty()
                    elif verb == "equip":
                        equip(creature, game_state.inventory, arg)
                        app.mark_dirty()
                    elif verb == "shell":
                        equip_shell(game_state, game_state.inventory,
                                    arg or None)
                        app.mark_dirty()
                    elif verb == "screen":
                        # "screen:<id>" fits a skin, "screen:" clears it
                        equip_screen(game_state, game_state.inventory,
                                     arg or None)
                        app.mark_dirty()
                    elif action == "unequip":
                        unequip(creature)
                        app.mark_dirty()
                    elif action == "privacy_ok":
                        app.show_privacy = False
                    elif action.startswith("eat:"):
                        food_id = action.split(":", 1)[1]
                        hunger_before = creature.hunger
                        if feed_item(creature, wallet, food_id):
                            window.start_eat_animation(
                                food_id, hunger_before, creature.hunger)
                        app.mark_dirty()

                _tick_rates(game_state, creature, now)
                creature.apply_time_decay(now, game_state.rates.drain_mult)
                creature.check_dormancy(now)
                creature.check_stage_advance(app.lifetime_bits_earned, now)
                if creature.stage is not prev_stage:
                    app.mark_dirty()

                game_state.apply_creature(creature)
                game_state.apply_wallet(wallet)
                game_state.lifetime_bits_earned = app.lifetime_bits_earned

            # Persist on change, or on a slow heartbeat — NOT every frame.
            #
            # Saving unconditionally at 30fps costs ~30 JSON serialisations
            # plus temp-file write-and-rename per second, about 2.6M temp
            # files a day, for a 648-byte file. Measured at 3.92ms against
            # 0.92ms for the entire render — four times the cost of drawing
            # the game. It also multiplies exposure to the Windows rename
            # race guarded in StateManager.save() by roughly a hundredfold.
            #
            # Hunger is safe to persist lazily: apply_time_decay() recomputes
            # from the stored last_hunger_update, so a stale file self-corrects
            # on load rather than losing progress.
            if app.should_save(time.monotonic()):
                try:
                    manager.save(game_state)
                    app.mark_saved(time.monotonic())
                except Exception as exc:
                    logger.warning("State save failed: %s", exc)

            window.tick(FPS)  # type: ignore[union-attr]

    finally:
        if watcher_started:
            watcher.stop()
        # Always flush on the way out, whatever the dirty flag says — this is
        # the write that makes lazy persistence safe.
        try:
            with lock:
                game_state.apply_creature(creature)
                game_state.apply_wallet(wallet)
                game_state.lifetime_bits_earned = app.lifetime_bits_earned
                manager.save(game_state)
        except Exception as exc:
            logger.warning("Final state save failed: %s", exc)


def _tick_rates(game_state, creature, now) -> None:
    """Recompute the multipliers when a 6h slot boundary has passed.

    THE ORDER IN HERE IS THE WHOLE FUNCTION. Hunger burned before the boundary
    must be charged at the OLD appetite, so the creature is flushed up to the
    boundary first and only then does the new multiplier get installed.
    Swapping first would retroactively re-price hunger that was already spent —
    the same shape of error as a baseline that never advances, which inflates
    currency by ~190x.
    """
    r = game_state.rates
    slot = raterules.period_start(now)
    if r.period_start is not None and slot <= r.period_start:
        return                      # already computed for this slot

    creature.apply_time_decay(slot, r.drain_mult)

    new = raterules.compute(game_state.usage_history, r.earn_mult,
                            r.drain_mult, r.last_token_at, now)
    r.prev_earn_mult, r.prev_drain_mult = r.earn_mult, r.drain_mult
    r.earn_mult, r.drain_mult = new.earn, new.drain
    r.baseline_output_per_day = new.baseline
    r.resting, r.calibrating = new.resting, new.calibrating
    r.period_start = slot
    r.history.append(RatePoint(at=slot, earn=new.earn, drain=new.drain))
    del r.history[:-raterules.HISTORY_CAP]


# The guard is required by the PyInstaller build, which analyses THIS FILE as
# a script (see tokengotchi.spec) rather than going through the console-script
# entry point in pyproject.toml. Without it the frozen exe imports the module,
# defines these functions and exits — silently, because the spec sets
# console=False.
#
# Keep this call the LAST statement in the file. Run as a script the module
# body executes top to bottom, so main() must not be invoked above any
# function it reaches at runtime (_tick_rates is called from the render loop).
# The console-script path imports main() and calls it after the whole module
# has been defined, so an ordering mistake here is invisible from source and
# only surfaces in the frozen exe.
if __name__ == "__main__":
    main()
