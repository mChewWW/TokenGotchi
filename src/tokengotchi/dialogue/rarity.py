"""Feed-dialogue rarity gate (direction contract v18, Part A).

The complaint, measured: driving the real `main()` loop over 20 consecutive
feeds parked 20 lines — 100%. Feeding is the only *unbounded* dialogue source
(`hatch`/`adult` fire once per save ever; purchases are capped at 29 per install
against 62 written lines and already coalesce). So the gate applies to the four
`fed_*` keys and nothing else — see `GATED_MOMENTS`. Every other moment passes
through untouched.

A raw 1-in-4 dice is memoryless: it can speak twice running (undercutting
"special") or stay silent through fifteen feeds (feels broken). Instead this is
a bounded **pity gate** over `feeds_since_spoken`:

    n < FLOOR      → always silent
    n >= CEILING   → always speak
    otherwise      → speak with probability P

With FLOOR=3, CEILING=8, P=0.35 the gap distribution is
`{3: .35, 4: .23, 5: .15, 6: .10, 7: .06, 8: .12}` — mean gap 4.64, squarely
inside the human's "1/4 or 1/5", with both tails cut off.

The gate must sit BEFORE the line is parked, never at delivery: `window.py`
holds a single last-write-wins pending slot, so a delivery-side gate produces
double silence (the discarded line first evicts an already-earned one, then
discards itself).
"""
from __future__ import annotations

import random

# The only moments feeding can produce. Everything else — hatch, adult,
# wake_dormant, purchases, day-rollover — is out of scope and never gated.
GATED_MOMENTS = frozenset({"fed_hungry", "fed_full", "fed_wasted", "overfed"})

FLOOR = 3       # below this many silent feeds, never speak
CEILING = 8     # at or above this many, always speak
P = 0.35        # speak probability in the open interval — tuned for mean gap 4.64


class FeedGate:
    """Session-scoped pity gate for feed lines.

    Holds `feeds_since_spoken` and an injectable RNG seam so tests can assert
    the boundary behaviour deterministically rather than probabilistically.
    The counter is runtime-only: cadence should feel fresh each launch, and
    there is no schema field to persist it into.
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._since = 0

    def allow(self, key: str, *, first_feed: bool = False,
              rescue: bool = False) -> bool:
        """Whether a feed line for `key` should be parked this feed.

        Non-feed keys always pass — the gate owns feeding alone. `first_feed`
        (the once-per-install moment the player discovers the pet reacts at
        all) and `rescue` (a feed from the `dying` band) bypass the counter
        entirely: both are moments where silence would misteach or feel cold.
        A bypass still RESETS the counter, because a line did get spoken.
        """
        if key not in GATED_MOMENTS:
            return True
        if first_feed or rescue:
            self._since = 0
            return True

        self._since += 1
        if self._since < FLOOR:
            return False
        if self._since >= CEILING:
            self._since = 0
            return True
        if self._rng.random() < P:
            self._since = 0
            return True
        return False
