"""Event-driven dialogue — direction contract v17, Layer 3.

The whole of v17's event path shipped with zero automated coverage: an
adversarial review found that deleting the `if` around `purchase(...)` in
`main.py` would still have passed the entire suite. Every test here defends
one named constraint of that contract against exactly that class of silent
regression.

Where a constraint lives in `main.py`'s action loop (constraints 4 and 7, and
the human's "equipping stays silent" decision) the test drives the REAL loop
via `main()` with a scripted window double, so the gate being tested is the
production `if`, not a re-implementation of it. Where it lives in `window.py`
(constraints 2 and 3, the starving diversion, the generic fallback) the test
drives a REAL `GameWindow`. Only the pure selection constraints (6 and the
`_select` mix) are exercised against `DialogueScheduler` directly, because
that is where they live.
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from tokengotchi.dialogue import scheduler as sched_mod
from tokengotchi.dialogue.context import resolve_context, tone_group
from tokengotchi.dialogue.context_lines import CONTEXT_LINES
from tokengotchi.dialogue.event_lines import PURCHASE_LINES
from tokengotchi.dialogue.lines import LINES
from tokengotchi.dialogue.moment_lines import MOMENT_LINES
from tokengotchi.dialogue.scheduler import CONTEXT_BIAS, DialogueScheduler
from tokengotchi.engine.creature import Stage, hunger_state
from tokengotchi.engine.state_manager import (
    CreatureState,
    GameState,
    StateManager,
    WalletState,
)
from tokengotchi.main import _HeadlessWindow, main
from tokengotchi.renderer import shop_panel as shoppanel
from tokengotchi.renderer import uikit as uikit_mod
from tokengotchi.renderer import window as win_mod
from tokengotchi.renderer.window import GameWindow
from tokengotchi.shop import catalogue as shopcat

# A fixed clock for the context sweep: every assertion below is about an AGE,
# so the "now" it is measured against must not drift with the test run.
NOW = datetime(2026, 8, 7, 4, 0, 0, tzinfo=timezone.utc)

# Real catalogue ids, one per cosmetic ItemKind. Named here rather than
# inlined so a catalogue rename is one edit and an obvious failure.
HAT_ID = "hat_cap"
SCREEN_ID = "screen_amber"
SHELL_ID = "shell_graphite"
FIELD_ID = "field_snow"


# ── Harness: the real main() loop, driven by a scripted window ──────────────


class _ScriptedWindow(_HeadlessWindow):
    """A window double that plays a fixed script of per-frame action lists.

    Subclasses `_HeadlessWindow` so it carries the same interface `main()`
    expects, and RECORDS the two v17 dialogue hooks instead of drawing them.
    The point is to test `main.py`'s gating — the `bool` check around
    `purchase()`, the DORMANT/EGG/BABY discrimination in `_note_stage_change`,
    and the deliberate silence of the equip verbs — with the real loop, real
    `Creature` and real `Wallet` doing the work.
    """

    def __init__(self, script: list[list[str]]) -> None:
        super().__init__()
        self._script = [list(frame) for frame in script]
        self._frame = 0
        self.purchases: list[tuple[str, float, bool]] = []
        self.moments: list[str] = []
        self.seen: list[dict] = []

    def should_quit(self) -> bool:
        return self._frame >= len(self._script)

    def render_frame(self, game_state, **kwargs) -> list[str]:
        self.seen.append({
            "stage": game_state.creature.stage,
            "hat_slot": game_state.creature.hat_slot,
            "screen_slot": game_state.screen_slot,
            "shell_slot": game_state.shell_slot,
            "field_slot": game_state.field_slot,
            "inventory": list(game_state.inventory),
        })
        actions = self._script[self._frame]
        self._frame += 1
        return list(actions)

    def note_purchase(self, item_id: str, *, hunger: float,
                      first_of_kind: bool) -> None:
        self.purchases.append((item_id, hunger, first_of_kind))

    def note_moment(self, key: str) -> None:
        self.moments.append(key)

    def start_eat_animation(self, food_id, hunger_before, hunger_after) -> None:
        pass


def _run_main(tmp_path: Path, state: GameState,
              script: list[list[str]]) -> tuple[_ScriptedWindow, GameState]:
    """Save `state`, run the REAL main loop over `script`, reload from disk.

    `stats_path` deliberately points at a file (and a `projects/` tree) that
    does not exist, so `_has_claude_data` is False, `stats_missing` is True and
    `StatsWatcher` is never started — no background thread, no wall-clock
    dependency, no token credits arriving mid-test.
    """
    state_path = tmp_path / "state.json"
    stats_path = tmp_path / "claude_home" / "stats-cache.json"
    StateManager(state_path=state_path).save(state)

    window = _ScriptedWindow(script)
    main(state_path=state_path, stats_path=stats_path, window=window)
    return window, StateManager(state_path=state_path).load()


def _state(*, stage: str = "BABY", hunger: float = 100.0, bits: int = 0,
           echoes: int = 0, inventory: list[str] | None = None,
           lifetime_bits: int = 0,
           feeding_log: list[str] | None = None,
           pre_dormant_stage: str | None = None,
           dormancy_start: datetime | None = None) -> GameState:
    return GameState(
        creature=CreatureState(
            stage=stage,
            hunger=hunger,
            daily_feeding_log=list(feeding_log or []),
            pre_dormant_stage=pre_dormant_stage,
            dormancy_start=dormancy_start,
        ),
        wallet=WalletState(bits=bits, echoes=echoes),
        inventory=list(inventory or []),
        lifetime_bits_earned=lifetime_bits,
    )


# ── Harness: a real GameWindow ─────────────────────────────────────────────


@pytest.fixture
def window():
    """A real `GameWindow` on the dummy SDL video driver.

    `uikit._font_cache` is a process-wide dict keyed on (size, bold) that
    survives a pygame.quit()/init() cycle holding Font objects tied to a
    destroyed font subsystem; reusing one segfaults rather than raising. It is
    cleared here for the same reason `test_dialogue_window_integration.py`
    clears it.
    """
    uikit_mod._font_cache.clear()
    pygame.init()
    w = GameWindow()
    try:
        yield w
    finally:
        w.close()
        pygame.quit()


def _window_state(hunger: float = 100.0) -> GameState:
    """A hatched, non-dormant creature — the only state dialogue speaks in."""
    return GameState(creature=CreatureState(stage="BABY", hunger=hunger))


def _silence_ambient(window, monkeypatch) -> None:
    """Pin the ambient interval far in the future.

    The scheduler is rebuilt AFTER the patch because `GameWindow.__init__`
    already drew its first interval from the real `random.uniform`.
    """
    monkeypatch.setattr(sched_mod.random, "uniform", lambda a, b: 999999.0)
    window._dialogue_scheduler = DialogueScheduler()


# ═══ 1. CONSTRAINT 4 — a purchase line requires a SUCCESSFUL purchase ══════


def test_failed_purchase_never_speaks_and_never_mutates_inventory(tmp_path):
    """Contract v17 constraint 4: the hook fires only on a confirmed success.

    `main.py` reads `purchase()`'s `bool` before calling `note_purchase`.
    Dropping that check — the reviewer's exact mutation, "deleting the `if`
    around `purchase(...)`" — would congratulate the player on a purchase
    that never happened. All three of `purchase()`'s failure modes are driven
    through the real loop here: an unaffordable item, an already-owned item,
    and an id that is not in the catalogue at all.
    """
    price = shopcat.get(HAT_ID).cost

    # (a) Insufficient ECHOES.
    win, saved = _run_main(
        tmp_path / "poor",
        _state(echoes=price - 1),
        [[f"buy:{HAT_ID}"]],
    )
    assert win.purchases == [], "an unaffordable buy must not speak"
    assert saved.inventory == []
    assert saved.wallet.echoes == price - 1, "no charge on a failed buy"

    # (b) Already owned — purchase() refuses and charges nothing.
    win, saved = _run_main(
        tmp_path / "owned",
        _state(echoes=price * 3, inventory=[HAT_ID]),
        [[f"buy:{HAT_ID}"]],
    )
    assert win.purchases == [], "re-buying an owned item must not speak"
    assert saved.inventory == [HAT_ID]
    assert saved.wallet.echoes == price * 3

    # (c) An id that is not in the catalogue.
    win, saved = _run_main(
        tmp_path / "unknown",
        _state(echoes=price * 3),
        [["buy:not_a_real_item_id"]],
    )
    assert win.purchases == [], "an unknown id must not speak"
    assert saved.inventory == []
    assert saved.wallet.echoes == price * 3


def test_successful_purchase_speaks_exactly_once(tmp_path):
    """Contract v17 constraint 4, the other direction.

    A genuine buy must produce exactly ONE hook call, carrying the item id,
    the hunger at the instant of the purchase, and `first_of_kind` computed
    BEFORE `purchase()` appended to the inventory (asking afterwards always
    answers "already owned").
    """
    price = shopcat.get(HAT_ID).cost
    win, saved = _run_main(
        tmp_path,
        _state(hunger=90.0, echoes=price),
        [[f"buy:{HAT_ID}"]],
    )

    assert len(win.purchases) == 1, win.purchases
    item_id, hunger, first_of_kind = win.purchases[0]
    assert item_id == HAT_ID
    assert first_of_kind is True, (
        "first_of_kind must be read before purchase() mutates the inventory"
    )
    assert 80.0 < hunger <= 90.0, hunger
    assert saved.inventory == [HAT_ID]
    assert saved.wallet.echoes == 0


def test_second_item_of_a_kind_is_not_first_of_kind(tmp_path):
    """Contract v17 constraint 4's companion: `_owns_kind` is by ItemKind.

    Owning a hat already means a second hat is not a milestone — the pool
    precedence in `note_purchase` depends on this flag being honest.
    """
    second = "hat_beanie"
    price = shopcat.get(second).cost
    win, _ = _run_main(
        tmp_path,
        _state(echoes=price, inventory=[HAT_ID]),
        [[f"buy:{second}"]],
    )
    assert len(win.purchases) == 1
    assert win.purchases[0][0] == second
    assert win.purchases[0][2] is False


# ═══ 2. CONSTRAINT 2 — deferral to shop-close, and coalescing ══════════════


def test_purchases_are_deferred_while_the_shop_is_open_and_coalesce(
        window, monkeypatch):
    """Contract v17 constraint 2: park the line, deliver it on shop-close.

    The shop is open at the instant of purchase and `_dialogue_visible` is
    False while it is, so a line shown then is drawn to nobody. Several
    purchases in one shopping trip must therefore produce NO visible dialogue
    at all, and then exactly ONE line once the shop closes — the line for the
    MOST RECENT purchase, because the window holds one pending event, not a
    queue ("pause, don't queue"; three popups fired back-to-back is a
    notification backlog, not a pet).
    """
    _silence_ambient(window, monkeypatch)
    state = _window_state()

    shows: list[str] = []
    real_show = window._dialogue.show

    def spy_show(text, *a, **kw):
        shows.append(text)
        real_show(text, *a, **kw)

    window._dialogue.show = spy_show

    window.render_frame(state)          # one frame so the rects are sized
    assert shows == []

    window._shop.open((100, 100))
    assert window._shop.is_open

    for item_id in (HAT_ID, SCREEN_ID, FIELD_ID):
        window.note_purchase(item_id, hunger=100.0, first_of_kind=False)
        window.render_frame(state)

    assert shows == [], (
        "no dialogue may be shown while the shop covers the popup"
    )
    assert not window._dialogue.is_open
    assert window._pending_event in PURCHASE_LINES["field"], (
        "the parked line must be the most recent purchase's, not the first"
    )

    # Close the shop outright — its own closing animation is ShopPanel's
    # concern, not what this test is about.
    window._shop.phase = shoppanel.Phase.CLOSED
    assert not window._shop.is_open

    window.render_frame(state)
    assert len(shows) == 1, "exactly one line on the frame the shop closes"
    assert shows[0] in PURCHASE_LINES["field"], shows[0]
    assert shows[0] not in PURCHASE_LINES["hat"]
    assert shows[0] not in PURCHASE_LINES["screen"]
    assert window._pending_event is None, "the parked line must be consumed"

    # And it is delivered once, not on every subsequent frame.
    for _ in range(5):
        window.render_frame(state)
    assert len(shows) == 1


def test_an_empty_pool_does_not_silence_an_already_parked_line(window,
                                                              monkeypatch):
    """Contract v17 constraint 2, the coalescing edge.

    Coalescing to the most recent event must not be able to DELETE a line
    that was already earned: `_park` only overwrites when the new draw
    actually produced something. An unknown moment key (silence by design) is
    the reachable case.
    """
    _silence_ambient(window, monkeypatch)
    window.note_purchase(HAT_ID, hunger=100.0, first_of_kind=False)
    parked = window._pending_event
    assert parked in PURCHASE_LINES["hat"]

    window.note_moment("a_moment_that_has_no_pool")
    assert window._pending_event == parked


def test_a_parked_hatch_survives_a_later_purchase(window, monkeypatch):
    """Contract v18 bug fix: the creature's first words cannot be destroyed.

    `hatch`/`adult` fire once per save, ever. If the shop is open on the frame
    one of them parks, the single last-write-wins pending slot would let a
    repeatable purchase line overwrite it — and it would never fire again. The
    milestone is protected: a non-protected event landing on top of it is
    dropped, not the milestone.
    """
    _silence_ambient(window, monkeypatch)

    window.note_moment("hatch")
    parked = window._pending_event
    assert parked in MOMENT_LINES["hatch"], "the hatch line must park first"

    # A purchase (the exact real case: shop open when hatch fires) must not
    # evict it.
    window.note_purchase(HAT_ID, hunger=100.0, first_of_kind=False)
    assert window._pending_event == parked, (
        "a purchase overwrote the once-ever hatch line"
    )

    # Another milestone MAY still coalesce over it — that ordering is
    # deliberate elsewhere and not what this guard is about.
    window.note_moment("adult")
    assert window._pending_event in MOMENT_LINES["adult"]


# ═══ 3. CONSTRAINT 3 — event lines never flash; ambient lines still do ═════


def test_event_line_does_not_flash_the_taskbar(window, monkeypatch):
    """Contract v17 constraint 3: the event path must NOT flash.

    Every event line reacts to a click the player just made, so they are
    already looking at the window; a flash would be the app trying to attract
    attention it already has. This is asserted here rather than left to
    `flash_taskbar`'s own foreground guard, which is a best-effort platform
    check — relying on it would make correct behaviour an accident of Windows
    API availability.
    """
    _silence_ambient(window, monkeypatch)
    flashes: list[int] = []
    monkeypatch.setattr(win_mod, "flash_taskbar", lambda: flashes.append(1))

    state = _window_state()
    window.render_frame(state)
    assert flashes == []

    window.note_purchase(HAT_ID, hunger=100.0, first_of_kind=False)
    assert window._pending_event is not None

    window.render_frame(state)
    assert window._dialogue.is_open, "the parked line must actually be shown"
    assert window._dialogue._text in PURCHASE_LINES["hat"]
    assert flashes == [], "an event line must not flash the taskbar"


def test_ambient_line_still_flashes_the_taskbar(window, monkeypatch):
    """Contract v17 constraint 3, the other direction (contract v12 point 1).

    Silencing the flash on the event path must not silence it everywhere: an
    ambient line arrives unprompted and may well land while the window is in
    the background, which is the whole reason the flash exists.
    """
    monkeypatch.setattr(sched_mod.random, "uniform", lambda a, b: 0.0)
    window._dialogue_scheduler = DialogueScheduler()

    flashes: list[int] = []
    monkeypatch.setattr(win_mod, "flash_taskbar", lambda: flashes.append(1))

    state = _window_state()
    assert window._pending_event is None, "this must exercise the ambient path"

    window.render_frame(state)
    assert window._dialogue.is_open
    assert window._dialogue._text in LINES["healthy"]
    assert flashes == [1], "an ambient line must still flash the taskbar"


# ═══ 4. CONSTRAINT 7 — a wake from DORMANT is not a stage advance ══════════


def test_wake_from_dormancy_speaks_the_wake_line_not_a_hatch(tmp_path):
    """Contract v17 constraint 7: `stage is not prev_stage` is not an advance.

    `Creature.exit_dormancy` restores the pre-dormant stage on the feed that
    revives the pet, so DORMANT -> BABY trips exactly the same inequality a
    real EGG -> BABY hatch does. A hatch line gated on the bare comparison
    would fire on every single wake — the pet's first-words-ever pool, spoken
    to a player it has known for weeks.
    """
    win, saved = _run_main(
        tmp_path,
        _state(stage=Stage.DORMANT.value, hunger=0.0, bits=100,
               pre_dormant_stage=Stage.BABY.value),
        [["feed"]],
    )

    assert saved.creature.stage == Stage.BABY.value, (
        "the feed must really have woken the pet — otherwise this test is "
        "asserting silence about an edge it never reached"
    )
    assert "wake_dormant" in win.moments
    assert "hatch" not in win.moments, "a wake is not a hatch"
    assert "adult" not in win.moments, "a wake is not a stage advance"
    # The reviving feed's own line is parked first, so the wake COALESCES
    # over it: coming back from nothing is the bigger event of the two.
    assert win.moments == ["fed_hungry", "wake_dormant"], win.moments


def test_wake_from_dormancy_to_adult_is_also_not_an_advance(tmp_path):
    """Contract v17 constraint 7, the ADULT arm.

    `exit_dormancy` restores ADULT just as readily as BABY, so DORMANT ->
    ADULT is the second edge a bare comparison cannot tell from a real
    BABY -> ADULT advance.
    """
    win, saved = _run_main(
        tmp_path,
        _state(stage=Stage.DORMANT.value, hunger=0.0, bits=100,
               pre_dormant_stage=Stage.ADULT.value),
        [["feed"]],
    )
    assert saved.creature.stage == Stage.ADULT.value
    assert win.moments == ["fed_hungry", "wake_dormant"], win.moments


def test_a_real_hatch_still_speaks(tmp_path):
    """Contract v17 constraint 7's other half: real advances must NOT go mute.

    EGG -> BABY on `lifetime_bits_earned >= EGG_TO_BABY_BITS`, with no feed
    involved — the pure advance edge.
    """
    win, saved = _run_main(
        tmp_path,
        _state(stage=Stage.EGG.value, lifetime_bits=100),
        [[]],
    )
    assert saved.creature.stage == Stage.BABY.value
    assert win.moments == ["hatch"], win.moments
    assert MOMENT_LINES["hatch"], "the pool this defends must not be empty"


def test_a_real_adulthood_still_speaks(tmp_path):
    """Contract v17 constraint 7's other half: BABY -> ADULT must speak.

    `check_stage_advance` grants ADULT on seven DISTINCT days carrying a
    feeding, so the feed applied this frame is the seventh.

    Contract v18: the feed line that carries this advance is rarity-gated (a
    fresh session's first gated feed is below the pity FLOOR, so `fed_full` is
    silent here) but `adult` is NOT gated — a milestone earned over a week must
    never be discarded. The single surviving `adult` is exactly that guarantee.
    """
    today = datetime.now(timezone.utc).date()
    six_earlier = [(today - timedelta(days=i)).isoformat() for i in range(1, 7)]

    win, saved = _run_main(
        tmp_path,
        _state(stage=Stage.BABY.value, hunger=100.0, bits=100,
               feeding_log=six_earlier),
        [["feed"]],
    )
    assert saved.creature.stage == Stage.ADULT.value
    assert win.moments == ["adult"], win.moments


# ═══ 5. EQUIPPING STAYS SILENT (the human's explicit decision) ═════════════


def test_equipping_is_silent(tmp_path):
    """Contract v17 Open Question 3, resolved by the human: purchase only.

    `equip`/`equip_screen`/`equip_shell`/`equip_field` deliberately discard
    their `bool` return. That is a decision, not an oversight, so it needs a
    test: adding a hook to any of the four verbs must fail here. The equips
    are asserted to have actually LANDED, so the test cannot pass by the
    actions being silently dropped instead of silently applied.
    """
    inventory = [HAT_ID, SCREEN_ID, SHELL_ID, FIELD_ID]
    win, saved = _run_main(
        tmp_path,
        _state(inventory=inventory, echoes=0),
        [
            [f"equip:{HAT_ID}", f"screen:{SCREEN_ID}",
             f"shell:{SHELL_ID}", f"field:{FIELD_ID}"],
            ["unequip"],
            [],
        ],
    )

    # Frame 2 sees the state the equips produced on frame 1.
    applied = win.seen[1]
    assert applied["hat_slot"] == HAT_ID
    assert applied["screen_slot"] == SCREEN_ID
    assert applied["shell_slot"] == SHELL_ID
    assert applied["field_slot"] == FIELD_ID
    # Frame 3 sees the unequip from frame 2.
    assert win.seen[2]["hat_slot"] is None
    assert saved.creature.hat_slot is None

    assert win.purchases == [], "equipping is not a purchase"
    assert win.moments == [], "equipping must produce no dialogue at all"


# ═══ 6. THE STARVING DIVERSION ═════════════════════════════════════════════


@pytest.mark.parametrize("hunger", [49.0, 20.0, 5.0])
def test_cosmetic_bought_while_starving_draws_the_guilt_pool(window, hunger):
    """Contract v17's headline content behaviour: the starving diversion.

    A cosmetic bought while the pet is distressed/horror/dying replaces the
    cheerful per-kind pool ENTIRELY, whatever was bought. Losing this turns
    "you walked past the feed button to do it" into "nice hat".
    """
    assert hunger_state(hunger) in win_mod._STARVING_BANDS, hunger
    for item_id in (HAT_ID, SCREEN_ID, SHELL_ID, FIELD_ID):
        window._pending_event = None
        window.note_purchase(item_id, hunger=hunger, first_of_kind=False)
        assert window._pending_event in PURCHASE_LINES["starving"], (
            f"{item_id} @ hunger {hunger} escaped the diversion"
        )


def test_the_diversion_outranks_first_of_kind(window):
    """Contract v17: `starving` outranks even `first_of_kind`.

    A first hat bought over a starving creature is not a milestone — it is
    the diversion's whole point.
    """
    window.note_purchase(HAT_ID, hunger=12.0, first_of_kind=True)
    assert window._pending_event in PURCHASE_LINES["starving"]
    assert window._pending_event not in PURCHASE_LINES["first_of_kind"]


@pytest.mark.parametrize("hunger", [100.0, 60.0])
def test_a_fed_pet_draws_the_per_kind_pool(window, hunger):
    """Contract v17: at healthy/sad the per-kind pool speaks.

    A hat, a screen, a shell and a field are mechanically different things
    and the writing carries that — a single shared pool would throw away the
    only thing that makes those 48 lines worth having.
    """
    assert hunger_state(hunger) not in win_mod._STARVING_BANDS, hunger
    for item_id in (HAT_ID, SCREEN_ID, SHELL_ID, FIELD_ID):
        kind = shopcat.get(item_id).kind.value
        window._pending_event = None
        window.note_purchase(item_id, hunger=hunger, first_of_kind=False)
        assert window._pending_event in PURCHASE_LINES[kind], (
            f"{item_id} @ hunger {hunger} did not draw the {kind} pool"
        )


def test_first_of_kind_outranks_the_per_kind_pool_when_fed(window):
    """Contract v17 precedence step 2, between `starving` and the kind pool."""
    window.note_purchase(HAT_ID, hunger=100.0, first_of_kind=True)
    assert window._pending_event in PURCHASE_LINES["first_of_kind"]
    assert window._pending_event not in PURCHASE_LINES["hat"]


# ═══ 7. AN UNMAPPED ITEM MUST DEGRADE TO `generic`, NEVER TO SILENCE ══════


def test_an_unmapped_item_falls_back_to_generic_and_is_never_silent(window):
    """Contract v17: a sixth ItemKind added later must not be silent.

    Two reachable cases: an id that is not in the catalogue at all (`get()`
    returns None), and a real ItemKind with no pool — `CONSUMABLE` has none
    by design, since rations are food rather than cosmetics.
    """
    for item_id in ("an_item_from_the_future", "feed"):
        for _ in range(30):
            window._pending_event = None
            window.note_purchase(item_id, hunger=100.0, first_of_kind=False)
            assert window._pending_event is not None, (
                f"{item_id} produced silence"
            )
            assert window._pending_event in PURCHASE_LINES["generic"], (
                f"{item_id} did not fall back to the generic pool"
            )


def test_the_consumable_kind_really_has_no_pool_of_its_own():
    """Guards the premise of the test above: `consumable` is deliberately
    unmapped, so it must stay unmapped or that test stops testing anything."""
    from tokengotchi.shop.catalogue import ItemKind

    assert ItemKind.CONSUMABLE.value not in PURCHASE_LINES
    for kind in (ItemKind.HAT, ItemKind.SCREEN, ItemKind.SHELL, ItemKind.FIELD):
        assert PURCHASE_LINES.get(kind.value), kind


# ═══ 8. CONSTRAINT 6 — an empty draw must not burn the interval ═══════════


def test_an_empty_selection_does_not_burn_the_interval(monkeypatch):
    """Contract v17 constraint 6: reset the timer only on a SUCCESSFUL draw.

    The interval used to be reset on firing, before the draw was attempted,
    so a pool that came back empty burned the whole 2-5 minute window in
    silence — and quite possibly did it again. Selecting first and resetting
    after means an empty selection costs one FRAME, not one INTERVAL.
    """
    monkeypatch.setattr(sched_mod.random, "uniform", lambda a, b: 1.0)

    # Control: a fresh scheduler cannot fire on a zero-length frame, so the
    # second assertion below can only pass if the interval genuinely survived.
    control = DialogueScheduler()
    assert control.update(0.0, "healthy", True) is None

    s = DialogueScheduler()
    assert s.update(1.0, "no-such-band", True) is None, (
        "an unknown band has no pool — the draw must come back empty"
    )
    # Several more ripe-but-empty frames must not consume it either.
    for _ in range(10):
        assert s.update(0.0, "no-such-band", True) is None

    assert s.update(0.0, "healthy", True) is not None, (
        "the interval must survive an empty selection and speak the moment "
        "a pool has something to say"
    )


def test_the_interval_is_reset_once_a_line_is_actually_drawn(monkeypatch):
    """Contract v17 constraint 6's other half: a real draw DOES reset it.

    Without this, "don't burn the interval on an empty draw" could be
    satisfied by never resetting the interval at all, which would turn the
    ambient cadence into one line per frame.
    """
    monkeypatch.setattr(sched_mod.random, "uniform", lambda a, b: 1.0)
    s = DialogueScheduler()
    assert s.update(1.0, "healthy", True) is not None
    assert s.update(0.0, "healthy", True) is None, "the timer must have reset"
    assert s.update(0.9, "healthy", True) is None
    assert s.update(0.2, "healthy", True) is not None


# ═══ 9. THE POOL MIX — CONTEXT_BIAS keeps the 150 Layer-1 lines alive ═════


def test_select_mixes_the_gated_pool_with_the_general_band_pool():
    """Contract v17: `_select` is a MIX, not a preference.

    A context resolves in almost every reachable state, so a strict "context
    wins" made the 30-line general bands dead content everywhere except the
    `last_token_at is None` column and left a settled player hearing the same
    10-16 gated lines on a loop. Both pools must be reachable while a context
    is active, with the bias still favouring the specific line.
    """
    gated = set(CONTEXT_LINES["hoarding"]["hungry"])
    general = set(LINES["distressed"])
    assert gated and general
    assert not (gated & general), (
        "the two pools share a line — this test can no longer tell them apart"
    )

    random.seed(20260807)
    s = DialogueScheduler()
    draws = [s._select("distressed", "hoarding") for _ in range(400)]
    assert all(d is not None for d in draws)

    from_gated = sum(1 for d in draws if d in gated)
    from_general = sum(1 for d in draws if d in general)
    assert from_gated + from_general == len(draws), "a line came from nowhere"
    assert from_gated > 0, "the gated pool is unreachable — v17 Layer 2 is dead"
    assert from_general > 0, (
        "the general pool is unreachable — the 150 Layer-1 lines are dead"
    )
    assert CONTEXT_BIAS > 0.5
    assert from_gated > from_general, (
        "the specific line must stay the pet's characteristic voice"
    )


def test_select_uses_the_general_pool_when_no_context_resolves():
    """Contract v17: no context means the general band pool, unconditionally.

    `lines.py` asserts only hunger and mood, so it is honest in every state
    its band is true in — which is exactly why it is a safe fallback.
    """
    random.seed(7)
    s = DialogueScheduler()
    for band in ("healthy", "sad", "distressed", "horror", "dying"):
        for _ in range(40):
            assert s._select(band, None) in LINES[band]


# ═══ 10. REACHABILITY GUARD — no cell of CONTEXT_LINES may go dead ════════


def test_every_populated_context_cell_is_reachable_from_a_real_state():
    """Contract v17 constraint 1's structural companion: no dead content.

    Two separate bugs have already made 30 written lines unreachable — an
    `earning` gate that covered everything under four hours starved the
    `hungry` halves of lull/quiet/restless, and `hoarding` outranking the
    shallow rungs swallowed them whole. Both were invisible from the content
    files, which is why this sweeps the real gate: every populated
    (context, tone_group) cell must be produced by SOME real
    (hunger, bits, last_token_at age) triple, and every cell the gate can
    produce must have lines behind it.
    """
    hungers = (0.0, 5.0, 9.9, 10.0, 20.0, 24.9, 25.0, 43.0, 49.9, 50.0,
               60.0, 74.9, 75.0, 90.0, 100.0)
    balances = (0, 1, 2, 3, 14, 15, 100, 1358)
    ages_h = (0.0, 0.1, 0.4, 0.49, 0.5, 0.6, 0.9, 1.0, 1.5, 2.0, 3.0, 3.9,
              4.0, 5.0, 6.0, 7.0, 11.9, 12.0, 24.0, 60.0)

    reachable: set[tuple[str, str]] = set()
    for hunger in hungers:
        for bits in balances:
            for hours in ages_h:
                context = resolve_context(
                    hunger=hunger, bits=bits,
                    last_token_at=NOW - timedelta(hours=hours), now=NOW,
                )
                if context is not None:
                    reachable.add(
                        (context, tone_group(hunger_state(hunger))))

    populated = {
        (context, group)
        for context, groups in CONTEXT_LINES.items()
        for group, pool in groups.items()
        if pool
    }
    assert populated, "CONTEXT_LINES is empty — the sweep proves nothing"

    dead = sorted(populated - reachable)
    assert not dead, (
        f"written but unreachable — no real state resolves these cells: {dead}"
    )
    ghosts = sorted(reachable - populated)
    assert not ghosts, (
        f"the gate resolves cells with no lines behind them: {ghosts}"
    )
