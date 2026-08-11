"""Random-cadence dialogue triggering with per-pool repeat avoidance.

Direction contract v11 point 4: dialogue fires periodically at random while
the app runs, independent of hunger-band transitions — not only at the
moment of crossing a threshold. Point 5: each band's lines are drawn from a
shuffle bag so repeats are rare and a reshuffle never immediately repeats
the line just shown.

Direction contract v17 adds two more sources of lines on top of that timer,
and both of them are selected ELSEWHERE — this module owns cadence and
repeat-avoidance only, never the question of what is true right now:

  * a context pool (`dialogue/context.py` resolves the gate) preempts the
    general band pool while its condition holds;
  * an event line (a purchase, a hatch, a feed) bypasses the timer entirely
    via `draw_immediate`, because it is a reaction to something the player
    just did rather than an ambient remark.
"""
from __future__ import annotations

import random
from typing import Sequence

from .context import context_pool, tone_group
from .lines import LINES

# "randomized within a several-minute window" (contract v11 point 4) — the
# exact bounds are an implementation detail, not a re-opened scope question.
MIN_INTERVAL_S = 120.0
MAX_INTERVAL_S = 300.0

# How often a resolved context takes the frame, versus the general band pool.
# See `DialogueScheduler._select` for why this is a mix and not a preference.
# Above half so the specific line stays the pet's characteristic voice.
CONTEXT_BIAS = 0.65


class _BandBag:
    """Shuffled consumption of one pool's line list.

    Named for the hunger bands it was introduced to serve; v17 also backs
    context and event pools with it. Renaming it would churn the tests that
    import it by name for no behavioural gain.
    """

    def __init__(self, lines: tuple[str, ...]) -> None:
        self._lines = lines
        self._bag: list[str] = []
        self._last: str | None = None

    def draw(self) -> str | None:
        if not self._lines:
            return None
        if not self._bag:
            self._bag = list(self._lines)
            random.shuffle(self._bag)
            if len(self._bag) > 1 and self._bag[-1] == self._last:
                swap = random.randrange(0, len(self._bag) - 1)
                self._bag[-1], self._bag[swap] = self._bag[swap], self._bag[-1]
        self._last = self._bag.pop()
        return self._last


class DialogueScheduler:
    """Owns the jittered interval timer and the shuffle bag behind every pool.

    Degrades to silence — never a placeholder string — if a pool has no
    lines, per the contract's "dialogue is decoration, never a gate"
    constraint.
    """

    def __init__(self) -> None:
        self._bags = {band: _BandBag(lines) for band, lines in LINES.items()}
        # Context and event bags are built on first use and keyed by pool
        # identity, so switching band or context mid-session resumes that
        # pool's bag where it left off instead of reshuffling from full.
        self._pools: dict[str, _BandBag] = {}
        # Repeat avoidance ACROSS bags. Each `_BandBag` only knows what it
        # last emitted, so a switch from the general pool to a context pool
        # (or from an ambient line to an event line) could show the same
        # string twice in a row without anything noticing. This is the
        # scheduler-level memory that closes that gap.
        self._last_shown: str | None = None
        self._elapsed = 0.0
        self._next = random.uniform(MIN_INTERVAL_S, MAX_INTERVAL_S)

    def update(
        self,
        dt: float,
        band: str,
        allow_trigger: bool,
        context: str | None = None,
    ) -> str | None:
        """Advance the timer; return a freshly-drawn line iff it just fired.

        `allow_trigger` is False while the creature is silenced (EGG stage,
        DORMANT state) or another panel (food/shop/rates) is open. The clock
        pauses rather than accumulates in that case, so closing the other
        panel doesn't immediately dump a queued popup on top of it.

        `context` is the gate resolved by `dialogue.context.resolve_context`,
        or None for the general pool.

        THE INTERVAL IS RESET ONLY ON A SUCCESSFUL DRAW (contract v17
        constraint 6). It used to be reset immediately on firing, before the
        draw was attempted, so a pool that came back empty burned the whole
        2-5 minute interval in silence and then quite possibly did it again.
        Selecting first and resetting after means an empty selection costs one
        frame, not one interval: the timer stays ripe and re-attempts next
        frame, and speaks the moment anything has something to say.
        """
        if not allow_trigger:
            return None
        self._elapsed += dt
        if self._elapsed < self._next:
            return None
        line = self._select(band, context)
        if line is None:
            return None
        self._elapsed = 0.0
        self._next = random.uniform(MIN_INTERVAL_S, MAX_INTERVAL_S)
        return line

    def draw_immediate(self, key: str, lines: Sequence[str]) -> str | None:
        """Draw an event line NOW, bypassing the timer.

        For lines that react to something the player just did — a purchase, a
        hatch, a feed — where waiting out an ambient interval would deliver
        the reaction minutes after the moment it is about.

        The ambient clock is deliberately left alone: an event is not an
        ambient remark and must not push the next one out, nor pull it in.
        The caller owns which pool `lines` comes from and owns delivery
        (contract v17 defers purchase lines to shop-close); this method owns
        only the shuffle bag and the cross-pool repeat guard.

        `key` identifies the bag, so it must be stable per pool — the caller
        namespaces it (`"purchase:hat"`, `"moment:hatch"`).
        """
        pool = tuple(lines)
        if not pool:
            return None
        return self._pull(self._bag_for(key, pool))

    # ── internals ───────────────────────────────────────────────────────────

    def _select(self, band: str, context: str | None) -> str | None:
        """Mostly the context pool when the gate opened one, else the general
        band pool.

        WHY THIS IS A MIX RATHER THAN A PREFERENCE. A context resolves in
        almost every reachable state — once `last_token_at` exists at all, some
        rung or wallet fact is always true — so a strict "context wins" made
        the general pool dead content everywhere except the `last_token_at is
        None` column, and left a settled player hearing the same 10-16 gated
        lines on a loop. Mixing pulls the 30-line general pool back in, which
        roughly triples the variety at any given moment.

        It is safe precisely because of the v17 split: the general pool asserts
        only hunger, mood and the need to be fed, so it is true in EVERY state
        its band is true in. There is no state where substituting it says
        something false — that is the whole reason Layer 1 was rewritten, and
        this is what cashes it in.

        The bias stays well above half so the pointed, specific line remains
        the pet's characteristic voice; the general pool is the texture around
        it, not an equal partner.
        """
        pool = context_pool(context, band)
        if pool and random.random() < CONTEXT_BIAS:
            # Keyed by tone group as well as context: `fed` and `hungry` are
            # different line lists under the same context name and must not
            # share a bag.
            line = self._pull(self._bag_for(
                f"ctx:{context}:{tone_group(band)}", pool))
            if line is not None:
                return line
        bag = self._bags.get(band)
        line = self._pull(bag) if bag is not None else None
        if line is not None:
            return line
        # The general pool is missing or exhausted to nothing (a band with no
        # lines). Fall back to the gated pool rather than going silent.
        if pool:
            return self._pull(self._bag_for(
                f"ctx:{context}:{tone_group(band)}", pool))
        return None

    def _bag_for(self, key: str, pool: tuple[str, ...]) -> _BandBag:
        bag = self._pools.get(key)
        if bag is None:
            bag = _BandBag(pool)
            self._pools[key] = bag
        return bag

    def _pull(self, bag: _BandBag) -> str | None:
        """Draw from `bag`, avoiding an immediate repeat of the last line
        shown from ANY bag.

        One redraw, not a loop: the bag reshuffles rather than blocking, so a
        second draw always yields a different line unless the pool holds
        exactly one — in which case repeating it is the only alternative to
        going silent, and silence is the worse of the two for a pool that
        was specifically selected as the true thing to say.
        """
        line = bag.draw()
        if line is None:
            return None
        if line == self._last_shown:
            alt = bag.draw()
            if alt is not None:
                line = alt
        self._last_shown = line
        return line
