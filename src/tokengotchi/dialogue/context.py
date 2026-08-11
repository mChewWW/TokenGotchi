"""Context gating — the decision of WHICH pool speaks. Direction contract v17.

`context_lines.py` is the writing; this is the gate that licenses it. The two
are deliberately separate files: the pools are allowed to say sharp, specific,
provable things *only* because something upstream proved the condition, and
that proof is small enough to read in one sitting and test without pygame.

THE SIGNAL. Hunger falls because the player has not clicked FEED. BITS are
earned by using Claude Code. Those are independent quantities, which is the
whole defect v17 exists to fix — a player can prompt all day, bank a fortune
and never feed, and the old band-only selection would tell them they had gone
silent. `rates.last_token_at` is the timestamp of the last watcher fire that
carried a non-zero token delta, i.e. the last time the player actually used
Claude Code. It is the real activity signal and it is already persisted.

WHAT IS DELIBERATELY NOT USED:

  * `rates.resting` — a cached "last_token_at is >= 48h old" flag, written only
    inside `_tick_rates` behind a 6h slot-boundary early return, and `main.py`
    re-anchors `period_start` on every launch. It can be arbitrarily stale.
    The age is recomputed live here instead, every time.
  * `rates.calibrating` — fewer than 2 distinct days in the trailing window.
    A returning veteran reads as a newcomer through it.
  * "wallet.bits unchanged" — points at the right concept and the wrong
    mechanism in both directions: a player who earns and feeds in equal
    measure shows an unchanged balance while being maximally active, and at
    BITS_RATIO=500 a genuinely working player can go a long stretch with no
    whole-BIT credit landing at all.

WHY THE TIERS ARE DECLARED HERE AND NOT BORROWED FROM `engine/rates.py`
(contract constraint 5): `REST_HOURS` and friends tune the *appetite economy*.
If the writing read them, retuning how fast the pet gets hungry would silently
retune what it is willing to accuse the player of. Two different jobs, two
different sets of numbers, even where the numbers happen to agree today.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..engine.actions import BITS_PER_FEED
from ..engine.creature import hunger_state
from .context_lines import CONTEXT_LINES

# The graded ladder, resolved by the human 2026-08-07 over a flat 4h binary and
# widened by them from four rungs to six the same day. The tier itself carries
# the escalation, which is what lets the pools stay band-coarse (fed/hungry)
# instead of a 30-cell tier x band matrix.
#
# THE BLAME LINE SITS AT `drought`. The first three rungs escalate ATTENTION,
# not accusation: at one or two hours the player is plausibly in a meeting, at
# lunch, or deep in work that has not billed a token yet, and blaming them
# there would reintroduce the exact defect this module exists to remove.
DIALOGUE_LULL_MINUTES: float = 30.0
DIALOGUE_QUIET_HOURS: float = 1.0
DIALOGUE_RESTLESS_HOURS: float = 2.0
DIALOGUE_DROUGHT_HOURS: float = 4.0
DIALOGUE_DEEP_DROUGHT_HOURS: float = 6.0
DIALOGUE_ABANDONED_HOURS: float = 12.0

# Tone groups are band-coarse. `sad` sits with `healthy` rather than with the
# low bands because a `sad` pet is at 50-75% hunger — visibly fine — and a
# line written for a starving creature would read as melodrama over that
# sprite. See the module docstring in `context_lines.py`.
_FED_BANDS: frozenset[str] = frozenset({"healthy", "sad"})

# The six ladder tiers with their thresholds in seconds, DESCENDING by
# severity. Only these may fire at `healthy`: they claim something about the
# player's SILENCE, which is true regardless of how well fed the pet is.
# `hoarding`/`earning` claim something about the pet needing food, which is not.
_LADDER: tuple[tuple[str, float], ...] = (
    ("abandoned", DIALOGUE_ABANDONED_HOURS * 3600.0),
    ("deep_drought", DIALOGUE_DEEP_DROUGHT_HOURS * 3600.0),
    ("drought", DIALOGUE_DROUGHT_HOURS * 3600.0),
    ("restless", DIALOGUE_RESTLESS_HOURS * 3600.0),
    ("quiet", DIALOGUE_QUIET_HOURS * 3600.0),
    ("lull", DIALOGUE_LULL_MINUTES * 60.0),
)

_TIER_CONTEXTS: tuple[str, ...] = tuple(name for name, _ in _LADDER)

# The rungs deep enough that the silence outranks the wallet — which is exactly
# the set permitted to blame (>= `drought`, 4h).
#
# WHY THE LINE IS DRAWN HERE. `hoarding` is true whenever the player holds a
# feed's worth of BITS, which for a habitual user is essentially always; if it
# outranked the shallow rungs it would swallow them whole and the graded ladder
# the human asked for would be dead content at every band below `healthy`.
# Measured on the live save (1358 BITS): with `drought` on the wallet's side of
# this line, `hoarding` won every cell from 29 minutes to six hours.
#
# The split also reads correctly as tone. Below 4h the pet has no standing to
# blame anyone for silence, so the honest specific complaint — "you can afford
# to feed me and haven't" — is the right thing to say. At 4h and beyond the
# silence has become the larger fact and the ladder takes it back.
_OUTRANKS_HOARDING: frozenset[str] = frozenset(
    {"abandoned", "deep_drought", "drought"}
)


def tone_group(band: str) -> str:
    """Map a hunger band onto the coarse tone split the gated pools use."""
    return "fed" if band in _FED_BANDS else "hungry"


def context_pool(context: str | None, band: str) -> tuple[str, ...]:
    """The lines a resolved context offers at this band, or `()` for none.

    Returning an empty tuple rather than raising on an unknown context is the
    same failure mode `DialogueScheduler` already has: a spelling drift
    between gate and content means silence at that cell, and the general pool
    picks the frame up — never a crash and never a placeholder string.
    """
    if not context:
        return ()
    return CONTEXT_LINES.get(context, {}).get(tone_group(band), ())


def _age_seconds(last_token_at: datetime | None, now: datetime) -> float | None:
    """Seconds since the player last actually used Claude Code.

    None means "unknowable", which is NOT the same as "a long time" — see the
    precedence note in `resolve_context`.

    Mixed tz-awareness is normalised rather than allowed to raise. Everything
    that writes `last_token_at` writes an aware UTC datetime, but the state
    file is user-editable and pydantic will happily hand back a naive value
    from a hand-edited save; subtracting that from an aware `now` is a
    TypeError inside the render loop, and dialogue is decoration and must
    never be able to take the frame down with it.
    """
    if last_token_at is None:
        return None
    a, b = last_token_at, now
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    age = (b - a).total_seconds()
    # A future timestamp (clock skew, a save copied across machines, a manual
    # edit) is not evidence of silence. Read as "just now".
    return max(0.0, age)


def resolve_context(
    *,
    hunger: float,
    bits: int,
    last_token_at: datetime | None,
    now: datetime,
) -> str | None:
    """Pick the gated pool that is provably true right now, or None.

    None means "nothing specific is known" and the caller falls back to the
    general band pool in `lines.py`, which asserts only hunger and mood and is
    therefore unconditionally honest.

    PRECEDENCE — first match wins:

    0. `last_token_at is None` -> **not a drought, and not anything else.**
       A fresh install and a forward-migrated save both look identical to a
       player who has been silent for a week, and the cost of guessing wrong
       is accusing somebody who has not yet had the chance to do anything.
       Return None and let the general pool speak.
    1. `abandoned` (>= 12h), then `deep_drought` (>= 6h). These outrank
       `hoarding` deliberately: at that depth the silence is the bigger story
       than the unspent balance, and a line needling somebody about their
       wallet after half a day away is aiming at the wrong thing.
    2. `hoarding` (`bits >= BITS_PER_FEED`, low bands only). The human's exact
       complaint, and it outranks every shallow tier because it is both more
       specific and more provable: one click fixes this and it has not been
       clicked. Note that it does NOT assume silence — a hoarding player may
       be mid-prompt this second, which is precisely why it sits above the
       shallow tiers rather than being merged into them.
    THE AFFORDABILITY LINE IS `BITS_PER_FEED` (3), NOT `FEED_COST` (15).
    `main.py` spends `FEED_COST` when the wallet can cover it and otherwise
    spends whatever is left, feeding as long as that clears `BITS_PER_FEED` —
    so the FEED button genuinely works from 3 BITS up. Gating on `FEED_COST`
    told every player holding 3-14 BITS "you can't afford me yet" while the
    button in front of them worked, and simultaneously withheld `hoarding` —
    the human's headline complaint — from a window where one click really did
    fix it. Both halves were false, so both halves move to the real threshold.

    3. `earning` (`bits < BITS_PER_FEED`, activity inside the `lull` window, low
       bands only). Sympathetic: they are doing the right thing and it has not
       landed yet. Gated on RECENT ACTIVITY rather than merely "no drought",
       because the pool asserts the player is working right now and only a
       fresh `last_token_at` is evidence of that. Mutually exclusive with
       `hoarding` by the same `bits` test.
    4. The shallow rungs, deepest first: `drought` (>= 4h) — the first tier
       permitted to blame — then `restless` (>= 2h), `quiet` (>= 1h) and
       `lull` (>= 30min), which escalate attention without accusing. Offering
       them deepest-first means a rung whose pool is missing degrades to the
       shallower phrasing rather than to silence.

    BAND RESTRICTION. Only the six ladder tiers may fire at `healthy`: a fed
    pet has nothing to accuse anyone of, so `hoarding` and `earning` — both of
    which are about needing food — must never reach it. Context never changes
    the band itself; the band still drives the sprite and the emotional
    register, and a context that could move it would produce a starved-looking
    pet talking cheerfully.

    EMPTY-POOL GUARD. A candidate whose pool is empty for this tone group is
    skipped, not returned. This is load-bearing rather than paranoid:
    `hoarding` and `earning` are written for the `hungry` group only, so at
    `sad` (which is tone group `fed`) they are silently unreachable and the
    next candidate down — usually a ladder tier — takes the frame. Returning
    an empty pool would hand the scheduler a guaranteed silence instead.
    """
    age = _age_seconds(last_token_at, now)
    if age is None:
        return None

    band = hunger_state(hunger)
    # "Low" is every band except healthy — the four bands the contract lets a
    # context speak into about food.
    low = band != "healthy"
    in_drought = age >= DIALOGUE_DROUGHT_HOURS * 3600.0

    # Every rung the player has passed, deepest first. Offering all of them
    # rather than just the deepest is what lets a rung with a missing pool
    # degrade to the shallower phrasing instead of falling through to nothing.
    reached = [name for name, threshold in _LADDER if age >= threshold]

    candidates: list[str] = []
    candidates.extend(n for n in reached if n in _OUTRANKS_HOARDING)
    if low and bits >= BITS_PER_FEED:
        candidates.append("hoarding")
    elif low and age < DIALOGUE_LULL_MINUTES * 60.0:
        # `bits < BITS_PER_FEED` by the branch above: working, broke, owed.
        #
        # GATED ON THE SAME WINDOW AS `lull`, NOT ON "no drought". The earlier
        # `not in_drought` spelling let this fire anywhere from 0s to 3h59m of
        # total silence, so a broke player who had stopped hours ago was told
        # "the tokens are coming in, I can feel it" — an assertion about their
        # activity that the gate did not remotely prove, which is the exact
        # defect this module exists to remove. Sympathy has to be earned by
        # evidence of actual work, and the only evidence available is a recent
        # `last_token_at`.
        #
        # Tightening this is also what makes the `hungry` halves of lull/quiet/
        # restless reachable at all: they sit below `earning`, so an `earning`
        # that covered everything under four hours starved them of every state.
        candidates.append("earning")
    candidates.extend(n for n in reached if n not in _OUTRANKS_HOARDING)

    group = tone_group(band)
    for ctx in candidates:
        if not low and ctx not in _TIER_CONTEXTS:
            continue        # belt and braces; `low` already gates both cases
        if CONTEXT_LINES.get(ctx, {}).get(group):
            return ctx
    return None
