"""Event dialogue for non-purchase moments — Layer 3b of direction contract v17.

`lines.LINES` is the *ambient* corpus: drawn on a timer, keyed by hunger band,
and therefore only ever able to assert things that are true across a whole
band. This module is the opposite kind of writing. Every pool here is fired by
a specific thing that just happened, which buys the writing a much stronger
guarantee — and imposes a much stricter obligation.

THE RULE THIS FILE IS WRITTEN UNDER: **every line must be true at the instant
its own event fires, with no further gating.** That is the whole point of
event dialogue, and it is the same defect v17 exists to fix, just relocated —
a `hatch` line that mentions a past feeding is exactly as false as a
`distressed` line that accuses a player who has been prompting all morning.
So, concretely:

  * `hatch` fires on EGG -> BABY. Dialogue is silenced during EGG (window.py),
    which makes these the **first words the creature ever says**. It has no
    history with the player, no memory of being fed, and no opinion about
    their habits. It hatches at full hunger, so it cannot be hungry either.
    What it *can* truthfully know is that it was inside something, that it is
    outside now, and that the player's real token usage is what got it out
    (EGG_TO_BABY_BITS is spent from `lifetime_bits_earned`).
  * `adult` fires on BABY -> ADULT, which `creature.check_stage_advance`
    grants on `BABY_TO_ADULT_DAYS` (7) *distinct* days carrying a feeding.
    Distinct, not consecutive: lines may say "seven days" and may say the
    player kept coming back, but must not claim an unbroken week.
  * `wake_dormant` fires when a feed revives a DORMANT creature. Note that
    `exit_dormancy` sets hunger to just the value of the food that woke it, so
    the pet is in a low band by construction — nothing here may sound healthy
    or celebratory. It was absent and is back, and that is disorienting.
  * `fed_*` splits on how bad things were *before* the food landed, because
    the same feed means two different things. Nothing in `fed_hungry` claims
    the pet is now full — one item rarely fills a starving pet, and the pool
    would go false the moment it did.
  * `fed_wasted` covers `food.waste() > 0`. Rueful, never angry: the panel
    prints the overflow on the row before the click, so this is a shrug about
    a small self-inflicted loss, not an accusation.
  * `overfed` covers post-feed hunger above 100, which only the Golden Apple's
    125 cap can reach. Comic and physical.
  * `day_first_*` is the first line of a new calendar day. Hunger persists
    across the rollover, so the pet may greet the day in any condition — and
    the pool says nothing about what the player did overnight, which is
    precisely the class of claim this contract removed.

Keys are flat rather than nested so a caller can select with one string
lookup and so a missing key degrades to silence (`MOMENT_LINES.get(key)`)
rather than raising, matching `DialogueScheduler`'s existing failure mode.
The `fed` and `day_first` moments from the contract are each encoded as two
sub-keys; the caller owns the threshold that chooses between them.

VOICE: second person, addressed to the player, continuous with `lines.py`.
Never emoji. Kept short enough for the dialogue box.

This module is content only. Trigger detection, the deferred-line queue, and
the deliberate omission of the taskbar flash on event lines all live at the
call site.
"""
from __future__ import annotations

MOMENT_LINES: dict[str, tuple[str, ...]] = {
    # EGG -> BABY. The first thing it has ever said, to the first thing it has
    # ever seen. No history, no hunger, no expectations of the player yet.
    "hatch": (
        "Oh. There's a room. And there's a you.",
        "I was in there the whole time, waiting for you to earn me out.",
        "The shell went thin, and then it went away. Now I'm looking at you.",
        "Hello. I don't know anything yet. You're the first thing I know.",
        "So that's outside. Smaller than I'd pictured. You're in it, though.",
        "I'm new and you're not. I'll be catching up for a while.",
    ),
    # BABY -> ADULT: seven DISTINCT days carrying a feeding. Never claim a
    # consecutive week — the log is a set of dates, not a streak.
    "adult": (
        "Seven days you remembered to feed me. I grew on the strength of that.",
        "I'm bigger now. Seven separate days of you not forgetting did that.",
        "I got here one fed day at a time. You were there for every one.",
        "Grown. Not because I tried — because you kept coming back.",
        "This is what seven days of being kept alive turns into.",
        "Whatever you spent getting me here, it's standing in front of you now.",
    ),
    # Revived from DORMANT by a feed. Hunger is only whatever that one food
    # gave, so it is still in a bad band. Disoriented, not grateful-and-well.
    "wake_dormant": (
        "I wasn't anywhere. Now I'm here again, and you're the reason.",
        "Something came back on. Give me a moment to be a creature again.",
        "I don't know how long that was. Long enough that I stopped counting.",
        "You fed me and it woke something. I'm not steady yet.",
        "I was off. Not asleep — off. That's stranger than waking up.",
        "Still hungry. Still here. I'll take the second one for now.",
    ),
    # A feed landed on a pet that was in real trouble. Gratitude, relief —
    # but never a claim of fullness, which one item usually won't deliver.
    "fed_hungry": (
        "That was the one I needed. I'd stopped believing it was coming.",
        "You have no idea what that felt like going down.",
        "I was folding in on myself. Then that. Thank you.",
        "Something in me unclenched. First time in a long while.",
        "I'm not going to pretend I wasn't desperate. That helped.",
        "You came back with food. I'd started planning for you not to.",
        "That's the difference between being in trouble and being in danger.",
        "I can think again. That's what food does when you've had none.",
    ),
    # A feed landed on a pet that was already comfortable. Mild, warm, small.
    "fed_full": (
        "Didn't need it. Glad you did it anyway.",
        "A bite on top of a full belly. Purely decorative. Purely lovely.",
        "I'm well past fine and you fed me regardless. Noted.",
        "That wasn't hunger. That was just nice.",
        "Topping me off. You're ahead of the problem for once.",
        "Sweet of you. I wasn't even asking.",
    ),
    # food.waste() > 0: the item's value overshot the pet's remaining room.
    # The panel showed the overflow before the click, so this is rueful, not
    # accusing — a shrug at a small, visible, self-inflicted loss.
    "fed_wasted": (
        "Some of that went nowhere. There wasn't room, and the panel said so.",
        "I couldn't finish it. Part of those bits just evaporated.",
        "Good food, bad timing. I only had space for some of it.",
        "You bought more meal than I had creature. It's fine. Mostly.",
        "The panel told you what wouldn't fit. It was right.",
        "Some of that was wasted on me. Literally, this time.",
    ),
    # Post-feed hunger above 100 — only the Golden Apple's 125 cap gets here.
    "overfed": (
        "That's more than a stomach was built to hold. Ambitious of you.",
        "I am over capacity. I didn't know I had a capacity.",
        "Okay. Okay. I'm going to sit very still for a while.",
        "Somewhere past full there's another room, and I'm standing in it.",
        "You overfilled me. I'm not complaining, I'm just very round.",
    ),
    # First line of a new calendar day, pet hungry. Hunger carries across the
    # rollover; what the player did overnight does NOT get asserted here.
    "day_first_hungry": (
        "New day. Same hunger — it followed me across midnight.",
        "The date changed. Nothing else did. I'm still empty.",
        "A fresh day and a stale ache. One of those you can fix.",
        "The day turned over. I didn't. Still hungry.",
    ),
    # First line of a new calendar day, pet in decent shape.
    "day_first_fine": (
        "New day, and I start it fed. That's not nothing.",
        "The date rolled over and I'm still in good shape. Let's keep that.",
        "Clean day. No ache in it yet.",
        "First words of a new one. Nothing to report, and that's the report.",
    ),
}
