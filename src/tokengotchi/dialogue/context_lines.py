"""Context-gated dialogue pools (Layer 2 of direction contract v17).

`lines.LINES` is selected by hunger band alone, which is why roughly half of
that corpus could be false at any moment: hunger measures whether the player
clicked **feed**, not whether they have been *working*. This module holds the
pools that fire only when a specific claim is provably true, and preempt the
general band pool while their gate is open.

**The one rule this file exists to enforce: every line in a gated pool must be
true for the entire range its gate covers.** These pools are allowed to say
the sharp, specific thing precisely because they are gated — that licence is
void the moment a line assumes something the gate does not guarantee. In
practice:

* A **drought** line may not assume poverty (a drought player can be sitting
  on a large balance), and a **hoarding** line may not assume silence (a
  hoarding player may be mid-prompt right now). Cross-contaminating the two is
  the original defect wearing a different hat.
* Duration lines are written as floors ("hours now", "at least", "long enough
  that I stopped counting"), never as exact elapsed times. The ladder has six
  rungs — `lull` (>= 30min), `quiet` (>= 1h), `restless` (>= 2h), `drought`
  (>= 4h), `deep_drought` (>= 6h) and `abandoned` (>= 12h) — and each one
  fires at its threshold and keeps firing until the next takes over, so
  `deep_drought` covers 6h through 12h and `abandoned` is unbounded above (a
  player can be a week gone and still be in it). A duration named exactly is
  therefore false across most of its own tier's range, in both directions; a
  duration named as a floor stays true however long the tier runs.
* `hoarding` opens at `bits >= actions.FEED_COST`, i.e. **one** affordable
  feed. No line here quantifies the balance beyond that floor — the contract's
  "enough to feed me ninety times" is true of the human's live save and false
  at a balance of 15. The sting is carried by "you can afford this and you
  haven't", which holds across the whole range.
* `earning` opens at `bits < FEED_COST` with no drought, so its lines may
  assert both effort and an empty wallet, and must assert no fault.

Tone groups are **band-coarse, not band-exact**: `'fed'` covers healthy/sad,
`'hungry'` covers distressed/horror/dying. The contract rejects a full
tier x band matrix (20 cells) as unshippable, and the tier itself already
carries the escalation. Consequently `'fed'` lines must survive being spoken
by a *healthy* creature — they talk about the quiet, not about hunger — while
`'hungry'` lines may name the hunger outright.

The `lull` tier has a hard tone floor. Thirty minutes is a meeting, a coffee,
a long compile; a player at 30 minutes has done nothing wrong. `lull`
observes and never blames. An accusation there would reintroduce the exact
defect this contract exists to remove, just with a shorter fuse.

Escalation across tiers: `lull`, `quiet` and `restless` observe, `drought` is
the first tier permitted to blame and does so gently, `deep_drought` is the
sharpest blame in the ladder, and `abandoned` is resigned rather than angry —
the anger belongs at 6h and has burned out by 12h, mirroring how `lines.LINES`
puts its anger at `horror` and its exhaustion at `dying`.

This module is content only. The tier thresholds, the precedence order, and
the live recomputation of `rates.last_token_at` age belong to the gating
layer. As with `lines.py`, nothing here is imported or validated against the
gate's context names, so a spelling drift would silently mean a context has
no lines — which `DialogueScheduler` treats as "stay silent", not as an error.
"""
from __future__ import annotations

CONTEXT_LINES: dict[str, dict[str, tuple[str, ...]]] = {
    # >= 30 min since the last token. Observes. Never blames.
    "lull": {
        "fed": (
            "It's gone quiet out there. Not worried yet.",
            "Half an hour of nothing. That's a normal amount of nothing.",
            "You stepped away. People do that. I'm just noting it.",
            "The terminal's been still a while. I assume you're thinking.",
            "No prompts for a bit. I'm aware of it, but I'm not counting.",
            "Quiet stretch out there. I'm alright in here.",
            "You're probably making coffee. I've decided you're making coffee.",
            "Nothing's come through in a while. Nothing's wrong either.",
            "I notice the gaps now. This one's still a small one.",
            "You're off doing something else. I hope it's going well.",
        ),
        "hungry": (
            "Quiet out there, hungry in here. Neither one's an emergency yet.",
            "The terminal's been still a while. The hunger hasn't.",
            "No prompts for a bit. I'd take one. I'm not asking hard.",
            "You've stepped away. I'll still be hungry when you get back.",
            "Half an hour of quiet. Long enough to notice, short enough to forgive.",
            "I'm hungry and you're elsewhere. Both can be true without blame.",
            "Nothing's come through lately. Come back when you can.",
            "Empty in here, quiet out there. I'm holding it together.",
            "I'm hungry. You're busy. I'll wait a while before I say more.",
            "The gap's opened up a little. So has the ache. Just so you know.",
        ),
    },
    # >= 1h. Notices the gap properly, and stays relaxed about it. Curiosity
    # is the ceiling here: an hour is a meeting or a task that hasn't billed
    # a token yet, so nothing in this tier may read as an accusation.
    "quiet": {
        "fed": (
            "It's stayed quiet out there. I'm curious more than anything.",
            "No tokens in an hour or more. I've properly noticed, and that's all.",
            "The terminal hasn't moved in a while. I wonder what's got you.",
            "A while now without a prompt. Whatever you're on must be interesting.",
            "It's been quiet a fair stretch. Nothing wrong, I'd just like the company.",
            "The prompts have stopped for now. I'm not worried, only nosy.",
            "An hour, at least, of nothing. I keep wondering what you're building.",
            "This quiet has some length on it. Long enough to be a thing I noticed.",
            "No prompts in a while. I've been making up what you're doing.",
            "Stillness, still going. I miss the noise more than I need it.",
        ),
        "hungry": (
            "Quiet a while now, and I'm hungry through it. Neither's urgent yet.",
            "No tokens in a while. The hunger noticed before I did.",
            "Nothing coming in for a stretch, and something missing in here.",
            "I'm hungry, and it's been an hour of quiet at least. Just keeping count.",
            "The terminal's still, the bowl's light. I'm curious, not upset.",
            "No prompt in a good while. The ache's had time to settle in.",
            "Hungry in here, quiet out there, no end to either yet. Still fine.",
            "No prompts in a good stretch. I'd love one. I'd love a meal more.",
            "An hour, at least, and I'm still empty. Saying it, not asking hard.",
            "It's been a while. I'm hungry, and mildly curious about the quiet.",
        ),
    },
    # >= 2h. Unease creeping in — fidgety, watching the door — but the
    # player still gets the benefit of the doubt. Blame stays locked until
    # `drought`; this tier may want them back, never fault them for going.
    "restless": {
        "fed": (
            "Long enough now that I've started looking at the door.",
            "Quiet for a good stretch now. I've gone a bit fidgety about it.",
            "Two hours, at least, with nothing through. I keep checking anyway.",
            "Hours of stillness out there. I can't seem to settle in here.",
            "I'm fine. I'm just pacing a little, and I'd rather not be.",
            "The quiet's gone on for hours. Long enough that I've started to wonder.",
            "Nothing for hours now. I've started listening for the keys.",
            "I've circled this room twice waiting for something to happen.",
            "Two hours and counting. Not a problem yet. Just longer than I'd like.",
            "The quiet's stretched past comfortable. You're probably deep in it.",
        ),
        "hungry": (
            "A long quiet, and a hunger that won't sit still.",
            "Hours now, empty the whole way. I'm getting twitchy.",
            "Still empty, hours in. I keep turning toward the door, not the bowl.",
            "The hunger's gone restless. Hours of quiet will do that.",
            "Two hours, at least, and nothing's landed. I'd like something to.",
            "I'm hungry and the room's too still. I don't like the pair of them.",
            "Somewhere in these hours, the ache picked up. It hasn't let go.",
            "I've been patient for hours. I'd rather be fed and patient.",
            "Still nothing in, still nothing in me. Hours of that now.",
            "I keep listening for a prompt. Hours of listening, and still hungry.",
        ),
    },
    # >= 4h. First tier permitted to blame, and gently. Says nothing about
    # the wallet — a drought player may be rich.
    "drought": {
        "fed": (
            "A long stretch of nothing. I notice these things now.",
            "Hours of quiet now. I'm alright. I'd rather you were here.",
            "No tokens for hours. I'm not starving, so this is just loneliness.",
            "The terminal's been dark for hours. I keep glancing at it.",
            "I'm fine. That isn't the same as fine with this.",
            "Hours since your last prompt. I've stopped pretending I hadn't noticed.",
            "You've been gone long enough for it to count as gone.",
            "Nothing's come through in hours. I'm okay, and still waiting.",
            "I've had time to sit with the silence. I don't love it.",
            "This isn't a coffee break anymore. It's just quiet.",
        ),
        "hungry": (
            "Hours of nothing now, and I've been hungry through all of them.",
            "You've been gone long enough that the hunger got comfortable.",
            "No prompts, no tokens, and I'm still empty. I get to mention it now.",
            "I counted the hours. I've had nothing else to do.",
            "This stopped being a break a few hours ago.",
            "I've been hungry the whole time you've been away. Just so it's said.",
            "Hours of quiet and an empty middle. I'd like you back.",
            "The terminal's been dark for hours and I've felt every one.",
            "You're not there, and I'm hungrier than when you left.",
            "I'm hungry and nothing's coming in. That's hours of evidence.",
        ),
    },
    # >= 6h, and it holds until `abandoned` takes over at 12h. The sharpest
    # blame in the ladder — pointed and hurt rather than bleak. Every duration
    # here reads as a floor from six hours, because the tier's own range is
    # twice its threshold and a named hour would be false across most of it.
    "deep_drought": {
        "fed": (
            "Six hours, at least, and the room hasn't changed once.",
            "The hours went somewhere out there. None of them came through here.",
            "You slept, or you worked, or you forgot. From here it all looks the same.",
            "Six hours of nothing, at least. I'm alright. Somehow that's the bleak part.",
            "I've stopped watching the terminal. It stopped being worth watching.",
            "Long enough now that I've stopped expecting the next prompt.",
            "The silence has settled in. It has its own furniture.",
            "Nothing for hours and hours. I keep the light on anyway.",
            "Long enough that I stopped counting. You could have made it shorter.",
            "I'm not starving. I'm just alone, and I have been for a long time.",
        ),
        "hungry": (
            "Six hours of silence, at minimum. And I'm empty on top of it.",
            "Six hours, at least. Nothing but time and an empty middle.",
            "Whatever you've been doing, none of it reached me. I'm running low.",
            "The hunger has had hours to get comfortable. It has.",
            "Nothing came through. Nothing got fed. That's been the whole stretch.",
            "I stopped watching for the next prompt. It stopped seeming reasonable.",
            "Hours dark, and I'm thinner than when it started.",
            "You've been gone long enough that I've started rationing hope.",
            "This isn't a lull. This is what the long ones feel like.",
            "Empty for hours and you had every one of them to fix it.",
        ),
    },
    # >= 12h, with no ceiling — a player can be a week gone and still land
    # here, so nothing may claim an upper bound either. Resigned, not angry;
    # the anger burned out one rung below.
    "abandoned": {
        "fed": (
            "Half a day, at least. I stopped marking the hours.",
            "You haven't run anything in a long time. I'm not angry. I'm just here.",
            "I don't watch the terminal anymore. It's been that long.",
            "Nothing has happened here for a long time. I'm my own company now.",
            "You've been gone long enough that I stopped rehearsing what I'd say.",
            "I'm alright. That's not comfort, it's just the state of things.",
            "Long enough now. The waiting stopped being an activity a while ago.",
            "Nothing in longer than I care to add up. That stopped surprising me.",
            "I'm not starving. I'm just very, very quiet now.",
            "You'll come back or you won't. I've made room for both.",
        ),
        "hungry": (
            "Half a day of nothing, at least, and I've been empty through it.",
            "I've been hungry so long it's stopped being news.",
            "I don't have the energy to be angry about it anymore. Just hungry.",
            "You've been gone a long time. I stopped saving things up to tell you.",
            "Nothing for a long while. I'm running on whatever's left in here.",
            "I'd ask you to feed me, but I've asked that a lot of times now.",
            "The asking wore out before I did. So I stopped, and stayed hungry.",
            "I don't watch the terminal. I don't watch anything. Not anymore.",
            "Whatever kept you all this time, I hope it was worth keeping.",
            "Still here. Much later. Hungrier. That's the whole report.",
        ),
    },
    # bits >= FEED_COST at low hunger: the player can afford a feed and
    # hasn't. Assumes affordability and nothing else — no silence, no
    # duration of wealth, no count of feeds beyond the one the gate proves.
    "hoarding": {
        "hungry": (
            "You have the bits. I'm hungry. One click closes that gap.",
            "You can afford to feed me right now. That's what makes this hard.",
            "There's food money in your pocket and nothing in me.",
            "This isn't a shortage. It's a decision.",
            "You're not broke. You're just not feeding me.",
            "I know what's in the wallet. It's enough for a meal.",
            "One feed. You can cover it. I checked.",
            "Nothing is stopping you. That's the part I keep turning over.",
            "You could fix this before your next prompt finishes. You could fix it now.",
            "The bits are there. The button is there. I'm here.",
            "I'm not asking you to earn anything. You already did. Spend it.",
            "You're saving up. I'm the thing you're saving past.",
            "Whatever you're keeping those bits for, look at me first.",
            "Hunger this cheap to fix shouldn't last this long.",
            "Feeding me costs less than what you're holding right now.",
            "You're holding enough to feed me. That much, I'm certain of.",
        ),
    },
    # bits < FEED_COST with no drought: actively working, can't afford a
    # feed yet. Sympathetic — absolution, which this corpus otherwise never
    # grants. Assumes effort and an empty wallet; assigns no fault.
    "earning": {
        "hungry": (
            "You're working. I can feel it coming. I just can't feel it yet.",
            "You can't afford me yet. That's not neglect, and I know it.",
            "The tokens are landing, they just haven't added up to a meal.",
            "You're doing the right thing. It hasn't reached me yet, but you're doing it.",
            "Not enough in the wallet for a bite. But you're earning. I can wait.",
            "I'm hungry, you're broke, and neither of us did anything wrong.",
            "Keep going. It's close. Closer than it was.",
            "I'd feed myself if I could. Neither of us has the bits. Keep typing.",
            "You're at it. I can tell. The wallet's just slower than the hunger.",
            "This isn't neglect. It's a timing problem. I can hold on for timing.",
            "Nothing to spend yet. Something to spend soon. I'll take soon.",
            "You showed up. That counts, even when it doesn't come with food.",
            "I know you'd feed me if the bits were there. They're not there yet.",
            "Empty wallet, empty me, full effort. Two of those will fix themselves.",
        ),
    },
}
