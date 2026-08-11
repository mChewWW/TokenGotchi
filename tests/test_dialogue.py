"""Dialogue system: hunger-band parity, shuffle-bag repeat avoidance, and the
DialoguePanel's non-blocking lifecycle. Direction contract v11, extended by
v17 (context gating, event lines, the timer-burn fix)."""
from __future__ import annotations

import ast
import inspect
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from tokengotchi.dialogue import context as ctx_mod
from tokengotchi.dialogue import scheduler as sched_mod
from tokengotchi.dialogue.context import (
    context_pool,
    resolve_context,
    tone_group,
)
from tokengotchi.dialogue.context_lines import CONTEXT_LINES
from tokengotchi.dialogue.lines import LINES
from tokengotchi.dialogue.scheduler import DialogueScheduler
from tokengotchi.engine.actions import BITS_PER_FEED, FEED_COST
from tokengotchi.engine.creature import HUNGER_BANDS, hunger_state
from tokengotchi.renderer import sprites
from tokengotchi.renderer.dialogue_panel import DialoguePanel

# A fixed clock: every context assertion below is about an AGE, so the "now"
# it is measured against must not drift with the test run.
NOW = datetime(2026, 8, 7, 4, 0, 0, tzinfo=timezone.utc)


def _ago(hours: float) -> datetime:
    return NOW - timedelta(hours=hours)


def _ctx(hunger: float, bits: int, hours_ago: float | None) -> str | None:
    return resolve_context(
        hunger=hunger, bits=bits,
        last_token_at=None if hours_ago is None else _ago(hours_ago),
        now=NOW,
    )


# ── Single source of truth for hunger bands ─────────────────────────────────

def test_hunger_state_thresholds():
    assert hunger_state(100) == "healthy"
    assert hunger_state(75) == "healthy"
    assert hunger_state(74.9) == "sad"
    assert hunger_state(50) == "sad"
    assert hunger_state(49.9) == "distressed"
    assert hunger_state(25) == "distressed"
    assert hunger_state(24.9) == "horror"
    assert hunger_state(10) == "horror"
    assert hunger_state(9.9) == "dying"
    assert hunger_state(0) == "dying"


def test_sprites_reuses_the_same_function_object():
    """sprites.py must never define its own copy of the hunger ladder."""
    assert sprites._hunger_state is hunger_state


def test_lines_bands_match_engine_bands():
    assert set(LINES.keys()) == set(HUNGER_BANDS)
    for band, lines in LINES.items():
        assert len(lines) > 0, f"{band} has no lines"


# ── Context gating (contract v17 Layer 2) ───────────────────────────────────

def test_the_reported_defect_no_longer_selects_a_general_line():
    """The human's live save, reproduced field for field.

    hunger 43.07 (band `distressed`), wallet.bits 1358, last token 1.4h ago.
    The old selector reached for `LINES['distressed']`, half of which asserted
    the player had gone silent — while they were, at that moment, working.
    The gate must now resolve the one claim that is actually provable here:
    they can afford to feed and have not.
    """
    assert _ctx(43.07, 1358, 1.4) == "hoarding"


def test_never_accuses_a_player_with_no_recorded_activity():
    """`last_token_at is None` is a fresh install or a forward-migrated save.

    It is NOT 48 hours of silence, and guessing wrong means accusing somebody
    who has not yet had the chance to do anything. Falls through to the
    general pool at every band and every balance.
    """
    for hunger in (100.0, 60.0, 43.0, 15.0, 0.0):
        for bits in (0, FEED_COST - 1, FEED_COST, 5000):
            assert _ctx(hunger, bits, None) is None


def test_deep_silence_outranks_an_unspent_balance():
    """From `drought` (4h) up, the silence is the bigger story than the wallet.

    Ladder re-timed by the human 2026-08-07 from four rungs to six:
    abandoned 12h, deep_drought 6h, drought 4h.
    """
    assert _ctx(43.0, 1358, 60) == "abandoned"        # a week away is still 12h+
    assert _ctx(43.0, 1358, 13) == "abandoned"
    assert _ctx(43.0, 1358, 7) == "deep_drought"
    assert _ctx(43.0, 1358, 5) == "drought"


def test_hoarding_outranks_the_attention_tiers_but_not_the_blaming_ones():
    """Where the wallet beats the clock, and where it stops.

    `hoarding` is true whenever a feed is affordable, which for a habitual
    user is essentially always. If it outranked the blaming rungs it would
    swallow the graded ladder whole at every band below `healthy` — measured
    on the live save (1358 BITS) it won every cell from 29 minutes to six
    hours. So it beats the attention-only rungs (lull/quiet/restless) and
    yields to the ones permitted to blame (drought and deeper).
    """
    assert _ctx(43.0, BITS_PER_FEED, 0.6) == "hoarding"   # over `lull`
    assert _ctx(43.0, BITS_PER_FEED, 1.5) == "hoarding"   # over `quiet`
    assert _ctx(43.0, BITS_PER_FEED, 3.0) == "hoarding"   # over `restless`
    assert _ctx(43.0, BITS_PER_FEED, 5) == "drought"      # yields to `drought`


def test_affordability_is_the_partial_feed_floor_not_the_full_feed_cost():
    """`main.py` feeds with whatever is left once it clears `BITS_PER_FEED`.

    `spend = FEED_COST if bits >= FEED_COST else bits; if spend >=
    BITS_PER_FEED` (main.py) — so the FEED button genuinely works from 3 BITS
    up, not from 15. Gating the wallet split on `FEED_COST` told everyone
    holding 3-14 BITS "you can't afford me yet" while the button in front of
    them worked, and withheld `hoarding` from a window where one click really
    did fix it. Both halves were false.
    """
    assert BITS_PER_FEED < FEED_COST, "the gap this test exists for is gone"
    for bits in range(BITS_PER_FEED, FEED_COST):
        assert _ctx(43.0, bits, 0.9) == "hoarding", bits
    # Genuinely unable to feed: below the partial-feed floor. Inside the `lull`
    # window, since `earning` now also needs evidence of recent work.
    assert _ctx(43.0, BITS_PER_FEED - 1, 0.4) == "earning"


def test_earning_needs_poverty_and_recent_work():
    assert _ctx(43.0, BITS_PER_FEED - 1, 0.4) == "earning"
    # Sympathy is gated on EVIDENCE of work, not merely on "no drought" — the
    # pool asserts the player is earning right now, and only a fresh
    # `last_token_at` proves that. Past the `lull` window it must yield.
    assert _ctx(43.0, BITS_PER_FEED - 1, 1.5) == "quiet"
    assert _ctx(43.0, BITS_PER_FEED - 1, 5) == "drought"


def test_a_healthy_pet_accuses_nobody_of_starving_it():
    """Only the ladder tiers may fire at `healthy` (contract v17).

    `hoarding` and `earning` are both claims about needing food. A pet at 75%+
    hunger has none to make, however the wallet looks.
    """
    for bits in (0, FEED_COST - 1, FEED_COST, 5000):
        for hours in (0.1, 0.6, 5, 13, 60):
            assert _ctx(100.0, bits, hours) in (
                None, "lull", "drought", "deep_drought", "abandoned")


def test_a_resolved_context_always_has_lines_to_speak():
    """The empty-pool guard, swept across the whole reachable grid.

    Load-bearing rather than paranoid: `hoarding` and `earning` exist only in
    the `hungry` tone group, so at `sad` — which groups with `fed` — they are
    unreachable and something else must take the frame. A gate that returned
    them anyway would hand the scheduler a guaranteed silence.
    """
    for hunger in (100.0, 80.0, 60.0, 43.0, 20.0, 5.0, 0.0):
        for bits in (0, 1, FEED_COST - 1, FEED_COST, 1358):
            for hours in (0.0, 0.4, 0.51, 3.9, 4.0, 11.9, 12.0, 47.9, 48.0):
                c = _ctx(hunger, bits, hours)
                if c is None:
                    continue
                pool = context_pool(c, hunger_state(hunger))
                assert pool, f"{c} @ {hunger_state(hunger)} resolved but empty"


def test_context_pools_meet_the_line_floor():
    """Contract v17 constraint 1: ~10 lines per reachable (band, context).

    Below that floor a gated pool repeats itself inside one sitting, which is
    the failure mode the general pool's 30-line bands exist to avoid.
    """
    reachable: set[tuple[str, str]] = set()
    for hunger in (100.0, 60.0, 43.0, 20.0, 5.0):
        for bits in (0, FEED_COST - 1, FEED_COST, 1358):
            for hours in (0.6, 5, 13, 60):
                c = _ctx(hunger, bits, hours)
                if c is not None:
                    reachable.add((c, tone_group(hunger_state(hunger))))
    assert reachable, "gate resolves nothing — the sweep is broken, not the content"
    for context, group in sorted(reachable):
        pool = CONTEXT_LINES[context][group]
        assert len(pool) >= 10, f"{context}/{group} has only {len(pool)} lines"


def test_tone_group_is_coarse_by_design():
    assert tone_group("healthy") == "fed"
    assert tone_group("sad") == "fed"
    for band in ("distressed", "horror", "dying"):
        assert tone_group(band) == "hungry"


def test_dialogue_tiers_are_independent_of_the_appetite_economy():
    """Contract v17 constraint 5: retuning hunger must not retune the writing.

    `engine/rates.py` owns REST_HOURS and friends for the appetite economy. If
    this module imported them, changing how fast the pet gets hungry would
    silently change what it is willing to accuse the player of.
    """
    tree = ast.parse(inspect.getsource(ctx_mod))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("rates" in m for m in imported), imported
    # The six-rung ladder resolved by the human 2026-08-07.
    assert ctx_mod.DIALOGUE_LULL_MINUTES == 30.0
    assert ctx_mod.DIALOGUE_QUIET_HOURS == 1.0
    assert ctx_mod.DIALOGUE_RESTLESS_HOURS == 2.0
    assert ctx_mod.DIALOGUE_DROUGHT_HOURS == 4.0
    assert ctx_mod.DIALOGUE_DEEP_DROUGHT_HOURS == 6.0
    assert ctx_mod.DIALOGUE_ABANDONED_HOURS == 12.0
    # The rungs must stay strictly ordered, or a deeper tier is unreachable.
    thresholds = [t for _, t in ctx_mod._LADDER]
    assert thresholds == sorted(thresholds, reverse=True), ctx_mod._LADDER


def test_a_broken_clock_is_not_evidence_of_silence():
    """A future `last_token_at` (skew, a save copied between machines, a hand
    edit) must read as "just now", and a naive datetime out of a hand-edited
    save must not raise inside the render loop."""
    assert resolve_context(hunger=100.0, bits=0,
                           last_token_at=NOW + timedelta(hours=9),
                           now=NOW) is None
    # Naive, and exactly 24h before NOW once read as UTC — past the 12h rung.
    assert resolve_context(hunger=43.0, bits=0,
                           last_token_at=datetime(2026, 8, 6, 4, 0, 0),
                           now=NOW) == "abandoned"


# ── Scheduler: cadence + repeat avoidance ───────────────────────────────────

def test_scheduler_fires_after_interval(monkeypatch):
    monkeypatch.setattr(sched_mod.random, "uniform", lambda a, b: 1.0)
    s = DialogueScheduler()
    assert s.update(0.5, "healthy", True) is None
    line = s.update(0.5, "healthy", True)
    assert line in LINES["healthy"]


def test_scheduler_paused_while_not_allowed(monkeypatch):
    monkeypatch.setattr(sched_mod.random, "uniform", lambda a, b: 1.0)
    s = DialogueScheduler()
    for _ in range(100):
        assert s.update(0.5, "healthy", False) is None
    # Nothing accumulated while paused; still needs the full interval.
    assert s.update(0.9, "healthy", True) is None
    assert s.update(0.1, "healthy", True) is not None


def test_scheduler_paused_while_dialogue_pinned_open(monkeypatch):
    """Contract v12 point 3: "pause, don't queue".

    `window.py` no longer calls `update()` unconditionally once the previous
    popup is dismissed on its own timer — a pinned popup (`is_open` staying
    True indefinitely, per contract v12) must ALSO suppress new triggers, on
    top of the existing egg/dormant/FOOD/SHOP/RATES gate. This is simulated
    here with a stand-in exposing `is_open`, mirroring how `window.py`
    computes its `dialogue_ok = self._dialogue_visible(...) and not
    self._dialogue.is_open` gate, without needing a real `GameWindow`.
    """
    monkeypatch.setattr(sched_mod.random, "uniform", lambda a, b: 1.0)
    s = DialogueScheduler()

    class _Pinned:
        is_open = True

    dialogue = _Pinned()
    # Time keeps passing well past the interval, but a still-pinned popup
    # keeps suppressing the trigger indefinitely -- no eventual fire, and
    # (per the scheduler's own "pause, don't accumulate" contract) nothing
    # is silently queued up behind the scenes either.
    for _ in range(50):
        assert s.update(1.0, "healthy", not dialogue.is_open) is None

    # Once dismissed, the clock -- having never accumulated while paused --
    # still needs the full interval from here; dismissing does not dump an
    # immediate backlogged trigger.
    dialogue.is_open = False
    assert s.update(0.9, "healthy", not dialogue.is_open) is None
    assert s.update(0.2, "healthy", not dialogue.is_open) is not None


def test_scheduler_silent_for_unknown_band(monkeypatch):
    monkeypatch.setattr(sched_mod.random, "uniform", lambda a, b: 0.1)
    s = DialogueScheduler()
    assert s.update(1.0, "nonexistent-band", True) is None


def test_bag_never_immediately_repeats():
    from tokengotchi.dialogue.scheduler import _BandBag

    bag = _BandBag(("a", "b"))
    seen = [bag.draw() for _ in range(40)]
    for prev, nxt in zip(seen, seen[1:]):
        assert prev != nxt


def test_bag_exhausts_before_repeating():
    from tokengotchi.dialogue.scheduler import _BandBag

    lines = ("a", "b", "c", "d", "e")
    bag = _BandBag(lines)
    first_pass = {bag.draw() for _ in range(len(lines))}
    assert first_pass == set(lines)


def test_bag_is_silent_when_empty():
    from tokengotchi.dialogue.scheduler import _BandBag

    bag = _BandBag(())
    assert bag.draw() is None


# ── DialoguePanel: non-blocking auto-dismiss lifecycle ──────────────────────

@pytest.fixture(scope="module", autouse=True)
def _pygame_video():
    pygame.init()
    pygame.display.set_mode((10, 10))
    yield
    pygame.quit()


def test_panel_ignores_empty_text():
    p = DialoguePanel()
    p.show("", "healthy", stage="baby", hunger=80.0, hat=None, frame=0)
    assert not p.is_open


def test_panel_holds_open_until_dismissed_by_click():
    """Contract v12: `_HELD` no longer auto-advances to `_OUT` on a timer.

    Once the typewriter reveal finishes, the popup must stay open (pinned)
    for an unbounded amount of time — only a click (via `handle_event`)
    dismisses it. A large cumulative `update(dt)` that would have blown well
    past the old `HOLD_AFTER_REVEAL_S` timeout must NOT close it.
    """
    p = DialoguePanel()
    p.show("Hi", "healthy", stage="baby", hunger=80.0, hat=None, frame=0)
    assert p.is_open
    for _ in range(2000):
        p.update(0.05)  # 100s cumulative — far beyond any old hold timer
    assert p.is_open


def test_panel_draw_is_a_noop_when_closed():
    p = DialoguePanel()
    surf = pygame.Surface((348, 250))
    before = surf.copy()
    p.draw(surf)
    assert surf.get_buffer().raw == before.get_buffer().raw


def test_panel_freezes_pose_at_show_not_at_draw():
    """Feeding mid-popup must not retroactively change the shown portrait.

    `draw()` takes no live stage/hunger/hat/frame args at all — the only way
    those change is another `show()` call, which this test never makes.
    """
    p = DialoguePanel()
    p.show("Hi", "dying", stage="baby", hunger=5.0, hat=None, frame=0)
    assert p._hunger == 5.0 and p._stage == "baby"
    surf = pygame.Surface((348, 250))
    p.draw(surf)  # no hunger/stage args accepted; nothing to desync
    assert p._hunger == 5.0 and p._stage == "baby"


def test_panel_adult_stage_draws_without_error():
    p = DialoguePanel()
    p.show("Hi", "healthy", stage="adult", hunger=80.0, hat=None, frame=0)
    surf = pygame.Surface((348, 250))
    p.draw(surf)
    assert p.is_open
